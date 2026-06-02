# 港口字典缺口整体修 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ONE 合约入库的 3997「港口未匹配」行尽量救回（别名归一 + 补字典 + 多港拆分），并修 air 区域多港格丢港。

**Architecture:** 新建共享 `port_normalizer.canonicalize`（别名/去尾缀/去标点折叠），接进 sea 的 `activator_mappers._resolve_port` 末步兜底；`scripts/seed_data.PORTS` 追加真缺的港（reseed 共享同列表，无需改 admin.py）；`orchestrator.add_file` 对 sea 行做 `expand_multi_port_sea`（仅多 UN/LOCODE 才拆）；`air_ees._clean_dest` 改 `findall` 取全部三字码、调用处每码发一行。

**Tech Stack:** Python + SQLAlchemy + pytest。无前端改动。

**Spec:** `docs/superpowers/specs/2026-06-01-port-coverage-fix-design.md`

**⚠️ 计划期范围微调（已与用户确认）**：Phase 1 只接 `activator_mappers._resolve_port`（ONE 合约 commit 实际用的解析器）。spec 提到的 `rate_parser._resolve_port` 结构不同、有自己的 `PORT_ALIAS_MAP`、且成功标准用不到 → **defer**，避免回归风险。air 侧只改 `air_ees.py`（`air_weight_break.py` 经核实取 dest 是原值、无区域多港逻辑 → 不碰）。

---

## File Structure

- 新建 `backend/app/services/step1_rates/port_normalizer.py` —— 港口名规范化（别名 + 去尾缀 + 折叠），纯函数无依赖。
- 改 `backend/app/services/step1_rates/activator_mappers.py` —— `_resolve_port` 末步加 canonicalize 兜底。
- 改 `scripts/seed_data.py` —— `PORTS` 追加 22 个港。
- 改 `backend/app/services/step1_rates/sheet_builder/orchestrator.py` —— 加 `expand_multi_port_sea`，`add_file` 对 sea 调用。
- 改 `backend/app/services/step1_rates/sheet_builder/air_ees.py` —— `_clean_dest` 返回 list，调用处每码发一行。
- 测试：`tests/services/step1_rates/test_port_normalizer.py`(新)、`test_resolve_port_aliases.py`(新)、`test_seed_new_ports.py`(新)、`tests/sheet_builder/test_orchestrator.py`(增)、`tests/sheet_builder/test_air_ees.py`(增)。

任务顺序按 phase：1a normalizer → 1b 接入 → 2 补字典 → 3 sea 拆分 → 4 air 拆分 → 5 全量验证。每 phase 后可重跑诊断看增量。

---

## Task 1: port_normalizer.canonicalize（Phase 1a）

**Files:**
- Create: `backend/app/services/step1_rates/port_normalizer.py`
- Test: `backend/tests/services/step1_rates/test_port_normalizer.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/services/step1_rates/test_port_normalizer.py`：

```python
from app.services.step1_rates.port_normalizer import canonicalize


def test_alias_pusan_to_busan():
    assert canonicalize("PUSAN") == "BUSAN"


def test_strip_city_suffix():
    assert canonicalize("KAOHSIUNG CITY") == "KAOHSIUNG"
    assert canonicalize("TAICHUNG CITY") == "TAICHUNG"


def test_strip_port_suffix():
    assert canonicalize("KATTUPALLI PORT") == "KATTUPALLI"


def test_saint_louis_alias_and_fold():
    assert canonicalize("SAINT LOUIS") == "STLOUIS"


def test_port_klang_keeps_leading_port():
    # 末尾词是 KLANG(非尾缀)，首词 PORT 不删；KLANG→KELANG
    assert canonicalize("PORT KLANG") == "PORTKELANG"


def test_chittagong_alias():
    assert canonicalize("CHITTAGONG") == "CHATTOGRAM"


def test_empty():
    assert canonicalize(None) == ""
    assert canonicalize("") == ""
    assert canonicalize("   ") == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_port_normalizer.py -q`
Expected: FAIL（ModuleNotFoundError: port_normalizer）。

- [ ] **Step 3: 写实现**

新建 `backend/app/services/step1_rates/port_normalizer.py`：

