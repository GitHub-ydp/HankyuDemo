"""T-B5 RateMatcher 单测。

复用 T-B3 sqlite in-memory + 真实 model 模式（参见 test_rate_repository.py:30-100）。
覆盖任务单 §8 的 V-B5-01..V-B5-11。
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
from app.services.step2_bidding.entities import (
    CostType,
    PkgRow,
    RowStatus,
)
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
    airline_code: str | None,
    service_desc: str,
    price_day1: Decimal = Decimal("50.00"),
    currency: str = "CNY",
    remark: str = "test weekly",
) -> AirFreightRate:
    rate = AirFreightRate(
        origin=origin,
        destination=destination,
        airline_code=airline_code,
        service_desc=service_desc,
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
        remark=remark,
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
    effective_date: date = date(2026, 4, 1),
    myc_min: Decimal | None = Decimal("50.00"),
    myc: Decimal | None = Decimal("2.00"),
    msc_min: Decimal | None = Decimal("30.00"),
    msc: Decimal | None = Decimal("1.00"),
    currency: str = "CNY",
) -> AirSurcharge:
    sur = AirSurcharge(
        area="Asia",
        from_region="PVG",
        airline_code=airline_code,
        effective_date=effective_date,
        myc_min=myc_min,
        myc_fee_per_kg=myc,
        msc_min=msc_min,
        msc_fee_per_kg=msc,
        destination_scope="ALL",
        remarks="test surcharge",
        currency=currency,
        batch_id=batch.batch_id,
    )
    session.add(sur)
    session.flush()
    return sur


def _make_pkg_row(
    *,
    section_code: str = "PVG",
    origin_code: str = "PVG",
    destination_code: str = "ATL",
    cost_type: CostType = CostType.AIR_FREIGHT,
    currency: str = "CNY",
    is_example: bool = False,
    existing_price: Decimal | None = None,
) -> PkgRow:
    return PkgRow(
        row_idx=10,
        section_index=0,
        section_code=section_code,
        origin_code=origin_code,
        origin_text_raw="上海 (PVG)",
        destination_text_raw="アトランタ (ATL)",
        destination_code=destination_code,
        cost_type=cost_type,
        currency=currency,
        volume_desc=None,
        existing_price=existing_price,
        existing_lead_time=None,
        existing_carrier=None,
        existing_remark=None,
        is_example=is_example,
        client_constraint_text=None,
    )


# ---------- V-B5-01..05 预过滤短路 ----------

def test_v_b5_01_non_local_leg(db_session: Session):
    """V-B5-01：section_code='NRT' → NON_LOCAL_LEG"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(section_code="NRT")
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.NON_LOCAL_LEG
    assert candidates == []


def test_v_b5_02_example_row(db_session: Session):
    """V-B5-02：is_example=True → EXAMPLE"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(is_example=True)
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.EXAMPLE
    assert candidates == []


def test_v_b5_03_local_delivery(db_session: Session):
    """V-B5-03：cost_type=LOCAL_DELIVERY → LOCAL_DELIVERY_MANUAL"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(cost_type=CostType.LOCAL_DELIVERY)
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.LOCAL_DELIVERY_MANUAL
    assert candidates == []


def test_v_b5_04_already_filled(db_session: Session):
    """V-B5-04：existing_price != 0 → ALREADY_FILLED"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(existing_price=Decimal("100.00"))
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.ALREADY_FILLED
    assert candidates == []


def test_v_b5_05_unknown_destination(db_session: Session):
    """V-B5-05：destination_code='UNKNOWN' → NO_RATE"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(destination_code="UNKNOWN")
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.NO_RATE
    assert candidates == []


# ---------- V-B5-06 happy path ----------

def test_v_b5_06_happy_path_with_surcharge(db_session: Session):
    """V-B5-06：周表 'OZ direct' + surcharge OZ(myc=2, msc=1) → cost=base+3"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="アトランタ (ATL)",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("50.00"),
    )
    _add_surcharge(
        db_session,
        active,
        airline_code="OZ",
        myc=Decimal("2.00"),
        msc=Decimal("1.00"),
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))

    assert status == RowStatus.FILLED
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.airline_codes == ["OZ"]
    assert cand.myc_applied is True
    assert cand.msc_applied is True
    assert cand.cost_price == Decimal("53.00")
    assert cand.base_price == Decimal("50.00")
    assert cand.base_price_day_index == 3  # 4/22 - 4/20 = 2 → day3
    assert cand.source_batch_id == str(active.batch_id)
    assert cand.source_weekly_record_id != 0
    assert cand.source_surcharge_record_id is not None
    assert cand.currency == "CNY"


# ---------- V-B5-07 无 surcharge 兜底 ----------

def test_v_b5_07_no_surcharge_match(db_session: Session):
    """V-B5-07：service_desc='CK direct'，surcharge 表无 CK → cost=base, myc/msc 不适用"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="CK direct",
        price_day1=Decimal("60.00"),
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))

    assert status == RowStatus.FILLED
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.airline_codes == ["CK"]
    assert cand.myc_applied is False
    assert cand.msc_applied is False
    assert cand.myc_fee_per_kg is None
    assert cand.msc_fee_per_kg is None
    assert cand.cost_price == Decimal("60.00")
    assert cand.source_surcharge_record_id is None


