# Step2 T-B7 — Customer A fill 双版本回写 架构任务单

- **版本**：v1.0（2026-04-23）
- **作者**：架构大师
- **拆分依据**：
  - 业务需求：`docs/Step2_入札対応_T-B7_customer_a_fill_业务需求_20260423.md`（§0 黄金样本实测 / §需求 4 决策表 / §需求 5 原格式硬约束 / §需求 7 V1-V7 验收）
  - 总架构任务单：`docs/Step2_入札対応_Customer_A_架构任务单_20260422.md` §6.4（fill 算法 L564-L577）、§8.1（markup 常量 L669-L684）、§8.2（H 列 ALL-in L686-L690）、§11.1-11.2（回填规则 + 两版差异表 L823-L843）、§16.3（V-B19/V-B22 验收）
  - 同类粒度参考：`docs/Step2_入札対応_T-B5_RateMatcher_架构任务单_20260423.md`、`docs/Step2_入札対応_T-B8_customer_identifier_架构任务单_20260423.md`
  - Step1 writer 保真参照：`backend/app/services/step1_rates/writers/base.py:15-48`（`is_formula_cell` / `safe_set`）、`writers/air.py:30`（`load_workbook(path, data_only=False)`）、`writers/base.py:71-82`（`stamp_document_properties`）
- **本任务单单独面向开发大师 + 测试大师**。总架构任务单 §6.4 是骨架（14 行伪代码），本文件是落地拆分。
- **强制约束**：
  - 不写实际函数体（只给签名 + 注释级别伪步骤 + 决策表）
  - 不引入新依赖（仅用既有 `openpyxl / shutil / decimal / dataclasses / datetime`）；**禁止** `pandas`（业务需求 §需求 5 风险 5 + CLAUDE.md）
  - markup 系数**禁止写死在 T-B7 内部**（业务需求 §9.2 风险 2）；必须通过依赖注入的 `markup_fn` 协议接入，T-B6 未到时由 service 层传入 `fixed_markup(ratio=Decimal("1.15"))` 兜底
  - **禁止**动 非 PVG 段任何单元格（业务需求 §需求 5 规则 1-12；§需求 7 V4）
  - **禁止**动 PVG 段 LOCAL_DELIVERY 行（R14 / R17）任何单元格（业务需求 §需求 4 LOCAL_DELIVERY_MANUAL 分支；§需求 7 V5）
  - 凡 file:line 必须真实存在，监工可抽查

---

## 0. 上下文复盘（开发大师必读 60 秒）

- T-B7 上游 = T-B5 `RateMatcher.match(...)` 返回 `(RowStatus, list[QuoteCandidate])`，由 service 层（T-B9 待建）汇总为 `list[PerRowReport]`（`entities.py:111-127`），每条与 `ParsedPkg.rows` 的 `row_idx` 一一对应
- T-B7 下游 = T-B10 API `GET /api/v1/bidding/{bid_id}/download?variant=cost|sr`（待建），**T-B7 仅保证两份物理文件存在、路径可记录进 `FillReport.cost_file_path / sr_file_path`**（`entities.py:138-139`）
- T-B7 输入素材：
  1. 源 xlsx 文件（客户原上传、未动过的模板），`Path` 类型
  2. `ParsedPkg`（含 sections + rows；T-B4 产出，`entities.py:76-86`）
  3. `list[PerRowReport]`（T-B5 + 加价后产出，已按 row_idx 对齐 rows）
  4. `markup_fn: Callable[[Decimal], Decimal]`（cost→sell 的纯函数；可由 service 层传入 `lambda c: ceil_int(c * Decimal("1.15"))`）
- T-B7 产出：
  1. 两个独立 .xlsx 文件，路径由 service 层预先生成并作为参数传入
  2. 一份 `FillReport`（本轮由 T-B7 构造并返回；service 层可进一步扩展字段）
- 当前状态：`customer_a.py:125-136` 占位 `NotImplementedError`；`CustomerProfile` 协议（`protocols.py:32-39`）已定义 `fill(source_path, parsed, row_reports, variant, output_path) -> None` 签名。**本任务不改协议签名**；markup_fn 由 service 层构造 `lambda` / `functools.partial` 提前绑好，以字段方式暂存在 `CustomerAProfile` 实例上（见 §3.2）。

---

## 1. 任务范围（in / out）

### 1.1 in（v1.0 必做）

- 实现 `CustomerAProfile.fill(source_path, parsed, row_reports, variant, output_path)`（`customer_a.py:125-136`）真实逻辑，支持 `variant in {"cost", "sr"}`
- 实现一个 Customer A 专用的**原格式回填**流程：`shutil.copy2` → `openpyxl.load_workbook(data_only=False)` → 仅对 PVG 段 5 条 AIR_FREIGHT 行写入 E/F/G/H → `stamp_document_properties` → `wb.save`
- 实现 markup 依赖注入机制：`CustomerAProfile.__init__(markup_fn)` 接收 `Callable[[Decimal], Decimal]`；未传时默认使用本文件定义的 `default_markup_fn`（内部常量 `_DEFAULT_MARKUP_RATIO = Decimal("1.15")` + `_ceil_int`）
- 产出 `FillReport`（见 §3.3）
- 新增 T-B7 专用帮助器：`_pvg_rowset(parsed)`（找 PVG 段的所有 row_idx 集合）、`_targets_for_status(status, variant, report, row)`（返回 (E,F,G,H) 四元组，None 表示不写）
- 新增一个**复用** `step1_rates/writers/base.py:safe_set / is_formula_cell` 的引用（直接 import，不复刻）
- v1.0 文件命名规范（业务需求 §需求 6）：cost 版 = `cost_<原文件名>.xlsx`；S/R 版 = `sr_<原文件名>.xlsx`；由 service 层（T-B9）生成 `output_path` 参数，T-B7 不在 fill 内部拼文件名（**职责单一**：T-B7 负责写内容，service 负责定路径）

### 1.2 out（v1.0 不做，且不留 stub）

