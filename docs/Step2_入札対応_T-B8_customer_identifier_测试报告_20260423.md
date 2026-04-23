# T-B8 customer_identifier 测试报告

- 任务编号：T-B8（Step2 入札対応）
- 测试轮次：交付后首轮独立验证（开发大师交付 → 测试大师独立验收）
- 日期：2026-04-23
- 测试者：测试大师（独立角色，未抄开发大师自测数字）

## 0. 结论

**PASS**。45/45 pytest 全过；6 份真实样本端到端实测全部符合预期；4 条边界反向（含 OR 关系反证）全部 PASS；红线两条全空；T-B3+T-B4+T-B5 共 32 条回归无异常。

## 1. 执行环境

| 项 | 值 |
|---|---|
| Python | 3.10.20 |
| pytest | 9.0.3 / pluggy 1.6.0 |
| venv | `/Users/zhangdongxu/Desktop/project/阪急阪神/.venv` |
| 工作目录 | `/Users/zhangdongxu/Desktop/project/阪急阪神/backend` |
| Git HEAD | `eb1c9ba57d2845a4fa7c1ad87b6330dc78a4b89d`（已是开发大师 T-B8 提交后的 HEAD） |
| 分支 | `main` |

## 2. A. pytest 全量结果（独立复跑，不抄开发大师）

命令：

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate && cd backend \
  && python -m pytest tests/services/step2_bidding/ -v 2>&1 | tee /tmp/tb8_pytest.log
```

测试大师独立跑出的尾部输出（原样复制）：

```
============================== 45 passed in 0.92s ==============================
```

逐项分布：

| 文件 | 数量 | 结果 |
|---|---:|---|
| `test_customer_a_parse.py`（T-B3+T-B4 回归） | 14 | 14 PASS |
| `test_customer_identifier.py`（T-B8 本轮） | 13 | 13 PASS |
| `test_rate_matcher.py`（T-B5 回归） | 12 | 12 PASS |
| `test_rate_repository.py`（T-B3 回归） | 6 | 6 PASS |
| **合计** | **45** | **45 PASS / 0 FAIL / 0 SKIP** |

时长：0.92s。与开发大师自测同为 45 passed，**测试大师在本机独立复跑得出此结论**，并附 `/tmp/tb8_pytest.log` 全文为证。

## 3. B. 13 条 pytest 形式化作弊审查

逐条检查 `backend/tests/services/step2_bidding/test_customer_identifier.py`：

| 用例 | 关键审查点 | 结论 |
|---|---|---|
| V-T-B8-01..03 | 直接读 `资料/2026.04.02/Customer A (Air)/2-①.xlsx, 2-②.xlsx, 2-④.xlsx`；6 条 assert 覆盖 customer/dimensions/confidence/warnings/unmatched_reason/source | 真实文件、强 assert，**无作弊** |
| V-T-B8-04 | 读真实 Customer B `2-①.xlsx`；assert 含 `"2025 LCL RATE"`。本测试者打开文件确认 sheet 名为 `'2025 LCL RATE(1001-0331) '`，断言来自真值 | **无作弊** |
| V-T-B8-05 | 读真实 Customer E；assert 含 `"AIR入力フォーム"`，并断言 warnings 不含 `MULTI_SHEET`（因 sheet 名不含 `見積りシート`） | **无作弊** |
| V-T-B8-06 | 读真实 Nitori `阪急阪神【to GLOBAL】2026年1月～3月_見積り書.xlsx` | **无作弊** |
| V-T-B8-07 | 用 `os.urandom(1024)` 写真随机字节 → openpyxl 加载触发 `BadZipFile`，走 `WBOPEN_FAIL:` 分支。断言 `warnings[0].startswith("WBOPEN_FAIL:")` | 真损坏文件，**非空文件糊弄** |
| V-T-B8-08 | 真用 `Workbook()` 创建 `見積りシート` + `wb.create_sheet("Notes")`；表头写第 3 行三关键字。assert dimensions=("D",) 且 warnings 含 `MULTI_SHEET` | **真多 sheet** |
| V-T-B8-09 | 用 `for r in range(1,5): cell(r,2,"公告 R{r}")` 占 1~4 行，第 5 行写表头三关键字。assert dimensions=("B","D") | **真把表头放第 5 行** |
| V-T-B8-10 | 仅 B 命中：sheet 名对、表头 G 列留空 → 触发 `HEADER_MISMATCH` warning | **无作弊** |
| V-T-B8-11 | 仅 D 命中：sheet 名 `Quote Sheet 2026-01`、表头 3 关键字齐 → 触发 `SHEET_NAME_VARIANT` warning | **无作弊** |
| V-T-B8-12 | sheet 名 `'  見積りシート  '`（前后空白），覆盖 normalize 路径 | **无作弊** |
| V-T-B8-R01 | 独立 import `CustomerAProfile`，对真实样本调 `.detect()`，验证升级后未破坏 T-B4 | **无作弊** |

13 条全部"真实文件 + 强 assert"或"真实临时构造 + 强 assert"，无 `assert True`、无空 assert、无魔法路径绕过。

## 4. C. 真实样本端到端独立验证（最关键）

命令：

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate \
  && python /tmp/test_tb8_e2e.py 2>&1 | tee /tmp/tb8_e2e.log
```

