"""做表运价 → 入库（save-from-session）。

审核台勾选/编辑后的归一行(就是下载 POST 的那份 rows)直接落库，**不重解析下载的 xlsx**。
只持久化「档位行」(带 tier_prices)；周表行(day1-7，Market Price)跳过并计数——它另有 adapter
导入路径，硬塞会和现有 weekly air 批次互相 supersede。

档位行写进 air_tier_rates，挂在一个 file_type=air_tier 的 ImportBatch 下；每次入库降级上一个
active 的 air_tier 批次(只降 air_tier，不碰 weekly air)，与 activator 的批次语义一致。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.import_batch import (
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)


@dataclass
class CommitResult:
    """入库结果。tier_rows=0 时不建批次，batch_id 为空串。"""

    batch_id: str
    tier_rows: int
    skipped_weekly: int


def commit_tier_rows(
    rows: list[dict[str, Any]],
    db: Session,
    *,
    source_file: str | None = None,
    imported_by: str | None = None,
) -> CommitResult:
    """把审核后的档位行入库；周表行跳过计数。无档位行则不建批次。"""
    tier_rows = [r for r in rows if r.get("tier_prices")]
    skipped_weekly = len(rows) - len(tier_rows)

    if not tier_rows:
        return CommitResult(batch_id="", tier_rows=0, skipped_weekly=skipped_weekly)

    # 只降级上一个 active 的 air_tier 批次(weekly air 不受影响)。
    db.execute(
        update(ImportBatch)
        .where(
            ImportBatch.file_type == ImportBatchFileType.air_tier,
            ImportBatch.status == ImportBatchStatus.active,
        )
        .values(status=ImportBatchStatus.superseded)
    )

    batch_uuid = uuid.uuid4()
    effective = _first_effective(tier_rows)
    batch = ImportBatch(
        batch_id=batch_uuid,
        file_type=ImportBatchFileType.air_tier,
        source_file=source_file,
        effective_from=effective,
        row_count=len(tier_rows),
        status=ImportBatchStatus.active,
        imported_by=imported_by,
    )
    db.add(batch)

    for r in tier_rows:
        db.add(
            AirTierRate(
                origin=r.get("origin") or "PVG",
                destination=r.get("destination") or "",
                service_desc=r.get("service"),
                tier_prices=_norm_tiers(r["tier_prices"]),
                effective_from=_to_date(r.get("effective_week_start")),
                currency=r.get("currency") or "CNY",
                remark=r.get("remark"),
                batch_id=batch_uuid,
            )
        )

    db.commit()
    return CommitResult(
        batch_id=str(batch_uuid),
        tier_rows=len(tier_rows),
        skipped_weekly=skipped_weekly,
    )


def _norm_tiers(tier_prices: dict[Any, Any]) -> dict[int, float]:
    """键归一为 int(KG)、值 float——JSON 往返后键可能是字符串('45')。"""
    return {int(kg): float(price) for kg, price in tier_prices.items() if price is not None}


def _first_effective(rows: list[dict[str, Any]]) -> date | None:
    for r in rows:
        d = _to_date(r.get("effective_week_start"))
        if d is not None:
            return d
    return None


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
