# 统一运价入库口 — Phase 2 实现计划（Option A：只清死路）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 删除 Phase 1 后已成死代码的冗余入库/解析路径，让运价入库只剩两条各司其职的活路：①「文件导入 = `draft→activate`」②「AI 解析 = `/ai/confirm`」。**不动在用的 `/ai/confirm`**。

**背景（勘探已确认，2026-06-06）：**
- `/rates/upload/parse` + `/rates/upload/confirm`（rates.py 的 `upload_and_parse`/`confirm_import`）：**死**。前端 Excel tab 在 Phase 1 已改走 `rateBatchApi.upload`(draft→activate)；`rateApi.confirmImport` 只在 `isAi ? ai : rate` 三元的 false 分支，而 `parseResult` 只由 AI 路设置 → `isAi` 恒 true → 永不调用。无测试覆盖。
- `import_data.py`（`/import/tariffs`、`/import/preview`）+ `import_service.py`（写老 `Tariff` 表）：**死且未挂载**。`router.py` 根本没 include import_data_router；前端零调用；除 import_data 自引 import_service 外无引用。
- `/ai/confirm`（ai_parse.py，微信/邮件 AI 解析 → `import_parsed_rates` → FreightRate，additive）：**活**，demo 在用 → **保留不动**。
- `import_parsed_rates`（rate_parser.py）：删 `/rates/upload/confirm` 后仍被 `/ai/confirm` 用 → **保留**。
- `_parse_cache`（定义在 rates.py，被 ai_parse.py import + ai_parse 的 parse 端点写入 + `/ai/confirm` 读）→ **保留在 rates.py**（仅加注释说明归属 AI 流）。
- `tariffs.py` / `lanes.py` 也未在 router.py 注册，但**不在本次范围**（与"运价入库路"无关，可能是预留），不动。

**验证基线：** 后端全量 440 passed / 3 failed（仅 test_ai_client 的 3 个 vLLM，无关）；前端 build 通过。

---

## Task 1: 后端删死路

**Files:**
- Modify: `backend/app/api/v1/rates.py`（删 `upload_and_parse` + `confirm_import` 两个端点 + 清理因此变无用的 import）
- Delete: `backend/app/api/v1/import_data.py`
- Delete: `backend/app/services/import_service.py`

- [ ] **Step 1: 删 rates.py 两个死端点**

删除 `@router.post("/upload/parse")` 的 `upload_and_parse` 函数、`@router.post("/upload/confirm")` 的 `confirm_import` 函数（整段）。
- **保留** `_parse_cache: dict[str, dict] = {}`（ai_parse.py 仍 import 它），在其上方加注释：`# AI 解析(/ai/parse-*) 暂存解析结果供 /ai/confirm 入库；文件导入已改走 draft→activate`。
- 顶部 `from app.services.rate_parser import (detect_and_parse, import_parsed_rates, ...)` 里删掉删端点后**不再被 rates.py 用到**的名字（`detect_and_parse`、`import_parsed_rates`——确认 rates.py 内无其它引用后删；若该 import 块还有别的名字被其它端点用，保留那些）。
- 删除仅被这两个端点用到的其它 import（如 `os`/`uuid`/`settings` 中确已无用者——**逐个 grep rates.py 确认无其它使用再删**，不确定就留着，避免误删）。

- [ ] **Step 2: 删死文件**

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神
git rm backend/app/api/v1/import_data.py backend/app/services/import_service.py
```
（`router.py` 无需改——它本就没 include import_data_router；删前用 `grep -rn "import_data\|import_service" backend/app | grep -v __pycache__` 复核确认除被删文件外无引用。）

- [ ] **Step 3: 残留与回归验证**

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神
grep -rn "upload_and_parse\|confirm_import\|import_data\|import_service\|/upload/parse\|/upload/confirm" backend/app | grep -v __pycache__   # 期望:空(rates.py 残留 confirm_import 名字应已无)
cd backend && ../.venv/bin/python -c "from app.api.v1.ai_parse import _parse_cache; print('ai_parse 仍能 import _parse_cache OK')"
../.venv/bin/python -m pytest -q   # 期望: 440(±) passed, 仅 3 个 test_ai_client vLLM failed
```
> ⚠️ 若 `import_parsed_rates`/`detect_and_parse` 删 import 后有 NameError，或 ai_parse import _parse_cache 失败，说明清过头，回补。`/ai/confirm` 路径必须仍可用（ai_parse 直接 `from app.services.rate_parser import import_parsed_rates`，不依赖 rates.py 的 import）。

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/v1/rates.py
git rm backend/app/api/v1/import_data.py backend/app/services/import_service.py
git commit -m "refactor(step1): Phase2 清死路-删 rates /upload/parse+confirm 旧直写 + 未挂载的 import_data/import_service(Tariff)"
```

---

## Task 2: 前端清死分支

**Files:**
- Modify: `frontend/src/services/api.ts`（删 `rateApi.confirmImport`）
- Modify: `frontend/src/pages/RateUpload.tsx`（`handleConfirm` 去掉死三元，固定走 `aiParseApi.confirmImport`）

- [ ] **Step 1: api.ts 删 rateApi.confirmImport**

删除 `rateApi` 对象里的 `confirmImport`（约 102 行，POST `/rates/upload/confirm` 的那个）。**保留** `aiParseApi.confirmImport`（约 161 行，POST `/ai/confirm`）。先 grep 确认 `rateApi.confirmImport` 仅 RateUpload.tsx 用。

- [ ] **Step 2: RateUpload.tsx 简化 handleConfirm**

把：
```ts
      const isAi = ['email_text', 'wechat_image', 'inbox_email', 'inbox_attachment'].includes(
        parseResult.source_type
      );
      const fn = isAi ? aiParseApi.confirmImport : rateApi.confirmImport;
      const res = await fn(parseResult.batch_id);
```
改为（parseResult 只由 AI 路产生，恒走 AI confirm）：
```ts
      const res = await aiParseApi.confirmImport(parseResult.batch_id);
```
删除随之无用的 `rateApi` import（若 RateUpload 其它处仍用 rateApi 则保留；先 grep `rateApi` 在该文件的全部使用）。

- [ ] **Step 3: 残留 + 构建验证**

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神/frontend
grep -rn "rateApi.confirmImport\|/rates/upload/confirm\|/rates/upload/parse" src/   # 期望:空
npm run build   # 期望: 通过(tsc 不报未用 import / 未定义)
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/services/api.ts frontend/src/pages/RateUpload.tsx
git commit -m "refactor(step1): Phase2 前端清死分支-handleConfirm 固定走 AI confirm + 删 rateApi.confirmImport"
```

---

## 收尾验收

- [ ] 后端全量 pytest：440(±) passed，仅 3 个 test_ai_client vLLM failed（无新增失败）。
- [ ] 前端 build 通过。
- [ ] `/ai/confirm` 微信解析路仍可用（ai_parse 未被触碰）。
- [ ] grep 确认死端点/死文件无残留引用。

## 验收对照（用户诉求 → 结果）
- 用户要"顺手收敛老入库路" → 删掉全部死的冗余入库/解析端点；活路只剩「文件导入=draft→activate」+「AI 解析=ai/confirm」两条，各司其职、无冗余。
- 未动在用 demo 的 AI 路（低风险）；其与 activator 的语义冲突(additive vs supersede)记录在案，若日后要真合并另起子项目。