```python
"""港口名规范化：把料表/合约里的写法折叠成『更可能命中字典』的规范名。

只产出规范名，匹配仍交给 _resolve_port 复用。别名/尾缀为代码常量(YAGNI，不上 DB)。
"""
from __future__ import annotations

import re

# 别名：合约/料表写法(词级, 全大写) → 字典规范名
PORT_ALIASES = {
    "PUSAN": "BUSAN",          # 罗马音变体
    "CHITTAGONG": "CHATTOGRAM",  # 旧名/新名
    "KLANG": "KELANG",         # PORT KLANG → PORT KELANG
    "SAINT": "ST",             # SAINT LOUIS → ST LOUIS →(折叠去点)STLOUIS
}
_SUFFIX_WORDS = {"CITY", "PORT"}  # 末尾独立词尾缀，去掉(KAOHSIUNG CITY / KATTUPALLI PORT)


def canonicalize(name: str | None) -> str:
    """大写 → 拆词(非字母数字分隔) → 去末尾 CITY/PORT 词 → 词级套别名 → 拼成 alnum 串。

    例：'PUSAN'→'BUSAN'、'KAOHSIUNG CITY'→'KAOHSIUNG'、'SAINT LOUIS'→'STLOUIS'、
    'PORT KLANG'→'PORTKELANG'、'KATTUPALLI PORT'→'KATTUPALLI'。无内容→''。
    """
    if not name:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", str(name).upper())
    if not words:
        return ""
    if len(words) > 1 and words[-1] in _SUFFIX_WORDS:
        words = words[:-1]
    words = [PORT_ALIASES.get(w, w) for w in words]
    return "".join(words)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_port_normalizer.py -q`
Expected: 8 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/port_normalizer.py backend/tests/services/step1_rates/test_port_normalizer.py
git commit -m "feat(step1): port_normalizer.canonicalize 港口名归一(别名/去尾缀/折叠)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 接进 activator_mappers._resolve_port（Phase 1b）

**Files:**
- Modify: `backend/app/services/step1_rates/activator_mappers.py`（import + `_resolve_port` 末步，约 :335-341）
- Test: `backend/tests/services/step1_rates/test_resolve_port_aliases.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/services/step1_rates/test_resolve_port_aliases.py`：

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.port import Port
from app.services.step1_rates.activator_mappers import _resolve_port


