# Step2 T-B5 — RateMatcher 架构任务单

- **版本**：v1.0（2026-04-23）
- **作者**：架构大师
- **拆分依据**：
  - 业务需求：`docs/Step2_入札对应_业务需求_20260422.md` §3.5（费率检索）+ §4.1-4.4（Step1 接口、Air 周表 7 列、币种、上海发地）
  - 总架构任务单：`docs/Step2_入札対応_Customer_A_架构任务单_20260422.md` §7（RateMatcher）+ §10（Q1-Q7 默认值）+ §11.1（查不到的回填规则）
- **本任务单单独面向开发大师 + 测试大师**；Step2 总架构任务单 §7 是骨架，本文是落地拆分。
- **强制约束**：
  - 不写实际函数体（只给签名 + 注释级别伪步骤）
  - 不引入新依赖（仅用既有 `sqlalchemy / decimal / dataclasses`）
  - T-B2 Alembic 迁移仍延后，本任务全程走 in-memory（`Step1RateRepository` + sqlite），与 T-B3 测试同模式
  - **凡 file:line 必须真实存在**，监工可抽查

---

## 0. 上下文复盘（开发大师必读 30 秒）

- T-B5 上游 = `Step1RateRepository`（`backend/app/services/step2_bidding/rate_repository.py:28`），已交付 `query_air_weekly` / `query_air_surcharges`
- T-B5 下游 = T-B6 `MarkupApplier`（cost→sell）+ T-B7 `CustomerAProfile.fill`（写回 Excel）。本任务**只输出 cost_price 与候选**，不做加价、不做写文件
- T-B5 输入素材 = `CustomerAProfile.parse` 产出的 `ParsedPkg`（`backend/app/services/step2_bidding/entities.py:76-86`）中的每条 `PkgRow`
- T-B5 不依赖 T-B2（无新建数据表），完全在内存与既有 Step1 物理表上运算

---

## 1. 输入 / 输出契约

### 1.1 模块在 service.py 编排里的位置（来自总架构任务单 §2 第 164 行）

```
[Step 2.2 解析] CustomerAProfile.parse → ParsedPkg
       │
       ▼
[Step 2.3 检索] for row in parsed.rows:
                    status, candidates = RateMatcher(repo).match(row, effective_on=...)
                → 收集为 list[(PkgRow, RowStatus, list[QuoteCandidate])]
       │
       ▼
[Step 2.4 加价 + 写表] T-B6 MarkupApplier + T-B7 CustomerAProfile.fill
```

### 1.2 输入

| 名称 | 类型 | 说明 |
|---|---|---|
| `row` | `PkgRow` (`entities.py:55-73`) | 解析结果中单条航线 |
| `effective_on` | `datetime.date`（关键字参数） | 周表生效判定基准日。service 层默认 = period 月份第 15 日（任务单 §10 Q5/Q7 默认） |
| `carrier_preference` | `list[str] \| None` | 客户硬约束航司白名单（v1.0 Customer A PKG 未提供，恒为 None；保留接口 v2.0 Customer E 用） |
| `max_candidates` | `int` (默认 5) | 排序后截断数量 |

### 1.3 输出

返回 `tuple[RowStatus, list[QuoteCandidate]]`：

- `RowStatus` 枚举值已在 `entities.py:31-39` 定义，全部 8 个 case 都会被本模块用到（`FILLED / NO_RATE / ALREADY_FILLED / EXAMPLE / NON_LOCAL_LEG / LOCAL_DELIVERY_MANUAL / CONSTRAINT_BLOCK / OVERRIDDEN（OVERRIDDEN 不由 matcher 写）`）
- `QuoteCandidate` 字段定义在 `entities.py:88-107`；本模块负责填全所有字段（`source_*`、`step1_must_go`、`step1_case_by_case`、`match_score`、`cost_price`、`base_price_day_index` 等）
- 当 status ∈ {NON_LOCAL_LEG, EXAMPLE, ALREADY_FILLED, LOCAL_DELIVERY_MANUAL, NO_RATE, CONSTRAINT_BLOCK} → candidates 必为 `[]`

