from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
import uuid


class RateSourceKind(str, Enum):
    excel = "excel"
    email_text = "email_text"
    wechat_image = "wechat_image"


class Step1FileType(str, Enum):
    air = "air"
    ocean = "ocean"
    ocean_ngb = "ocean_ngb"


@dataclass(slots=True)
class Step1ParseRequest:
    """Step1 统一解析入口请求。"""

    source_kind: RateSourceKind
    file_path: str | None = None
    file_name: str | None = None
    text: str | None = None
    extra_context: str | None = None
    parser_hint: str | None = None

    def resolved_file_name(self) -> str:
        if self.file_name:
            return self.file_name
        if self.file_path:
            return Path(self.file_path).name
        return "unknown"

    def require_file_path(self) -> str:
        if not self.file_path:
            raise ValueError("Step1 解析请求缺少 file_path")
        return self.file_path

    def require_text(self) -> str:
        if not self.text:
            raise ValueError("Step1 解析请求缺少 text")
        return self.text


@dataclass(slots=True)
class Step1RateRow:
    """Step1 统一费率中间行结构。"""

    carrier_id: int | None = None
    carrier_name: str | None = None
    origin_port_id: int | None = None
    origin_port_name: str | None = None
    destination_port_id: int | None = None
    destination_port_name: str | None = None
    rate_level: str | None = None
    service_code: str | None = None
    container_20gp: Decimal | None = None
    container_40gp: Decimal | None = None
    container_40hq: Decimal | None = None
    container_45: Decimal | None = None
    baf_20: Decimal | None = None
    baf_40: Decimal | None = None
    lss_20: Decimal | None = None
    lss_40: Decimal | None = None
    lss_cic: Decimal | None = None
    baf: Decimal | None = None
    ebs: Decimal | None = None
    yas_caf: Decimal | None = None
    booking_charge: Decimal | None = None
    thc: Decimal | None = None
    doc: Decimal | None = None
    isps: Decimal | None = None
    equipment_mgmt: Decimal | None = None
    freight_per_cbm: Decimal | None = None
    freight_per_ton: Decimal | None = None
    sailing_day: str | None = None
    via: str | None = None
    transit_time_text: str | None = None
    airline_code: str | None = None
    service_desc: str | None = None
    effective_week_start: date | None = None
    effective_week_end: date | None = None
    price_day1: Decimal | None = None
    price_day2: Decimal | None = None
    price_day3: Decimal | None = None
    price_day4: Decimal | None = None
    price_day5: Decimal | None = None
    price_day6: Decimal | None = None
    price_day7: Decimal | None = None
    record_kind: str | None = None
    currency: str = "USD"
    valid_from: date | None = None
    valid_to: date | None = None
    transit_days: int | None = None
    is_direct: bool = True
    remarks: str | None = None
    source_type: str = RateSourceKind.excel.value
    source_file: str | None = None
    upload_batch_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        payload = {
            "carrier_id": self.carrier_id,
            "carrier_name": self.carrier_name,
            "origin_port_id": self.origin_port_id,
            "origin_port_name": self.origin_port_name,
            "destination_port_id": self.destination_port_id,
            "destination_port_name": self.destination_port_name,
            "rate_level": self.rate_level,
            "service_code": self.service_code,
            "container_20gp": self.container_20gp,
            "container_40gp": self.container_40gp,
            "container_40hq": self.container_40hq,
            "container_45": self.container_45,
            "baf_20": self.baf_20,
            "baf_40": self.baf_40,
            "lss_20": self.lss_20,
            "lss_40": self.lss_40,
            "lss_cic": self.lss_cic,
            "baf": self.baf,
            "ebs": self.ebs,
            "yas_caf": self.yas_caf,
            "booking_charge": self.booking_charge,
            "thc": self.thc,
            "doc": self.doc,
            "isps": self.isps,
            "equipment_mgmt": self.equipment_mgmt,
            "freight_per_cbm": self.freight_per_cbm,
            "freight_per_ton": self.freight_per_ton,
            "sailing_day": self.sailing_day,
            "via": self.via,
            "transit_time_text": self.transit_time_text,
            "airline_code": self.airline_code,
            "service_desc": self.service_desc,
            "effective_week_start": self.effective_week_start,
            "effective_week_end": self.effective_week_end,
            "price_day1": self.price_day1,
            "price_day2": self.price_day2,
            "price_day3": self.price_day3,
            "price_day4": self.price_day4,
            "price_day5": self.price_day5,
            "price_day6": self.price_day6,
            "price_day7": self.price_day7,
            "record_kind": self.record_kind,
            "currency": self.currency,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "transit_days": self.transit_days,
            "is_direct": self.is_direct,
            "remarks": self.remarks,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "upload_batch_id": self.upload_batch_id,
        }
        payload.update(self.extras)
        return payload


@dataclass(slots=True)
class Step1SheetResult:
    """兼容多 Sheet Excel 的中间结构。"""

    sheet_name: str
    rows: list[Step1RateRow] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    def to_legacy_dict(self) -> dict[str, Any]:
        payload = {
            "sheet_name": self.sheet_name,
            "parsed_rows": [row.to_legacy_dict() for row in self.rows],
            "total_rows": self.total_rows,
        }
        payload.update(self.metadata)
        return payload


@dataclass(slots=True)
class Step1ParseResult:
    """Step1 统一解析结果。"""

    batch_id: str
    file_name: str
    source_kind: RateSourceKind
    adapter_key: str
    carrier_code: str | None = None
    parsed_rows: list[Step1RateRow] = field(default_factory=list)
    sheets: list[Step1SheetResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        if self.sheets:
            return sum(sheet.total_rows for sheet in self.sheets)
        return len(self.parsed_rows)

    def all_rows(self) -> list[Step1RateRow]:
        if self.sheets:
            rows: list[Step1RateRow] = []
            for sheet in self.sheets:
                rows.extend(sheet.rows)
            return rows
        return list(self.parsed_rows)

    def to_legacy_dict(self) -> dict[str, Any]:
        payload = {
            "batch_id": self.batch_id,
            "file_name": self.file_name,
            "source_type": self.source_kind.value,
            "carrier_code": self.carrier_code,
            "total_rows": self.total_rows,
            "warnings": list(self.warnings),
        }

        if self.sheets:
            payload["sheets"] = [sheet.to_legacy_dict() for sheet in self.sheets]
        else:
            payload["parsed_rows"] = [row.to_legacy_dict() for row in self.parsed_rows]

        payload.update(self.metadata)
        return payload


@dataclass(slots=True)
class ParsedRateRecord(Step1RateRow):
    """Step1 文档语义下的统一记录结构。"""


@dataclass(slots=True)
class ParsedRateBatch:
    """Step1 文档语义下的统一批次结构。"""

    file_type: Step1FileType
    source_file: str
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    effective_from: date | None = None
    effective_to: date | None = None
    records: list[ParsedRateRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adapter_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        parsed_rows = [record.to_legacy_dict() for record in self.records]
        payload = {
            "batch_id": self.batch_id,
            "file_type": self.file_type.value,
            "source_file": self.source_file,
            "file_name": self.source_file,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "total_rows": len(self.records),
            "warnings": list(self.warnings),
            "records": parsed_rows,
            "parsed_rows": parsed_rows,
        }
        if self.adapter_key is not None:
            payload["adapter_key"] = self.adapter_key
        payload.update(self.metadata)
        return payload
