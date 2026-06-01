# Customer A (Air) 日本段 JPY（B1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Customer A (Air) 投标包日本段(成田 NRT / 円 JPY)能自动填回——泛化 air_tier 管道到 NRT/JPY 段（做表审核台手录 → 入库 → 匹配 → 回填）。

**Architecture:** 后端只把 `_LOCAL_SECTION_CODES`(rate_matcher + customer_a) 加入 `"NRT"`（matcher 已 origin/currency 感知、commit 已读行 origin/currency，无需更多后端改动；fill 随 `is_local_section` 自动覆盖 NRT 段）。前端给 air 做表加会话级「起运港/币种」+ 审核台「＋手动添加行」+ 提交时盖 origin/currency。

**Tech Stack:** Python + SQLAlchemy + pytest（后端）；React + TS + Ant Design v6 + i18next（前端，验证靠 `npm run build` + 手测）。

**Spec:** `docs/superpowers/specs/2026-06-01-customer-a-japan-jpy-design.md`

**范围说明**：投标包有 5 个起运段(NRT/PVG/AMS/TPE/ICN)，本版**只做日本段 NRT**；AMS/TPE/ICN 仍 NON_LOCAL_LEG（同模式后续可加，非本次）。

---

## File Structure

- 改 `backend/app/services/step2_bidding/rate_matcher.py` — `_LOCAL_SECTION_CODES` += "NRT"。
- 改 `backend/app/services/step2_bidding/customer_profiles/customer_a.py` — 同上常量 += "NRT"（fill/`_pvg_rowset`/`is_local_section` 随之自动纳入 NRT，无需改主体）。
- 改 `backend/tests/services/step2_bidding/test_rate_matcher.py` — V-B5-01 过时断言(NRT→NON_LOCAL_LEG)改用仍未实装的 AMS 段。
- 改 `backend/tests/services/step2_bidding/test_rate_matcher_tier.py` — 增 NRT/JPY 匹配用例（扩 helper 支持 origin/currency/section_code）。
- 改 `backend/tests/services/step2_bidding/test_customer_a_parse.py` — 增 NRT 段进 handled-rowset 断言。
- 改 `frontend/src/pages/RateSheetBuilder.tsx` — air 会话起运/币种 + 添加行 + buildFinalRows 盖章。
- 改 `frontend/src/i18n/{zh,ja,en}.json` — 新增 `addRow`。

任务顺序：Task1 matcher 后端 → Task2 customer_a 后端 → Task3 前端 → Task4 全量验证+手测。

---

## Task 1: matcher gate 加 NRT + 更新过时断言 + NRT/JPY 匹配测试

**Files:**
- Modify: `backend/app/services/step2_bidding/rate_matcher.py:21`
- Modify: `backend/tests/services/step2_bidding/test_rate_matcher.py:167-174`
- Modify: `backend/tests/services/step2_bidding/test_rate_matcher_tier.py`（helper + 新用例）

- [ ] **Step 1: 扩 tier 测试 helper 支持 origin/currency/section_code**

在 `test_rate_matcher_tier.py` 把 `_add_tier_batch` 与 `_pkg_row` 改为可传 origin/currency/section_code（默认值保持旧行为）：

`_add_tier_batch` 签名与 AirTierRate 构造改为：
```python
def _add_tier_batch(session, *, destination, tier_prices, service_desc="平散货", origin="PVG", currency="CNY"):
    batch = ImportBatch(
        batch_id=uuid.uuid4(),
        file_type=ImportBatchFileType.air_tier,
        effective_from=date(2026, 5, 21),
        row_count=1,
        status=ImportBatchStatus.active,
    )
    session.add(batch)
    session.flush()
    session.add(
        AirTierRate(
            origin=origin,
            destination=destination,
            service_desc=service_desc,
            tier_prices=tier_prices,
            effective_from=date(2026, 5, 21),
            currency=currency,
            remark="以上价格均已包含附加费（燃油/战险/地面操作），但不含杂费",
            batch_id=batch.batch_id,
        )
    )
    session.commit()
```

