# Customer A (Air) 日本段 JPY（B1）设计文档

- 日期：2026-06-01
- 分支：`feature/step1-review-desk`
- 关联记忆：[[step2-air-bid-format]] [[step1-air-ees-format]] [[mvp-minimal-scope-remind]] [[hankyu-demo-branch-state]]

## 背景与重新定性

Customer A (Air) 投标包 `見積りシート` 含上下两块：**日本(成田)段 単価(円/kg)** 与 **中国(上海)段 単価(CNY/kg)**。
中国段（上海 PVG / CNY）已通过 air_tier「做表→入库→按货量取价→回填」全链路实现；日本段（成田 NRT / JPY）一直 defer。

排查结论（代码现状）——**日本段缺口主要在「数据录入 UI」，匹配/入库几乎现成**：

- **匹配器已 origin/currency 感知**：`rate_matcher` 的重量档支路 `query_air_tier(origin=row.origin_code, currency=row.currency)` 用车道自己的起运码与币种；日本段车道 `origin_code=NRT`（`customer_a` 已映射 成田/日本→NRT）、`currency=JPY`（円→JPY 已映射）。`query_air_tier` 按 origin 精确 + currency 硬过滤。
- **入库已读行 origin/currency**：`commit_tier_rows` 用 `origin=r.get("origin") or "PVG"`、`currency=r.get("currency") or "CNY"`。前端把行标成 NRT/JPY 即可。
- **真正的 gate 只有两处**（都因常量只含 "PVG"）：
  1. `rate_matcher.py:48` `if row.section_code not in _LOCAL_SECTION_CODES: return NON_LOCAL_LEG` —— 日本段车道被早退跳过。
  2. `customer_a.py` 同名常量 → `is_local_section`（仅 PVG 段 True）→ `_pvg_rowset` → `fill` 只回填 PVG 段。
- **缺数据 + 缺录入口**：air 做表起运写死 PVG、币种默认 CNY，审核台无「币种/加行」，没法手录 NRT/JPY 运价。

诊断确认：仓库内（含 `资料/2026.05.27/air`）**无任何日本出发 JPY 空运元料金**（EES/唯凯均上海发 CNY，其中 NRT 是目的港）。故日本段运价靠**人工在做表审核台手录**（用户决策）。

## 目标

让 Customer A (Air) 投标包的**日本段 単価(円/kg) 能被自动填回**：泛化 air_tier 管道到 NRT/JPY 段
（做表审核台手录 → 入库 → 匹配 → 回填），不依赖特定文件格式。中国段 CNY 行为不变。

**成功标准**：在做表审核台手录几条 NRT/JPY 日本段档位价并入库 → 上传 Customer A (Air) 投标包 →
日本段 単価(円/kg) 被填上正确档位价，中国段(CNY)不受影响。

## 范围

### 本版做
1. **后端 gate 扩展**：`_LOCAL_SECTION_CODES` 两处加 `"NRT"` → 日本段过 gate 被匹配 + 回填。
2. **前端做表手录 NRT/JPY**：air 做表会话级「起运港 + 币种」选择 + 审核台「＋手动添加行」。
3. **回填验证**：确认 `fill` 自动覆盖 NRT 段（随 `is_local_section` 纳入）。

### 非目标（defer，见 [[mvp-minimal-scope-remind]]）
- **本地配送费（LOCAL DELIVERY COST，B2）**：`rate_matcher.py:52` 已识别为 `LOCAL_DELIVERY_MANUAL`，本版仍人工，不做。
- **JPY 厂商文件适配器**：无文件、走手录，不立项。
- **真实 JPY 运价数据**：用户后续手录/提供；本版用手录样例验证。
- **per-row 币种 / 手录行报价周(effective date)录入**：本版会话级单一币种；手录行 effective 留空（匹配器 validity 仅打分、不挡，日本段无竞争候选照样中选）。
- **`is_local_section` 字段改名**：该字段在 `entities.py:51`，跨文件改名风险大；保留原名、扩语义 + 注释（命名债记录）。

## 设计

### Part 1 · 后端 gate 扩展（很小）

- `rate_matcher.py:21` `_LOCAL_SECTION_CODES = frozenset({"PVG"})` → `frozenset({"PVG", "NRT"})`，注释改为「我们处理的段：PVG 上海发 + NRT 成田发」。
- `customer_a.py:74` `_LOCAL_SECTION_CODES = {"PVG"}` → `{"PVG", "NRT"}`，同注释。
  - 连带：`_scan`/`_parse` 阶段 `is_local_section = section_code in _LOCAL_SECTION_CODES`（:423）→ NRT 段变 True；`_pvg_rowset`（:235，靠 `s.is_local_section`）→ 自动纳入 NRT 段行；`fill`（:177）→ 自动回填日本段。**预期无需改 fill 主体**，以测试 + 手测确认。
- 不动 `RowStatus.NON_LOCAL_LEG` 枚举名（公共枚举，含义仍是「非我们处理的段」）。

### Part 2 · 前端做表手录 NRT/JPY（主要工作量）

