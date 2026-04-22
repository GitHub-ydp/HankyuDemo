# Step2 入札対応 Customer A — T-B1..T-B4 独立测试报告

- **轮次**：Step2 T-B1..T-B4（打地基 4 项）
- **日期**：2026-04-22
- **测试人**：独立测试大师
- **交付方**：开发大师 B
- **依据任务单**：`docs/Step2_入札対応_Customer_A_架构任务单_20260422.md`
- **业务红线**：`docs/Step2_入札对应_业务需求_20260422.md`

## 结论

**PASS**（无 P0/P1 阻塞问题；1 条 P2 改进建议）

所有 20 条 pytest 用例真实执行通过；黄金样本 10 行独立对数 100% 一致；DEPRECATED 模块在
`step2_bidding/` 下 0 引用；RateRepository in-memory 独立构造验证通过；边界/反例（空 sheet、
错 sheet 名、未知城市、`TBD`/`-`/`－`/`0`/合法数字 5 种 price 分支）行为符合预期。

## 执行环境

- Python：3.10.20
- HEAD：`6c7d39d702b6f34dc2fca6b7c0255829b4508ea3`（commit aeb7d26 → 本次未 commit）
- 分支：main（有未提交的 Step2 新增文件，符合任务书"本轮不 commit"）
- 依赖：pytest 9.0.3、openpyxl 3.1.5、SQLAlchemy 2.x、sqlite（in-memory）

## 场景 1：pytest 真实绿数

### 命令
```
./.venv/bin/pytest backend/tests/services/step2_bidding/ -v
./.venv/bin/pytest backend/tests -q
```

### step2_bidding 子集（20 条）

| # | 用例 | 结果 |
|---|---|---|
| 1 | test_v_b01_detect_returns_true | PASS |
| 2 | test_customer_a_profile_implements_customer_profile_protocol | PASS |
| 3 | test_v_b02_five_sections | PASS |
| 4 | test_v_b03_section_codes_order | PASS |
| 5 | test_v_b04_section_currencies | PASS |
| 6 | test_v_b05_pvg_section_has_seven_rows | PASS |
| 7 | test_v_b06_local_delivery_rows | PASS |
| 8 | test_v_b07_example_rows_flagged_and_pvg_has_no_example | PASS |
| 9 | test_v_b08_icn_section_level_remark_contains_r38 | PASS |
| 10 | test_v_b09_destination_codes_r13_and_r19 | PASS |
| 11 | test_period_passed_through_preserved_over_b1 | PASS |
| 12 | test_period_falls_back_to_b1_when_empty | PASS |
| 13 | test_existing_price_parsed_as_decimal | PASS |
| 14 | test_fill_not_implemented_in_this_round | PASS |
| 15 | test_query_air_weekly_returns_active_batch_only | PASS |
| 16 | test_query_air_weekly_destination_like_match | PASS |
| 17 | test_query_air_weekly_effective_on_out_of_week_excluded | PASS |
| 18 | test_query_air_weekly_currency_and_airline_filters | PASS |
| 19 | test_query_air_surcharges_returns_active_and_before_effective | PASS |
| 20 | test_ocean_and_lcl_raise_not_implemented | PASS |

总耗时 0.41s，20/20 PASS。

### 全量
`91 passed, 1 warning in 12.49s`（唯一 warning 为 pydantic v2 config 弃用提示，与本轮无关，已是
老存量）

## 场景 2：CustomerAProfile.parse 黄金样本 10 行独立对数

黄金样本：`资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx`

独立用 openpyxl 读原单元格（B/C/E/G/H 列）与 `profile.parse` 输出逐一比对：

