# 港口字典缺口整体修 — 设计文档

- 日期：2026-06-01
- 分支：`feature/step1-review-desk`
- 关联记忆：[[step1-one-contract-port-coverage-gap]] [[step1-pdf-one-contract-adapter]] [[nitori-ocean-db-match]] [[step1-air-ees-format]] [[mvp-minimal-scope-remind]]
- 前序：A4 海运审核台（`2026-06-01-ocean-review-desk-columns-design.md`）暴露出本问题

## 背景与问题

A4 后用户把真实 372 页 ONE 合约 PDF 入库，8032 入库 / 4284 跳过。诊断（重解析 12316 行 +
复刻 `commit_ocean_rows` 跳过逻辑）拆出：

- **287 无价**（编码行 R5/2400 等）→ 正常，不在本范围。
- **3997 未匹配**（港口查不到字典）→ 真运价被静默丢，是**字典覆盖缺口、非 bug**（A4 未碰跳过逻辑）。
  - 起运港未匹配 2783、目的港未匹配 1533（去重后 3997；船司 0）。

按性质分三类（数字为诊断实测行数）：

| 类 | 说明 | 行数 | 代表 |
|---|---|---|---|
| ① 别名/变体 | 港**已在字典**，只是名字对不上 | ~2081 | PUSAN→Busan、KAOHSIUNG CITY→Kaohsiung、SAINT LOUIS→St. Louis |
| ② 真缺 | 字典根本没有，需 seed | ~1595 | COCHIN、KOLKATA、夏威夷 HILO… |
| ③ 多港挤一格 | 一格 N 个码，现只取首个 | ~321(sea)+air | `USLAX USLGB`；air `SEA LAX SFO`/`MEX,MTY,CUN` |

## 目标

把 ① ② ③ 一并修，让 ONE 合约入库的「未匹配」从 3997 降到接近 0（仅余极少真·非港文本），
并修掉 air 区域多港格丢港。**成功标准 = 重跑诊断脚本，sea 未匹配 ≈ 0；air 区域格展开为多行。**

## 范围

### 本版做（4 个 phase）
1. **别名/变体归一** —— 共享 `port_normalizer` + 接进 sea 的 `_resolve_port`。
2. **补字典** —— seed 真缺的港 + 同步 reseed。
3. **sea 多港拆 N 行** —— `USLAX USLGB` → 2 行。
4. **air 区域多港拆 N 行** —— `SEA LAX SFO` → 3 行。

### 非目标（defer，见 [[mvp-minimal-scope-remind]]）
- 别名表上 DB（代码常量足够）。
- 统一三处 `_resolve_port`（`rate_parser` / `activator_mappers` / `ocean._resolve_port_ref`）重复实现——只抽**共享 normalizer**，不重构调用方。
- air 目的港解析成 `port_id`（air 入库 `AirTierRate` 本就存文本，无 port FK）。
- seed 里 `JPTOY` 被 Toyohashi 占用（Toyama 的官方码）这个**既有错配**——仅记录，本次不动；Toyama Shinko 用新码避让。
- 附加费金额、合约级 MQC（与本问题无关）。

## 设计

### Phase 1 · 别名/变体归一

**新建** `backend/app/services/step1_rates/port_normalizer.py`：

```python
# 别名表：合约/料表里的写法 → 字典里的规范名（全大写比较）
PORT_ALIASES = {
    "PUSAN": "BUSAN",
    "CHITTAGONG": "CHATTOGRAM",
    "KLANG": "KELANG",          # PORT KLANG → PORT KELANG
    "SAINT": "ST",              # SAINT LOUIS → ST LOUIS（再与 "St. Louis" 去标点匹配）
}
_SUFFIXES = ("CITY", "PORT")    # 去尾缀：KAOHSIUNG CITY / KATTUPALLI PORT

def canonicalize(name: str) -> str:
    """大写 → 去标点 → 折空格 → 去 CITY/PORT 尾缀 → 套别名（逐词）。
    产出一个『更可能命中字典』的规范名，交给现有 _resolve_port 的匹配步骤。"""
```

