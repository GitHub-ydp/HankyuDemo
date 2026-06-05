import uuid
from app.models import AirTierRate
from app.services.step1_rates.activator_mappers import to_air_tier_rate
from app.services.step1_rates.entities import ParsedRateRecord


def _rec() -> ParsedRateRecord:
    return ParsedRateRecord(
        record_kind="air_tier",
        origin_port_name="PVG",
        destination_port_name="NRT",
        service_desc="CA",
        currency="JPY",
        extras={
            "tier_prices": {"45": 17.0, "100": "14"},
            "cargo_class": "普货",
            "packing": "托",
            "density": "1:167",
            "carrier": "CA",
            "row_index": 2,
        },
    )


def test_to_air_tier_rate_maps_fields():
    rate = to_air_tier_rate(_rec(), uuid.uuid4())
    assert isinstance(rate, AirTierRate)
    assert rate.origin == "PVG"
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"
    assert rate.cargo_class == "普货"
    assert rate.carrier == "CA"
    # 键归 int、值归 float
    assert rate.tier_prices == {45: 17.0, 100: 14.0}


def test_to_air_tier_rate_defaults():
    # 注意：ParsedRateRecord 继承 Step1RateRow.currency 默认值 "USD"(非 None)，省略 currency
    # 得到的是 "USD" 而非空。真实回流中由 AirTierAdapter 对空币种格填 "CNY"；mapper 的
    # `or "CNY"` 是兜底层，故这里显式传 currency=None 来验证兜底。
    rec = ParsedRateRecord(
        record_kind="air_tier", currency=None, extras={"tier_prices": {"45": 10.0}}
    )
    rate = to_air_tier_rate(rec, uuid.uuid4())
    assert rate.origin == "PVG"        # 缺省起运港
    assert rate.destination == ""      # 缺省目的地
    assert rate.currency == "CNY"      # currency=None → 兜底 CNY