`_pkg_row` 增加 `section_code` / `origin_code` 形参（默认 PVG）：
```python
def _pkg_row(*, destination_code="ATL", volume_desc, currency="CNY", section_code="PVG", origin_code="PVG") -> PkgRow:
    return PkgRow(
        row_idx=12,
        section_index=1,
        section_code=section_code,
        origin_code=origin_code,
        origin_text_raw="中国 (上海)",
        destination_text_raw="アメリカ (アトランタ)",
        destination_code=destination_code,
        cost_type=CostType.AIR_FREIGHT,
        currency=currency,
        volume_desc=volume_desc,
        existing_price=None,
        existing_lead_time=None,
        existing_carrier=None,
        existing_remark=None,
        is_example=False,
        client_constraint_text=None,
    )
```

- [ ] **Step 2: 写失败测试（NRT/JPY 日本段匹配）**

在 `test_rate_matcher_tier.py` 末尾新增：
```python
def test_nrt_jpy_japan_segment_matches(db_session):
    """日本段(NRT/JPY)手录档位 → 不再 NON_LOCAL_LEG，按想定平均重量选档命中。"""
    _add_tier_batch(db_session, destination="ATL", tier_prices={"100": 450.0, "300": 430.0},
                    origin="NRT", currency="JPY")
    matcher = RateMatcher(Step1RateRepository(db_session))
    row = _pkg_row(section_code="NRT", origin_code="NRT", currency="JPY",
                   volume_desc="1件当たりの想定平均重量：150kg/shipment")
    status, cands = matcher.match(row, effective_on=date(2026, 5, 25))
    assert status == RowStatus.FILLED
    assert len(cands) == 1
    assert cands[0].cost_price == Decimal("450.0")  # 150kg → 100KG 档
    assert cands[0].currency == "JPY"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_rate_matcher_tier.py::test_nrt_jpy_japan_segment_matches -v`
Expected: FAIL —— status == `NON_LOCAL_LEG`（NRT 不在 `_LOCAL_SECTION_CODES`），断言 FILLED 失败。

- [ ] **Step 4: matcher 加 NRT**

`rate_matcher.py:21`：
```python
_LOCAL_SECTION_CODES: frozenset[str] = frozenset({"PVG"})
```
改为：
```python
# 我们处理(匹配+回填)的起运段：PVG 上海发 / NRT 成田发(日本段 JPY)。其余段(AMS/TPE/ICN)暂 NON_LOCAL_LEG。
_LOCAL_SECTION_CODES: frozenset[str] = frozenset({"PVG", "NRT"})
```

- [ ] **Step 5: 更新过时断言 V-B5-01（NRT→AMS）**

`test_rate_matcher.py:167-174` 把用例改用仍未实装的 AMS 段（保留「未处理段→NON_LOCAL_LEG」原意）：
```python
def test_v_b5_01_non_local_leg(db_session: Session):
    """V-B5-01：未实装的起运段(如 AMS) → NON_LOCAL_LEG。
    (NRT 自 2026-06 日本段 JPY 起改为已处理段，故本用例改用 AMS。)"""
    repo = Step1RateRepository(db_session)
    matcher = RateMatcher(repo)
    row = _make_pkg_row(section_code="AMS")
    status, candidates = matcher.match(row, effective_on=date(2026, 4, 22))
    assert status == RowStatus.NON_LOCAL_LEG
    assert candidates == []
```

