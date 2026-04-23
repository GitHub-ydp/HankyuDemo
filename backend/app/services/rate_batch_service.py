from __future__ import annotations

"""Step1 rate batch service skeleton."""

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import FreightRate, RateStatus
from app.services.step1_rates import activator
from app.services.step1_rates.entities import ParsedRateRecord
from app.services.step1_rates.service import (
    DEFAULT_RATE_ADAPTER_REGISTRY,
    parse_excel_file,
)

SUPPORTED_BATCH_FILE_EXTENSIONS = {".xlsx", ".xls", ".csv"}
PREVIEW_LIMIT = 50
DIFF_ITEM_LIMIT = 20
STORAGE_MODE = "memory_stub"


@dataclass(slots=True)
class DraftRateBatch:
    batch_id: str
    file_name: str
    source_type: str
    batch_status: str
    activation_status: str
    adapter_key: str | None
    parser_hint: str | None
    carrier_code: str | None
    total_rows: int
    warnings: list[str]
    sheets: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    row_payloads: list[dict[str, Any]] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=lambda: ["diff", "activate"])
    file_path: str | None = None
    legacy_payload: dict[str, Any] = field(default_factory=dict)
    parse_records: list[ParsedRateRecord] = field(default_factory=list)


_draft_batches: dict[str, DraftRateBatch] = {}


def create_draft_batch_from_upload(
    *,
    file_name: str,
    content: bytes,
    db: Session,
    parser_hint: str | None = None,
) -> dict[str, Any]:
    """Parse an uploaded Step1 rate file and register a draft batch."""
    if not file_name:
        raise ValueError("file_name is required")

    file_ext = Path(file_name).suffix.lower()
    if file_ext not in SUPPORTED_BATCH_FILE_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_BATCH_FILE_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {file_ext or 'unknown'}. Allowed: {allowed}")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_file_name(file_name)
    saved_name = f"step1_batch_{uuid.uuid4().hex[:8]}_{safe_name}"
    saved_path = upload_dir / saved_name
    saved_path.write_bytes(content)

    try:
        parse_result = parse_excel_file(
            str(saved_path),
            db,
            file_name=file_name,
            parser_hint=parser_hint,
        )
    except LookupError as exc:
        saved_path.unlink(missing_ok=True)
        available = ", ".join(DEFAULT_RATE_ADAPTER_REGISTRY.keys())
        raise ValueError(f"{exc}. Available parser_hint values: {available}") from exc
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise

    draft = _build_draft_batch(
        parse_result=parse_result,
        parser_hint=parser_hint,
        file_path=str(saved_path),
    )
    _draft_batches[draft.batch_id] = draft
    return serialize_detail(draft)


