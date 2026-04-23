"""Customer A PKG 解析验收用例（T-B4 范围：V-B01..V-B09）。

黄金样本：资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.step2_bidding.customer_profiles.customer_a import CustomerAProfile
from app.services.step2_bidding.entities import CostType, ParsedPkg
from app.services.step2_bidding.protocols import CustomerProfile


GOLDEN_SAMPLE = (
    Path(__file__).resolve().parents[4]
    / "资料"
    / "2026.04.02"
    / "Customer A (Air)"
    / "Customer A (Air)"
    / "2-①.xlsx"
)


@pytest.fixture(scope="module")
def parsed() -> ParsedPkg:
    if not GOLDEN_SAMPLE.exists():
        pytest.skip(f"Customer A 黄金样本不可用：{GOLDEN_SAMPLE}")
    profile = CustomerAProfile()
    return profile.parse(GOLDEN_SAMPLE, bid_id="bid_test", period="2026-01")


def test_v_b01_detect_returns_true():
    if not GOLDEN_SAMPLE.exists():
        pytest.skip("sample missing")
    assert CustomerAProfile().detect(GOLDEN_SAMPLE) is True


def test_customer_a_profile_implements_customer_profile_protocol():
    profile = CustomerAProfile()
    assert isinstance(profile, CustomerProfile)
    assert profile.customer_code == "customer_a"


def test_v_b02_five_sections(parsed: ParsedPkg):
    assert len(parsed.sections) == 5


def test_v_b03_section_codes_order(parsed: ParsedPkg):
    codes = [s.section_code for s in parsed.sections]
    assert codes == ["NRT", "PVG", "AMS", "TPE", "ICN"]


def test_v_b04_section_currencies(parsed: ParsedPkg):
    currencies = [s.currency for s in parsed.sections]
    assert currencies == ["JPY", "CNY", "EUR", "USD", "USD"]


def test_v_b05_pvg_section_has_seven_rows(parsed: ParsedPkg):
    pvg_rows = [r for r in parsed.rows if r.section_code == "PVG"]
    assert len(pvg_rows) == 7
    assert [r.row_idx for r in pvg_rows] == [13, 14, 15, 16, 17, 18, 19]


def test_v_b06_local_delivery_rows(parsed: ParsedPkg):
    by_idx = {r.row_idx: r for r in parsed.rows}
    assert by_idx[14].cost_type == CostType.LOCAL_DELIVERY
    assert by_idx[17].cost_type == CostType.LOCAL_DELIVERY


def test_v_b07_example_rows_flagged_and_pvg_has_no_example(parsed: ParsedPkg):
    by_idx = {r.row_idx: r for r in parsed.rows}
    assert by_idx[4].is_example is True
    assert by_idx[5].is_example is True
    pvg_rows = [r for r in parsed.rows if r.section_code == "PVG"]
    assert all(not r.is_example for r in pvg_rows)


def test_v_b08_icn_section_level_remark_contains_r38(parsed: ParsedPkg):
    icn = next(s for s in parsed.sections if s.section_code == "ICN")
    assert len(icn.section_level_remarks) == 1
    assert "韓国→日本→ブラジル" in icn.section_level_remarks[0]


def test_v_b09_destination_codes_r13_and_r19(parsed: ParsedPkg):
    by_idx = {r.row_idx: r for r in parsed.rows}
    assert by_idx[13].destination_code == "ATL"
    assert by_idx[19].destination_code == "TPE"


def test_period_passed_through_preserved_over_b1(parsed: ParsedPkg):
    """传入 period='2026-01' 时不应被 B1 ('1月') 覆盖。"""
    assert parsed.period == "2026-01"


def test_period_falls_back_to_b1_when_empty():
    if not GOLDEN_SAMPLE.exists():
        pytest.skip("sample missing")
    parsed = CustomerAProfile().parse(GOLDEN_SAMPLE, bid_id="bid_x", period="")
    assert parsed.period == "1月"


def test_existing_price_parsed_as_decimal(parsed: ParsedPkg):
    by_idx = {r.row_idx: r for r in parsed.rows}
    # R5 模板填了 750（既存报价）
    assert by_idx[5].existing_price == Decimal("750")
    # PVG 段首行 R13 为 0（未填）
    assert by_idx[13].existing_price == Decimal("0")