- **不**打开源 xlsx 重新解析业务字段（已由 T-B4 完成；业务需求 §需求 3 边界）
- **不**再调 `RateRepository` / `RateMatcher`（已由上游完成）
- **不**处理 `RowStatus.OVERRIDDEN`（审核页 T-B10 才交付；业务需求 §需求 4 边界）
- **不**在 H 列追加 `client_constraint_text`（**仅** CONSTRAINT_BLOCK 状态下的 H 列才写 constraint；FILLED 状态下 H 列只写 `'ALL-in'`，业务需求 §需求 4 边界 + §9.3 Q-T-B7-02）
- **不**做加价策略（cost→sell 交给注入的 markup_fn；业务需求 §9.2）
- **不**做邮件发送（§需求 1 边界）
- **不**做审核页前端 UI
- **不**做 VBA 保真（Customer A 黄金样本无宏；业务需求 §需求 5 边界）
- **不**做二次改价回写（T-B10 PATCH 场景）
- **不**做 zip 打包下载
- **不**为 Customer B / E / Nitori fill 逻辑留 stub（它们不在 v1.0 范围）
- **不**并发多线程写文件（两版串行；性能不是 v1.0 目标）

### 1.3 与 T-B9 service 编排的边界

service 层（待建）负责：
- 构造 `markup_fn`（读配置 / 接 T-B6 `MarkupApplier.apply`；本轮临时用 `lambda c: _ceil_int(c * Decimal("1.15"))`）
- 把 `(RowStatus, list[QuoteCandidate])` 翻译成 `PerRowReport`（填好 cost_price / sell_price / lead_time_text / carrier_text / remark_text / constraint_hits；**sell_price 是否在 service 层提前算好、或延迟到 T-B7 里由 markup_fn 算**，选后者（见 §3.2 决定 1））
- 生成两个 `output_path`（含目录隔离：按 `bid_id` 分目录，业务需求 §需求 6 边界兜底）
- 调 `profile.fill(..., variant="cost", output_path=...)` 一次，再调 `variant="sr"` 一次（**二次调用** / 见 §3.2 决定 2）
- 汇总两次产出的 `FillReport`，把 `cost_file_path / sr_file_path` 合并进单一 `FillReport` 交下游

T-B7 只管单次调用内的事：**一次 fill 调用产一个文件**。

---

## 2. 文件级改动清单

| 路径 | 行号提示 | 新建/修改 | 做什么 |
|---|---|---|---|
| `backend/app/services/step2_bidding/customer_profiles/customer_a.py` | 第 1-18 行 imports 追加 `shutil` + `Callable` + `datetime` + `functools` + Step1 writers.base 的 `safe_set, is_formula_cell, stamp_document_properties`；第 85-91 行 `class CustomerAProfile` 追加 `__init__(self, markup_fn=None)`；**替换** 第 123-136 行 `fill` 占位为 40-60 行实现 + 新增 5 个私有 helper（约 120 行）；新增 3 个模块级常量（`_DEFAULT_MARKUP_RATIO = Decimal("1.15")` / `_SR_FIXED_REMARK = "ALL-in"` / `_T_B7_WRITER_VERSION = "step2-customer_a-fill-0.1.0"`） | 修改 | T-B7 唯一改动的业务源文件 |
| `backend/app/services/step2_bidding/customer_profiles/customer_a.py` | 模块末尾追加 `def default_markup_fn(cost: Decimal) -> Decimal: ...` + `def _ceil_int(value: Decimal) -> Decimal: ...` | 修改 | 默认加价兜底（T-B6 未到时 service 层或测试可直接用） |
| `backend/app/services/step2_bidding/__init__.py` | 第 21 行附近追加 `from .customer_profiles.customer_a import CustomerAProfile, default_markup_fn`（若尚未导出）；`__all__` 追加 `"CustomerAProfile"`, `"default_markup_fn"` | 修改 | 暴露 fill 能力给 service 层与测试 |
| `backend/tests/services/step2_bidding/test_customer_a_fill.py` | 全文（预估 350-450 行） | **新建** | §7 7 条验收用例 + 3 条 diff 辅助工具内部测试 |
| `backend/tests/services/step2_bidding/fixtures/fill/fixtures.py`（或 conftest.py 内置 fixture） | 新建（约 80 行） | **新建** | mock PerRowReport 构造器 / 黄金样本路径常量 / 跨段 diff 辅助 |

**禁止改动**：
- `backend/app/services/step2_bidding/entities.py`（`FillReport` / `PerRowReport` / `PkgRow` 字段已够用，不新增字段）
- `backend/app/services/step2_bidding/protocols.py`（`CustomerProfile.fill` 签名已定）
- `backend/app/services/step2_bidding/rate_matcher.py`（与 T-B7 无关）
- `backend/app/services/step2_bidding/rate_repository.py`（与 T-B7 无关）
- `backend/app/services/step1_rates/**`（严禁回流修改）
- `backend/app/models/**`、`backend/alembic/versions/**`（T-B7 不落库）

---

## 3. 接口契约

### 3.1 模块在 service.py 编排里的位置

```
[Step 2.2 解析]  CustomerAProfile.parse            → ParsedPkg
       │
[Step 2.3 检索]  for row: RateMatcher.match(row)   → list[(row, status, candidates)]
       │
[Step 2.4 加价]  for (row, status, candidates):   ← v1.0 由 service 挑第 0 条候选
                   PerRowReport(cost_price, sell_price=markup_fn(cost_price), ...)
       │
[Step 2.5 写表]  profile.fill(src, parsed, reports, variant="cost", out=P_cost)  ← T-B7
                 profile.fill(src, parsed, reports, variant="sr",   out=P_sr)     ← T-B7
       │
[Step 2.6 返回]  FillReport(cost_file_path=P_cost, sr_file_path=P_sr, ...)
```

### 3.2 CustomerAProfile 最终签名

