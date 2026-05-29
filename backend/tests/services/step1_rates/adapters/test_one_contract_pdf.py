"""ONE 服务合约 PDF 适配器单元测试。"""
import app.services.step1_rates.adapters.one_contract_pdf as ocp
from app.services.step1_rates.adapters.one_contract_pdf import (
    _clean_port_name,
    parse_rate_blocks,
)


def test_clean_port_name_strips_state_suffix():
    assert _clean_port_name("HONOLULU, HI") == "HONOLULU"


def test_clean_port_name_strips_country_and_parens():
    assert _clean_port_name("DALIAN, LIAONING, CHINA(CY)") == "DALIAN"
    assert _clean_port_name("TAIPEI, TAIWAN(CY)") == "TAIPEI"


def test_clean_port_name_plain_passthrough():
    assert _clean_port_name("BUSAN") == "BUSAN"
    assert _clean_port_name("") == ""
    assert _clean_port_name(None) == ""


def _line(*pairs):
    """构造一行：pairs 为 (text, x0) 序列。"""
    return [{"text": t, "x0": float(x)} for t, x in pairs]


def _clean_block_lines():
    # 列坐标：Destination=10, Cntry=200, Term=350, Type=400, Cur=450,
    #         20'=500, 40'=560, 40HC=620, 45'=680, Note=740
    return [
        _line(("6.", 5), ("CONTRACT", 30), ("RATES", 120), ("OR", 200), ("RATE", 240), ("SCHEDULE(S)", 300)),
        _line(("211)", 5), ("COMMODITY", 40), (":", 150), ("TPE1-FAK", 170)),
        _line(("ORIGIN", 5), (":", 150), ("DALIAN,", 170), ("LIAONING,", 230), ("CHINA(CY)", 300)),
        _line(("Destination", 10), ("Cntry", 200), ("Term", 350), ("Type", 400),
              ("Cur", 450), ("20'", 500), ("40'", 560), ("40HC", 620), ("45'", 680), ("Note", 740)),
        _line(("HILO,", 10), ("HI", 60), ("US", 200), ("CY", 350), ("Dry", 400),
              ("USD", 450), ("5240", 500), ("7100", 560), ("7200", 620)),
        _line(("HONOLULU,", 10), ("HI", 90), ("US", 200), ("CY", 350), ("Dry", 400),
              ("USD", 450), ("3840", 500), ("4800", 560), ("4800", 620), ("6075", 680)),
        _line(("<", 5), ("NOTE", 20), ("FOR", 60), ("COMMODITY", 100), (">", 200)),
        _line(("Rates", 10), ("are", 50), ("valid", 80), ("from", 120), ("20260203", 160), ("to", 230), ("20260228", 260)),
        _line(("Rates", 10), ("are", 50), ("inclusive", 80), ("of", 140), ("the", 160),
              ("ADEN", 190), ("GULF", 230), ("SURCHARGE(AGS)", 280)),
    ]


def test_parse_clean_block_yields_rows_with_prices():
    rows = parse_rate_blocks(_clean_block_lines())
    assert len(rows) == 2

    r0 = rows[0]
    assert r0["carrier_name"] == "ONE"
    assert r0["origin_port_name"] == "DALIAN"            # 已清洗
    assert r0["destination_port_name"] == "HILO"         # "HILO, HI" → "HILO"
    assert r0["container_20gp"] == 5240.0
    assert r0["container_40gp"] == 7100.0
    assert r0["container_40hq"] == 7200.0
    assert r0["container_45"] is None
    assert r0["currency"] == "USD"
    assert r0["needs_review"] is False
    # NOTE 回填
    assert r0["valid_from"] == "2026-02-03"
    assert r0["valid_to"] == "2026-02-28"
    assert "inclusive of" in (r0["remark"] or "")
    assert r0["commodity"] == "TPE1-FAK"

    assert rows[1]["destination_port_name"] == "HONOLULU"
    assert rows[1]["container_45"] == 6075.0


def _coded_block_lines():
    return [
        _line(("6.", 5), ("CONTRACT", 30), ("RATES", 120), ("OR", 200), ("RATE", 240), ("SCHEDULE(S)", 300)),
        _line(("212)", 5), ("COMMODITY", 40), (":", 150), ("TPE1-FAK", 170)),
        _line(("ORIGIN", 5), (":", 150), ("TAIPEI,", 170), ("TAIWAN(CY)", 240)),
        _line(("Destination", 10), ("Cntry", 200), ("Term", 350), ("Type", 400),
              ("Cur", 450), ("20'", 500), ("40'", 560), ("40HC", 620), ("45'", 680), ("Note", 740)),
        # 冷藏 RF + 编码价 R2/2400(落在 40' 列)
        _line(("USLAX", 10), ("USLGB", 70), ("US", 200), ("CY", 350), ("RF", 400),
              ("USD", 450), ("R2/2400", 560)),
    ]


def test_parse_coded_row_flagged_needs_review():
    rows = parse_rate_blocks(_coded_block_lines())
    assert len(rows) == 1
    r = rows[0]
    assert r["needs_review"] is True
    assert r["rate_level"] == "R2/2400"      # 编码原文保留
    assert r["container_40gp"] is None        # 非数字 → 不当价
    assert r["origin_port_name"] == "TAIPEI"
    assert r["valid_from"] is None
    assert r["valid_to"] is None


