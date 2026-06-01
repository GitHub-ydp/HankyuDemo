"""做表运价入库(db_writer)测试：审核台勾选/编辑后的档位行 → air_tier 批次 + AirTierRate 行。

只持久化「档位行」(带 tier_prices)；周表行(day1-7，Market Price)跳过并计数(它另有 adapter 导入路径)。
入库走 save-from-session：直接吃前端传回的归一行(JSON 往返后 tier_prices 键是字符串)。
air_tier 批次与 weekly air 批次**隔离**：互不 supersede。
"""
from __future__ import annotations

import uuid

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.base import Base
from app.models.import_batch import (
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
)
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


def _tier_row(dest: str, tiers: dict, **kw):
    row = {
        "origin": "PVG",
        "destination": dest,
        "service": "CK/MU",
        "tier_prices": tiers,
        "remark": "含油",
        "effective_week_start": "2026-05-21",
    }
    row.update(kw)
    return row


def _norm(tp: dict) -> dict:
    # JSON 列读回后键可能是字符串，统一成 int 再比较
    return {int(k): float(v) for k, v in tp.items()}


def test_commit_persists_tier_rows_and_skips_weekly(db_session):
    rows = [
        _tier_row("KIX", {"45": 17, "100": 14}),
        _tier_row("BKK", {"100": 16, "300": 16}),
        {"origin": "PVG", "destination": "NRT", "service": "CK", "day1": 14},  # 周表行→跳过
    ]
    res = db_writer.commit_tier_rows(rows, db_session)

    assert res.tier_rows == 2
    assert res.skipped_weekly == 1
    assert res.batch_id

    batches = (
        db_session.execute(
            select(ImportBatch).where(ImportBatch.file_type == ImportBatchFileType.air_tier)
        )
        .scalars()
        .all()
    )
    assert len(batches) == 1
    assert batches[0].status == ImportBatchStatus.active
    assert batches[0].row_count == 2

    tiers = db_session.execute(select(AirTierRate)).scalars().all()
    assert len(tiers) == 2
    kix = next(t for t in tiers if t.destination == "KIX")
    assert kix.origin == "PVG"
    assert kix.service_desc == "CK/MU"
    assert _norm(kix.tier_prices) == {45: 17.0, 100: 14.0}
    assert kix.remark == "含油"
    assert kix.effective_from == date(2026, 5, 21)
    assert str(kix.batch_id) == res.batch_id


def test_commit_supersedes_prior_air_tier_but_not_weekly(db_session):
    # 先放一个 active 的 weekly air 批次，证明 air_tier 入库不会把它降级
    weekly = ImportBatch(
        batch_id=uuid.uuid4(),
        file_type=ImportBatchFileType.air,
        status=ImportBatchStatus.active,
        row_count=0,
    )
    db_session.add(weekly)
    db_session.commit()

    db_writer.commit_tier_rows([_tier_row("KIX", {"100": 14})], db_session)
    res2 = db_writer.commit_tier_rows([_tier_row("KIX", {"100": 13})], db_session)

    air_tier = (
        db_session.execute(
            select(ImportBatch).where(ImportBatch.file_type == ImportBatchFileType.air_tier)
        )
        .scalars()
        .all()
    )
    actives = [b for b in air_tier if b.status == ImportBatchStatus.active]
    superseded = [b for b in air_tier if b.status == ImportBatchStatus.superseded]
    assert len(actives) == 1 and str(actives[0].batch_id) == res2.batch_id
    assert len(superseded) == 1

    db_session.refresh(weekly)
    assert weekly.status == ImportBatchStatus.active, "weekly air 批次不应被 air_tier 入库降级"


def test_commit_all_weekly_creates_no_tier_batch(db_session):
    rows = [{"origin": "PVG", "destination": "NRT", "service": "CK", "day1": 14}]
    res = db_writer.commit_tier_rows(rows, db_session)

    assert res.tier_rows == 0
    assert res.skipped_weekly == 1
    assert res.batch_id == ""
    assert db_session.execute(select(ImportBatch)).scalars().all() == []


def test_air_tier_rate_has_multidim_columns():
    from app.models.air_tier_rate import AirTierRate
    cols = set(AirTierRate.__table__.columns.keys())
    assert {"cargo_class", "packing", "density", "carrier"} <= cols


def test_commit_persists_multidim_fields(db_session):
    row = _tier_row(
        "LAX", {"45": 60, "100": 60},
        cargo_class="普货", packing="托", density="1:167",
        carrier="CK/CA", currency="CNY", effective_to="2026-05-29",
    )
    res = db_writer.commit_tier_rows([row], db_session)
    assert res.tier_rows == 1

    rate = db_session.execute(select(AirTierRate)).scalars().one()
    assert rate.cargo_class == "普货"
    assert rate.packing == "托"
    assert rate.density == "1:167"
    assert rate.carrier == "CK/CA"
    assert rate.currency == "CNY"
    assert rate.effective_to == date(2026, 5, 29)