```python
# backend/app/services/step2_bidding/customer_profiles/customer_a.py
class CustomerAProfile:
    customer_code = "customer_a"
    display_name = "ミマキエンジニアリング"
    priority = 100

    def __init__(self, markup_fn: Callable[[Decimal], Decimal] | None = None) -> None:
        """
        markup_fn: cost(Decimal) → sell(Decimal) 的纯函数；不传则默认用 default_markup_fn。
        业务规则：markup_fn 只在 variant=='sr' 时使用；variant=='cost' 永远写 cost_price 原值。
        """

    def detect(self, path: Path, hint: str | None = None) -> bool: ...      # T-B4 已有
    def parse(self, path: Path, bid_id: str, period: str) -> ParsedPkg: ...  # T-B4 已有

    def fill(
        self,
        source_path: Path,
        parsed: ParsedPkg,
        row_reports: list[PerRowReport],
        variant: str,                     # "cost" | "sr"；其它值抛 ValueError
        output_path: Path,
    ) -> FillReport:
        """
        一次调用产一个 xlsx 文件。
        返回的 FillReport 只填本次 variant 对应的 *_file_path；另一版由 service 层合并。
        """
```

**关键决定（逐条说明**，对应业务大师问题清单问题 1 / 2 / 6）：

1. **markup_fn 注入位置**：构造函数入参。**理由**：`CustomerProfile.fill` 签名（`protocols.py:32-39`）不能改（Protocol 一改就破 T-B4/T-B5/T-B8 已落地契约），因此 markup_fn 不能做 fill 的位置参数；改为构造函数字段是侵入最小的方案。service 层在创建 profile 实例时注入：
   ```python
   profile = CustomerAProfile(markup_fn=lambda c: _ceil_int(c * Decimal("1.15")))
   ```
   T-B6 交付后 service 改成：
   ```python
   markup = MarkupApplier(ratio=..., ceiling="ceil_int")
   profile = CustomerAProfile(markup_fn=lambda c: markup.apply(c, currency="CNY"))
   ```
   **T-B7 自身零改动**即可接入 T-B6。

2. **两文件产出机制**：**二次调用 fill**。业务需求 §需求 6 规则 4 禁止合并文件。service 层编排：
   ```python
   report_cost = profile.fill(src, parsed, reports, variant="cost", output_path=p_cost)
   report_sr   = profile.fill(src, parsed, reports, variant="sr",   output_path=p_sr)
   merged = FillReport(
       bid_id=..., generated_at=...,
       row_reports=report_cost.row_reports,   # 两次 row_reports 结构一致，取一即可
       filled_count=report_cost.filled_count,
       no_rate_count=report_cost.no_rate_count,
       skipped_count=report_cost.skipped_count,
       cost_file_path=str(p_cost),
       sr_file_path=str(p_sr),
       global_warnings=[*report_cost.global_warnings, *report_sr.global_warnings],
   )
   ```
   **T-B7 不在 fill 内部触发第二次写**——保持 "一次 fill 管一个 variant" 的单一职责。

3. **output_path 由 service 层提供**：业务需求 §需求 6 规则 1 文件名（`cost_` / `sr_` 前缀）→ 由 T-B9 service 构造。T-B7 只接受完整 `Path` 参数、做 `shutil.copy2(src, output_path)` 后继续。**这符合现有 `protocols.py:32-39` 签名**，无需改协议。

4. **sell_price 在哪一步算**：**延迟到 T-B7 内部，通过 `markup_fn(cost_price)` 计算**（不依赖 `PerRowReport.sell_price` 字段）。**理由**：若 service 层提前算好并写进 `PerRowReport.sell_price`，则需要每次都算；且 T-B6 策略一变，service 层也要改一次调用。让 T-B7 调 markup_fn 一次到位、T-B6 交付后仅 service 层替换 markup_fn 函数体，T-B7 零改动。**PerRowReport.sell_price 字段在 v1.0 视为可选信息字段，T-B7 不读取**（仅写入 FillReport 时记录为 "本次 fill 实际写入的 sr 价"）。

### 3.3 FillReport 填写规则（T-B7 范围内的字段）

`FillReport` 定义：`entities.py:131-140`。T-B7 单次 fill 调用返回的 FillReport 按以下规则填：

| 字段 | v1.0 填写策略 |
|---|---|
| `bid_id` | = `parsed.bid_id` |
| `generated_at` | = `datetime.utcnow()` |
| `row_reports` | = 入参 `row_reports` 的浅拷贝（不改内容；保留原 status 供审核页显示） |
| `filled_count` | = `sum(1 for r in reports if r.status == RowStatus.FILLED)` |
| `no_rate_count` | = `sum(1 for r in reports if r.status == RowStatus.NO_RATE)` |
| `skipped_count` | = `len(reports) - filled_count - no_rate_count`（即除 FILLED/NO_RATE 之外的所有其它 status 合计） |
| `cost_file_path` | variant=="cost" 时填 `str(output_path)`，否则空字符串 |
| `sr_file_path` | variant=="sr" 时填 `str(output_path)`，否则空字符串 |
| `global_warnings` | T-B7 自身产出的警告（例如"PVG 行 client_constraint_text 非空但未合并到 H 列"——见业务需求 §9.3）；与 row_reports 内部的 validator_warnings 不重复 |

> service 层合并两次 FillReport 的策略见 §3.2 决定 2。

---

## 4. 数据流（7 步说清）

```
源 xlsx (source_path)                              (禁写)
     │
     │ shutil.copy2(source_path, output_path)      → output_path 创建为源文件精确副本
     ▼
output_path                                        (以下所有操作都作用于副本，永不触 source)
     │
     │ wb = load_workbook(output_path, data_only=False, keep_vba=False)
     │ ws = wb["見積りシート"]                       ← 业务需求 §需求 5 规则 12
     ▼
pvg_row_idx_set = _pvg_rowset(parsed)              ← 仅该集合中的 row_idx 允许被写
     │
     ▼
for report in row_reports:                         ← 按 row_reports 的顺序遍历
    row = _find_row_by_idx(parsed, report.row_idx) ← 取对应 PkgRow；找不到 → 警告并跳过
    if row.row_idx not in pvg_row_idx_set:
        continue                                   ← 非 PVG 段一律跳过（NON_LOCAL_LEG 防御）
    (e, f, g, h) = _targets_for_status(
        status=report.status,
        variant=variant,
        report=report,
        row=row,
        markup_fn=self._markup_fn,
    )                                              ← 决策表（§5）返回 4 个目标值；None = 不写
    for (col, value) in [(E,e), (F,f), (G,g), (H,h)]:
        if value is _SENTINEL_KEEP:                ← 保持原值 → 彻底不碰 cell
            continue
        safe_set(ws.cell(row.row_idx, col), value) ← 公式 cell 自动跳过（来自 Step1 writers.base）
     │
     ▼
stamp_document_properties(wb, batch_id=f"{parsed.bid_id}:{variant}")
                                                    ← 复用 Step1 writer；title/subject/description 追加
wb.save(output_path); wb.close()
     │
     ▼
return FillReport(...)                             ← 按 §3.3 字段规则构造
```