- [ ] **Step 6: 跑测试确认通过 + matcher 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_rate_matcher.py tests/services/step2_bidding/test_rate_matcher_tier.py -q`
Expected: 全 PASS（新 NRT/JPY 用例 + V-B5-01(AMS) + 既有 PVG 用例都过）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/step2_bidding/rate_matcher.py backend/tests/services/step2_bidding/test_rate_matcher.py backend/tests/services/step2_bidding/test_rate_matcher_tier.py
git commit -m "feat(step2): matcher 处理日本段(NRT)——_LOCAL_SECTION_CODES 加 NRT, 按 NRT/JPY 匹配档位价

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: customer_a gate 加 NRT（fill 自动覆盖日本段）

**Files:**
- Modify: `backend/app/services/step2_bidding/customer_profiles/customer_a.py:74`
- Modify: `backend/tests/services/step2_bidding/test_customer_a_parse.py`（增 rowset 断言）

- [ ] **Step 1: 写失败测试（NRT 段进 handled-rowset）**

在 `test_customer_a_parse.py` 末尾新增（复用模块级 `parsed` fixture + `CustomerAProfile`）：
```python
def test_nrt_section_now_handled(parsed: ParsedPkg):
    """日本段(NRT)自 2026-06 纳入处理段：is_local_section=True 且进入 fill 的 _pvg_rowset。"""
    nrt = next(s for s in parsed.sections if s.section_code == "NRT")
    assert nrt.is_local_section is True
    rowset = CustomerAProfile._pvg_rowset(parsed)
    nrt_row_idxs = [r.row_idx for r in parsed.rows if r.section_code == "NRT"]
    assert nrt_row_idxs, "样本应有 NRT 段行"
    assert all(idx in rowset for idx in nrt_row_idxs), "NRT 段行应全部进入 fill 行集"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_customer_a_parse.py::test_nrt_section_now_handled -v`
Expected: FAIL —— `nrt.is_local_section` 当前为 False（仅 PVG True）。

- [ ] **Step 3: customer_a 加 NRT**

`customer_a.py:74`：
```python
_LOCAL_SECTION_CODES = {"PVG"}
```
改为：
```python
# 我们处理(匹配+回填)的起运段：PVG 上海发 / NRT 成田发(日本段 JPY)。其余段暂不处理。
_LOCAL_SECTION_CODES = {"PVG", "NRT"}
```

- [ ] **Step 4: 跑测试确认通过 + customer_a 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_customer_a_parse.py tests/services/step2_bidding/test_customer_a_fill.py -q`
Expected: 全 PASS。新断言过；既有 fill 用例不破——`_happy_reports` 给 NRT 行的 report 状态是 `NON_LOCAL_LEG`，`_targets_for_status(NON_LOCAL_LEG)=_ALL_KEEP` → NRT 单元格不写、`test_v_b7_04_non_pvg_zero_diff` 仍成立。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step2_bidding/customer_profiles/customer_a.py backend/tests/services/step2_bidding/test_customer_a_parse.py
git commit -m "feat(step2): customer_a 把日本段(NRT)纳入处理段, fill 随 is_local_section 覆盖 NRT 段

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 前端 air 做表会话起运/币种 + 审核台手动添加行

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`
- Modify: `frontend/src/i18n/{zh,ja,en}.json`

- [ ] **Step 1: i18n 加 `addRow`（三语）**

在三份 JSON 的 `rateSheet` 对象内（紧跟 `commit` 键之后）加：
- zh.json: `"addRow": "＋手动添加行",`
- ja.json: `"addRow": "＋手動で行追加",`
- en.json: `"addRow": "+ Add row",`

- [ ] **Step 2: 引入 Select + 会话起运/币种 state**

`RateSheetBuilder.tsx`：把 antd import 行加上 `Select`：
```tsx
import { Upload, Input, InputNumber, Table, Tooltip, message, Select } from 'antd';
```
在现有 `useState` 区（`editedRows` 之后）加：
```tsx
  // air 做表会话级起运港 + 币种(默认 PVG/CNY；日本段选 NRT/JPY)。中国段默认不变。
  const [sessionOrigin, setSessionOrigin] = useState<string>('PVG');
  const [sessionCurrency, setSessionCurrency] = useState<string>('CNY');
```

- [ ] **Step 3: buildFinalRows 给 air 行盖 origin/currency**

把 A4 已有的 `buildFinalRows` 里 `if (templateType === 'sea') { ... }` 块之后、`return merged;` 之前，追加 air 分支：
```tsx
        if (templateType === 'air') {
          merged.origin = sessionOrigin;
          merged.currency = sessionCurrency;
        }
```

- [ ] **Step 4: 手动添加行 handler**

在 `buildFinalRows` 定义之后新增：
```tsx
  // 手动添加一条 air 档位行(默认 5 档)，用于无文件来源的手录(如日本段 NRT/JPY)。
  const handleAddRow = () => {
    const nextRid = rows.length ? Math.max(...rows.map((r) => r._rid ?? 0)) + 1 : 0;
    const newRow: PreviewRow = {
      _rid: nextRid,
      origin: sessionOrigin,
      destination: '',
      service: '',
      currency: sessionCurrency,
      tier_prices: { '45': null, '100': null, '300': null, '500': null, '1000': null },
    };
    setRows((prev) => [...prev, newRow]);
    setSelectedRowKeys((prev) => [...prev, nextRid]);
    setSummary((s) => s ?? { total_rows: 0, needs_review: 0 });
  };
