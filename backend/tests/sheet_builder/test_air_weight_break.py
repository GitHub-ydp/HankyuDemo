"""重量档 Air 报价解析测试（阪急唯凯式）。真实样本缺失时优雅 skip。"""
from pathlib import Path

import pytest

from app.services.step1_rates.sheet_builder import air_weight_break

_REPO = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO / "资料/2026.05.27/air/阪急唯凯报价05-26.xls"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="阪急唯凯样本缺失，跳过")
def test_parse_clean_route_sheets_with_100kg():
    res = air_weight_break.parse_weight_break(str(_SAMPLE))
    rows = res["parsed_rows"]
    assert rows, "应从规整航线表抽到行"

    # 每行：+100KG 价填满 day1-7，且带目的港 + multi_flight_pick 标记
    sample = rows[0]
    assert sample["destination_port_name"]
    assert sample["multi_flight_pick"] is True
    assert all(sample[f"price_day{d}"] == sample["price_day1"] for d in range(1, 8))

    # 按勘探确认的具体值核对（+100KG 列）
    def price_of(dest, service_contains):
        for r in rows:
            if r["destination_port_name"] == dest and (r.get("service_desc") or "").upper().startswith(service_contains):
                return r["price_day1"]
        return None

    assert price_of("KIX", "CK247") == 13, "日本 KIX/CK247 +100KG 应为 13"
    assert price_of("NRT", "KZ226") == 13, "日本 NRT/KZ226 +100KG 应为 13"
    assert price_of("BOM", "CX") == 28, "印度 BOM/CX +100KG 应为 28"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="阪急唯凯样本缺失，跳过")
def test_coverage_reported_in_warnings():
    res = air_weight_break.parse_weight_break(str(_SAMPLE))
    joined = " ".join(res["warnings"])
    assert "日本" in joined and "印度" in joined, "覆盖的航线表应在 warnings 报告"
    assert "未覆盖" in joined, "未覆盖的航司表应如实报告"