---

## 2. 文件级改动清单

| 路径 | 行号提示 | 新建/修改 | 做什么 |
|---|---|---|---|
| `backend/app/services/step2_bidding/rate_matcher.py` | 全文（约 230 行） | **新建** | T-B5 唯一新增源文件 |
| `backend/app/services/step2_bidding/__init__.py` | 在 19 行后追加 `from .rate_matcher import RateMatcher`；并在 `__all__`（21-34 行）补 `"RateMatcher"` | 修改 | 暴露公共入口 |
| `backend/app/services/step2_bidding/entities.py` | 第 88-107 行 `QuoteCandidate` | **不修改** | 字段已齐 |
| `backend/app/services/step2_bidding/protocols.py` | 第 50-66 行 | **不修改** | T-B3 已提供 `query_air_weekly` / `query_air_surcharges` 两个方法，T-B5 只用这两个 |
| `backend/app/services/step2_bidding/rate_repository.py` | 第 113-171 行 `_weekly_to_step1_row` / `_surcharge_to_step1_row` | **修改（小改，详见 §3.1）** | 把 must_go / case_by_case / airline_codes / all_fees_dash 这些 Step1 解析时 extras 字段，转成 Step1RateRow.extras 透传给 Matcher（**当前 extras 只有 step2_record_id+step2_batch_status**，Matcher 必需的 must_go 等字段无法获取）|
| `backend/tests/services/step2_bidding/test_rate_matcher.py` | 全文（约 250 行） | **新建** | 见 §6 |

**禁止改动**：
- `backend/app/services/step1_rates/**`
- `backend/app/models/{air_freight_rate,air_surcharge,import_batch}.py`
- `backend/alembic/versions/20260421_0001_step1_rate_models.py`

---

## 3. 上游补丁（rate_repository.py 局部）

### 3.1 为什么要改 `_weekly_to_step1_row` / `_surcharge_to_step1_row`

**事实**（grep 已核）：
- `air_freight_rates` 表（`backend/app/models/air_freight_rate.py:24-47`）**没有** `extras / airline_codes / has_must_go` 这些列；只有单列 `airline_code`，Step1 air adapter 第 238 行又把它存为 `None`（用 `service_desc` 文本 + parse 时的 `extras["airline_codes"]` 替代）
- 因此 Step1 入库时，`has_must_go / is_case_by_case / airline_codes` 都**没有持久化**到 DB
- 而总架构任务单 §7.2 step b/c 要求 Matcher 从 candidate 中取 airline_codes、must_go、case_by_case；step c 还要按 surcharge 的 `all_fees_dash` 过滤

**结论**：Matcher 必须在**仓储层即时从原始字段重算**这些派生标记，否则 §7.2 算法无法落地。

**改动范围**（仅 `_weekly_to_step1_row` 与 `_surcharge_to_step1_row` 的 extras dict，**不动 SQL、不动表结构**）：

- `_weekly_to_step1_row`（`rate_repository.py:113-143`）`extras` 字典追加：
  - `"airline_codes": _extract_airline_codes_from_service_desc(rate.service_desc)`（重用 `app.services.step1_rates.adapters.air.AirAdapter._extract_airline_codes` 的同款正则 / 或在 rate_matcher 模块内放一份本地小函数；**首选后者，避免跨服务导入私有方法**）
  - `"has_must_go": "must go" in (rate.remark or "").lower()`
  - `"is_case_by_case": "case by case" in (rate.remark or "").lower()`
- `_surcharge_to_step1_row`（`rate_repository.py:145-171`）extras 已有 myc/msc/area/destination_scope；只追加：
  - `"all_fees_dash": _all_fees_dash(sur.myc_min, sur.myc_fee_per_kg, sur.msc_min, sur.msc_fee_per_kg)`（`all(v is None for v in [...])` 的本地小工具）

