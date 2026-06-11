"""P1-2 回归：做表(Sea) Excel 必须与导入页同一套解析器。

链路B实测(2026-06-08)：做表(Sea)+真实『【Ocean】Sea Net Rate』文件 → 旧
rate_parser.detect_and_parse 只认 KMTC/NVO FAK 两种格式 → 三 sheet 全报
找不到表头/无法识别、抽 0 行、下载件无运价；同一文件走导入页能出 110+ 行。
修复：sea Excel 先走 step1 海运适配器注册表(kmtc/nvo_fak/ocean/ocean_ngb)，
无适配器命中再回落旧解析器(保住内容嗅探路径)。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.step1_rates.sheet_builder import orchestrator


REAL_OCEAN_FILE = (
    Path(__file__).resolve().parents[3]
    / "资料"
    / "2026.04.21"
    / "RE_ 今後の進め方に関するご提案"
    / "【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx"
)
REAL_KMTC_FILE = Path(__file__).resolve().parents[3] / "资料" / "2026.03.31" / "kmtc 运价表 0319.xlsx"


def test_sea_excel_parses_real_ocean_workbook():
    """真实 Sea Net Rate 工作簿：抽出 FCL 行(>0)，不再 0 行。"""
    if not REAL_OCEAN_FILE.exists():
        pytest.skip(f"Ocean 真实样本不可用：{REAL_OCEAN_FILE}")
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, REAL_OCEAN_FILE.name, str(REAL_OCEAN_FILE), db=None)

    assert fr.status == "parsed", fr.message
    assert fr.row_count == 84  # 全部 FCL 行；39 行 LCL 不进 Sea 模板(箱型列布局)
    # LCL 行被剔除时必须带 warning 提示，不许静默
    assert any("LCL" in w for w in fr.warnings)

    tokyo_tsl = [
        r for r in s.rows if r["carrier"] == "T.S.L" and "TOKYO" in str(r["destination"]).upper()
    ]
    assert tokyo_tsl, "应抽到 TOKYO/YOKOHAMA × T.S.L 行"
    row = tokyo_tsl[0]
    assert row["freight_20"] == row["container_20gp"] == 80
    assert row["container_40gp"] == 160
    # ocean adapter 供数的附加费列应进入归一行（模板有对应列）
    assert row["baf"] == 200
    assert row["yas_caf"] == 30


def test_sea_excel_kmtc_still_works_via_registry():
    """KMTC 文件改走 step1 KmtcAdapter 后行为不退化。"""
    if not REAL_KMTC_FILE.exists():
        pytest.skip(f"KMTC 真实样本不可用：{REAL_KMTC_FILE}")
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, REAL_KMTC_FILE.name, str(REAL_KMTC_FILE), db=None)

    assert fr.status == "parsed", fr.message
    assert fr.row_count == 90
    assert all(r["carrier"] == "KMTC" for r in s.rows)


def test_sea_excel_unknown_format_falls_back_to_legacy(tmp_path):
    """无适配器命中的 Excel 回落旧解析器：保持「无法识别」显式报错(skipped)。"""
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "hello"
    path = tmp_path / "mystery.xlsx"
    wb.save(path)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, path.name, str(path), db=None)

    assert fr.status == "skipped"
    assert "无法识别" in fr.message or "未识别" in fr.message


def test_sea_excel_zero_fcl_rows_marks_skipped(monkeypatch):
    """适配器命中但 0 FCL 行 → 显式 skipped，不许静默空表(P0-1 口径)。"""
    from app.services.step1_rates import service as step1_service

    def fake_parse(file_path, db, *, file_type_hint=None, registry=None):
        return {"parsed_rows": [], "records": [], "warnings": [], "file_type": "ocean"}

    monkeypatch.setattr(step1_service, "parse_rate_file_to_legacy", fake_parse)
    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean_x.xlsx", "/tmp/ocean_x.xlsx", db=None)

    assert fr.status == "skipped"
    assert fr.message
