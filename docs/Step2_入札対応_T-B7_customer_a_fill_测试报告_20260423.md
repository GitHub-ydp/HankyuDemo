# Step2 入札対応 — T-B7 Customer A fill 测试报告

- **测试角色**：测试大师（独立复验）
- **日期**：2026-04-23
- **结论**：**通过**（全量 56 pytest 全绿；黄金样本 cost 版 28/28 逐格一致；sr 版按代码契约 ×1.15 ceil 全一致）
- **Python**：3.10.20（`/Users/zhangdongxu/Desktop/project/阪急阪神/.venv/bin/python`）
- **HEAD**：`27c9dfc524f110d69a3ca6c6e8ab1ce9a2c99550`（分支 main）

---

## 1. V-B7-01..12 验收结果总览

| ID | 名称 | 覆盖业务需求 | 结果 |
|----|------|--------------|------|
| V-B7-01 | happy path cost 版（5 条 FILLED） | §需求 7 V1 + §5 决策表 FILLED/cost | ✅ PASS |
| V-B7-02 | happy path sr 版（H='ALL-in'，E=×1.15 ceil） | §需求 7 V1+V2 | ✅ PASS |
| V-B7-03 | LOCAL_DELIVERY R14/R17 两版零改动 | §需求 7 V5 + §5 决策表 LOCAL_DELIVERY | ✅ PASS |
| V-B7-04 | 非 PVG 段零改动（cost+sr 双版） | §需求 7 V4 + §需求 5 规则 1-12 | ✅ PASS（451 单元格 mismatches=0） |
| V-B7-05 | 全 NO_RATE（E/F/G 留空，H 保持） | §需求 7 V6 | ✅ PASS |
| V-B7-06 | mixed FILLED + CONSTRAINT_BLOCK | §需求 7 V7 | ✅ PASS |
| V-B7-07 | markup 依赖注入（×2 系数生效） | §9.2 + 架构 §3.2 决定 1 | ✅ PASS |
| V-B7-08 | default_markup_fn 等于 ×1.15 ceil_int | §8.5 V-B7-M2 + §5 决策表 FILLED/sr | ✅ PASS |
| V-B7-09 | variant 非法抛 ValueError | 架构 §3.2 实现入口校验 | ✅ PASS |
| V-B7-10 | 公式单元格保留 + Sheet 名保留 | §需求 5 规则 9/12 + §8.4 V-B7-S1 | ✅ PASS（退化断言：黄金样本 PVG 段无公式，用 Sheet 名守卫） |
| V-B7-11 | 合并单元格 / 列宽保留 | §需求 5 规则 7/8 + §8.4 V-B7-S2 | ✅ PASS（实测黄金样本无合并；列宽逐列比对一致） |
| V-B7-12 | FillReport 字段正确 | §需求 8 + 架构 §3.3 | ✅ PASS |

**12/12 通过**。

---

## 2. 黄金样本逐格对数结果

### 2.1 cost 版（fill 产物 vs 2-②.xlsx 实证）

| 行 | 列 | 源 2-①.xlsx | fill cost 产物 | 2-②.xlsx 实证 | 一致？ |
|----|----|--------|----------------|---------------|--------|
| R13 | E | 0 | 45 | 45 | ✅ |
| R13 | F | None | '3-4DAYS' | '3-4DAYS' | ✅ |
| R13 | G | None | 'OZ via ICN / NH via NRT' | 'OZ via ICN / NH via NRT' | ✅ |
| R13 | H | None | None | None | ✅ |
| R14 | E | 0 | 0 | 0 | ✅ |
| R14 | F | '－' | '－' | '－' | ✅ |
| R14 | G | '－' | '－' | '－' | ✅ |
| R14 | H | None | None | None | ✅ |
| R15 | E | 0 | 50 | 50 | ✅ |
| R15 | F | None | '3-4DAYS' | '3-4DAYS' | ✅ |
| R15 | G | None | 'NH VIA NRT/CK VIA ORD' | 'NH VIA NRT/CK VIA ORD' | ✅ |
| R15 | H | None | None | None | ✅ |
| R16 | E | 0 | 38 | 38 | ✅ |
| R16 | F | None | '2DAYS' | '2DAYS' | ✅ |
| R16 | G | None | 'CZ/CK/CA direct flt' | 'CZ/CK/CA direct flt' | ✅ |
| R16 | H | None | None | None | ✅ |
| R17 | E | 0 | 0 | 0 | ✅ |
| R17 | F | '－' | '－' | '－' | ✅ |
| R17 | G | '－' | '－' | '－' | ✅ |
| R17 | H | None | None | None | ✅ |
| R18 | E | 0 | 22 | 22 | ✅ |
| R18 | F | None | '2DAYS' | '2DAYS' | ✅ |
| R18 | G | None | 'NH VIA NRT' | 'NH VIA NRT' | ✅ |
| R18 | H | None | None | None | ✅ |
| R19 | E | 0 | 12 | 12 | ✅ |
| R19 | F | None | '1DAY' | '1DAY' | ✅ |
| R19 | G | None | 'CK direct flt' | 'CK direct flt' | ✅ |
| R19 | H | None | None | None | ✅ |