> 关键：**变量 `_SENTINEL_KEEP` 是 T-B7 内部定义的哨兵对象**（`_SENTINEL_KEEP = object()`），与 `None`（= safe_set 跳过，保留原值）语义一致但更显式，方便读懂"故意不碰"。实际实现时 `None` 足够，但建议用 `_SENTINEL_KEEP` 提升可读性。

---

## 5. 核心算法 — RowStatus × variant 决策表（8 × 4）

**设计意图**：把业务需求 §需求 4 的业务决策表翻译成单一 Python 函数 `_targets_for_status(...)`，一次查表即可得到 (E, F, G, H) 四个目标值。减少 if/else 嵌套分支。

### 5.1 决策表语义约定

- `KEEP` = 不写该格，保留 2-①.xlsx 原值（通过 `None` 传给 safe_set 或直接 `continue`；下面用 `KEEP` 表示哨兵）
- `""`（空字符串）= 显式清空（仅 NO_RATE 某些格需要）
- `cost` = `report.cost_price`（Decimal）
- `sr` = `markup_fn(report.cost_price)`（Decimal；`markup_fn` = self._markup_fn）
- `lead` = `report.lead_time_text`
- `carrier` = `report.carrier_text`
- `ALL-in` = 模块常量 `_SR_FIXED_REMARK`
- `constraint` = `report.remark_text or "; ".join(report.constraint_hits)`（CONSTRAINT_BLOCK 时 service 层应已把原约束文本拷到 `remark_text`；T-B7 兜底用 constraint_hits）

### 5.2 完整决策表（开发大师照此实现 `_targets_for_status`）

| RowStatus | variant | E（col 5） | F（col 6） | G（col 7） | H（col 8） |
|---|---|---|---|---|---|
| FILLED | cost | cost | lead | carrier | KEEP（模板 H 原本就空 → 保持；§0.2 实测） |
| FILLED | sr | sr | lead | carrier | `"ALL-in"` |
| NO_RATE | cost | `""` | `""` | `""` | KEEP |
| NO_RATE | sr | `""` | `""` | `""` | KEEP |
| CONSTRAINT_BLOCK | cost | `""` | `""` | `""` | constraint |
| CONSTRAINT_BLOCK | sr | `""` | `""` | `""` | constraint |
| NON_LOCAL_LEG | cost/sr | KEEP | KEEP | KEEP | KEEP |
| EXAMPLE | cost/sr | KEEP | KEEP | KEEP | KEEP |
| LOCAL_DELIVERY_MANUAL | cost/sr | KEEP | KEEP | KEEP | KEEP |
| ALREADY_FILLED | cost/sr | KEEP | KEEP | KEEP | KEEP |
| OVERRIDDEN | cost/sr | **v1.0 不支持**，抛 `NotImplementedError` 或降级为 FILLED（本轮选后者：按 FILLED 对待）|

**特别说明**：
- 业务需求 §需求 4 要求 LOCAL_DELIVERY_MANUAL 在 PVG 段内（R14 / R17）严格零改动。`_targets_for_status` 的 `LOCAL_DELIVERY_MANUAL` 行返回 `(KEEP, KEEP, KEEP, KEEP)`，主循环的 `safe_set` 看到 None（KEEP）即 return False 不写。**双保险**：(a) 决策表返回 KEEP；(b) `_pvg_rowset` 仅含 PVG 段所有 row_idx（包括 R14/R17），但 status 为 LOCAL_DELIVERY_MANUAL 时决策表已经 KEEP；即便未来 status 被误标，只要 cost_type==LOCAL_DELIVERY，建议在 `_targets_for_status` 入口做一次断言：`if row.cost_type == CostType.LOCAL_DELIVERY: return KEEP_ALL`。
- NO_RATE：E/F/G 写 `""` 而非 None 的原因 —— 若未来营业人审核时手动清空 cell，Excel 会显示空；此处显式写空串保证"营业看到明显是留白待处理"。`safe_set` 对 `""` 会当作有效值写入（见 `writers/base.py:38-41`：value is None 才跳过）。
- CONSTRAINT_BLOCK H 列写 constraint（业务需求 §需求 4 + §需求 7 V7）；两版一致（cost/sr 都写约束原文，不写 ALL-in）。
- OVERRIDDEN 本轮按 FILLED 分支处理，不抛异常（避免 Demo 前万一 T-B10 回写了这个 status 导致整包失败）。

### 5.3 伪代码骨架（不写函数体）

