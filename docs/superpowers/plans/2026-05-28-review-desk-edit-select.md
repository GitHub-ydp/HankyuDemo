# 审核台勾选保留 + 手工编辑 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让运价表生成器审核台支持「任意行勾选保留/排除 + 所有数据格手工编辑」，下载时把「勾选×编辑后」的最终行 POST 给后端填模板。

**Architecture:** 方案 A — 勾选/编辑状态全在前端（刷新即失，内存会话可接受）。后端只新增一个无状态接口 `POST /rate-sheet/{id}/download`，接收前端传来的行、用 `fill_template` 填模板返回 xlsx；不改 `session.rows`，`GET /download` 保留兜底。

**Tech Stack:** FastAPI + pydantic（后端）；React 19 + TS + Ant Design v6（前端，AntD `rowSelection` / `InputNumber` / `Input`）。

设计文档：`docs/superpowers/specs/2026-05-28-review-desk-edit-select-design.md`

---

## 文件结构

- 改 `backend/app/api/v1/rate_sheet.py`：加 `DownloadRequest` 模型 + `POST /download` 接口
- 改 `backend/tests/sheet_builder/test_rate_sheet_api.py`：加 2 个测试
- 改 `frontend/src/services/api.ts`：加 `downloadFilled(sessionId, rows)`
- 改 `frontend/src/i18n/{zh,ja,en}.json`：加 `rateSheet.downloadFailed`
- 改 `frontend/src/pages/RateSheetBuilder.tsx`：勾选 + 行内编辑 + 实时汇总 + POST 下载
- 改 `frontend/src/styles/design.css`：`.row-excluded` / `.row-needs-review`

---

## Task 1: 后端 `POST /download`（按给定行填模板）

**Files:**
- Modify: `backend/app/api/v1/rate_sheet.py`
- Test: `backend/tests/sheet_builder/test_rate_sheet_api.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/sheet_builder/test_rate_sheet_api.py` 末尾追加：

```python
def test_download_post_fills_given_rows(client):
    from io import BytesIO
    from openpyxl import load_workbook

    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    sid = r.json()["data"]["session_id"]

    rows = [{"destination": "OSAKA", "carrier": "ONE", "freight_20": 111, "freight_40": 222}]
    r = client.post(f"/api/v1/rate-sheet/{sid}/download", json={"rows": rows})

    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx = zip
    ws = load_workbook(BytesIO(r.content))["JP N RATE FCL & LCL"]
    assert ws.cell(9, 1).value == "OSAKA"  # 数据起始行 r9, A=目的港
    assert ws.cell(9, 4).value == 111      # D=运费, 20FT 行取 freight_20


def test_download_post_unknown_session_404(client):
    r = client.post("/api/v1/rate-sheet/does-not-exist/download", json={"rows": []})
    assert r.json()["code"] == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_rate_sheet_api.py::test_download_post_fills_given_rows -v`
Expected: FAIL（POST 未定义 → 405 Method Not Allowed，`r.content[:2]` 非 `PK`）

- [ ] **Step 3: 实现接口**

在 `backend/app/api/v1/rate_sheet.py` 顶部 import 区补两行：

```python
from typing import Any

from pydantic import BaseModel
```

在文件末尾（`GET /download` 之后）追加：

```python
class DownloadRequest(BaseModel):
    rows: list[dict[str, Any]]


@router.post("/{session_id}/download")
def download_rate_sheet_post(session_id: str, body: DownloadRequest):
    """按前端传来的「勾选+编辑后」最终行填模板并返回 xlsx（不读 session.rows）。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    content, filename = fill_template(session.template_type, body.rows)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_rate_sheet_api.py -v`
Expected: PASS（含新增 2 个 + 原有全绿）

- [ ] **Step 5: 全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 仅原有 3 个 `test_ai_client`(vllm) 失败，其余全绿

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/rate_sheet.py backend/tests/sheet_builder/test_rate_sheet_api.py
git commit -m "feat(step1): 审核台下载接口 POST /download(按给定行填模板)"
```

---

## Task 2: 前端 API 层 + i18n

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/i18n/zh.json` / `ja.json` / `en.json`

- [ ] **Step 1: api.ts 加 downloadFilled**

把 `rateSheetApi` 里的 `downloadUrl` 项替换为（保留 downloadUrl，并新增 downloadFilled）：

