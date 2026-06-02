# A4 海运审核台 ocean 列补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把残缺的海运审核台（只 5 列）按动态列补全，并修掉「改价不入库 / 40HC 不可见」的价格口径割裂。

**Architecture:** 前端为主——`RateSheetBuilder.tsx` 的 `seaCols` 改为动态列（某列有数据才渲染），价格列直接绑结构化 `container_*`（入库读这些），在 `buildFinalRows()` 收口时为 sea 行派生下载链路用的 `freight_*`/`transit`。后端只动 2 处各 1 行（`_normalize_sea` 透传 currency、`commit_ocean_rows` 取行 currency），不碰价格读取逻辑。

**Tech Stack:** React 19 + TS + Ant Design v6 + i18next（前端）；Python + pytest（后端）。前端无 test runner，验证靠 `npm run build`(tsc) + 手测。

**Spec:** `docs/superpowers/specs/2026-06-01-ocean-review-desk-columns-design.md`

---

## File Structure

- `backend/app/services/step1_rates/sheet_builder/orchestrator.py` — `_normalize_sea` 加 currency 透传（+1 行）。
- `backend/app/services/step1_rates/sheet_builder/db_writer.py` — `commit_ocean_rows` currency 取行值（改 1 行）。
- `backend/tests/sheet_builder/test_orchestrator.py` — 加 currency 透传测试。
- `backend/tests/sheet_builder/test_ocean_writer.py` — 加 commit 取行 currency 测试。
- `frontend/src/i18n/{zh,ja,en}.json` — 加 12 个 `rateSheet.col*` 键。
- `frontend/src/pages/RateSheetBuilder.tsx` — 扩 `PreviewRow`、加只读列工厂 `roCol`、动态 `seaCols`、价格绑 `container_*`、`buildFinalRows` sea 派生、Table 横向滚动。

任务顺序：先后端（可 TDD、独立）→ i18n（前端列引用的文案）→ 前端主改 → 端到端手测。

---

## Task 1: 后端 currency 透传 + 入库取行 currency

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`（`_normalize_sea`，约 :179-208）
- Modify: `backend/app/services/step1_rates/sheet_builder/db_writer.py`（`commit_ocean_rows`，:197 `currency="USD"`）
- Test: `backend/tests/sheet_builder/test_orchestrator.py`、`backend/tests/sheet_builder/test_ocean_writer.py`

- [ ] **Step 1: 写失败测试（_normalize_sea 透传 currency）**

在 `backend/tests/sheet_builder/test_orchestrator.py` 末尾新增：

```python
def test_normalize_sea_passes_through_currency():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea
    # 行带 currency → 原样透传
    assert _normalize_sea({"destination_port_name": "HILO", "currency": "USD"}, "")["currency"] == "USD"
    # 行无 currency → 默认 USD
    assert _normalize_sea({"destination_port_name": "HILO"}, "")["currency"] == "USD"
```

- [ ] **Step 2: 写失败测试（commit 取行 currency）**

在 `backend/tests/sheet_builder/test_ocean_writer.py` 末尾新增（复用文件内 `db_session` fixture 与 `_row` 助手）：

```python
def test_commit_ocean_uses_row_currency(db_session):
    row = _row("HONG KONG", Decimal("250"), Decimal("500"))
    row["currency"] = "CNY"
    db_writer.commit_ocean_rows([row], db_session)
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.currency == "CNY"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py::test_normalize_sea_passes_through_currency tests/sheet_builder/test_ocean_writer.py::test_commit_ocean_uses_row_currency -v`
Expected: 两条都 FAIL（`_normalize_sea` 输出无 `currency` 键 → KeyError；commit 硬编码 USD → `assert "USD" == "CNY"` 失败）。

- [ ] **Step 4: 改 `_normalize_sea` 加 currency 透传**

在 `orchestrator.py` 的 `_normalize_sea` 返回 dict 里，`"source_type"` 那一行附近加一行（位置随意，建议紧挨 `"source_type"`）：

```python
        "source_type": row.get("source_type"),
        "currency": row.get("currency") or "USD",
        "needs_review": row.get("needs_review", False),
```

- [ ] **Step 5: 改 `commit_ocean_rows` 取行 currency**

在 `db_writer.py` 的 `commit_ocean_rows` 里，把 FreightRate 构造的这一行：

```python
                currency="USD",