**接入** `activator_mappers._resolve_port`（commit_ocean_rows 用的就是它）：在现有
「name_en/cn 包含 → 去括号折空格」步骤**都失败后**，加一个 fallback：
`canon = canonicalize(name)`，对 `canon` 再走一遍现有匹配（含**去标点+折空格**双向比较，
解决 "St. Louis" 的 `.`）。`rate_parser._resolve_port` 同样接入（KMTC/NVO 等 Excel 海运同受益）。

> 关键：canonicalize 只产出规范名，**复用**现有匹配逻辑命中字典，不引入全表扫描。
> 别名/尾缀为「逐词」处理：`PUSAN`→`BUSAN`、`KAOHSIUNG CITY`→`KAOHSIUNG`、`PORT KLANG`→`PORT KELANG`。

### Phase 2 · 补字典

往 `scripts/seed_data.py` 的 `PORTS` 追加下列港（`(un_locode, name_en, name_cn, country, region)`），
**locode 为 demo 临时值**（保证唯一即可；解析按 name 匹配，不依赖官方 locode 精确）：

```python
# === 2026-06 ONE 合约覆盖缺口补充 ===
# 起运港（亚洲/南亚/非洲）
("INCOK", "Cochin", "科钦", "India", "South Asia"),
("LKCMB", "Colombo", "科伦坡", "Sri Lanka", "South Asia"),
("INCCU", "Kolkata", "加尔各答", "India", "South Asia"),
("INNML", "Mangalore", "芒格洛尔", "India", "South Asia"),
("INPAV", "Pipavav", "皮帕瓦沃", "India", "South Asia"),
("PKBQM", "Muhammad Bin Qasim", "卡西姆港", "Pakistan", "South Asia"),
("TWTYN", "Taoyuan", "桃园", "Taiwan", "East Asia"),
("CNSHK", "Shekou", "蛇口", "China", "East Asia"),
("JPNAH", "Naha", "那霸", "Japan", "East Asia"),
("JPTYM", "Toyama Shinko", "富山新港", "Japan", "East Asia"),
("MZBEW", "Beira", "贝拉", "Mozambique", "East Africa"),
("ZACPT", "Cape Town", "开普敦", "South Africa", "Southern Africa"),
("ZACOE", "Coega", "科加", "South Africa", "Southern Africa"),
("ZADUR", "Durban", "德班", "South Africa", "Southern Africa"),
("MZMPM", "Maputo", "马普托", "Mozambique", "East Africa"),
("NAWVB", "Walvis Bay", "鲸湾港", "Namibia", "Southern Africa"),
# 目的港（美国/夏威夷）
("USITO", "Hilo", "希洛", "USA", "North America"),
("USOGG", "Kahului", "卡胡卢伊", "USA", "North America"),
("USKWH", "Kawaihae", "卡瓦伊哈埃", "USA", "North America"),
("USLIH", "Nawiliwili", "纳威利威利", "USA", "North America"),
("USHVY", "Harvey", "哈维", "USA", "North America"),
("USPHL", "Philadelphia", "费城", "USA", "North America"),
```

**reseed 已自动覆盖（已核实）**：`seed_data.reseed_dictionaries`（:309）与 `seed_ports` **共享同一个
`PORTS` 列表、不复制**；`admin.py` 又是动态加载 `scripts/seed_data.py` 调该函数。故**只改 `PORTS`
一处即可**，Admin「清空运价」回灌自动带上新港，**无需改 admin.py**。

### Phase 3 · sea 多港拆 N 行

**位置**：`orchestrator.add_file`（有 db），在 sea 归一后加一步 `expand_multi_port_sea(rows, db)`。

```python
def expand_multi_port_sea(rows, db):
    """sea 归一行：destination 形如 'USLAX USLGB'（多 UN/LOCODE）→ 拆成 N 行（同价）。
    仅当按空白拆出 >1 段、且【每段都能 _resolve_port 成港】才拆；否则原样
    （'LOS ANGELES' 的 'LOS'/'ANGELES' 单独解析不成 → 不拆）。"""
```

拆出的每行 = 原行浅拷贝 + 单一 `destination`（其余字段含价格不变）。审核台会展示拆开后的 N 行（透明）。

### Phase 4 · air 区域多港拆 N 行

**位置**：`air_ees._clean_dest`（air_ees.py:219）。

