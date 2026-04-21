from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from app.services.step1_rates.entities import (
    ParsedRateBatch,
    ParsedRateRecord,
    RateSourceKind,
    Step1FileType,
    Step1RateRow,
)

_ROW_KEYS = {
    "carrier_id",
    "carrier_name",
    "origin_port_id",
    "origin_port_name",
    "destination_port_id",
    "destination_port_name",
    "rate_level",
    "service_code",
    "container_20gp",
    "container_40gp",
    "container_40hq",
    "container_45",
    "baf_20",
    "baf_40",
    "lss_20",
    "lss_40",
    "lss_cic",
    "baf",
    "ebs",
    "yas_caf",
    "booking_charge",
    "thc",
    "doc",
    "isps",
    "equipment_mgmt",
    "freight_per_cbm",
    "freight_per_ton",
    "sailing_day",
    "via",
    "transit_time_text",
    "airline_code",
    "service_desc",
    "effective_week_start",
    "effective_week_end",
    "price_day1",
    "price_day2",
    "price_day3",
    "price_day4",
    "price_day5",
    "price_day6",
    "price_day7",
    "record_kind",
    "currency",
    "valid_from",
    "valid_to",
    "transit_days",
    "is_direct",
    "remarks",
    "source_type",
    "source_file",
    "upload_batch_id",
    "batch_id",
}


def coerce_source_kind(value: RateSourceKind | str | None, default: RateSourceKind) -> RateSourceKind:
    if isinstance(value, RateSourceKind):
        return value
    if isinstance(value, str):
        try:
            return RateSourceKind(value)
        except ValueError:
            return default
    return default


def coerce_file_type(value: Step1FileType | str | None, default: Step1FileType) -> Step1FileType:
    if isinstance(value, Step1FileType):
        return value
    if isinstance(value, str):
        try:
            return Step1FileType(value)
        except ValueError:
            return default
    return default


def legacy_row_to_step1(row: Mapping[str, Any], default_source_kind: RateSourceKind) -> Step1RateRow:
    extras = {key: value for key, value in row.items() if key not in _ROW_KEYS}
    return Step1RateRow(
        carrier_id=row.get("carrier_id"),
        carrier_name=row.get("carrier_name"),
        origin_port_id=row.get("origin_port_id"),
        origin_port_name=row.get("origin_port_name"),
        destination_port_id=row.get("destination_port_id"),
        destination_port_name=row.get("destination_port_name"),
        rate_level=row.get("rate_level"),
        service_code=row.get("service_code"),
        container_20gp=row.get("container_20gp"),
        container_40gp=row.get("container_40gp"),
        container_40hq=row.get("container_40hq"),
        container_45=row.get("container_45"),
        baf_20=row.get("baf_20"),
        baf_40=row.get("baf_40"),
        lss_20=row.get("lss_20"),
        lss_40=row.get("lss_40"),
        lss_cic=row.get("lss_cic"),
        baf=row.get("baf"),
        ebs=row.get("ebs"),
        yas_caf=row.get("yas_caf"),
        booking_charge=row.get("booking_charge"),
        thc=row.get("thc"),
        doc=row.get("doc"),
        isps=row.get("isps"),
        equipment_mgmt=row.get("equipment_mgmt"),
        freight_per_cbm=row.get("freight_per_cbm"),
        freight_per_ton=row.get("freight_per_ton"),
        sailing_day=row.get("sailing_day"),
        via=row.get("via"),
        transit_time_text=row.get("transit_time_text"),
        airline_code=row.get("airline_code"),
        service_desc=row.get("service_desc"),
        effective_week_start=row.get("effective_week_start"),
        effective_week_end=row.get("effective_week_end"),
        price_day1=row.get("price_day1"),
        price_day2=row.get("price_day2"),
        price_day3=row.get("price_day3"),
        price_day4=row.get("price_day4"),
        price_day5=row.get("price_day5"),
        price_day6=row.get("price_day6"),
        price_day7=row.get("price_day7"),
        record_kind=row.get("record_kind"),
        currency=row.get("currency", "USD"),
        valid_from=row.get("valid_from"),
        valid_to=row.get("valid_to"),
        transit_days=row.get("transit_days"),
        is_direct=row.get("is_direct", True),
        remarks=row.get("remarks"),
        source_type=row.get("source_type", default_source_kind.value),
        source_file=row.get("source_file"),
        upload_batch_id=row.get("upload_batch_id") or row.get("batch_id"),
        extras=extras,
    )


def legacy_row_to_parsed_record(
    row: Mapping[str, Any],
    *,
    default_file_type: Step1FileType,
    default_source_kind: RateSourceKind = RateSourceKind.excel,
) -> ParsedRateRecord:
    step1_row = legacy_row_to_step1(row, default_source_kind)
    extras = dict(step1_row.extras)
    extras.setdefault("file_type", default_file_type.value)
    payload = {
        field.name: getattr(step1_row, field.name)
        for field in fields(Step1RateRow)
        if field.name != "extras"
    }
    return ParsedRateRecord(**payload, extras=extras)


def legacy_payload_to_parsed_batch(
    payload: Mapping[str, Any],
    *,
    file_type: Step1FileType,
    adapter_key: str | None = None,
    source_file: str | None = None,
    effective_from: Any = None,
    effective_to: Any = None,
) -> ParsedRateBatch:
    if "records" in payload:
        records = [
            legacy_row_to_parsed_record(row, default_file_type=file_type)
            for row in payload.get("records", []) or []
        ]
    else:
        records: list[ParsedRateRecord] = []
        for row in payload.get("parsed_rows", []) or []:
            records.append(legacy_row_to_parsed_record(row, default_file_type=file_type))
        for raw_sheet in payload.get("sheets", []) or []:
            for row in raw_sheet.get("parsed_rows", []) or []:
                records.append(legacy_row_to_parsed_record(row, default_file_type=file_type))

    metadata = dict(payload)
    metadata.pop("records", None)
    metadata.pop("parsed_rows", None)
    metadata.pop("sheets", None)
    metadata.pop("warnings", None)
    metadata.pop("file_type", None)
    metadata.pop("source_file", None)
    metadata.pop("effective_from", None)
    metadata.pop("effective_to", None)

    return ParsedRateBatch(
        file_type=coerce_file_type(payload.get("file_type"), file_type),
        source_file=source_file or payload.get("source_file") or payload.get("file_name") or "unknown",
        effective_from=payload.get("effective_from", effective_from),
        effective_to=payload.get("effective_to", effective_to),
        records=records,
        warnings=list(payload.get("warnings", []) or []),
        adapter_key=adapter_key or payload.get("adapter_key"),
        metadata=metadata,
    )