| # | 行 | 字段 | 原 Excel 单元格 | profile.parse 输出 | 一致 |
|---|---|---|---|---|---|
| 1 | R4 | B='日本 (成田)' + G='※記入例\nCarrier: 5X...' | origin='NRT', is_example | section_code=NRT, origin_code=NRT, is_example=True | PASS |
| 2 | R5 | E=750, C='アメリカ (アトランタ)\nLOCAL DELIVERY COST', G='※記入例' | existing_price=750, cost_type=local_delivery, is_example | Decimal('750'), cost_type=local_delivery, is_example=True | PASS |
| 3 | R13 | B='中国 (上海)', C='アメリカ (アトランタ)\nAIR FREIGHT COST', E=0 | origin=PVG, dest=ATL, cost_type=air_freight, price=0 | section_code=PVG, destination_code=ATL, cost_type=air_freight, existing_price=Decimal('0') | PASS |
| 4 | R14 | C='アメリカ (アトランタ)\nLOCAL DELIVERY COST', E=0, F='－' | dest=ATL, cost_type=local_delivery | destination_code=ATL, cost_type=local_delivery | PASS |
| 5 | R17 | C='オランダ (アムステルダム) \nLOCAL DELIVERY COST', F='－' | cost_type=local_delivery | cost_type=local_delivery，existing_lead_time='－' | PASS |
| 6 | R19 | C='台湾\n(台北)'（注意 PVG 段里有台湾着地） | dest=TPE | destination_code=TPE | PASS |
| 7 | R21 | E 列表头 '単価 (ユーロ/kg)' | currency=EUR | currency=EUR, currency_header_raw='単価 (ユーロ/kg)' | PASS |
| 8 | R3 | E 列表头 '単価 (円/kg)' | currency=JPY | currency=JPY, currency_header_raw='単価 (円/kg)' | PASS |
| 9 | R38 | B='※韓国→日本→ブラジルなどトランジット回数を抑え安いルートでも可'（C/E 均空） | ICN 段 section_level_remarks | ICN.section_level_remarks=['※韓国→日本→ブラジル...'] | PASS |
| 10 | R31 | C='中国\n(上海, PVG)' 位于 TPE 段 → 着地 PVG | section=TPE, dest=PVG | section_code=TPE, destination_code=PVG, currency=USD | PASS |

### 段摘要独立核对

| section_index | section_code | header_row | origin_text_raw | origin_code | currency | currency_header_raw |
|---|---|---|---|---|---|---|
| 0 | NRT | R3 | '日本  (成田)' | NRT | JPY | '単価 (円/kg)' |
| 1 | PVG | R12 | '中国  (上海)' | PVG | CNY | '単価 (CNY/kg)' |
| 2 | AMS | R21 | 'オランダ\n  (アムステルダム)' | AMS | EUR | '単価 (ユーロ/kg)' |
| 3 | TPE | R25 | '台湾  (台北)' | TPE | USD | '単価 （USD/kg)' |
| 4 | ICN | R34 | '韓国  (インチョン)' | ICN | USD | '単価 （USD/kg)' |

五段 origin_code 映射 100% 正确，`_ORIGIN_MAP` 长匹配顺序（アムステルダム 先于 オランダ；成田 先于 日本；インチョン 先于 韓国）已正确配置。

### 总行数
- 总行数 26
- NRT 段 7 行（R4..R10）含 R4/R5 `is_example=True`
- PVG 段 7 行（R13..R19）全部非 example — 与 V-B05/V-B07 断言一致
- AMS 段 2 行（R22..R23）
- TPE 段 7 行（R26..R32）
- ICN 段 3 行（R35..R37）+ R38 进入 section_level_remarks（不计入 rows）

## 场景 3：DEPRECATED 引用独立验证

### 命令
```
grep -rn "from app.services.pkg_parser\|from app.services.pkg_filler\|from app.services.rate_db" backend/app backend/tests
grep -rn "pkg_parser\|pkg_filler\|rate_db" backend/app/services/step2_bidding/
```

### 结果
仅 5 条引用全部为旧 Demo 内部：
- `backend/app/api/v1/pkg.py:10-12`（旧 Demo 路由）
- `backend/app/services/pkg_filler.py:14,19`（三兄弟内部互相引用）

**`backend/app/services/step2_bidding/` 整个包下 0 条引用 DEPRECATED 模块**。DEPRECATED 注释三连
头部都已写明"判删于 2026-04-22 Step2 重构（架构任务单 T-B11）"并指向新包路径，纪律达标。

## 场景 4：Step1RateRepository 独立 in-memory 验证