> **替代方案讨论**：把派生计算放在 `rate_matcher.py` 自己内部（不动 repository）。**不采纳**，因为 (a) extras 是 repository 的天然出口；(b) 多客户/多 matcher 复用时不必重复实现；(c) 改动 5 行内，监工可一眼看清。

---

## 4. rate_matcher.py 接口骨架（不写函数体）

```python
# backend/app/services/step2_bidding/rate_matcher.py
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.services.step1_rates.entities import Step1RateRow
from app.services.step2_bidding.entities import (
    PkgRow, QuoteCandidate, RowStatus, CostType,
)
from app.services.step2_bidding.protocols import RateRepository


# -------- 模块级常量（楢崎 P0 答复后只改这里）--------
_LOCAL_SECTION_CODES: frozenset[str] = frozenset({"PVG"})    # 见业务需求 §4.4
_DEFAULT_MAX_CANDIDATES = 5
_SCORE_DEST_EXACT = 0.4
_SCORE_CURRENCY_MATCH = 0.2
_SCORE_VALIDITY_COVER = 0.2
_SCORE_CARRIER_PREF = 0.1
_SCORE_NO_CONSTRAINT = 0.1
_CASE_BY_CASE_DAMP = 0.5     # case_by_case 候选 match_score × 0.5（任务单 §7.4）

class RateMatcher:
    """单航线 → 候选费率列表。无副作用，无状态。

    使用方式：
        matcher = RateMatcher(repo)
        status, candidates = matcher.match(row, effective_on=some_date)
    """

    def __init__(self, repo: RateRepository) -> None: ...

    def match(
        self,
        row: PkgRow,
        *,
        effective_on: date,
        carrier_preference: list[str] | None = None,
        max_candidates: int = _DEFAULT_MAX_CANDIDATES,
    ) -> tuple[RowStatus, list[QuoteCandidate]]: ...

    # ---- 内部辅助（私有）----
    def _build_candidate(
        self,
        weekly_row: Step1RateRow,
        airline_code: str,
        surcharge_row: Step1RateRow | None,
        effective_on: date,
        carrier_preference: list[str] | None,
    ) -> QuoteCandidate | None: ...

    @staticmethod
    def _pick_price_by_etd(
        weekly_row: Step1RateRow, effective_on: date
    ) -> tuple[Decimal | None, int | None]:
        """返回 (price, day_index_1to7)；全 None 时 (None, None)。"""
        ...

    @staticmethod
    def _calc_score(
        *,
        dest_exact: bool,
        currency_match: bool,
        validity_cover: bool,
        in_carrier_pref: bool,
        no_constraint: bool,
        case_by_case: bool,
    ) -> float: ...
```

> 与 `entities.py:88-107` 字段一一对照：开发大师在 `_build_candidate` 中**必须写满**所有非 Optional 字段；`source_surcharge_record_id` 在无 surcharge 命中时填 `None`。

---

## 5. 核心算法分步（按 §7.2 落地，逐条对应业务需求）

> **整体语义**：matcher 是**纯函数 + IO 仓储**；不写 DB、不写文件、不调 AI；同一 row 多次 match 结果应一致。

### 5.1 预过滤（短路返回）

按以下顺序判断（任一命中即 return，candidates=[]）：

1. `not row.section_code in _LOCAL_SECTION_CODES` → `(NON_LOCAL_LEG, [])`
   - 业务依据：业务需求 §4.4 + 总任务单 §7.2 step 1
2. `row.is_example` → `(EXAMPLE, [])`
3. `row.cost_type == CostType.LOCAL_DELIVERY` → `(LOCAL_DELIVERY_MANUAL, [])`
   - 业务依据：业务需求 §3.6 规则 3；任务单 §11.1 表
