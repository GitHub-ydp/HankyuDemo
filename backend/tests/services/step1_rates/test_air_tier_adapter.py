from pathlib import Path
from openpyxl import Workbook
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.entities import Step1FileType


def _make_tier_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Air Rates 2026-06-01"
    header = ["Origin (POL)", "Destination", "Service", "45KG", "100KG",
              "Currency", "Effective From", "Effective To",
              "Carrier", "Cargo Class", "Packing", "Density", "Remark"]
    for c, label in enumerate(header, start=1):
        ws.cell(1, c).value = label
    ws.append(["PVG", "NRT", "CA", 17, 14, "JPY",
               "2026-06-01", "2026-06-07", "CA", "普货", "托", "1:167", "周一报价"])
    path = tmp_path / "air_tier_rate_sheet_filled.xlsx"
    wb.save(path)
    return path


def _make_ocean_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "JP N RATE FCL & LCL"
    path = tmp_path / "ocean_xx.xlsx"
    wb.save(path)
    return path


def test_detect_by_content(tmp_path):
    a = AirTierAdapter()
    assert a.detect(_make_tier_xlsx(tmp_path)) is True
    assert a.detect(_make_ocean_xlsx(tmp_path)) is False


def test_detect_by_hint(tmp_path):
    a = AirTierAdapter()
    assert a.detect(_make_ocean_xlsx(tmp_path), file_type_hint=Step1FileType.air_tier) is True


def test_parse_tier_rows(tmp_path):
    batch = AirTierAdapter().parse(_make_tier_xlsx(tmp_path), db=None)
    assert batch.file_type is Step1FileType.air_tier
    assert len(batch.records) == 1
    r = batch.records[0]
    assert r.record_kind == "air_tier"
    assert r.origin_port_name == "PVG"
    assert r.destination_port_name == "NRT"
    assert r.service_desc == "CA"
    assert r.currency == "JPY"
    assert str(r.valid_from) == "2026-06-01"
    assert r.extras["tier_prices"] == {45: 17.0, 100: 14.0}
    assert r.extras["cargo_class"] == "普货"
    assert r.extras["carrier"] == "CA"


def test_parse_skips_non_numeric_tier(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Air Rates"
    for c, label in enumerate(["Origin (POL)", "Destination", "Service", "45KG", "100KG"], start=1):
        ws.cell(1, c).value = label
    ws.append(["PVG", "NRT", "CA", "ASK", 14])   # 45KG 非数字 → 跳过, 不炸
    path = tmp_path / "air_tier_dirty.xlsx"
    wb.save(path)
    batch = AirTierAdapter().parse(path, db=None)
    assert len(batch.records) == 1
    assert batch.records[0].extras["tier_prices"] == {100: 14.0}


def test_parse_slash_date(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for c, label in enumerate(["Origin (POL)", "Destination", "45KG", "Effective From"], start=1):
        ws.cell(1, c).value = label
    ws.append(["PVG", "NRT", 17, "2026/06/01"])
    path = tmp_path / "air_tier_slash.xlsx"
    wb.save(path)
    rec = AirTierAdapter().parse(path, db=None).records[0]
    assert str(rec.valid_from) == "2026-06-01"


def test_parse_no_match_warns(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "JP N RATE FCL & LCL"   # 非档位表
    path = tmp_path / "not_tier.xlsx"
    wb.save(path)
    batch = AirTierAdapter().parse(path, db=None)
    assert batch.records == []
    assert batch.warnings  # 落空有提示