### 命令
```
./.venv/bin/python /tmp/step2_rate_repo_indep.py
```
### 输入（与开发大师用例完全不同的数据）
- active 批次 2 条：PVG→LAX (MU, 40 CNY)、PVG→JFK (CA, 55 CNY)
- superseded 批次 1 条：PVG→LAX (MU, 99 CNY)

### 期望 vs 实际
| 场景 | 期望 | 实际 | 结论 |
|---|---|---|---|
| query PVG→LAX on 4/22 | 1 条 (MU, 40)，排除 superseded 99 | 1 条 (MU, price_day1=40.00)，record_kind='air_weekly' | PASS |
| query PVG→JFK on 4/22 | 1 条 (CA, 55) | 1 条 (CA, 55.00) | PASS |
| sum over LAX+JFK | 2 条 | 2 条 | PASS |
| query NRT→LAX (origin 错) | 0 条 | 0 条 | PASS |
| query PVG→LAX on 5/1 (超周) | 0 条 | 0 条 | PASS |

开发大师的 6 条 pytest 场景覆盖度复核：
- active 过滤 → test_query_air_weekly_returns_active_batch_only
- destination LIKE（`アトランタ (ATL)` 含 `ATL`）→ test_query_air_weekly_destination_like_match
- effective_on 超范围 → test_query_air_weekly_effective_on_out_of_week_excluded
- currency / airline_code_in → test_query_air_weekly_currency_and_airline_filters
- surcharge active + before effective → test_query_air_surcharges_returns_active_and_before_effective
- ocean/lcl 占位 NotImplementedError → test_ocean_and_lcl_raise_not_implemented

**6 项全覆盖**。

## 场景 5：T-B2 推迟的合理性

### 证据
- `TODO_T_B2.md` 写明了：需建表（bidding_requests、bidding_row_reports）、消费方（service.py 在 T-B9）、
  落地时机（T-B5+T-B9 合并批次）。
- 审计 T-B3 代码确认：仅依赖已存在的 `AirFreightRate / AirSurcharge / ImportBatch` 三张 Step1 表，
  字段 `origin / destination / airline_code / effective_week_start/end / price_day1..7 / currency /
  remark / batch_id / status` 均已存在（见 `backend/app/models/air_freight_rate.py` 和
  `backend/app/models/air_surcharge.py`）。
- 审计 T-B4 解析器：纯内存 dataclass 输出 `ParsedPkg`，完全不写 DB，不依赖新表。
- 当前 20 条 pytest 在无新迁移的情况下全绿。

**结论**：T-B2 推迟合理，T-B3/T-B4 不依赖新表。仅需在 T-B5/T-B9 开始写持久化前补回。

## 场景 6：origin_code 映射表独立验证

开发大师声明：长匹配优先表位于 `customer_a.py:_ORIGIN_MAP`。

独立跑 `_map_origin(s)`，5 段原文输入：

| 原文 | 映射结果 | 期望 |
|---|---|---|
| '日本  (成田)' | NRT | NRT |
| '中国  (上海)' | PVG | PVG |
| 'オランダ\n  (アムステルダム)' | AMS | AMS |
| '台湾  (台北)' | TPE | TPE |
| '韓国  (インチョン)' | ICN | ICN |

**5 段全对**。关键细节：`アムステルダム` 必须排在 `オランダ` 之前（否则会命中 `オランダ`→AMS 但没
细化到市级），开发已正确排列。类似 `成田` 先于 `日本`，`インチョン` 先于 `韓国`。

## 场景 7：边界/反例独立覆盖

### 命令
```
./.venv/bin/python /tmp/step2_boundary.py
```

| 反例 | 输入 | 期望行为 | 实际行为 | 结论 |
|---|---|---|---|---|
| 1 | sheet 名 '見積りシート' 但完全空 | detect=False, parse→sections=0 | detect=False, sections=0, warnings=['未识别到任何表头行（...）'] | PASS |
| 2 | sheet 名 'WrongName' | detect=False, parse 抛 ValueError | detect=False, ValueError("找不到 Sheet '見積りシート'...") | PASS |
| 3 | 未知发地'火星 (火星都市)' + 未知着地'金星 (金星都市)' | 不抛异常，section_code=SECTION_0, origin_code=UNKNOWN, dest_code=UNKNOWN，有 warning | 全部符合，warning='段 0 (header R3) 未识别发地代码，原文=\'火星 (火星都市)\'' | PASS |
| 4a | existing_price='TBD' | Decimal None（InvalidOperation 分支） | None | PASS |
| 4b | existing_price='-' | None | None | PASS |
| 4c | existing_price='－'（全角） | None | None | PASS |
| 4d | existing_price=0 | Decimal('0') | Decimal('0') | PASS |
| 4e | existing_price='750.25' | Decimal('750.25') | Decimal('750.25') | PASS |

