from app.services.step1_rates.service import build_default_registry
from app.services.step1_rates.entities import Step1FileType
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air import AirAdapter


def test_ocean_hint_routes_to_ocean_not_kmtc(tmp_path):
    rows = [{"destination": "USLAX", "carrier": "ONE",
             "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850}]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_sea_filled.xlsx"
    path.write_bytes(content)
    reg = build_default_registry()
    adapter = reg.resolve(path, file_type_hint=Step1FileType.ocean)
    assert adapter.key == "ocean"   # 不再被 kmtc 抢


def test_air_tier_priority_unique_below_nvo(tmp_path):
    from app.services.step1_rates.adapters.air_tier import AirTierAdapter
    from app.services.step1_rates.adapters.nvo_fak import NvoFakAdapter
    assert AirTierAdapter().priority < NvoFakAdapter().priority


def test_air_weekly_sets_batch_effective(tmp_path):
    # 严格按模板后做表周表不带起运港列 → 回流走 AirAdapter（非 AirWeeklyAdapter）；
    # 批次生效期仍由周表 sheet 名 + 日期表头解析得出，无损。
    rows = [{"origin": "PVG", "destination": "NRT", "service": "CA",
             "currency": "JPY", "effective_week_start": "2026-05-25",
             "day1": 10, "day7": 16}]
    content, _ = fill_template("air", rows)
    path = tmp_path / "air_market_price_filled.xlsx"
    path.write_bytes(content)
    batch = AirAdapter().parse(path, db=None)
    assert str(batch.effective_from) == "2026-05-25"
    assert str(batch.effective_to) == "2026-05-31"
