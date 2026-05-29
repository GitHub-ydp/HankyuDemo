"""Step1RateRepository.query_air_tier 测试：step2 取做表入库的重量档运价(air_tier 批次)。

只返回 active 批次；destination LIKE；tier_prices 归一为 int 键放进 extras。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.base import Base
from app.models.import_batch import (
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401 触发模型注册

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_air_tier_batch(session, *, status):
    batch = ImportBatch(
        batch_id=uuid.uuid4(),
        file_type=ImportBatchFileType.air_tier,
        effective_from=date(2026, 5, 21),
        row_count=0,
        status=status,
    )
    session.add(batch)
    session.flush()
    return batch


def _add_tier(session, batch, *, destination, tier_prices, currency="CNY"):
    session.add(
        AirTierRate(
            origin="PVG",
            destination=destination,
            service_desc="平散货",
            tier_prices=tier_prices,
            effective_from=date(2026, 5, 21),
            currency=currency,
            remark="以上价格均已包含附加费（燃油/战险/地面操作），但不含杂费",
            batch_id=batch.batch_id,
        )
    )
    session.commit()


def test_query_air_tier_returns_only_active_with_int_keyed_tiers(db_session):
    active = _make_air_tier_batch(db_session, status=ImportBatchStatus.active)
    old = _make_air_tier_batch(db_session, status=ImportBatchStatus.superseded)
    _add_tier(db_session, active, destination="ATL", tier_prices={"100": 45.0, "300": 45.0})
    _add_tier(db_session, old, destination="ATL", tier_prices={"100": 99.0})

    repo = Step1RateRepository(db_session)
    rows = repo.query_air_tier(origin="PVG", destination="ATL", effective_on=date(2026, 5, 25))

    assert len(rows) == 1, "只返回 active 批次"
    r = rows[0]
    assert r.origin_port_name == "PVG"
    assert r.destination_port_name == "ATL"
    assert r.record_kind == "air_tier"
    assert r.extras["tier_prices"] == {100: 45.0, 300: 45.0}, "tier_prices 归一为 int 键"
    assert r.currency == "CNY"
    assert r.remarks and "不含杂费" in r.remarks


def test_query_air_tier_destination_like_and_currency_filter(db_session):
    b = _make_air_tier_batch(db_session, status=ImportBatchStatus.active)
    _add_tier(db_session, b, destination="アメリカ (アトランタ/ATL)", tier_prices={"100": 45.0})
    _add_tier(db_session, b, destination="AMS", tier_prices={"100": 40.0}, currency="USD")

    repo = Step1RateRepository(db_session)
    atl = repo.query_air_tier(origin="PVG", destination="ATL")
    assert len(atl) == 1 and atl[0].extras["tier_prices"] == {100: 45.0}

    cny_ams = repo.query_air_tier(origin="PVG", destination="AMS", currency="CNY")
    assert cny_ams == [], "currency 过滤生效(AMS 是 USD)"
