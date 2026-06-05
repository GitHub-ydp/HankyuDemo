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