```python
# 模块级
_SR_FIXED_REMARK = "ALL-in"
_DEFAULT_MARKUP_RATIO = Decimal("1.15")
_T_B7_WRITER_VERSION = "step2-customer_a-fill-0.1.0"
_SENTINEL_KEEP = object()                        # 语义：保留 2-①.xlsx 原值

_ALL_KEEP = (_SENTINEL_KEEP,) * 4

def default_markup_fn(cost: Decimal) -> Decimal:
    return _ceil_int(cost * _DEFAULT_MARKUP_RATIO)

def _ceil_int(value: Decimal) -> Decimal:
    # 向上取整到整数；业务需求 §需求 7 V1 期望 45×1.15→52（即 ceil）
    ...

class CustomerAProfile:
    def __init__(self, markup_fn: Callable[[Decimal], Decimal] | None = None) -> None:
        self._markup_fn = markup_fn or default_markup_fn
        # parse / detect 所需的无状态字段 —— 继续用模块级常量

    def fill(self, source_path, parsed, row_reports, variant, output_path) -> FillReport:
        if variant not in ("cost", "sr"):
            raise ValueError(f"variant 必须为 cost / sr；实际：{variant!r}")
        shutil.copy2(source_path, output_path)
        wb = load_workbook(output_path, data_only=False, keep_vba=False)
        try:
            if _SHEET_NAME not in wb.sheetnames:
                raise ValueError(f"Sheet {_SHEET_NAME!r} 缺失，无法回写")
            ws = wb[_SHEET_NAME]
            pvg_rows = self._pvg_rowset(parsed)        # set[int]
            row_by_idx = {r.row_idx: r for r in parsed.rows}
            global_warnings: list[str] = []

            for report in row_reports:
                row = row_by_idx.get(report.row_idx)
                if row is None:
                    global_warnings.append(
                        f"row_reports 中 row_idx={report.row_idx} 在 parsed.rows 中不存在"
                    )
                    continue
                if report.row_idx not in pvg_rows:
                    # NON_LOCAL_LEG 防御；即便 status 误标也不写
                    continue
                targets = self._targets_for_status(
                    status=report.status,
                    variant=variant,
                    report=report,
                    row=row,
                )
                for col_idx, value in zip(
                    (_COL_PRICE, _COL_LEAD_TIME, _COL_CARRIER, _COL_REMARK), targets
                ):
                    if value is _SENTINEL_KEEP:
                        continue
                    safe_set(ws.cell(row.row_idx, col_idx), value)

                # PVG 行若 client_constraint_text 非空 FILLED-sr → warning（业务需求 §9.3）
                if (
                    report.status == RowStatus.FILLED
                    and variant == "sr"
                    and row.client_constraint_text
                ):
                    global_warnings.append(
                        f"R{row.row_idx} 有客户约束文本 {row.client_constraint_text!r}，"
                        f"v1.0 未并入 H 列 'ALL-in'；审核页请人工处理"
                    )

            stamp_document_properties(
                wb, batch_id=f"{parsed.bid_id}:{variant}"
            )
            wb.save(output_path)
        finally:
            wb.close()

        return self._build_fill_report(
            parsed=parsed, row_reports=row_reports, variant=variant,
            output_path=output_path, warnings=global_warnings,
        )

    # ---------- helpers ----------
    def _pvg_rowset(self, parsed: ParsedPkg) -> set[int]: ...
        # 返回 is_local_section=True 段下所有 row.row_idx
    def _targets_for_status(self, *, status, variant, report, row) -> tuple: ...
        # 返回 (E, F, G, H)；每格要么 _SENTINEL_KEEP 要么具体值
    def _build_fill_report(self, *, parsed, row_reports, variant, output_path, warnings) -> FillReport: ...
```

---

## 6. 原格式保真技术方案（引用 Step1 writer 经验）

### 6.1 保真 7 条（逐条对应业务需求 §需求 5 的 12 条硬约束）

| # | 保真项 | 实现手段 | 依据 |
|---|---|---|---|
| 1 | 非 PVG 段所有单元格零改动 | `_pvg_rowset` + 主循环 `if not in pvg_rows: continue`；**不 open 其它 sheet、不遍历其它 row** | 业务需求 §需求 5 规则 1 |
| 2 | 字体 / 颜色 / 边框 / 对齐 | `openpyxl.load_workbook(..., data_only=False)` 默认保留 cell.style | 业务需求 §需求 5 规则 6 |
| 3 | 合并单元格 | `load_workbook` 默认保留 `ws.merged_cells`；**T-B7 禁止调 `ws.unmerge_cells` / `ws.merge_cells`** | 业务需求 §需求 5 规则 7 |
| 4 | 列宽 / 行高 | `load_workbook` 默认保留 `ws.column_dimensions` / `ws.row_dimensions`；T-B7 不修改 | 业务需求 §需求 5 规则 8 |
| 5 | 公式 | `safe_set(cell, value)` 内部 `is_formula_cell` 守卫（`writers/base.py:15-20` 已落地），公式 cell 拒写 | 业务需求 §需求 5 规则 9 |
| 6 | 批注 | `load_workbook` 默认保留 `cell.comment`；T-B7 不触碰非 PVG cell → 批注自然保留 | 业务需求 §需求 5 规则 10 |
| 7 | Document Properties | `stamp_document_properties`（`writers/base.py:71-82`）**追加** title / subject / description；不清除已有字段（openpyxl `props.creator` / `keywords` 等未被覆盖） | 业务需求 §需求 5 规则 11 |
| 8 | Sheet 名 & 不增 Sheet | T-B7 仅用 `wb["見積りシート"]`，不新增 Sheet；`wb.save` 默认保留 sheet 结构 | 业务需求 §需求 5 规则 12 |

### 6.2 复用而非复刻：从 Step1 writers 直接 import

```python
from app.services.step1_rates.writers.base import (
    is_formula_cell,
    safe_set,
    stamp_document_properties,
)
```

**理由**：
- `safe_set` 的两条语义（None 跳过 / 公式拒写）完全适配 T-B7 决策表；已在 Step1 TD-2 25 条 pytest 下通过
- `stamp_document_properties` 的 title/subject/description 三字段设计，T-B7 仅需把 `batch_id` 参数改为 `f"{bid_id}:{variant}"` 即可
- **禁止**在 T-B7 内复刻同功能代码（避免两套"公式守卫"实现漂移）

### 6.3 openpyxl 不保真的边界（业务需求 §需求 5 边界 + §9.5 风险 5）

| 项 | 保真情况 | v1.0 策略 |
|---|---|---|
| 冻结窗格 | openpyxl 默认保留 | 代码不触碰；测试用 openpyxl 读出 `ws.freeze_panes` 做二次比对（V-fixture-03） |
| 条件格式 | openpyxl 对部分条件格式有保留问题，但 Customer A 黄金样本无条件格式 | 不特殊处理；测试前用 openpyxl 检查原文件 `ws.conditional_formatting` 是否为空，非空则升 P0 |
| 数据验证 | openpyxl 默认保留 | 不特殊处理；边界测试抽检 |
| 超链接 | openpyxl 默认保留 | 不特殊处理；黄金样本无超链接 |
| 图片 | openpyxl 有风险 | Customer A 黄金样本无图片；测试 V-fixture-04 确认 |
| VBA 宏 | **不保真** | Customer A 无宏；`keep_vba=False` 明示 |

