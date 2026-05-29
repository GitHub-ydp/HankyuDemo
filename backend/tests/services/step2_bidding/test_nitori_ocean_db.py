"""NitoriProfile.match 优先查 DB(repo.query_ocean_fcl)，按箱型取价。"""
from __future__ import annotations

from decimal import Decimal

from app.services.step1_rates.entities import Step1RateRow
from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
from app.services.step2_bidding.entities import (
    CostType, ParsedPkg, PkgRow, PkgSection, RowStatus,
)


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows

    def query_ocean_fcl(self, *, origin, destination, effective_on=None, currency=None):
        return self._rows


def _pkg(size):
    row = PkgRow(
        row_idx=9, section_index=0, section_code="GLOBAL",
        origin_code="SHANGHAI", origin_text_raw="SHANGHAI",
        destination_text_raw="HONG KONG", destination_code="HONGKONG",
        cost_type=CostType.UNKNOWN, currency="USD",
        volume_desc=None, existing_price=None, existing_lead_time=None,
        existing_carrier=None, existing_remark=None, is_example=False,
        client_constraint_text=None,
        extras={"size": size, "pod_raw": "HONG KONG", "is_china": True},
    )
    section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
    return ParsedPkg(
        bid_id="b", customer_code="nitori", period="x", sheet_name="s",
        source_file="f", sections=[section], rows=[row], warnings=[],
    )


def _rate():
    return Step1RateRow(
        carrier_name="KMTC", container_20gp=Decimal("250"),
        container_40hq=Decimal("500"), transit_days=3, record_kind="ocean_fcl",
    )


def test_nitori_match_uses_db_40hc():
    rep = NitoriProfile(repo=_FakeRepo([_rate()])).match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.FILLED
    assert rep.cost_price == Decimal("500")
    assert rep.sell_price == Decimal("575")
    assert rep.carrier_text == "KMTC"


def test_nitori_match_uses_db_20f():
    rep = NitoriProfile(repo=_FakeRepo([_rate()])).match(_pkg("20F"))[0]
    assert rep.cost_price == Decimal("250")


def test_nitori_match_no_rate_when_db_empty_and_no_costbook():
    rep = NitoriProfile(repo=_FakeRepo([])).match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.NO_RATE
