"""Air 抽取器测试：复用 AirAdapter 从「Market Price (Air)」周报抽出每日价行。

真实样本缺失时优雅 skip（不误报失败），与 step2 nitori 测试同风格。
"""
from pathlib import Path

import pytest

from app.services.step1_rates.sheet_builder import air_extractor

# backend/tests/sheet_builder/ → 上三层是仓库根
_REPO = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO / "资料/2026.05.26/Market Price updated on  May 25 (Air).xlsx"


@pytest.mark.skipif(not _SAMPLE.exists(), reason="真实 air 周报样本缺失，跳过")
def test_extract_real_weekly_yields_daily_prices():
    res = air_extractor.extract_air_rates(str(_SAMPLE), db=None)
    rows = res.get("parsed_rows", [])
    assert rows, "应从真实周报抽到 weekly 行"
    assert all(r.get("record_kind") == "air_weekly" for r in rows), "只应返回 weekly 行(滤掉 surcharge)"
    # 每行应带至少一个每日价 + 目的港 + service
    sample = rows[0]
    assert sample.get("destination_port_name")
    assert sample.get("service_desc") or sample.get("airline_code")
    assert any(sample.get(f"price_day{d}") is not None for d in range(1, 8))


@pytest.mark.skipif(not _SAMPLE.exists(), reason="真实 air 周报样本缺失，跳过")
def test_extract_keeps_only_latest_week():
    """周报常含多周 sheet；模板只针对一周，抽取应只保留最新一周、组内不重复。"""
    res = air_extractor.extract_air_rates(str(_SAMPLE), db=None)
    rows = res["parsed_rows"]
    weeks = {r.get("effective_week_start") for r in rows}
    assert len(weeks) == 1, f"应只保留最新一周，实际 {len(weeks)} 周"
    pairs = [(r.get("destination_port_name"), r.get("service_desc")) for r in rows]
    assert len(pairs) == len(set(pairs)), "同一周内 (目的港, service) 不应重复"


def test_unrecognized_air_file_returns_error(tmp_path):
    """非 Air 周报(文件名/结构不匹配) → 返回 error，不抛。"""
    bogus = tmp_path / "随便.txt"
    bogus.write_text("not an excel")
    res = air_extractor.extract_air_rates(str(bogus), db=None)
    assert res.get("error")
    assert res.get("parsed_rows") == []