## 问题清单

### P0 阻塞问题
无

### P1 次要问题
无

### P2 改进建议（建议但不阻塞）

**P2-1（建议 T-B5 或 T-B7 一并处理）**：`_ORIGIN_MAP` 和 `_DEST_MAP` 是模块级 list（O(n)）且是
Customer A 私有；当 T-B8 新增 Customer B/E 时，若每家都单列一份，易产生"长匹配顺序"踩坑。
建议在 T-B8 前把长匹配规则提取到一个通用 helper（例：`longest_keyword_match(text, mapping)`），
并在三段测试（NRT/PVG/TPE）上写"顺序反转会失败"的防回归用例。目前对 T-B4 无影响。

**P2-2（观测，非问题）**：`_MAX_SCAN_ROWS=60` 目前足够（黄金样本 41 行）；若 Customer A 未来扩
增段数，应提前放大或改为动态，但非本轮问题。

**P2-3（观测）**：`existing_lead_time` / `existing_carrier` / `existing_remark` 全部以 `str(v)`
入库（保留原文换行与 ※ 标记），在 T-B7 回填时要注意"空字符串"vs"None"的区分；开发对 `d_raw is
None` 分支已处理，当前 OK。

## 没测到的点（坦白告知）

- CustomerAProfile.fill 被确认 NotImplementedError，**没有测 fill 实际写 Excel 的行为**（T-B7 范畴，
  不在本轮范围）
- 没跑 RateRepository 在真 PostgreSQL 上的 enum 兼容性（sqlite 与 PG enum 在边界场景可能有差异）。
  本轮测试在 sqlite in-memory 做独立验证可接受；上生产前建议监工安排一轮 PG 冒烟
- 没测 Customer A `2-②.xlsx / 2-④.xlsx` 其它变体的 detect/parse（任务单只点名黄金样本 `2-①`）
- 没对 `import_batch.status` 表中"superseded → active 流转"后 query 能否立刻反映（纯读实现不涉及
  写入，但未覆盖并发读写场景）
- V-B10..V-B25 未测（本轮不在范围，留给 T-B5+）

## 对开发大师 B 的回修建议

本轮交付无 P0/P1，无必须回修。建议（可选）：
1. **P2-1**：T-B8 前把长匹配规则抽成通用 helper + 防回归用例，避免后续客户适配踩坑
2. 下次提交 commit 信息里把"DEPRECATED 注释三连"的理由明示（便于监工 audit）

## 给开发大师的复现命令

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神

# 1. pytest 绿数
./.venv/bin/pytest backend/tests/services/step2_bidding/ -v
./.venv/bin/pytest backend/tests -q

# 2. 独立解析 + 原始 Excel 转储
./.venv/bin/python /tmp/step2_parse_verify.py
./.venv/bin/python /tmp/step2_parse_verify2.py

# 3. 边界/反例
./.venv/bin/python /tmp/step2_boundary.py

# 4. 独立 RateRepository in-memory
./.venv/bin/python /tmp/step2_rate_repo_indep.py

# 5. DEPRECATED 引用检查
grep -rn "from app.services.pkg_parser\|from app.services.pkg_filler\|from app.services.rate_db" backend/app backend/tests
grep -rn "pkg_parser\|pkg_filler\|rate_db" backend/app/services/step2_bidding/
```

## 汇总
- PASS：8 个场景 / 8 个场景
- 阻塞问题（P0）：0
- 次要问题（P1）：0
- 改进建议（P2）：3（均可延后）
- 黄金样本 10 行独立对数一致率：10/10 = 100%
- 5 段 origin_code 覆盖率：5/5 = 100%
- pytest 20/20，全量 91/91

**结论：PASS**