4. `row.existing_price is not None and row.existing_price != Decimal("0")` → `(ALREADY_FILLED, [])`
   - 业务依据：业务需求 §3.4 规则 3 + 任务单 §10 Q7 默认值
5. `row.destination_code == "UNKNOWN"` → `(NO_RATE, [])`
   - 任务单 §7.2 step 1 末行

### 5.2 调仓储查周表

```
weekly_rows = repo.query_air_weekly(
    origin=row.origin_code,            # 'PVG' (因为 §5.1 已过滤了非 PVG)
    destination=row.destination_code,
    effective_on=effective_on,
    currency=row.currency,
    airline_code_in=None,
)
if not weekly_rows: return (NO_RATE, [])
```

> **币种边界**：`query_air_weekly` 在 `rate_repository.py:65-66` 已支持 currency 过滤。若 `row.currency != "CNY"`（业务需求 §4.3 提到 PVG 段固定 CNY，但 5 段中其他段非 CNY；§5.1 已经过滤掉了非 PVG，所以 v1.0 实务上这里恒 currency='CNY'）。**Q4 的"换汇"问题在 v1.0 不实现**：行 currency 与 Step1 入库 currency 不一致 → 自动 NO_RATE（依任务单 §10 Q4 默认）。

### 5.3 对每条 weekly_row 展开候选

对 `weekly_rows` 每一条：

a. **取价**：`price, day_index = _pick_price_by_etd(weekly_row, effective_on)`；price 为 None → 跳过（不计入候选）

b. **取航司列表**：`airline_codes = weekly_row.extras.get("airline_codes", [])`（依赖 §3.1 上游补丁）
   - 若空（service_desc 没解析出航司）→ 仍生成 1 个候选，airline_code 记 `""`，surcharge_record_id=None，**myc/msc 均按 0 处理**，并 `match_score -= 0.1` 保守降权（见 §5.5）。这种情况业务需求 §3.5 规则 5 要求"标记需购买部门询价"，但 status 仍 FILLED（以保留候选给营业人工处理）

c. **每个 airline_code 查 surcharge**（任务单 §7.2 step c）：
   ```
   surcharges = repo.query_air_surcharges(airline_code=ac, effective_on=effective_on, currency=row.currency)
   surcharge = next((s for s in surcharges if not s.extras["all_fees_dash"]), None)
   ```
   - 若 surcharge.extras["all_fees_dash"] 全为 True → 跳过该航司不产生候选（`all_fees_dash=True` 表示该航司当期 4 项费率全是 "—"，无法报价）
   - 若 `surcharges == []` → 仍产生候选；`myc_applied=False, msc_applied=False, myc_fee_per_kg=None, msc_fee_per_kg=None`

d. **计算 cost_price**：
   ```
   cost_price = price
              + (surcharge.extras["myc_fee_per_kg"] if myc_applied else Decimal("0"))
              + (surcharge.extras["msc_fee_per_kg"] if msc_applied else Decimal("0"))
   ```
   - `myc_applied = surcharge is not None and surcharge.extras["myc_fee_per_kg"] not in (None, Decimal("0"))`
   - `msc_applied = surcharge is not None and surcharge.extras["msc_fee_per_kg"] not in (None, Decimal("0"))`

e. **填 must_go / case_by_case**（透传，不做静默过滤）：
   ```
   step1_must_go = bool(weekly_row.extras.get("has_must_go"))
   step1_case_by_case = bool(weekly_row.extras.get("is_case_by_case"))
   remarks_from_step1 = "\n".join(filter(None, [weekly_row.remarks, surcharge.remarks if surcharge else None]))
   ```

### 5.4 客户航司硬约束过滤（§7.2 step 4）

- v1.0 Customer A PKG **未提供** `carrier_preference`（解析侧没填该字段），所以入参恒 None；本步保留接口
- 当 `carrier_preference is not None` 且**所有候选** airline_code 都不在 preference 中 → `(CONSTRAINT_BLOCK, [])`

