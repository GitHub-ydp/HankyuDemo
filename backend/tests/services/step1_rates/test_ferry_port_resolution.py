"""P1-4 回归：太仓→下关轮渡不得错归到大阪/神户轮渡。

根因：_resolve_port 在模糊匹配前会把括号内容剥掉，"Ferry (TAG to SHIMONOSEKI)"
只剩 "Ferry"，ilike '%Ferry%' 先命中字典里 id 较小的 "Ferry (OSA/KOB)"。
修复：破坏性清洗前先做「全名归一精确匹配」，并补 ferry shimonoseki 别名。
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.port import Port
from app.services.rate_parser import _resolve_port as rp_resolve
from app.services.step1_rates.activator_mappers import _resolve_port as am_resolve


@pytest.fixture()
def db():
    import app.models  # noqa: F401 注册全部模型

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    # 与 seed_data.py 一致；JPFEROSK 故意排在前（id 更小）以复现 ilike 先命中问题
    s.add_all(
        [
            Port(un_locode="JPFEROSK", name_en="Ferry (OSA/KOB)", name_cn="轮渡(大阪/神户)"),
            Port(un_locode="JPFERTAG", name_en="Ferry (TAG to SHIMONOSEKI)", name_cn="轮渡(太仓至下关)"),
            Port(un_locode="JPTYO", name_en="Tokyo", name_cn="东京"),
        ]
    )
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ferry (TAG to SHIMONOSEKI)", "JPFERTAG"),  # JP sheet FCL 太仓段 row104
        ("Ferry\n (OSA/KOB)", "JPFEROSK"),           # JP sheet FCL 上海段 row41
        ("Ferry OSA/KOB", "JPFEROSK"),               # JP sheet LCL 上海段 row126（无括号变体）
        ("Ferry Shimonoseki", "JPFERTAG"),           # JP sheet LCL 太仓段 row131
        ("TOKYO", "JPTYO"),                          # 常规港不回归
    ],
)
def test_rate_parser_resolve_ferry(db, raw, expected):
    port = rp_resolve(raw, db)
    assert port is not None, f"{raw!r} 应解析到港"
    assert port.un_locode == expected, f"{raw!r} → {port.un_locode}，期望 {expected}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ferry (TAG to SHIMONOSEKI)", "JPFERTAG"),
        ("Ferry (OSA/KOB)", "JPFEROSK"),
    ],
)
def test_activator_resolve_ferry(db, raw, expected):
    port = am_resolve(db, raw)
    assert port is not None, f"{raw!r} 应解析到港"
    assert port.un_locode == expected, f"{raw!r} → {port.un_locode}，期望 {expected}"
