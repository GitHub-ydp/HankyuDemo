# 测试报告 — Step2 T-B5 RateMatcher 独立验证

**日期**：2026-04-23
**测试人**：test-master（独立验证），监工抽查复核
**分支/HEAD**：main @ 9b075b3（待 commit T-B5 改动）
**Python**：3.10.20（venv `/Users/zhangdongxu/Desktop/project/阪急阪神/.venv`）
**pytest**：9.0.3

## 结论

**PASS（带 1 条 P1 回炉项 — `_build_candidate` score 死代码）**

- 31/31 pytest 全绿（独立复跑 0.65s）
- 端到端黄金样本 `2-①.xlsx` 26 行被正确分流：FILLED×3 / NO_RATE×2 / LOCAL_DELIVERY_MANUAL×2 / NON_LOCAL_LEG×19
- 5 条边界反向用例全 PASS
- T-B3 + T-B4 回归 20/20 全绿
- **遗留**：rate_matcher.py:169-173 的 `dest_exact` 与 `currency_match` 是与自身比对的死代码（已要求开发大师当场修复，不进 commit）

## A. pytest 全量结果

```
tests/services/step2_bidding/test_customer_a_parse.py   14 passed
tests/services/step2_bidding/test_rate_matcher.py       11 passed
tests/services/step2_bidding/test_rate_repository.py     6 passed
============================== 31 passed in 0.65s ==============================
```

开发大师自报 1.08s，独立复跑 0.65s，行为一致（时间差异属环境抖动）。

## B. 11 条单测形式化审查

| ID | 真断言 | 备注 |
|---|---|---|
| V-B5-01 non_local_leg | ✅ | 状态 + candidates=[] 双断言 |
| V-B5-02 example_row | ✅ | 同上模式 |
| V-B5-03 local_delivery | ✅ | 同上模式 |
| V-B5-04 already_filled | ✅ | existing_price=Decimal('100') 真触发 |
| V-B5-05 unknown_destination | ✅ | 真触发 NO_RATE |
| V-B5-06 happy_path_with_surcharge | ✅ | **断言 cost=53 / base=50 / day_index=3 等 11 个数值**，50+2+1=53、4/22-4/20=2→day3，真实计算 |
| V-B5-07 no_surcharge_match | ✅ | cost==base==60，source_surcharge_record_id is None |
| V-B5-08 all_fees_dash_skip | ✅ | 单航司情形真测；多航司部分 dash 由 D-3 补测 |
| V-B5-09 carrier_preference_block | ✅ | OZ + carrier_preference=['NH'] → CONSTRAINT_BLOCK |
| V-B5-10 sort_and_truncate | ⚠半真 | 3 条候选 / 真造价差 / 真截断；但 score 二级排序因死代码未实质验证 |
| V-B5-11 superseded_batch_ignored | ✅ | 双 batch（active 100 / superseded 50）真造，断言只取 active |

**形式化作弊审查发现的 P1 bug**：

```python
# rate_matcher.py:169-172
dest_exact = bool(
    weekly_row.destination_port_name
    and weekly_row.destination_port_name  # SQL LIKE 命中
)  # 等价于 bool(weekly_row.destination_port_name)；row 未参与判定

# rate_matcher.py:173
currency_match = (weekly_row.currency or "") == (weekly_row.currency or "")
# 跟自己比，恒为 True
```

任务单 §5.5 明文要求：`dest_exact` 应是 `row.destination_code` 与 `weekly.destination_port_name` 比对，`currency_match` 应是 `weekly.currency == row.currency`。当前实现与契约不符。

**v1.0 功能无 bug**（SQL §5.2 已用 LIKE %destination% + currency=row.currency 过滤掉错的），但 score 加权评分失效，导致同 cost_price 多候选无法二级排序。

## C. 端到端对数（黄金样本 2-①.xlsx）

