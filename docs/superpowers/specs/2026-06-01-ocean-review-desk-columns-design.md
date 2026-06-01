# A4 海运审核台 ocean 列补全 — 设计文档

- 日期：2026-06-01
- 分支：`feature/step1-review-desk`
- 关联记忆：[[hankyu-demo-branch-state]] [[nitori-ocean-db-match]] [[step1-pdf-one-contract-adapter]] [[mvp-minimal-scope-remind]]
- 关联 spec：`2026-05-28-review-desk-edit-select-design.md`（审核台勾选/编辑）、`2026-05-29-one-contract-pdf-adapter-design.md`（ONE 合约 PDF 字段来源）

## 背景与问题定性

step1 做表的前端审核台（`frontend/src/pages/RateSheetBuilder.tsx`）现已支持 sea 模板：
有 `seaCols`、sea 模板选项、`fcl_rows` 入库回显。**「ocean 列未做」这条旧记忆已过时**——
它在 ONE 合约 PDF 适配器那批 commit 里顺手加上了。

但当前 sea 审核台只有 **5 列**（目的港 / 船司 / 20' / 40' / 备注 / ⚠），而后端
`_normalize_sea`（`orchestrator.py:175`）现在产出的字段远多于此。`preview` 接口
（`api/v1/rate_sheet.py:87`）把 `session.rows` 整行原样返回，所以**所有海运字段都已到达前端，
只是没有列去渲染**。当前看不见的字段：

- `origin`（起运港 POL）、`container_40hq`（40HC）、`container_45`（45'）
- ONE 合约专属：`via`（中转）、`commodity`、`valid_from` / `valid_to`（生效日）、
  `service_code`、`rate_level`（编码，如 R5/2400）、币种
- Excel 专属：`lss_cic`、`baf`、`transit`（航程）

### 真 bug：海运「改价不入库」+ 40HC 不可见

- 前端价格列编辑的是 `freight_20` / `freight_40`（合并展示字段）。
- **下载**：`template_filler._fill_sea` 读 `freight_20` / `freight_40`（`_SEA_CONTAINER_ROWS`）→ 改价生效 ✓
- **入库**：`commit_ocean_rows` 读 `container_20gp` / `container_40gp` / `container_40hq` → **改价不生效**，
  DB 落的是原始价 ✗
- 且 `freight_40 = container_40gp or container_40hq`：一行同时有 40GP 和 40HC 时，
  界面只给一个数字，**40HC 既看不见也改不了**。

→ 价格展示/下载链路（`freight_*`，合并）与入库链路（`container_*`，结构化）**字段口径割裂**，
编辑只命中前者，入库读后者。这是 A4 必须修的核心，不是可选项——否则「改价→入库」整条审核动作是
静默失效的。

## 目标

把残缺的海运审核台列**按动态列方式补全**，并修掉「改价不入库 / 40HC 不可见」的口径割裂，
让海运做表的 UX 与 air 一致。

## 范围

### 本版做
1. 海运审核台**动态列**（某列只要该批次有 ≥1 行非空就出现，与现有 air 档位列同逻辑）。
2. 价格列绑定到结构化 `container_*` 字段，修「改价不入库 / 40HC 不可见」。
3. 后端 2 处 1 行 currency 透传 + 一致性修正。
4. 新列 i18n（zh / ja / en 三份）。

### 本版不做（MVP 边界，见 [[mvp-minimal-scope-remind]]）
- 附加费金额抽取（ONE 合约只存清单文本，不结构化金额）。
- 合约级 MQC / 合约号结构化入库。
- Sea Net Rate **模板列结构**改造（`template_filler._fill_sea` 的 2 行展开、
  `_SEA_CONTAINER_ROWS` 维持原样）。
- 前端单元测试（项目无前端 test runner，只有 lint + build）。
- 多币种入库逻辑（海运实际恒 USD；本版只透传展示 + 入库取行值，不做汇率/多币种校验）。

## 设计

### 1. 列模型（动态列）