---

## 7. 子任务拆分（开发大师按此顺序实施，每项 0.5-1 人日）

| ID | 标题 | 内容 | 预估 | 依赖 |
|---|---|---|---|---|
| **T-B7a** | 骨架 + markup 注入 | 在 `customer_a.py` 新增 3 个模块级常量 + `__init__(markup_fn)` + `default_markup_fn` + `_ceil_int`；单元测试 1 条（markup fn 默认值 `Decimal(45)` → `Decimal(52)`） | 0.25 人日 | 无 |
| **T-B7b** | 决策表 helper | 实现 `_targets_for_status` + `_pvg_rowset`；**纯函数**，无文件 IO；单元测试 9 条（8 × variant 的 17 个决策表格全覆盖） | 0.5 人日 | T-B7a |
| **T-B7c** | fill 主循环 + 保真 | 实现 `fill(...)` 主体：shutil.copy2 / load_workbook / 主 for / stamp / save；`_build_fill_report` | 0.5 人日 | T-B7b；依赖 Step1 writers.base 已就绪（已入库） |
| **T-B7d** | 双版本集成 | 一次 fixture 调两次 fill（cost + sr）→ 验收 V1/V2/V3（黄金样本数值对齐） | 0.25 人日 | T-B7c |
| **T-B7e** | 原格式保真集成 | 跨段 diff 工具 `assert_non_pvg_cells_identical(src, out)`；验收 V4/V5；openpyxl 侧 merged_cells / 列宽 / freeze_panes 二次核验 | 0.5 人日 | T-B7c；交测试大师 |
| **T-B7f** | 边界验收 | V6（全 NO_RATE）、V7（部分 FILLED + CONSTRAINT_BLOCK） | 0.25 人日 | T-B7d / T-B7e |
| **T-B7g** | `__init__.py` 导出 + 文档 | 暴露 `CustomerAProfile` + `default_markup_fn` | 0.1 人日 | T-B7c |

**合计**：开发 1.5 人日 + 测试 0.5 人日 = **2.0 人日**。可在 2 工作日内交付完成。

---

## 8. 测试辅助工具（给测试大师）

测试文件 `backend/tests/services/step2_bidding/test_customer_a_fill.py`；pytest fixture 建议放 `conftest.py` 或 `fixtures/fill/fixtures.py`。

### 8.1 fixture 构造器（建议放 conftest.py）

```python
# 参数化工厂：按 (row_idx, status, cost_price, lead, carrier, remark) 一次造 PerRowReport
@pytest.fixture
def make_report():
    def _make(
        row_idx: int,
        status: RowStatus = RowStatus.FILLED,
        cost_price: Decimal | None = None,
        lead_time_text: str | None = None,
        carrier_text: str | None = None,
        remark_text: str | None = None,
        constraint_hits: list[str] | None = None,
    ) -> PerRowReport:
        ...
    return _make

# 黄金样本路径；测试不得直接打开 2-② / 2-④，只能当期望对照
@pytest.fixture
def golden_blank_path() -> Path:
    return Path("资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx")

@pytest.fixture
def parsed_pkg(golden_blank_path) -> ParsedPkg:
    return CustomerAProfile().parse(golden_blank_path, bid_id="bid_test", period="2026-01")

@pytest.fixture
def pvg_reports_happy(parsed_pkg, make_report) -> list[PerRowReport]:
    # 5 条 AIR_FREIGHT FILLED + 2 条 LOCAL_DELIVERY_MANUAL（R14/R17）
    # + 非 PVG 段 rows 全部 NON_LOCAL_LEG
    ...
```

### 8.2 diff 辅助函数（测试大师必写；核心 pytest 断言工具）

```python
# tests/services/step2_bidding/fixtures/fill/diff.py
from openpyxl import load_workbook

def cells_identical(src_path: Path, out_path: Path, *, sheet: str, cell_coords: Iterable[tuple[int, int]]) -> list[str]:
    """返回 mismatches list；空 list = 全部一致。"""
    # 比较 value、number_format、font、fill、alignment、border、comment

def assert_non_pvg_cells_identical(src: Path, out: Path, *, parsed: ParsedPkg) -> None:
    """
    业务需求 §需求 7 V4 / V5 的核心断言：
    - 对 ws 的每个 cell（row 1..max_row, col 1..max_col）：
      - 若 row 在 PVG 段 AIR_FREIGHT 行的 E/F/G/H → 跳过
      - 其它 cell → assert value & style 一致
    - 失败时打印首个不一致 cell 的 (row, col, src_value, out_value)
    """

def assert_merged_cells_identical(src: Path, out: Path, *, sheet: str) -> None: ...
def assert_column_dimensions_identical(src: Path, out: Path, *, sheet: str) -> None: ...
def assert_sheet_name_preserved(out: Path) -> None: ...  # ws.title == '見積りシート'
```

> **非 PVG 段零改动如何在 pytest 里断言**：`assert_non_pvg_cells_identical` 遍历源文件每个 cell，建立 (row,col) → value+style 的快照，然后对产出文件做同样遍历，排除 PVG 段 `AIR_FREIGHT 行的 5×4=20` 个白名单单元格，其它全部等值校验。**这是 V4 / V5 的唯一自动化保证**。

### 8.3 7 条 pytest 验收用例（与业务需求 §需求 7 一一映射）