- 现状：`_IATA.search(s)` 取**首个**三字码 → 区域格只剩首港。
- 改为：`_IATA.findall(s)` 取**全部**三字码，返回 `list[str]`；调用处（行构建循环，约 air_ees.py:140-162）
  对每个码发一行（其余字段含 tier_prices 不变）。
- 单码（`KIX`、去前缀后的 `DFW`）→ findall 得 1 个 → 行为不变。`>1` 才算多港。
- **同查 `air_weight_break.py`**（唯凯）是否有同款 `_clean_dest`/首码逻辑；有则一并改，无则不动。

## 数据流

```
ONE 合约 PDF → 解析 → _normalize_sea → add_file:
    └ expand_multi_port_sea(db)            ← Phase 3：USLAX USLGB → 2 行
  → session.rows → 审核台（展示拆开后的行）
  → commit_ocean_rows → _resolve_port      ← Phase 1：canonicalize 兜底命中字典(Phase 2 新港)

EES Excel → air_ees.extract → _clean_dest(findall) ← Phase 4：SEA LAX SFO → 3 行
  → air 归一 → 审核台 → commit_tier_rows（destination 存文本）
```

## 错误处理 / 边界

- **单港多词名不被拆**（Phase 3）：`LOS ANGELES`/`NEW YORK`/`PORT KELANG` 因分段无法各自解析成港 → 保持整体。
- **别名误伤**：别名/尾缀逐词且大写精确匹配，`PORT KELANG` 的 `KELANG` 不会被当 `PORT` 尾缀误删（尾缀仅去**末尾独立词** CITY/PORT，且去后仍须能解析，不能解析则回退原名）。
- **air 误拆**：仅当 `findall` 命中 >1 个三字码才发多行；普通单港 cell 不受影响。区域格里的中文标签（如「美国西部：」）不含大写拉丁三连，不会被 `_IATA` 误匹配。
- **locode 冲突**：新 locode 与现有不重复（已避让 `JPTOY`/`CNTAO` 等）。

## 测试 / 验证

- **诊断脚本回归（核心指标）**：重跑 `/tmp/a4_skip_diag.py`（已存在）→ sea 未匹配从 3997 降到接近 0；
  按 phase 增量验证（仅 Phase1 后 ~2081↓、+Phase2 ~1595↓、+Phase3 ~321↓）。
- **单测（TDD）**：
  - `port_normalizer`：`canonicalize("PUSAN")=="BUSAN"`、`"KAOHSIUNG CITY"→"KAOHSIUNG"`、`"SAINT LOUIS"→"ST LOUIS"`、`"PORT KLANG"→"PORT KELANG"`。
  - sea 拆分：`expand_multi_port_sea` 对 `USLAX USLGB` 出 2 行同价、对 `LOS ANGELES` 出 1 行不拆。
  - air 拆分：`_clean_dest("SEA LAX SFO")→["SEA","LAX","SFO"]`、`"NH-DFW"→["DFW"]`、`"MEX,MTY,CUN"→3`。
  - `_resolve_port`：新增别名/新港端到端命中（PUSAN→Busan、COCHIN→新 seed）。
- **全量**：`pytest -q` 不回归（基线 365 passed，仅 3 vLLM 环境失败）；`scripts/seed_data.py` 跑通、港口数增加。
- **手测**：重新做表入库 ONE 合约 → 提示「未匹配」数显著下降；air EES 做表 → 区域格目的港变多行。

## 文件级改动清单（预估，细节交 plan）

- 新增 `backend/app/services/step1_rates/port_normalizer.py`（+ 测试 `tests/.../test_port_normalizer.py`）。
- 改 `backend/app/services/step1_rates/activator_mappers.py`（`_resolve_port` 接 normalizer fallback）。
- 改 `backend/app/services/rate_parser.py`（`_resolve_port` 同上）。
- 改 `scripts/seed_data.py`（`PORTS` 追加；`reseed_dictionaries` 共享同列表，admin.py 动态加载，**无需改 admin.py**）。
- 改 `backend/app/services/step1_rates/sheet_builder/orchestrator.py`（`add_file` 加 `expand_multi_port_sea`）。
- 改 `backend/app/services/step1_rates/sheet_builder/air_ees.py`（`_clean_dest` findall + 调用处发多行）；按需 `air_weight_break.py`。
- 测试：`tests/sheet_builder/`、`tests/services/step1_rates/` 增用例。