def test_parse_one_contract_pdf_wraps_blocks(monkeypatch):
    monkeypatch.setattr(ocp, "_extract_word_lines", lambda path: _clean_block_lines())
    out = ocp.parse_one_contract_pdf("/fake/path.pdf", db=None)
    assert out["carrier_code"] == "ONE"
    assert len(out["parsed_rows"]) == 2
    assert out["parsed_rows"][0]["destination_port_name"] == "HILO"
    assert isinstance(out.get("warnings"), list)


def _via_block_lines():
    """构造带 Destination Via 列（两个 Cntry）的 fixture 块。
    列坐标参照真实 PDF：
      Destination@63.9, Cntry@147.5, Destination@200.2, Via@242.6,
      Cntry@287.9, Term@315.1, Type@340.7, Cur@365.3,
      20'@397.4, 40'@436.8, 40HC@471.1, 45'@515.4, Note@568.3
    数据行：CHICAGO, IL US LOS ANGELES,CA US CY Dry USD 1500 2500 2600
      destination=CHICAGO, via=LOS ANGELES (after clean), 20gp=1500, 40gp=2500, 40hq=2600
    """
    return [
        _line(("6.", 5), ("CONTRACT", 30), ("RATES", 120), ("OR", 200),
              ("RATE", 240), ("SCHEDULE(S)", 300)),
        _line(("221)", 5), ("COMMODITY", 40), (":", 150), ("FAK-TEST", 170)),
        _line(("ORIGIN", 5), (":", 150), ("SHANGHAI,", 170), ("CHINA(CY)", 240)),
        _line(("Destination", 63.9), ("Cntry", 147.5),
              ("Destination", 200.2), ("Via", 242.6),
              ("Cntry", 287.9), ("Term", 315.1), ("Type", 340.7),
              ("Cur", 365.3), ("20'", 397.4), ("40'", 436.8),
              ("40HC", 471.1), ("45'", 515.4), ("Note", 568.3)),
        # 数据行：CHICAGO, IL US LOS ANGELES, CA US CY Dry USD 1500 2500 2600
        _line(("CHICAGO,", 27.6), ("IL", 80.0), ("US", 151.4),
              ("LOS", 173.7), ("ANGELES,", 195.0), ("CA", 250.0),
              ("US", 291.8), ("CY", 318.5), ("Dry", 343.2),
              ("USD", 363.4), ("1500", 393.8), ("2500", 433.1), ("2600", 472.4)),
        _line(("<", 5), ("NOTE", 20), ("FOR", 60), ("COMMODITY", 100), (">", 200)),
        _line(("Rates", 10), ("are", 50), ("valid", 80), ("from", 120),
              ("20260301", 160), ("to", 230), ("20260331", 260)),
    ]


def test_parse_via_block_extracts_via():
    """有 Destination Via 列（两个 Cntry）时，via 应被正确解析，destination 不含 via 词。"""
    rows = parse_rate_blocks(_via_block_lines())
    assert len(rows) == 1
    r = rows[0]
    assert r["destination_port_name"] == "CHICAGO"
    assert r["via"] is not None, "via 应被解析出来"
    assert "LOS ANGELES" in r["via"] or "LOS" in r["via"], f"via 应包含 LOS ANGELES 信息，实际: {r['via']}"
    assert r["container_20gp"] == 1500.0
    assert r["container_40gp"] == 2500.0
    assert r["container_40hq"] == 2600.0


def test_parse_no_via_column_backward_compat():
    """无 Destination Via 列（只有一个 Cntry，旧格式）时，via 应仍为 None，老测试路径不破坏。"""
    rows = parse_rate_blocks(_clean_block_lines())
    # _clean_block_lines 只有一个 Cntry，via 应仍为 None
    for r in rows:
        assert r["via"] is None, f"单 Cntry 格式 via 应为 None，实际: {r['via']}"
    # 基本解析不受影响
    assert len(rows) == 2
    assert rows[0]["destination_port_name"] == "HILO"


import os
import pytest

_SAMPLE = "/Users/zhangdongxu/Desktop/project/阪急阪神/资料/2026.05.27/Sea Net Rete/LAX0751N25v93 (2).pdf"


@pytest.mark.integration
@pytest.mark.skipif(not os.path.exists(_SAMPLE), reason="真实 ONE 合约样例不在本机")
def test_real_one_contract_parses_rows():
    out = ocp.parse_one_contract_pdf(_SAMPLE, db=None)
    assert out["carrier_code"] == "ONE"
    assert len(out["parsed_rows"]) > 0          # 至少抽到运价行
    # 干净数字行应有价（不全是 needs_review）
    priced = [r for r in out["parsed_rows"]
              if r["container_20gp"] is not None or r["container_40gp"] is not None]
    assert len(priced) > 0
    # I-1：via 列应被解析，非空行数应占大多数
    via_filled = [r for r in out["parsed_rows"] if r.get("via")]
    assert len(via_filled) > len(out["parsed_rows"]) * 0.5, (
        f"via 填充率应 >50%，实际 {len(via_filled)}/{len(out['parsed_rows'])}"
    )