脚本：`/tmp/test_tb8_e2e.py`（直接 import `from app.services.step2_bidding import identify, IdentifierResult`，对 6 个真实文件各调一次）

### 6 文件实测对照表（stdout 节选见 `/tmp/tb8_e2e.log`）

| 序 | 文件 | matched_customer | matched_dimensions | confidence | warnings | unmatched_reason 摘要 | 期望 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 1 | Customer A `2-①.xlsx` | `customer_a` | `('B','D')` | `high` | `()` | None | customer_a + (B,D) | PASS |
| 2 | Customer A `2-②.xlsx` | `customer_a` | `('B','D')` | `high` | `()` | None | customer_a + (B,D) | PASS |
| 3 | Customer A `2-④.xlsx` | `customer_a` | `('B','D')` | `high` | `()` | None | customer_a + (B,D) | PASS |
| 4 | Customer B `2-①.xlsx` | `unknown` | `()` | `low` | `()` | sheet 名 `'2025 LCL RATE(1001-0331) '`，非 Customer A 模板；表头行 1-10 未找到 3 关键字 | unknown + () | PASS |
| 5 | Customer E `2-①.xlsx` | `unknown` | `()` | `low` | `()` | 工作簿含 2 sheet `['AIR入力フォーム','SEA入力フォーム']`；表头行 1-10 未找到 3 关键字 | unknown + () | PASS |
| 6 | Nitori `阪急阪神【to GLOBAL】2026年1月～3月_見積り書.xlsx` | `unknown` | `()` | `low` | `()` | 工作簿含 3 sheet `['お客様案内（TO Global)','Quotation (Global) Jan-Mar','所要日数 ']`；表头行 1-10 未找到 3 关键字 | unknown + () | PASS |

**独立汇总：6/6 PASS**。

### 关键观察

- Customer B 的 `unmatched_reason` 含人类可读的真实 sheet 名 `'2025 LCL RATE(1001-0331) '`（注意末尾有空格），与 V-T-B8-04 中 `assert "2025 LCL RATE" in result.unmatched_reason` 字面契合。
- Customer E 的 `unmatched_reason` 含 `'AIR入力フォーム'`，与 V-T-B8-05 字面契合，且无任何 `MULTI_SHEET` warning（因为它没有名为 `見積りシート` 的 sheet）。
- Nitori 是 3 sheet 工作簿，全部 sheet 名不命中模板，正确兜底为 unknown。

## 5. D. 边界反向独立验证

命令：

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate \
  && python /tmp/test_tb8_boundary.py 2>&1 | tee /tmp/tb8_boundary.log
```

脚本：`/tmp/test_tb8_boundary.py`

| 编号 | 场景 | matched_customer | matched_dimensions | warnings | 期望 | 结论 |
|---|---|---|---|---|---|---|
| B-1 | 复制 Customer A `2-①.xlsx`，sheet 名改 `'  見積りシート  '`（前后空白），表头不改 | `customer_a` | `('B','D')` | `()` | customer_a + 含 B（D 也应在） | PASS（normalize 正确剥空白） |
| B-2 | 复制 Customer A `2-①.xlsx`，sheet 名改 `'見積もりシート'`（"り" → "もり"，平假变体），表头不改 | `customer_a` | `('D',)` | `("SHEET_NAME_VARIANT: 表头命中但 sheet 名异常: ['見積もりシート']",)` | customer_a + ('D',) | PASS — **OR 关系反证成功**：B 不中、D 中、整体仍 customer_a，并触发 SHEET_NAME_VARIANT warning |
| B-3 | 用 openpyxl 创建空 wb（默认保留 1 个空 'Sheet'） | `unknown` | `()` | `()` | unknown 兜底 | PASS（注：openpyxl 不允许 0 sheet，故走 sheet 名不匹配路径，EMPTY_WB 不触发，符合实现约束） |
| B-4 | 表头放第 8 行（接近 `_HEADER_SCAN_LAST_ROW=10` 上限） | `customer_a` | `('B','D')` | `()` | customer_a + 含 D | PASS |

**边界汇总：4/4 PASS**。其中 B-2 是关键 OR 关系反证：单 D 也能识别为 customer_a。

## 6. E. 回归 + 红线核查

### 回归（T-B3+T-B4+T-B5 共 32 条）

命令：

```bash
python -m pytest \
  tests/services/step2_bidding/test_customer_a_parse.py \
  tests/services/step2_bidding/test_rate_matcher.py \
  tests/services/step2_bidding/test_rate_repository.py -v