```ts
  downloadUrl: (sessionId: string) =>
    `${api.defaults.baseURL}/rate-sheet/${sessionId}/download`,
  downloadFilled: (sessionId: string, rows: unknown[]): Promise<Blob> =>
    api.post<unknown, Blob>(
      `/rate-sheet/${sessionId}/download`,
      { rows },
      { responseType: 'blob' },
    ),
```

（响应拦截器返回 `response.data`，`responseType:'blob'` 时即 Blob。）

- [ ] **Step 2: 三语补 downloadFailed**

`zh.json` 在 `"download"` 行后加：`"downloadFailed": "下载失败",`
`ja.json` 在 `"download"` 行后加：`"downloadFailed": "ダウンロード失敗",`
`en.json` 在 `"download"` 行后加：`"downloadFailed": "Download failed",`

- [ ] **Step 3: 提交**

```bash
git add frontend/src/services/api.ts frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "feat(step1): 前端运价表 POST 下载接口 + downloadFailed 文案"
```

---

## Task 3: 审核台勾选 + 行内编辑 + 实时汇总 + 下载

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`
- Modify: `frontend/src/styles/design.css`

- [ ] **Step 1: import 补 Input/InputNumber**

把 antd import 里加入 `Input, InputNumber`（与现有 `Table, Tag` 等并列）。

- [ ] **Step 2: PreviewRow 加 _rid**

在 `interface PreviewRow {` 第一行加：`  _rid?: number;`

- [ ] **Step 3: 加勾选/编辑状态**

在 `const [uploading, setUploading] = useState(false);` 之后加：

```tsx
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [editedRows, setEditedRows] = useState<Record<number, Partial<PreviewRow>>>({});
```

- [ ] **Step 4: 上传后初始化勾选/编辑**

把 `handleUpload` 里的
```tsx
        if (pv.code === 0) {
          setRows((pv.data as { rows: PreviewRow[] }).rows);
        }
```
替换为：
```tsx
        if (pv.code === 0) {
          const pvRows = (pv.data as { rows: PreviewRow[] }).rows.map((r, i) => ({ ...r, _rid: i }));
          setRows(pvRows);
          setSelectedRowKeys(pvRows.map((r) => r._rid as number));
          setEditedRows({});
        }
```

- [ ] **Step 5: 加取值/改值/列工厂**

在 `const statusTag = ...` 之前加：

```tsx
  const valueOf = (r: PreviewRow, field: keyof PreviewRow) =>
    ({ ...r, ...editedRows[r._rid as number] })[field];

  const editCell = (rid: number, field: keyof PreviewRow, value: unknown) =>
    setEditedRows((prev) => ({ ...prev, [rid]: { ...prev[rid], [field]: value } }));

  const textCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    render: (_: unknown, r: PreviewRow) => (
      <Input
        size="small"
        value={(valueOf(r, field) as string) ?? ''}
        onChange={(e) => editCell(r._rid as number, field, e.target.value)}
      />
    ),
  });

  const numCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    render: (_: unknown, r: PreviewRow) => (
      <InputNumber
        size="small"
        style={{ width: '100%' }}
        value={valueOf(r, field) as number | null | undefined}
        onChange={(v) => editCell(r._rid as number, field, v)}
      />
    ),
  });

  const reviewCol = {
    title: t('rateSheet.needsReview'),
    key: 'needs_review',
    render: (_: unknown, r: PreviewRow) =>
      r.needs_review ? <Tag color="orange">{t('rateSheet.needsReview')}</Tag> : null,
  };
