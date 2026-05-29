"""按投标包货量选重量档。

Customer A (Air) 投标包是「单一价」(每条航线一个単価格)，但货量写在「想定物量」列：
`1件当たりの想定平均重量：150kg/shipment`。据此把多档运价塌成一个数：
解析想定平均重量 → 选「阈值 ≤ 计费重的最高档」(150kg→100KG 档)。

计费重直接用想定平均重量(投标包已给重量，暂不做体积重换算)。选档规则、min charge、
「凑高档取低价」(break-down) 等待福山确认后微调——见 memory step2-air-bid-format。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# 「…想定平均重量：750kg…」/「…：530 kg…」(全角或半角冒号，数字与 kg 间可有空格)
_AVG_WEIGHT = re.compile(r"想定平均重量\s*[：:]\s*(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE)


def parse_assumed_weight(volume_desc: str | None) -> Decimal | None:
    """从「想定物量」单元格文本解析想定平均重量(kg)；无则 None。"""
    if not volume_desc:
        return None
    m = _AVG_WEIGHT.search(volume_desc)
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except InvalidOperation:
        return None


def select_tier_price(
    tier_prices: dict[Any, Any], weight: Decimal | None
) -> tuple[Decimal, int] | None:
    """按计费重选一档 → (单价 Decimal, 档位 KG)。

    规则：取「阈值 ≤ weight 的最高档」；weight 低于最小档则取最小档。
    weight 为 None(投标包没给重量) → 返回 None，**不自动默认某档**(避免重蹈「默认100」)。
    tier_prices 键可能是 int 或字符串(JSON 列读回)。
    """
    if weight is None or not tier_prices:
        return None
    tiers = {int(kg): price for kg, price in tier_prices.items() if price is not None}
    if not tiers:
        return None

    le = [kg for kg in tiers if kg <= weight]
    chosen = max(le) if le else min(tiers)
    return (Decimal(str(tiers[chosen])), chosen)
