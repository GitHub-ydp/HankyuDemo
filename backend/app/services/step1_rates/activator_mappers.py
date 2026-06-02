"""Step1 激活映射器 — ParsedRateRecord → ORM 对象（纯函数）。

见架构任务单 §5 映射表。
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AirFreightRate,
    AirSurcharge,
    Carrier,
    FreightRate,
    LclRate,
    Port,
    RateStatus,
    SourceType,
)
from app.services.rate_parser import _resolve_port as _rp_resolve_port
from app.services.step1_rates.entities import ParsedRateRecord
from app.services.step1_rates.port_normalizer import canonicalize


class ActivationError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        row_index: int | None = None,
        record_kind: str | None = None,
    ) -> None:
        super().__init__(f"[{code}] row={row_index} kind={record_kind}: {detail}")
        self.code = code
        self.detail = detail
        self.row_index = row_index
        self.record_kind = record_kind


def _row_index(record: ParsedRateRecord) -> int | None:
    try:
        return record.extras.get("row_index")
    except AttributeError:
        return None


def to_air_freight_rate(record: ParsedRateRecord, batch_id: uuid.UUID) -> AirFreightRate:
    return AirFreightRate(
        origin=record.origin_port_name or "",
        destination=record.destination_port_name or "",
        airline_code=record.airline_code,
        service_desc=record.service_desc,
        effective_week_start=record.effective_week_start,
        effective_week_end=record.effective_week_end,
        price_day1=record.price_day1,
        price_day2=record.price_day2,
        price_day3=record.price_day3,
        price_day4=record.price_day4,
        price_day5=record.price_day5,
        price_day6=record.price_day6,
        price_day7=record.price_day7,
        currency=record.currency or "CNY",
        remark=record.remarks,
        batch_id=batch_id,
    )


def to_air_surcharge(record: ParsedRateRecord, batch_id: uuid.UUID) -> AirSurcharge:
    extras = record.extras or {}
    return AirSurcharge(
        area=extras.get("area"),
        from_region=extras.get("from_region"),
        airline_code=record.airline_code,
        effective_date=record.valid_from,
        myc_min=extras.get("myc_min_value"),
        myc_fee_per_kg=extras.get("myc_fee_per_kg"),
        msc_min=extras.get("msc_min_value"),
        msc_fee_per_kg=extras.get("msc_fee_per_kg"),
        destination_scope=extras.get("destination_scope"),
        remarks=record.remarks,
        currency=record.currency or "CNY",
        batch_id=batch_id,
    )


def to_freight_rate_from_ocean(
    record: ParsedRateRecord,
    batch_id: uuid.UUID,
    db: Session,
    *,
    source_file: str | None = None,
) -> FreightRate:
    carrier_id = _lookup_carrier(db, record.carrier_name, record)
    origin_port_id = record.origin_port_id
    destination_port_id = record.destination_port_id

    if origin_port_id is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"origin_port_id missing; origin_port_name='{record.origin_port_name}'",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    if destination_port_id is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"destination_port_id missing; destination_port_name='{record.destination_port_name}'",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )

    return FreightRate(
        carrier_id=carrier_id,
        origin_port_id=origin_port_id,
        destination_port_id=destination_port_id,
        service_code=None,
        container_20gp=record.container_20gp,
        container_40gp=record.container_40gp,
        container_40hq=record.container_40hq,
        container_45=record.container_45,
        baf_20=record.baf_20,
        baf_40=record.baf_40,
        lss_20=record.lss_20,
        lss_40=record.lss_40,
        lss_cic=record.lss_cic,
        baf=record.baf,
        ebs=record.ebs,
        yas_caf=record.yas_caf,
        booking_charge=record.booking_charge,
        thc=record.thc,
        doc=record.doc,
        isps=record.isps,
        equipment_mgmt=record.equipment_mgmt,
        currency=record.currency or "USD",
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        sailing_day=record.sailing_day,
        via=record.via,
        transit_time_text=record.transit_time_text,
        remarks=record.remarks,
        source_type=SourceType.excel,
        source_file=source_file or record.source_file,
        batch_id=batch_id,
        status=RateStatus.active,
        rate_level=None,
    )


def to_freight_rate_from_ngb(
    record: ParsedRateRecord,
    batch_id: uuid.UUID,
    db: Session,
    *,
    source_file: str | None = None,
) -> FreightRate:
    carrier_id = _lookup_carrier(db, record.carrier_name, record)
    origin_port = _resolve_port(db, record.origin_port_name)
    if origin_port is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"origin port '{record.origin_port_name}' not found in ports dict",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    destination_port = _resolve_port(db, record.destination_port_name)
    if destination_port is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"destination port '{record.destination_port_name}' not found in ports dict",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )

    return FreightRate(
        carrier_id=carrier_id,
        origin_port_id=origin_port.id,
        destination_port_id=destination_port.id,
        service_code=None,
        container_20gp=record.container_20gp,
        container_40gp=record.container_40gp,
        container_40hq=record.container_40hq,
        container_45=None,
        currency=record.currency or "USD",
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        remarks=record.remarks,
        source_type=SourceType.excel,
        source_file=source_file or record.source_file,
        batch_id=batch_id,
        status=RateStatus.active,
        rate_level=record.rate_level,
    )


def to_lcl_rate(
    record: ParsedRateRecord,
    batch_id: uuid.UUID,
    db: Session,
    *,
    source_file: str | None = None,
) -> LclRate:
    """LCL record（kind=lcl / ocean_ngb_lcl）→ LclRate。

    LclRate 无 carrier 概念，只解析起运/目的港（与 NGB FCL 同用 _resolve_port）。
    """
    # LCL 港名常含 "EN/中文" 或终端/别名变体，用 rate_parser 的强解析器（拆 "/"、别名表、
    # 去括号、折叠空格），与 ocean adapter FCL 解析能力一致
    origin_port = _rp_resolve_port(record.origin_port_name, db)
    if origin_port is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"origin port '{record.origin_port_name}' not found in ports dict",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    destination_port = _rp_resolve_port(record.destination_port_name, db)
    if destination_port is None:
        raise ActivationError(
            code="PORT_NOT_FOUND",
            detail=f"destination port '{record.destination_port_name}' not found in ports dict",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    extras = record.extras or {}
    return LclRate(
        origin_port_id=origin_port.id,
        destination_port_id=destination_port.id,
        freight_per_cbm=record.freight_per_cbm,
        freight_per_ton=record.freight_per_ton,
        currency=record.currency or "USD",
        lss=_clip(extras.get("lss_raw") or extras.get("lss"), 50),
        ebs=_clip(extras.get("ebs_raw") or extras.get("ebs"), 50),
        cic=_clip(extras.get("cic_raw") or extras.get("cic"), 50),
        ams_aci_ens=_clip(extras.get("ams_aci_ens") or extras.get("ams_raw"), 50),
        sailing_day=_clip(record.sailing_day, 50),
        via=_clip(record.via, 100),
        transit_time_text=_clip(record.transit_time_text, 100),
        remarks=record.remarks,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        batch_id=batch_id,
    )


def _clip(value, maxlen: int):
    """把可能超长 / 非字符串的值裁剪成 String(maxlen) 可存的文本；None 透传。"""
    if value is None:
        return None
    s = str(value).strip()
    return s[:maxlen] if s else None


def _lookup_carrier(db: Session, carrier_name: str | None, record: ParsedRateRecord) -> int:
    if not carrier_name:
        raise ActivationError(
            code="CARRIER_NOT_FOUND",
            detail="carrier_name is empty",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    name = carrier_name.strip()
    carrier = db.query(Carrier).filter(Carrier.code == name).first()
    if carrier is None:
        carrier = (
            db.query(Carrier)
            .filter(Carrier.name_en.ilike(f"%{name}%"))
            .first()
        )
    if carrier is None:
        carrier = (
            db.query(Carrier)
            .filter(Carrier.code.ilike(f"%{name}%"))
            .first()
        )
    # 归一兜底：折叠空格，对 code / name_en(同样折叠空格)做包含匹配
    # → 修 "XIN JIAN ZHEN"→XINJIANZHEN 等空格变体
    norm = re.sub(r"\s+", "", name)
    if carrier is None and len(norm) >= 2:
        carrier = (
            db.query(Carrier)
            .filter(func.replace(Carrier.code, " ", "").ilike(f"%{norm}%"))
            .first()
        )
    if carrier is None and len(norm) >= 2:
        carrier = (
            db.query(Carrier)
            .filter(func.replace(Carrier.name_en, " ", "").ilike(f"%{norm}%"))
            .first()
        )
    if carrier is None:
        raise ActivationError(
            code="CARRIER_NOT_FOUND",
            detail=f"carrier '{carrier_name}' not found in carriers dict",
            row_index=_row_index(record),
            record_kind=record.record_kind,
        )
    return carrier.id


def _resolve_port(db: Session, name_raw: str | None) -> Port | None:
    if not name_raw or not str(name_raw).strip():
        return None
    name = str(name_raw).strip()
    if len(name) == 5 and name.isalpha() and name.isupper():
        port = db.query(Port).filter(Port.un_locode == name).first()
        if port is not None:
            return port
    port = (
        db.query(Port)
        .filter(Port.name_en.ilike(f"%{name}%"))
        .first()
    )
    if port is not None:
        return port
    port = db.query(Port).filter(Port.name_cn.ilike(f"%{name}%")).first()
    if port is not None:
        return port
    # 归一兜底：去括号注解(如 "CHICAGO (via LAX)") + 折叠所有空格，
    # 对 name_en(同样折叠空格)做包含匹配 → 修 "HAI PHONG"/"HONGKONG"/"PASIRGUDANG" 等空格变体
    norm = re.sub(r"\(.*?\)", "", name)
    norm = re.sub(r"\s+", "", norm)
    if len(norm) >= 3:
        port = (
            db.query(Port)
            .filter(func.replace(Port.name_en, " ", "").ilike(f"%{norm}%"))
            .first()
        )
        if port is not None:
            return port
    # 双语合并名 "English/中文"(如 KMTC 的 "Shanghai/上海"、"Busan/釜山")：整串匹配不到时
    # 按分隔符拆段，逐段递归再试，命中任一即可。拆出的段不含分隔符，递归只下探一层。
    parts = [p.strip() for p in re.split(r"[/／|]", name) if p.strip()]
    if len(parts) > 1:
        for part in parts:
            hit = _resolve_port(db, part)
            if hit is not None:
                return hit
    # 规范化兜底：别名(PUSAN→BUSAN)/去尾缀(CITY/PORT)/去标点折叠后，对 alnum 折叠的 name_en 做包含匹配。
    # 解决 "PUSAN"/"KAOHSIUNG CITY"/"SAINT LOUIS"(对 "St. Louis" 的句点) 等变体。
    canon = canonicalize(name)
    if len(canon) >= 3:
        folded = func.replace(
            func.replace(func.replace(Port.name_en, " ", ""), ".", ""), "-", ""
        )
        port = db.query(Port).filter(folded.ilike(f"%{canon}%")).first()
        if port is not None:
            return port
    return None
