"""ONE(Ocean Network Express) 服务合约 PDF 运价解析。

文字版 PDF（pdftotext/pdfplumber 可抽），第 6 节 "CONTRACT RATES OR RATE SCHEDULE(S)"
按 COMMODITY 块组织：每块有 ORIGIN、目的港运价表(20'/40'/40HC/45')、NOTE(生效日 + 附加费清单)。
本模块只懂 ONE 这一种版式；纯解析，不依赖 vLLM。
"""
from __future__ import annotations

import re
from typing import Any

_CARRIER = "ONE"


def _clean_port_name(raw: Any) -> str:
    """港名清洗：去括号注解(如 "(CY)")、取逗号前主名 → 供 _resolve_port 匹配。"""
    if not raw:
        return ""
    s = re.sub(r"\(.*?\)", "", str(raw))   # 去 (CY)/(via …) 等括号注解
    s = s.split(",")[0]                     # "HONOLULU, HI" → "HONOLULU"
    return s.strip()


_TOL = 25.0  # 列对齐容差(pt)
_PRICE_HEADERS = [
    ("container_20gp", "20'"),
    ("container_40gp", "40'"),
    ("container_40hq", "40HC"),
    ("container_45", "45'"),
]


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _after_colon(text: str) -> str:
    return text.split(":", 1)[1].strip() if ":" in text else text.strip()


def _is_number(s: str) -> bool:
    return bool(re.fullmatch(r"\d{2,7}", s.replace(",", "")))


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _word_at(line: list[dict], x: float, tol: float = _TOL) -> dict | None:
    """返回 x0 最接近 x 且在容差内的词；无则 None。"""
    best, best_d = None, tol
    for w in line:
        d = abs(w["x0"] - x)
        if d <= best_d:
            best, best_d = w, d
    return best


def _parse_header(line: list[dict]) -> tuple[dict, float | None]:
    """从列头行取各价列 x0 + 目的港右边界(第一个 Cntry 的 x0)。"""
    cols: dict[str, float] = {}
    for w in line:
        for key, label in _PRICE_HEADERS:
            if w["text"] == label:
                cols[key] = w["x0"]
    dest_right = next((w["x0"] for w in line if w["text"] == "Cntry"), None)
    return cols, dest_right


def _parse_note(note_lines: list[str]) -> tuple[str | None, str | None, str | None]:
    text = " ".join(note_lines)
    vf = vt = None
    m = re.search(r"valid from (\d{8}) to (\d{8})", text, re.I)
    if m:
        vf, vt = _iso(m.group(1)), _iso(m.group(2))
    else:
        m_to = re.search(r"valid to (\d{8})", text, re.I)
        m_from = re.search(r"valid from (\d{8})", text, re.I)
        vt = _iso(m_to.group(1)) if m_to else None
        vf = _iso(m_from.group(1)) if m_from else None
    sn = None
    m_inc = re.search(r"(inclusive of .+?)(?:Rates are subject|$)", text, re.I)
    if m_inc:
        sn = m_inc.group(1).strip()
    return vf, vt, sn


def _parse_data_row(line: list[dict], price_cols: dict, dest_right: float | None, ctx: dict) -> dict | None:
    if not dest_right:
        return None
    dest_raw = " ".join(w["text"] for w in line if w["x0"] < dest_right - _TOL).strip()
    destination = _clean_port_name(dest_raw)
    if not destination:
        return None
    row: dict[str, Any] = {
        "carrier_name": _CARRIER,
        "origin_port_name": ctx.get("origin"),
        "destination_port_name": destination,
        "container_20gp": None, "container_40gp": None,
        "container_40hq": None, "container_45": None,
        "currency": "USD",
        "valid_from": None, "valid_to": None,
        "rate_level": None,
        "service_code": ctx.get("service_code"),
        "via": None, "is_direct": True,
        "commodity": ctx.get("commodity"),
        "remark": None,
        "needs_review": False,
    }
    has_price = False
    for key, x in price_cols.items():
        w = _word_at(line, x)
        if w is None:
            continue
        if _is_number(w["text"]):
            row[key] = _to_float(w["text"])
            has_price = True
        else:
            row["rate_level"] = w["text"]      # 编码格子(如 R5/2400)
            row["needs_review"] = True
    if not has_price and not row["needs_review"]:
        return None                            # 既无价也无编码 → 非数据行
    if not has_price:
        row["needs_review"] = True
    return row


def parse_rate_blocks(lines: list[list[dict]]) -> list[dict]:
    """状态机：扫 COMMODITY 块 → 产 parsed_rows。纯函数，不读 PDF。"""
    results: list[dict] = []
    ctx: dict[str, Any] = {}
    block_rows: list[dict] = []
    note_buf: list[str] = []
    price_cols: dict[str, float] = {}
    dest_right: float | None = None
    in_section = False
    in_note = False

    def flush_block() -> None:
        nonlocal block_rows, note_buf
        if note_buf:
            vf, vt, sn = _parse_note(note_buf)
            for r in block_rows:
                r["valid_from"], r["valid_to"] = vf, vt
                if sn:
                    r["remark"] = sn
        results.extend(block_rows)
        block_rows, note_buf = [], []

    for line in lines:
        text = _line_text(line).strip()
        if not text:
            continue
        if "CONTRACT RATES OR RATE SCHEDULE" in text.upper():
            in_section = True
            continue
        if not in_section:
            continue
        if "NOTE FOR COMMODITY" in text.upper():
            in_note = True
            note_buf = []
            continue
        is_commodity = bool(re.match(r"^\d+\)\s*COMMODITY", text))
        if in_note and not is_commodity:
            note_buf.append(text)
            continue
        if is_commodity:
            in_note = False
            flush_block()
            ctx = {"commodity": _after_colon(text) or None, "origin": None, "service_code": None}
            price_cols, dest_right = {}, None
            continue
        if text.upper().startswith("ORIGIN VIA"):
            continue
        if text.upper().startswith("ORIGIN"):
            ctx["origin"] = _clean_port_name(_after_colon(text))
            continue
        if "Destination" in text and "Cntry" in text and "Cur" in text:
            price_cols, dest_right = _parse_header(line)
            continue
        if price_cols:
            row = _parse_data_row(line, price_cols, dest_right, ctx)
            if row:
                block_rows.append(row)
    flush_block()
    return results