### 5.5 match_score（任务单 §7.2 step e）

加权求和（最大 1.0）：
- +0.4 目的地精确匹配（`weekly_row.destination_port_name` 含 row.destination_code，已 LIKE 命中即视为精确）
- +0.2 币种匹配（`weekly_row.currency == row.currency`；§5.2 已 SQL 过滤，恒为 True，但函数内仍判断以便 v2.0 放开）
- +0.2 有效期完整覆盖（`effective_on` 落在 `[effective_week_start, effective_week_end]`，SQL 已过滤恒 True）
- +0.1 航司在 `carrier_preference` 中（preference=None 视为不计 +0）
- +0.1 无 must_go && 无 case_by_case
- 若 `step1_case_by_case == True` → 最终 score × 0.5（任务单 §7.4）

### 5.6 排序 + 截断（§7.2 step 5）

```
candidates.sort(key=lambda c: (c.cost_price, -c.match_score))
candidates = candidates[:max_candidates]
return (FILLED, candidates)
```

> **Q9 默认**：最低 cost_price 优先；同价时 match_score 高的在前（任务单 §10 Q9 默认值）

---

## 6. 错误处理 / 边界条件

| 场景 | 行为 | 依据 |
|---|---|---|
| 上游 row 缺关键字段（如 origin_code = ""） | 走 §5.1 step 5 → NO_RATE，不抛异常 | 业务需求 §3.5 规则 5 |
| `query_air_weekly` 返回 0 条 | NO_RATE | §5.2 |
| weekly_row 7 天 price 全 None | 该 weekly_row 不产生候选；最终列表为空 → NO_RATE | §5.3 a |
| weekly_row 含航司但 surcharges 全 all_fees_dash | 该航司不产生候选；其它航司仍可 | §5.3 c |
| weekly_row 无 airline_codes（service_desc 无 IATA） | 1 个 airline=""候选，myc/msc=0，score 降 0.1 | §5.3 b |
| 同 cost_price 多条 | 不去重；按 (price, -score) 排序后全部返回（截 max_candidates） | §5.6 |
| `Step1RateRow.currency` 与 row.currency 不一致 | SQL 已过滤；不会出现。但代码侧仍以 §5.2 currency 参数兜底 | 任务单 §10 Q4 默认 |
| `carrier_preference` 为空列表 `[]` vs None | `[]` = 客户明确"不接受任何航司" → CONSTRAINT_BLOCK；`None` = 客户未指定，全放行 | 总任务单 §7.2 step 4 |
| `effective_on` 是周末/超出所有批次 | SQL 自然返回 0 → NO_RATE | 业务需求 §3.5 规则 5 |
| Step1 入库的 `weekly_row.extras` 字典缺键（如老数据） | 用 `extras.get("...")` 默认 None / [] 兜底，不抛 KeyError | §3.1 给上游打了补丁，新数据保证有；旧数据兜底 |

---

## 7. 测试用例点位（交测试大师独立验证）

测试文件 `backend/tests/services/step2_bidding/test_rate_matcher.py`，沿用 T-B3 的 sqlite in-memory + 真实 model 模式（参见 `test_rate_repository.py:30-50`）。共 **10 条单测**：

