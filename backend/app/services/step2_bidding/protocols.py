"""Step2 入札対応 接口协议。

见架构任务单 §5。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from app.services.step1_rates.entities import Step1RateRow
    from app.services.step2_bidding.entities import (
        FillReport,
        ParsedPkg,
        PerRowReport,
    )


@runtime_checkable
class CustomerProfile(Protocol):
    """客户适配器协议。每家客户一个独立实现，不抽公共基类。"""

    customer_code: str
    display_name: str
    priority: int

    def detect(self, path: Path, hint: str | None = None) -> bool: ...

    def parse(self, path: Path, bid_id: str, period: str) -> "ParsedPkg": ...

    def fill(
        self,
        source_path: Path,
        parsed: "ParsedPkg",
        row_reports: list["PerRowReport"],
        variant: str,
        output_path: Path,
    ) -> None: ...


@runtime_checkable
class RateRepository(Protocol):
    """Step2 只读 Step1 入库数据的唯一入口。

    - 只返回 active 批次下的记录
    - 返回类型统一为 Step1RateRow，不暴露 SQLAlchemy model
    """

    def query_air_weekly(
        self,
        *,
        origin: str,
        destination: str,
        effective_on: date,
        currency: str | None = None,
        airline_code_in: list[str] | None = None,
    ) -> list["Step1RateRow"]: ...

    def query_air_surcharges(
        self,
        *,
        airline_code: str,
        effective_on: date,
        currency: str | None = None,
    ) -> list["Step1RateRow"]: ...

    def query_ocean_fcl(self, **kwargs) -> list["Step1RateRow"]: ...

    def query_lcl(self, **kwargs) -> list["Step1RateRow"]: ...
