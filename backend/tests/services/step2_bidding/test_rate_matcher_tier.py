"""RateMatcher 重量档支路：按投标包想定平均重量从做表入库的 air_tier 运价选一档(单一价)。

Customer A (Air) 投标包每条线一个単价格，货量写在「想定物量」(想定平均重量：150kg)。
matcher 在周报价候选之外，新增 tier 候选：query_air_tier → 按计费重选档 → 含油 All-in 直接当 cost。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

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
from app.services.step2_bidding.entities import CostType, PkgRow, RowStatus
from app.services.step2_bidding.rate_matcher import RateMatcher
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _add_tier_batch(session, *, destination, tier_prices, service_desc="平散货"):
    batch = ImportBatch(
        batch_id=uuid.uuid4(),
        file_type=ImportBatchFileType.air_tier,
        effective_from=date(2026, 5, 21),
        row_count=1,
        status=ImportBatchStatus.active,
    )
    session.add(batch)
    session.flush()
    session.add(
        AirTierRate(
            origin="PVG",
            destination=destination,
            service_desc=service_desc,
            tier_prices=tier_prices,
            effective_from=date(2026, 5, 21),
            currency="CNY",
            remark="以上价格均已包含附加费（燃油/战险/地面操作），但不含杂费",
            batch_id=batch.batch_id,
        )
    )
    session.commit()


def _pkg_row(*, destination_code="ATL", volume_desc, currency="CNY") -> PkgRow:
    return PkgRow(
        row_idx=12,
        section_index=1,
        section_code="PVG",
        origin_code="PVG",
        origin_text_raw="中国 (上海)",
        destination_text_raw="アメリカ (アトランタ)",
        destination_code=destination_code,
        cost_type=CostType.AIR_FREIGHT,
        currency=currency,
        volume_desc=volume_desc,
        existing_price=None,
        existing_lead_time=None,
        existing_carrier=None,
        existing_remark=None,
        is_example=False,
        client_constraint_text=None,
    )


def test_tier_candidate_picks_by_assumed_weight(db_session):
    # ATL 档位：45=65 / 100=49 / 500=49 / 1000=49；想定平均重量 150kg → 100KG 档 = 49
    _add_tier_batch(db_session, destination="ATL", tier_prices={"45": 65.0, "100": 49.0, "500": 49.0, "1000": 49.0})
    matcher = RateMatcher(Step1RateRepository(db_session))
    row = _pkg_row(volume_desc="1件当たりの想定平均重量：150kg/shipment\n想定重量帯：50kg ～300kg")

    status, cands = matcher.match(row, effective_on=date(2026, 5, 25))

    assert status == RowStatus.FILLED
    assert len(cands) == 1
    c = cands[0]
    assert c.base_price == Decimal("49.0")
    assert c.cost_price == Decimal("49.0")  # tier 含油 All-in，不加 MYC/MSC
    assert c.myc_applied is False and c.msc_applied is False
    assert c.base_price_day_index is None
    assert c.service_desc == "平散货"
    assert c.remarks_from_step1 and "不含杂费" in c.remarks_from_step1


def test_tier_only_lane_no_weekly_still_filled(db_session):
    """该航线只有重量档运价、没有周报价 → 仍能出价(证明不被『无周报价即 NO_RATE』挡掉)。"""
    _add_tier_batch(db_session, destination="AMS", tier_prices={"100": 40.0, "300": 40.0, "500": 40.0})
    matcher = RateMatcher(Step1RateRepository(db_session))
    row = _pkg_row(destination_code="AMS", volume_desc="1件当たりの想定平均重量：600kg/shipment")

    status, cands = matcher.match(row, effective_on=date(2026, 5, 25))
    assert status == RowStatus.FILLED
    assert cands[0].base_price == Decimal("40.0")  # 600kg → 500KG 档


def test_tier_no_weight_in_pkg_yields_no_rate(db_session):
    """PKG 没给重量 → 不自动默认某档 → 无候选 → NO_RATE(诚实，不乱报价)。"""
    _add_tier_batch(db_session, destination="ATL", tier_prices={"100": 49.0})
    matcher = RateMatcher(Step1RateRepository(db_session))
    row = _pkg_row(volume_desc="想定荷姿：カートン（重量未記載）")

    status, cands = matcher.match(row, effective_on=date(2026, 5, 25))
    assert status == RowStatus.NO_RATE
    assert cands == []
