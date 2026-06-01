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
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services import rate_parser, wechat_image_parser
from app.services.step1_rates.sheet_builder import air_extractor
from app.services.step1_rates.sheet_builder.template_registry import get_template_config

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}  # .xls(老二进制)经 xlrd 读取，见 requirements
_TEXT_EXTS = {".txt", ".md", ".eml"}
_PDF_EXTS = {".pdf"}


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

    if ext not in _EXCEL_EXTS and ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS and ext not in _PDF_EXTS:
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
            if session.template_type == "air":
                # Air 走专用抽取器(复用 AirAdapter 的每日价解析)；Sea 走结构化 Excel 解析。
                parsed = air_extractor.extract_air_rates(file_path, db)
            else:
                parsed = rate_parser.detect_and_parse(file_path, db)
            source_type = "excel"
        elif ext in _PDF_EXTS:
            from app.services.rate_parser_pdf import detect_and_parse_pdf
            parsed = detect_and_parse_pdf(file_path, db)
            source_type = "pdf"
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

    # parser 跑通但识别不了格式(返回 error 且无行)：标 skipped 并把原因透传给用户，
    # 不要静默显示 0 行让人对着空表猜。
    if not raw_rows and parsed.get("error"):
        result = FileResult(
            name=file_name,
            source_type=source_type,
            status="skipped",
            message=str(parsed["error"]),
        )
        session.files.append(result)
        return result

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
    c20 = row.get("container_20gp")
    c40gp = row.get("container_40gp")
    c40hq = row.get("container_40hq")
    return {
        # 起运港按文件，默认上海（Sea Net Rate 模板 From: Shanghai）
        "origin": row.get("origin_port_name") or "SHANGHAI",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "carrier": row.get("carrier_name") or carrier_fallback,
        # 结构化箱型价：入库 FreightRate 用，不再合并丢失
        "container_20gp": c20,
        "container_40gp": c40gp,
        "container_40hq": c40hq,
        "transit_days": row.get("transit_days"),
        # 兼容前端现有 sea 预览列
        "freight_20": c20,
        "freight_40": c40gp or c40hq,
        "lss_cic": row.get("lss_20") or row.get("lss_40"),
        "baf": row.get("baf_20") or row.get("baf_40"),
        "transit": row.get("transit_days"),
        "remark": row.get("remark") or row.get("remarks"),
        "source_file": row.get("source_file"),
        # PDF(ONE 合约)透传字段：老 Excel 行无这些键 → None/默认，无影响
        "container_45": row.get("container_45"),
        "valid_from": row.get("valid_from"),
        "valid_to": row.get("valid_to"),
        "rate_level": row.get("rate_level"),
        "service_code": row.get("service_code"),
        "via": row.get("via"),
        "is_direct": row.get("is_direct", True),
        "commodity": row.get("commodity"),
        "source_type": row.get("source_type"),
        "currency": row.get("currency") or "USD",
        "needs_review": row.get("needs_review", False),
    }


def _normalize_air(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    """air_extractor 产两种形态，映射到模板字段后二选一：
      - 周表源(Market Price)：price_dayN → day1..day7（按周给价）；
      - 档位源(EES/唯凯)：tier_prices(稀疏 KG→价) 原样透传（值转 float），不发 day1-7。
    Decimal 转 float 便于写表与 JSON。
    """
    normalized: dict[str, Any] = {
        # 起运港：Air 默认上海 PVG（与 AirAdapter._DEFAULT_ORIGIN 一致；EES 等联运商均沪发）。
        "origin": row.get("origin_port_name") or "PVG",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "service": (
            row.get("service_desc")
            or row.get("airline_code")
            or row.get("service_code")
            or row.get("service")
            or carrier_fallback
        ),
        "remark": row.get("remarks") or row.get("remark"),
        "source_file": row.get("source_file"),
        # 周起始日：随行带到填充器，按该周动态改写模板的 day1-7 日期表头/sheet 名（ISO 字符串便于 JSON 往返）。
        "effective_week_start": _to_week_str(row.get("effective_week_start")),
        # 重量档报价(联运商)同港多航班 → 按目的港标 needs_review，交审核台人工选一条。
        "needs_review_by_destination": bool(row.get("multi_flight_pick")),
    }
    tier_prices = row.get("tier_prices")
    if tier_prices:
        # 档位源：键归一为 int(KG)、值统一 float（前端动态档位列 + 程序生成档位表）。
        normalized["tier_prices"] = {
            int(kg): float(price)
            for kg, price in tier_prices.items()
            if price is not None
        }
    else:
        for day in range(1, 8):
            normalized[f"day{day}"] = _to_number(row.get(f"price_day{day}"))
    return normalized


def _to_week_str(value: Any) -> str | None:
    """date/datetime → 'YYYY-MM-DD' ISO 字符串；已是字符串则取前 10 位；None 保持 None。"""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10] or None


def _to_number(value: Any) -> Any:
    """Decimal → float（None 保持 None），便于 openpyxl 写入与 JSON 序列化。"""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _review_key(row: dict[str, Any]) -> tuple[Any, ...]:
    # 重量档报价(联运商)：同目的港多航班需人工选一条 → 仅按目的港聚合。
    if row.get("needs_review_by_destination"):
        return (row.get("destination"),)
    # sea 行有 "carrier" 字段；air 周报行有 "service" 字段。
    # sea 分支扩展 key 加入 via 和 commodity：同 dest+carrier 但网关/commodity 不同的合约行不被误判重复。
    # kmtc/Excel 行 via=None, commodity=None → key 与原来等价，行为不变。
    if "carrier" in row:
        return (
            row.get("origin"),
            row.get("destination"),
            row.get("carrier"),
            row.get("via"),
            row.get("commodity"),
            row.get("valid_from"),
        )
    return (row.get("destination"), row.get("service"))


def _mark_needs_review(rows: list[dict[str, Any]]) -> None:
    """同 (目的港, 船司/service) 出现多条 → 全部标 needs_review，供审核台人工选。
    已被解析器标 needs_review=True 的行（如编码/RF 行）保留不被覆盖。"""
    keys = Counter(_review_key(r) for r in rows)
    for r in rows:
        r["needs_review"] = bool(r.get("needs_review")) or (keys[_review_key(r)] > 1)
