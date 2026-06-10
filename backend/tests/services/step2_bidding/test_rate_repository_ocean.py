"""query_ocean_fcl：按 origin/dest 查 active FreightRate → Step1RateRow。"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.models.port import Port
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="CNSHA", name_en="SHANGHAI"),
        Port(un_locode="HKHKG", name_en="HONG KONG"),
        Carrier(code="KMTC", name_en="KOREA MARINE TRANSPORT"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_rate(s, status=ImportBatchStatus.active, c20=Decimal("250"), c40hq=Decimal("500")):
    sha = s.query(Port).filter_by(un_locode="CNSHA").one()
    hkg = s.query(Port).filter_by(un_locode="HKHKG").one()
    km = s.query(Carrier).filter_by(code="KMTC").one()
    bid = uuid.uuid4()
    s.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.ocean, status=status))
    s.add(FreightRate(
        carrier_id=km.id, origin_port_id=sha.id, destination_port_id=hkg.id,
        container_20gp=c20, container_40hq=c40hq, transit_days=3,
        currency="USD", status=RateStatus.active, batch_id=bid,
    ))
    s.commit()


def test_query_ocean_fcl_returns_active_rate(db_session):
    _seed_rate(db_session)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="HONG KONG")
    assert len(rows) == 1
    r = rows[0]
    assert r.container_20gp == Decimal("250")
    assert r.container_40hq == Decimal("500")
    assert r.carrier_name == "KOREA MARINE TRANSPORT"
    assert r.transit_days == 3
    assert r.record_kind == "ocean_fcl"


def test_query_ocean_fcl_excludes_superseded(db_session):
    _seed_rate(db_session, status=ImportBatchStatus.superseded)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="HONG KONG")
    assert rows == []


def test_query_ocean_fcl_unresolved_port_returns_empty(db_session):
    _seed_rate(db_session)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="NOWHERE")
    assert rows == []


def test_query_ocean_fcl_resolves_tanjung_priok_alias(db_session):
    """招标书写 TANJUNG PRIOK，字典/价源是 Jakarta → 别名解析后能查到。"""
    db_session.add(Port(un_locode="IDJKT", name_en="Jakarta"))
    db_session.commit()
    sha = db_session.query(Port).filter_by(un_locode="CNSHA").one()
    jkt = db_session.query(Port).filter_by(un_locode="IDJKT").one()
    km = db_session.query(Carrier).filter_by(code="KMTC").one()
    bid = uuid.uuid4()
    db_session.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.ocean,
                               status=ImportBatchStatus.active))
    db_session.add(FreightRate(
        carrier_id=km.id, origin_port_id=sha.id, destination_port_id=jkt.id,
        container_20gp=Decimal("810"), container_40hq=Decimal("1420"),
        currency="USD", status=RateStatus.active, batch_id=bid,
    ))
    db_session.commit()
    rows = Step1RateRepository(db_session).query_ocean_fcl(
        origin="SHANGHAI", destination="TANJUNG PRIOK")
    assert len(rows) == 1
    assert rows[0].container_20gp == Decimal("810")


def test_query_ocean_fcl_carries_surcharges_and_validity(db_session):
    """THC/DOC/LSS/有效期要透传到 Step1RateRow，供投标回写与选价策略用。"""
    from datetime import date
    sha = db_session.query(Port).filter_by(un_locode="CNSHA").one()
    hkg = db_session.query(Port).filter_by(un_locode="HKHKG").one()
    km = db_session.query(Carrier).filter_by(code="KMTC").one()
    bid = uuid.uuid4()
    db_session.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.ocean,
                               status=ImportBatchStatus.active))
    db_session.add(FreightRate(
        carrier_id=km.id, origin_port_id=sha.id, destination_port_id=hkg.id,
        container_20gp=Decimal("300"), container_40hq=Decimal("500"),
        thc=Decimal("982"), doc=Decimal("450"),
        lss_20=Decimal("200"), lss_40=Decimal("400"),
        valid_from=date(2026, 5, 15), valid_to=date(2026, 5, 31),
        currency="USD", status=RateStatus.active, batch_id=bid,
    ))
    db_session.commit()
    r = Step1RateRepository(db_session).query_ocean_fcl(
        origin="SHANGHAI", destination="HONG KONG")[0]
    assert r.thc == Decimal("982")
    assert r.doc == Decimal("450")
    assert r.lss_20 == Decimal("200")
    assert r.lss_40 == Decimal("400")
    assert r.valid_from == date(2026, 5, 15)
    assert r.valid_to == date(2026, 5, 31)
    assert r.source_file is None or isinstance(r.source_file, str)
