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
            "origin": "PVG",
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

    # 新增起运港列在最左：A 起运港 / B 目的港 / C 服务 / D-J 每日价 / K 备注
    assert ws.cell(1, 1).value == "Origin (POL)"  # 表头未破坏
    assert ws.cell(1, 2).value == "Destinations"
    assert ws.cell(2, 1).value == "PVG"
    assert ws.cell(2, 2).value == "NRT"
    assert ws.cell(2, 3).value == "普货"
    assert ws.cell(2, 4).value == 14   # day1
    assert ws.cell(2, 10).value == 15  # day7
    assert ws.cell(2, 11).value == "x"


def test_fill_empty_rows_keeps_header_and_blank_body():
    content, _ = fill_template("sea", [])
    ws = _reload(content)["JP N RATE FCL & LCL"]
    assert ws.cell(8, 1).value == "To"            # 表头还在
    assert ws.cell(9, 1).value in (None, "")      # 数据区仍空


def test_fill_air_rewrites_week_headers_from_data():
    """行带 effective_week_start 时，按该周改写 day1-7 日期表头 + sheet 名。"""
    rows = [
        {"destination": "NRT", "service": "CK", "day1": 14, "day7": 14,
         "effective_week_start": "2026-06-01"},
    ]
    content, _ = fill_template("air", rows)
    wb = _reload(content)

    assert wb.sheetnames == ["Jun 1 to Jun 7"], "sheet 名应按周改写"
    ws = wb["Jun 1 to Jun 7"]
    assert str(ws.cell(1, 4).value).startswith("2026/6/1"), "day1 表头应为该周起始日(POL 后移至 D 列)"
    assert str(ws.cell(1, 10).value).startswith("2026/6/7"), "day7 表头应为该周第7日"
    assert ws.cell(2, 2).value == "NRT"  # 数据照填(目的港后移至 B 列)


def test_fill_air_without_week_keeps_template():
    """无 effective_week_start（如重量档报价）→ 保留模板原日期/名，不乱改。"""
    rows = [{"destination": "NRT", "service": "CK", "day1": 14}]
    content, _ = fill_template("air", rows)
    wb = _reload(content)

    assert wb.sheetnames == ["May 25 to May 31"], "无周信息应保留模板原样"
    assert str(wb["May 25 to May 31"].cell(1, 4).value).startswith("2026/5/25")  # day1 表头 D 列


def test_build_air_tier_sheet_dynamic_columns():
    """档位行(带 tier_prices) → 程序生成档位表(不套 air_blank)：
    起运港|目的港|服务|动态 KG 列(全表并集升序)|备注；稀疏档某行缺的留空。"""
    rows = [
        {"origin": "PVG", "destination": "KIX", "service": "CK/MU",
         "tier_prices": {45: 17.0, 100: 14.0}, "remark": "含油"},
        {"origin": "PVG", "destination": "BKK", "service": "平散货",
         "tier_prices": {100: 16.0, 300: 16.0, 500: 16.0, 1000: 16.0}, "remark": None},
    ]
    content, filename = fill_template("air", rows)
    wb = _reload(content)
    ws = wb[wb.sheetnames[0]]

    # 表头：固定列 + 全表档位并集(45/100/300/500/1000)升序 + 元数据列 + 备注
    header = [ws.cell(1, c).value for c in range(1, 17)]
    assert header == [
        "Origin (POL)", "Destination", "Service",
        "45KG", "100KG", "300KG", "500KG", "1000KG",
        "Currency", "Effective From", "Effective To",
        "Carrier", "Cargo Class", "Packing", "Density", "Remark",
    ]
    # KIX 行(r2)：45=17 / 100=14，其余档留空
    assert ws.cell(2, 1).value == "PVG"
    assert ws.cell(2, 2).value == "KIX"
    assert ws.cell(2, 3).value == "CK/MU"
    assert ws.cell(2, 4).value == 17.0           # 45KG
    assert ws.cell(2, 5).value == 14.0           # 100KG
    assert ws.cell(2, 6).value in (None, "")     # 300KG 留空
    assert ws.cell(2, 16).value == "含油"          # 备注(移到元数据列之后)
    # BKK 行(r3)：100/300/500/1000=16，45 留空
    assert ws.cell(3, 4).value in (None, "")     # 45KG 留空
    assert ws.cell(3, 5).value == 16.0
    assert ws.cell(3, 8).value == 16.0           # 1000KG
    assert filename.endswith(".xlsx")


def test_build_air_tier_sheet_names_from_report_date():
    """报价日(effective_week_start)进 sheet 名；无则用通用名。"""
    rows = [{"origin": "PVG", "destination": "KIX", "service": "CK",
             "tier_prices": {100: 14.0}, "effective_week_start": "2026-05-21"}]
    content, _ = fill_template("air", rows)
    wb = _reload(content)
    assert "2026-05-21" in wb.sheetnames[0]


def test_build_air_tier_sheet_accepts_string_tier_keys():
    """下载 POST 经 JSON 往返后档位键会变字符串('45') → 仍能正确成列取值。"""
    rows = [{"origin": "PVG", "destination": "KIX", "service": "CK",
             "tier_prices": {"45": 17.0, "100": 14.0}, "remark": None}]
    content, _ = fill_template("air", rows)
    ws = _reload(content)[_reload(content).sheetnames[0]]
    header = [ws.cell(1, c).value for c in range(1, 6)]
    assert header[:3] == ["Origin (POL)", "Destination", "Service"]
    assert "45KG" in header and "100KG" in header
    assert ws.cell(2, 4).value == 17.0