```

改为：

```python
                currency=r.get("currency") or "USD",
```

- [ ] **Step 6: 跑测试确认通过 + 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/ -q`
Expected: 全 PASS（含新 2 条；既有 `test_commit_ocean_writes_freightrate` 的 `currency == "USD"` 仍过——行无 currency 默认 USD）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/app/services/step1_rates/sheet_builder/db_writer.py backend/tests/sheet_builder/test_orchestrator.py backend/tests/sheet_builder/test_ocean_writer.py
git commit -m "feat(step1): 海运行透传 currency, 入库取行币种(原硬编码USD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 前端 i18n 新增 12 个海运列键

**Files:**
- Modify: `frontend/src/i18n/zh.json`、`frontend/src/i18n/ja.json`、`frontend/src/i18n/en.json`（均在 `"rateSheet": { ... }` 对象内）

- [ ] **Step 1: zh.json 加键**

在 `frontend/src/i18n/zh.json` 的 `rateSheet` 对象内（建议紧跟 `colFreight40` 之后）加入：

```json
    "col40gp": "40GP",
    "col40hq": "40HC",
    "col45": "45'",
    "colVia": "中转(Via)",
    "colCurrency": "币种",
    "colValidFrom": "生效日",
    "colValidTo": "失效日",
    "colCommodity": "品名",
    "colRateLevel": "编码",
    "colLss": "LSS/CIC",
    "colBaf": "BAF",
    "colTransit": "航程(天)",
```

- [ ] **Step 2: ja.json 加键**

在 `frontend/src/i18n/ja.json` 的 `rateSheet` 对象内加入：

```json
    "col40gp": "40GP",
    "col40hq": "40HC",
    "col45": "45'",
    "colVia": "経由(Via)",
    "colCurrency": "通貨",
    "colValidFrom": "有効開始日",
    "colValidTo": "有効終了日",
    "colCommodity": "品目",
    "colRateLevel": "コード",
    "colLss": "LSS/CIC",
    "colBaf": "BAF",
    "colTransit": "航行日数",
```

- [ ] **Step 3: en.json 加键**

在 `frontend/src/i18n/en.json` 的 `rateSheet` 对象内加入：

```json
    "col40gp": "40GP",
    "col40hq": "40HC",
    "col45": "45'",
    "colVia": "Via",
    "colCurrency": "Currency",
    "colValidFrom": "Valid From",
    "colValidTo": "Valid To",
    "colCommodity": "Commodity",
    "colRateLevel": "Rate Code",
    "colLss": "LSS/CIC",
    "colBaf": "BAF",
    "colTransit": "Transit (d)",
```

- [ ] **Step 4: 校验三份 JSON 合法且键齐**

Run:
```bash
cd frontend && for f in zh ja en; do node -e "const r=require('./src/i18n/$f.json').rateSheet; const need=['col40gp','col40hq','col45','colVia','colCurrency','colValidFrom','colValidTo','colCommodity','colRateLevel','colLss','colBaf','colTransit']; const miss=need.filter(k=>!(k in r)); console.log('$f', miss.length? 'MISSING '+miss : 'OK')"; done
```
Expected: `zh OK` / `ja OK` / `en OK`（任一 JSON 语法错会直接抛错）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "feat(step1): 海运审核台新列 i18n(40GP/40HC/45/via/币种/生效日/commodity/编码/LSS/BAF/航程) 三语

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 前端 RateSheetBuilder.tsx 动态海运列 + 价格绑 container_* + buildFinalRows 派生

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`

- [ ] **Step 1: 扩展 `PreviewRow` 接口**

在 `interface PreviewRow { ... }`（约 :17-36）的 `freight_40` 之后、`service` 之前插入结构化海运字段：

```typescript
  // 结构化海运字段(入库 commit_ocean_rows 读这些；审核台价格列直接绑定它们)
  container_20gp?: number | string | null;
  container_40gp?: number | string | null;
  container_40hq?: number | string | null;
  container_45?: number | string | null;
  currency?: string | null;
  via?: string | null;
  commodity?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  rate_level?: string | null;
  service_code?: string | null;
  lss_cic?: number | string | null;
  baf?: number | string | null;
  transit_days?: number | string | null;
  transit?: number | string | null;
