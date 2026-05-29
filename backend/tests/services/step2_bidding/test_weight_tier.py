"""按投标包货量选重量档(weight_tier)测试。

Customer A (Air) 投标包是「单一价」：每条航线一个単価格，但货量写在「想定物量」列里
(1件当たりの想定平均重量：150kg/shipment)。据此：解析想定平均重量 → 选「阈值 ≤ 计费重的最高档」。
真实文本片段取自 资料/2026.04.02/Customer A (Air) 的 見積りシート。
"""
from decimal import Decimal

from app.services.step2_bidding.weight_tier import (
    parse_assumed_weight,
    select_tier_price,
)


def test_parse_assumed_weight_from_pkg_text():
    f = parse_assumed_weight
    # 真实「想定物量」单元格(全角冒号；有的带空格)
    assert f(
        "想定荷姿：カートン\n月間の想定出荷件数：15件/月\n"
        "1件当たりの想定平均重量：750kg/shipment\n1件当たりの想定重量帯：100kg ～ 2000kg/shipment"
    ) == Decimal("750")
    assert f("1件当たりの想定平均重量：150kg/shipment") == Decimal("150")
    assert f("1件当たりの想定平均重量：530 kg/shipment") == Decimal("530")  # 数字与 kg 间有空格
    assert f("同上") is None  # LOCAL DELIVERY 行「同上」无重量
    assert f(None) is None
    assert f("") is None


def test_select_tier_price_picks_highest_threshold_le_weight():
    tiers = {45: 17.0, 100: 14.0, 500: 13.5, 1000: 13.0}
    # 150kg → 落 100~300 间 → 用 100KG 档
    assert select_tier_price(tiers, Decimal("150")) == (Decimal("14.0"), 100)
    assert select_tier_price(tiers, Decimal("600")) == (Decimal("13.5"), 500)
    assert select_tier_price(tiers, Decimal("2000")) == (Decimal("13.0"), 1000)
    assert select_tier_price(tiers, Decimal("100")) == (Decimal("14.0"), 100)  # 恰等于阈值


def test_select_tier_price_below_min_uses_min_tier():
    tiers = {45: 17.0, 100: 14.0}
    assert select_tier_price(tiers, Decimal("40")) == (Decimal("17.0"), 45)


def test_select_tier_price_string_keys_and_edge_cases():
    tiers = {"100": 42.0, "300": 42.0, "500": 42.0}  # JSON 列读回是字符串键
    assert select_tier_price(tiers, Decimal("150")) == (Decimal("42.0"), 100)
    assert select_tier_price(tiers, None) is None  # 无计费重 → 不自动选(不默认100)
    assert select_tier_price({}, Decimal("150")) is None
