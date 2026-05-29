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
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus, SourceType
from app.models.import_batch import (
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)
from app.services.step1_rates.activator_mappers import _resolve_port


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


@dataclass
class OceanCommitResult:
    """海运入库结果。fcl_rows=0 时不建批次，batch_id 为空串。"""

    batch_id: str
    fcl_rows: int
    skipped_no_price: int
    skipped_unresolved: int


_OCEAN_PRICE_KEYS = ("container_20gp", "container_40gp", "container_40hq")


def commit_ocean_rows(
    rows: list[dict[str, Any]],
    db: Session,
    *,
    source_file: str | None = None,
    imported_by: str | None = None,
) -> OceanCommitResult:
    """审核后的海运行入库 FreightRate(FCL)；无箱型价/港口船司解析不到的行跳过计数。

    只写 active；新批次 supersede 上一个 active 的 ocean 批(与 air_tier 套路一致)。
    """
    priced = [r for r in rows if any(r.get(k) is not None for k in _OCEAN_PRICE_KEYS)]
    skipped_no_price = len(rows) - len(priced)
    if not priced:
        return OceanCommitResult(batch_id="", fcl_rows=0, skipped_no_price=skipped_no_price, skipped_unresolved=0)

    db.execute(
        update(ImportBatch)
        .where(
            ImportBatch.file_type == ImportBatchFileType.ocean,
            ImportBatch.status == ImportBatchStatus.active,
        )
        .values(status=ImportBatchStatus.superseded)
    )

    batch_uuid = uuid.uuid4()
    batch = ImportBatch(
        batch_id=batch_uuid,
        file_type=ImportBatchFileType.ocean,
        source_file=source_file,
        status=ImportBatchStatus.active,
        imported_by=imported_by,
    )
    db.add(batch)

    written = 0
    skipped_unresolved = 0
    for r in priced:
        origin_port = _resolve_port(db, r.get("origin") or "SHANGHAI")
        dest_port = _resolve_port(db, r.get("destination"))
        carrier_id = _resolve_carrier_id(db, r.get("carrier"))
        if origin_port is None or dest_port is None or carrier_id is None:
            skipped_unresolved += 1
            continue
        db.add(
            FreightRate(
                carrier_id=carrier_id,
                origin_port_id=origin_port.id,
                destination_port_id=dest_port.id,
                container_20gp=_to_decimal(r.get("container_20gp")),
                container_40gp=_to_decimal(r.get("container_40gp")),
                container_40hq=_to_decimal(r.get("container_40hq")),
                container_45=_to_decimal(r.get("container_45")),
                valid_from=_to_date(r.get("valid_from")),
                valid_to=_to_date(r.get("valid_to")),
                rate_level=(r.get("rate_level") or None) and str(r.get("rate_level"))[:10],
                service_code=r.get("service_code"),
                via=r.get("via"),
                is_direct=r.get("is_direct", True),
                rmks=r.get("commodity"),
                transit_days=_to_int(r.get("transit_days")),
                currency="USD",
                status=RateStatus.active,
                source_type=SourceType.excel,
                source_file=source_file or r.get("source_file"),
                remarks=r.get("remark"),
                batch_id=batch_uuid,
            )
        )
        written += 1

    batch.row_count = written
    db.commit()
    return OceanCommitResult(
        batch_id=str(batch_uuid),
        fcl_rows=written,
        skipped_no_price=skipped_no_price,
        skipped_unresolved=skipped_unresolved,
    )


def _resolve_carrier_id(db: Session, name: Any) -> int | None:
    """宽松解析船司 → id(查不到返回 None，不抛异常)。"""
    if not name:
        return None
    n = str(name).strip()
    c = db.query(Carrier).filter(Carrier.code == n).first()
    if c is None:
        c = db.query(Carrier).filter(Carrier.name_en.ilike(f"%{n}%")).first()
    if c is None:
        c = db.query(Carrier).filter(Carrier.code.ilike(f"%{n}%")).first()
    return c.id if c else None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
