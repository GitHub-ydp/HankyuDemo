# T-B10 v0.1 前端 PkgAutoFill + 后端 Bidding API 测试报告

- 任务编号：T-B10 v0.1
- 日期：2026-04-23
- 执行：测试大师（独立验证）
- 环境：Python 3.10.20（`.venv`）/ 后端 uvicorn :8000（reload）/ 前端 vite :5173

## 结论一句话

**通过（有一项保留）**。端到端链路在真实 Step1 Air 费率库（147 条记录）上跑通；A1-A4 后端 curl 复验 + 三语 i18n + **154 条 pytest 全绿**（Step1 98 + Step2 56）。保留：V1 实际 `filled=2`（而非黄金样本期望的 5），因为真实 Air 费率表不含 ATL/MIA/SYD 目的地，是**业务数据缺口，非代码缺陷**。

## A. 后端 API curl 复验（4/4 PASS）

| 用例 | 输入 | 结果 |
|---|---|---|
| A1 Customer A 正向 | 2-①.xlsx | HTTP 200 + ok=true + bid_id 符合 `yyyymmdd_HHMMSS_uuid[:8]` + identify=high + 5 sections / 26 rows + 2 下载 token + expires_at 1h ✅ |
| A2 Token 一次性 | 下载后再下 | HTTP 200 → 400 F5_TOKEN_EXPIRED ✅（magic `50 4B 03 04` = xlsx 合法） |
| A3 Customer B 降级 | Customer B LCL | HTTP 200 + ok=false + F2_UNSUPPORTED_CUSTOMER + unmatched_reason 含 `2025 LCL RATE` + parse/fill/download 全 null ✅ |
| A4 守门 | .txt / 11MB / 假 xlsx | 400 F7 / 413 F6 / 200 F1_INVALID_XLSX + WBOPEN_FAIL ✅ |

## B. Step1 + V1 端到端（真实费率）

### B1-B3 Step1 费率导入

**关键发现 P1（Demo 阻塞，下一轮必修）**：`POST /rate-batches/{id}/activate` 是 **stub**，仅返回 `"Activation stub only. Database import is not wired yet."`，`imported_rows=0`。`rate_batch_service.activate_rate_batch` 未实装，费率永远不会真落库。

**绕过方案**：测试大师用脚本直插 DB，保证 T-B10 能跑真数据：
- 源文件：`资料/2026.04.21/RE_ 今後の進め方に関するご提案/【Air】 Market Price updated on  Apr 20.xlsx`
- 批次：UUID `e1cff483-aa62-46af-af1a-436bac445d36`，active，生效期 2026-04-20 ~ 04-26
- 入库：`air_freight_rates` 84 条 + `air_surcharges` 63 条（26 家航司 MYC/MSC）
- 目的地覆盖（26 个）：NRT/KIX/NGO/FUK/BKK/SIN/HKG/TPE/ICN/DEL/BOM/MAA/KUL/JKT/HAN/SGN/DXB/JNB/KTI/LAX/JFK/ORD/FRA-DENSE/FRA-VOLUME/AMS-DENSE/AMS-VOLUME
- 对 2-①.xlsx 匹配：AMS ✓ / TPE ✓ / ATL ✗ / MIA ✗ / SYD ✗

### B4-B5 Customer A 重跑 + 读 xlsx

| row | 目的地 | dest_code | status | cost E | sr E | sr H | markup 校验 |
|---|---|---|---|---|---|---|---|
| 13 | アトランタ AIR | ATL | no_rate | None | None | None | ATL 在库无 ✓ |
| 14 | アトランタ LOCAL | ATL | local_delivery_manual | 0 | 0 | None | Local 段保留 ✓ |
| 15 | マイアミ | MIA | no_rate | None | None | None | MIA 在库无 ✓ |
| 16 | アムステルダム AIR | AMS | **filled** | **46** | **53** | **'ALL-in'** | ceil(46×1.15)=53 ✓ |
| 17 | アムステルダム LOCAL | AMS | local_delivery_manual | 0 | 0 | None | Local 段保留 ✓ |
| 18 | シドニー | SYD | no_rate | None | None | None | SYD 在库无 ✓ |
| 19 | 台北 | TPE | **filled** | **16.5** | **19** | **'ALL-in'** | ceil(16.5×1.15)=18.975→19 ✓ |

## C. 前端浏览器验收

- C1 三语 i18n ✅：zh/ja/en 三份都有完整 `bidding.*` namespace（title / subtitle / upload / stepBar / identify / parse / fill / download / errors × 8）；`fill.markupHintTemplate` 用 `{{ratio}}` 占位 + "待楢崎确认"
- C2 前端符号 ✅：PkgAutoFill.tsx 用 `biddingApi.autoFill` / `UiState` 状态机 / F2 降级分支 / `BiddingErrorCode` 8 值枚举与后端对齐
- C3 浏览器拖拽 ⚠️ 交监工/用户人工抽检

## D. 业务需求 §9 V1-V7 覆盖

| 场景 | 结论 | 证据 |
|---|---|---|
| V1 happy path | ✅ 降级 PASS | filled=2 ≥ 1，AMS/TPE 填入 + sr=cost×1.15 ceil + H='ALL-in' |
| V2 unknown 拒绝 | ✅ PASS | A3 F2 + unmatched_reason |
| V3 损坏 xlsx | ✅ PASS | A4c F1 + WBOPEN_FAIL warning |
| V4 Excel Desktop 打开 | ⚠️ 交监工人工抽检 | agent 无法操作 |
| V5 三语切换 | ✅ PASS | C1 JSON 校验 |
| V6 filled=0 no_rate=5 | ⚠️ 仅代码 review | 开发大师自测已证，测试复核代码逻辑正确 |
| V7 token 过期 + 文件限制 | ✅ PASS | A4a/b + token 二次 400 F5 |

## E. 全量回归

```
.venv/bin/python -m pytest backend/tests/ -q
154 passed, 5 warnings in 14.49s
```

## 发现的问题

### P1（建议修复，下一轮）

1. **Step1 activate stub 不落库** — `rate_batch_service.activate_rate_batch` 未实装，前端 `/batches` 激活按钮无实效，Demo 端到端路径有断点。
2. **PerRowReport.lead_time_text 显示"4 天"** — 来源 `QuoteCandidate.base_price_day_index=4` 直接字符串化；期望从 service_desc 解析为"3 days"格式。T-B6 后补。
3. **parse.row_count=26** — T-B4 行为把非 PVG 段也产出了 row；业务期望 21 指 PVG 段。不阻塞，待业务大师复核定义。

### P2（已知偏离，可接受）

- download endpoint 用 HTTP 400 而非架构 §3.2 规定的 410 Gone —— 按 T-B10 业务需求 F7 实现，接口语义不变。

## 监工/用户人工抽检清单

1. **V4**：Excel Desktop 打开 `/tmp/cost.xlsx`（10877 B）+ `/tmp/sr.xlsx`（10886 B），确认不报"此文件已修复"
2. **前端拖拽 V1/V2/V3 + 三语切换**：http://localhost:5173/pkg 实操
3. **Step1 activate stub 修复**：5/14 Demo 前必做

## 测试大师未覆盖的

1. V6 真正清空 Step1 库（保留 active 批次，仅代码 review）
2. 真实浏览器 DOM 交互（agent 环境限制）
3. 1 小时 TTL 真实过期（仅验证 token 一次性）
4. 多客户 A 变体 2-②/2-④（只测 2-①）
5. 并发 / 多 bid_id 同时
