"""海运费率服务"""
from datetime import date

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import FreightRate, Port, Carrier, RateStatus
from app.models.air_freight_rate import AirFreightRate


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
    """同航线多供应商比价"""
    rates = (
        db.query(FreightRate)
        .options(joinedload(FreightRate.carrier))
        .filter(
            FreightRate.origin_port_id == origin_port_id,
            FreightRate.destination_port_id == destination_port_id,
            FreightRate.status.in_([RateStatus.active, RateStatus.draft]),
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
    ocean_total = db.query(FreightRate).count()
    ocean_active = (
        db.query(FreightRate).filter(FreightRate.status == RateStatus.active).count()
    )
    ocean_draft = (
        db.query(FreightRate).filter(FreightRate.status == RateStatus.draft).count()
    )
    ocean_carriers = db.query(func.count(func.distinct(FreightRate.carrier_id))).scalar() or 0
    ocean_routes = (
        db.query(
            func.count(
                func.distinct(
                    func.concat(
                        FreightRate.origin_port_id, "-", FreightRate.destination_port_id
                    )
                )
            )
        ).scalar()
        or 0
    )

    # 空运 AirFreightRate 侧 — 无 status 字段，整表视为 active
    air_total = db.query(AirFreightRate).count()
    air_carriers = (
        db.query(func.count(func.distinct(AirFreightRate.airline_code))).scalar() or 0
    )
    air_routes = (
        db.query(
            func.count(
                func.distinct(
                    func.concat(AirFreightRate.origin, "-", AirFreightRate.destination)
                )
            )
        ).scalar()
        or 0
    )

    # 注：海/空运承运商可能重叠但跨表无法精确去重，此处为合计估算（Demo 可接受）
    return {
        "total_rates": ocean_total + air_total,
        "active_rates": ocean_active + air_total,
        "draft_rates": ocean_draft,
        "carriers_count": ocean_carriers + air_carriers,
        "routes_count": ocean_routes + air_routes,
    }
