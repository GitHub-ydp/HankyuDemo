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


def test_ocean_image_ai_failure_marked_skipped_not_parsed(monkeypatch):
    """海运图片 AI 识别失败(0 行)应标 skipped 并透传原因，而非绿色 parsed(已抽取)。"""
    from app.services import ai_client

    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "rate.png", "/tmp/rate.png", db=None)

    assert fr.status == "skipped", "AI 识别失败应标 skipped，而非 parsed(绿色成功)"
    assert "失败" in fr.message
    assert fr.row_count == 0
    assert s.rows == []


def test_air_image_ai_failure_marked_skipped_not_parsed(monkeypatch):
    """空运图片 AI 识别失败(0 行)同样应标 skipped，而非绿色 parsed。"""
    from app.services import ai_client

    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "rate.png", "/tmp/rate.png", db=None)

    assert fr.status == "skipped", "AI 识别失败应标 skipped，而非 parsed(绿色成功)"
    assert "失败" in fr.message
    assert fr.row_count == 0
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


def test_sea_same_dest_carrier_different_via_not_marked_review(monkeypatch):
    """M-1：同 destination+carrier 但 via 不同的两行不应被标 needs_review。"""
    f1 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "container_20gp": 1500, "via": "USLAX"}
    ], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "container_20gp": 1600, "via": "USLB"}
    ], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(not r["needs_review"] for r in s.rows), "via 不同的行不应被标 needs_review"


def test_sea_same_dest_carrier_same_via_marked_review(monkeypatch):
    """M-1：同 destination+carrier+via 的两行应仍被标 needs_review。"""
    f1 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "container_20gp": 1500, "via": "USLAX"}
    ], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "container_20gp": 1600, "via": "USLAX"}
    ], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(r["needs_review"] for r in s.rows), "via 相同时仍应标 needs_review"


def test_sea_kmtc_no_via_review_behavior_unchanged(monkeypatch):
    """M-1 兼容性：kmtc/Excel 行无 via → key 等价于原来 (destination, carrier)，行为不变。"""
    f1 = {"parsed_rows": [
        {"destination_port_name": "BUSAN", "carrier_name": "KMTC", "container_20gp": 130}
    ], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [
        {"destination_port_name": "BUSAN", "carrier_name": "KMTC", "container_20gp": 140}
    ], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert all(r["needs_review"] for r in s.rows), "kmtc 无 via 时同目的港+船司两行仍标 needs_review"


def test_unsupported_docx_still_skipped():
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "report.docx", "/tmp/report.docx", db=None)
    assert fr.status == "skipped"
    assert fr.source_type == "unsupported"
    assert s.rows == []


def test_sea_same_dest_carrier_different_origin_not_marked_review(monkeypatch):
    """M-1 关键：同 dest+carrier 但 origin 不同的两行（PDF 合约 148 起运港场景）不应标 needs_review。"""
    f1 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "origin_port_name": "DALIAN", "container_20gp": 1500}
    ], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [
        {"destination_port_name": "CHICAGO", "carrier_name": "ONE",
         "origin_port_name": "SHANGHAI", "container_20gp": 1600}
    ], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(not r["needs_review"] for r in s.rows), "origin 不同的行不应被标 needs_review"


def test_sea_same_full_key_still_marked_review(monkeypatch):
    """M-1：origin+dest+carrier+via+commodity+valid_from 全同的两行仍应标 needs_review。"""
    row_data = {
        "destination_port_name": "CHICAGO", "carrier_name": "ONE",
        "origin_port_name": "DALIAN", "container_20gp": 1500,
        "via": "USLAX", "commodity": "FAK", "valid_from": "2026-02-03",
    }
    f1 = {"parsed_rows": [dict(row_data)], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [dict(row_data)], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(r["needs_review"] for r in s.rows), "6 维全同时仍应标 needs_review"


def test_sea_same_dest_carrier_different_valid_from_not_marked_review(monkeypatch):
    """M-1：同 dest+carrier+origin 但 valid_from 不同（不同有效期）不应标 needs_review。"""
    f1 = {"parsed_rows": [
        {"destination_port_name": "HILO", "carrier_name": "ONE",
         "origin_port_name": "DALIAN", "container_20gp": 5000, "valid_from": "2026-02-03"}
    ], "carrier_code": "", "warnings": []}
    f2 = {"parsed_rows": [
        {"destination_port_name": "HILO", "carrier_name": "ONE",
         "origin_port_name": "DALIAN", "container_20gp": 5200, "valid_from": "2026-03-01"}
    ], "carrier_code": "", "warnings": []}
    calls = iter([f1, f2])
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: next(calls))

    s = orchestrator.create_session("sea")
    orchestrator.add_file(s.session_id, "a.xlsx", "/tmp/a.xlsx", db=None)
    orchestrator.add_file(s.session_id, "b.xlsx", "/tmp/b.xlsx", db=None)

    assert len(s.rows) == 2
    assert all(not r["needs_review"] for r in s.rows), "valid_from 不同的行不应被标 needs_review"


# ── 编码/RF 行 needs_review 透传修复测试 ─────────────────────────────────────


