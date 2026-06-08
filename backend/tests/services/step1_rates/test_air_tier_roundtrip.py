import uuid
from decimal import Decimal
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.activator_mappers import to_air_tier_rate


def test_air_tier_roundtrip_lossless(tmp_path):
    # 往返无损是「动态多档表」分支的能力（多档→导出→重新解析回多档）。
    # 默认出表已改为严格按模板(只取 +100KG，多档会丢)，故这里显式关 strict
    # 验证保留的动态档表分支仍无损。
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "carrier": "CA", "cargo_class": "普货",
        "packing": "托", "density": "1:167",
        "effective_week_start": "2026-06-01", "effective_to": "2026-06-07",
        "remark": "周一报价", "tier_prices": {45: 17.0, 100: 14.0, 300: 12.0},
    }]
    content, _ = fill_template("air", rows, strict_air_template=False)
    path = tmp_path / "air_tier_rate_sheet_filled.xlsx"
    path.write_bytes(content)

    batch = AirTierAdapter().parse(path, db=None)
    assert len(batch.records) == 1
    rate = to_air_tier_rate(batch.records[0], uuid.uuid4())

    assert rate.origin == "PVG"
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"          # 关键：日本段币种不丢
    assert str(rate.effective_from) == "2026-06-01"
    assert rate.carrier == "CA"
    assert rate.cargo_class == "普货"
    assert rate.tier_prices == {45: 17.0, 100: 14.0, 300: 12.0}


def test_strict_air_template_roundtrip_via_air_adapter(tmp_path):
    """默认严格按模板导出(无起运港/币种列) → 回流由 AirAdapter 接管(不再是 AirWeeklyAdapter)：
    起运港默认补 PVG、币种默认 CNY、目的港/+100KG 价/周期无损。
    (代价：strict 模式下币种不入表，非 CNY 线回流会落 CNY；需无损币种走 strict=False 档位表。)"""
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY",  # 严格按模板不入表 → 回流默认 CNY
        "tier_prices": {45: 17.0, 100: 14.0, 300: 12.0},
        "effective_week_start": "2026-06-01",
    }]
    content, _ = fill_template("air", rows)  # 默认 strict → 周表(只 +100KG)
    path = tmp_path / "air_rate_sheet_filled.xlsx"
    path.write_bytes(content)

    batch = AirAdapter().parse(path, db=None)
    weekly = [r for r in batch.records if r.record_kind == "air_weekly"]
    assert len(weekly) == 1
    rec = weekly[0]
    assert rec.origin_port_name == "PVG"        # AirAdapter 默认补 PVG
    assert rec.destination_port_name == "NRT"
    assert rec.currency == "CNY"                 # 按模板无币种列 → 默认 CNY
    assert rec.price_day1 == Decimal("14")       # +100KG 档铺满 day1-7
    assert rec.price_day7 == Decimal("14")
    assert str(batch.effective_from) == "2026-06-01"