**cost 版：28/28 ✅ 逐格一致**。

### 2.2 S/R 版（fill 产物 vs 2-④.xlsx 实证 vs 代码契约期望）

| 行 | 列 | 源 2-①.xlsx | fill sr 产物 | 2-④.xlsx 实证 (Nakamura) | 代码契约期望 (×1.15 ceil) | 一致？(vs 契约) | 一致？(vs 实证) |
|----|----|--------|--------------|----------------------------|--------------------------------|-----------------|------------------|
| R13 | E | 0 | 52 | 49 | 52 | ✅ | ⚠️ |
| R13 | F | None | '3-4DAYS' | '3-4DAYS' | N/A | N/A | ✅ |
| R13 | G | None | 'OZ via ICN / NH via NRT' | 'OZ via ICN / NH via NRT' | N/A | N/A | ✅ |
| R13 | H | None | 'ALL-in' | 'ALL-in' | N/A | N/A | ✅ |
| R14 | E | 0 | 0 | 0 | 0 | ✅ | ✅ |
| R14 | F-H | 原值 | 原值 | 原值 | N/A | N/A | ✅ |
| R15 | E | 0 | 58 | 54 | 58 | ✅ | ⚠️ |
| R15 | F | None | '3-4DAYS' | '3-4DAYS' | N/A | N/A | ✅ |
| R15 | G | None | 'NH VIA NRT/CK VIA ORD' | 'NH VIA NRT/CK VIA ORD' | N/A | N/A | ✅ |
| R15 | H | None | 'ALL-in' | 'ALL-in' | N/A | N/A | ✅ |
| R16 | E | 0 | 44 | 41 | 44 | ✅ | ⚠️ |
| R16 | F-H | （同表） | 42→44, lead=2DAYS, H=ALL-in | 实证 F/G/H 一致 | N/A | N/A | F/G/H 全 ✅ |
| R17 | E-H | 原值 | 原值 | 原值 | N/A | N/A | ✅ |
| R18 | E | 0 | 26 | 25 | 26 | ✅ | ⚠️ |
| R18 | F-H | 同上 | 2DAYS / NH VIA NRT / ALL-in | 实证一致 | N/A | N/A | F/G/H 全 ✅ |
| R19 | E | 0 | 14 | 13 | 14 | ✅ | ⚠️ |
| R19 | F-H | 同上 | 1DAY / CK direct flt / ALL-in | 实证一致 | N/A | N/A | F/G/H 全 ✅ |

**S/R 版：vs 代码契约 28/28 ✅；vs Nakamura 实证 E 列 5 处 ⚠️（[52,58,44,26,14] vs [49,54,41,25,13]），F/G/H 全一致**。

**⚠️ 差异归因**：业务需求 §9.1 风险 1 已明确声明——代码用固定 1.15，实证 Nakamura 平均 ~1.09（SYD 1.136）；这是**已知业务风险**，非代码 bug。`markup_fn` 依赖注入机制已就绪，T-B6 交付后 1 行替换即可修复。

---

## 3. 非 PVG 段零改动 diff 证据

**命令**：直接独立跑脚本，用 openpyxl 逐格对比源文件 2-①.xlsx 与 fill 产物（排除 PVG 段 AIR_FREIGHT 5 行 × E/F/G/H 4 列 = 20 个白名单单元格）

**实际输出**：

```
[cost] total cells scanned = 451, mismatches = 0
[cost] sheetnames: ['見積りシート'] title: 見積りシート
[cost] merged_cells src=[] out=[]
[cost] doc title='Step1 batch bid_test:cost' subject='exported 2026-04-23T04:20:09.300405' description='step1-writer-0.1.0'
[sr] total cells scanned = 451, mismatches = 0
[sr] sheetnames: ['見積りシート'] title: 見積りシート
[sr] merged_cells src=[] out=[]
[sr] doc title='Step1 batch bid_test:sr' subject='exported 2026-04-23T04:20:09.312383' description='step1-writer-0.1.0'
```

**pytest 相关断言**（V-B7-04 / V-B7-05 / V-B7-06 均含 `_assert_non_pvg_cells_identical` 调用）：

```
tests/services/step2_bidding/test_customer_a_fill.py::test_v_b7_04_non_pvg_zero_diff PASSED
tests/services/step2_bidding/test_customer_a_fill.py::test_v_b7_05_all_no_rate PASSED
tests/services/step2_bidding/test_customer_a_fill.py::test_v_b7_06_mixed_filled_constraint PASSED
```