```

- [ ] **Step 2: `buildFinalRows` 为 sea 行派生下载链路字段**

把 `buildFinalRows`（约 :128-135）整体替换为：

```typescript
  // 勾选保留 + 行内编辑后的最终行（下载与入库共用）
  const buildFinalRows = () =>
    rows
      .filter((r) => selectedRowKeys.includes(r._rid as number))
      .map((r) => {
        const merged = { ...r, ...editedRows[r._rid as number] } as PreviewRow;
        delete (merged as { _rid?: number })._rid;
        // 海运：价格/航程审核台编辑的是结构化字段(container_*/transit_days，入库读这些)；
        // 这里派生下载链路用的合并字段(freight_*/transit，template_filler 读这些)，让两条路都吃到编辑。
        if (templateType === 'sea') {
          merged.freight_20 = (merged.container_20gp as number | null) ?? null;
          merged.freight_40 =
            (merged.container_40gp as number | null) ?? (merged.container_40hq as number | null) ?? null;
          merged.transit = (merged.transit_days as number | null) ?? null;
        }
        return merged;
      });
```

- [ ] **Step 3: 加只读列工厂 `roCol` 与 `seaHas` 判定**

在 `numCol` 工厂（约 :226-239）之后插入：

```typescript
  // 只读列：直接展示原值(不进 editedRows)，用于起运港/币种/编码等标识性字段
  const roCol = (title: string, field: keyof PreviewRow, width = 80) => ({
    title,
    key: field as string,
    width,
    render: (_: unknown, r: PreviewRow) => {
      const v = (r as Record<string, unknown>)[field as string];
      return v === null || v === undefined ? '' : String(v);
    },
  });

  // 动态列判定：该字段全表至少一行有非空值时才渲染对应列(与 air 档位列并集同思路)
  const seaHas = (field: string) =>
    rows.some((r) => {
      const v = (r as Record<string, unknown>)[field];
      return v !== null && v !== undefined && v !== '';
    });
```

- [ ] **Step 4: 重写 `seaCols` 为动态列、价格绑 `container_*`**

把现有 `seaCols`（约 :287-294）整体替换为：

```typescript
  // 海运动态列：起运港/目的港/备注恒显；其余按该批次是否有数据出现。
  // 价格列绑结构化 container_*(入库读这些)；via/commodity/生效日可编辑(needs_review 行纠正目标)；
  // 起运港/币种/编码只读(标识性字段)。
  const seaCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination'),
    ...(seaHas('via') ? [textCol(t('rateSheet.colVia'), 'via')] : []),
    textCol(t('rateSheet.colCarrier'), 'carrier'),
    ...(seaHas('container_20gp') ? [numCol(t('rateSheet.colFreight20'), 'container_20gp')] : []),
    ...(seaHas('container_40gp') ? [numCol(t('rateSheet.col40gp'), 'container_40gp')] : []),
    ...(seaHas('container_40hq') ? [numCol(t('rateSheet.col40hq'), 'container_40hq')] : []),
    ...(seaHas('container_45') ? [numCol(t('rateSheet.col45'), 'container_45')] : []),
    ...(seaHas('currency') ? [roCol(t('rateSheet.colCurrency'), 'currency', 64)] : []),
    ...(seaHas('valid_from') ? [textCol(t('rateSheet.colValidFrom'), 'valid_from')] : []),
    ...(seaHas('valid_to') ? [textCol(t('rateSheet.colValidTo'), 'valid_to')] : []),
    ...(seaHas('commodity') ? [textCol(t('rateSheet.colCommodity'), 'commodity')] : []),
    ...(seaHas('rate_level') ? [roCol(t('rateSheet.colRateLevel'), 'rate_level', 72)] : []),
    ...(seaHas('lss_cic') ? [numCol(t('rateSheet.colLss'), 'lss_cic')] : []),
    ...(seaHas('baf') ? [numCol(t('rateSheet.colBaf'), 'baf')] : []),
    ...(seaHas('transit_days') ? [numCol(t('rateSheet.colTransit'), 'transit_days')] : []),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