| ID | 名称 | 输入构造 | 期望 | 覆盖 |
|---|---|---|---|---|
| V-B5-01 | non_local_leg | row.section_code='NRT' | (NON_LOCAL_LEG, []) | §5.1-1 |
| V-B5-02 | example_row | row.is_example=True | (EXAMPLE, []) | §5.1-2 |
| V-B5-03 | local_delivery | row.cost_type=LOCAL_DELIVERY | (LOCAL_DELIVERY_MANUAL, []) | §5.1-3 |
| V-B5-04 | already_filled | row.existing_price=Decimal('100') | (ALREADY_FILLED, []) | §5.1-4 |
| V-B5-05 | unknown_destination | row.destination_code='UNKNOWN' | (NO_RATE, []) | §5.1-5 |
| V-B5-06 | happy_path_with_surcharge | 入库 1 条 PVG→ATL 周表（service_desc='OZ direct'），1 条 OZ surcharge（myc=2.0, msc=1.0）；row currency=CNY | (FILLED, [c]) where c.cost_price=base+2+1, airline='OZ', source_*非空 | §5.2-5.3 全流程 |
| V-B5-07 | no_surcharge_match | 入库周表 service_desc='CK direct'，但 surcharge 表无 CK 行 | (FILLED, [c]) c.myc_applied=False, c.msc_applied=False, cost_price=base | §5.3-c 兜底 |
| V-B5-08 | all_fees_dash_skip | 入库 surcharge 4 项均 None（all_fees_dash=True） | 该航司不产生候选；若仅一航司则 NO_RATE | §5.3-c 跳过 |
| V-B5-09 | carrier_preference_block | weekly 仅 OZ 候选，传 carrier_preference=['NH'] | (CONSTRAINT_BLOCK, []) | §5.4 |
| V-B5-10 | sort_and_truncate | 入库 3 条不同价（45/50/40），max_candidates=2 | candidates=[40, 45]，长度=2，第 0 条 cost_price=40 | §5.6 |

**附加 1 条集成回归**（建议）：
| V-B5-11 | superseded_batch_ignored | 入库 active 批次价 100、superseded 批次价 50 | candidates 仅含 100（不应取 superseded） | repository 联动验证 |

> **不写**：UI / API / Markup / fill 相关测试（不在本任务范围）。
> **测试 fixture 复用**：`db_session`、`_make_batch` 直接抄 `test_rate_repository.py:30-100`，不要新造。

---

## 8. 数据流（5 行说清）

```
PkgRow ─(§5.1 5 道预过滤)──► 早退 RowStatus
   │ (通过)
   ▼
repo.query_air_weekly(origin=PVG, dest, etd, currency)──► weekly_rows
   │ for each weekly_row:
   ▼
_pick_price_by_etd → price_dayN ; weekly_row.extras['airline_codes'] for ac:
   repo.query_air_surcharges(ac, etd) → surcharge → 过滤 all_fees_dash
   ▼
QuoteCandidate(cost_price = price + myc + msc, score=...)  →  排序  →  截断  →  (FILLED, candidates)
```

---

## 9. 依赖 / 阻塞

### 9.1 内部依赖

| 依赖 | 来源 | 状态 |
|---|---|---|
| `Step1RateRepository.query_air_weekly` | `rate_repository.py:36-71` | **已就绪**（T-B3） |
| `Step1RateRepository.query_air_surcharges` | `rate_repository.py:75-99` | **已就绪**（T-B3） |
| `PkgRow / QuoteCandidate / RowStatus` | `entities.py:31,55,88` | **已就绪**（T-B1） |
| `RateRepository` Protocol | `protocols.py:43-66` | **已就绪**（T-B1） |
| extras 中 `must_go / case_by_case / airline_codes / all_fees_dash` 透传 | `rate_repository.py:113-171`（§3.1） | **本任务内附带补丁**（5 行修改） |

### 9.2 不阻塞的事项

- **T-B2（bidding_requests / bidding_row_reports 表）已推迟**：T-B5 输入是 `PkgRow` 数据类（内存），输出是 `tuple[RowStatus, list[QuoteCandidate]]`（内存），全程不落库，不依赖 T-B2
- **T-B6 MarkupApplier**：T-B5 仅产出 cost_price，不调 markup；T-B5 完成后 T-B6 可独立开发
- **T-B7 fill**：T-B5 不写 Excel
- **T-B8 CustomerIdentifier**：T-B5 收到的 row 已有 customer_code 上下文，无需识别

### 9.3 阻塞 / 半阻塞 — 楢崎 P0 问题