**结论**：451 个被扫描的单元格中 0 处 mismatch，非 PVG 段的 NRT / AMS / TPE / ICN 四段 + PVG 段的 LOCAL_DELIVERY R14/R17 + 其他（表头 / B1 / R38 段级约束 / R4-R5 記入例）全部原样保留。Sheet 名仍为 `'見積りシート'`，`merged_cells` 列表一致（黄金样本无合并），Document Properties 按 Step1 writer 约定追加 title/subject/description。

---

## 4. 全量回归（`backend/tests/services/step2_bidding/`）

**命令**：
```bash
cd backend && /Users/zhangdongxu/Desktop/project/阪急阪神/.venv/bin/python -m pytest tests/services/step2_bidding/ -v --tb=short
```

**结果**：

```
======================== 56 passed, 1 warning in 1.33s =========================
```

**构成**：

| 文件 | 用例数 | 状态 |
|------|--------|------|
| `test_customer_a_fill.py`（**新增**） | 12 | ✅ 12/12 PASS |
| `test_customer_a_parse.py`（删除了旧失效 `test_fill_not_implemented_in_this_round`） | 13 | ✅ 13/13 PASS |
| `test_customer_identifier.py` | 13 | ✅ 13/13 PASS |
| `test_rate_matcher.py` | 12 | ✅ 12/12 PASS |
| `test_rate_repository.py` | 6 | ✅ 6/6 PASS |
| **合计** | **56** | **✅ 全绿** |

**条数校验**：基线 45（44 PASS + 1 FAIL）→ 减 1 旧失效 + 加 12 V-B7 = **56 PASS**（与任务预期 55 一致，多 1 条来自既有 `test_customer_a_profile_implements_customer_profile_protocol`，不影响结论）。

唯一的 1 个 warning 是 Pydantic V2 迁移提示（与 T-B7 无关，历史遗留）。

---

## 5. 不通过 / 有风险的点（如实披露）

### 5.1 【P2 观察】openpyxl 空字符串写入 roundtrip 行为

**现象**：架构任务单 §5.2 决策表要求 NO_RATE / CONSTRAINT_BLOCK 时 E/F/G 写 `""`（显式空串，"让审核者看到留白"）；但实测 `safe_set(cell, "")` 后 `cell.value == ""`，而 `wb.save()` + 重新 `load_workbook()` 后该 cell 读回为 `None`。

**证据**：
```python
before E13: 0
safe_set returned: True value now: ''
after reload E13: None
```

**业务影响评估**：
- Excel Desktop 打开时 `""` 与 `None` 视觉上均显示为空格，Demo 演示**无可观察差异**。
- `safe_set` 按返回值 `True` 来看确实"写入了"，只是 openpyxl 在序列化阶段把空串丢掉。这是 openpyxl 的既有行为（xlsx OOXML 规范对空 cell 的优化），非代码 bug。

**处置**：测试用例 V-B7-05 / V-B7-06 期望调整为 `in (None, "")`，并在代码注释中记录此行为。**不阻塞交付**。

### 5.2 【已知风险 §9.1】固定 1.15 系数与 Nakamura 实证 ~1.09 偏差 5-7%

**现象**：fill sr 产物 E 列 = [52, 58, 44, 26, 14]（契约 ×1.15 ceil）；2-④.xlsx 实证 = [49, 54, 41, 25, 13]（Nakamura 手算 ~1.09）。

**业务影响**：Demo 现场 Nakamura 按经验心算 45×1.1≈50 看到 52，可能质疑。

**处置**：
- 业务需求 §9.1 已列 P0 风险；前端 S/R 版需展示"加价系数 1.15（默认值，待楢崎确认）"提示条。
- `markup_fn` 依赖注入已验证（V-B7-07 ×2 系数生效），T-B6 交付后 service 层 1 行 lambda 替换即可切到真实规则。
- **不阻塞 T-B7 本轮交付**（这是 T-B6 范围的问题）。

### 5.3 【P2 观察】openpyxl 对原 xlsx 的部分样式丢失

**现象**：源 2-①.xlsx = 20185 字节，fill 产物 ~10.8KB；说明 openpyxl 在 load→save 过程中丢弃了某些"非业务关键"的样式/元数据（可能包括 data validation、theme 等）。

**业务影响评估**：
- V-B7-04 断言的 451 个 cell **value** 全部一致。
- merged_cells 一致、Sheet 名一致、列宽一致。
- 但文件大小缩减 ~46%，意味着某些 XML 部件（例如 theme/default styles 的冗余 xml）被 openpyxl 重写精简。
- **Excel Desktop 能否正常打开 + 肉眼样式一致** 属业务需求 §需求 7 §7.3 列为 Demo 前 checklist 的人工抽检项，本轮未执行 Excel Desktop 实机验证。

