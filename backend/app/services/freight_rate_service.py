"""海运费率服务"""
from datetime import date
from typing import Any

from sqlalchemy import JSON, String, and_, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    AirSurcharge,
    Carrier,
    FreightRate,
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
    LclRate,
    Port,
    RateStatus,
)
from app.models.air_freight_rate import AirFreightRate
from app.models.air_tier_rate import AirTierRate
from app.schemas.freight_rate import RateType


def get_rates(
    db: Session,
    origin_port_id: int | None = None,
    destination_port_id: int | None = None,
    carrier_id: int | None = None,
    origin_keyword: str | None = None,
    destination_keyword: str | None = None,
    carrier_keyword: str | None = None,
    status: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[FreightRate], int]:
    """多条件查询费率"""
    q = db.query(FreightRate)

    if origin_port_id:
        q = q.filter(FreightRate.origin_port_id == origin_port_id)
    if destination_port_id:
        q = q.filter(FreightRate.destination_port_id == destination_port_id)
    if carrier_id:
        q = q.filter(FreightRate.carrier_id == carrier_id)
    if status:
        q = q.filter(FreightRate.status == status)
    if active_only:
        today = date.today()
        q = q.filter(
            FreightRate.status == RateStatus.active,
            or_(FreightRate.valid_to == None, FreightRate.valid_to >= today),
        )

    # 关键词搜索（跨关联表）
    if origin_keyword:
        like = f"%{origin_keyword}%"
        q = q.join(FreightRate.origin_port).filter(
            or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
        )
    if destination_keyword:
        like = f"%{destination_keyword}%"
        origin_joined = origin_keyword is not None
        if origin_joined:
            # 需要使用 aliased 或分开 join
            dest_port = db.query(Port).filter(
                or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
            ).all()
            dest_ids = [p.id for p in dest_port]
            if dest_ids:
                q = q.filter(FreightRate.destination_port_id.in_(dest_ids))
            else:
                q = q.filter(False)  # 没有匹配的目的港
        else:
            q = q.join(FreightRate.destination_port).filter(
                or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
            )
    if carrier_keyword:
        like = f"%{carrier_keyword}%"
        q = q.join(FreightRate.carrier).filter(
            or_(Carrier.name_en.ilike(like), Carrier.name_cn.ilike(like), Carrier.code.ilike(like))
        )

    total = q.count()
    items = (
        q.options(
            joinedload(FreightRate.carrier),
            joinedload(FreightRate.origin_port),
            joinedload(FreightRate.destination_port),
        )
        .order_by(FreightRate.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


# 运价总览判重口径(邓老师 2026-06-10)：除运价编号(id)与批次/来源文件等元数据列外，
# 业务字段全部相同 → 视为重复，列表只保留 id 最大(最新导入)的一条。
_DEDUP_METADATA_COLS = {
    "id",
    "batch_id",
    "upload_batch_id",
    "source_file",
    "created_at",
    "updated_at",
}


def _dedup_keep_latest(q, model):
    """对已带筛选条件的 query 按业务列去重，返回收窄后的同源 query。

    用窗口函数在筛选范围内分组(业务列全同为一组)，每组保留 id 最大的一行；
    去重发生在 count/分页之前，total 与页内容一致。JSON 列(如 tier_prices)
    无通用等值比较，cast 成文本参与分组。
    """
    partition = []
    for col in model.__table__.columns:
        if col.name in _DEDUP_METADATA_COLS:
            continue
        partition.append(cast(col, String) if isinstance(col.type, JSON) else col)
    rn = (
        func.row_number()
        .over(partition_by=partition, order_by=model.id.desc())
        .label("rn")
    )
    sub = q.with_entities(model.id.label("id"), rn).subquery()
    keep_ids = select(sub.c.id).where(sub.c.rn == 1).scalar_subquery()
    return q.filter(model.id.in_(keep_ids))


def list_rates_by_type(
    db: Session,
    rate_type: RateType,
    *,
    # 海运族（ocean_fcl / ocean_ngb / lcl）
    origin_port_id: int | None = None,
    destination_port_id: int | None = None,
    carrier_id: int | None = None,
    origin_keyword: str | None = None,
    destination_keyword: str | None = None,
    carrier_keyword: str | None = None,
    status: str | None = None,
    # 空运族（air_weekly / air_surcharge）
    origin_text: str | None = None,
    destination_text: str | None = None,
    airline_code: str | None = None,
    # 通用
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Any], int]:
    """按类型分派查询。返回 items 为对应 Model 实例列表，API 层再按 schema 序列化。"""
    if rate_type in (RateType.ocean_fcl, RateType.ocean_ngb):
        return _list_ocean_like(
            db,
            rate_type,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
            carrier_id=carrier_id,
            origin_keyword=origin_keyword,
            destination_keyword=destination_keyword,
            carrier_keyword=carrier_keyword,
            status=status,
            page=page,
            page_size=page_size,
        )
    if rate_type == RateType.air_weekly:
        return _list_air_weekly(
            db,
            origin_text=origin_text,
            destination_text=destination_text,
            airline_code=airline_code,
            page=page,
            page_size=page_size,
        )
    if rate_type == RateType.air_tier:
        return _list_air_tier(
            db,
            origin_text=origin_text,
            destination_text=destination_text,
            airline_code=airline_code,
            page=page,
            page_size=page_size,
        )
    if rate_type == RateType.air_surcharge:
        return _list_air_surcharge(
            db,
            airline_code=airline_code,
            page=page,
            page_size=page_size,
        )
    if rate_type == RateType.lcl:
        return _list_lcl(
            db,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
            page=page,
            page_size=page_size,
        )
    raise ValueError(f"Unknown rate_type: {rate_type}")


def _list_ocean_like(
    db: Session,
    rate_type: RateType,
    *,
    origin_port_id: int | None = None,
    destination_port_id: int | None = None,
    carrier_id: int | None = None,
    origin_keyword: str | None = None,
    destination_keyword: str | None = None,
    carrier_keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[FreightRate], int]:
    """Ocean FCL / NGB 共享 FreightRate 表，区分规则见 §0.2.4。"""
    q = db.query(FreightRate).outerjoin(
        ImportBatch, FreightRate.batch_id == ImportBatch.batch_id
    )
    if rate_type == RateType.ocean_fcl:
        # Ocean：排除 NGB；batch_id IS NULL 的老数据兜底归入 ocean_fcl
        q = q.filter(
            or_(
                ImportBatch.file_type == ImportBatchFileType.ocean,
                FreightRate.batch_id.is_(None),
            )
        )
    else:
        q = q.filter(ImportBatch.file_type == ImportBatchFileType.ocean_ngb)

    if origin_port_id:
        q = q.filter(FreightRate.origin_port_id == origin_port_id)
    if destination_port_id:
        q = q.filter(FreightRate.destination_port_id == destination_port_id)
    if carrier_id:
        q = q.filter(FreightRate.carrier_id == carrier_id)
    if status:
        q = q.filter(FreightRate.status == status)

    if origin_keyword:
        like = f"%{origin_keyword}%"
        q = q.join(FreightRate.origin_port).filter(
            or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
        )
    if destination_keyword:
        like = f"%{destination_keyword}%"
        if origin_keyword:
            dest_ports = db.query(Port.id).filter(
                or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
            ).all()
            dest_ids = [p.id for p in dest_ports]
            q = q.filter(FreightRate.destination_port_id.in_(dest_ids)) if dest_ids else q.filter(False)
        else:
            q = q.join(FreightRate.destination_port).filter(
                or_(Port.name_en.ilike(like), Port.name_cn.ilike(like), Port.un_locode.ilike(like))
            )
    if carrier_keyword:
        like = f"%{carrier_keyword}%"
        q = q.join(FreightRate.carrier).filter(
            or_(Carrier.name_en.ilike(like), Carrier.name_cn.ilike(like), Carrier.code.ilike(like))
        )

    q = _dedup_keep_latest(q, FreightRate)
    total = q.count()
    items = (
        q.options(
            joinedload(FreightRate.carrier),
            joinedload(FreightRate.origin_port),
            joinedload(FreightRate.destination_port),
        )
        .order_by(FreightRate.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _list_air_weekly(
    db: Session,
    *,
    origin_text: str | None = None,
    destination_text: str | None = None,
    airline_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AirFreightRate], int]:
    """空运周价列表：返回所有已导入行（含已过周末的最近导入批次）。

    与 Ocean 一致，不再按 effective_week_end >= today 过滤；
    在效语义由 ImportBatch.status（active/superseded）在激活链路上保证。
    """
    q = db.query(AirFreightRate)
    if origin_text:
        q = q.filter(AirFreightRate.origin.ilike(f"%{origin_text}%"))
    if destination_text:
        q = q.filter(AirFreightRate.destination.ilike(f"%{destination_text}%"))
    if airline_code:
        q = q.filter(AirFreightRate.airline_code == airline_code)

    q = _dedup_keep_latest(q, AirFreightRate)
    total = q.count()
    items = (
        q.order_by(AirFreightRate.effective_week_start.desc().nullslast(), AirFreightRate.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _list_air_tier(
    db: Session,
    *,
    origin_text: str | None = None,
    destination_text: str | None = None,
    airline_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AirTierRate], int]:
    """空运重量档列表：返回所有已导入档位行（航司过滤走 AirTierRate.carrier）。"""
    q = db.query(AirTierRate)
    if origin_text:
        q = q.filter(AirTierRate.origin.ilike(f"%{origin_text}%"))
    if destination_text:
        q = q.filter(AirTierRate.destination.ilike(f"%{destination_text}%"))
    if airline_code:
        q = q.filter(AirTierRate.carrier == airline_code)

    q = _dedup_keep_latest(q, AirTierRate)
    total = q.count()
    items = (
        q.order_by(
            AirTierRate.origin.asc(),
            AirTierRate.destination.asc(),
            AirTierRate.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _list_air_surcharge(
    db: Session,
    *,
    airline_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AirSurcharge], int]:
    q = db.query(AirSurcharge)
    if airline_code:
        q = q.filter(AirSurcharge.airline_code == airline_code)
    q = _dedup_keep_latest(q, AirSurcharge)
    total = q.count()
    items = (
        q.order_by(AirSurcharge.effective_date.desc().nullslast(), AirSurcharge.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _list_lcl(
    db: Session,
    *,
    origin_port_id: int | None = None,
    destination_port_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[LclRate], int]:
    q = db.query(LclRate)
    if origin_port_id:
        q = q.filter(LclRate.origin_port_id == origin_port_id)
    if destination_port_id:
        q = q.filter(LclRate.destination_port_id == destination_port_id)
    q = _dedup_keep_latest(q, LclRate)
    total = q.count()
    items = (
        q.options(joinedload(LclRate.origin_port), joinedload(LclRate.destination_port))
        .order_by(LclRate.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_rate(db: Session, rate_id: int) -> FreightRate | None:
    return (
        db.query(FreightRate)
        .options(
            joinedload(FreightRate.carrier),
            joinedload(FreightRate.origin_port),
            joinedload(FreightRate.destination_port),
        )
        .filter(FreightRate.id == rate_id)
        .first()
    )


def compare_rates(
    db: Session,
    origin_port_id: int,
    destination_port_id: int,
) -> list[dict]:
    """同航线多供应商比价（P0-3 即时修复：加 valid_to 过滤）。"""
    today = date.today()
    rates = (
        db.query(FreightRate)
        .options(joinedload(FreightRate.carrier))
        .filter(
            FreightRate.origin_port_id == origin_port_id,
            FreightRate.destination_port_id == destination_port_id,
            FreightRate.status.in_([RateStatus.active, RateStatus.draft]),
            or_(FreightRate.valid_to == None, FreightRate.valid_to >= today),  # noqa: E711
        )
        .order_by(FreightRate.container_20gp.asc().nullslast())
        .all()
    )

    result = []
    for r in rates:
        result.append({
            "rate_id": r.id,
            "carrier_code": r.carrier.code if r.carrier else "",
            "carrier_name": f"{r.carrier.name_en} / {r.carrier.name_cn}" if r.carrier else "",
            "container_20gp": r.container_20gp,
            "container_40gp": r.container_40gp,
            "container_40hq": r.container_40hq,
            "container_45": r.container_45,
            "baf_20": r.baf_20,
            "baf_40": r.baf_40,
            "lss_20": r.lss_20,
            "lss_40": r.lss_40,
            "currency": r.currency,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
            "transit_days": r.transit_days,
            "is_direct": r.is_direct,
            "source_type": r.source_type.value if r.source_type else None,
            "status": r.status.value if r.status else None,
        })
    return result


def compare_rates_by_type(
    db: Session,
    rate_type: RateType,
    *,
    origin_port_id: int | None = None,
    destination_port_id: int | None = None,
    origin_text: str | None = None,
    destination_text: str | None = None,
) -> dict:
    """按类型分派比价。返回 {origin, destination, rates, total}。"""
    if rate_type in (RateType.ocean_fcl, RateType.ocean_ngb):
        return _compare_ocean_like(
            db,
            rate_type,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
        )
    if rate_type == RateType.air_weekly:
        return _compare_air_weekly(
            db,
            origin_text=origin_text,
            destination_text=destination_text,
        )
    if rate_type == RateType.air_tier:
        return _compare_air_tier(
            db,
            origin_text=origin_text,
            destination_text=destination_text,
        )
    if rate_type == RateType.lcl:
        return _compare_lcl(
            db,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
        )
    if rate_type == RateType.air_surcharge:
        raise ValueError("air_surcharge 不支持比价（业务需求明确）")
    raise ValueError(f"Unknown rate_type: {rate_type}")


def _compare_ocean_like(
    db: Session,
    rate_type: RateType,
    *,
    origin_port_id: int | None,
    destination_port_id: int | None,
) -> dict:
    today = date.today()
    origin = db.query(Port).filter(Port.id == origin_port_id).first() if origin_port_id else None
    destination = (
        db.query(Port).filter(Port.id == destination_port_id).first()
        if destination_port_id
        else None
    )

    q = (
        db.query(FreightRate)
        .options(joinedload(FreightRate.carrier))
        .outerjoin(ImportBatch, FreightRate.batch_id == ImportBatch.batch_id)
        .filter(
            FreightRate.status.in_([RateStatus.active, RateStatus.draft]),
            or_(FreightRate.valid_to == None, FreightRate.valid_to >= today),  # noqa: E711
        )
    )
    if origin_port_id:
        q = q.filter(FreightRate.origin_port_id == origin_port_id)
    if destination_port_id:
        q = q.filter(FreightRate.destination_port_id == destination_port_id)
    if rate_type == RateType.ocean_fcl:
        q = q.filter(
            or_(
                ImportBatch.file_type == ImportBatchFileType.ocean,
                FreightRate.batch_id.is_(None),
            )
        )
    else:
        q = q.filter(ImportBatch.file_type == ImportBatchFileType.ocean_ngb)

    rates = q.order_by(FreightRate.container_20gp.asc().nullslast()).all()

    items = []
    for r in rates:
        items.append({
            "rate_id": r.id,
            "carrier_code": r.carrier.code if r.carrier else "",
            "carrier_name": f"{r.carrier.name_en} / {r.carrier.name_cn}" if r.carrier else "",
            "container_20gp": r.container_20gp,
            "container_40gp": r.container_40gp,
            "container_40hq": r.container_40hq,
            "baf_20": r.baf_20,
            "baf_40": r.baf_40,
            "currency": r.currency,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
            "transit_days": r.transit_days,
            "is_direct": r.is_direct,
            "source_type": r.source_type.value if r.source_type else None,
            "status": r.status.value if r.status else None,
        })

    return {
        "origin": origin,
        "destination": destination,
        "rates": items,
        "total": len(items),
    }


def _compare_air_weekly(
    db: Session,
    *,
    origin_text: str | None,
    destination_text: str | None,
) -> dict:
    # 与 _list_air_weekly 一致：不再按 effective_week_end >= today 过滤，
    # 让最近一次导入（即便周末已过）也能在比价页面看到。
    q = db.query(AirFreightRate)
    if origin_text:
        q = q.filter(AirFreightRate.origin.ilike(f"{origin_text}%"))
    if destination_text:
        q = q.filter(AirFreightRate.destination.ilike(f"{destination_text}%"))

    rates = q.order_by(AirFreightRate.price_day1.asc().nullslast(), AirFreightRate.id.asc()).all()

    items = []
    for r in rates:
        items.append({
            "rate_id": r.id,
            "airline_code": r.airline_code,
            "service_desc": r.service_desc,
            "effective_week_start": r.effective_week_start,
            "effective_week_end": r.effective_week_end,
            "price_day1": r.price_day1,
            "price_day2": r.price_day2,
            "price_day3": r.price_day3,
            "price_day4": r.price_day4,
            "price_day5": r.price_day5,
            "price_day6": r.price_day6,
            "price_day7": r.price_day7,
            "currency": r.currency,
            "remark": r.remark,
        })

    return {
        "origin": origin_text or "",
        "destination": destination_text or "",
        "rates": items,
        "total": len(items),
    }


def _compare_air_tier(
    db: Session,
    *,
    origin_text: str | None,
    destination_text: str | None,
) -> dict:
    """空运重量档比价：同航线多航司的档位价一览。"""
    q = db.query(AirTierRate)
    if origin_text:
        q = q.filter(AirTierRate.origin.ilike(f"{origin_text}%"))
    if destination_text:
        q = q.filter(AirTierRate.destination.ilike(f"{destination_text}%"))

    rates = q.order_by(AirTierRate.carrier.asc().nullslast(), AirTierRate.id.asc()).all()

    items = []
    for r in rates:
        items.append({
            "rate_id": r.id,
            "carrier": r.carrier,
            "service_desc": r.service_desc,
            "tier_prices": {str(k): v for k, v in (r.tier_prices or {}).items()},
            "cargo_class": r.cargo_class,
            "packing": r.packing,
            "density": r.density,
            "effective_from": r.effective_from,
            "effective_to": r.effective_to,
            "currency": r.currency,
            "remark": r.remark,
        })

    return {
        "origin": origin_text or "",
        "destination": destination_text or "",
        "rates": items,
        "total": len(items),
    }


def _compare_lcl(
    db: Session,
    *,
    origin_port_id: int | None,
    destination_port_id: int | None,
) -> dict:
    today = date.today()
    origin = db.query(Port).filter(Port.id == origin_port_id).first() if origin_port_id else None
    destination = (
        db.query(Port).filter(Port.id == destination_port_id).first()
        if destination_port_id
        else None
    )

    q = db.query(LclRate).filter(
        or_(LclRate.valid_to == None, LclRate.valid_to >= today),  # noqa: E711
    )
    if origin_port_id:
        q = q.filter(LclRate.origin_port_id == origin_port_id)
    if destination_port_id:
        q = q.filter(LclRate.destination_port_id == destination_port_id)

    rates = q.order_by(LclRate.freight_per_cbm.asc().nullslast(), LclRate.id.asc()).all()

    items = []
    for r in rates:
        items.append({
            "rate_id": r.id,
            "freight_per_cbm": r.freight_per_cbm,
            "freight_per_ton": r.freight_per_ton,
            "currency": r.currency,
            "lss": r.lss,
            "ebs": r.ebs,
            "cic": r.cic,
            "ams_aci_ens": r.ams_aci_ens,
            "sailing_day": r.sailing_day,
            "via": r.via,
            "transit_time_text": r.transit_time_text,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
        })

    return {
        "origin": origin,
        "destination": destination,
        "rates": items,
        "total": len(items),
    }


def update_rate_status(db: Session, rate_id: int, status: RateStatus) -> FreightRate | None:
    """更新费率状态"""
    rate = db.query(FreightRate).filter(FreightRate.id == rate_id).first()
    if rate:
        rate.status = status
        db.commit()
        db.refresh(rate)
    return rate


def batch_update_status(db: Session, batch_id: str, status: RateStatus) -> int:
    """批量更新同一批次的费率状态"""
    count = (
        db.query(FreightRate)
        .filter(FreightRate.upload_batch_id == batch_id)
        .update({FreightRate.status: status})
    )
    db.commit()
    return count


def delete_rate(db: Session, rate_id: int) -> bool:
    rate = db.query(FreightRate).filter(FreightRate.id == rate_id).first()
    if rate:
        db.delete(rate)
        db.commit()
        return True
    return False


def get_rate_stats(db: Session) -> dict:
    """费率统计信息（海运 FreightRate + 空运 AirFreightRate 合并）。"""
    # 海运 FreightRate 侧（Ocean / Ocean-NGB / 旧导入链路）
    # 与 RateList 同口径去重(业务字段全同只计一次)，Dashboard 总数 = 各 tab 之和
    ocean_total = _dedup_keep_latest(db.query(FreightRate), FreightRate).count()
    ocean_active = _dedup_keep_latest(
        db.query(FreightRate).filter(FreightRate.status == RateStatus.active),
        FreightRate,
    ).count()
    ocean_draft = _dedup_keep_latest(
        db.query(FreightRate).filter(FreightRate.status == RateStatus.draft),
        FreightRate,
    ).count()
    ocean_carriers = db.query(func.count(func.distinct(FreightRate.carrier_id))).scalar() or 0
    ocean_routes = (
        db.query(FreightRate.origin_port_id, FreightRate.destination_port_id)
        .distinct()
        .count()
    )

    # 空运 AirFreightRate 侧 — 与 _list_air_weekly 口径一致：统计全部已导入行(去重)
    air_total = _dedup_keep_latest(db.query(AirFreightRate), AirFreightRate).count()
    air_carriers = (
        db.query(func.count(func.distinct(AirFreightRate.airline_code))).scalar()
        or 0
    )
    air_routes = (
        db.query(AirFreightRate.origin, AirFreightRate.destination)
        .distinct()
        .count()
    )

    # 空运附加费 / 拼箱（5 tab 合计口径，Dashboard 与 RateList 5 tab 之和对齐）
    air_surcharge_total = _dedup_keep_latest(
        db.query(AirSurcharge), AirSurcharge
    ).count()
    lcl_total = _dedup_keep_latest(db.query(LclRate), LclRate).count()

    # 空运重量档（做表→入库 air_tier）— 只数 active 批，与 query_air_tier 口径一致
    air_tier_total = _dedup_keep_latest(
        db.query(AirTierRate)
        .join(ImportBatch, AirTierRate.batch_id == ImportBatch.batch_id)
        .filter(ImportBatch.status == ImportBatchStatus.active),
        AirTierRate,
    ).count()
    air_tier_routes = (
        db.query(AirTierRate.origin, AirTierRate.destination)
        .join(ImportBatch, AirTierRate.batch_id == ImportBatch.batch_id)
        .filter(ImportBatch.status == ImportBatchStatus.active)
        .distinct()
        .count()
    )

    # 注：海/空运承运商可能重叠但跨表无法精确去重，此处为合计估算（Demo 可接受）
    # air_tier 无规范化船司字段（service_desc 是 "CK/MU" 这类路由提示），故不计入 carriers。
    return {
        "total_rates": ocean_total + air_total + air_surcharge_total + lcl_total + air_tier_total,
        "active_rates": ocean_active + air_total + air_surcharge_total + lcl_total + air_tier_total,
        "draft_rates": ocean_draft,
        "carriers_count": ocean_carriers + air_carriers,
        "routes_count": ocean_routes + air_routes + air_tier_routes,
    }
