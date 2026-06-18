"""Ocean(海运) 规整网格截图 → 行：本地 RapidOCR 确定性抽取，替 VLM 处理订舱网站导出的表格图。

检测不到表头 / 抽 0 行 / 引擎异常 → 返回带 error 的空结果（不抛），由 orchestrator 回落 VLM。
对外只暴露 parse_ocean_grid，返回结构与 ocean_ai_extractor.parse_ocean_image 同构。
"""
from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy.orm import Session

_PRICE_COLS = ("c20", "c40gp", "c40hq", "c45")
_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
# 航程天数 token(如「49天」「6 天」):订舱网格里夹在起运港→目的港之间,OCR 易落进
# 目的港/起运港列,会污染港名。识别出来→剔出港名 + 收进 transit_days。
_TRANSIT_RE = re.compile(r"^(\d+)\s*天$")

_engine = None


def _get_engine():
    """RapidOCR 进程内单例懒加载（避免每张图重载模型）。"""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _blocks_from_result(result: Any) -> list[dict[str, Any]]:
    """RapidOCR 结果(list[[box,text,score]] 或 None) → 归一文本块；丢空文本。"""
    blocks: list[dict[str, Any]] = []
    for box, text, _score in (result or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        t = str(text).strip()
        if not t:
            continue
        blocks.append({
            "text": t,
            "xc": sum(xs) / 4.0, "yc": sum(ys) / 4.0,
            "xl": min(xs), "xr": max(xs), "h": max(ys) - min(ys),
        })
    return blocks


def _cluster_rows(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 Y 把块聚成行：相邻块 Y 间隔 > 中位字高×0.8 视为新行（POC 验证过的口径）。"""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b["yc"])
    heights = sorted(b["h"] for b in ordered)
    med_h = heights[len(heights) // 2] or 20
    rows: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    last_y: float | None = None
    for b in ordered:
        if last_y is not None and b["yc"] - last_y > med_h * 0.8:
            rows.append(cur)
            cur = []
        cur.append(b)
        last_y = b["yc"]
    if cur:
        rows.append(cur)
    return rows


def _classify_header(text: str) -> str | None:
    """单个表头单元 → 规范列名；认不出返回 None。OCR 轻微变形做容错。"""
    if "起运港" in text or "起運港" in text:
        return "origin"
    if "目的港" in text or "目的" in text:
        return "destination"
    if "船司" in text:
        return "carrier"
    if "有效期" in text:
        return "valid"
    t = text.upper().replace(" ", "").replace("'", "").replace("’", "")
    if "45" in t and "HQ" in t:
        return "c45"
    if "40" in t and "HQ" in t:
        return "c40hq"
    if "40" in t and "GP" in t:
        return "c40gp"
    if "20" in t and "GP" in t:
        return "c20"
    return None


def _cols_to_bands(cells: list[tuple[str, float]]) -> dict[str, tuple[float, float]]:
    """(列名, x中心) 列表 → 每列 X 区间(相邻中心取中点;首尾开放)。"""
    cells = sorted(cells, key=lambda c: c[1])
    bands: dict[str, tuple[float, float]] = {}
    for i, (col, xc) in enumerate(cells):
        left = float("-inf") if i == 0 else (cells[i - 1][1] + xc) / 2.0
        right = float("inf") if i == len(cells) - 1 else (xc + cells[i + 1][1]) / 2.0
        bands[col] = (left, right)
    return bands


def _detect_grid_header(
    rows: list[list[dict[str, Any]]]
) -> tuple[int, dict[str, tuple[float, float]]] | None:
    """找表头行(≥4 已知列 + 含目的港 + ≥1 价格列)。返回 (行号, 列X区间)。

    用整行所有单元(未知列给占位名 _xN)切 band,使中间列(舱位/船期/历史等)各占自己的带,
    不污染目标列。未命中返回 None(交路由回落 VLM)。
    """
    for idx, row in enumerate(rows):
        ordered = sorted(row, key=lambda d: d["xc"])
        known = [_classify_header(b["text"]) for b in ordered]
        known_set = {k for k in known if k}
        if len(known_set) >= 4 and "destination" in known_set and (known_set & set(_PRICE_COLS)):
            cells: list[tuple[str, float]] = []
            used: set[str] = set()
            for i, b in enumerate(ordered):
                col = known[i]
                if not col or col in used:
                    col = f"_x{i}"
                used.add(col)
                cells.append((col, b["xc"]))
            return idx, _cols_to_bands(cells)
    return None


def _norm_price(text: str) -> float | None:
    """金额文本 → float。去 $ ¥ 逗号空格;修 OCR 把 $ 误读成的前导 S(S1000);取首个数字。"""
    t = text.strip().replace(",", "").replace(" ", "").lstrip("$¥￥")
    t = re.sub(r"^[Ss](?=\d)", "", t)
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        v = float(m.group())
    except ValueError:
        return None
    return v if v > 0 else None


def _assign(xc: float, bands: dict[str, tuple[float, float]]) -> str | None:
    """token 的 x 中心落到哪个列区间。"""
    for col, (left, right) in bands.items():
        if left <= xc < right:
            return col
    return None


_CURRENCY_PREFIX = re.compile(r"^[$¥￥Ss]\s*\d")


def _looks_priced(text: str) -> bool:
    """原文带货币标记($ ¥ ￥ 或 OCR 把 $ 误读的前导 S),用来从水印纯数字里挑出真价。"""
    return bool(_CURRENCY_PREFIX.match(text.strip()))


def _first_price(
    blocks_in_col: list[dict[str, Any]] | None,
    band: tuple[float, float] | None = None,
) -> float | None:
    """从某价列的候选块里挑价:优先带货币标记的;其次离列中心最近(挡水印纯数字)。"""
    cands = [(b, _norm_price(b["text"])) for b in (blocks_in_col or [])]
    cands = [(b, p) for b, p in cands if p is not None]
    if not cands:
        return None
    marked = [bp for bp in cands if _looks_priced(bp[0]["text"])]
    pool = marked or cands
    if band and band[0] != float("-inf") and band[1] != float("inf"):
        center = (band[0] + band[1]) / 2.0
        pool.sort(key=lambda bp: abs(bp[0]["xc"] - center))
    else:
        pool.sort(key=lambda bp: bp[0]["xl"])
    return pool[0][1]


def _iso_dates(text: str) -> list[str]:
    """抽出文本里的日期并规范成 ISO YYYY-MM-DD(容错 - / . 分隔与单位数月日)。"""
    out: list[str] = []
    for m in _DATE_RE.finditer(text):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        out.append(f"{y}-{mo:02d}-{d:02d}")
    return out


def _distinct_prices(blocks_in_col: list[dict[str, Any]] | None) -> set[float]:
    """某价列里能解析出的不同价格值集合(用于判该列是否多候选/有歧义)。"""
    vals: set[float] = set()
    for b in (blocks_in_col or []):
        p = _norm_price(b["text"])
        if p is not None:
            vals.add(p)
    return vals


def _join_col(blocks_in_col: list[dict[str, Any]] | None) -> str:
    """拼港名列文本;剔掉夹进来的航程天数 token(「X天」非港名一部分)。"""
    return " ".join(
        t["text"] for t in sorted(blocks_in_col or [], key=lambda d: (d["yc"], d["xl"]))
        if not _TRANSIT_RE.match(t["text"].strip())
    ).strip()


def _transit_days(blocks: list[dict[str, Any]] | None) -> int | None:
    """从给定块里找航程天数「X天」→ int;无则 None。"""
    for b in (blocks or []):
        m = _TRANSIT_RE.match(b["text"].strip())
        if m:
            return int(m.group(1))
    return None


def _rows_from_ocr(
    rows: list[list[dict[str, Any]]],
    header_idx: int,
    bands: dict[str, tuple[float, float]],
    source_file: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """表头之下每行 → 按列 X 绑 token → 归一为 ocean 行 dict(与 ocean_ai_extractor 同构)。"""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for row in rows[header_idx + 1:]:
        binned: dict[str, list[dict[str, Any]]] = {}
        for b in row:
            col = _assign(b["xc"], bands)
            if col:
                binned.setdefault(col, []).append(b)
        dest = _join_col(binned.get("destination"))
        if not dest:
            continue
        c20 = _first_price(binned.get("c20"), bands.get("c20"))
        c40gp = _first_price(binned.get("c40gp"), bands.get("c40gp"))
        c40hq = _first_price(binned.get("c40hq"), bands.get("c40hq"))
        c45 = _first_price(binned.get("c45"), bands.get("c45"))
        if not any((c20, c40gp, c40hq, c45)):
            continue  # 无价行(分隔/空行)跳过
        carrier = None
        if binned.get("carrier"):
            carrier = sorted(binned["carrier"], key=lambda d: d["xl"])[0]["text"].strip() or None
        dates = sorted({
            iso for b in binned.get("valid", []) for iso in _iso_dates(b["text"])
        })
        valid_from = dates[0] if dates else None
        valid_to = dates[-1] if len(dates) >= 2 else None
        origin = _join_col(binned.get("origin")) or "NINGBO"
        transit_days = _transit_days((binned.get("destination") or []) + (binned.get("origin") or []))
        price_ambiguous = any(len(_distinct_prices(binned.get(c))) >= 2 for c in _PRICE_COLS)
        needs_review = (not carrier) or (not valid_to) or (not (c20 and c40gp)) or price_ambiguous
        out.append({
            "origin": origin,
            "destination": dest,
            "carrier": carrier,
            "vessel_voyage": None,
            "via": None,
            "is_direct": True,
            "container_20gp": c20,
            "container_40gp": c40gp,
            "container_40hq": c40hq,
            "container_45": c45,
            "currency": "USD",
            "valid_from": valid_from,
            "valid_to": valid_to,
            "transit_days": transit_days,
            "surcharges": [],
            "remark": None,
            "needs_review": needs_review,
            "source_file": source_file,
            "source_type": "ocean_image",
        })
    return out, warnings


def _empty(source_file: str, msg: str) -> dict[str, Any]:
    return {
        "parsed_rows": [], "total_rows": 0, "error": msg,
        "source_type": "ocean_image", "file_name": source_file,
    }


def parse_ocean_grid(image_path: str, db: Session | None = None) -> dict[str, Any]:
    """规整网格海运截图 → 行。未检测到表头/0行/引擎异常 → 带 error 的空结果(交路由回落 VLM)。"""
    source_file = os.path.basename(image_path)
    try:
        engine = _get_engine()
        result, _elapse = engine(image_path)
    except Exception as e:  # noqa: BLE001 — 引擎缺失/异常不抛,回落 VLM
        return _empty(source_file, f"OCR 引擎不可用: {e}")
    rows_clustered = _cluster_rows(_blocks_from_result(result))
    header = _detect_grid_header(rows_clustered)
    if header is None:
        return _empty(source_file, "未检测到规整表头(非网格表)")
    header_idx, bands = header
    rows, warnings = _rows_from_ocr(rows_clustered, header_idx, bands, source_file)
    if not rows:
        return _empty(source_file, "检测到表头但未抽出有效运价行")
    return {
        "parsed_rows": rows, "total_rows": len(rows),
        "warnings": warnings, "source_type": "ocean_image", "file_name": source_file,
    }
