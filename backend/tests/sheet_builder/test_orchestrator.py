"""会话编排测试：多源分发抽取 → 汇总 normalize → 同(港+司)多报价标 needs_review。

parser 一律 mock（不打真实 AI / 不读真实文件），只验证编排逻辑。
"""
import pytest

from app.services import rate_parser
from app.services.step1_rates.sheet_builder import orchestrator


def test_create_session_validates_type():
    s = orchestrator.create_session("sea")
    assert s.template_type == "sea"
    assert s.session_id
    with pytest.raises(ValueError):
        orchestrator.create_session("rail")


def test_add_excel_file_normalizes_sea_rows(monkeypatch):
    fake = {
        "parsed_rows": [
            {
                "destination_port_name": "BUSAN/釜山",
                "carrier_name": None,  # row 无船司 → 用顶层 carrier_code
                "container_20gp": 130,
                "container_40gp": 260,
                "lss_20": "Incl.",
                "baf_20": 50,
                "transit_days": 2,
                "remarks": "直达",
            }
        ],
        "carrier_code": "KMTC",
        "warnings": [],
    }
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "kmtc.xlsx", "/tmp/kmtc.xlsx", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "excel"
    assert fr.row_count == 1
    row = s.rows[0]
    assert row["destination"] == "BUSAN/釜山"
    assert row["carrier"] == "KMTC"        # fallback 到顶层 carrier_code
    assert row["freight_20"] == 130
    assert row["freight_40"] == 260
    assert row["baf"] == 50
    assert row["needs_review"] is False


def test_multi_quote_same_lane_marks_needs_review(monkeypatch):
    f1 = {"parsed_rows": [{"destination_port_name": "BUSAN", "carrier_name": "SJJ", "container_20gp": 130}], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [{"destination_port_name": "BUSAN", "carrier_name": "SJJ", "container_20gp": 140}], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(r["needs_review"] for r in s.rows), "同目的港+船司的多条应全部标 needs_review"


def test_unsupported_extension_skipped():
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "LAX.pdf", "/tmp/LAX.pdf", db=None)
    assert fr.status == "skipped"
    assert fr.source_type == "unsupported"
    assert s.rows == []


def test_legacy_xls_routed_to_excel_parser(monkeypatch):
    """老 .xls(Excel 97-2003) 应走 excel 解析器，不再被当作 unsupported 跳过。"""
    fake = {
        "parsed_rows": [
            {"destination_port_name": "BUSAN/釜山", "carrier_name": "KMTC", "container_20gp": 130}
        ],
        "carrier_code": "KMTC",
        "warnings": [],
    }
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "old_rates.xls", "/tmp/old_rates.xls", db=None)

    assert fr.source_type == "excel", "应路由到 excel 解析器，而非 unsupported"
    assert fr.status == "parsed"
    assert fr.row_count == 1


def test_unrecognized_format_surfaces_reason(monkeypatch):
    """parser 跑通但识别不了格式(返回 error)时，应把原因透传给用户，而非静默显示 0 行。"""
    monkeypatch.setattr(
        rate_parser,
        "detect_and_parse",
        lambda p, db: {
            "error": "无法识别的 Excel 格式，支持 KMTC 运价表和 NVO FAK 格式",
            "parsed_rows": [],
        },
    )

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "air_quote.xls", "/tmp/air_quote.xls", db=None)

    assert fr.status == "skipped", "识别不了应标 skipped，而非 parsed"
    assert "无法识别" in fr.message, "应把 parser 的原因透传到 message"
    assert fr.row_count == 0
    assert s.rows == []


def test_parser_error_marked_not_crash(monkeypatch):
    def boom(p, db):
        raise RuntimeError("解析炸了")
    monkeypatch.setattr(rate_parser, "detect_and_parse", boom)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "bad.xlsx", "/tmp/bad.xlsx", db=None)
    assert fr.status == "error"
    assert "解析炸了" in fr.message
    assert s.rows == []
