# 审计报告 — 运价表生成器（Rate Sheet Builder）

- **日期**：2026-05-27（连夜开发，晨审）
- **分支**：`feature/step1-rate-sheet-builder`（从 `feature/step2-nitori-demo` 切出）
- **目标**：按确认口径，把 step1 从「导入成品表」扶正为「**选模板 → 上传杂料 → AI 抽取 → 填进客户空白模板 → 人工审核 → 下载**」的运价表生成闭环。
- **计划文档**：`docs/superpowers/plans/2026-05-27-rate-sheet-builder.md`

---

## 一、本次交付（全部走 TDD，5 个 commit）

| # | 模块 | 文件 | 测试 |
|---|---|---|---|
| 1 | 模板注册表 | `sheet_builder/template_registry.py` + 内置模板 `templates/{air,sea}_blank.xlsx` | 3 |
| 2 | 模板填充器 | `sheet_builder/template_filler.py` | 3 |
| 3 | 会话编排 | `sheet_builder/orchestrator.py` | 5 |
| 4 | HTTP API | `api/v1/rate_sheet.py`（挂到 v1 router） | 3 |
| 5 | 前端页 | `pages/RateSheetBuilder.tsx` + `rateSheetApi` + 菜单/路由/i18n(zh/ja/en) | build 通过 |

**复用未改**：`rate_parser`(kmtc/nvo Excel)、`wechat_image_parser`(微信图)、`email_text_parser`(邮件)、`ai_client`、`writers/base.safe_set`。**新代码全在新子包/新 router/新页，未触碰现有 544 导入链路与 step2。**

## 二、数据流

```
选模板(air/sea) → 多文件上传 → orchestrator 按扩展名路由到对应 parser
  → 各 parser 抽取 parsed_rows → 归一为 filler 字段 → 汇总进会话
  → 同(目的港+船司)多条标 needs_review
  → template_filler 从数据起始行逐行写空白模板(保留表头/解除数据区合并) → xlsx
```

## 三、端到端验证证据（已真实跑通，非 mock）

用真实 DB(含字典) + 真实样本跑 `sea` 链路（Excel 不依赖 AI）：

```
parsed   excel        rows= 90   kmtc 运价表 0319.xlsx
parsed   excel        rows=250   NVO FAK 2026 (Mar 20 to Mar 31).xlsx
skipped  unsupported  rows=  0   LAX0751N25v93 (2).pdf   ← 友好降级
[汇总] 运价行=340  needs_review=310
[填模板核验] 表头 r8.A='To'（未被破坏）
  r9 : ['Busan/釜山', 'KMTC', '20FT', 130]
  r10: ['Busan/釜山', 'KMTC', '40FT/40HQ', 260]   ← 箱型展开正确
[产物] /tmp/sea_rate_sheet_filled.xlsx  43555 bytes（合法 xlsx）
```

## 四、测试结果

- **新增 14 个测试全绿**（registry 3 / filler 3 / orchestrator 5 / api 3）。
- **全量回归 273 passed**；4 个 `test_ai_client` 失败是 **pre-existing**（已用 `git stash` 验证：去掉本次全部改动后同样 4 failed）——根因本地未起 vllm（`vllm 502`）+ 缺 PIL。**本次已 `pip install Pillow`**，剩 vllm 健康检查需真实服务。

## 五、关键决策与取舍（自主决策记录）

1. **本轮支持来源**：结构化 Excel(kmtc/nvo)、微信图、邮件文本（抽取能力已成熟）。**EES 超复杂手册 / PDF(无库) / .xls(无 xlrd)** → 识别即友好跳过(skipped)，不报错。
2. **不入库**：需求是「做表」，产物即填好的 xlsx；入库留作后续。
3. **填充精度**：Sea 按 20FT/40FT 展开两行；**填充前解除数据区合并单元格**（否则合并从属格 value 只读会崩），数据正确优先于合并视觉。
4. **多报价**：同(目的港+船司)多条全部保留 + 标 `needs_review`，交审核台人工选——不替客户拍板。

## 六、已知问题 / 未完成（明早重点看 + 后续）

1. **`needs_review` 偏高(310/340)**：去重键 `(目的港,船司)` 对 NVO 这种同港多 service 的表过粗。**建议**：去重键并入 service/coast，或仅对"价格不同"才标。
2. **Air 来源抽取**：现有 parser 是海运向(container_*)，**不产 Air 的「每日价 day1-7」**。Air 模板填充器已就绪并测试，但缺「Air 微信图/EES → 每日价」的专门抽取 prompt。Air 端到端尚未通。
3. **微信图链路**：代码就绪 + Pillow 已装，但本地无 vllm 未实跑，**需在有 vllm 的环境验证视觉抽取**。
4. **Sea 只填 JP sheet**：`FCL N RATE OF OTHER PORTS` / `LCL N RATE` 两 sheet 暂未填（留 TODO）。
5. **审核台交互**：前端目前**只展示+标记** needs_review，尚无「勾选保留哪条」的人工选操作（后端汇总已具备，待加前端交互 + 一个"应用选择"接口）。
6. **会话存内存**：重启即失（demo 可接受）。

## 七、怎么手动验证（明早）

```bash
# 后端
cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
# 前端
cd frontend && npm run dev
```
浏览器进「运价表生成」菜单 → 选 **Sea** → 上传 `资料/2026.05.27/Sea Net Rete/` 下的
`kmtc…xlsx` 和 `NVO FAK…xlsx` → 点「上传并抽取」→ 看汇总预览 → 点「下载填好的运价表」。
（微信图需后端 vllm 可用；Air 链路待补每日价抽取。）

## 八、下一步（等福山回复后）

- 福山确认「上传=选模板+传杂料+人工审核」后，补**审核台手工选多报价**交互。
- 按客户给的「同航线多报价取舍规则」细化去重/推荐。
- 补 Air 每日价抽取 prompt；按需补 Sea OTHER/LCL sheet。