种子：3 条 PVG 周表（OZ→ATL=50、CK→MIA=70、NH→SYD=80 must_go）+ 2 条 surcharge（OZ myc=2/msc=1，NH myc=3.5/msc=0.8）

| row | sec | dest | type | status | n_cand | cost | airline |
|---|---|---|---|---|---|---|---|
| 4 | NRT | ATL | air | non_local_leg | 0 | — | |
| 13 | PVG | ATL | air | **filled** | 1 | **53.0000** | OZ |
| 14 | PVG | ATL | local | local_delivery_manual | 0 | — | |
| 15 | PVG | MIA | air | **filled** | 1 | **70.00** | CK |
| 16 | PVG | AMS | air | no_rate | 0 | — | |
| 18 | PVG | SYD | air | **filled** | 1 | **84.3000** | NH |
| 19 | PVG | TPE | air | no_rate | 0 | — | |
| 22 | AMS | ATL | air | non_local_leg | 0 | — | |
| 35 | ICN | ATL | air | non_local_leg | 0 | — | |

数字核对全部命中：50+2+1=53 ✓ / 70+0+0=70 ✓ / 80+3.5+0.8=84.3 ✓
状态分布：filled 3 / local_delivery_manual 2 / no_rate 2 / non_local_leg 19 ✓

## D. 边界反向验证

| ID | 输入 | 期望 | 实测 |
|---|---|---|---|
| D-1 | effective_on=2026-05-01（周外） | NO_RATE 不抛 | NO_RATE ✓ |
| D-2 | row.currency=USD vs 入库 CNY | NO_RATE | NO_RATE ✓ |
| D-3 | service_desc='OZ NH'，OZ全dash NH正常 | FILLED 仅 NH 候选 | FILLED, [NH] ✓ |
| D-4 | weekly 7 天价全 None | NO_RATE | NO_RATE ✓ |
| D-5 | row.origin_code='' | NO_RATE 不抛 | NO_RATE ✓ |

## E. 回归验证

T-B3（test_rate_repository.py 6 条）+ T-B4（test_customer_a_parse.py 14 条）独立单跑：20 passed in 0.41s。
extras 字典补丁（追加 4 个 key）未破坏 T-B3 中对 `extras["myc_fee_per_kg"]` 等的断言。

## P1 / P2 回炉清单

**P1（已派开发大师当场修复，不进 commit）**：
- `rate_matcher.py:169-173` `_build_candidate` 加 `row: PkgRow` 参数；`dest_exact` 与 `currency_match` 改用 row 字段比对
- 补 1 条 pytest：同 cost_price 不同 score（用 `case_by_case=True` 触发 ×0.5）→ 验证二级排序

**P2（覆盖率不足，留 T-B12 阶段补）**：
- `_calc_score` 中 `_CASE_BY_CASE_DAMP=0.5` 路径无单测
- `_calc_score` 中 `_NO_AIRLINE_PENALTY=0.1` 路径无单测
- `_pick_price_by_etd` 中"该天 None → 周内非 None 平均"分支无单测

## 监工复跑清单

```bash
cd /Users/zhangdongxu/Desktop/project/阪急阪神 && source .venv/bin/activate
cd backend && python -m pytest tests/services/step2_bidding/ -v
python /tmp/test_tb5_e2e.py
python /tmp/test_tb5_boundary.py
python -m pytest tests/services/step2_bidding/test_rate_repository.py tests/services/step2_bidding/test_customer_a_parse.py -v
```

## 测了 / 没测

**测了**：11 条单测 + 形式化审查 / 端到端 parse→match 真链路 / 5 条边界 / T-B3+T-B4 回归 / score 内部探针

**没测**（明示）：
- v2.0 才用的 query_ocean_fcl / query_lcl（不在 T-B5 范围）
- 真实 Step1 Air Adapter 入库链路再喂 matcher（用 in-memory + 直接 INSERT 替代）
- T-B5 与 T-B6/T-B7 联动（T-B6/T-B7 尚未交付）
- 并发 / 性能（任务单未要求）