`frontend/src/pages/RateSheetBuilder.tsx`（air 路径）：

- **会话级「起运港 + 币种」**：air 模板下显示两个选择器：
  - 起运港 `originSel ∈ {PVG, NRT}`（默认 PVG）；币种 `currencySel ∈ {CNY, JPY}`（默认 CNY）。
  - 默认 PVG/CNY → 中国段现有流程**完全不变**（向后兼容）。
- **「＋手动添加行」按钮**（仅 air）：向 `rows` 追加一条手录行：
  `{ _rid, _manual: true, origin: originSel, destination: '', service: '', currency: currencySel,
     tier_prices: {45: null, 100: null, 300: null, 500: null, 1000: null} }`
  - 默认 5 档（标准空运重量档）→ 审核台动态档位列逻辑(`tierColumns` 并集)自然渲染出 45/100/300/500/1000 列供编辑；新行自动勾选。
- **提交/下载时盖章**：`buildFinalRows()` 对 air 行写入 `origin = originSel`、`currency = currencySel`
  （确保手录行与会话一致；上传的 EES 行在默认 PVG/CNY 下为 no-op，向后兼容）。
- 既有 air 审核台编辑（destination/service/tier 价）复用；起运港列只读展示行的 origin（手录行即 NRT）。

### Part 3 · i18n

- 选择器标签**复用** `colOrigin`/`colCurrency`（A4 已加，三语齐）。
- **仅新增** `rateSheet.addRow`（zh「＋手动添加行」/ ja「＋手動で行追加」/ en「+ Add row」）。
- 起运港/币种选项值 PVG/NRT/CNY/JPY 为代码，不入 i18n。

## 数据流

```
做表(air) 选 起运港=NRT 币种=JPY → ＋添加行(手录 NRT→ATL 等档位价)
  → buildFinalRows 盖 origin=NRT/currency=JPY
  → POST /commit → commit_tier_rows(读行 origin/currency) → air_tier(origin=NRT,currency=JPY)

上传 Customer A (Air) 投标包
  → customer_a.parse: 日本段 section_code=NRT、is_local_section=True(Part1)
  → rate_matcher: NRT 段过 gate(Part1) → query_air_tier(origin=NRT,currency=JPY) 命中手录行
    → 按 想定平均重量 select_tier_price 选档 → 候选
  → fill: 回填日本段 単価(円/kg) 单元格(随 _pvg_rowset 纳入)
```

## 错误处理 / 边界

- **手录行无报价周**：`effective_week_start=None` → 匹配器 `validity_cover=False`（仅降分，不挡）；日本段无竞争候选 → 仍中选。
- **手录行全空价**：`commit_tier_rows._norm_tiers` 过滤 None → 空 tier_prices；建议前端提交前忽略「目的港为空或全档空价」的手录行（前端守卫），避免落无效行。
- **币种硬过滤**：`query_air_tier(currency=JPY)` 只返回 JPY 行 → 手录行币种必须存对 JPY（盖章保证）；中国段 CNY 行不会串到日本段。
- **中国段不回归**：默认 PVG/CNY；Part1 只是「新增」NRT 段被处理，PVG 段逻辑不变。
- **想定平均重量缺失的日本段车道**：`select_tier_price` 返回 None → 该车道 `NO_RATE`（与中国段同口径，非回归）。

## 测试 / 验证

- **后端（TDD）**：
  - `test_rate_matcher_tier.py` 增：NRT 段车道（section_code=NRT, currency=JPY）+ 仓储有 NRT/JPY air_tier 行 → 不再 `NON_LOCAL_LEG`、按重量选档命中（对照：去掉 NRT 数据则 `NO_RATE`）。
  - customer_a：日本段 section `is_local_section=True`、`_pvg_rowset` 含 NRT 行；`fill` 回填日本段单元格（小型 fixture 或断言 rowset）。
  - 全量 `pytest -q` 不回归（基线 376 passed，仅 3 vLLM 环境失败无关）。
- **前端**：`npm run build`(tsc) 通过。
- **手测（端到端，核心）**：做表选 NRT/JPY → 添加行手录 NRT→ATL/MIA/AMS… 档位价 → 入库 → 上传 `资料/2026.04.02/Customer A (Air)/.../2-①.xlsx` → 日本段 単価(円/kg) 被填、中国段不受影响。

## 文件级改动清单（预估，细节交 plan）

- 改 `backend/app/services/step2_bidding/rate_matcher.py`（`_LOCAL_SECTION_CODES` += NRT）。
- 改 `backend/app/services/step2_bidding/customer_profiles/customer_a.py`（同上 + 注释；fill 以测试确认无需改主体）。
- 改 `frontend/src/pages/RateSheetBuilder.tsx`（起运港/币种选择器 + 添加行 + buildFinalRows 盖章）。
- 改 `frontend/src/i18n/{zh,ja,en}.json`（addRow 等键）。
- 测试：`backend/tests/services/step2_bidding/test_rate_matcher_tier.py`（+ 视情 customer_a / fill 测试）。
