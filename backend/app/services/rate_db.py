"""航空费率数据库（Demo 用内存数据库）

基于 Customer A (ミマキエンジニアリング) 的真实报价数据构建。
数据来源：
- 1-②-2.msg: Yang Jie (购买部) 提供的成本价
- 1-②-3.msg: Nakamura (经理) 确认的 Selling Rate
- 2-④.xlsx: 最终填入的数据
"""
from dataclasses import dataclass


@dataclass
class AirRate:
    """航空运费费率"""
    origin_code: str           # 起运地代码 (PVG, NRT, TPE, AMS, ICN)
    destination_code: str      # 目的地代码 (ATL, MIA, AMS, SYD, TPE, GRU)
    currency: str              # 币种
    unit_price: float          # 单价 (/kg)
    lead_time: str             # 时效
    carrier_route: str         # 航司与路由
    remarks: str = 'ALL-in'    # 备注
    cost_type: str = 'AIR_FREIGHT'  # 费用类型
    confidence: float = 0.95   # 匹配置信度


# ── 费率数据库（基于真实案例） ──────────────────────────────

# 中国(上海) 发 — 来源：邮件 1-②-3 Nakamura S/R + 2-④ 最终填入
RATE_DB: list[AirRate] = [
    # ═══ 中国 (上海/PVG) 发 ═══
    AirRate(
        origin_code='PVG',
        destination_code='ATL',
        currency='CNY',
        unit_price=49,
        lead_time='3-4DAYS',
        carrier_route='OZ via ICN / NH via NRT',
    ),
    AirRate(
        origin_code='PVG',
        destination_code='MIA',
        currency='CNY',
        unit_price=54,
        lead_time='3-4DAYS',
        carrier_route='NH VIA NRT/CK VIA ORD',
    ),
    AirRate(
        origin_code='PVG',
        destination_code='AMS',
        currency='CNY',
        unit_price=41,
        lead_time='2DAYS',
        carrier_route='CZ/CK/CA direct flt',
    ),
    AirRate(
        origin_code='PVG',
        destination_code='SYD',
        currency='CNY',
        unit_price=25,
        lead_time='2DAYS',
        carrier_route='NH VIA NRT',
    ),
    AirRate(
        origin_code='PVG',
        destination_code='TPE',
        currency='CNY',
        unit_price=13,
        lead_time='1DAY',
        carrier_route='CK direct flt',
    ),
    AirRate(
        origin_code='PVG',
        destination_code='GRU',
        currency='CNY',
        unit_price=68,
        lead_time='5-6DAYS',
        carrier_route='CK VIA NRT/LAX',
        confidence=0.80,
    ),

    # ═══ 日本 (成田/NRT) 发 ═══ — 示例数据，Demo 用
    AirRate(
        origin_code='NRT',
        destination_code='ATL',
        currency='JPY',
        unit_price=850,
        lead_time='2DAYS',
        carrier_route='Carrier: 5X\nRoute: NRT-ANC-ATL',
        confidence=0.85,
    ),
    AirRate(
        origin_code='NRT',
        destination_code='MIA',
        currency='JPY',
        unit_price=920,
        lead_time='2-3DAYS',
        carrier_route='NH NRT-ORD-MIA',
        confidence=0.85,
    ),
    AirRate(
        origin_code='NRT',
        destination_code='AMS',
        currency='JPY',
        unit_price=780,
        lead_time='2DAYS',
        carrier_route='NH/LH direct',
        confidence=0.85,
    ),
    AirRate(
        origin_code='NRT',
        destination_code='GRU',
        currency='JPY',
        unit_price=1200,
        lead_time='3-4DAYS',
        carrier_route='NH VIA LAX',
        confidence=0.75,
    ),
    AirRate(
        origin_code='NRT',
        destination_code='SYD',
        currency='JPY',
        unit_price=650,
        lead_time='1-2DAYS',
        carrier_route='NH/JL direct',
        confidence=0.85,
    ),

    # ═══ 台湾 (台北/TPE) 发 ═══ — 示例数据
    AirRate(
        origin_code='TPE',
        destination_code='ATL',
        currency='USD',
        unit_price=5.8,
        lead_time='3-4DAYS',
        carrier_route='CI VIA LAX / BR VIA SFO',
        confidence=0.80,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='MIA',
        currency='USD',
        unit_price=6.5,
        lead_time='3-4DAYS',
        carrier_route='CI VIA LAX',
        confidence=0.80,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='AMS',
        currency='USD',
        unit_price=5.2,
        lead_time='2-3DAYS',
        carrier_route='CI/BR VIA BKK/HKG',
        confidence=0.80,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='PVG',
        currency='USD',
        unit_price=2.0,
        lead_time='1DAY',
        carrier_route='CI/CK direct',
        confidence=0.80,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='GRU',
        currency='USD',
        unit_price=9.5,
        lead_time='5-6DAYS',
        carrier_route='CI VIA LAX',
        confidence=0.70,
    ),

    # ═══ オランダ (アムステルダム/AMS) 発 ═══
    AirRate(
        origin_code='AMS',
        destination_code='ATL',
        currency='EUR',
        unit_price=4.5,
        lead_time='1-2DAYS',
        carrier_route='KL/DL direct',
        confidence=0.75,
    ),
    AirRate(
        origin_code='AMS',
        destination_code='MIA',
        currency='EUR',
        unit_price=5.0,
        lead_time='2DAYS',
        carrier_route='KL VIA ATL',
        confidence=0.75,
    ),

    # ═══ 韓国 (インチョン/ICN) 発 ═══
    AirRate(
        origin_code='ICN',
        destination_code='ATL',
        currency='USD',
        unit_price=5.5,
        lead_time='2-3DAYS',
        carrier_route='OZ VIA ICN direct / KE VIA LAX',
        confidence=0.75,
    ),
    AirRate(
        origin_code='ICN',
        destination_code='AMS',
        currency='USD',
        unit_price=4.8,
        lead_time='2DAYS',
        carrier_route='OZ/KE direct',
        confidence=0.75,
    ),
    AirRate(
        origin_code='ICN',
        destination_code='GRU',
        currency='USD',
        unit_price=9.0,
        lead_time='4-5DAYS',
        carrier_route='KE VIA NRT/LAX',
        confidence=0.70,
    ),

    # ═══ LOCAL DELIVERY COST ═══
    # ATL 着地配送
    AirRate(
        origin_code='NRT',
        destination_code='ATL',
        currency='JPY',
        unit_price=750,
        lead_time='',
        carrier_route='',
        remarks='現地配達料金 (100kg~2000kg: JPY500~JPY1500)',
        cost_type='LOCAL_DELIVERY',
        confidence=0.90,
    ),
    AirRate(
        origin_code='PVG',
        destination_code='ATL',
        currency='CNY',
        unit_price=0,
        lead_time='',
        carrier_route='',
        remarks='',
        cost_type='LOCAL_DELIVERY',
        confidence=0.60,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='ATL',
        currency='USD',
        unit_price=0,
        lead_time='',
        carrier_route='',
        remarks='',
        cost_type='LOCAL_DELIVERY',
        confidence=0.60,
    ),
    # AMS 着地配送
    AirRate(
        origin_code='NRT',
        destination_code='AMS',
        currency='JPY',
        unit_price=0,
        lead_time='',
        carrier_route='',
        remarks='',
        cost_type='LOCAL_DELIVERY',
        confidence=0.60,
    ),
    AirRate(
        origin_code='PVG',
        destination_code='AMS',
        currency='CNY',
        unit_price=0,
        lead_time='',
        carrier_route='',
        remarks='',
        cost_type='LOCAL_DELIVERY',
        confidence=0.60,
    ),
    AirRate(
        origin_code='TPE',
        destination_code='AMS',
        currency='USD',
        unit_price=0,
        lead_time='',
        carrier_route='',
        remarks='',
        cost_type='LOCAL_DELIVERY',
        confidence=0.60,
    ),
]


