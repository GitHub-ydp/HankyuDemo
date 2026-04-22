"""Step2 入札対応自动化服务模块。

当前实现范围：T-B1..T-B4（entities + protocols + rate_repository + customer_a parse）。
后续任务：T-B5 RateMatcher、T-B6 Markup/Validator、T-B7 fill、T-B8 CustomerIdentifier、
T-B9 service 编排、T-B10 API、T-B11 删旧代码、T-B12 pytest 验收全集。
"""
from app.services.step2_bidding.entities import (
    BiddingRequest,
    BiddingStatus,
    CostType,
    FillReport,
    ParsedPkg,
    PerRowReport,
    PkgRow,
    PkgSection,
    QuoteCandidate,
    RowStatus,
)
from app.services.step2_bidding.protocols import CustomerProfile, RateRepository

__all__ = [
    "BiddingRequest",
    "BiddingStatus",
    "CostType",
    "CustomerProfile",
    "FillReport",
    "ParsedPkg",
    "PerRowReport",
    "PkgRow",
    "PkgSection",
    "QuoteCandidate",
    "RateRepository",
    "RowStatus",
]
