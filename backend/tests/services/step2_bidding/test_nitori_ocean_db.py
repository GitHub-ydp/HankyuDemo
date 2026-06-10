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


# ---- 选价策略（邓老师口径 2026-06-10）：最新期间优先，同期多报价取最低价并标注复核提示 ----

from datetime import date


def _rate_v(carrier, c20, c40hq, vt, thc=None, doc=None, lss20=None, lss40=None,
            lead=None, src=None):
    return Step1RateRow(
        carrier_name=carrier,
        container_20gp=Decimal(c20) if c20 else None,
        container_40hq=Decimal(c40hq) if c40hq else None,
        thc=Decimal(thc) if thc else None,
        doc=Decimal(doc) if doc else None,
        lss_20=Decimal(lss20) if lss20 else None,
        lss_40=Decimal(lss40) if lss40 else None,
        valid_to=vt, transit_time_text=lead, source_file=src,
        record_kind="ocean_fcl",
    )


def test_nitori_match_prefers_latest_period():
    """3月旧批次更便宜也不能赢——先取最新期间（取错3月KMTC旧表的回归测试）。"""
    old = _rate_v("KMTC-MAR", "650", "1300", date(2026, 3, 27))
    new = _rate_v("KMTC", "800", "1600", date(2026, 5, 31))
    rep = NitoriProfile(repo=_FakeRepo([old, new])).match(_pkg("40HC"))[0]
    assert rep.cost_price == Decimal("1600")
    assert rep.carrier_text == "KMTC"


def test_nitori_match_lowest_within_same_period_with_review_note():
    """同期两家船司 → 取最低价，并在 remark 标注候选与复核提示。"""
    a = _rate_v("KMTC", "800", "1600", date(2026, 5, 31))
    b = _rate_v("EMC", "750", "1500", date(2026, 5, 31))
    rep = NitoriProfile(repo=_FakeRepo([a, b])).match(_pkg("20F"))[0]
    assert rep.cost_price == Decimal("750")
    assert rep.carrier_text == "EMC"
    assert rep.remark_text is not None
    assert "最低" in rep.remark_text
    assert "复核" in rep.remark_text
    assert "2" in rep.remark_text          # 候选条数
    assert "KMTC" in rep.remark_text       # 未选中的候选也要可见


def test_nitori_match_single_candidate_no_review_note():
    rep = NitoriProfile(repo=_FakeRepo([_rate_v("KMTC", "800", "1600", date(2026, 5, 31))])).match(_pkg("20F"))[0]
    assert rep.status == RowStatus.FILLED
    assert not (rep.remark_text and "复核" in rep.remark_text)


def test_nitori_match_skips_candidate_missing_size_price():
    """最新期间没有该箱型价 → 回退到有价的旧期间，而不是 NO_RATE。"""
    new_no40 = _rate_v("NEW", "700", None, date(2026, 5, 31))
    old = _rate_v("OLD", "650", "1300", date(2026, 3, 27))
    rep = NitoriProfile(repo=_FakeRepo([new_no40, old])).match(_pkg("40HC"))[0]
    assert rep.cost_price == Decimal("1300")
    assert rep.carrier_text == "OLD"


def test_nitori_match_carries_surcharges_by_size():
    r = _rate_v("COSCO", "300", "500", date(2026, 5, 31),
                thc="982", doc="450", lss20="200", lss40="400")
    rep40 = NitoriProfile(repo=_FakeRepo([r])).match(_pkg("40HC"))[0]
    assert rep40.thc_amount == Decimal("982")
    assert rep40.doc_amount == Decimal("450")
    assert rep40.lss_amount == Decimal("400")
    rep20 = NitoriProfile(repo=_FakeRepo([r])).match(_pkg("20F"))[0]
    assert rep20.thc_amount is None        # 库中 thc≈40 箱档值，20F 宁缺勿错
    assert rep20.doc_amount == Decimal("450")   # DOC per BL 不分箱型
    assert rep20.lss_amount == Decimal("200")


def test_nitori_no_rate_marks_pending_inquiry():
    rep = NitoriProfile(repo=_FakeRepo([])).match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.NO_RATE
    assert rep.remark_text is not None
    assert "待询价" in rep.remark_text
