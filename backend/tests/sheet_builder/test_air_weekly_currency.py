from io import BytesIO
from openpyxl import load_workbook
from app.services.step1_rates.sheet_builder.template_filler import fill_template


def test_air_weekly_sheet_has_currency_column():
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "day1": 10, "day2": 11,
        "effective_week_start": "2026-05-25",
    }]
    content, _ = fill_template("air", rows)  # 无 tier_prices → 走周表分支
    ws = load_workbook(BytesIO(content)).active
    header = [c.value for c in ws[1]]
    assert "Currency" in header
    cur_col = header.index("Currency") + 1
    assert ws.cell(2, cur_col).value == "JPY"