@pytest.fixture()
def db():
    import app.models  # noqa: F401 注册全部模型
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="KRPUS", name_en="Busan", name_cn="釜山"),
        Port(un_locode="TWKHH", name_en="Kaohsiung", name_cn="高雄"),
        Port(un_locode="INKTP", name_en="Kattupalli", name_cn="卡图帕利"),
        Port(un_locode="BDCGP", name_en="Chattogram", name_cn="吉大港"),
        Port(un_locode="MYPKG", name_en="Port Kelang", name_cn="巴生港"),
        Port(un_locode="TWTXG", name_en="Taichung", name_cn="台中"),
        Port(un_locode="USSTL", name_en="St. Louis", name_cn="圣路易斯"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_resolve_variant_ports(db):
    cases = {
        "PUSAN": "KRPUS",
        "KAOHSIUNG CITY": "TWKHH",
        "KATTUPALLI PORT": "INKTP",
        "CHITTAGONG": "BDCGP",
        "PORT KLANG": "MYPKG",
        "TAICHUNG CITY": "TWTXG",
        "SAINT LOUIS": "USSTL",
    }
    for raw, expected in cases.items():
        port = _resolve_port(db, raw)
        assert port is not None, f"{raw} 应解析到港"
        assert port.un_locode == expected, f"{raw} → {port.un_locode}, 期望 {expected}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_resolve_port_aliases.py -q`
Expected: FAIL（PUSAN/KAOHSIUNG CITY/SAINT LOUIS 等当前解析不到 → AssertionError）。

- [ ] **Step 3: 加 import**

在 `backend/app/services/step1_rates/activator_mappers.py` 顶部 import 区加：

```python
from app.services.step1_rates.port_normalizer import canonicalize
```

- [ ] **Step 4: 在 `_resolve_port` 末步加 canonicalize 兜底**

找到 `_resolve_port` 结尾的双语拆分块 + `return None`，替换为（在 `return None` 前插入兜底）：

```python
    # 双语合并名 "English/中文"(如 KMTC 的 "Shanghai/上海"、"Busan/釜山")：整串匹配不到时
    # 按分隔符拆段，逐段递归再试，命中任一即可。拆出的段不含分隔符，递归只下探一层。
    parts = [p.strip() for p in re.split(r"[/／|]", name) if p.strip()]
    if len(parts) > 1:
        for part in parts:
            hit = _resolve_port(db, part)
            if hit is not None:
                return hit
    # 规范化兜底：别名(PUSAN→BUSAN)/去尾缀(CITY/PORT)/去标点折叠后，对 alnum 折叠的 name_en 做包含匹配。
    # 解决 "PUSAN"/"KAOHSIUNG CITY"/"SAINT LOUIS"(对 "St. Louis" 的句点) 等变体。
    canon = canonicalize(name)
    if len(canon) >= 3:
        folded = func.replace(
            func.replace(func.replace(Port.name_en, " ", ""), ".", ""), "-", ""
        )
        port = db.query(Port).filter(folded.ilike(f"%{canon}%")).first()
        if port is not None:
            return port
    return None
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_resolve_port_aliases.py -q`
Expected: 1 passed（7 个变体全解析到）。

- [ ] **Step 6: 回归 step1_rates 测试**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/ -q`
Expected: 全 PASS（兜底是最后一步，不改既有命中行为）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/step1_rates/activator_mappers.py backend/tests/services/step1_rates/test_resolve_port_aliases.py
git commit -m "feat(step1): _resolve_port 末步加 canonicalize 兜底, 救回别名/变体港(PUSAN/KAOHSIUNG CITY/SAINT LOUIS 等)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 补字典（Phase 2）

**Files:**
- Modify: `scripts/seed_data.py`（`PORTS` 列表，约 :205-217 组合港之后）
- Test: `backend/tests/services/step1_rates/test_seed_new_ports.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/services/step1_rates/test_seed_new_ports.py`：

```python
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.services.step1_rates.activator_mappers import _resolve_port


def _load_seed():
    # scripts/ 不是 python 包，动态加载(同 admin.py 套路)
    p = Path(__file__).resolve().parents[4] / "scripts" / "seed_data.py"
    spec = importlib.util.spec_from_file_location("seed_data", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_new_ports_seeded_and_resolvable():
    import app.models  # noqa: F401
    mod = _load_seed()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    mod.seed_ports(s)
    for nm in ["Cochin", "Colombo", "Kolkata", "Mangalore", "Pipavav",
               "Naha", "Shekou", "Hilo", "Philadelphia", "Durban"]:
        assert _resolve_port(s, nm) is not None, f"{nm} 应在补充后可解析"
    s.close()
    engine.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_seed_new_ports.py -q`
Expected: FAIL（Cochin 等未 seed → _resolve_port 返回 None → AssertionError）。

- [ ] **Step 3: 追加 PORTS**

在 `scripts/seed_data.py` 的 `PORTS` 列表**末尾 `]` 之前**（现有组合港块之后）追加：

```python
    # === 2026-06 ONE 合约覆盖缺口补充（locode 为 demo 临时值, 解析按 name 匹配）===
    # 起运港（南亚/东亚/非洲）
    ("INCOK", "Cochin", "科钦", "India", "South Asia"),
    ("LKCMB", "Colombo", "科伦坡", "Sri Lanka", "South Asia"),
    ("INCCU", "Kolkata", "加尔各答", "India", "South Asia"),
    ("INNML", "Mangalore", "芒格洛尔", "India", "South Asia"),
    ("INPAV", "Pipavav", "皮帕瓦沃", "India", "South Asia"),
    ("PKBQM", "Muhammad Bin Qasim", "卡西姆港", "Pakistan", "South Asia"),
    ("TWTYN", "Taoyuan", "桃园", "Taiwan", "East Asia"),
    ("CNSHK", "Shekou", "蛇口", "China", "East Asia"),
    ("JPNAH", "Naha", "那霸", "Japan", "East Asia"),
    ("JPTYM", "Toyama Shinko", "富山新港", "Japan", "East Asia"),
    ("MZBEW", "Beira", "贝拉", "Mozambique", "East Africa"),
    ("ZACPT", "Cape Town", "开普敦", "South Africa", "Southern Africa"),
    ("ZACOE", "Coega", "科加", "South Africa", "Southern Africa"),
    ("ZADUR", "Durban", "德班", "South Africa", "Southern Africa"),
    ("MZMPM", "Maputo", "马普托", "Mozambique", "East Africa"),
    ("NAWVB", "Walvis Bay", "鲸湾港", "Namibia", "Southern Africa"),
    # 目的港（美国/夏威夷）
    ("USITO", "Hilo", "希洛", "USA", "North America"),
    ("USOGG", "Kahului", "卡胡卢伊", "USA", "North America"),
    ("USKWH", "Kawaihae", "卡瓦伊哈埃", "USA", "North America"),
    ("USLIH", "Nawiliwili", "纳威利威利", "USA", "North America"),
    ("USHVY", "Harvey", "哈维", "USA", "North America"),
    ("USPHL", "Philadelphia", "费城", "USA", "North America"),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_seed_new_ports.py -q`
Expected: 1 passed。

- [ ] **Step 5: 确认 seed 脚本仍可跑（语法/无重复 locode）**

Run: `cd /Users/zhangdongxu/Desktop/project/阪急阪神 && .venv/bin/python -c "import importlib.util,pathlib; p=pathlib.Path('scripts/seed_data.py'); s=importlib.util.spec_from_file_location('sd',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); locs=[r[0] for r in m.PORTS]; assert len(locs)==len(set(locs)), '有重复 locode: '+str([x for x in locs if locs.count(x)>1]); print('PORTS', len(locs), 'unique OK')"`
Expected: 打印 `PORTS <N> unique OK`（无重复 locode）。

- [ ] **Step 6: 提交**

```bash
git add scripts/seed_data.py backend/tests/services/step1_rates/test_seed_new_ports.py
git commit -m "feat(step1): 补字典 22 港(ONE合约覆盖缺口:南亚/非洲/夏威夷等), reseed 自动覆盖

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: sea 多港拆 N 行（Phase 3）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`（加 `expand_multi_port_sea`；`add_file` 调用，约 :139-144）
- Test: `backend/tests/sheet_builder/test_orchestrator.py`（增）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/sheet_builder/test_orchestrator.py` 末尾追加：

```python
def test_expand_multi_port_sea_splits_locode_pair():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.base import Base
    from app.models.port import Port
    from app.services.step1_rates.sheet_builder.orchestrator import expand_multi_port_sea
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="USLAX", name_en="Los Angeles", name_cn="洛杉矶"),
        Port(un_locode="USLGB", name_en="Long Beach", name_cn="长滩"),
    ])
    s.commit()

    rows = [{"destination": "USLAX USLGB", "container_20gp": 100}]
    out = expand_multi_port_sea(rows, s)
    assert len(out) == 2
    assert {r["destination"] for r in out} == {"USLAX", "USLGB"}
    assert all(r["container_20gp"] == 100 for r in out)

    # 单港多词名不拆：'LOS'/'ANGELES' 非 5 位 locode → 保持整体
    rows2 = [{"destination": "LOS ANGELES", "container_20gp": 100}]
    out2 = expand_multi_port_sea(rows2, s)
    assert len(out2) == 1 and out2[0]["destination"] == "LOS ANGELES"
    s.close()
    engine.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py::test_expand_multi_port_sea_splits_locode_pair -q`
Expected: FAIL（ImportError: expand_multi_port_sea）。

- [ ] **Step 3: 加 `expand_multi_port_sea` 函数**

在 `orchestrator.py` 的 `_normalize_sea` 函数**之后**新增：

```python
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
```

- [ ] **Step 4: `add_file` 对 sea 调用**

在 `add_file` 里找到归一段（约 :139-144）：

```python
    carrier_fallback = parsed.get("carrier_code", "") or ""
    normalized = [
        _normalize(session.template_type, r, carrier_fallback) for r in raw_rows
    ]
    session.rows.extend(normalized)
    _mark_needs_review(session.rows)
```

替换为：

```python
    carrier_fallback = parsed.get("carrier_code", "") or ""
    normalized = [
        _normalize(session.template_type, r, carrier_fallback) for r in raw_rows
    ]
    # sea 多港格(如 'USLAX USLGB')拆成多行(同价)，审核台展示拆开后的行
    if session.template_type == "sea" and db is not None:
        normalized = expand_multi_port_sea(normalized, db)
    session.rows.extend(normalized)
    _mark_needs_review(session.rows)
```

- [ ] **Step 5: 跑测试确认通过 + orchestrator 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -q`
Expected: 全 PASS（含新测试；既有用例 destination 非 locode 对，不被拆，行为不变）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): sea 多港格(USLAX USLGB)拆成多行入库, 仅多 UN/LOCODE 才拆

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: air 区域多港拆 N 行（Phase 4）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/air_ees.py`（`_clean_dest` :219-223；调用循环 :135-166）
- Test: `backend/tests/sheet_builder/test_air_ees.py`（增）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/sheet_builder/test_air_ees.py` 末尾追加：

```python
def test_clean_dest_returns_all_codes():
    from app.services.step1_rates.sheet_builder.air_ees import _clean_dest
    assert _clean_dest("KIX") == ["KIX"]                       # 单港
    assert _clean_dest("NH-DFW") == ["DFW"]                    # 去航司前缀
    assert _clean_dest("CK/MU-LAX") == ["LAX"]                 # 去多段航司前缀
    assert _clean_dest("美国西部：SEA LAX SFO") == ["SEA", "LAX", "SFO"]  # 区域多港
    assert _clean_dest("MEX,MTY,CUN") == ["MEX", "MTY", "CUN"]  # 逗号多港
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_air_ees.py::test_clean_dest_returns_all_codes -q`
Expected: FAIL（现 `_clean_dest` 返回 str/None，非 list）。

- [ ] **Step 3: 改 `_clean_dest` 返回全部码**

把 `air_ees.py` 的 `_clean_dest`（:219-223）：

```python
def _clean_dest(raw: str) -> str | None:
    """目的港单元格 → 机场三字码：先去航司前缀(NH- / CK/MU-)，再取首个三字码。"""
    s = _AIRLINE_PREFIX.sub("", raw.strip())
    m = _IATA.search(s)
    return m.group(0) if m else None
```

替换为：

```python
def _clean_dest(raw: str) -> list[str]:
    """目的港单元格 → 机场三字码列表：先去航司前缀(NH- / CK/MU-)，再取全部三字码。
    单港→1 个码；区域/多港格(SEA LAX SFO / MEX,MTY,CUN)→多个码(下游每码发一行)。"""
    s = _AIRLINE_PREFIX.sub("", raw.strip())
    return _IATA.findall(s)
```

- [ ] **Step 4: 调用循环改成每码发一行**

在 `air_ees.py` 抽取循环里改三处。其一，`current_dest` 初值（:135）：

```python
    current_dest: str | None = None
```
→
```python
    current_dest: list[str] = []
```

其二，dest 赋值块（:145-149）：

```python
        raw_dest = _clean(row[cmap["dest"]]) if cmap["dest"] < len(row) else None
        if raw_dest:
            code = _clean_dest(raw_dest)
            if code:
                current_dest = code
```
→
```python
        raw_dest = _clean(row[cmap["dest"]]) if cmap["dest"] < len(row) else None
        if raw_dest:
            codes = _clean_dest(raw_dest)
            if codes:
                current_dest = codes
```

其三，守卫 + append（:152-166）：

```python
        tier_prices = _row_tier_prices(row, cmap["tiers"])
        if current_dest is None or not tier_prices:
            continue

        out.append(
            {
                "destination_port_name": current_dest,
                "service_desc": _row_service(row, cmap),
                # 稀疏档位 dict(KG 升序)：有哪档数字存哪档，取代单价×7天。
                "tier_prices": tier_prices,
                "remarks": _EES_FUEL_NOTE,  # 含油说明进备注(档位表「备注」列)
                "multi_flight_pick": True,  # 同港多条 → 交审核台人工选一条
                "source_file": source_file,
                "effective_week_start": effective,  # 文件名报价日 → 下游改写表头/sheet 名
            }
        )
```
→
```python
        tier_prices = _row_tier_prices(row, cmap["tiers"])
        if not current_dest or not tier_prices:
            continue

        for dest in current_dest:  # 区域多港:每个码各发一行(同价)
            out.append(
                {
                    "destination_port_name": dest,
                    "service_desc": _row_service(row, cmap),
                    # 稀疏档位 dict(KG 升序)：有哪档数字存哪档，取代单价×7天。
                    "tier_prices": tier_prices,
                    "remarks": _EES_FUEL_NOTE,  # 含油说明进备注(档位表「备注」列)
                    "multi_flight_pick": True,  # 同港多条 → 交审核台人工选一条
                    "source_file": source_file,
                    "effective_week_start": effective,  # 文件名报价日 → 下游改写表头/sheet 名
                }
            )
```

- [ ] **Step 5: 跑测试确认通过 + air_ees 回归（重点看既有用例）**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_air_ees.py -q`
Expected: 全 PASS。既有单港用例(KIX/BKK/AMS…)产 1 行不变；`_tier_dicts(rows,"MEX")` 类断言仍命中（拆分后 MEX 行仍在）。**若有断言因区域格现产多行而失败，更新该断言以匹配新的多行结果**（区域格目的港由「只首码」变为「全部码各一行」）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/air_ees.py backend/tests/sheet_builder/test_air_ees.py
git commit -m "feat(step1): air_ees 区域多港格(SEA LAX SFO)拆成多行, _clean_dest 取全部三字码

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 全量验证（诊断回归 + pytest + seed）

**Files:** 无（验证）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全 PASS（基线 365 passed + 本轮新增；仅 3 个 `test_ai_client` vLLM 环境失败为既有无关项）。

- [ ] **Step 2: 重灌本地字典（让新港进 DB，诊断脚本才查得到）**

> 诊断脚本用本地 `hankyu_hanshin.db` 解析港。新港需先 seed 进去。
Run: `cd /Users/zhangdongxu/Desktop/project/阪急阪神 && .venv/bin/python scripts/seed_data.py`
Expected: 港口新增若干条（不报错；已存在的跳过）。

- [ ] **Step 3: 重跑诊断脚本看未匹配下降（核心成功指标）**

Run: `cd backend && PYTHONPATH=. nohup ../.venv/bin/python /tmp/a4_skip_diag.py > /tmp/portfix_diag.out 2>&1 & ` 然后等 `DONE`：
`until grep -qE "DONE|Traceback" /tmp/portfix_diag.out; do sleep 3; done; cat /tmp/portfix_diag.out`
Expected: `未匹配 unresolved` 从 3997 **大幅下降到接近 0**（起运港/目的港未匹配数显著减少；剩余应仅极少数真·非港文本）。记录前后对比数字。

- [ ] **Step 4: 手测端到端（前后端在 :8000/:5173）**

1. Sea 做表上传 ONE 合约 PDF → 提示「未匹配」数显著下降、入库行数显著上升；审核台能看到 `USLAX USLGB` 拆成两行。
2. Air 做表上传 EES → 区域格目的港（如美国西部）变成多行（SEA/LAX/SFO 各一行）。

- [ ] **Step 5: 记录结果回报用户**

把诊断前后对比（unresolved 3997 → X）+ pytest 结果 + 手测结论回报。NG 则定位回对应 Task。

---

## Self-Review（写完已自检）

- **Spec 覆盖**：Phase1 别名归一(Task1+2)、Phase2 补字典(Task3)、Phase3 sea 拆分(Task4)、Phase4 air 拆分(Task5)、成功标准诊断回归(Task6)——spec 各节均有任务。spec 提的 `rate_parser._resolve_port` 与 `air_weight_break` 已在头部「范围微调」显式 defer/排除并说明理由。
- **占位符**：无 TBD/TODO；每个改码步骤含完整代码与确切命令。
- **类型一致**：`canonicalize`(Task1)→activator_mappers 调用(Task2) 一致；`_clean_dest` 返回 `list[str]`(Task5 Step3) 与调用处 `current_dest: list[str]`、`for dest in current_dest`(Step4) 一致；`expand_multi_port_sea(rows, db)` 签名(Task4 Step3)与 add_file 调用(Step4)一致。
- **风险点**：Task5 改 `_clean_dest` 返回类型可能动到既有 air_ees 断言 → 已在 Step5 显式要求跑全量并按需更新断言（区域格行为变化）。诊断脚本依赖本地 DB 有新港 → Task6 Step2 先 reseed。