```

- [ ] **Step 6: 用列工厂重写 sea/air 列**

把现有 `baseCols` / `seaCols` / `airDayCols` / `airCols` / `previewCols` 整段替换为：

```tsx
  const seaCols = [
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colCarrier'), 'carrier'),
    numCol(t('rateSheet.colFreight20'), 'freight_20'),
    numCol(t('rateSheet.colFreight40'), 'freight_40'),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  const airCols = [
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colService'), 'service'),
    ...Array.from({ length: 7 }, (_, i) =>
      numCol(t('rateSheet.colDay', { n: i + 1 }), `day${i + 1}` as keyof PreviewRow),
    ),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  const previewCols = templateType === 'air' ? airCols : seaCols;
```

- [ ] **Step 7: 实时汇总 + 下载 handler**

把现有 `handleDownload` 替换为：

```tsx
  const keptCount = selectedRowKeys.length;
  const keptReview = rows.filter(
    (r) => selectedRowKeys.includes(r._rid as number) && r.needs_review,
  ).length;

  const handleDownload = async () => {
    if (!sessionId) return;
    const finalRows = rows
      .filter((r) => selectedRowKeys.includes(r._rid as number))
      .map((r) => {
        const merged = { ...r, ...editedRows[r._rid as number] };
        delete (merged as { _rid?: number })._rid;
        return merged;
      });
    try {
      const blob = await rateSheetApi.downloadFilled(sessionId, finalRows);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${templateType ?? 'rate'}_rate_sheet_filled.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error(t('rateSheet.downloadFailed'));
    }
  };
```

- [ ] **Step 8: 下载按钮禁用条件改用 keptCount**

把 step3 卡片 extra 里的下载按钮
```tsx
          <Button type="primary" disabled={!summary || summary.total_rows === 0} onClick={handleDownload}>
```
改为：
```tsx
          <Button type="primary" disabled={!summary || keptCount === 0} onClick={handleDownload}>
```

- [ ] **Step 9: 汇总 Statistic 改为「勾选/总数」实时值**

把两个 `Statistic` 替换为：
```tsx
              <Col>
                <Statistic title={t('rateSheet.summaryTotal')} value={`${keptCount} / ${summary.total_rows}`} />
              </Col>
              <Col>
                <Statistic
                  title={t('rateSheet.summaryReview')}
                  value={`${keptReview} / ${summary.needs_review}`}
                  valueStyle={{ color: keptReview > 0 ? '#F79009' : undefined }}
                />
              </Col>
```

- [ ] **Step 10: 预览表加 rowSelection + 置灰**

把预览 `<Table ...>`（step3 里那个，`columns={previewCols}` 的）改为带 `rowKey`/`rowSelection`/`rowClassName`：
```tsx
            <Table
              size="small"
              rowKey={(r: PreviewRow) => r._rid as number}
              rowSelection={{
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys as number[]),
              }}
              columns={previewCols}
              dataSource={rows}
              rowClassName={(r: PreviewRow) =>
                !selectedRowKeys.includes(r._rid as number)
                  ? 'row-excluded'
                  : r.needs_review
                    ? 'row-needs-review'
                    : ''
              }
              pagination={{ pageSize: 20 }}
            />
```

- [ ] **Step 11: CSS 加置灰/底色**

在 `frontend/src/styles/design.css` 末尾加：
```css
.row-excluded td { opacity: 0.4; }
.row-needs-review td { background: #fffbe6; }
```

- [ ] **Step 12: 类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: `tsc -b` 无类型错误，`vite build` 成功

- [ ] **Step 13: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx frontend/src/styles/design.css
git commit -m "feat(step1): 审核台支持勾选保留/置灰 + 行内编辑 + 实时汇总 + POST 下载"
```

---

## Task 4: 端到端 HTTP 自检（交付前）

**Files:** 无（验证）

- [ ] **Step 1: 重启后端加载新接口**

```bash
PID=$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t); [ -n "$PID" ] && kill "$PID"; sleep 2
cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000 &
```

- [ ] **Step 2: POST /download 冒烟**

建 sea 会话 → `curl -X POST .../download -H 'Content-Type: application/json' -d '{"rows":[{"destination":"OSAKA","carrier":"ONE","freight_20":111,"freight_40":222}]}' -o /tmp/t.xlsx`，确认 `/tmp/t.xlsx` 是合法 xlsx（`file /tmp/t.xlsx` 显示 Excel）。

- [ ] **Step 3: 交付 UI 验收**

前端 dev server（5173）HMR 自动生效；通知用户做 UI 验收：上传 → 勾掉几行变灰 → 改几个价 → 看顶部汇总实时变 → 下载，确认 xlsx 只含勾选行且为编辑后的值。

---

## 自检对照（spec 覆盖）

- 任意行勾选保留/排除（默认全选、置灰）→ Task 3 Step 10/11 ✓
- 所有数据格可编辑（数值/文本）→ Task 3 Step 5/6 ✓
- 顶部汇总实时（勾选/总数、勾选且待确认/原始）→ Task 3 Step 7/9 ✓
- 下载走 POST blob、剥 _rid、空选禁用 → Task 3 Step 7/8 + Task 2 ✓
- 后端无状态 POST /download、GET 保留 → Task 1 ✓
- 测试：POST 填值核验 + 404 + 全量回归 → Task 1 ✓
