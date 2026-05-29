"""会话编排测试：多源分发抽取 → 汇总 normalize → 同(港+司)多报价标 needs_review。

parser 一律 mock（不打真实 AI / 不读真实文件），只验证编排逻辑。
"""
import pytest

from app.services import rate_parser
from app.services.step1_rates.sheet_builder import air_extractor, orchestrator


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


def test_air_template_extracts_daily_prices(monkeypatch):
    """选 air 模板时 Excel 走 air 抽取，price_dayN 归一为 dayN，service 用 service_desc。"""
    fake = {
        "parsed_rows": [
            {
                "destination_port_name": "NRT",
                "service_desc": "CK 2 days service",
                "airline_code": "CK",
                "price_day1": 14, "price_day2": 14, "price_day3": 15,
                "price_day4": 14, "price_day5": 14, "price_day6": 13, "price_day7": 14,
            }
        ],
        "warnings": [],
    }
    monkeypatch.setattr(air_extractor, "extract_air_rates", lambda p, db: fake)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "Market Price (Air).xlsx", "/tmp/air.xlsx", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "excel"
    assert fr.row_count == 1
    row = s.rows[0]
    assert row["destination"] == "NRT"
    assert row["service"] == "CK 2 days service"
    assert row["origin"] == "PVG"  # 未提供起运港时默认 PVG(上海)
    assert row["day1"] == 14
    assert row["day3"] == 15
    assert row["day7"] == 14


def test_air_same_dest_different_service_not_marked_review(monkeypatch):
    """air 同目的港不同 service 是不同行，不应被当成重复多报价。"""
    fake = {
        "parsed_rows": [
            {"destination_port_name": "NRT", "service_desc": "CK 2 days", "airline_code": "CK", "price_day1": 14},
            {"destination_port_name": "NRT", "service_desc": "HO 2 days", "airline_code": "HO", "price_day1": 15},
        ],
        "warnings": [],
    }
    monkeypatch.setattr(air_extractor, "extract_air_rates", lambda p, db: fake)

    s = orchestrator.create_session("air")
    orchestrator.add_file(s.session_id, "air.xlsx", "/tmp/air.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(not r["needs_review"] for r in s.rows), "不同 service 不算重复多报价"


def test_air_weight_break_same_dest_multi_flight_marked_review(monkeypatch):
    """档位源(唯凯)：同目的港多航班(multi_flight_pick) → 全标 needs_review 供人工选一条；单航班不标。
    tier_prices 透传(不再走 day1-7)。"""
    tiers = {"tier_prices": {100: 13, 500: 13, 1000: 13}}
    fake = {
        "parsed_rows": [
            {"destination_port_name": "NRT", "service_desc": "KZ226", "multi_flight_pick": True, **tiers},
            {"destination_port_name": "NRT", "service_desc": "KZ228", "multi_flight_pick": True, **tiers},
            {"destination_port_name": "KIX", "service_desc": "CK247", "multi_flight_pick": True, **tiers},
        ],
        "warnings": [],
    }
    monkeypatch.setattr(air_extractor, "extract_air_rates", lambda p, db: fake)

    s = orchestrator.create_session("air")
    orchestrator.add_file(s.session_id, "weightbreak.xls", "/tmp/wb.xls", db=None)

    nrt = [r for r in s.rows if r["destination"] == "NRT"]
    kix = [r for r in s.rows if r["destination"] == "KIX"]
    assert len(nrt) == 2 and all(r["needs_review"] for r in nrt), "NRT 两航班应标 needs_review"
    assert not kix[0]["needs_review"], "KIX 单航班不必标"
    assert nrt[0]["tier_prices"] == {100: 13.0, 500: 13.0, 1000: 13.0}, "档位应透传"


def test_air_tier_row_normalizes_with_tier_prices(monkeypatch):
    """档位源(EES/唯凯)行带 tier_prices → 归一透传 tier_prices(值转 float)、不发 day1-7、
    备注取 remarks、起运港默认 PVG、multi_flight_pick → needs_review_by_destination。"""
    from decimal import Decimal

    fake = {
        "parsed_rows": [
            {
                "destination_port_name": "KIX",
                "service_desc": "CK/MU",
                "tier_prices": {45: Decimal("17"), 100: 14},  # Decimal/int 混入应都转 float
                "remarks": "含油备注",
                "multi_flight_pick": True,
            }
        ],
        "warnings": [],
    }
    monkeypatch.setattr(air_extractor, "extract_air_rates", lambda p, db: fake)

    s = orchestrator.create_session("air")
    orchestrator.add_file(s.session_id, "EES.xlsx", "/tmp/ees.xlsx", db=None)

    row = s.rows[0]
    assert row["origin"] == "PVG"
    assert row["destination"] == "KIX"
    assert row["service"] == "CK/MU"
    assert row["tier_prices"] == {45: 17.0, 100: 14.0}
    assert all(isinstance(v, float) for v in row["tier_prices"].values()), "值应转 float 便于 JSON/写表"
    assert all(f"day{d}" not in row for d in range(1, 8)), "档位行不应带 day1-7"
    assert row["remark"] == "含油备注"
    assert row["needs_review_by_destination"] is True


def test_add_pdf_file_routes_to_pdf_parser(tmp_path, monkeypatch):
    import app.services.rate_parser_pdf as rpp
    from app.services.step1_rates.sheet_builder import orchestrator

    # 假 PDF（内容无所谓，分流被 monkeypatch）
    fake = tmp_path / "ONE_contract.pdf"
    fake.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        rpp, "detect_and_parse_pdf",
        lambda path, db: {"parsed_rows": [{
            "carrier_name": "ONE", "origin_port_name": "DALIAN",
            "destination_port_name": "HILO", "container_20gp": 5240.0,
            "container_40gp": 7100.0, "container_40hq": 7200.0,
        }], "carrier_code": "ONE", "warnings": []},
    )

    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "ONE_contract.pdf", str(fake), db=None)

    assert res.status == "parsed"
    assert res.row_count == 1
    rows = orchestrator.get_session(sess.session_id).rows
    assert rows[0]["destination"] == "HILO"            # _normalize_sea 已映射
    assert rows[0]["container_20gp"] == 5240.0


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


