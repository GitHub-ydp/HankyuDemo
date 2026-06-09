"""按客户模板回填海运运价（OTHER PORTS 页）核心测试。

纯函数 refill_into_template：给模板 bytes + 当前会话 rows，返回填好的 xlsx bytes。
夹具 = 客户真实「空白 着地あり」模板（保留目的港名、价格留空）。
"""
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.step1_rates.sheet_builder.template_refill import (
    RefillError,
    refill_into_template,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sea_other_ports_template.xlsx"
SHEET = "FCL N RATE OF OTHER PORTS"


def _tpl_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _refill(rows):
    content = refill_into_template(_tpl_bytes(), rows)
    assert content[:2] == b"PK"  # xlsx = zip
    return load_workbook(BytesIO(content), data_only=False)


def test_basic_fill_carrier_and_container_rows():
    rows = [
        {"destination": "HONG KONG", "carrier": "SJJ",
         "container_20gp": 230, "container_40gp": 460, "container_40hq": 460,
         "via": "DIRECT", "transit": "4days"},
        {"destination": "HONG KONG", "carrier": "ASL",
         "container_20gp": 240, "container_40hq": 480},
        {"destination": "BUSAN", "carrier": "EAS",
         "container_20gp": 160, "container_40hq": 320},
    ]
    ws = _refill(rows)[SHEET]
    # HONG KONG（模板首港）从数据起始行 r9 开始，2 船司 × 2 箱型 = 4 行
    assert ws.cell(9, 1).value == "HONG KONG"
    assert ws.cell(9, 2).value == "SJJ"
    assert ws.cell(9, 3).value == "20FT"
    assert ws.cell(9, 4).value == 230
    assert ws.cell(10, 3).value == "40FT/40HQ"
    assert ws.cell(10, 4).value == 460
    assert ws.cell(11, 2).value == "ASL"
    assert ws.cell(11, 4).value == 240
    assert ws.cell(12, 4).value == 480
    # A 列港名竖向合并整块 r9:r12
    assert any(str(m) == "A9:A12" for m in ws.merged_cells.ranges)
    # 模板原序：HK 后接 KEELUNG/KAOHSIUNG/TAICHUNG（均无数据，各就地占 1 行）
    assert ws.cell(13, 1).value == "KEELUNG"
    assert ws.cell(14, 1).value == "KAOHSIUNG"
    assert ws.cell(15, 1).value == "TAICHUNG"
    # BUSAN（模板第 5 个港）就地落在 r16，1 船司 × 2 行
    assert ws.cell(16, 1).value == "BUSAN"
    assert ws.cell(16, 2).value == "EAS"
    assert ws.cell(17, 3).value == "40FT/40HQ"
    assert ws.cell(17, 4).value == 320


# BUSAN 是模板第 5 个港；HK/KEELUNG/KAOHSIUNG/TAICHUNG 无数据各占 1 行(r9-r12)
# → BUSAN 数据按模板原序就地落在 r13(20FT)/r14(40)。
_BUSAN_R20 = 13
_BUSAN_R40 = 14


def test_40_row_takes_40hq_when_differ():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40gp": 300, "container_40hq": 320}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(_BUSAN_R20, 4).value == 160      # 20FT
    assert ws.cell(_BUSAN_R40, 4).value == 320      # 40 行取 40HQ（≠40GP 时）


def test_40_row_falls_back_to_40gp_when_no_40hq():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40gp": 300}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(_BUSAN_R40, 4).value == 300      # 40HQ 空 → 回退 40GP


def test_surcharges_map_to_lss_baf_cic_caf():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40hq": 320,
             "surcharges": [
                 {"code": "LSS", "included": True},
                 {"code": "BAF", "payment": "collect"},
                 {"code": "CIC", "amount_20": 50, "amount_40": 100},
                 {"code": "CAF", "note": "subject to dest"},
             ]}]
    ws = _refill(rows)[SHEET]
    # 20FT 行：E=LSS F=BAF G=CIC H=CAF
    assert ws.cell(_BUSAN_R20, 5).value == "Incl."
    assert ws.cell(_BUSAN_R20, 6).value == "Collect"
    assert ws.cell(_BUSAN_R20, 7).value == 50
    assert ws.cell(_BUSAN_R20, 8).value == "subject to dest"
    # 40 行 CIC 取 amount_40
    assert ws.cell(_BUSAN_R40, 7).value == 100


def test_surcharge_falls_back_to_flat_lss_cic():
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160,
             "lss_cic": "Incl.", "baf": 30}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(_BUSAN_R20, 5).value == "Incl."   # 无 surcharges → 用扁平 lss_cic 落 LSS 列
    assert ws.cell(_BUSAN_R20, 6).value == 30        # 扁平 baf 落 BAF 列


def test_empty_port_keeps_name_one_blank_row():
    # SINGAPORE 在模板里，rows 没有它 → 留港名 + 1 空行
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    ws = _refill(rows)[SHEET]
    col_a = [ws.cell(r, 1).value for r in range(9, 40)]
    assert "SINGAPORE" in col_a
    # SINGAPORE 那一行价格列(D)为空
    sg_row = 9 + col_a.index("SINGAPORE")
    assert ws.cell(sg_row, 4).value in (None, "")


