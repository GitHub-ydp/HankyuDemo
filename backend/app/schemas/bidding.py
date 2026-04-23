"""Pydantic schemas for T-B10 v0.1 bidding auto-fill endpoint.

对应架构任务单 §3 接口契约。字段 / 降级规则见 §3.1 / §4。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class BiddingErrorCode(str, Enum):
    F1_INVALID_XLSX = "F1_INVALID_XLSX"
    F2_UNSUPPORTED_CUSTOMER = "F2_UNSUPPORTED_CUSTOMER"
    F3_PARSE_FAILED = "F3_PARSE_FAILED"
    F4_FILL_FAILED = "F4_FILL_FAILED"
    F5_TOKEN_EXPIRED = "F5_TOKEN_EXPIRED"
    F6_FILE_TOO_LARGE = "F6_FILE_TOO_LARGE"
    F7_WRONG_EXTENSION = "F7_WRONG_EXTENSION"
    F8_NETWORK_ERROR = "F8_NETWORK_ERROR"


class BiddingErrorBlock(BaseModel):
    code: BiddingErrorCode
    message_key: str
    detail: str


class IdentifyBlock(BaseModel):
    matched_customer: Literal["customer_a", "unknown"]
    matched_dimensions: list[str]
    confidence: Literal["high", "medium", "low"]
    unmatched_reason: str | None = None
    warnings: list[str] = []


class SampleRow(BaseModel):
    row_idx: int
    section_code: str
    destination_text: str
    cost_type: Literal["air_freight", "local_delivery", "unknown"]


class ParseBlock(BaseModel):
    period: str
    sheet_name: str
    section_count: int
    row_count: int
    sample_rows: list[SampleRow]
    warnings: list[str] = []


class FillRowBlock(BaseModel):
    row_idx: int
    section_code: str
    destination_code: str
    status: str
    cost_price: str | None = None
    sell_price: str | None = None
    markup_ratio: str | None = None
    source_batch_id: str | None = None
    confidence: float = 0.0


class FillBlock(BaseModel):
    filled_count: int
    no_rate_count: int
    skipped_count: int
    global_warnings: list[str] = []
    rows: list[FillRowBlock]
    markup_ratio: str


class DownloadTokens(BaseModel):
    cost_token: str
    sr_token: str
    cost_filename: str
    sr_filename: str
    expires_at: datetime
    one_time_use: bool = True


class BiddingAutoFillResponse(BaseModel):
    bid_id: str
    ok: bool
    error: BiddingErrorBlock | None = None
    identify: IdentifyBlock
    parse: ParseBlock | None = None
    fill: FillBlock | None = None
    download: DownloadTokens | None = None