def test_coded_row_needs_review_preserved_when_no_collision():
    """解析器标过 needs_review=True 的编码行，即使不与任何其他行碰撞，也应保持 True。

    修复前：_mark_needs_review 直接赋值 keys[key] > 1，单独的编码行
    因不碰撞被冲成 False，人工会漏审。
    """
    from app.services.step1_rates.sheet_builder.orchestrator import _mark_needs_review

    rows = [
        # 编码行：解析器已标 needs_review=True，且此行在会话中唯一（不碰撞）
        {
            "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
            "via": None, "commodity": "TPE1-FAK", "valid_from": "2026-02-03",
            "needs_review": True,
        },
        # 普通行：无编码标记，不碰撞 → 应保持 False
        {
            "origin": "DALIAN", "destination": "BUSAN", "carrier": "ONE",
            "via": None, "commodity": None, "valid_from": "2026-02-03",
            "needs_review": False,
        },
    ]
    _mark_needs_review(rows)

    assert rows[0]["needs_review"] is True, (
        "编码行不碰撞时仍应保持 needs_review=True（修复前会被冲成 False）"
    )
    assert rows[1]["needs_review"] is False, "普通不碰撞行应保持 False"


def test_collision_still_marks_needs_review():
    """碰撞逻辑不受 OR 改动影响：两行 key 完全相同时仍双双标 True。"""
    from app.services.step1_rates.sheet_builder.orchestrator import _mark_needs_review

    rows = [
        {
            "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
            "via": None, "commodity": "FAK", "valid_from": "2026-02-03",
            "needs_review": False,  # 解析器未标，靠碰撞检测
        },
        {
            "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
            "via": None, "commodity": "FAK", "valid_from": "2026-02-03",
            "needs_review": False,
        },
    ]
    _mark_needs_review(rows)

    assert all(r["needs_review"] for r in rows), "碰撞行仍应全部标 True"


def test_coded_row_collision_also_true():
    """编码行本身已是 True，再碰撞也应 True（OR 后不变）。"""
    from app.services.step1_rates.sheet_builder.orchestrator import _mark_needs_review

    rows = [
        {
            "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
            "via": None, "commodity": "TPE1-FAK", "valid_from": "2026-02-03",
            "needs_review": True,
        },
        {
            "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
            "via": None, "commodity": "TPE1-FAK", "valid_from": "2026-02-03",
            "needs_review": False,
        },
    ]
    _mark_needs_review(rows)

    assert all(r["needs_review"] for r in rows), "编码行碰撞时两行均应为 True"


def test_normalize_sea_passes_through_needs_review():
    """_normalize_sea 应透传 needs_review 字段；无此键时默认 False。"""
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea

    row_coded = {
        "carrier_name": "ONE", "destination_port_name": "HILO",
        "container_20gp": None, "needs_review": True,
    }
    row_normal = {
        "carrier_name": "ONE", "destination_port_name": "BUSAN",
        "container_20gp": 1500,
        # 无 needs_review 键
    }

    out_coded = _normalize_sea(row_coded, "")
    out_normal = _normalize_sea(row_normal, "")

    assert out_coded["needs_review"] is True, "解析器设置的 needs_review 应透传"
    assert out_normal["needs_review"] is False, "无 needs_review 键时应默认 False"


def test_normalize_sea_passes_through_currency():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea
    # 行带 currency → 原样透传
    assert _normalize_sea({"destination_port_name": "HILO", "currency": "USD"}, "")["currency"] == "USD"
    # 行无 currency → 默认 USD
    assert _normalize_sea({"destination_port_name": "HILO"}, "")["currency"] == "USD"


def test_expand_multi_port_sea_splits_locode_pair():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.base import Base
    from app.models.port import Port
    from app.services.step1_rates.sheet_builder.orchestrator import expand_multi_port_sea
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="USLAX", name_en="Los Angeles", name_cn="洛杉矶"),
        Port(un_locode="USLGB", name_en="Long Beach", name_cn="长滩"),
    ])
    s.commit()

    rows = [{"destination": "USLAX USLGB", "container_20gp": 100}]
    out = expand_multi_port_sea(rows, s)
    assert len(out) == 2
    assert {r["destination"] for r in out} == {"USLAX", "USLGB"}
    assert all(r["container_20gp"] == 100 for r in out)

    # 单港多词名不拆：'LOS'/'ANGELES' 非 5 位 locode → 保持整体
    rows2 = [{"destination": "LOS ANGELES", "container_20gp": 100}]
    out2 = expand_multi_port_sea(rows2, s)
    assert len(out2) == 1 and out2[0]["destination"] == "LOS ANGELES"
    s.close()
    engine.dispose()


