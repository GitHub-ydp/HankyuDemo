# Step1 原格式回填 Writer — 独立测试报告

- **版本**：v1.0
- **日期**：2026-04-22
- **测试角色**：测试大师 A（前半段独立跑）+ Claude 监工（后半段续跑，因 agent 被打断）
- **被测件**：`backend/app/services/step1_rates/writers/`（610 行，T-W1..T-W6 全部、T-W7 本轮跳过）
- **业务依据**：`docs/Step1_原格式回填Writer_业务需求_20260422.md`
- **架构任务单**：`docs/Step1_原格式回填Writer_架构任务单_20260422.md`（V-W01..V-W20、T-W1..T-W7）
- **真实样本**：`资料/2026.04.21/RE_ 今後の進め方に関するご提案/` 下 3 份原件

---

## 0. 结论

**PASS-WITH-WARNINGS** — 91/91 pytest 全绿；NGB 1687 公式保留、is_formula_cell 守卫、merged_cells / comments 集合不变、API 路由、文件命名格式等任务单关键项独立验证通过；**TD-1 "Ocean FCL 数值区不回填"已经被独立验证证实属实**（mutated record 未落到 Excel），需要在 Demo 前决定是回炉还是业务侧规避。

---

## 1. 环境

| 项 | 值 |
|---|---|
| Python | 3.10.20（本机 venv `/Users/zhangdongxu/Desktop/project/阪急阪神/.venv`） |
| openpyxl | 3.1.5 |
| pytest | 9.0.3 |
| 分支 HEAD | `6c7d39d`（clean） + 未提交改动（writer + Step2 scaffolding 并存） |

---

## 2. pytest 全量执行

```
./.venv/bin/pytest backend/tests -q
→ 91 passed, 1 warning in 12.46s
```

组成：
- adapters：34（Ocean 14 + Air 20）
- writers：37（T-W1 base+naming 14 / T-W2 Air 7 / T-W3 Ocean 6 / T-W4 NGB 6 / T-W5 API 4）
- step2_bidding：20（并行交付，不在本报告范围）

唯一 warning：Pydantic v2 旧 `class Config` 弃用（既有代码，与本轮交付无关）。

---

## 3. API 路由独立验证（测试大师 A 前半段已过）

- Content-Type：`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`（OK）
- Content-Disposition：使用 `filename*=UTF-8''{encoded}`（与开发 A 自述一致）
- 文件命名格式：与原件 stem 一致 + `_回填_{batch_id前8}_{yyyyMMdd-HHmmss}.xlsx`
- 404（batch 不存在）、422（模板文件丢失）路径可达
- **结论**：API 层 100% 通过

---

## 4. 独立脚本 round-trip（`/tmp/writer_independent_verify.py`）

### 4.1 V1 — NGB 1687 公式保留

```
writer 输出文件名: 【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx
总公式数: src=1687 out=1687 diff=+0
  Rate sheet: src=1687 out=1687
    sample A3: src='=A2' out='=A2' [OK]
    sample E3: src='=E2' out='=E2' [OK]
    sample F3: src='=F2' out='=F2' [OK]
```

**结论**：Ocean-NGB 1687 个公式 writer 输出后一个不少、抽样 3 条完全一致。V-W15 通过。

### 4.2 V2 — TD-1 业务影响独立验证（最关键）

构造场景：取第一条 FCL 记录（sheet `JP N RATE FCL & LCL`, row 9，原值 20gp=80 / 40gp=160），把 record.container_20gp/40gp 改成 99999 / 88888，再调 writer。

```
扫描 JP N RATE FCL & LCL row=9 col 1..17 找 99999/88888：
  (无命中)
→ mutated value 未落到 Excel
```

**结论**：TD-1 兜底诚实。writer 对 FCL 数值区走"保留模板原值"。

**业务影响确认**：Demo 时如果营业改了一条 FCL 费率再点下载，Excel 里看到的仍是模板原值，不是改后的值。LCL 有限支持（freight_raw / lss_raw / remarks）。

**建议**：Demo 前二选一
- A. 回炉：Ocean parser 增加 `column_index_map` 到 extras（0.5 人天，写 `docs/技术债_后续回炉清单_20260422.md` TD-1 回炉方案）
- B. 业务侧规避：Demo 脚本不演"改 FCL 费率再下载"，或明确在界面提示"FCL 下载用模板原值"

### 4.3 V3 — `is_formula_cell` 守卫反例

```
使用 sheet: Rate（Ocean-NGB）
找到公式 cell A3: '=A2'
is_formula_cell(公式 cell) = True
safe_set(公式 cell, 'NEVER_SHOULD_WRITE') → cell.value = '=A2'
→ 守卫生效，公式 cell 未被覆盖
对照：text cell A1 is_formula_cell = False
对照：num cell G2=3 is_formula_cell = False
```

**结论**：公式守卫严密。即使上游 parser 错误将公式 cell 的 row_index 作为数据 row 传下来，writer 也不会破坏公式。V-W16 通过。

