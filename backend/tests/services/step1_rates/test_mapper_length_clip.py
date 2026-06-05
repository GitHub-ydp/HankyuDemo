import uuid
from app.models import AirTierRate, AirFreightRate
from app.services.step1_rates.activator_mappers import to_air_tier_rate, to_air_freight_rate
from app.services.step1_rates.entities import ParsedRateRecord


def test_air_tier_clips_overlong():
    rec = ParsedRateRecord(
        record_kind="air_tier",
        origin_port_name="PVG-VERY-LONG-ORIGIN-CODE-OVER20",
        destination_port_name="NRT",
        currency="USD/CNY/EUR",
        extras={"tier_prices": {45: 10.0}, "cargo_class": "普货-9610-9710-超长货类描述",
                "packing": "托散混装超长包装描述", "density": "1:167超长泡比描述", "carrier": "C" * 200},
    )
    r = to_air_tier_rate(rec, uuid.uuid4())
    assert len(r.origin) <= 20
    assert len(r.currency) <= 5
    assert len(r.cargo_class) <= 20
    assert len(r.packing) <= 20
    assert len(r.density) <= 20
    assert len(r.carrier) <= 100
    assert r.origin  # 非空保持


def test_air_freight_clips_overlong():
    rec = ParsedRateRecord(
        record_kind="air_weekly",
        origin_port_name="PVG-VERY-LONG-ORIGIN-OVER-20-CHARS",
        destination_port_name="NRT",
        airline_code="A" * 50,
        service_desc="S" * 200,
        currency="USD/CNY/EUR",
    )
    r = to_air_freight_rate(rec, uuid.uuid4())
    assert len(r.origin) <= 20
    assert len(r.currency) <= 5
    assert len(r.airline_code) <= 20
    assert len(r.service_desc) <= 100
    assert r.origin


def test_clip_preserves_normal_values():
    rec = ParsedRateRecord(
        record_kind="air_tier", origin_port_name="PVG", destination_port_name="NRT",
        currency="JPY", extras={"tier_prices": {45: 10.0}, "cargo_class": "普货", "carrier": "CA"},
    )
    r = to_air_tier_rate(rec, uuid.uuid4())
    assert r.origin == "PVG" and r.currency == "JPY" and r.cargo_class == "普货" and r.carrier == "CA"