```

结果：

```
============================== 32 passed in 0.48s ==============================
```

含 `test_v_b01_detect_returns_true`（T-B4 V-B01）→ 升级 detect 加 G 列校验后真实样本仍 True，**回归无破坏**。

### 红线检查

```bash
$ find backend/app/services/step2_bidding/customer_profiles -name '*stub*'
（空）

$ grep -rEn 'dim_a|dim_c|domain|filename_pattern' backend/app/services/step2_bidding/
（空）
```

两条红线全空：未为 Customer B/E/Nitori 留 stub，未引入 dim_a/dim_c/domain/filename_pattern 任何 v2.0 概念。

## 7. 不通过项 / 建议回炉项

**无不通过项**。

可改进点（**非阻塞**，仅记录给后续轮次留意，不要求本轮回炉）：

1. `EMPTY_WB` warning 在 openpyxl 路径下其实**永远不会触发**（openpyxl 不允许 0 sheet 工作簿，空 wb 仍会有默认 'Sheet'）。代码 `if not sheetnames: return _make_unknown(... "EMPTY_WB" ...)` 是防御性死分支。建议下一轮文档里明确这是"理论保险丝"，或在 docstring 注释。
2. Customer B 的真实 sheet 名末尾带一个**半角空格**（`'2025 LCL RATE(1001-0331) '`），`unmatched_reason` 直接 `repr()` 输出含尾空格的字符串。当前实现 OK，但若未来给业务看的 UI 想"友好显示"可考虑 strip。本轮**不算缺陷**。
3. 6 个真实样本中，`unmatched_reason` 全部很长（含完整 sheet 列表与扫描结果），这是设计意图（给营业看），但 UI 展示时建议折叠/截断。

## 8. 给开发大师的复现命令

```bash
# 主验证（45 条）
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate && cd backend \
  && python -m pytest tests/services/step2_bidding/ -v

# 真实样本端到端
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate \
  && python /tmp/test_tb8_e2e.py

# 边界反向
cd /Users/zhangdongxu/Desktop/project/阪急阪神 \
  && source .venv/bin/activate \
  && python /tmp/test_tb8_boundary.py
```

## 9. 测了什么 / 没测什么

**已测**：
- 45 条 pytest 全量复跑
- 13 条 T-B8 用例的形式化作弊审查（每条都人工检查了 fixture 来源与 assert 强度）
- 6 个真实样本（3 份 A 正例 + Customer B/E/Nitori 各 1 份反例）端到端
- 4 条边界（前后空白 sheet 名、平假名异体 sheet 名、空 wb、第 8 行表头）
- 红线（stub 文件 + 违禁词）
- 32 条 T-B3/B4/B5 回归

**没测**（明确告知监工，不自评"全面"）：
- 未测受 Excel 密码保护的 xlsx（任务单未要求；当前 `WBOPEN_FAIL` 分支应能兜底，但未实测）
- 未测**超大 xlsx**（>100MB）的耗时上界（架构任务单 §11 NFR 要求 <1s，本轮 6 份真实样本最大也未到 100KB 量级，未压测）
- 未测 hint 参数路径（v1.0 业务需求未交付 manual override，identify 不接受 hint）
- 未测多线程并发调用 identify（业务暂不需要）
- 未对 `_HEADER_SCAN_LAST_ROW=10` 之外的极端表头（第 11 行）做反向，因为 V-T-B8-09 与 B-4 已覆盖第 5 行与第 8 行；任务单明确上限就是 10，超过即应 unknown，相信单元测试隐含覆盖