# ---------- V-B5-08 all_fees_dash 跳过 ----------

def test_v_b5_08_all_fees_dash_skip(db_session: Session):
    """V-B5-08：surcharge 4 项均 None（all_fees_dash=True）→ 跳过该航司；唯一航司则 NO_RATE"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("50.00"),
    )
    _add_surcharge(
        db_session,
        active,
        airline_code="OZ",
        myc_min=None,
        myc=None,
        msc_min=None,
        msc=None,
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))

    assert status == RowStatus.NO_RATE
    assert candidates == []


# ---------- V-B5-09 carrier_preference 硬约束 ----------

def test_v_b5_09_carrier_preference_block(db_session: Session):
    """V-B5-09：weekly 仅 OZ 候选，carrier_preference=['NH'] → CONSTRAINT_BLOCK"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("50.00"),
    )
    _add_surcharge(db_session, active, airline_code="OZ")
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(
        row,
        effective_on=date(2026, 4, 22),
        carrier_preference=["NH"],
    )

    assert status == RowStatus.CONSTRAINT_BLOCK
    assert candidates == []


# ---------- V-B5-10 排序 + 截断 ----------

def test_v_b5_10_sort_and_truncate(db_session: Session):
    """V-B5-10：3 条不同价 (45/50/40)，max_candidates=2 → [40, 45]"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("45.00"),
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="NH direct",
        price_day1=Decimal("50.00"),
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="CA direct",
        price_day1=Decimal("40.00"),
    )
    # 三家航司都没有 surcharge → cost = base
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(
        row, effective_on=date(2026, 4, 22), max_candidates=2
    )

    assert status == RowStatus.FILLED
    assert len(candidates) == 2
    assert candidates[0].cost_price == Decimal("40.00")
    assert candidates[1].cost_price == Decimal("45.00")


# ---------- V-B5-11 superseded 批次不应混入 ----------

def test_v_b5_11_superseded_batch_ignored(db_session: Session):
    """V-B5-11：active 批次价 100、superseded 批次价 50 → 只返回 100"""
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="active.xlsx"
    )
    superseded = _make_batch(
        db_session,
        status=ImportBatchStatus.superseded,
        source_file="superseded.xlsx",
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("100.00"),
    )
    _add_weekly(
        db_session,
        superseded,
        destination="ATL",
        airline_code=None,
        service_desc="NH direct",
        price_day1=Decimal("50.00"),
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))

    assert status == RowStatus.FILLED
    assert len(candidates) == 1
    assert candidates[0].cost_price == Decimal("100.00")
    assert candidates[0].airline_codes == ["OZ"]


# ---------- V-B5-12 同价排序：score 高（非 case_by_case）排前 ----------

def test_v_b5_12_score_secondary_sort(db_session: Session):
    """V-B5-12：两条候选 cost_price 相同（=50），其中一条 remark='case by case'
    触发 score ×0.5 衰减；按 (cost_price asc, -match_score) 排序后，
    非 case_by_case 的应排在前。
    """
    active = _make_batch(
        db_session, status=ImportBatchStatus.active, source_file="a.xlsx"
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="OZ direct",
        price_day1=Decimal("50.00"),
        remark="case by case",
    )
    _add_weekly(
        db_session,
        active,
        destination="ATL",
        airline_code=None,
        service_desc="NH direct",
        price_day1=Decimal("50.00"),
        remark="normal",
    )
    db_session.commit()

    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row()
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))

    assert status == RowStatus.FILLED
    assert len(candidates) == 2
    assert candidates[0].cost_price == candidates[1].cost_price == Decimal("50.00")
    assert candidates[0].step1_case_by_case is False
    assert candidates[0].airline_codes == ["NH"]
    assert candidates[1].step1_case_by_case is True
    assert candidates[1].airline_codes == ["OZ"]
    assert candidates[0].match_score > candidates[1].match_score