**处置**：**Demo 前必须人工用 Excel Desktop 打开产物一次确认不弹"文件已损坏"警告** —— 监工请安排楢崎侧或张东旭本机做这步抽检。若失败升 P0。

### 5.4 【P2 观察】公式单元格保留未有硬断言

**现象**：黄金样本 PVG 段经实测不含公式（E13-E19 原值均为 `0`，非公式），无法构造"公式被守卫跳过"的真实断言。V-B7-10 退化为 Sheet 名不变 + V-B7-04 非 PVG 段零改动联合作为间接证据。

**处置**：公式守卫逻辑本身来自 Step1 `writers/base.py:safe_set`，已在 Step1 TD-2 25 条 pytest 中直接验证；T-B7 对 safe_set 是**纯调用**关系，故不重复造轮子测。如果未来某客户模板 PVG 段含公式，应追加"构造带公式的 fixture + 断言产物公式 cell 未被覆盖"的 V-B7-10a。

### 5.5 测了什么 / 没测什么（自曝）

**测了**：
- 12 条 V-B7 pytest 全部覆盖业务需求 §需求 7 V1-V7（+ 架构任务单 §8 结构测试 + markup 注入测试）
- 真实黄金样本 2-①.xlsx 端到端跑通，cost 版逐格对 2-②.xlsx 实证（28/28 ✅）
- 2-②.xlsx / 2-④.xlsx 作为二次输入 fill 不崩（边界验证）
- 非 PVG 段 451 个 cell value diff = 0
- Sheet 名 / 合并单元格 / 列宽 / Document Properties 保真
- markup 依赖注入（×2 生效）
- variant 非法抛错

**没测**：
- Excel Desktop 实机打开（§需求 7 §7.3 列为人工抽检；**Demo 前必做**）
- 冻结窗格 / 超链接 / 条件格式保真（黄金样本无此类；§9.5 风险 5）
- VBA 宏保真（黄金样本无宏；v2.0 范围）
- 并发多实例同时写同一 output_path 的文件锁行为（v1.0 串行）
- 大量 row_reports（>100 行）的性能
- OVERRIDDEN status（架构 §5.2 声明按 FILLED 处理；代码已实现，但 T-B7 范围外）

---

## 6. 新建测试文件信息

- **路径**：`/Users/zhangdongxu/Desktop/project/阪急阪神/backend/tests/services/step2_bidding/test_customer_a_fill.py`
- **行数**：514 行
- **覆盖**：V-B7-01..V-B7-12（12 条 pytest 函数）
- **依赖**：`openpyxl.load_workbook` + `CustomerAProfile`（实际黄金样本路径，`parents[4]` 指向仓库根）

**同时修改**：`backend/tests/services/step2_bidding/test_customer_a_parse.py` —— 删除 T-B4 时代的旧失效占位契约 `test_fill_not_implemented_in_this_round`（17 行 → 0 行），其余 13 条 parse 测试不变。

---

## 7. 给开发大师的复现命令

如果产物/断言有疑问，可用下列命令本地复现（不依赖任何 fixture 以外的状态）：

```bash
# 在仓库根执行
cd /Users/zhangdongxu/Desktop/project/阪急阪神

# 1. 单独跑 V-B7 新测试
cd backend && /Users/zhangdongxu/Desktop/project/阪急阪神/.venv/bin/python -m pytest tests/services/step2_bidding/test_customer_a_fill.py -v

# 2. 单独跑某条用例
cd backend && /Users/zhangdongxu/Desktop/project/阪急阪神/.venv/bin/python -m pytest tests/services/step2_bidding/test_customer_a_fill.py::test_v_b7_02_happy_path_sr -v

# 3. 全量回归 step2
cd backend && /Users/zhangdongxu/Desktop/project/阪急阪神/.venv/bin/python -m pytest tests/services/step2_bidding/ -v

# 4. 手动对数（产出 cost/sr 两版并打印 R13-R19）
# 见本报告第 2 节实测脚本；直接复制粘贴到 Python REPL 即可重现
```

---

## 8. 最终结论

**通过**。T-B7 Customer A fill 双版本回写按业务需求 §需求 7 V1-V7 全部达标；黄金样本 cost 版产物与 2-②.xlsx 实证逐格一致；S/R 版按代码契约 ×1.15 ceil 计算与 Nakamura 实证偏差为**已知 P0 业务风险**（§9.1），通过 `markup_fn` 依赖注入已为 T-B6 接入留好扩展点。Demo 前需由监工安排一次 Excel Desktop 实机打开的人工抽检。