沿用现有 air 的「字段并集」思路（`RateSheetBuilder.tsx:264` 的 `tierColumns`）：
对 sea，遍历全部行，**某字段至少一行有非空值时才渲染该列**。`origin`（默认 SHANGHAI）、
`currency`（默认 USD）恒有值故恒显。

| 列 | 绑定字段 | 编辑性 | 出现条件 |
|---|---|---|---|
| 起运港 | `origin` | 只读 | 恒显 |
| 目的港 | `destination` | ✏️ 文本 | 恒显 |
| via 中转 | `via` | ✏️ 文本 | 有非空 |
| 船司 | `carrier` | ✏️ 文本 | 恒显 |
| 20' | `container_20gp` | ✏️ 数字 | 有非空 |
| 40GP | `container_40gp` | ✏️ 数字 | 有非空 |
| 40HC | `container_40hq` | ✏️ 数字 | 有非空 |
| 45' | `container_45` | ✏️ 数字 | 有非空 |
| 币种 | `currency` | 只读 | 恒显（USD） |
| 生效日 | `valid_from` | ✏️ 文本 | 有非空 |
| 失效日 | `valid_to` | ✏️ 文本 | 有非空 |
| commodity | `commodity` | ✏️ 文本 | 有非空 |
| 编码 | `rate_level` | 只读 | 有非空 |
| LSS/CIC | `lss_cic` | ✏️ 数字 | 有非空 |
| BAF | `baf` | ✏️ 数字 | 有非空 |
| 航程 | `transit` | ✏️ 数字 | 有非空 |
| 备注 | `remark` | ✏️ 文本 | 恒显 |
| ⚠ | `needs_review` | 标记列 | 恒显 |

设计理由：
- **via / commodity / valid_from / valid_to 可编辑**——它们正是 ONE 合约里 needs_review
  （编码/RF/塌列）行人工纠正的目标。
- **起运港 / 币种 / 编码 只读**——标识性字段，不该手改（起运港按文件固定、币种恒 USD、
  编码是合约费率级别标识）。
- 生效日用**文本**输入（保持与后端 `valid_from`/`valid_to` 的 ISO 字符串往返一致，
  不引 DatePicker，避免时区/格式心智负担；`commit_ocean_rows._to_date` 已能解析 `str[:10]`）。

复用 `RateSheetBuilder.tsx` 已有的列工厂：`textCol`（文本可编辑）、`numCol`（数字可编辑）、
`reviewCol`；只读列仿现有 `originCol` 写法（直接渲染值，不进 `editedRows`）。

### 2. 价格列绑定 + 「改价不入库」修正（纯前端，零后端价格逻辑改动）

- 价格列从绑定 `freight_20`/`freight_40` 改为直接绑定 `container_20gp` / `container_40gp` /
  `container_40hq` / `container_45`（入库 `commit_ocean_rows` 本就读这些）。
- 在 `buildFinalRows()`（`RateSheetBuilder.tsx:128`）收口时，对 sea 行**派生**回写
  下载链路所需的合并字段：
  - `freight_20 = container_20gp`
  - `freight_40 = container_40gp ?? container_40hq`（与后端 `_normalize_sea` 的合并口径一致；
    用 `??` 空值合并比原 `or` 更准，避免 0 价被跳过）
- 效果：改价对**下载**（读 `freight_*`）与**入库**（读 `container_*`）**双生效**；40HC 可见可编辑。
- `template_filler._fill_sea` 与 `commit_ocean_rows` 的价格读取逻辑**完全不动** → 后端
  362 测试不受影响。

> 仅在 `buildFinalRows`（同时服务下载与入库）做一次派生，集中收口，避免在每个 `editCell`
> 里散落同步逻辑。

### 3. 后端 currency 透传 + 一致性（2 处各 1 行）

- `orchestrator._normalize_sea`：新增 `"currency": row.get("currency") or "USD"`
  （ONE 合约 parsed row 的 `Cur` 列本有值，现被丢弃；Excel 行无则默认 USD）。
