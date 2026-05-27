# 运价表生成器（Rate Sheet Builder）实现计划

> **执行方式：** 本计划由 Claude 在同一 session **inline 执行**（用户已 /goal 授权连夜开发、明早审计）。每个模块按 TDD：先写失败测试 → 最小实现 → 跑通 → commit。本文件是执行蓝图 + 决策记录，供明早审计。

**Goal:** 实现「选空白模板 → 上传多源杂料 → AI 抽取 → 汇总 → 填进客户空白模板 → 人工审核 → 下载」的运价表生成闭环，把 step1 从"导入成品表"扶正为"从元料金做成运价表"。

**Architecture:** 在现有成熟的多源抽取能力（`rate_parser` / `wechat_image_parser` / `email_text_parser` / `ai_client` 视觉）之上，新增一个**编排层**：会话(选模板) → 多文件分发到对应 parser → 汇总 parsed_rows → 去重/多报价标记 → 配置驱动的**模板填充器**把数据写进客户空白模板。不入库（"做表"非"导表"），但复用 `writers/base.safe_set` 写入守卫。

**Tech Stack:** Python 3.10 / FastAPI / openpyxl / pytest（mock AI）；前端 React19 + AntD v6 + i18next。

---

## 一、背景与口径（认知修正）

经 5/26 楢崎邮件 + 5/27 福山资料 + 多轮对齐确认：**step1 的真实需求是「采购从代理/船司收集的元料金（杂乱多源：各家 Excel、微信截图、PDF、邮件正文）→ AI 抽取 → 填入 HHE 指定空白模板 → 做成运价表」**。我们此前实现的「导入成品表→入库 544 条」方向反了（做了下游）。根因是 step1 需求当初以附件发送、DHC 打不开附件，只能对着成品表反推。详见记忆 `step1-true-requirement-make-not-import`。

**已与用户锁定的口径：**
- 上传交互 = 用户**先选模板**(Air / Sea) → 传该模板对应的一堆杂料 → AI 抽取填表 → 系统审核台人工确认/纠正。
- 同一航线多家报价 → AI 给推荐 + 人工在审核台手工选。
- demo 先做 **Air + Sea** 两组（福山按这两组发的资料）；SHA+NGB 等元料金到位后补。

## 二、demo 范围与关键决策（自主决策，记录供审计）

| 决策 | 选择 | 理由 |
|---|---|---|
| 支持的来源（本轮） | 结构化 Excel（kmtc/nvo via `rate_parser.detect_and_parse`）、微信图（`wechat_image_parser`）、邮件文本（`email_text_parser`） | 这三类抽取能力**已成熟**，复用即可跑通 |
| 暂不支持的来源 | EES 超复杂综合手册(12 sheet/16383 列)、PDF（无解析库）、.xls（无 xlrd） | 友好降级：识别到就提示"本轮暂不支持，已跳过"，不报错 |
| 是否入库 | **否**，直接填模板产出 xlsx | 需求是"做表"，表是产物；入库是后续可选 |
| 填充精度 | 配置驱动逐行写（表头保留，数据区从起始行往下排）；Sea 按 20FT/40FT 展开行，Air 一行一条 | demo 求"结构正确、数据齐全、人可审"，不追求 100% 复刻原版预留格 |
| 多报价处理 | 同 (目的港+船司) 出现多条 → 全部保留 + 标 `needs_review`，审核台人工选 | 取舍是业务规则，系统只推荐不替客户拍板 |
| 测试 AI | 一律 mock，不打真实 vllm | 测编排逻辑而非模型；真实 AI 留手动验证 |

## 三、复用 vs 新增

**复用（不改）：** `ai_client.chat_with_image/extract_json`、`wechat_image_parser.parse_wechat_image`、`email_text_parser.parse_email_text`、`rate_parser.detect_and_parse`、`writers/base.safe_set`。

**新增：** `app/services/step1_rates/sheet_builder/` 一个新子包 + 一个新 API router + 一个前端页。**不动**现有 step1 导入链路、544 数据、step2。

## 四、文件结构