from decimal import Decimal
from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea


def test_normalize_sea_preserves_container_breakdown_and_origin():
    row = {
        "destination_port_name": "HONG KONG",
        "carrier_name": "KMTC",
        "container_20gp": Decimal("250"),
        "container_40gp": Decimal("500"),
        "container_40hq": Decimal("520"),
        "transit_days": 3,
        "remarks": "直达",
    }
    out = _normalize_sea(row, "FALLBACK")
    assert out["origin"] == "SHANGHAI"
    assert out["destination"] == "HONG KONG"
    assert out["carrier"] == "KMTC"
    assert out["container_20gp"] == Decimal("250")
    assert out["container_40gp"] == Decimal("500")
    assert out["container_40hq"] == Decimal("520")
    assert out["transit_days"] == 3
    assert out["freight_20"] == Decimal("250")
    assert out["freight_40"] == Decimal("500")


def test_normalize_sea_passes_through_pdf_fields():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea
    raw = {
        "carrier_name": "ONE", "destination_port_name": "HILO",
        "container_20gp": 5240.0, "container_40gp": 7100.0, "container_40hq": 7200.0,
        "container_45": 6075.0, "valid_from": "2026-02-03", "valid_to": "2026-02-28",
        "rate_level": "R5", "service_code": "EC3", "via": "BUSAN", "is_direct": False,
        "commodity": "TPE1-FAK", "remark": "inclusive of AGS",
    }
    out = _normalize_sea(raw, carrier_fallback="")
    assert out["container_45"] == 6075.0
    assert out["valid_from"] == "2026-02-03"
    assert out["valid_to"] == "2026-02-28"
    assert out["rate_level"] == "R5"
    assert out["service_code"] == "EC3"
    assert out["via"] == "BUSAN"
    assert out["is_direct"] is False
    assert out["commodity"] == "TPE1-FAK"
    assert out["remark"] == "inclusive of AGS"


def test_unsupported_docx_still_skipped():
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "report.docx", "/tmp/report.docx", db=None)
    assert fr.status == "skipped"
    assert fr.source_type == "unsupported"
    assert s.rows == []