```

- [ ] **Step 5: air 模板下显示起运港/币种选择器**

在模板选择 chip-group（`rateSheet.step1` 卡片的 `chip-group` div）之后、卡片 `card-body` 结束前，加 air 专属控件：
```tsx
            {templateType === 'air' && (
              <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <span>{t('rateSheet.colOrigin')}</span>
                <Select size="small" value={sessionOrigin} onChange={setSessionOrigin} style={{ width: 96 }}
                  options={[{ value: 'PVG', label: 'PVG' }, { value: 'NRT', label: 'NRT' }]} />
                <span>{t('rateSheet.colCurrency')}</span>
                <Select size="small" value={sessionCurrency} onChange={setSessionCurrency} style={{ width: 96 }}
                  options={[{ value: 'CNY', label: 'CNY' }, { value: 'JPY', label: 'JPY' }]} />
              </div>
            )}
```

- [ ] **Step 6: 审核台「＋手动添加行」按钮 + 预览表无 summary 也显示**

(a) 预览 `Table` 渲染条件：把 `{summary ? (` 改为 `{(summary || rows.length > 0) ? (`；KPI 的 `summary.total_rows` 改 `(summary?.total_rows ?? rows.length)`、`summary.needs_review` 改 `(summary?.needs_review ?? 0)`。

(b) 在 `rateSheet.step3` 卡片头(`card-head`，下载/入库按钮所在 div)内，air 时加添加行按钮（放在下载按钮之前）：
```tsx
          {templateType === 'air' && (
            <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }}
              disabled={!sessionId} onClick={handleAddRow}>
              {t('rateSheet.addRow')}
            </button>
          )}
```
> 注：原下载/入库按钮的 `marginLeft:'auto'` 已把它们推到右侧；新增按钮加 `marginLeft:'auto'` 会与之冲突。实现时确保**只有第一个出现的按钮**带 `marginLeft:'auto'`（把 auto 挪到添加行按钮，下载/入库改 `marginLeft: 8`）。

- [ ] **Step 7: 类型检查 / 构建**

Run: `cd frontend && npm run build`
Expected: tsc-b + vite build 通过，无 TS 报错。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "feat(step1): air 做表会话级起运港/币种 + 审核台手动添加行(支持手录 NRT/JPY 日本段)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 全量验证 + 端到端手测

**Files:** 无（验证）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全 PASS（基线 376 passed + 本轮新增；仅 3 个 `test_ai_client` vLLM 环境失败为既有无关项）。

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 3: 端到端手测（前后端 :8000/:5173，硬刷新）**

1. 运价表生成 → 选 **Air** → 起运港选 **NRT**、币种选 **JPY**。
2. 点「＋手动添加行」数次，手录日本段：目的港填 ATL/MIA/AMS…，在 100KG 等档位列填 JPY 价（如 450）。
3. 「确认入库」→ 提示已入库 N 条重量档运价。
4. 切到 PkgAutoFill，上传 `资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx`。
5. 预览/下载结果：**日本段(成田) 単価(円/kg) 被填上**对应档位价；中国段(上海/CNY)不受影响；本地配送费(LOCAL DELIVERY)行仍空(本版 manual)。

- [ ] **Step 4: 记录结果回报用户（每条 OK/NG + 证据）。NG 则定位回对应 Task。**

---

## Self-Review（写完已自检）

- **Spec 覆盖**：Part1 后端 gate(Task1 matcher + Task2 customer_a)、Part2 前端手录(Task3)、回填验证(Task2 rowset + Task4 手测)、成功标准(Task4)——spec 各节均有任务。AMS/TPE/ICN 仅做 NRT 的范围在头部说明。
- **占位符**：无 TBD/TODO；每个改码步骤含完整代码与确切命令。
- **类型一致**：`_add_tier_batch`/`_pkg_row` 扩参默认值向后兼容；`sessionOrigin`/`sessionCurrency`(Task3 Step2)→ buildFinalRows(Step3)/handleAddRow(Step4)/选择器(Step5) 命名一致；`PreviewRow` 的 origin/currency/tier_prices 字段 A4 已定义。
- **回归风险**：① `test_rate_matcher.py` V-B5-01 过时断言已在 Task1 Step5 显式改 AMS；② 既有 fill 测试不破已论证(NON_LOCAL_LEG→_ALL_KEEP)；③ 前端预览表无 summary 显示 + 按钮 marginLeft 冲突已在 Task3 Step6 标注处理。
