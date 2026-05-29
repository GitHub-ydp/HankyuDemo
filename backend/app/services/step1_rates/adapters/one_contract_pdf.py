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
