"""仪表盘统计(get_rate_stats)应计入做表→入库的 air_tier 档位运价。

回归：air_tier 表是 step1「确认入库」新加的，旧的 get_rate_stats 只数
FreightRate/AirFreightRate/AirSurcharge/Lcl，对 air_tier 视而不见 → 用户入库后
仪表盘仍显示 0。本测试锁死「入库的档位运价要被统计、且只数 active 批」。
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.services.freight_rate_service import get_rate_stats
from app.services.step1_rates.sheet_builder import db_writer


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401 触发全部模型注册

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _tier_row(dest: str, tiers: dict) -> dict:
    return {
        "origin": "PVG",
        "destination": dest,
        "service": "CK/MU",
        "tier_prices": tiers,
        "effective_week_start": "2026-05-21",
    }


def test_stats_counts_committed_air_tier_rows(db_session):
    db_writer.commit_tier_rows(
        [_tier_row("KIX", {"45": 17, "100": 14}), _tier_row("BKK", {"100": 16})],
        db_session,
    )

    stats = get_rate_stats(db_session)

    assert stats["total_rates"] == 2
    assert stats["active_rates"] == 2


def test_stats_excludes_superseded_air_tier(db_session):
    # 两次入库：第一批被降级 superseded，仪表盘应只数 active 批。
    db_writer.commit_tier_rows([_tier_row("KIX", {"100": 14})], db_session)
    db_writer.commit_tier_rows(
        [_tier_row("KIX", {"100": 13}), _tier_row("NRT", {"100": 13})],
        db_session,
    )

    stats = get_rate_stats(db_session)

    assert stats["total_rates"] == 2  # 仅 active 批的 2 条，不含被降级的 1 条


def test_stats_counts_air_tier_distinct_routes(db_session):
    # 3 行但只有 2 条不同航线（PVG-KIX 两档算一条）。
    db_writer.commit_tier_rows(
        [
            _tier_row("KIX", {"45": 17, "100": 14}),
            _tier_row("KIX", {"500": 13}),
            _tier_row("BKK", {"100": 16}),
        ],
        db_session,
    )

    stats = get_rate_stats(db_session)

    assert stats["routes_count"] == 2