def test_air_image_routes_to_air_ai_extractor(monkeypatch):
    from app.services.step1_rates.sheet_builder import air_ai_extractor
    fake = {"parsed_rows": [{
        "origin": "PVG", "destination": "LAX", "carrier": "CK/CA",
        "cargo_class": "普货", "packing": "托", "density": "1:167",
        "tier_prices": {45: 60.0, 100: 60.0}, "currency": "CNY",
        "effective_week_start": "2026-05-26", "effective_to": "2026-05-29",
        "multi_flight_pick": True,
    }], "warnings": [], "source_type": "air_image"}
    monkeypatch.setattr(air_ai_extractor, "parse_air_image", lambda p, db: fake)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "air.png", "/tmp/air.png", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "air_image"
    row = s.rows[0]
    assert row["destination"] == "LAX"
    assert row["carrier"] == "CK/CA"
    assert row["cargo_class"] == "普货"
    assert row["packing"] == "托"
    assert row["density"] == "1:167"
    assert row["currency"] == "CNY"
    assert row["effective_to"] == "2026-05-29"
    assert row["tier_prices"] == {45: 60.0, 100: 60.0}
    assert row["needs_review_by_destination"] is True


def test_sea_image_routes_to_ocean_ai_extractor(monkeypatch):
    from app.services.step1_rates.sheet_builder import ocean_ai_extractor
    fake = {
        "parsed_rows": [{
            "origin": "NINGBO", "destination": "ICD AHMEDABAD", "carrier": "KMTC",
            "vessel_voyage": "X/1", "via": "NHAVA SHEVA", "is_direct": False,
            "container_20gp": 1650.0, "container_40gp": 1700.0, "container_40hq": None,
            "container_45": None, "currency": "USD", "valid_from": None, "valid_to": "2026-03-22",
            "transit_days": None,
            "surcharges": [{"code": "EIS", "amount_20": 150.0, "amount_40": 300.0,
                            "currency": None, "payment": "collect", "included": False, "note": None}],
            "remark": None, "needs_review": False,
            "source_file": "ocean.png", "source_type": "ocean_image",
        }],
        "warnings": [], "source_type": "ocean_image", "file_name": "ocean.png",
    }
    monkeypatch.setattr(ocean_ai_extractor, "parse_ocean_image", lambda p, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean.png", "/tmp/ocean.png", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "ocean_image"
    row = s.rows[0]
    assert row["origin"] == "NINGBO"               # _normalize_sea origin 兜底到 row['origin']
    assert row["destination"] == "ICD AHMEDABAD"
    assert row["carrier"] == "KMTC"                # carrier 兜底到 row['carrier']
    assert row["via"] == "NHAVA SHEVA"
    assert row["vessel_voyage"] == "X/1"           # 新透传字段
    assert row["surcharges"][0]["code"] == "EIS"   # 新透传字段
    assert row["currency"] == "USD"


def test_sea_text_routes_to_ocean_ai_extractor(tmp_path, monkeypatch):
    from app.services.step1_rates.sheet_builder import ocean_ai_extractor
    f = tmp_path / "ocean.txt"
    f.write_text("海运报价文本", encoding="utf-8")
    fake = {"parsed_rows": [{"origin_port_name": "TIANJIN", "origin": "SHANGHAI",
            "destination": "BUSAN", "carrier": "KMTC",
            "container_20gp": 130.0, "currency": "USD", "surcharges": []}],
            "warnings": [], "source_type": "ocean_text", "file_name": "ocean.txt"}
    monkeypatch.setattr(ocean_ai_extractor, "parse_ocean_text", lambda text, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean.txt", str(f), db=None)

    assert fr.source_type == "ocean_text"
    assert s.rows[0]["destination"] == "BUSAN"
    assert s.rows[0]["carrier"] == "KMTC"
    assert s.rows[0]["origin"] == "TIANJIN"      # origin_port_name 优先于 origin(Excel 行依赖此不变量)
    assert s.rows[0]["surcharges"] == []         # 文本路径 surcharges 透传(空列表)


def test_air_text_routes_to_air_ai_extractor(tmp_path, monkeypatch):
    from app.services.step1_rates.sheet_builder import air_ai_extractor
    f = tmp_path / "air.txt"
    f.write_text("空运报价文本", encoding="utf-8")
    fake = {"parsed_rows": [{"origin": "PVG", "destination": "AMS",
            "tier_prices": {100: 40.0}, "currency": "CNY", "multi_flight_pick": True}],
            "warnings": [], "source_type": "air_text"}
    monkeypatch.setattr(air_ai_extractor, "parse_air_text", lambda text, db: fake)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "air.txt", str(f), db=None)

    assert fr.source_type == "air_text"
    assert s.rows[0]["destination"] == "AMS"


def test_normalize_air_carries_multidim_fields():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_air
    row = {
        "origin": "PVG", "destination": "LAX", "carrier": "CK/CA",
        "cargo_class": "普货", "packing": "托", "density": "1:167",
        "tier_prices": {45: 60.0}, "currency": "CNY",
        "effective_week_start": "2026-05-26", "effective_to": "2026-05-29",
        "multi_flight_pick": True,
    }
    out = _normalize_air(row, "")
    assert out["origin"] == "PVG"
    assert out["carrier"] == "CK/CA"
    assert out["cargo_class"] == "普货"
    assert out["packing"] == "托"
    assert out["density"] == "1:167"
    assert out["currency"] == "CNY"
    assert out["effective_to"] == "2026-05-29"
    assert out["tier_prices"] == {45: 60.0}
