"""运价表生成会话编排。

职责：创建会话(选模板) → 接收多文件 → 按扩展名路由到现有 parser 抽取 →
把各 parser 的 parsed_rows 归一为填充器认的 normalized dict → 汇总进会话 →
同(目的港+船司)多条标 needs_review 供人工选。

复用现有抽取能力（不改）：
  rate_parser.detect_and_parse   — 结构化 Excel(kmtc/nvo 等)
  ocean_ai_extractor.parse_ocean_image — 海运微信/截图运价(AI 视觉, 箱型价+结构化附加费)
  ocean_ai_extractor.parse_ocean_text  — 海运邮件/文本运价

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

from app.services import rate_parser
from app.services.step1_rates.sheet_builder import air_extractor, air_ai_extractor, ocean_ai_extractor
from app.services.step1_rates.sheet_builder.template_registry import get_template_config

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}  # .xls(老二进制)经 xlrd 读取，见 requirements
_TEXT_EXTS = {".txt", ".md", ".eml"}
_PDF_EXTS = {".pdf"}


@dataclass
class FileResult:
    """单个上传文件的处理结果。"""

    name: str
    source_type: str  # excel / pdf / air_image / air_text / ocean_image / ocean_text / unsupported / error
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
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_image(file_path, db)
                source_type = "air_image"
            else:
                parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)
                source_type = "ocean_image"
        else:  # 文本
            with open(file_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_text(text, db)
                source_type = "air_text"
            else:
                parsed = ocean_ai_extractor.parse_ocean_text(text, db)
                source_type = "ocean_text"
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
    # sea 多港格(如 'USLAX USLGB')拆成多行(同价)，审核台展示拆开后的行
    if session.template_type == "sea" and db is not None:
        normalized = expand_multi_port_sea(normalized, db)
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
        "origin": row.get("origin_port_name") or row.get("origin") or "SHANGHAI",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "carrier": row.get("carrier_name") or row.get("carrier") or carrier_fallback,
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
        # ocean AI 抽取新字段（旧 Excel/PDF 行无这些键 → None/[]，不影响）
        "surcharges": row.get("surcharges") or [],
        "vessel_voyage": row.get("vessel_voyage"),
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


def expand_multi_port_sea(
    rows: list[dict[str, Any]], db: Session
) -> list[dict[str, Any]]:
    """sea 归一行 destination 形如 'USLAX USLGB'(多 UN/LOCODE 空格拼接)→ 拆成多行(同价)。

    仅当按空白拆出 >1 段、且每段都是已存在的 5 位 UN/LOCODE 才拆；否则原样
    ('LOS ANGELES' 的 'LOS'/'ANGELES' 非 locode → 不拆，避开单港多词名被拆烂)。
    """
    from app.models.port import Port

    def _is_locode(token: str) -> bool:
        return (
            len(token) == 5
            and token.isalpha()
            and token.isupper()
            and db.query(Port).filter(Port.un_locode == token).first() is not None
        )

    out: list[dict[str, Any]] = []
    for row in rows:
        dest = row.get("destination")
        parts = str(dest).split() if dest else []
        if len(parts) > 1 and all(_is_locode(p) for p in parts):
            out.extend({**row, "destination": p} for p in parts)
        else:
            out.append(row)
    return out


def _normalize_air(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    """air_extractor/air_ai_extractor 产多形态，映射到模板字段：
      - 周表源(Market Price)：price_dayN → day1..day7；
      - 档位源(EES/唯凯/air 图片/文本)：tier_prices(稀疏 KG→价)原样透传(值转 float)。
    air 图片/文本另带结构化多维字段(carrier/cargo_class/packing/density/currency/effective_to)，
    EES/周表行无这些键 → None，不影响。Decimal 转 float 便于写表与 JSON。
    """
    normalized: dict[str, Any] = {
        # 起运港：air 图片行带 origin；否则默认上海 PVG。
        "origin": row.get("origin_port_name") or row.get("origin") or "PVG",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "service": (
            row.get("service_desc")
            or row.get("airline_code")
            or row.get("service_code")
            or row.get("service")
            or carrier_fallback
        ),
        # 结构化多维字段(air 图片/文本)；EES/周表行无 → None。
        "carrier": row.get("carrier"),
        "cargo_class": row.get("cargo_class"),
        "packing": row.get("packing"),
        "density": row.get("density"),
        "currency": row.get("currency"),
        "remark": row.get("remarks") or row.get("remark"),
        "source_file": row.get("source_file"),
        "effective_week_start": _to_week_str(row.get("effective_week_start")),
        "effective_to": _to_week_str(row.get("effective_to")),
        "needs_review_by_destination": bool(row.get("multi_flight_pick")),
    }
    tier_prices = row.get("tier_prices")
    if tier_prices:
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
    # air 行有 "service" 键(由 _normalize_air 恒设, 即使空串); sea 行从不设 → 用它区分聚合分支。
    # 不能再用 "carrier" in row 判别——air 行现也带 carrier 键(会误判进 sea 分支)。
    if "service" in row:
        return (row.get("destination"), row.get("service"))
    return (
        row.get("origin"),
        row.get("destination"),
        row.get("carrier"),
        row.get("via"),
        row.get("commodity"),
        row.get("valid_from"),
    )


def _mark_needs_review(rows: list[dict[str, Any]]) -> None:
    """同 (目的港, 船司/service) 出现多条 → 全部标 needs_review，供审核台人工选。
    已被解析器标 needs_review=True 的行（如编码/RF 行）保留不被覆盖。"""
    keys = Counter(_review_key(r) for r in rows)
    for r in rows:
        r["needs_review"] = bool(r.get("needs_review")) or (keys[_review_key(r)] > 1)
