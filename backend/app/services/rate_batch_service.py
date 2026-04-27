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
from app.models import FreightRate, ImportBatch, ImportBatchStatus, RateStatus
from app.services.email_text_parser import parse_email_text
from app.services.step1_rates import activator
from app.services.step1_rates.entities import ParsedRateBatch, ParsedRateRecord, Step1FileType
from app.services.step1_rates.normalizers import legacy_payload_to_parsed_batch
from app.services.step1_rates.service import (
    DEFAULT_RATE_ADAPTER_REGISTRY,
    parse_excel_file,
)
import openpyxl

SUPPORTED_BATCH_FILE_EXTENSIONS = {".xlsx", ".xls", ".csv"}
PREVIEW_LIMIT = 50
DIFF_ITEM_LIMIT = 20
STORAGE_MODE = "memory_stub"
AI_FALLBACK_SOURCE_TYPE = "excel_ai_fallback"


class NoRatesFoundError(ValueError):
    """Raised when AI fallback cannot extract any rate rows from the Excel."""


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


# upload_dir 解析锚点：始终落到「backend/」目录之下，避免依赖进程 cwd。
# 进程从仓库根、systemd unit、docker、IDE 各种姿势启动时，cwd 不一致会让
# `Path("uploads")` 解析到完全不同的位置（甚至无写权限的根目录）。
# rate_batch_service.py 在 backend/app/services/ → parents[2] = backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_upload_dir() -> Path:
    """把 settings.upload_dir 解析成绝对路径，并确保目录存在 + 可写。

    - 绝对路径：原样使用（典型 prod 场景：UPLOAD_DIR=/var/lib/hankyu/uploads）
    - 相对路径：锚定到 backend/ 而非进程 cwd，行为与启动姿势解耦
    """
    raw = Path(settings.upload_dir)
    if raw.is_absolute():
        upload_dir = raw
    else:
        upload_dir = (_BACKEND_ROOT / raw).resolve()

    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        import getpass

        try:
            user = getpass.getuser()
        except Exception:
            user = f"uid={os.getuid()}"
        raise PermissionError(
            f"Cannot create upload dir: {upload_dir} "
            f"(user={user}, settings.upload_dir={settings.upload_dir!r}). "
            f"Fix: sudo mkdir -p {upload_dir} && sudo chown -R {user}: {upload_dir.parent} "
            f"or set UPLOAD_DIR=/abs/path in .env"
        ) from exc
    return upload_dir


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

    upload_dir = _resolve_upload_dir()

    safe_name = _safe_file_name(file_name)
    saved_name = f"step1_batch_{uuid.uuid4().hex[:8]}_{safe_name}"
    saved_path = upload_dir / saved_name
    try:
        saved_path.write_bytes(content)
    except PermissionError as exc:
        # 服务器上常见：upload_dir 属主与 uvicorn 运行用户不一致（之前 sudo 跑过留下的 root 目录）
        # 报错暴露 cwd + 解析路径 + 当前 uid，方便运维一眼定位
        import getpass

        cwd = os.getcwd()
        try:
            user = getpass.getuser()
        except Exception:
            user = f"uid={os.getuid()}"
        raise PermissionError(
            f"Cannot write to upload dir: {saved_path} "
            f"(cwd={cwd}, user={user}, settings.upload_dir={settings.upload_dir!r}). "
            f"Fix: chown -R {user}: {upload_dir} && chmod -R u+rwX {upload_dir} "
            f"or set UPLOAD_DIR=/abs/path in .env"
        ) from exc

    ai_fallback_used = False
    try:
        parse_result = parse_excel_file(
            str(saved_path),
            db,
            file_name=file_name,
            parser_hint=parser_hint,
        )
    except LookupError:
        # 第 2 段：AI 兜底
        try:
            parse_result = _try_ai_fallback_on_excel(saved_path, file_name, db)
        except NoRatesFoundError:
            saved_path.unlink(missing_ok=True)
            raise
        except Exception:
            saved_path.unlink(missing_ok=True)
            raise
        ai_fallback_used = True
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise

    draft = _build_draft_batch(
        parse_result=parse_result,
        parser_hint=parser_hint,
        file_path=str(saved_path),
        source_type_override=AI_FALLBACK_SOURCE_TYPE if ai_fallback_used else None,
    )
    _draft_batches[draft.batch_id] = draft
    return serialize_detail(draft)


