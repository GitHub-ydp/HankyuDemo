"""海运闭环：commit_ocean_rows → query_ocean_fcl → NitoriProfile.match。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.port import Port
from app.services.step1_rates.sheet_builder import db_writer
from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
from app.services.step2_bidding.entities import (
    CostType, ParsedPkg, PkgRow, PkgSection, RowStatus,
)
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


def _pkg(size):
    row = PkgRow(
        row_idx=9, section_index=0, section_code="GLOBAL",
        origin_code="SHANGHAI", origin_text_raw="SHANGHAI",
        destination_text_raw="HONG KONG", destination_code="HONG KONG",
        cost_type=CostType.UNKNOWN, currency="USD",
        volume_desc=None, existing_price=None, existing_lead_time=None,
        existing_carrier=None, existing_remark=None, is_example=False,
        client_constraint_text=None,
        extras={"size": size, "pod_raw": "HONG KONG", "is_china": True},
    )
    section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
    return ParsedPkg(bid_id="b", customer_code="nitori", period="x", sheet_name="s",
                     source_file="f", sections=[section], rows=[row], warnings=[])


def test_ocean_chain_commit_query_nitori(db_session):
    # 1. 入库（模拟做表归一行）
    res = db_writer.commit_ocean_rows([{
        "origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC",
        "container_20gp": Decimal("250"), "container_40hq": Decimal("500"), "transit_days": 3,
    }], db_session)
    assert res.fcl_rows == 1

    # 2. 查 + Nitori 取价
    profile = NitoriProfile(repo=Step1RateRepository(db_session))
    rep = profile.match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.FILLED
    assert rep.cost_price == Decimal("500")
    assert rep.sell_price == Decimal("575")
    assert rep.carrier_text == "KOREA MARINE TRANSPORT"
