import uuid
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.activator_mappers import to_air_tier_rate


def test_air_tier_roundtrip_lossless(tmp_path):
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "carrier": "CA", "cargo_class": "普货",
        "packing": "托", "density": "1:167",
        "effective_week_start": "2026-06-01", "effective_to": "2026-06-07",
        "remark": "周一报价", "tier_prices": {45: 17.0, 100: 14.0, 300: 12.0},
    }]
    content, _ = fill_template("air", rows)
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
