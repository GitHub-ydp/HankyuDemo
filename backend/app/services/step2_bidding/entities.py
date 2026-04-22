"""Step2 入札対応 数据实体定义。

字段契约见 docs/Step2_入札対応_Customer_A_架构任务单_20260422.md §4。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class BiddingStatus(str, Enum):
    CREATED = "created"
    PARSING = "parsing"
    PARSED = "parsed"
    QUOTING = "quoting"
    QUOTED = "quoted"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTED = "submitted"
    FAILED = "failed"


class CostType(str, Enum):
    AIR_FREIGHT = "air_freight"
    LOCAL_DELIVERY = "local_delivery"
    UNKNOWN = "unknown"


class RowStatus(str, Enum):
    FILLED = "filled"
    NO_RATE = "no_rate"
    ALREADY_FILLED = "already_filled"
    EXAMPLE = "example"
    NON_LOCAL_LEG = "non_local_leg"
    LOCAL_DELIVERY_MANUAL = "local_delivery_manual"
    CONSTRAINT_BLOCK = "constraint_block"
    OVERRIDDEN = "overridden"


@dataclass(slots=True)
class PkgSection:
    section_index: int
    section_code: str
    header_row: int
    origin_text_raw: str
    origin_code: str
    currency: str
    currency_header_raw: str
    is_local_section: bool
    section_level_remarks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PkgRow:
    row_idx: int
    section_index: int
    section_code: str
    origin_code: str
    origin_text_raw: str
    destination_text_raw: str
    destination_code: str
    cost_type: CostType
    currency: str
    volume_desc: str | None
    existing_price: Decimal | None
    existing_lead_time: str | None
    existing_carrier: str | None
    existing_remark: str | None
    is_example: bool
    client_constraint_text: str | None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedPkg:
    bid_id: str
    customer_code: str
    period: str
    sheet_name: str
    source_file: str
    sections: list[PkgSection]
    rows: list[PkgRow]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuoteCandidate:
    base_price: Decimal
    base_price_day_index: int | None
    airline_codes: list[str]
    service_desc: str
    via: str | None
    myc_fee_per_kg: Decimal | None
    msc_fee_per_kg: Decimal | None
    myc_applied: bool
    msc_applied: bool
    cost_price: Decimal
    currency: str
    source_batch_id: str
    source_weekly_record_id: int
    source_surcharge_record_id: int | None
    remarks_from_step1: str | None
    step1_must_go: bool
    step1_case_by_case: bool
    match_score: float


@dataclass(slots=True)
class PerRowReport:
    row_idx: int
    section_code: str
    destination_code: str
    status: RowStatus
    cost_price: Decimal | None
    sell_price: Decimal | None
    markup_ratio: Decimal | None
    lead_time_text: str | None
    carrier_text: str | None
    remark_text: str | None
    selected_candidate: QuoteCandidate | None
    constraint_hits: list[str] = field(default_factory=list)
    validator_warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    overridden_by: str | None = None
    overridden_at: datetime | None = None


@dataclass(slots=True)
class FillReport:
    bid_id: str
    generated_at: datetime
    row_reports: list[PerRowReport]
    filled_count: int
    no_rate_count: int
    skipped_count: int
    cost_file_path: str
    sr_file_path: str
    global_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BiddingRequest:
    bid_id: str
    customer_code: str
    period: str
    status: BiddingStatus
    source_file_path: str
    uploader: str | None
    created_at: datetime
    updated_at: datetime
    parsed_pkg: ParsedPkg | None = None
    fill_report: FillReport | None = None
