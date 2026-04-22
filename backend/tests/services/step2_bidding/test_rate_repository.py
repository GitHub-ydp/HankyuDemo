"""Step1RateRepository 单元测试（T-B3）。

用 sqlite in-memory 建 Step1 真实模型表，构造 active / superseded 批次两条对照数据，
验证：
1. 只返回 active 批次的记录
2. destination LIKE 匹配（兼容 Step1 入库保留原文）
3. effective_on 落在周内才返回
4. currency / airline_code_in 过滤
5. 返回类型为 Step1RateRow（不暴露 SQLAlchemy model）
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.air_freight_rate import AirFreightRate
from app.models.air_surcharge import AirSurcharge
from app.models.base import Base
from app.models.import_batch import (
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)
from app.services.step1_rates.entities import Step1RateRow
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    # 触发全部 model 注册
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_batch(
    session: Session,
    *,
    status: ImportBatchStatus,
    source_file: str,
) -> ImportBatch:
    batch = ImportBatch(
        batch_id=uuid.uuid4(),
        file_type=ImportBatchFileType.air,
        source_file=source_file,
        sheet_name="Apr 20 to Apr 26",
        effective_from=date(2026, 4, 20),
        effective_to=date(2026, 4, 26),
        row_count=0,
        status=status,
        imported_by="test",
    )
    session.add(batch)
    session.flush()
    return batch


def _add_weekly(
    session: Session,
    batch: ImportBatch,
    *,
    origin: str = "PVG",
    destination: str,
    airline_code: str,
    price_day1: Decimal = Decimal("50.00"),
    currency: str = "CNY",
) -> AirFreightRate:
    rate = AirFreightRate(
        origin=origin,
        destination=destination,
        airline_code=airline_code,
        service_desc=f"PVG-{destination} via {airline_code}",
        effective_week_start=date(2026, 4, 20),
        effective_week_end=date(2026, 4, 26),
        price_day1=price_day1,
        price_day2=price_day1,
        price_day3=price_day1,
        price_day4=price_day1,
        price_day5=price_day1,
        price_day6=price_day1,
        price_day7=price_day1,
        currency=currency,
        remark="test weekly",
        batch_id=batch.batch_id,
    )
    session.add(rate)
    session.flush()
    return rate


def _add_surcharge(
    session: Session,
    batch: ImportBatch,
    *,
    airline_code: str,
    effective_date: date,
    myc: Decimal = Decimal("0.50"),
    msc: Decimal = Decimal("0.30"),
    currency: str = "CNY",
) -> AirSurcharge:
    sur = AirSurcharge(
        area="Asia",
        from_region="PVG",
        airline_code=airline_code,
        effective_date=effective_date,
        myc_min=Decimal("50.00"),
        myc_fee_per_kg=myc,
        msc_min=Decimal("30.00"),
        msc_fee_per_kg=msc,
        destination_scope="ALL",
        remarks="test surcharge",
        currency=currency,
        batch_id=batch.batch_id,
    )
    session.add(sur)
    session.flush()
    return sur


def test_query_air_weekly_returns_active_batch_only(db_session: Session):
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="active.xlsx"
    )
    superseded = _make_batch(
        db_session,
        status=ImportBatchStatus.superseded,
        source_file="superseded.xlsx",
    )
    _add_weekly(db_session, active, destination="ATL", airline_code="MU")
    _add_weekly(
        db_session,
        superseded,
        destination="ATL",
        airline_code="CA",
        price_day1=Decimal("30.00"),
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    rows = repo.query_air_weekly(
        origin="PVG", destination="ATL", effective_on=date(2026, 4, 22)
    )
    assert len(rows) == 1
    assert rows[0].airline_code == "MU"
    assert isinstance(rows[0], Step1RateRow)
    assert rows[0].record_kind == "air_weekly"


def test_query_air_weekly_destination_like_match(db_session: Session):
    """Step1 入库保留 destination 原文（如 'アトランタ (ATL)'），应用 LIKE 匹配。"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(db_session, active, destination="アトランタ (ATL)", airline_code="MU")
    db_session.commit()

    repo = Step1RateRepository(db_session)
    rows = repo.query_air_weekly(
        origin="PVG", destination="ATL", effective_on=date(2026, 4, 22)
    )
    assert len(rows) == 1
    assert "ATL" in rows[0].destination_port_name


def test_query_air_weekly_effective_on_out_of_week_excluded(db_session: Session):
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(db_session, active, destination="ATL", airline_code="MU")
    db_session.commit()

    repo = Step1RateRepository(db_session)
    # 4/27 超出 [4/20, 4/26]
    rows = repo.query_air_weekly(
        origin="PVG", destination="ATL", effective_on=date(2026, 4, 27)
    )
    assert rows == []


def test_query_air_weekly_currency_and_airline_filters(db_session: Session):
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(db_session, active, destination="ATL", airline_code="MU", currency="CNY")
    _add_weekly(db_session, active, destination="ATL", airline_code="OZ", currency="USD")
    _add_weekly(db_session, active, destination="ATL", airline_code="NH", currency="CNY")
    db_session.commit()

    repo = Step1RateRepository(db_session)

    cny_rows = repo.query_air_weekly(
        origin="PVG",
        destination="ATL",
        effective_on=date(2026, 4, 22),
        currency="CNY",
    )
    assert {r.airline_code for r in cny_rows} == {"MU", "NH"}

    filtered = repo.query_air_weekly(
        origin="PVG",
        destination="ATL",
        effective_on=date(2026, 4, 22),
        airline_code_in=["MU"],
    )
    assert [r.airline_code for r in filtered] == ["MU"]


def test_query_air_surcharges_returns_active_and_before_effective(db_session: Session):
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    superseded = _make_batch(
        db_session, status=ImportBatchStatus.superseded, source_file="b.xlsx"
    )
    _add_surcharge(
        db_session, active, airline_code="MU", effective_date=date(2026, 4, 1)
    )
    _add_surcharge(
        db_session, active, airline_code="MU", effective_date=date(2026, 5, 1)
    )
    _add_surcharge(
        db_session, superseded, airline_code="MU", effective_date=date(2026, 3, 1)
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    rows = repo.query_air_surcharges(
        airline_code="MU", effective_on=date(2026, 4, 22)
    )
    assert len(rows) == 1  # 仅 4/1 那条；5/1 尚未生效；superseded 被排除
    row = rows[0]
    assert row.record_kind == "air_surcharge"
    assert row.extras["myc_fee_per_kg"] == Decimal("0.50")
    assert row.extras["msc_fee_per_kg"] == Decimal("0.30")


def test_ocean_and_lcl_raise_not_implemented(db_session: Session):
    repo = Step1RateRepository(db_session)
    with pytest.raises(NotImplementedError):
        repo.query_ocean_fcl()
    with pytest.raises(NotImplementedError):
        repo.query_lcl()