def list_rate_batches(
    *,
    page: int = 1,
    page_size: int = 20,
    batch_status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List draft rate batches from the in-memory store."""
    items = list(_draft_batches.values())
    if batch_status:
        normalized_status = batch_status.strip().lower()
        items = [item for item in items if item.batch_status == normalized_status]

    items.sort(key=lambda item: item.created_at, reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return [serialize_summary(item) for item in items[start:end]], total


def get_rate_batch_detail(batch_id: str) -> dict[str, Any] | None:
    """Get one draft batch detail."""
    draft = _draft_batches.get(batch_id)
    if not draft:
        return None
    return serialize_detail(draft)


def get_rate_batch_diff(batch_id: str, db: Session) -> dict[str, Any] | None:
    """Build a stable diff response against the current rate table."""
    draft = _draft_batches.get(batch_id)
    if not draft:
        return None

    counters = {
        "total_rows": draft.total_rows,
        "new_rows": 0,
        "changed_rows": 0,
        "unchanged_rows": 0,
        "unmatched_rows": 0,
    }
    items: list[dict[str, Any]] = []
    for row_payload in draft.row_payloads:
        diff_item = _build_diff_item(row_payload, db)
        counters[f"{diff_item['status']}_rows"] += 1
        if len(items) < DIFF_ITEM_LIMIT:
            items.append(diff_item)

    return {
        "batch_id": draft.batch_id,
        "batch_status": draft.batch_status,
        "diff_status": "ready",
        "generated_at": _now(),
        "summary": counters,
        "items": items,
        "is_stub": False,
        "message": "Diff is computed against current freight_rates using a lane-level heuristic.",
    }


def activate_rate_batch(
    batch_id: str,
    db: Session,
    *,
    dry_run: bool = True,
    force: bool = False,
    selected_row_indices: list[int] | None = None,
) -> dict[str, Any] | None:
    """真激活批次或 dry_run 预览。"""
    draft = _draft_batches.get(batch_id)
    if not draft:
        return None

    diff_payload = get_rate_batch_diff(batch_id, db)
    diff_summary = diff_payload["summary"] if diff_payload else {
        "total_rows": draft.total_rows,
        "new_rows": 0,
        "changed_rows": 0,
        "unchanged_rows": 0,
        "unmatched_rows": 0,
    }

    selected_count = (
        len(selected_row_indices)
        if selected_row_indices is not None
        else draft.total_rows
    )

    if draft.batch_status == "active":
        return {
            "batch_id": draft.batch_id,
            "batch_status": "active",
            "activation_status": "already_active",
            "activated": False,
            "imported_rows": 0,
            "skipped_rows": 0,
            "generated_at": _now(),
            "selected_rows": selected_count,
            "diff_summary": diff_summary,
            "is_stub": False,
            "message": "该批次已激活，当前状态 active",
            "file_type": (draft.legacy_payload or {}).get("file_type"),
            "effective_from": (draft.legacy_payload or {}).get("effective_from"),
            "effective_to": (draft.legacy_payload or {}).get("effective_to"),
            "imported_detail": {},
            "superseded_batch_ids": [],
            "warnings": [],
            "errors": [],
        }

    if len(draft.parse_records) == 0:
        return {
            "batch_id": draft.batch_id,
            "batch_status": "draft",
            "activation_status": "empty_batch",
            "activated": False,
            "imported_rows": 0,
            "skipped_rows": 0,
            "generated_at": _now(),
            "selected_rows": selected_count,
            "diff_summary": diff_summary,
            "is_stub": False,
            "message": "该批次无可入库数据（0 条）",
            "file_type": (draft.legacy_payload or {}).get("file_type"),
            "effective_from": (draft.legacy_payload or {}).get("effective_from"),
            "effective_to": (draft.legacy_payload or {}).get("effective_to"),
            "imported_detail": {},
            "superseded_batch_ids": [],
            "warnings": [],
            "errors": [],
        }

    result = activator.activate(draft, db, dry_run=dry_run, force=force)

    errors_payload = [
        {
            "code": e.code,
            "detail": e.detail,
            "row_index": e.row_index,
            "record_kind": e.record_kind,
        }
        for e in result.errors
    ]

    if result.activation_status == "activated":
        batch_status = "active"
    elif result.activation_status == "dry_run":
        batch_status = draft.batch_status
    else:
        batch_status = "draft"

    return {
        "batch_id": result.batch_id,
        "batch_status": batch_status,
        "activation_status": result.activation_status,
        "activated": result.activated,
        "imported_rows": result.imported_rows,
        "skipped_rows": result.skipped_rows,
        "generated_at": _now(),
        "selected_rows": selected_count,
        "diff_summary": diff_summary,
        "is_stub": False,
        "message": result.message,
        "file_type": result.file_type,
        "effective_from": result.effective_from,
        "effective_to": result.effective_to,
        "imported_detail": dict(result.imported_detail),
        "superseded_batch_ids": list(result.superseded_batch_ids),
        "warnings": list(result.warnings),
        "errors": errors_payload,
    }


def serialize_summary(draft: DraftRateBatch) -> dict[str, Any]:
    return {
        "batch_id": draft.batch_id,
        "file_name": draft.file_name,
        "source_type": draft.source_type,
        "batch_status": draft.batch_status,
        "activation_status": draft.activation_status,
        "adapter_key": draft.adapter_key,
        "parser_hint": draft.parser_hint,
        "carrier_code": draft.carrier_code,
        "total_rows": draft.total_rows,
        "preview_count": len(draft.preview_rows),
        "warnings": list(draft.warnings),
        "sheets": list(draft.sheets),
        "storage_mode": STORAGE_MODE,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def serialize_detail(draft: DraftRateBatch) -> dict[str, Any]:
    payload = serialize_summary(draft)
    payload.update(
        {
            "preview_rows": list(draft.preview_rows),
            "preview_truncated": draft.total_rows > len(draft.preview_rows),
            "available_actions": list(draft.available_actions),
        }
    )
    return payload


def _build_draft_batch(
    *,
    parse_result: Any,
    parser_hint: str | None,
    file_path: str,
) -> DraftRateBatch:
    legacy_payload = parse_result.to_legacy_dict()
    all_rows = _collect_rows(legacy_payload)
    preview_rows = [row["preview"] for row in all_rows[:PREVIEW_LIMIT]]
    parse_records: list[ParsedRateRecord] = []
    records_attr = getattr(parse_result, "records", None)
    if records_attr:
        parse_records = list(records_attr)
    else:
        all_rows_fn = getattr(parse_result, "all_rows", None)
        if callable(all_rows_fn):
            parse_records = list(all_rows_fn())
    now = _now()
    return DraftRateBatch(
        batch_id=legacy_payload["batch_id"],
        file_name=legacy_payload.get("file_name") or Path(file_path).name,
        source_type=legacy_payload.get("source_type", "excel"),
        batch_status="draft",
        activation_status="not_activated",
        adapter_key=getattr(parse_result, "adapter_key", None),
        parser_hint=parser_hint,
        carrier_code=legacy_payload.get("carrier_code"),
        total_rows=legacy_payload.get("total_rows", len(all_rows)),
        warnings=list(legacy_payload.get("warnings", [])),
        sheets=_extract_sheets(legacy_payload),
        created_at=now,
        updated_at=now,
        preview_rows=preview_rows,
        row_payloads=all_rows,
        file_path=file_path,
        legacy_payload=legacy_payload,
        parse_records=parse_records,
    )


def _collect_rows(parse_result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_rows = parse_result.get("parsed_rows")
    if source_rows:
        for index, row in enumerate(source_rows, start=1):
            rows.append(_normalize_row(row, index))
        return rows

    current_index = 1
    for sheet in parse_result.get("sheets", []):
        for row in sheet.get("parsed_rows", []):
            rows.append(_normalize_row(row, current_index))
            current_index += 1
    return rows


def _normalize_row(row: dict[str, Any], row_index: int) -> dict[str, Any]:
    preview = {
        "row_index": row_index,
        "carrier": row.get("carrier_name"),
        "origin_port": row.get("origin_port_name"),
        "destination_port": row.get("destination_port_name"),
        "service_code": row.get("service_code"),
        "currency": row.get("currency"),
        "container_20gp": _stringify(row.get("container_20gp")),
        "container_40gp": _stringify(row.get("container_40gp")),
        "container_40hq": _stringify(row.get("container_40hq")),
        "container_45": _stringify(row.get("container_45")),
        "baf_20": _stringify(row.get("baf_20")),
        "baf_40": _stringify(row.get("baf_40")),
        "lss_20": _stringify(row.get("lss_20")),
        "lss_40": _stringify(row.get("lss_40")),
        "valid_from": _stringify(row.get("valid_from")),
        "valid_to": _stringify(row.get("valid_to")),
        "transit_days": row.get("transit_days"),
        "is_direct": row.get("is_direct"),
        "remarks": row.get("remarks"),
    }
    return {
        "row_index": row_index,
        "preview": preview,
        "carrier_id": row.get("carrier_id"),
        "origin_port_id": row.get("origin_port_id"),
        "destination_port_id": row.get("destination_port_id"),
        "service_code": row.get("service_code"),
        "container_20gp": row.get("container_20gp"),
        "container_40gp": row.get("container_40gp"),
        "container_40hq": row.get("container_40hq"),
        "container_45": row.get("container_45"),
        "baf_20": row.get("baf_20"),
        "baf_40": row.get("baf_40"),
        "lss_20": row.get("lss_20"),
        "lss_40": row.get("lss_40"),
        "currency": row.get("currency"),
        "valid_from": row.get("valid_from"),
        "valid_to": row.get("valid_to"),
        "transit_days": row.get("transit_days"),
        "is_direct": row.get("is_direct"),
    }


def _extract_sheets(parse_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": sheet.get("sheet_name", ""),
            "rows": sheet.get("total_rows", 0),
        }
        for sheet in parse_result.get("sheets", [])
    ]


def _build_diff_item(row_payload: dict[str, Any], db: Session) -> dict[str, Any]:
    existing_rate = _find_existing_rate(row_payload, db)
    if existing_rate is None:
        status = "unmatched" if _is_key_missing(row_payload) else "new"
        reason = (
            "Missing carrier/port ids from parsed draft row."
            if status == "unmatched"
            else "No existing freight_rate matched the draft row key."
        )
        return {
            "row_index": row_payload["row_index"],
            "status": status,
            "existing_rate_id": None,
            "reason": reason,
            "changed_fields": [],
            "preview": row_payload["preview"],
        }

    changed_fields = _collect_changed_fields(row_payload, existing_rate)
    status = "changed" if changed_fields else "unchanged"
    reason = "Matched by carrier/origin/destination/service_code."
    if changed_fields:
        reason = f"{reason} Pricing or validity fields differ."

    return {
        "row_index": row_payload["row_index"],
        "status": status,
        "existing_rate_id": existing_rate.id,
        "reason": reason,
        "changed_fields": changed_fields,
        "preview": row_payload["preview"],
    }


def _find_existing_rate(row_payload: dict[str, Any], db: Session) -> FreightRate | None:
    if _is_key_missing(row_payload):
        return None

    query = db.query(FreightRate).filter(
        FreightRate.carrier_id == row_payload["carrier_id"],
        FreightRate.origin_port_id == row_payload["origin_port_id"],
        FreightRate.destination_port_id == row_payload["destination_port_id"],
        FreightRate.status.in_([RateStatus.draft, RateStatus.active]),
    )
    if row_payload.get("service_code"):
        query = query.filter(FreightRate.service_code == row_payload["service_code"])
    else:
        query = query.filter(FreightRate.service_code.is_(None))

    return query.order_by(FreightRate.updated_at.desc(), FreightRate.id.desc()).first()


def _collect_changed_fields(row_payload: dict[str, Any], existing_rate: FreightRate) -> list[str]:
    changed_fields: list[str] = []
    for field_name in (
        "container_20gp",
        "container_40gp",
        "container_40hq",
        "container_45",
        "baf_20",
        "baf_40",
        "lss_20",
        "lss_40",
        "currency",
        "valid_from",
        "valid_to",
        "transit_days",
        "is_direct",
    ):
        if _compare_values(row_payload.get(field_name), getattr(existing_rate, field_name)):
            continue
        changed_fields.append(field_name)
    return changed_fields


def _compare_values(left: Any, right: Any) -> bool:
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        return _stringify(left) == _stringify(right)
    if isinstance(left, date) or isinstance(right, date):
        return _stringify(left) == _stringify(right)
    return left == right


def _is_key_missing(row_payload: dict[str, Any]) -> bool:
    return not all(
        [
            row_payload.get("carrier_id"),
            row_payload.get("origin_port_id"),
            row_payload.get("destination_port_id"),
        ]
    )


def _safe_file_name(file_name: str) -> str:
    sanitized = os.path.basename(file_name).replace("/", "_").replace("\\", "_").strip()
    return sanitized or "upload.xlsx"


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)
