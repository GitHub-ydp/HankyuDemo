"""Step1 rate batch API schemas."""
from datetime import datetime

from pydantic import BaseModel, Field


class RateBatchSheetSummary(BaseModel):
    """Sheet summary for a parsed batch."""

    name: str
    rows: int


class RateBatchPreviewRow(BaseModel):
    """Preview row returned by the draft batch APIs."""

    row_index: int
    carrier: str | None = None
    origin_port: str | None = None
    destination_port: str | None = None
    service_code: str | None = None
    currency: str | None = None
    container_20gp: str | None = None
    container_40gp: str | None = None
    container_40hq: str | None = None
    container_45: str | None = None
    baf_20: str | None = None
    baf_40: str | None = None
    lss_20: str | None = None
    lss_40: str | None = None
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
    is_stub: bool = True
    message: str | None = None
