"""运价表生成会话编排。

职责：创建会话(选模板) → 接收多文件 → 按扩展名路由到现有 parser 抽取 →
把各 parser 的 parsed_rows 归一为填充器认的 normalized dict → 汇总进会话 →
同(目的港+船司)多条标 needs_review 供人工选。

复用现有抽取能力（不改）：
  rate_parser.detect_and_parse   — 结构化 Excel(kmtc/nvo 等)
  wechat_image_parser.parse_wechat_image — 微信/截图运价(AI 视觉)
  email_text_parser.parse_email_text     — 邮件正文运价

会话存内存（与 ai_parse 的 _parse_cache 同一风格；demo 重启即失，可接受）。
"""
from __future__ import annotations

import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services import rate_parser, wechat_image_parser
from app.services.step1_rates.sheet_builder.template_registry import get_template_config

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}  # .xls(老二进制)经 xlrd 读取，见 requirements
_TEXT_EXTS = {".txt", ".md", ".eml"}


@dataclass
class FileResult:
    """单个上传文件的处理结果。"""

    name: str
    source_type: str  # excel / wechat_image / email_text / unsupported / error
    status: str  # parsed / skipped / error
    row_count: int = 0
    warnings: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class SheetSession:
    """一次运价表生成会话。"""

    session_id: str
    template_type: str
    files: list[FileResult] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


_sessions: dict[str, SheetSession] = {}


def create_session(template_type: str) -> SheetSession:
    """创建会话，校验模板类型合法。"""
    get_template_config(template_type)  # 非法 type 抛 ValueError
    session_id = uuid.uuid4().hex[:12]
    session = SheetSession(session_id=session_id, template_type=template_type)
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> SheetSession:
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"rate sheet session {session_id} not found")
    return session


def add_file(
    session_id: str, file_name: str, file_path: str, db: Session | None
) -> FileResult:
    """把一个文件路由到对应 parser 抽取，归一后并入会话。失败/不支持不抛，标状态。"""
    session = get_session(session_id)
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in _EXCEL_EXTS and ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS:
        result = FileResult(
            name=file_name,
            source_type="unsupported",
            status="skipped",
            message=f"本轮暂不支持 {ext or '该'} 文件，已跳过",
        )
        session.files.append(result)
        return result

    try:
        if ext in _EXCEL_EXTS:
            parsed = rate_parser.detect_and_parse(file_path, db)
            source_type = "excel"
        elif ext in _IMAGE_EXTS:
            parsed = wechat_image_parser.parse_wechat_image(file_path, db)
            source_type = "wechat_image"
        else:  # 文本
            from app.services.email_text_parser import parse_email_text

            with open(file_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            parsed = parse_email_text(text, db)
            source_type = "email_text"
    except Exception as exc:  # noqa: BLE001 — 单文件失败不该让整批崩
        result = FileResult(
            name=file_name,
            source_type="error",
            status="error",
            message=f"解析失败: {exc}",
        )
        session.files.append(result)
        return result

    raw_rows = _extract_rows(parsed)
    carrier_fallback = parsed.get("carrier_code", "") or ""
    normalized = [
        _normalize(session.template_type, r, carrier_fallback) for r in raw_rows
    ]
    session.rows.extend(normalized)
    _mark_needs_review(session.rows)

    result = FileResult(
        name=file_name,
        source_type=source_type,
        status="parsed",
        row_count=len(normalized),
        warnings=list(parsed.get("warnings", []) or []),
    )
    session.files.append(result)
    return result


def _extract_rows(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容两种返回结构：顶层 parsed_rows，或 nvo 风格的 sheets[].parsed_rows。"""
    if parsed.get("parsed_rows"):
        return list(parsed["parsed_rows"])
    rows: list[dict[str, Any]] = []
    for sheet in parsed.get("sheets", []) or []:
        rows.extend(sheet.get("parsed_rows", []) or [])
    return rows


def _normalize(
    template_type: str, row: dict[str, Any], carrier_fallback: str
) -> dict[str, Any]:
    if template_type == "air":
        return _normalize_air(row, carrier_fallback)
    return _normalize_sea(row, carrier_fallback)


def _normalize_sea(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    return {
        "destination": row.get("destination_port_name") or row.get("destination"),
        "carrier": row.get("carrier_name") or carrier_fallback,
        "freight_20": row.get("container_20gp"),
        "freight_40": row.get("container_40gp") or row.get("container_40hq"),
        "lss_cic": row.get("lss_20") or row.get("lss_40"),
        "baf": row.get("baf_20") or row.get("baf_40"),
        "transit": row.get("transit_days"),
        "remark": row.get("remarks"),
        "source_file": row.get("source_file"),
    }


def _normalize_air(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    # 现有 parser 主产海运字段；Air 的每日价结构需专门抽取 prompt（见计划"未完成项"）。
    # 这里尽力映射通用字段，缺失留空，保证编排不崩。
    return {
        "destination": row.get("destination_port_name") or row.get("destination"),
        "service": row.get("service_code") or row.get("service") or carrier_fallback,
        "remark": row.get("remarks"),
        "source_file": row.get("source_file"),
    }


def _mark_needs_review(rows: list[dict[str, Any]]) -> None:
    """同 (目的港, 船司) 出现多条 → 全部标 needs_review，供审核台人工选。"""
    keys = Counter((r.get("destination"), r.get("carrier")) for r in rows)
    for r in rows:
        r["needs_review"] = keys[(r.get("destination"), r.get("carrier"))] > 1