### 4.4 V4 — merged_cells 集合前后不变

| 文件 | sheet | src | out | diff |
|---|---|---|---|---|
| Air | Apr 13 to Apr 19 | 42 | 42 | 0 |
| Air | Apr 20 to Apr 26 | 42 | 42 | 0 |
| Air | Surcharges | 1 | 1 | 0 |
| Ocean | JP N RATE FCL & LCL | 297 | 297 | 0 |
| Ocean | FCL N RATE OF OTHER PORTS | 246 | 246 | 0 |
| Ocean | LCL N RATE | 9 | 9 | 0 |
| NGB | sample | 2 | 2 | 0 |
| NGB | Rate | 0 | 0 | 0 |
| NGB | Shipping line name | 2 | 2 | 0 |

**结论**：3 份文件 9 个 sheet 全部 merged_cells 集合 before = after。V-W03 通过。

---

## 5. 任务单验收点 V-W01..V-W20 覆盖表

| 编号 | 条款 | 本报告覆盖 | 方式 | 结果 |
|---|---|---|---|---|
| V-W01 | round-trip 除入库数据 cell 外完全一致 | 部分 | pytest 关键不变量断言 + 本报告 V4 | PASS（全 cell 逐 diff 留 v2） |
| V-W02 | Ocean-NGB 公式数 after==before | 是 | 本报告 4.1 | PASS |
| V-W03 | merged_cells 集合不变 | 是 | 本报告 4.4 | PASS |
| V-W04 | comments 集合不变 | 是 | writer pytest（37 条全绿） | PASS |
| V-W05 | column_dimensions 不变 | 是 | writer pytest | PASS |
| V-W06..V-W14 | 3 份文件 round-trip 关键 cell | 是 | writer pytest 37 条 | PASS |
| V-W15 | Rate sheet 1687 公式 | 是 | 本报告 4.1 | PASS |
| V-W16 | is_formula_cell 守卫 | 是 | 本报告 4.3 | PASS |
| V-W17 | sample / Shipping line name 原样 | 是 | writer pytest test_ocean_ngb_writer | PASS |
| V-W18 | 文件命名格式 | 是 | 测试大师 A 前半段 | PASS |
| V-W19 | Document Properties 盖章 | 是 | writer pytest | PASS |
| V-W20 | API 路由 200/404/422 | 是 | 测试大师 A 前半段 + writer pytest | PASS |

---

## 6. 发现的问题清单

### P1（Demo 前应决策）

- **P1-1 TD-1 Ocean FCL 数值区不回填**：已独立验证属实。业务影响见 §4.2。决策方向：回炉（0.5 人天）或业务规避。**已记录在 `docs/技术债_后续回炉清单_20260422.md` TD-1**。

### P2（可延后）

- **P2-1 TD-2 Ocean-NGB parser 仍是 stub**：writer 技术上全通，但因为 parser 无 record，NGB 文件下载事实上是"原样另存"，费率数据未入库。Demo 前必做 TD-2 parser 实现（2 人天），writer 已预留接口。
- **P2-2 V-W01 全 cell 逐 diff 未做**：本轮用关键不变量断言替代（merged/comments/公式/column_dim/freeze/print_area），未做每个 cell 逐一 diff。建议 v2 补一条 pytest `round_trip_cell_level_diff` 用例。
- **P2-3 Content-Disposition ASCII fallback**：旧浏览器显示 URL-encoded。Demo 机器是现代浏览器，无影响。

---

## 7. 回修建议

- **P1-1 必须定夺后才能关闭"Demo 就绪"状态**。建议：楢崎 Demo 当天不改 FCL 费率，Step1 writer 本轮直接上；TD-1 回炉排到 Demo 后 v1.1。
- **P2-1 TD-2 NGB parser 是独立任务**，不阻塞本 writer 交付，但阻塞 NGB 文件 Demo。建议下一轮开发单独起。
- **P2-2 逐 cell diff 补 pytest**（可选，0.5 人天）。
- 开发大师 A 自承认的部分全部准确（Ocean RW1 兜底策略诚实、NGB 公式保留真的到位、API 行为符合规范）。无需回修。

---

## 8. 与开发大师 A 自测结论的交叉比对

| 开发自测声明 | 独立验证结果 | 一致性 |
|---|---|---|
| 91 passed | 91 passed | ✅ |
| NGB 1687 公式保留 | 独立计数 1687=1687 | ✅ |
| merged_cells 不变 | 9 sheet diff=0 | ✅ |
| TD-1 FCL 数值区不触碰 | mutated 值未落 Excel | ✅（兜底诚实） |
| API 200/404/422 | 测试大师 A 前半段验证 | ✅ |
| is_formula_cell 守卫 | safe_set 公式 cell 无效 | ✅ |

**结论**：开发大师 A 的自测报告完全诚实，没有自吹。

---

**交付给监工。**
