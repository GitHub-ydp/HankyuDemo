# 设计 — 运价表生成器审核台：勾选保留 + 手工编辑

- **日期**：2026-05-28
- **分支**：`feature/step1-review-desk`（从 `main` 切出）
- **背景**：运价表生成器目前审核台只「展示 + 标 needs_review」，下载是把 `session.rows`
  **全部**填进模板，人工无法干预。本设计补齐「人工选哪几行保留」+「手工修改任意单元格值」，
  让销售在下载前完成审核与微调。

## 一、目标与范围

**做：**
- 预览表升级为「可勾选 + 可编辑」的审核台。
- 勾选：任意行可保留/排除（默认全选），排除的行不进最终运价表。
- 编辑：所有数据列可直接点格编辑（数值列 / 文本列）。
- 顶部汇总实时反映「将要下载」的最终状态。
- 下载：把「勾选 × 编辑后」的最终行交给后端填模板，一键拿回 xlsx。

**不做（YAGNI / 本轮范围外）：**
- 新增整行（从零造行）。
- 编辑/勾选状态的服务端持久化（采用方案 A：纯前端状态，刷新即失——会话本就内存态）。
- 多报价的「自动推荐取哪条」（仍由人工选）。

## 二、方案（已确认 = 方案 A）

状态全在浏览器，点「下载」时把最终行 POST 给后端、直接返回 xlsx。后端只多一个
「按给定行填模板」的接口，不改 `session.rows`。代价：真刷新页面会丢失编辑（demo 可接受）。

**架构边界**：前端负责「选 / 改 / 组装最终行」，后端负责「按给定行填模板」。两者通过
一个无状态的 POST 接口通信，各自独立可测。

## 三、交互设计（UX）

预览区（③ 审核与下载）：

- **最左勾选列**：默认全选；表头勾选框一键全选/全清。取消勾选的行 **置灰**（`opacity:.4`，
  仍可见、可再勾回），不进下载。
- **所有数据格点击即编辑**（无需双击/进入编辑态）：
  - 数值列（sea 运费 20/40、air 第1~7日价）→ `InputNumber`
  - 文本列（目的港 / 船司 / 服务 / 备注）→ `Input`
  - `待确认` 列仍为只读 Tag
- **顶部汇总实时变**：`汇总 = 勾选数 / 原始总数`；`待确认 = (勾选且 needs_review)数 / 原始 needs_review 数`。
- **下载按钮**：勾选数 = 0 时禁用；否则 POST 最终行 → 下载 xlsx。

## 四、前端改动（`frontend/src/pages/RateSheetBuilder.tsx` + `services/api.ts`）

**状态（客户端，刷新即失）：**
- 预览行到达时给每行打稳定客户端 id `_rid`（0..n-1），**用 `_rid` 做 rowKey**，
  不用数组下标——规避分页时下标错位导致勾选/编辑串行。
- `selectedRowKeys: _rid[]`，上传后默认置为全部。
- `editedRows: Record<_rid, Partial<行>>`，编辑覆盖层；显示值 = `editedRows[rid]?.[列] ?? 原行[列]`。
- 每次新预览到达：重打 `_rid`、`selectedRowKeys` 全选、`editedRows` 清空。

**表格：**
- AntD `rowSelection`（自带勾选框 + 表头全选），`selectedRowKeys` 绑定状态。
- `rowClassName`：未勾选 → `row-excluded`（置灰，优先）；needs_review 行保留 `row-needs-review`。
- 列 `render` 成输入框（数值 `InputNumber` / 文本 `Input`），`onChange` 写 `editedRows`。
- 分页 20/页不变（每页只渲染当页输入框，340 行不卡）。

**下载：**
- `finalRows = rows.map(套用 editedRows).filter(在 selectedRowKeys 内)`，剥掉 `_rid`。
- `api.ts` 新增 `downloadFilled(sessionId, rows)`：axios POST `responseType:'blob'` → 得 xlsx blob
  → `URL.createObjectURL` + 隐藏 `<a>` 触发下载。
- `.row-excluded{opacity:.4}` 加到现有样式表。

## 五、后端改动（`backend/app/api/v1/rate_sheet.py`）

新增 POST 下载接口（与现有 GET 同路径、不同方法）：

```
POST /api/v1/rate-sheet/{session_id}/download
body: { "rows": [ {归一行...}, ... ] }
```

- 取 `session`（不存在 → 404），仅用其 `template_type` 选模板；行用 body 的，不读 `session.rows`。
- 调 `fill_template(session.template_type, body.rows)` → `StreamingResponse` 返回 xlsx。
- Pydantic：`class DownloadRequest(BaseModel): rows: list[dict[str, Any]]`。
- `fill_template` 只读它认识的字段，前端多带的 `_rid / needs_review / source_file` 等被忽略。
- **现有 `GET /download`（读 session.rows 填全部）保留不动**——回退用，且老测试不挂。

## 六、测试

**后端（TDD）：**
- `POST /download` 带显式 rows → 200、content-type 为 xlsx、body 非空；
  **用已知值核验**（填一行 → openpyxl 重开 → 断言该值在位）。
- `POST /download` + 不存在 session → 404。
- 全量回归确认 GET 老路径不受影响。

**前端：** 无单测框架 → `tsc -b` + `vite build` + UI 验收。

## 七、边界 / 已知取舍

- 刷新页面丢失勾选/编辑（方案 A，内存会话，demo 接受）。
- 空选（全不勾）→ 按钮禁用，不会产出空表。
- Sea 一行在 `_fill_sea` 里展开成 20FT/40FT 两行；编辑发生在归一行层（freight_20/40 各填到对应输出行）。
- 不支持新增整行。