| ID | 名称 | 输入构造 | 期望 | 覆盖 |
|---|---|---|---|---|
| V-B7-01 | double_variant_diff | 5 条 FILLED，cost = [45,50,38,22,12]；调两次 fill | cost 版 E = [45,50,38,22,12]；sr 版 E = [52,58,44,26,14]；5 条 sr > cost | §需求 7 V1 + §5 表 |
| V-B7-02 | h_col_variant_diff | 同上 | cost 版 H13/15/16/18/19 全空；sr 版全 `'ALL-in'`；H14/H17 两版均空 | §需求 7 V2 |
| V-B7-03 | fg_col_variant_identical | 同上 | F13/15/16/18/19 两版逐格相等；G 列同理 | §需求 7 V3 |
| V-B7-04 | non_pvg_zero_diff | 同上；调用 `assert_non_pvg_cells_identical` | 非 PVG 段零改动；R38 ICN 约束原样 | §需求 7 V4 + §需求 5 规则 1-12 |
| V-B7-05 | local_delivery_zero_diff | R14/R17 status = LOCAL_DELIVERY_MANUAL | R14/R17 E=0, F/G=`'－'`, H 空（与 2-①.xlsx 一致） | §需求 7 V5 |
| V-B7-06 | all_no_rate | 5 条 AIR_FREIGHT status = NO_RATE | 两版 E/F/G/H 在 R13/15/16/18/19 均留空；FillReport.no_rate_count=5 / filled_count=0；非 PVG 段零改动 | §需求 7 V6 |
| V-B7-07 | mixed_filled_constraint | R13/R15/R16 FILLED；R18/R19 CONSTRAINT_BLOCK (remark_text='※某约束') | R13/R15/R16 按 V1/V2 规则；R18/R19 E/F/G 空，H 写约束文本（两版一致）；非 PVG 段零改动 | §需求 7 V7 |

### 8.4 补充 3 条结构测试（不在 V1-V7 范围但必须跑）

| ID | 名称 | 检查点 |
|---|---|---|
| V-B7-S1 | sheet_preserved | 产出文件 `wb.sheetnames == ['見積りシート']`；`ws.title == '見積りシート'` |
| V-B7-S2 | merged_cells_preserved | `assert_merged_cells_identical(src, cost_out)` + 对 sr 同样 |
| V-B7-S3 | doc_props_stamped | `wb.properties.title == 'Step1 batch bid_test:cost'` 或等价（确认 stamp 生效、原 Author 未被清） |

### 8.5 markup 注入测试

| ID | 名称 | 检查点 |
|---|---|---|
| V-B7-M1 | custom_markup_fn | 传 `markup_fn=lambda c: c * Decimal("2")`；cost=45 → sr 版 E13 = 90（验证依赖注入生效，非 1.15 被硬编码） |
| V-B7-M2 | default_markup_fn_ceil | 调 `default_markup_fn(Decimal("45"))` == `Decimal(52)`（45×1.15=51.75 → ceil_int=52） |

### 8.6 不自动化的抽检（列入 Demo 前 checklist，业务需求 §需求 7 §7.3）

- Windows Excel Desktop 打开 `cost_*.xlsx` 与 `sr_*.xlsx` 不弹"文件已损坏"警告
- 冻结窗格 / 超链接 / 条件格式肉眼比对（若黄金样本有则测）

---

## 9. 依赖 / 阻塞

### 9.1 内部依赖

| 依赖 | 来源 | 状态 |
|---|---|---|
| `CustomerAProfile.parse` | `customer_a.py:140-176` | **已就绪**（T-B4） |
| `ParsedPkg / PkgRow / PkgSection` | `entities.py:42-86` | **已就绪**（T-B1） |
| `PerRowReport / FillReport / RowStatus` | `entities.py:111-140, 31-39` | **已就绪**（T-B1） |
| `CustomerProfile.fill` 协议签名 | `protocols.py:32-39` | **已就绪**（T-B1） |
| Step1 writers `safe_set / is_formula_cell / stamp_document_properties` | `step1_rates/writers/base.py:15-82` | **已就绪**（Step1 TD-2） |
| `_SHEET_NAME / _COL_PRICE / _COL_LEAD_TIME / _COL_CARRIER / _COL_REMARK` | `customer_a.py:25, 35-38` | **已就绪**（T-B4） |
| `_LOCAL_SECTION_CODES = {"PVG"}` | `customer_a.py:65` | **已就绪**（T-B4） |
| 黄金样本 2-①.xlsx | `资料/2026.04.02/Customer A (Air)/...` | **已就绪**（业务大师） |

### 9.2 不阻塞的事项

- **T-B6 MarkupApplier**：本任务通过 `markup_fn` 依赖注入兜底；T-B6 交付后 service 层 1 行替换即可
- **T-B2（DB schema）**：T-B7 全程文件 IO，不落库；`FillReport` 只是内存对象
- **T-B9 service 编排**：T-B7 接受 output_path 参数，自己不拼文件名；service 没到位也能通过 pytest 直接跑 `fill()`
- **T-B10 API 层**：T-B7 产出的文件可被任何下载接口读；不绑定特定 API 形态

### 9.3 半阻塞 — 业务需求 §9 的 3 个问题

| 编号 | 问题 | v1.0 默认（代码常量位置） | 阻塞？ |
|---|---|---|---|
| Q-T-B7-01 | 加价系数 1.15 是否正确 | `_DEFAULT_MARKUP_RATIO = Decimal("1.15")`（`customer_a.py` 模块级） | **不阻塞**（依赖注入，T-B6 / service 可覆盖）；Demo 前审核页需文案提示 |
| Q-T-B7-02 | H 列 ALL-in 是否追加 client_constraint | v1.0 仅写 `'ALL-in'`；PVG 行 client_constraint 非空时 `FillReport.global_warnings` 追加 warning | 不阻塞 |
| Q-T-B7-03 | 日文按钮文案 | 前端 i18n 文案；T-B7 内部无按钮，不受影响 | 不阻塞 |

### 9.4 监工警示

- **Step1 writers.base 的 safe_set 语义**：`value is None → 不写`，`value=""（空串）→ 写空串`。开发大师不得混淆这两种（NO_RATE 要显式写 `""` 让审核者看到"留白"）。
- **非 PVG 段零改动是 Demo 级硬底线**：代码写完后**必须**跑一次 `assert_non_pvg_cells_identical`；若因 openpyxl 副作用（如保存时重排 xml 导致某些 style 对象变化）触发 style mismatch，优先比对 value，style 比对可降级为 number_format / font.name / fill.start_color.index 等关键属性，但**禁止**为了绕过这条断言而主动修改 style。
- **Sheet 名 `見積りシート` 是日文**：源码中以 Unicode 字符保存；`customer_a.py:25` 已有 `_SHEET_NAME = "見積りシート"` 常量，复用即可。
- **`FillReport` 字段是 str 不是 Path**：`entities.py:138-139` 类型是 `str`；T-B7 返回时需 `str(output_path)`。