def query_rate(
    origin_code: str,
    destination_code: str,
    currency: str,
    cost_type: str = 'AIR_FREIGHT',
) -> AirRate | None:
    """按航线查询费率

    Args:
        origin_code: 起运地代码（如 PVG）
        destination_code: 目的地代码（如 ATL）
        currency: 币种（如 CNY）
        cost_type: 费用类型 AIR_FREIGHT / LOCAL_DELIVERY

    Returns:
        匹配的费率，无匹配返回 None
    """
    for rate in RATE_DB:
        if (rate.origin_code == origin_code
            and rate.destination_code == destination_code
            and rate.currency == currency
            and rate.cost_type == cost_type):
            return rate
    return None


def query_rates_for_section(origin_code: str, currency: str) -> list[AirRate]:
    """按发地段查询所有可用费率"""
    return [
        r for r in RATE_DB
        if r.origin_code == origin_code and r.currency == currency
    ]


def get_all_rates() -> list[dict]:
    """获取所有费率数据（API 用）"""
    return [
        {
            'origin_code': r.origin_code,
            'destination_code': r.destination_code,
            'currency': r.currency,
            'unit_price': r.unit_price,
            'lead_time': r.lead_time,
            'carrier_route': r.carrier_route,
            'remarks': r.remarks,
            'cost_type': r.cost_type,
            'confidence': r.confidence,
        }
        for r in RATE_DB
    ]
