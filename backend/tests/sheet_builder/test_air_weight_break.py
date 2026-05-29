"""重量档 Air 报价解析测试（阪急唯凯式）—— 自适应多档抽取。真实样本缺失时优雅 skip。

与 EES 同构(福山 2026-05-28 定稿)：从每个块的表头自适应读出所有数字档位列(唯凯表头档位是
**数字** 45/100/300/500/1000，澳洲还有 3000)，每行存稀疏 `tier_prices={45:15,100:13,…}`，
取代单一 +100KG×7天。断言里的档位价均来自对真实文件的逐行勘探。
"""
from pathlib import Path

import pytest

from app.services.step1_rates.sheet_builder import air_weight_break

_REPO = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO / "资料/2026.05.27/air/阪急唯凯报价05-26.xls"


def _dicts(rows, dest):
    return [r["tier_prices"] for r in rows if r["destination_port_name"] == dest]


@pytest.mark.skipif(not _SAMPLE.exists(), reason="阪急唯凯样本缺失，跳过")
def test_parse_yields_multi_tier_rows():
    rows = air_weight_break.parse_weight_break(str(_SAMPLE))["parsed_rows"]
    assert rows, "应从规整航线表抽到行"
    for r in rows:
        assert r["destination_port_name"]
        assert r["multi_flight_pick"] is True
        assert r["source_file"]
        tiers = r["tier_prices"]
        assert isinstance(tiers, dict) and tiers
        for kg, price in tiers.items():
            assert isinstance(kg, int) and kg > 0
            assert isinstance(price, (int, float)) and price > 0
        assert "price_day1" not in r, "+100KG×7天写法应已被档位 dict 取代"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="阪急唯凯样本缺失，跳过")
def test_known_routes_tier_dicts():
    rows = air_weight_break.parse_weight_break(str(_SAMPLE))["parsed_rows"]
    # 日本 KIX/CK247：45=15 / 100=13 / 500=13 / 1000=12.5
    assert {45: 15, 100: 13, 500: 13, 1000: 12.5} in _dicts(rows, "KIX")
    # 日本 NRT/KZ226：45 列为「/」留空，100/500/1000 全 13
    assert {100: 13, 500: 13, 1000: 13} in _dicts(rows, "NRT")
    # 印度 BOM/CX/CI：45 空，100/500/1000 全 28
    assert {100: 28, 500: 28, 1000: 28} in _dicts(rows, "BOM")
    # 新曼 SIN/CK287：含 300 档，45=24 其余 22 → 证明自适应读到 300
    assert {45: 24, 100: 22, 300: 22, 500: 22, 1000: 22} in _dicts(rows, "SIN")


def test_tier_kg_recognizes_numeric_headers_only():
    """档位识别：纯正整数表头(数字/字符串/浮点)认作档位；文本表头一律 None。"""
    f = air_weight_break._tier_kg
    assert f(100.0) == 100
    assert f("45") == 45
    assert f("1000.0") == 1000
    assert f(3000.0) == 3000
    assert f("DEST") is None
    assert f("Frequency") is None
    assert f("2.6") is None  # Frequency 值不是整数档位
    assert f(None) is None


@pytest.mark.skipif(not _SAMPLE.exists(), reason="阪急唯凯样本缺失，跳过")
def test_coverage_reported_in_warnings():
    res = air_weight_break.parse_weight_break(str(_SAMPLE))
    joined = " ".join(res["warnings"])
    assert "日本" in joined and "印度" in joined, "覆盖的航线表应在 warnings 报告"
    assert "未覆盖" in joined, "未覆盖的航司表应如实报告"
