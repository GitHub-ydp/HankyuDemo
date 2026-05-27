"""模板填充器测试：把 normalized rate dict 填进空白模板的正确格子，且不破坏表头。"""
from io import BytesIO

from openpyxl import load_workbook

from app.services.step1_rates.sheet_builder.template_filler import fill_template


def _reload(content: bytes):
    return load_workbook(BytesIO(content), data_only=False)


def test_fill_sea_expands_container_rows():
    rows = [
        {
            "destination": "BUSAN",
            "carrier": "SJJ",
            "freight_20": 130,
            "freight_40": 260,
            "lss_cic": "Incl.",
            "baf": 50,
            "transit": "2days",
            "remark": "直达",
        },
        {"destination": "INCHON", "carrier": "COSCO", "freight_20": 300, "freight_40": 500},
    ]
    content, filename = fill_template("sea", rows)
    ws = _reload(content)["JP N RATE FCL & LCL"]

    # 表头未被破坏
    assert ws.cell(8, 1).value == "To"
    # 第一条 BUSAN 展开 20FT / 40FT 两行，从 r9 开始
    assert ws.cell(9, 1).value == "BUSAN"
    assert ws.cell(9, 2).value == "SJJ"
    assert ws.cell(9, 3).value == "20FT"
    assert ws.cell(9, 4).value == 130
    assert ws.cell(9, 5).value == "Incl."  # LSS+CIC
    assert ws.cell(9, 6).value == 50       # BAF
    assert ws.cell(10, 3).value == "40FT/40HQ"
    assert ws.cell(10, 4).value == 260
    # 第二条 INCHON 从 r11
    assert ws.cell(11, 1).value == "INCHON"
    assert ws.cell(11, 4).value == 300
    assert ws.cell(12, 4).value == 500
    assert filename.endswith(".xlsx")


def test_fill_air_one_row_per_rate():
    rows = [
        {
            "destination": "NRT",
            "service": "普货",
            "day1": 14,
            "day2": 14,
            "day7": 15,
            "remark": "x",
        }
    ]
    content, _ = fill_template("air", rows)
    ws = _reload(content)["May 25 to May 31"]

    assert ws.cell(1, 1).value == "Destinations"  # 表头未破坏
    assert ws.cell(2, 1).value == "NRT"
    assert ws.cell(2, 2).value == "普货"
    assert ws.cell(2, 3).value == 14   # day1
    assert ws.cell(2, 9).value == 15   # day7
    assert ws.cell(2, 10).value == "x"


def test_fill_empty_rows_keeps_header_and_blank_body():
    content, _ = fill_template("sea", [])
    ws = _reload(content)["JP N RATE FCL & LCL"]
    assert ws.cell(8, 1).value == "To"            # 表头还在
    assert ws.cell(9, 1).value in (None, "")      # 数据区仍空
