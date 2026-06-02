"""做表海运行 → 入库 FreightRate(commit_ocean_rows)。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus, SourceType
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


def test_commit_ocean_writes_pdf_fields():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base, Carrier, CarrierType, Port
    from app.models.freight_rate import FreightRate
    from app.services.step1_rates.sheet_builder.db_writer import commit_ocean_rows

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Carrier(code="ONE", name_en="Ocean Network Express",
                   carrier_type=CarrierType.shipping_line, country="SG"))
    db.add(Port(un_locode="CNDLC", name_en="Dalian", name_cn="大连", country="CN", region="East Asia"))
    db.add(Port(un_locode="USHIL", name_en="Hilo", name_cn="希洛", country="US", region="North America"))
    db.commit()

    rows = [{
        "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
        "container_20gp": 5240, "container_40gp": 7100, "container_40hq": 7200,
        "container_45": 6075, "valid_from": "2026-02-03", "valid_to": "2026-02-28",
        "rate_level": "R5", "service_code": "EC3", "via": "BUSAN", "is_direct": False,
        "commodity": "TPE1-FAK", "remark": "inclusive of AGS",
        "source_type": "pdf",
    }]
    result = commit_ocean_rows(rows, db)
    assert result.fcl_rows == 1

    fr = db.query(FreightRate).one()
    assert fr.container_45 == 6075
    assert str(fr.valid_from) == "2026-02-03"
    assert str(fr.valid_to) == "2026-02-28"
    assert fr.rate_level == "R5"
    assert fr.service_code == "EC3"
    assert fr.via == "BUSAN"
    assert fr.is_direct is False
    assert fr.rmks == "TPE1-FAK"
    assert fr.remarks == "inclusive of AGS"
    assert fr.source_type == SourceType.pdf, "PDF 来源行应落 SourceType.pdf 而非 excel"
    db.close()


def test_commit_ocean_no_source_type_defaults_excel(db_session):
    """行里不带 source_type 时(kmtc/Excel 路径)，source_type 应落 SourceType.excel。"""
    res = db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("250"), Decimal("500"))], db_session)
    assert res.fcl_rows == 1
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.source_type == SourceType.excel


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


def test_commit_ocean_uses_row_currency(db_session):
    row = _row("HONG KONG", Decimal("250"), Decimal("500"))
    row["currency"] = "CNY"
    db_writer.commit_ocean_rows([row], db_session)
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.currency == "CNY"


def test_commit_ocean_rows_maps_ocean_image_source_type(db_session):
    """ocean_image source_type 应映射回 SourceType.wechat_image（SP3 前的存储行为）。"""
    row = _row("HONG KONG", Decimal("300"), Decimal("600"))
    row["source_type"] = "ocean_image"
    res = db_writer.commit_ocean_rows([row], db_session)
    assert res.fcl_rows == 1
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.source_type == SourceType.wechat_image


def test_commit_ocean_rows_maps_ocean_text_source_type(db_session):
    """ocean_text source_type 应映射回 SourceType.email_text。"""
    row = _row("HONG KONG", Decimal("310"), Decimal("620"))
    row["source_type"] = "ocean_text"
    res = db_writer.commit_ocean_rows([row], db_session)
    assert res.fcl_rows == 1
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.source_type == SourceType.email_text
