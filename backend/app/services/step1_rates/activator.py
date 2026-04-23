"""Step1 批次激活核心 — draft → 真实落库。

见架构任务单 §4 数据流 + §5 映射表。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import (
    AirFreightRate,
    AirSurcharge,
    FreightRate,
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)
from app.services.step1_rates.activator_mappers import (
    ActivationError,
    to_air_freight_rate,
    to_air_surcharge,
    to_freight_rate_from_ngb,
    to_freight_rate_from_ocean,
)
from app.services.step1_rates.entities import ParsedRateRecord

if TYPE_CHECKING:
    from app.services.rate_batch_service import DraftRateBatch


@dataclass(slots=True)
class ActivationErrorItem:
    code: str
    detail: str
    row_index: int | None = None
    record_kind: str | None = None


@dataclass(slots=True)
class ActivationResult:
    batch_id: str
    file_type: str
    activation_status: str  # "activated" / "dry_run" / "failed" / "already_active" / "empty_batch"
    activated: bool
    imported_rows: int
    skipped_rows: int
    imported_detail: dict[str, int] = field(default_factory=dict)
    superseded_batch_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[ActivationErrorItem] = field(default_factory=list)
    effective_from: date | None = None
    effective_to: date | None = None
    message: str | None = None


_FILE_TYPE_MAP = {
    "air": ImportBatchFileType.air,
    "ocean": ImportBatchFileType.ocean,
    "ocean_ngb": ImportBatchFileType.ocean_ngb,
}


def activate(
    draft: "DraftRateBatch",
    db: Session,
    *,
    dry_run: bool,
    force: bool = False,
) -> ActivationResult:
    """真激活或 dry_run 预览。

    - dry_run=True：只统计 imported/skipped + 预览 superseded_batch_ids，不落库
    - dry_run=False：同事务包裹 降级老 active → 插 import_batches → 插子表 → 更新 row_count
    - 任一失败整体 rollback，返回 activation_status='failed' + errors，HTTP 200
    """
    del force  # v0.1 force 与不 force 行为一致（保留参数位）

    file_type_raw = (draft.legacy_payload or {}).get("file_type") or "air"
    file_type_enum = _FILE_TYPE_MAP.get(file_type_raw)
    if file_type_enum is None:
        return ActivationResult(
            batch_id=draft.batch_id,
            file_type=file_type_raw,
            activation_status="failed",
            activated=False,
            imported_rows=0,
            skipped_rows=0,
            errors=[
                ActivationErrorItem(
                    code="F-ACT-05",
                    detail=f"unknown file_type '{file_type_raw}'",
                )
            ],
            message=f"unknown file_type '{file_type_raw}'",
        )

    records: list[ParsedRateRecord] = list(draft.parse_records or [])
    effective_from = (draft.legacy_payload or {}).get("effective_from")
    effective_to = (draft.legacy_payload or {}).get("effective_to")

    lcl_skipped_count = sum(
        1 for r in records if r.record_kind in {"lcl", "ocean_ngb_lcl"}
    )
    dispatchable = [
        r for r in records if r.record_kind not in {"lcl", "ocean_ngb_lcl"}
    ]

    superseded_preview = _query_superseded_batch_ids(db, file_type_enum)
    warnings: list[str] = []
    if lcl_skipped_count > 0:
        warnings.append(
            f"跳过 {lcl_skipped_count} 条 LCL records（v0.1 未实装 LCL 入库）"
        )

    if dry_run:
        planned_rows = len(dispatchable)
        detail_preview = _plan_imported_detail(file_type_raw, dispatchable)
        return ActivationResult(
            batch_id=draft.batch_id,
            file_type=file_type_raw,
            activation_status="dry_run",
            activated=False,
            imported_rows=planned_rows,
            skipped_rows=lcl_skipped_count,
            imported_detail=detail_preview,
            superseded_batch_ids=superseded_preview,
            warnings=warnings,
            effective_from=effective_from,
            effective_to=effective_to,
            message=f"Dry-run only. Would import {planned_rows} rows.",
        )

    batch_uuid = _coerce_uuid(draft.batch_id)
    source_file = (draft.legacy_payload or {}).get("source_file") or draft.file_name

    imported_detail: dict[str, int] = {}
    try:
        # Session 可能已 autobegin（上游已 query）。用 savepoint 嵌套保证原子：
        # 任一步异常触发 nested rollback，调用方未 commit 之前不会泄漏到外层事务。
        with db.begin_nested():
            superseded_ids = _supersede_old_active(db, file_type_enum)

            import_batch_row = ImportBatch(
                batch_id=batch_uuid,
                file_type=file_type_enum,
                source_file=source_file,
                sheet_name=_pick_sheet_name(draft),
                effective_from=effective_from,
                effective_to=effective_to,
                row_count=0,
                status=ImportBatchStatus.active,
                imported_by="step1_activator",
            )
            db.add(import_batch_row)
            db.flush()

            air_objs: list[AirFreightRate] = []
            sur_objs: list[AirSurcharge] = []
            freight_objs: list[FreightRate] = []

            for record in dispatchable:
                kind = record.record_kind
                if kind == "air_weekly":
                    air_objs.append(to_air_freight_rate(record, batch_uuid))
                elif kind == "air_surcharge":
                    sur_objs.append(to_air_surcharge(record, batch_uuid))
                elif kind == "fcl":
                    freight_objs.append(
                        to_freight_rate_from_ocean(
                            record, batch_uuid, db, source_file=source_file
                        )
                    )
                elif kind == "ocean_ngb_fcl":
                    freight_objs.append(
                        to_freight_rate_from_ngb(
                            record, batch_uuid, db, source_file=source_file
                        )
                    )
                else:
                    raise ActivationError(
                        code="F-ACT-05",
                        detail=f"unknown record_kind '{kind}'",
                        row_index=record.extras.get("row_index") if record.extras else None,
                        record_kind=kind,
                    )

            if air_objs:
                db.add_all(air_objs)
                imported_detail["air_freight_rates"] = len(air_objs)
            if sur_objs:
                db.add_all(sur_objs)
                imported_detail["air_surcharges"] = len(sur_objs)
            if freight_objs:
                db.add_all(freight_objs)
                imported_detail["freight_rates"] = len(freight_objs)

            imported_rows = len(air_objs) + len(sur_objs) + len(freight_objs)
            db.execute(
                update(ImportBatch)
                .where(ImportBatch.batch_id == batch_uuid)
                .values(row_count=imported_rows)
            )

        db.commit()
        draft.batch_status = "active"
        draft.activation_status = "activated"

        return ActivationResult(
            batch_id=draft.batch_id,
            file_type=file_type_raw,
            activation_status="activated",
            activated=True,
            imported_rows=imported_rows,
            skipped_rows=lcl_skipped_count,
            imported_detail=imported_detail,
            superseded_batch_ids=superseded_ids,
            warnings=warnings,
            effective_from=effective_from,
            effective_to=effective_to,
            message=f"Activated {imported_rows} rows.",
        )

    except ActivationError as err:
        try:
            db.rollback()
        except Exception:
            pass
        return ActivationResult(
            batch_id=draft.batch_id,
            file_type=file_type_raw,
            activation_status="failed",
            activated=False,
            imported_rows=0,
            skipped_rows=lcl_skipped_count,
            warnings=warnings,
            errors=[
                ActivationErrorItem(
                    code=err.code,
                    detail=err.detail,
                    row_index=err.row_index,
                    record_kind=err.record_kind,
                )
            ],
            effective_from=effective_from,
            effective_to=effective_to,
            message=f"Activation failed: {err.code} — {err.detail}",
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return ActivationResult(
            batch_id=draft.batch_id,
            file_type=file_type_raw,
            activation_status="failed",
            activated=False,
            imported_rows=0,
            skipped_rows=lcl_skipped_count,
            warnings=warnings,
            errors=[
                ActivationErrorItem(
                    code="F-ACT-05",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            ],
            effective_from=effective_from,
            effective_to=effective_to,
            message=f"Activation failed: F-ACT-05 — {type(exc).__name__}",
        )


def _query_superseded_batch_ids(
    db: Session, file_type_enum: ImportBatchFileType
) -> list[str]:
    rows = (
        db.query(ImportBatch.batch_id)
        .filter(
            ImportBatch.status == ImportBatchStatus.active,
            ImportBatch.file_type == file_type_enum,
        )
        .all()
    )
    return [str(r[0]) for r in rows]


def _supersede_old_active(
    db: Session, file_type_enum: ImportBatchFileType
) -> list[str]:
    old_ids = _query_superseded_batch_ids(db, file_type_enum)
    if old_ids:
        db.execute(
            update(ImportBatch)
            .where(
                ImportBatch.status == ImportBatchStatus.active,
                ImportBatch.file_type == file_type_enum,
            )
            .values(status=ImportBatchStatus.superseded)
        )
    return old_ids


def _plan_imported_detail(
    file_type_raw: str, records: list[ParsedRateRecord]
) -> dict[str, int]:
    detail: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for record in records:
        kind_counts[record.record_kind] = kind_counts.get(record.record_kind, 0) + 1
    if kind_counts.get("air_weekly"):
        detail["air_freight_rates"] = kind_counts["air_weekly"]
    if kind_counts.get("air_surcharge"):
        detail["air_surcharges"] = kind_counts["air_surcharge"]
    ocean_count = kind_counts.get("fcl", 0) + kind_counts.get("ocean_ngb_fcl", 0)
    if ocean_count:
        detail["freight_rates"] = ocean_count
    return detail


def _coerce_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _pick_sheet_name(draft: "DraftRateBatch") -> str | None:
    sheets = draft.sheets or []
    if not sheets:
        return None
    first = sheets[0]
    return first.get("name") if isinstance(first, dict) else None