- `db_writer.commit_ocean_rows`：把硬编码 `currency="USD"` 改为 `r.get("currency") or "USD"`，
  让审核台展示的币种与实际入库一致。

### 4. i18n（zh / ja / en 三份，缺一视为 bug）

复用现有键：`colOrigin` `colDestination` `colCarrier` `colRemark` `colFreight20`（用于 20' 列表头）。

新增键（`rateSheet.*`）：

| key | zh | ja | en |
|---|---|---|---|
| col40gp | 40GP | 40GP | 40GP |
| col40hq | 40HC | 40HC | 40HC |
| col45 | 45' | 45' | 45' |
| colVia | 中转(Via) | 経由(Via) | Via |
| colCurrency | 币种 | 通貨 | Currency |
| colValidFrom | 生效日 | 有効開始日 | Valid From |
| colValidTo | 失效日 | 有効終了日 | Valid To |
| colCommodity | 品名 | 品目 | Commodity |
| colRateLevel | 编码 | コード | Rate Code |
| colLss | LSS/CIC | LSS/CIC | LSS/CIC |
| colBaf | BAF | BAF | BAF |
| colTransit | 航程(天) | 航行日数 | Transit (d) |

（最终文案以三语术语表为准，见 CLAUDE.md。）

## 数据流

```
做表上传(Excel/ONE PDF)
  → orchestrator.add_file → _normalize_sea(含 currency 透传)
  → session.rows
  → GET /preview (整行返回，已含全部字段)
  → 前端 rows state
  → 动态列(字段并集) 渲染 + 行内编辑(写 editedRows，价格写 container_*)
  → buildFinalRows() 合并 editedRows + 对 sea 派生 freight_20/40
  → 下载 POST  /download  (template_filler 读 freight_*)
  → 入库 POST  /commit    (commit_ocean_rows 读 container_* + currency)
```

## 错误处理 / 边界

- 异构空列：某字段全批为空则该列不渲染（动态列天然处理，无需特判）。
- 0 价：`container_*` 用 `??` 派生，0 不被误当空。
- 生效日非法字符串：入库侧 `_to_date` 已容错（解析失败返回 None），前端不额外校验。
- air 模板路径完全不受影响：`previewCols = templateType === 'air' ? airCols : seaCols`，
  本次只改 `seaCols` 分支与 `buildFinalRows` 的 sea 派生。

## 测试 / 验证

- 后端：`cd backend && ../.venv/bin/python -m pytest -q` 仍 **362 passed**（确认 2 处 1 行 currency
  改动未碰坏 commit/normalize；可新增 1~2 个针对 `commit_ocean_rows` currency 取值的小用例）。
- 前端：无 test runner → `npm run build`（tsc-b）必过。
- 手测（端到端，最关键）：
  1. 选 Sea 模板 → 上传 ONE 合约 PDF（或 kmtc/nvo Excel）→ 审核台出现动态海运列。
  2. 改某行 40HC / 20' 价 → 点「确认入库」→ 到 RateList / DB 核对落库价 = 改后价（修复验证）。
  3. via/commodity/生效日 可编辑、改后入库回写正确。
  4. Excel 批次显示 LSS/BAF/航程、不显示 via/commodity；ONE 批次反之（动态列验证）。

## 文件级改动清单（预估，细节交 plan）

- 前端 `frontend/src/pages/RateSheetBuilder.tsx`：扩 `PreviewRow` 接口；重写 `seaCols` 为动态列 +
  只读列工厂；`buildFinalRows` sea 派生 `freight_*`。
- 前端 `frontend/src/i18n/{zh,ja,en}.json`：新增 12 个 `rateSheet.col*` 键。
- 后端 `backend/app/services/step1_rates/sheet_builder/orchestrator.py`：`_normalize_sea` +1 行。
- 后端 `backend/app/services/step1_rates/sheet_builder/db_writer.py`：`commit_ocean_rows` currency 改 1 行。
- 测试（可选）：`backend/tests/sheet_builder/` 加 currency 取值小用例。
