"""Step2 费率仓储 — Step1 入库数据的只读查询层。

设计约束（见架构任务单 §5）:
- 仅查 `import_batches.status == 'active'` 的批次
- 返回值统一为 Step1RateRow（不暴露 SQLAlchemy model）
- 不改 Step1 表结构（red line 1）

本轮（T-B3）实现:
- query_air_weekly
- query_air_surcharges
ocean/lcl 留 v2.0 占位。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.air_freight_rate import AirFreightRate
from app.models.air_surcharge import AirSurcharge
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.services.step1_rates.entities import RateSourceKind, Step1RateRow


class Step1RateRepository:
    """Step1 数据物理表 → Step1RateRow 的查询层。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ---------- Air Weekly ----------

    def query_air_weekly(
        self,
        *,
        origin: str,
        destination: str,
        effective_on: date,
        currency: str | None = None,
        airline_code_in: list[str] | None = None,
    ) -> list[Step1RateRow]:
        """查 PVG → destination 的周报价。

        - origin 精确匹配（如 'PVG'）
        - destination 用 LIKE '%dest%'，兼容 Step1 入库保留原文（见任务单 §5 说明）
        - effective_on ∈ [effective_week_start, effective_week_end]
        - 仅 active 批次
        """
        stmt = (
            select(AirFreightRate, ImportBatch)
            .join(ImportBatch, AirFreightRate.batch_id == ImportBatch.batch_id)
            .where(
                and_(
                    ImportBatch.status == ImportBatchStatus.active,
                    AirFreightRate.origin == origin,
                    AirFreightRate.destination.like(f"%{destination}%"),
                    AirFreightRate.effective_week_start <= effective_on,
                    AirFreightRate.effective_week_end >= effective_on,
                )
            )
        )
        if currency is not None:
            stmt = stmt.where(AirFreightRate.currency == currency)
        if airline_code_in:
            stmt = stmt.where(AirFreightRate.airline_code.in_(airline_code_in))

        rows = self._db.execute(stmt).all()
        return [self._weekly_to_step1_row(rate, batch) for rate, batch in rows]

    # ---------- Air Surcharges ----------

    def query_air_surcharges(
        self,
        *,
        airline_code: str,
        effective_on: date,
        currency: str | None = None,
    ) -> list[Step1RateRow]:
        """查某航司在 effective_on 当日生效的附加费（MYC/MSC）。"""
        stmt = (
            select(AirSurcharge, ImportBatch)
            .join(ImportBatch, AirSurcharge.batch_id == ImportBatch.batch_id)
            .where(
                and_(
                    ImportBatch.status == ImportBatchStatus.active,
                    AirSurcharge.airline_code == airline_code,
                    AirSurcharge.effective_date <= effective_on,
                )
            )
            .order_by(AirSurcharge.effective_date.desc())
        )
        if currency is not None:
            stmt = stmt.where(AirSurcharge.currency == currency)

        rows = self._db.execute(stmt).all()
        return [self._surcharge_to_step1_row(sur, batch) for sur, batch in rows]

    # ---------- effective_on 默认推断（R-01） ----------

    def infer_default_effective_on(
        self,
        *,
        file_type: ImportBatchFileType = ImportBatchFileType.air,
    ) -> date:
        """推断 effective_on 默认值（窗口感知）。

        策略（按优先级）：
        1. 查该 file_type 最新 active 批次（effective_to desc）：
           - today ∈ [effective_from, effective_to] → 返回 today
           - 否则返回 effective_to
        2. 找不到 active 批次 → 返回 utcnow().date()
        """
        today = datetime.utcnow().date()
        stmt = (
            select(ImportBatch.effective_from, ImportBatch.effective_to)
            .where(ImportBatch.status == ImportBatchStatus.active)
            .where(ImportBatch.file_type == file_type)
            .order_by(ImportBatch.effective_to.desc())
            .limit(1)
        )
        row = self._db.execute(stmt).first()
        if row is None:
            return today
        eff_from, eff_to = row
        if eff_from is not None and eff_to is not None and eff_from <= today <= eff_to:
            return today
        if eff_to is not None:
            return eff_to
        return today

    # ---------- Ocean / LCL 占位 ----------

    def query_ocean_fcl(self, **kwargs: Any) -> list[Step1RateRow]:
        # TODO(v2.0): FreightRate 表查询；Customer A v1.0 全为 Air，不需要
        raise NotImplementedError("query_ocean_fcl 将于 v2.0 实现")

    def query_lcl(self, **kwargs: Any) -> list[Step1RateRow]:
        # TODO(v2.0): LclRate 表查询
        raise NotImplementedError("query_lcl 将于 v2.0 实现")

    # ---------- Converters ----------

    @staticmethod
    def _weekly_to_step1_row(
        rate: AirFreightRate, batch: ImportBatch
    ) -> Step1RateRow:
        return Step1RateRow(
            origin_port_name=rate.origin,
            destination_port_name=rate.destination,
            airline_code=rate.airline_code,
            service_desc=rate.service_desc,
            effective_week_start=rate.effective_week_start,
            effective_week_end=rate.effective_week_end,
            price_day1=_as_decimal(rate.price_day1),
            price_day2=_as_decimal(rate.price_day2),
            price_day3=_as_decimal(rate.price_day3),
            price_day4=_as_decimal(rate.price_day4),
            price_day5=_as_decimal(rate.price_day5),
            price_day6=_as_decimal(rate.price_day6),
            price_day7=_as_decimal(rate.price_day7),
            record_kind="air_weekly",
            currency=rate.currency or "CNY",
            remarks=rate.remark,
            source_type=RateSourceKind.excel.value,
            source_file=batch.source_file,
            upload_batch_id=str(batch.batch_id),
            extras={
                "step2_record_id": rate.id,
                "step2_batch_status": batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status),
                "airline_codes": _extract_airline_codes(rate.service_desc),
                "has_must_go": "must go" in (rate.remark or "").lower(),
                "is_case_by_case": "case by case" in (rate.remark or "").lower(),
            },
        )

    @staticmethod
    def _surcharge_to_step1_row(
        sur: AirSurcharge, batch: ImportBatch
    ) -> Step1RateRow:
        return Step1RateRow(
            airline_code=sur.airline_code,
            valid_from=sur.effective_date,
            record_kind="air_surcharge",
            currency=sur.currency or "CNY",
            remarks=sur.remarks,
            source_type=RateSourceKind.excel.value,
            source_file=batch.source_file,
            upload_batch_id=str(batch.batch_id),
            extras={
                "step2_record_id": sur.id,
                "area": sur.area,
                "from_region": sur.from_region,
                "destination_scope": sur.destination_scope,
                "myc_min": _as_decimal(sur.myc_min),
                "myc_fee_per_kg": _as_decimal(sur.myc_fee_per_kg),
                "msc_min": _as_decimal(sur.msc_min),
                "msc_fee_per_kg": _as_decimal(sur.msc_fee_per_kg),
                "step2_batch_status": batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status),
                "all_fees_dash": _all_fees_dash(
                    sur.myc_min, sur.myc_fee_per_kg, sur.msc_min, sur.msc_fee_per_kg
                ),
            },
        )


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


_AIRLINE_CODE_RE = re.compile(r"\b([A-Z0-9]{2})\b")


def _extract_airline_codes(service_desc: str | None) -> list[str]:
    if not service_desc:
        return []
    seen: list[str] = []
    for match in _AIRLINE_CODE_RE.findall(service_desc):
        if match not in seen:
            seen.append(match)
    return seen


def _all_fees_dash(*values: Any) -> bool:
    return all(v is None for v in values)