def list_rate_batches(
    *,
    db: Session | None = None,
    page: int = 1,
    page_size: int = 20,
    batch_status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """合并内存 _draft_batches 与 DB import_batches 表，分页返回批次列表。"""
    memory_items: list[dict[str, Any]] = [
        serialize_summary(draft) for draft in _draft_batches.values()
    ]
    memory_ids = {item["batch_id"] for item in memory_items}

    db_items: list[dict[str, Any]] = []
    if db is not None:
        db_rows = (
            db.query(ImportBatch)
            .order_by(ImportBatch.imported_at.desc())
            .all()
        )
        for row in db_rows:
            if str(row.batch_id) in memory_ids:
                continue
            db_items.append(_serialize_import_batch_row(row))

    merged = memory_items + db_items

    if batch_status:
        normalized_status = batch_status.strip().lower()
        merged = [item for item in merged if item["batch_status"] == normalized_status]

    def _sort_key(item: dict[str, Any]) -> datetime:
        created = item.get("created_at")
        if isinstance(created, datetime):
            if created.tzinfo is None:
                return created.replace(tzinfo=timezone.utc)
            return created
        return datetime.min.replace(tzinfo=timezone.utc)

    merged.sort(key=_sort_key, reverse=True)
    total = len(merged)
    start = (page - 1) * page_size
    end = start + page_size
    return merged[start:end], total


def _serialize_import_batch_row(row: ImportBatch) -> dict[str, Any]:
    """把 ImportBatch DB 行映射成与 serialize_summary 对齐的 dict。"""
    status_value = (
        "active"
        if row.status == ImportBatchStatus.active
        else row.status.value
    )
    activation_status = (
        "activated"
        if row.status == ImportBatchStatus.active
        else "not_activated"
    )
    imported_at = row.imported_at
    if isinstance(imported_at, datetime) and imported_at.tzinfo is None:
        imported_at = imported_at.replace(tzinfo=timezone.utc)
    return {
        "batch_id": str(row.batch_id),
        "file_name": row.source_file or "",
        "source_type": "excel",
        "batch_status": status_value,
        "activation_status": activation_status,
        "adapter_key": row.file_type.value,
        "parser_hint": None,
        "carrier_code": None,
        "total_rows": row.row_count,
        "preview_count": 0,
        "warnings": [],
        "sheets": [],
        "storage_mode": "db",
        "created_at": imported_at,
        "updated_at": imported_at,
    }


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


def _summarize_carriers_from_records(records: list[ParsedRateRecord]) -> str | None:
    """当 adapter 没在 metadata 填 batch 级 carrier_code 时，从行级 carrier_name 聚合成摘要。

    单一承运商：「SITC」；两家：「SITC/SINO」；多于两家：「SITC/SINO +3」。
    """
    if not records:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for rec in records:
        name = (getattr(rec, "carrier_name", "") or "").strip()
        if not name:
            continue
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    head = "/".join(ordered[:2])
    if len(ordered) > 2:
        return f"{head} +{len(ordered) - 2}"
    return head


def _build_draft_batch(
    *,
    parse_result: Any,
    parser_hint: str | None,
    file_path: str,
    source_type_override: str | None = None,
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
        source_type=source_type_override or legacy_payload.get("source_type", "excel"),
        batch_status="draft",
        activation_status="not_activated",
        adapter_key=getattr(parse_result, "adapter_key", None),
        parser_hint=parser_hint,
        carrier_code=legacy_payload.get("carrier_code")
        or _summarize_carriers_from_records(parse_records),
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


def _try_ai_fallback_on_excel(
    saved_path: Path, file_name: str, db: Session
) -> ParsedRateBatch:
    """第 2 段：读 Excel 纯文本 → parse_email_text → ParsedRateBatch。

    AI 抓不到任何行时抛 NoRatesFoundError（第 3 段）。
    """
    try:
        text = _extract_excel_text(saved_path)
    except Exception as exc:  # noqa: BLE001
        raise NoRatesFoundError(
            f"Failed to read Excel text from {file_name}: {exc}"
        ) from exc
    legacy = parse_email_text(text, db)
    if not legacy.get("parsed_rows"):
        raise NoRatesFoundError(
            f"AI fallback found no rates in {file_name}"
        )
    return legacy_payload_to_parsed_batch(
        legacy,
        file_type=Step1FileType.ocean,
        adapter_key=None,
        source_file=file_name,
    )


def _extract_excel_text(path: Path, max_chars: int = 20000) -> str:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    lines: list[str] = []
    for sheet in wb.worksheets:
        lines.append(f"# Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip()]
            if cells:
                lines.append(" | ".join(cells))
        if sum(len(l) for l in lines) > max_chars:
            break
    wb.close()
    return "\n".join(lines)[:max_chars]
