"""运价总览判重（邓老师 2026-06-10 口径）：

除运价编号(id)及批次/文件等元数据外，其余业务字段全部相同 → 视为重复，
列表只保留一条（id 最大=最新导入）；total 同步去重。任一业务字段不同则都保留。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.port import Port
from app.models.freight_rate import FreightRate
from app.models.air_tier_rate import AirTierRate
from app.schemas.freight_rate import RateType
from app.services.freight_rate_service import list_rates_by_type


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    carrier = Carrier(code="SJJ", name_en="SJJ Shipping")
    pol = Port(un_locode="CNSHA", name_en="Shanghai")
    pod = Port(un_locode="TWTXG", name_en="Taichung")
    session.add_all([carrier, pol, pod])
    session.flush()
    session.info["ids"] = (carrier.id, pol.id, pod.id)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _fcl_row(db: Session, **overrides) -> FreightRate:
    carrier_id, pol_id, pod_id = db.info["ids"]
    fields = dict(
        carrier_id=carrier_id,
        origin_port_id=pol_id,
        destination_port_id=pod_id,
        container_20gp=Decimal("900"),
        container_40gp=Decimal("1800"),
        container_40hq=Decimal("1800"),
        currency="USD",
        valid_to=date(2026, 5, 31),
    )
    fields.update(overrides)
    row = FreightRate(**fields)
    db.add(row)
    db.flush()
    return row


def test_identical_fcl_rows_dedup_keep_latest(db):
    """RT-45 / RT-217 场景：除编号外全同 → 只留 1 条(id 大的)，total=1。"""
    old = _fcl_row(db)
    new = _fcl_row(db)
    items, total = list_rates_by_type(db, RateType.ocean_fcl)
    assert total == 1
    assert [r.id for r in items] == [new.id]
    assert old.id != new.id  # 防御：确实是两行


def test_fcl_rows_differ_one_field_both_kept(db):
    _fcl_row(db)
    _fcl_row(db, container_40gp=Decimal("1850"))
    _, total = list_rates_by_type(db, RateType.ocean_fcl)
    assert total == 2


def test_fcl_metadata_columns_not_compared(db):
    """source_file/upload_batch_id 是元数据，不参与判重：同业务字段仍算重复。"""
    _fcl_row(db, source_file="a.xlsx", upload_batch_id="b1")
    _fcl_row(db, source_file="b.xlsx", upload_batch_id="b2")
    _, total = list_rates_by_type(db, RateType.ocean_fcl)
    assert total == 1


def test_dedup_respects_pagination(db):
    """去重发生在分页前：3 对重复 → 共 3 条，每页 2 条时第 2 页只剩 1 条。"""
    for price in ("100", "200", "300"):
        _fcl_row(db, container_20gp=Decimal(price))
        _fcl_row(db, container_20gp=Decimal(price))
    items, total = list_rates_by_type(db, RateType.ocean_fcl, page=2, page_size=2)
    assert total == 3
    assert len(items) == 1


def _tier_row(db: Session, **overrides) -> AirTierRate:
    import uuid

    fields = dict(
        origin="PVG",
        destination="KIX",
        carrier="CK/MU",
        currency="CNY",
        tier_prices={45: 17.0, 100: 14.0},
        batch_id=uuid.uuid4(),  # 元数据列，不参与判重
    )
    fields.update(overrides)
    row = AirTierRate(**fields)
    db.add(row)
    db.flush()
    return row


def test_identical_air_tier_rows_dedup(db):
    """JSON 档位列也参与判重（全同档位 → 重复）。"""
    _tier_row(db)
    _tier_row(db)
    _, total = list_rates_by_type(db, RateType.air_tier)
    assert total == 1


def test_air_tier_different_tier_prices_both_kept(db):
    _tier_row(db)
    _tier_row(db, tier_prices={45: 17.0, 100: 13.5})
    _, total = list_rates_by_type(db, RateType.air_tier)
    assert total == 2


def test_stats_align_with_deduped_list(db):
    """仪表盘统计与 RateList 各 tab 同口径：重复行只计一次。"""
    from app.models import RateStatus
    from app.services.freight_rate_service import get_rate_stats

    _fcl_row(db, status=RateStatus.active)
    _fcl_row(db, status=RateStatus.active)

    stats = get_rate_stats(db)
    assert stats["total_rates"] == 1
    assert stats["active_rates"] == 1
