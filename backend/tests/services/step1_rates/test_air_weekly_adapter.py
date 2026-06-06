import uuid
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air_weekly import AirWeeklyAdapter
from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.activator_mappers import to_air_freight_rate
from app.services.step1_rates.entities import Step1FileType


def _make(tmp_path):
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "effective_week_start": "2026-05-25",
        "day1": 10, "day2": 11, "day3": 12, "day4": 13,
        "day5": 14, "day6": 15, "day7": 16, "remark": "wk",
    }]
    content, _ = fill_template("air", rows)  # 无 tier_prices → 周表分支
    path = tmp_path / "air_weekly_rate_sheet_filled.xlsx"
    path.write_bytes(content)
    return path


def test_detect_weekly_layout(tmp_path):
    path = _make(tmp_path)
    assert AirWeeklyAdapter().detect(path) is True


def test_air_weekly_priority_before_air(tmp_path):
    assert AirWeeklyAdapter().priority < AirAdapter().priority


def test_parse_and_roundtrip(tmp_path):
    path = _make(tmp_path)
    batch = AirWeeklyAdapter().parse(path, db=None)
    assert batch.file_type is Step1FileType.air
    recs = [r for r in batch.records if r.record_kind == "air_weekly"]
    assert len(recs) == 1
    r = recs[0]
    assert r.origin_port_name == "PVG"
    assert r.destination_port_name == "NRT"
    assert r.service_desc == "CA"
    assert r.currency == "JPY"
    assert str(r.effective_week_start) == "2026-05-25"
    rate = to_air_freight_rate(r, uuid.uuid4())
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"
    assert str(rate.price_day1) == "10"
    assert str(rate.price_day7) == "16"