```
backend/app/services/step1_rates/sheet_builder/
├── __init__.py
├── entities.py          # SheetBuildSession / NormalizedRate / BuildResult DTO
├── template_registry.py # Air/Sea 模板配置：路径 + 列映射 + 数据起始行 + sheet分流
├── template_filler.py   # 配置驱动填充器：records → 填空白模板 → xlsx bytes
└── orchestrator.py      # 会话编排：多文件分发抽取 → 汇总 → 去重/多报价标记
backend/app/api/v1/rate_sheet.py   # 新 router /rate-sheet
backend/tests/sheet_builder/
├── test_template_registry.py
├── test_template_filler.py
├── test_orchestrator.py
└── test_rate_sheet_api.py
frontend/src/pages/RateSheetBuilder.tsx  # 选模板→多文件→审核→下载
```

## 五、数据流

```
[前端] 选模板(air/sea) ──POST /rate-sheet/session──▶ session_id
        │
        ├─ 多文件上传 ──POST /rate-sheet/{sid}/files──▶ orchestrator
        │     每文件: 路由 → parser 抽取 → parsed_rows
        │     不支持来源 → 标 skipped + 原因
        │
        ▼
   汇总 NormalizedRate[] ── 去重 + 同(港+司)标 needs_review
        │
        ├─ GET /rate-sheet/{sid}/preview ──▶ 审核台数据(含 needs_review)
        └─ GET /rate-sheet/{sid}/download ──▶ template_filler 填模板 → xlsx
```

## 六、接口契约（API）

- `POST /api/v1/rate-sheet/session` body:`{template_type:"air"|"sea"}` → `{session_id, template_type}`
- `POST /api/v1/rate-sheet/{sid}/files` multipart 多文件 → `{files:[{name, source_type, status, row_count, warnings}], summary:{total_rows, needs_review}}`
- `GET /api/v1/rate-sheet/{sid}/preview` → `{template_type, rows:[NormalizedRate+needs_review], conflicts:[...]}`
- `GET /api/v1/rate-sheet/{sid}/download` → xlsx 文件流（Content-Disposition）
统一走 `ApiResponse`（download 除外，直接 StreamingResponse）。

## 七、模板配置（已调研确定）

**Sea / sheet `JP N RATE FCL & LCL`**：表头 r8，数据起始 **r9**。列：A(1)目的港 / B(2)船司 / C(3)箱型 / D(4)Freight / E(5)LSS+CIC / F(6)BAF / G(7)EBS / H(8)YAS·CAF / I(9)Sailing / J(10)Via / K(11)Transit / L(12)Booking / Q(17)RMKS。FCL 按 20FT/40FT 展开两行。（OTHER/LCL sheet 本轮可先不填，留 TODO。）

**Air / sheet `May 25 to May 31`**：表头 r1，数据起始 **r2**。列：A(1)目的港 / B(2)Service / C(3)~I(9) 每日价 day1~7 / J(10)Remark。与现有 `AirWriter._write_weekly` 列布局一致，可参考。

## 八、任务分解（TDD，逐个 commit）

- **Task 2 template_registry**：登记两模板配置（dataclass）。测试：取 air/sea 配置，断言起始行/关键列映射正确；模板文件存在。
- **Task 3 template_filler**：`fill(template_type, rows) -> bytes`。测试：构造 2~3 条 rate，填 sea 模板，重新读出断言 A9=目的港、D9=运费、表头 r8 未被覆盖；公式格不被覆盖（safe_set）。
- **Task 4 orchestrator**：`add_files` mock 各 parser，断言汇总行数、同(港+司)多条标 needs_review、不支持后缀标 skipped。
- **Task 5 API**：TestClient mock orchestrator/AI，跑 session→files→preview→download 全链路，断言 download 返回合法 xlsx。
- **Task 6 前端**：页面打通（时间不足则保证后端 API 可用 + 最小页）。
- **Task 7**：全量 pytest 回归 + 真实样本(kmtc/nvo/微信图)手动端到端 + 审计报告。

## 九、风险与降级

- **AI 视觉不稳/超时**：微信图抽取依赖真实 vllm 视觉；测试 mock，手动验证时若失败 → 报告记录，不阻塞 Excel 链路。
- **填充精度**：Sea 箱型展开/多 sheet 分流 demo 先简化，OTHER/LCL sheet 留 TODO。
- **会话存储**：用内存 dict（与现有 `_parse_cache` 一致），重启丢失——demo 可接受。
- **不破坏现有**：新代码全在新子包/新 router，跑全量 pytest 确认 544 链路与 step2 不回归。
```
