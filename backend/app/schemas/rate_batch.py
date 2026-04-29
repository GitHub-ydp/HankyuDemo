"""Step1 rate batch API schemas."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class RateBatchSheetSummary(BaseModel):
    """Sheet summary for a parsed batch."""

    name: str
    rows: int


class RateBatchPreviewRow(BaseModel):
    """Preview row returned by the draft batch APIs."""

    row_index: int
    record_kind: str | None = None
    carrier: str | None = None
    origin_port: str | None = None
    destination_port: str | None = None
    service_code: str | None = None
    currency: str | None = None
    # 海运
    container_20gp: str | None = None
    container_40gp: str | None = None
    container_40hq: str | None = None
    container_45: str | None = None
    baf_20: str | None = None
    baf_40: str | None = None
    lss_20: str | None = None
    lss_40: str | None = None
    # 空运周价
    airline_code: str | None = None
    service_desc: str | None = None
    effective_week_start: str | None = None
    effective_week_end: str | None = None
    price_day1: str | None = None
    price_day2: str | None = None
    price_day3: str | None = None
    price_day4: str | None = None
    price_day5: str | None = None
    price_day6: str | None = None
    price_day7: str | None = None
    # 空运附加费
    area: str | None = None
    from_region: str | None = None
    destination_scope: str | None = None
    effective_date: str | None = None
    myc_min: str | None = None
    myc_fee_per_kg: str | None = None
    msc_min: str | None = None
    msc_fee_per_kg: str | None = None
    # 通用
    valid_from: str | None = None
    valid_to: str | None = None
    transit_days: int | None = None
    is_direct: bool | None = None
    remarks: str | None = None


class RateBatchSummary(BaseModel):
    """Batch summary returned by list/detail APIs."""

    batch_id: str
    file_name: str
    source_type: str
    batch_status: str
    activation_status: str
    adapter_key: str | None = None
    parser_hint: str | None = None
    carrier_code: str | None = None
    total_rows: int
    preview_count: int
    warnings: list[str] = Field(default_factory=list)
    sheets: list[RateBatchSheetSummary] = Field(default_factory=list)
    storage_mode: str
    created_at: datetime
    updated_at: datetime


class RateBatchDetail(RateBatchSummary):
    """Detailed batch payload with draft preview rows."""

    preview_rows: list[RateBatchPreviewRow] = Field(default_factory=list)
    preview_truncated: bool = False
    available_actions: list[str] = Field(default_factory=list)


class RateBatchDiffSummary(BaseModel):
    """Aggregate diff counters for one batch."""

    total_rows: int
    new_rows: int
    changed_rows: int
    unchanged_rows: int
    unmatched_rows: int


class RateBatchDiffItem(BaseModel):
    """Single diff item for preview purposes."""

    row_index: int
    status: str
    existing_rate_id: int | None = None
    reason: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    preview: RateBatchPreviewRow


class RateBatchDiffResponse(BaseModel):
    """Stable diff response shape for Step1 draft batches."""

    batch_id: str
    batch_status: str
    diff_status: str
    generated_at: datetime
    summary: RateBatchDiffSummary
    items: list[RateBatchDiffItem] = Field(default_factory=list)
    is_stub: bool = False
    message: str | None = None


class RateBatchActivateRequest(BaseModel):
    """Request payload for future batch activation."""

    dry_run: bool = True
    force: bool = False
    selected_row_indices: list[int] | None = None


class ActivationErrorItem(BaseModel):
    """Single error entry for failed activations."""

    code: str
    detail: str
    row_index: int | None = None
    record_kind: str | None = None


class RateBatchActivateResponse(BaseModel):
    """Stable activation response shape for Step1 draft batches."""

    batch_id: str
    batch_status: str
    activation_status: str
    activated: bool
    imported_rows: int
    skipped_rows: int
    generated_at: datetime
    selected_rows: int
    diff_summary: RateBatchDiffSummary
    is_stub: bool = False
    message: str | None = None

    file_type: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    imported_detail: dict[str, int] = Field(default_factory=dict)
    superseded_batch_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[ActivationErrorItem] = Field(default_factory=list)
