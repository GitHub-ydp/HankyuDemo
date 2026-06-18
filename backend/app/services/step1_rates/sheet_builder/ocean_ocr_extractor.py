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
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

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