```

> 注意：`originCol` 已在文件内定义（air 用），此处复用；它在 `seaCols` 引用前已声明（`originCol` 定义在 :296，需确认在 `seaCols` 之前——若 `seaCols` 在 `originCol` 之前，则把 `originCol` 定义上移到 `seaCols` 之前）。

- [ ] **Step 5: 确认 `originCol` 声明在 `seaCols` 之前（必要时上移）**

当前 `seaCols`(:287) 在 `originCol`(:296) 之前，JS `const` 不提升 → 直接引用会 ReferenceError。把 `originCol` 的整段定义：

```typescript
  // 起运港：联运商均沪发，默认 PVG；只读展示（不参与编辑），让客户一眼看清从哪发。
  const originCol = {
    title: t('rateSheet.colOrigin'),
    key: 'origin',
    width: 72,
    render: (_: unknown, r: PreviewRow) => r.origin ?? '',
  };
```

移动到 `seaCols` 定义**之前**（例如紧跟 Step 3 的 `seaHas` 之后）。删除原 :295-301 处的旧定义，避免重复声明。

- [ ] **Step 6: 预览 Table 加横向滚动**

列变多后避免挤压——给预览 `Table`（约 :479-497）加 `scroll` 属性。在 `<Table className="rs-table" ...>` 的属性里加一行：

```tsx
                scroll={{ x: 'max-content' }}
```

- [ ] **Step 7: 类型检查 / 构建通过**

Run: `cd frontend && npm run build`
Expected: tsc-b 通过、vite build 成功（无 TS 报错）。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx
git commit -m "feat(step1): 海运审核台动态列补全 + 修改价不入库/40HC不可见

- seaCols 改动态列(40GP/40HC/45/via/币种/生效日/commodity/编码/LSS/BAF/航程)
- 价格列绑结构化 container_*(入库读这些), buildFinalRows 为 sea 派生 freight_*/transit(下载读这些)
- originCol 上移, 预览表横向滚动

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 端到端手测 + 全量回归

**Files:** 无（验证）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全 PASS（基线 362 passed + 本轮新增 2；3 个 `test_ai_client` vLLM 环境失败为既有无关项，可忽略）。

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 3: 手测——海运做表审核台（前后端已在 :8000/:5173 运行，HMR 生效）**

打开 http://localhost:5173 → 运价表生成（RateSheetBuilder）：
1. 选 **Sea 海运** 模板。
2. 上传一份海运料（ONE 合约 PDF：`資料/2026.05.27/Sea Net Rete/LAX0751N25v93 (2).pdf`；或 kmtc/nvo Excel）。
3. 核对审核台**动态列**：
   - ONE 合约批次出现 起运/目的/via/船司/20'/40GP/40HC/45'/币种/生效日/commodity/编码/备注。
   - Excel 批次出现 LSS/BAF/航程，不出现 via/commodity/45'。
4. **改价验证（核心 bug 修复）**：改某行 40HC 与 20' 的价 → 点「确认入库」→ 到 RateList（运价列表）查该 lane，落库价 = **改后价**（修复前会是原始价）。
5. via / commodity / 生效日 可编辑，改后入库回写正确。
6. 取消勾选某行 → 不纳入下载/入库（既有行为不回归）。

- [ ] **Step 4: 记录结果**

把手测结果（每条 OK / NG + 证据）回报给用户。NG 则定位后回到对应 Task 修复。

---

## Self-Review（写完已自检）

- **Spec 覆盖**：动态列(Task 3)、价格绑 container_* + 改价不入库修复(Task 3 Step 2/4)、40HC 可见(Task 3 Step 4)、currency 透传+一致性(Task 1)、i18n 12 键三语(Task 2)、手测口径(Task 4)——spec 各节均有对应任务。
- **占位符**：无 TBD/TODO；每个改码步骤含完整代码。
- **类型一致**：`container_20gp/40gp/40hq/45`、`transit_days`、`currency` 在 PreviewRow(Step 1)、buildFinalRows(Step 2)、seaCols(Step 4) 中命名一致；后端 `_normalize_sea` 输出键与 `commit_ocean_rows` 读取键一致(`currency`)。
- **风险点**：Task 3 Step 5 的 `originCol` 声明顺序——已显式列为一步处理，避免 `const` 不提升的 ReferenceError。
