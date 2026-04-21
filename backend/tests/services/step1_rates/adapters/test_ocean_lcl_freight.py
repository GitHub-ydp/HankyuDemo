from __future__ import annotations

from decimal import Decimal

from app.services.step1_rates.adapters.ocean import OceanAdapter


def test_placeholder_mbl_cc_returns_no_warning() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("MBL CC")
    assert per_cbm is None
    assert per_ton is None
    assert extras == {"freight_parse_status": "placeholder"}
    assert warning is None


def test_placeholder_dash_returns_no_warning() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("-")
    assert per_cbm is None
    assert per_ton is None
    assert extras == {"freight_parse_status": "placeholder"}
    assert warning is None


def test_placeholder_mbl_cc_case_and_whitespace_insensitive() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("  mbl cc  ")
    assert per_cbm is None
    assert per_ton is None
    assert extras == {"freight_parse_status": "placeholder"}
    assert warning is None


def test_zero_rt_emits_zero_warning_and_clears_values() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("0/RT")
    assert per_cbm is None
    assert per_ton is None
    assert extras == {"freight_unit": "RT"}
    assert warning == "zero freight rate ignored: 0/RT"


def test_zero_cbm_emits_warning_and_clears_value() -> None:
    # 说明：'0/CBM' 在现有实现下走的是"组合分支"（因为 '/CBM' 是子串匹配而非
    # endswith），extras 为空。零值判定按任务单要求在组合分支内落实。
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("0/CBM")
    assert per_cbm is None
    assert per_ton is None
    assert warning == "zero freight rate ignored: 0/CBM"


def test_zero_ton_emits_warning_and_clears_value() -> None:
    # 说明：同上，'0/TON' 走组合分支。
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("0/TON")
    assert per_cbm is None
    assert per_ton is None
    assert warning == "zero freight rate ignored: 0/TON"


def test_zero_combined_cbm_and_ton_single_warning() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("0/CBM, 0/TON")
    assert per_cbm is None
    assert per_ton is None
    assert warning is not None
    assert "zero freight rate ignored" in warning


def test_non_zero_rt_unchanged() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("850/RT")
    assert per_cbm == Decimal("850")
    assert per_ton == Decimal("850")
    assert extras == {"freight_unit": "RT"}
    assert warning is None


def test_non_zero_combined_cbm_ton_unchanged() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("5/CBM, 10/TON")
    assert per_cbm == Decimal("5")
    assert per_ton == Decimal("10")
    assert warning is None


def test_empty_string_returns_all_none() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight("")
    assert per_cbm is None
    assert per_ton is None
    assert extras == {}
    assert warning is None


def test_none_input_returns_all_none() -> None:
    adapter = OceanAdapter()
    per_cbm, per_ton, extras, warning = adapter._parse_lcl_freight(None)
    assert per_cbm is None
    assert per_ton is None
    assert extras == {}
    assert warning is None
