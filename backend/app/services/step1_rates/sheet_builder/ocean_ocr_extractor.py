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
