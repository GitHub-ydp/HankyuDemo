"""做表海运行 → 入库 FreightRate(commit_ocean_rows)。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.models.port import Port
from app.services.step1_rates.sheet_builder import db_writer


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401 注册全部模型

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="CNSHA", name_en="SHANGHAI", name_cn="上海"),
        Port(un_locode="HKHKG", name_en="HONG KONG", name_cn="香港"),
        Carrier(code="KMTC", name_en="KOREA MARINE TRANSPORT", name_cn="高丽海运"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _row(dest, c20, c40hq, carrier="KMTC"):
    return {
        "origin": "SHANGHAI", "destination": dest, "carrier": carrier,
        "container_20gp": c20, "container_40gp": None, "container_40hq": c40hq,
        "transit_days": 3, "remark": "直达",
    }


def test_commit_ocean_writes_freightrate(db_session):
    res = db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("250"), Decimal("500"))], db_session)
    assert res.fcl_rows == 1
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.container_20gp == Decimal("250")
    assert fr.container_40hq == Decimal("500")
    assert fr.status == RateStatus.active
    assert fr.currency == "USD"
    sha = db_session.execute(select(Port).where(Port.un_locode == "CNSHA")).scalars().one()
    hkg = db_session.execute(select(Port).where(Port.un_locode == "HKHKG")).scalars().one()
    km = db_session.execute(select(Carrier).where(Carrier.code == "KMTC")).scalars().one()
    assert fr.origin_port_id == sha.id
    assert fr.destination_port_id == hkg.id
    assert fr.carrier_id == km.id
    batch = db_session.execute(select(ImportBatch)).scalars().one()
    assert batch.file_type == ImportBatchFileType.ocean
    assert batch.status == ImportBatchStatus.active
    assert batch.row_count == 1


def test_commit_ocean_skips_unresolved_and_no_price(db_session):
    rows = [
        _row("HONG KONG", Decimal("250"), Decimal("500")),
        _row("NOWHERE PORT", Decimal("100"), Decimal("200")),
        {"origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC"},
    ]
    res = db_writer.commit_ocean_rows(rows, db_session)
    assert res.fcl_rows == 1
    assert res.skipped_unresolved == 1
    assert res.skipped_no_price == 1


def test_commit_ocean_supersedes_prior_active(db_session):
    db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("250"), Decimal("500"))], db_session)
    res2 = db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("240"), Decimal("480"))], db_session)
    batches = db_session.execute(
        select(ImportBatch).where(ImportBatch.file_type == ImportBatchFileType.ocean)
    ).scalars().all()
    actives = [b for b in batches if b.status == ImportBatchStatus.active]
    superseded = [b for b in batches if b.status == ImportBatchStatus.superseded]
    assert len(actives) == 1 and str(actives[0].batch_id) == res2.batch_id
    assert len(superseded) == 1