| 编号 | 问题 | 当前默认（代码常量位置） | 阻塞？ |
|---|---|---|---|
| Q3（业务需求 §7） | 成本→销售加价规则 | **不阻塞 T-B5**（T-B5 只算 cost）；阻塞 T-B6 | 否 |
| Q5 | Air 周表 7 日价取哪一日 | `_pick_price_by_etd`：按 effective_on 落在 (week_start..week_end) 的 day offset+1 取对应 price_dayN；该 day 为 None 时退化"周内非 None 平均"；全 None 跳过该 weekly_row | **半阻塞**：v1.0 可上线，但楢崎答复后必须改函数体；本文档已在审核界面提示 |
| Q4 | 币种换汇 | 不换汇；currency 不一致 → NO_RATE | **半阻塞**：Customer A 5 段非 CNY 段 v1.0 全部 NO_RATE，业务可接受（业务需求 §4.4 + 任务单 §10 Q4） |
| Q7 | 入札期间跨周 | service.py 默认 `effective_on = date(year, month, 15)`；T-B5 接收时已固定，无需关心 | 否（在 service.py 那一层） |
| Q9 | 同航线多候选排序 | (cost_price asc, match_score desc) | 否（已默认） |
| A-Q2 | 非 PVG 段币种 / 客户期望物量是否进检索 | v1.0 不进；§5.1 直接 NON_LOCAL_LEG | 否 |

### 9.4 监工警示

- §3.1 修改了 `_weekly_to_step1_row` / `_surcharge_to_step1_row` 的 extras。**测试大师必须重跑 T-B3 测试**（`test_rate_repository.py`）确认未破坏既有断言；如有断言"extras 仅含 step2_record_id+step2_batch_status"则需配合放宽

---

## 10. 预估人天

| 角色 | 工时 | 内容 |
|---|---|---|
| 开发大师（实现） | **1.0 人天** | rate_matcher.py 新建 230 行 + repository extras 补丁 5 行 + __init__.py 1 行 |
| 测试大师（独立验证） | **0.5 人天** | 11 条单测、复用 T-B3 fixture |
| **合计** | **1.5 人天** | 可在 1.5 工作日内交付完成 |

---

## 11. 验收 Checklist（监工抽查）

- [ ] `backend/app/services/step2_bidding/rate_matcher.py` 新增；定义 `class RateMatcher` 含 `match` + 3 个私有方法
- [ ] `__init__.py` 第 19/21 行追加 RateMatcher 导出
- [ ] `rate_repository.py:113-171` extras 增加 4 个键（`airline_codes / has_must_go / is_case_by_case / all_fees_dash`）
- [ ] 11 条 pytest 单测全过（`pytest backend/tests/services/step2_bidding/test_rate_matcher.py -v`）
- [ ] `pytest backend/tests/services/step2_bidding/test_rate_repository.py -v` 仍全过（无回归）
- [ ] 本文件 §3.1 改动**不动**任何 SQL / 表结构（grep 验证：`alembic/versions/` 无新增、`models/air_*.py` 无 diff）
- [ ] 不引入新依赖：`backend/requirements.txt` 无 diff

---

## 12. 监工汇报小结

**拆出子任务数**：1 个新文件 + 1 个上游小补丁 + 1 个测试文件 = **3 件改动**，开发可 1 天内完成。

**需楢崎拍板（不阻塞 T-B5 落地，但影响精确度）**：
- Q5 周表 7 日价取值粒度（默认按 ETD day_index）
- Q9 多候选排序（默认 cost_price asc）
- Q4 币种换汇（默认不换）

**不阻塞**：Q3 加价规则归 T-B6；Q7 ETD 默认归 service.py（T-B9）。

**建议**：直接交开发大师按本文档实施。**不需要回业务大师补需求**——业务需求 §3.5 + §4 已覆盖 T-B5 全部规则，剩余 P0 问题已用任务单 §10 默认值兜底，常量化后楢崎答复时只改一行。