def test_ports_keep_template_order():
    # 只给模板第 5 个港(BUSAN)数据：空港也须留在模板原位，港序不得被打乱。
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    ws = _refill(rows)[SHEET]
    # 模板首港 HONG KONG（空港）仍在 r9，而非被有数据的 BUSAN 顶到后面
    assert ws.cell(9, 1).value == "HONG KONG"
    assert ws.cell(10, 1).value == "KEELUNG"
    assert ws.cell(11, 1).value == "KAOHSIUNG"
    assert ws.cell(12, 1).value == "TAICHUNG"
    # BUSAN 块就地落在它的模板原序位置(r13)，不被移到数据起始行 r9
    assert ws.cell(13, 1).value == "BUSAN"
    assert ws.cell(13, 4).value == 160
    # 全表 A 列港名出现顺序 == 模板原序前缀
    col_a = [ws.cell(r, 1).value for r in range(9, ws.max_row + 1) if ws.cell(r, 1).value]
    assert col_a[:5] == ["HONG KONG", "KEELUNG", "KAOHSIUNG", "TAICHUNG", "BUSAN"]


def test_multiname_port_row_order_is_deterministic():
    # 多名模板港(TOKYO/YOKOHAMA 形态)下，多船司行的输出顺序须随输入序稳定，
    # 不受 set 迭代 / PYTHONHASHSEED 影响。直接对底层匹配函数断言。
    from app.services.step1_rates.sheet_builder.template_refill import _match_rows
    by_port = {"MADRAS": [{"carrier": "A"}], "CHENNAI": [{"carrier": "B"}]}
    out = [r["carrier"] for r in _match_rows("MADRAS / CHENNAI", by_port)]
    # whole(MADRASCHENNAI) 无命中 → 按 part 顺序 MADRAS 先于 CHENNAI
    assert out == ["A", "B"]


def test_surcharges_non_list_or_non_dict_no_crash():
    # surcharges 是字符串 / list 内含 None 等非 dict 时不得崩溃（接线前防御缺口）。
    rows = [
        {"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160,
         "surcharges": "Incl."},
        {"destination": "INCHON", "carrier": "X", "container_20gp": 170,
         "surcharges": [None, "junk", {"code": "LSS", "included": True}]},
    ]
    ws = _refill(rows)[SHEET]
    col_a = [ws.cell(r, 1).value for r in range(9, ws.max_row + 1)]
    assert "BUSAN" in col_a and "INCHON" in col_a
    # 含 None/字符串杂项但仍有合法 LSS 项 → 该项正常生效
    inchon_r = 9 + col_a.index("INCHON")
    assert ws.cell(inchon_r, 5).value == "Incl."


def test_alias_and_multiname_matching():
    rows = [
        {"destination": "PUSAN", "carrier": "EAS", "container_20gp": 160},       # PUSAN↔BUSAN
        {"destination": "CHENNAI", "carrier": "X", "container_20gp": 700},       # ↔ MADRAS / CHENNAI
        {"destination": "LOS ANGELES", "carrier": "Y", "container_20gp": 800},   # ↔ LONG BEACH⏎LOS ANGELES
        {"destination": "CHICAGO", "carrier": "Z", "container_20gp": 900},       # ↔ CHICAGO (via LAX)
    ]
    ws = _refill(rows)[SHEET]
    cells = {(ws.cell(r, 1).value, ws.cell(r, 2).value): ws.cell(r, 4).value
             for r in range(9, ws.max_row + 1)}
    assert ("BUSAN", "EAS") in cells and cells[("BUSAN", "EAS")] == 160
    assert ("MADRAS / CHENNAI", "X") in cells and cells[("MADRAS / CHENNAI", "X")] == 700
    assert ("LONG BEACH\nLOS ANGELES", "Y") in cells and cells[("LONG BEACH\nLOS ANGELES", "Y")] == 800
    assert ("CHICAGO (via LAX)", "Z") in cells and cells[("CHICAGO (via LAX)", "Z")] == 900


def test_unlisted_port_is_filtered_out():
    rows = [{"destination": "DALIAN", "carrier": "EAS", "container_20gp": 999},
            {"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    ws = _refill(rows)[SHEET]
    col_a = [ws.cell(r, 1).value for r in range(9, ws.max_row + 1)]
    assert "DALIAN" not in col_a       # 模板没列 → 不输出


def test_fidelity_other_sheets_and_header_untouched():
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    wb = _refill(rows)
    assert wb.sheetnames == [
        "JP N RATE FCL & LCL", "FCL N RATE OF OTHER PORTS", "LCL N RATE",
    ]
    # 表头 8 行不变
    assert wb[SHEET].cell(8, 1).value == "TO"
    # JP 页原样保留（她模板里 JP 页留了 TOKYO/OSAKA）
    assert wb["JP N RATE FCL & LCL"].cell(9, 1).value == "TOKYO\nYOKOHAMA"


def test_empty_rows_produce_blank_ports_no_crash():
    wb = _refill([])
    ws = wb[SHEET]
    # 所有港留名、价格空
    assert ws.cell(9, 1).value == "HONG KONG"
    assert ws.cell(9, 4).value in (None, "")


def test_missing_sheet_raises_refill_error():
    from openpyxl import Workbook
    buf = BytesIO()
    Workbook().save(buf)            # 全新空 workbook，无 OTHER PORTS 页
    with pytest.raises(RefillError):
        refill_into_template(buf.getvalue(), [])