---

## 10. 预估人天

| 角色 | 工时 | 内容 |
|---|---|---|
| 开发大师（实现） | **1.5 人天** | customer_a.py 修改约 120 行（含 helper）；__init__.py 1 行；markup helper 30 行 |
| 测试大师（独立验证） | **0.5 人天** | 7 条 V-B7 + 3 条结构 + 2 条 markup = 12 条单测；复用 T-B4 fixture |
| **合计** | **2.0 人天** | 可在 2 工作日内交付完成 |

---

## 11. 验收 Checklist（监工抽查）

- [ ] `backend/app/services/step2_bidding/customer_profiles/customer_a.py:125-136` 的 `raise NotImplementedError` 被替换为真实 fill 实现
- [ ] `customer_a.py` 新增 `__init__(self, markup_fn=None)`；原有 class 无状态字段被打破 —— parse / detect 仍能在无 markup_fn 的 profile 实例上正常工作
- [ ] `customer_a.py` 模块级新增 3 个常量：`_DEFAULT_MARKUP_RATIO / _SR_FIXED_REMARK / _T_B7_WRITER_VERSION`
- [ ] `customer_a.py` 末尾新增 `default_markup_fn` 与 `_ceil_int`
- [ ] `customer_a.py` 从 `app.services.step1_rates.writers.base` import `safe_set / is_formula_cell / stamp_document_properties`（不复刻）
- [ ] `__init__.py` 暴露 `CustomerAProfile` 与 `default_markup_fn`
- [ ] 12 条 pytest 全过（`pytest backend/tests/services/step2_bidding/test_customer_a_fill.py -v`）
- [ ] `pytest backend/tests/services/step2_bidding/test_customer_a_parse.py -v` 仍全过（无回归，parse 行为未受 `__init__` 改动破坏）
- [ ] `pytest backend/tests/services/step2_bidding/test_rate_matcher.py -v` 仍全过（无回归）
- [ ] `pytest backend/tests/services/step2_bidding/test_customer_identifier.py -v` 仍全过（无回归）
- [ ] 未新增 Python 依赖（`backend/requirements.txt` 无 diff）
- [ ] 未动 `protocols.py / entities.py / rate_matcher.py / rate_repository.py`
- [ ] 未动 `backend/app/services/step1_rates/**`
- [ ] 未动 `backend/app/models/**` / `backend/alembic/**`
- [ ] `assert_non_pvg_cells_identical` 在 V-B7-04 / V-B7-06 / V-B7-07 三条用例中均通过（监工可 grep 调用点）

---

## 12. 开放问题（给监工决策）

1. **Q-T-B7-arch-01**：`markup_fn` 注入到 `CustomerAProfile.__init__` 还是做成 fill 的 kwargs？本文件选前者（不改 Protocol 签名）。若监工认为"构造函数有状态违反 profile 的无状态假设"，可改为 fill 的关键字参数（但需同步改 `protocols.py:32-39` 签名和 T-B8 所有调用点）。**架构大师建议保持构造函数方案**。
2. **Q-T-B7-arch-02**：`FillReport` 单次 fill 调用返回只填一边的 `*_file_path`，由 service 层合并——是否要在 T-B7 内部就提供"两次合并"的 helper 函数？本文件选 service 层合并（T-B7 单一职责）。监工如认为便利性更重要，可追加一个模块级 `merge_fill_reports(cost, sr)` 函数（5 行）。
3. **Q-T-B7-arch-03**：本轮要不要真接 T-B6 `MarkupApplier`？T-B6 尚未交付架构任务单。若监工决定并行推进 T-B6，T-B7 的 `default_markup_fn` 可立即替换为 `MarkupApplier(...).apply`；若串行推进，T-B7 先用默认兜底，T-B6 到位后 service 层 1 行替换。**架构大师建议串行**：T-B6 是独立子任务，先让 T-B7 验收闭环，再推 T-B6。
4. **Q-T-B7-arch-04**：`PerRowReport.sell_price` 字段是否由 T-B7 回写？本文件选**不回写**（T-B7 只用 cost_price + markup_fn 现场算）。若监工希望 FillReport 的 row_reports 里也带 sell_price 便于审核页显示，可在 `_build_fill_report` 中同步写入 `report.sell_price = markup_fn(report.cost_price)`（mutate 入参有副作用风险，建议改为深拷贝）。

---

## 13. 监工汇报小结

**拆出子任务数**：7 个小任务（T-B7a..T-B7g），总改动 1 个业务源文件（customer_a.py）+ 1 个 __init__.py + 1 个测试文件 + 1 个测试 fixture 文件 = **4 件改动**。

**关键技术决策摘要**（给业务大师 / 监工的 3 条）：

1. **markup 依赖注入位置 = 构造函数**。`CustomerAProfile(markup_fn=...)` 由 service 层注入；T-B6 交付时 service 层 1 行替换即可，T-B7 零改动。这比"把 markup_fn 塞进 fill 的 kwargs"更不侵入（不改 `protocols.py:32-39` Protocol 签名）。
2. **双版本 = 二次调用 fill**。每次 fill 只管一个 variant（"cost" 或 "sr"），service 层串行调两次；两次写的是两个独立文件，T-B7 不在内部合并文件或合并 FillReport。
3. **非 PVG 段零改动 = `_pvg_rowset` 白名单 + `assert_non_pvg_cells_identical` 断言**。T-B7 主循环只对 PVG 段 row_idx 做写操作；测试大师用 diff 工具遍历源文件与产出文件逐 cell 比对，排除 5×4=20 个白名单 cell 后全部等值。这是 Demo 级硬底线的唯一自动化保证。

**建议**：交开发大师按 T-B7a..T-B7g 顺序实施。**不**需要回业务大师补需求——业务需求 §0-§9 已覆盖所有字段级决策（cost/sr 差异、LOCAL_DELIVERY 保持、ALL-in 常量、非 PVG 段零改动），剩余 3 个开放问题均在代码默认值范围内可落地。
