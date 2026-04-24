"""Step1 激活映射器 — ParsedRateRecord → ORM 对象（纯函数）。

见架构任务单 §5 映射表。
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import (
    AirFreightRate,
    AirSurcharge,
    Carrier,
    FreightRate,
    Port,
    RateStatus,
    SourceType,
)
from app.services.step1_rates.entities import ParsedRateRecord


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
    return db.query(Port).filter(Port.name_cn.ilike(f"%{name}%")).first()
