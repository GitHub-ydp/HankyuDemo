# Step1 NVO FAK adapter — 架构任务单

- **版本**：v1.0
- **发布日期**：2026-04-27
- **作者**：架构大师
- **业务依据**：用户口述 — 追加第 5 个固定 adapter，处理 `资料/2026.03.31/NVO FAK 2026 (Mar 20 to Mar 31).xlsx`，参考 `/tmp/old_parser/rate_parser.py:486-629` 的 `parse_nvo_fak_excel`
- **同类参考**：
  - `docs/Step1_kmtc_adapter_架构任务单_20260427.md`（行/列、In/Out、§9 自检风格 — 必须对齐此格式）
  - `backend/app/services/step1_rates/adapters/kmtc.py:1-565`（最近 hot fix 后的 db-free 范式 — NVO 必须沿用）
  - `backend/app/services/step1_rates/adapters/ocean_ngb.py:1-611`（多 sheet 输出范式 — NVO 4 sheet 直接拼）
- **读者**：开发大师（按本单直接动手，不二次决策）、测试大师（按 §7 验收点写用例）、监工（抽查 file:line 真实性）

## 红线（开发大师必须遵守，违反必被打回）

1. 不动 `entities.py` / `protocols.py` / `service.py` 顶层结构 / `registry.py` / `normalizers.py`
2. 不动 air / ocean / ocean_ngb / kmtc 四 adapter 的任何一行代码
3. 不给 `activator.py` / `activator_mappers.py` 加 NVO 专属分支（必须走通用 `to_freight_rate_from_ngb` 路径，复用 `_lookup_carrier` / `_resolve_port`）
4. 不写 alembic migration（schema 不变）
5. 不动 `/tmp/old_parser/rate_parser.py`（参考资料）
6. 不抽 `_BaseRateAdapter` 共用基类（CLAUDE.md "三份相似比过早抽象好"，第 5 份依然底线 — 单文件内实现）
7. **不在 adapter 里做 db-aware 早期校验** — KMTC hot fix 教训：adapter 必须纯解析，destination/origin port 仅做字符串清洗，db 解析交 activator
8. 不顺手清老 `app.services.rate_parser`（仍被 ocean / ocean_ngb / kmtc adapter 共用）
9. 不做 KMTC（已完成）
10. 不实现 Hawaii 双行表头的"自动列合并"通用框架 — 写死 R5+R6 即可

---

## 0. 任务范围（in / out 边界）

### 0.1 IN（本任务做的）

- 新建 `backend/app/services/step1_rates/adapters/nvo_fak.py` — 实现 `NvoFakAdapter`，单文件内实现，不抽公共基类
- 实现 `detect()`（文件名 / sheet 名 / 表头三策略）+ `parse()`（openpyxl + 4 sheet 循环 + 多区段表头分段扫描）
- 输出 `ParsedRateBatch`：`file_type=ocean`、`adapter_key="nvo_fak"`、`metadata={parser_version, sheets, effective_from/to, base_ports, record_kind_distribution}`
- 每条 record `record_kind="ocean_ngb_fcl"`（复用 NGB 入库通道，避免改 activator dispatch；详见 §3.1）
- 修改 `backend/app/services/step1_rates/adapters/__init__.py:1-11` — 注册 `NvoFakAdapter`
- 修改 `backend/app/services/step1_rates/service.py:13-21` — `build_default_registry` 中追加 `NvoFakAdapter()`
- 修改 `backend/app/services/rate_parser.py:19-131` PORT_ALIAS_MAP — 追加 14 条 alias（详见 §4.3）
- 修改 `scripts/seed_data.py:16-183` — 追加 6 条 ports（详见 §4.4）
- 新建 `backend/tests/services/step1_rates/adapters/test_nvo_fak_adapter.py` — pytest 验收点骨架（V-N01..V-N12）

### 0.2 OUT（本任务不做的）

- 不扩 `Step1FileType` 枚举（不加 `nvo_fak` 值）。复用 `Step1FileType.ocean`，理由同 KMTC（避免 entities/迁移/前端 enum 联动改造）。区分由 `adapter_key="nvo_fak"` 携带
- 不动 `Step1RateRow` schema — 现有字段 `container_20gp/40gp/40hq/container_45/service_code/valid_from/valid_to/remarks/extras` 已可承载 NVO 全部字段
- 不复用老 parser 的 `_match_carrier`（会自动建 carrier，违反"adapter 只输出 records"约定）。Carrier 名固定写 `"NVO_FAK"`，由 `_lookup_carrier` 精确匹配（seed 已有：`scripts/seed_data.py:205`）
- 不解析 `Arbitrary` sheet（这不是 FAK 干线运价，是 origin → port 的内陆中转杂费表，与 FreightRate 表 schema 不匹配。详见 §3.6 决策）
- 不把 `Effective from 3/20 to 3/31` 中的"年份外的 month/day"反向推断为下一年度（即跨年只接受 file 内含 4 位年份时；老 parser 实现一致）
- 不解析 IPI / Garment / DG cargo / Africa 段的"加价文本"为结构化字段（这些是 T&C 文本，写入 metadata.notes 留档）
- 不做 RAD 数值入库（详见 §3.4）
- 不写物理表（落库由 activator 统一处理）
- 不做前端 / Writer / API 改造

---

## 1. 数据流图

```
xlsx (NVO FAK 2026 (Mar 20 to Mar 31).xlsx, 4 sheets)
  ↓ openpyxl.load_workbook(path, data_only=True)
  ↓ NvoFakAdapter.parse(path, db)
  ↓
 for sheet in ['TPE', 'WPE', 'Hawaii']:        # Arbitrary skip（§3.6）
   ws = wb[sheet]
   ┌───────────────────────────────────────────────────────────────────┐
   │ TPE / WPE 通道（_parse_main_sheet）：                               │
   │  ├─ effective_from/to, year = _extract_effective_dates(ws)         │
   │  ├─ base_ports = _extract_base_ports(ws)                           │
   │  │     从前 5 行 A 列正则 'All Base Ports: ...'                    │
   │  ├─ section_iter = _iter_sections(ws)                              │
   │  │     扫所有 'Origin' 行作为段首，下一段首前/sheet 末为段尾        │
   │  │     段头列布局动态识别（_locate_columns_at_header_row）         │
   │  │     -> [(header_row, end_row, layout, section_label)]           │
   │  └─ for sec in section_iter:                                       │
   │       for ri in range(sec.header_row+1, sec.end_row):              │
   │         row = [ws.cell(ri, c).value for c in 1..max_col]           │
   │         if _should_skip(row, sec.layout): continue                 │
   │         records.extend(_build_records_from_row(                    │
   │             row, ri, sec.layout, sheet, sec.label, eff_from, eff_to│
   │         ))   # 一行多 origin 时拆多 record                          │
   ├───────────────────────────────────────────────────────────────────┤
   │ Hawaii 通道（_parse_hawaii_sheet）：                                 │
   │  ├─ effective_from/to = _extract_effective_dates(ws)               │
   │  ├─ layout = 写死 {country=1, origin=2, dest=3,                    │
   │  │            c20=4, c40=5, hc=6, c45=7}（R5+R6 双行合并表头）     │
   │  ├─ for ri in range(7, max_row+1):                                 │
   │  │   if _hawaii_should_skip(row): break  # REMARK / Note → break  │
   │  │   record = _build_hawaii_record(row, ri, eff_from, eff_to)     │
   │  │   if record is not None: records.append(record)                 │
   ├───────────────────────────────────────────────────────────────────┤
   │ Arbitrary 通道：跳过 + warning "Arbitrary sheet skipped (inland    │
   │   arbitrary fees, not freight rate)"                               │
   └───────────────────────────────────────────────────────────────────┘
  ↓
 records (~250-300 条) + warnings (去重) + metadata
  ↓
 ParsedRateBatch (file_type=ocean, adapter_key="nvo_fak")
  ↓ rate_batch_service._build_draft_batch → DraftRateBatch
  ↓ activator.activate(draft, db, dry_run/真激活)
       └─ for record in dispatchable: kind == "ocean_ngb_fcl"
            → to_freight_rate_from_ngb(record, batch_uuid, db)
                 ├─ _lookup_carrier(db, "NVO_FAK") → 命中 Carrier.code='NVO_FAK'
                 ├─ _resolve_port(db, origin_port_name="KRPUS") → 5字符 LOCODE 精确命中
                 ├─ _resolve_port(db, destination_port_name="Long Beach") → ilike 命中 USLGB
                 └─ FreightRate(... rate_level=None ...) 写入 freight_rates 表
```

---

## 2. 文件级改动清单

| 动作 | 路径 | 行号 / 说明 |
|---|---|---|
| 新增 | `backend/app/services/step1_rates/adapters/nvo_fak.py` | 单文件实现 NvoFakAdapter；约 450-550 行（比 kmtc 长，因 4 sheet + 多段表头） |
| 修改 | `backend/app/services/step1_rates/adapters/__init__.py:1-11` | line 4 后追加 `from app.services.step1_rates.adapters.nvo_fak import NvoFakAdapter`；`__all__` 列表（line 6-11）追加 `"NvoFakAdapter"` |
| 修改 | `backend/app/services/step1_rates/service.py:13-21` | `build_default_registry` line 7 import 加 `NvoFakAdapter`；line 15-20 adapters 列表追加 `NvoFakAdapter()` |
| 修改 | `backend/app/services/rate_parser.py:19-131` PORT_ALIAS_MAP | 14 条 alias 追加（详见 §4.3）— 在文件 line 131 } 闭合前插入 |
| 修改 | `scripts/seed_data.py:91` 后或 §4.4 指定位置 | 6 条 ports 追加（详见 §4.4） |
| 新增 | `backend/tests/services/step1_rates/adapters/test_nvo_fak_adapter.py` | pytest；fixture 用 `资料/2026.03.31/NVO FAK 2026 (Mar 20 to Mar 31).xlsx`；本单只定义 §7 验收点，用例由测试大师写 |
| 不动 | `backend/app/services/step1_rates/entities.py:18-22` | `Step1FileType.ocean` 复用；`Step1RateRow` 字段（line 53-108）足够 |
| 不动 | `backend/app/services/step1_rates/activator.py` | `kind == "ocean_ngb_fcl"` 已分流到 `to_freight_rate_from_ngb`，NVO 直接复用 |
| 不动 | `backend/app/services/step1_rates/activator_mappers.py:148-191` | `to_freight_rate_from_ngb` 已用通用 `_lookup_carrier` / `_resolve_port`；NVO 走通；R-N05 风险已识别（不写 BAF/LSS/container_45） |
| 不动 | `backend/app/services/rate_batch_service.py:64-118` | `create_draft_batch_from_upload` 走 `parse_excel_file` → `registry.resolve(path)` → `NvoFakAdapter.detect()` 命中 |
| 不动 | `backend/app/services/step1_rates/registry.py:18-30` | priority 数值越小越先；NVO 设 priority=5（最先匹配，因文件名特征最强） |

---

## 3. 关键设计决策（开发大师必须按此落，不要改）

### 3.1 record_kind 复用 `"ocean_ngb_fcl"`

**决策**：每条 NVO record 的 `record_kind = "ocean_ngb_fcl"`，不新增 kind。

**理由**：
- `activator.py` dispatch 表只认 4 个 kind（`air_weekly` / `air_surcharge` / `fcl` / `ocean_ngb_fcl`）；新增 kind 必须改 activator + `_plan_imported_detail`（违反红线 3）
- `to_freight_rate_from_ngb`（`activator_mappers.py:148-191`）的行为正符合 NVO：carrier 走 `_lookup_carrier(name="NVO_FAK")`，origin/dest 走 `_resolve_port`（NVO 的 origin 大多是 5 字符 LOCODE，5 字符精确匹配走第一击；dest 是 `"Long Beach"` 风格英文名，走第二击 ilike）
- `to_freight_rate_from_ocean` 要求 record 中已预解析 `origin_port_id` / `destination_port_id`（与 ocean.py 配套），不适用 — NVO adapter 同 KMTC 一样不接 db

**副作用**：metadata 中 NVO records 与 NGB / KMTC 共用 `ocean_ngb_fcl` 计数。前端按 `metadata.adapter_key="nvo_fak"` 过滤即可。

### 3.2 origin / destination 解析策略（与 KMTC 不同）

**核心差异**：KMTC origin 固定 `"Shanghai"`，NVO 每行 origin 不同（且**逗号分隔多 origin**：`"KRPUS,KRKAN"` 一行展开成 2 条 record）。

**Origin 处理**：
- 字符串 `_split_origins(s)` → 按 `,` 拆分 → strip → 过滤空串
- 每个 origin 单独建 1 条 record；除 `origin_port_name` 不同外其他字段（dest/rate/...）完全克隆
- 5 字符大写字母（如 `"KRPUS"`、`"INHZA"`）直接作为 `origin_port_name`，由 activator `_resolve_port` 走 LOCODE 精确匹配
- 对于"地理区域文本"（如 `"Cape Town / Durban / Coega"`、`"Mombasa"`、`"Kenya"`、`"Maputo / Beira"`、`"Mozambique"`、`"Namibia"`、`"Walvis Bay"`，见 TPE Africa 段）：取 `/` 左半的第一个港名作为 origin（参考 KMTC `_clean_and_resolve_port`）；如果 alias 命中 → LOCODE，否则保留清洗后纯英文 → activator ilike 兜底
- 对于"内陆英文名"（如 `"Memphis, TN"`、`"Saint Louis, MO"`，见 WPE IPI Add-Ons 段）：去 `, [A-Z]{2}$` 后查 alias → LOCODE，否则保留纯英文

**Destination 处理**（沿用 KMTC `_clean_and_resolve_port` 模式，**adapter 不接 db**）：
- 去 `, [A-Z]{2}$` 后缀（"Norfolk, VA" → "Norfolk"）
- 去括号 `(...)`
- alias 命中 → LOCODE
- alias 未命中 → 保留清洗后纯英文 → activator `_resolve_port` ilike 兜底
- 多港描述（"Los Angeles, Long Beach"、"Los Angeles, Oakland, Tacoma, Vancouver"）：**不展开成多 record**（与 origin 不同），取 `/` 或 `,` 的第一段作为代表港；warnings 收一条 `"row N: multi-port destination '<原文>' simplified to '<第一港>'"` 供人工核对（业务侧理解：客户在多港任一卸都用同一价，dest 只能选一个代表港落库）

### 3.3 detect 三策略 + priority

**优先级**：`priority=5`（最先 detect — NVO 文件名特征最强 "NVO" / "FAK" 不会误命中其他类型）

**detect 策略**（`NvoFakAdapter.detect(path, file_type_hint)` 按顺序，命中即 True）：

1. **file_type_hint**：`if file_type_hint == self.file_type: return True`（注：此 hint 也会被 OceanAdapter / OceanNgbAdapter / KmtcAdapter 命中。NVO priority=5 排第一，registry 升序遍历命中即返回，不会被后面 adapter 抢走）
2. **文件名关键字**（大小写不敏感）：`"nvo" in path.name.lower()` 或 `"fak" in path.name.lower()`
3. **sheet 名关键字**（兜底）：用 `openpyxl.load_workbook(path, read_only=True, data_only=True).sheetnames`，看是否含 `"TPE"` 或 `"WPE"` 或 `"Hawaii"`（任一命中即识别）；命中后 `wb.close()` 返回 True

**风险隔离**：策略 3 不深入读单元格（避免 KMTC 任务单 R-K12 的 AI fallback 隐患）。如样本文件名异常，用户上传时带 parser_hint 兜底。

### 3.4 RAD 列处理

**决策**：RAD 数值**不入库**，仅写入 `extras.rad_raw`。

**理由**：
- RAD = Reefer Add-On 或 Rail Add-On（语义不明确，老 parser 也未入库 — 见 `rate_parser.py:589-613` `parsed_rows.append` 字典中无 RAD 字段）
- `Step1RateRow` 没有对应字段；`FreightRate` 表也没有
- 大量空字符串 `''`（TPE 12/52 行、WPE 113/168 行 RAD 是 `''`），数值列偶尔为 ''，**adapter 必须把 `''` 当 `None`**（_safe_decimal 已正确处理）

### 3.5 5 种容器规格映射

| Excel 列名 | record 字段 | 说明 |
|---|---|---|
| `20ft` / `20'` | `container_20gp` | TPE/WPE col=6 ; Hawaii col=4 |
| `40ft` / `40'` | `container_40gp` | TPE/WPE col=7 ; Hawaii col=5 |
| `HC` / `40H` | `container_40hq` | TPE/WPE col=8 ; Hawaii col=6 |
| `45ft` / `45'` | `container_45` | TPE/WPE col=9 ; Hawaii col=7 |
| `RAD` | `extras.rad_raw`（不入库） | TPE/WPE col=10 ; Hawaii 无 RAD |

**注意 Hawaii 数值带 `$` 符号**（"$4,160"）— `_safe_decimal` 必须扩展处理 `$` 前缀和 `,` 千分位。当前 `app.services.rate_parser._safe_decimal` 只处理 `,`，**adapter 内自定义 `_nvo_safe_decimal`** 在调用 `_safe_decimal` 前 strip 掉 `$`（**不要修 `app.services.rate_parser._safe_decimal`**，会影响 KMTC/NGB）。

### 3.6 Arbitrary sheet 不解析

**决策**：跳过 `Arbitrary` sheet（与老 parser 行为一致，见 `/tmp/old_parser/rate_parser.py:496` `s.lower() not in ("arbitrary",)`）。

**理由**：
- `Arbitrary` 实际是 origin (内陆点) → port (沿海港) 的"内陆中转杂费表"，列含 D2/D4/D5/D7/RD5（按天计费），**不是干线 ocean FAK 运价**
- `FreightRate` 表 schema 没有"中转杂费"概念
- 业务侧未要求；本闭环不做

**操作**：`for sname in wb.sheetnames: if sname.lower() == "arbitrary": warnings.append(f"sheet '{sname}' skipped (inland arbitrary fees, not freight rate)"); continue`

### 3.7 多区段表头识别（核心难点 — 与 KMTC 最大差异）

**问题**：
- TPE 含 4 区段：R5(USA) / R127(Canada) / R146(FAK Africa, **列布局不同！** col6 是 `"20'"` 不是 `"20ft"`，col10 是 `"RAD"` 但 col8 是 `"40'H"` 而非 `"HC"`)
- WPE 含 3 区段：R5(USA) / R107(Canada) / R124(IPI Add-Ons, **列布局完全不同**：col1=Location, col2=Via, col3=Rate20, col4=Rate40, col5=Rate40H, col6=Rate45H, **无 origin / dest / coast / service**)
- 老 parser 用 `pd.read_excel(header=N)` 一次性读，**完全无法处理**，会把后续 'Origin' 行 / region label 当数据行读，列号错位

**决策**：实现 `_iter_sections(ws)` 主循环：
1. 在 `range(1, ws.max_row+1)` 中扫所有"段头候选行"
2. 段头判定：A 列是字符串 `"Origin"`（精确大小写无关比较 .strip().lower() == "origin"）**或** A 列含 `"Location"` 且 B 列含 `"Via"`（IPI 段）
3. 每段 `(header_row, layout, section_label)`：
   - `header_row`：段头行号
   - `layout`：通过 `_locate_columns_at_header_row(ws, header_row)` 动态生成（见下）
   - `section_label`：上一行 A 列文本（如 `"USA / Inclusive of OBS"` / `"Canada / Inclusive of OBS"` / `"IPI / RIPI Add-Ons ..."` / `"FAK - Africa to USA / Canada"`）
4. 段尾：下一段头行号 - 1 或 sheet 末
5. **layout 字典**：`{origin, pod, dest, coast, service, c20, c40, hc, c45, rad}`，每个值为 1-based 列号 或 None
6. 主段（USA / Canada）走 `_build_records_from_row` 标准路径
7. IPI 段走 `_build_ipi_record_from_row`：A 列(Location) → destination_port_name；B 列(Via) → extras.via；C/D/E/F → 20/40/HC/45；origin 留 None（IPI 是从沿海港"加价"，没有起运港概念，**这种行 origin_port_name = None**，由 activator `_resolve_port(None)` 返回 None → 整行被 ActivationError → 软失败 skip — **可接受**，因 IPI 数据不能直接入 FreightRate；记入 metadata.notes 即可。**不要把 IPI 段的 record 写入 records 列表**，仅 metadata.ipi_addon_count 计数）
8. Africa 段（TPE R145+）：层级特殊，`"Origin"` 不在 A 列，A 列是 `"FAK - Africa to USA / Canada"`，下一行才是表头但用 `"Destination"` `"Canal"` `"Coast"` `"Via"` 等。**由于 origin 是 "Maputo / Beira, Mozambique" 这种地理区域文本**（无 LOCODE），落库后大概率 ilike 不命中 → 软失败 skip。decided：Africa 段同样写 metadata.notes，**不写 records**。判定：当 section_label 含 `"Africa"` 字样 → 段类型为 africa → 仅 metadata 记录段内行数，不出 record

**总产出**：本闭环只把 USA + Canada 两类主段 + Hawaii 入库；IPI / Africa 段计数到 metadata，不入 records。

### 3.8 carrier_name 固定 "NVO_FAK"

每条 record `carrier_name = "NVO_FAK"`（字符串字面量）。`_lookup_carrier` 命中规则：精确 `Carrier.code == "NVO_FAK"`（seed 已有，line 205）。

### 3.9 effective_from / effective_to 抽取

- 每个 sheet 独立调用 `_extract_effective_dates(ws)` 抽取（沿用老 parser `_extract_effective_dates` 思路：前 5 行 A 列文本中找 `"20\d{2}"` 提取年份 + `"[Ee]ffective\s+(?:from\s+)?(\d{1,2})[/\-](\d{1,2})\s+to\s+(\d{1,2})[/\-](\d{1,2})"` 提取月日）
- batch 级 `effective_from = min(各 sheet effective_from 非空)`；`effective_to = max(各 sheet effective_to 非空)`
- 每个 sheet 解出的日期同时塞入 `metadata.sheets[i].effective_from / effective_to`
- 文件名兜底：如果前 5 行没找到年份，从 path.name 提取 `"20\d{2}"`（NVO 文件名 `NVO FAK 2026 (Mar 20 to Mar 31).xlsx` 含 `2026`）

---

## 4. 字段映射表

### 4.1 TPE/WPE 主段（USA / Canada）列号 → record 字段

| Col | 表头 (R5) | 业务字段 | record 字段 | 备注 |
|---|---|---|---|---|
| 1 | Origin | 起运港 LOCODE / 多 LOCODE | `origin_port_name` | "KRPUS,KRKAN" → 拆 2 record |
| 2 | Port of Discharge | 卸货港文本 | `extras.pod_raw` | 不直接落库 |
| 3 | Destination | 目的地文本 | `destination_port_name`（清洗后） | 优先用此列；为空时回退 col 2 |
| 4 | Coast | 区域代码 | `extras.coast` | "USWC(PS)"/"USEC"/"CAEC" 等 |
| 5 | Service | 季节代码 | `service_code` | "WIN"/"SUM" 或 None |
| 6 | 20ft | 20GP 价 | `container_20gp` | _safe_decimal；'' → None |
| 7 | 40ft | 40GP 价 | `container_40gp` | 同上 |
| 8 | HC | 40HQ 价 | `container_40hq` | 同上 |
| 9 | 45ft | 45ft 价 | `container_45` | 同上 |
| 10 | RAD | Reefer/Rail Add-On | `extras.rad_raw` | 不入库（§3.4） |

### 4.2 Hawaii sheet 列号映射（双行表头 R5+R6）

R5 主表头：`['COUNTRY', 'ORIGIN', 'Destination', 'Inclusive of DDC & OBS', None, None, None, None]`
R6 子表头：`[None, None, None, "20'", "40'", 'HC', "45'", None]`

| Col | 业务字段 | record 字段 |
|---|---|---|
| 1 | COUNTRY | `extras.country` |
| 2 | ORIGIN（英文名 "PUSAN" / "SHANGHAI"） | `origin_port_name`（清洗后） |
| 3 | Destination（"Honolulu" / "CY"） | `destination_port_name`（清洗后） |
| 4 | 20' | `container_20gp`（去 `$`、`,` 后 _safe_decimal） |
| 5 | 40' | `container_40gp` |
| 6 | HC | `container_40hq` |
| 7 | 45' | `container_45` |

**注意**：Hawaii row 中 col 1（COUNTRY）经常是 None（仅每段第一行有），不影响 origin 解析。col 3 destination 含 `"CY"`（Container Yard，非具体港 — 同样按 nan 处理：Honolulu 范围内部，destination=USHNL；记入 warning）。

### 4.3 PORT_ALIAS_MAP 缺口（必须在 `backend/app/services/rate_parser.py` line 19-131 内追加）

基于 §0 实测的全量 origin/destination 字面对照 PORT_ALIAS_MAP，确认下列 alias 缺失（按字母序）：

```python
# 在 line 131 } 闭合前插入（建议按地理分组就近插入）
"cebu": "PHCEB", "宿务": "PHCEB",                      # Hawaii origin
"dalian": "CNDLC", "大连": "CNDLC",                    # Hawaii origin（seed 已有 CNDLC，仅缺 alias）
"huangpu": "CNHUA", "黄埔": "CNHUA",                   # Hawaii origin（seed 缺 CNHUA — §4.4 补）
"leam chabang": "THLCH", "林查班 (拼写变体)": "THLCH",  # Hawaii origin "LEAM CHABANG"（拼写变体 of LAEM CHABANG）
"manila": "PHMNL", "manila (north)": "PHMNL", "马尼拉": "PHMNL",   # Hawaii origin
"pusan": "KRPUS",                                       # Hawaii origin（"PUSAN" 全大写 — alias 已有 "busan"，但 lookup 用 .lower() 后 "pusan" 未命中 "busan"。需补独立 key）
"taoyuan": "TWTPE",                                     # Hawaii origin（桃园机场港 ≈ 台北市辐射港）
"xingang": "CNXIN", "新港": "CNXIN",                   # Hawaii origin（天津新港，seed 缺 CNXIN — §4.4 补）
"laredo": "USLDO",                                      # TPE dest "Laredo, TX"（seed 缺 USLDO — §4.4 补）
"omaha": "USOMA",                                       # WPE IPI inland origin "Omaha, NE"（seed 缺 USOMA — §4.4 补）
"saint louis": "USSTL",                                 # WPE IPI "Saint Louis, MO"（seed 已有 USSTL；alias 已有 "st louis"/"st. louis" 未含 "saint louis" 全拼）
"tampa": "USTPA",                                       # WPE IPI "Tampa, FL"（seed 缺 USTPA — §4.4 补）
"crandall": "USCRA",                                    # WPE IPI（小镇，seed 缺 — §4.4 补；如客户后续不复现可从 seed 移除）
"greer": "USGRR",                                       # WPE IPI（小镇，seed 缺 — §4.4 补）
```

**总计：14 条 alias 必须新增**。

### 4.4 seed_data.py ports 缺口（必须在 `scripts/seed_data.py:16-183` PORTS 列表追加）

| LOCODE | name_en | name_cn | country | region | 来源 |
|---|---|---|---|---|---|
| `PHCEB` | Cebu | 宿务 | Philippines | Southeast Asia | Hawaii origin |
| `PHMNL` | Manila | 马尼拉 | Philippines | Southeast Asia | Hawaii origin "MANILA (NORTH)" |
| `CNHUA` | Huangpu | 黄埔 | China | East Asia | Hawaii origin "HUANGPU" |
| `CNXIN` | Xingang | 新港 | China | East Asia | Hawaii origin "XINGANG"（天津新港） |
| `USLDO` | Laredo | 拉雷多 | USA | North America | TPE dest "Laredo, TX" |
| `USOMA` | Omaha | 奥马哈 | USA | North America | WPE IPI "Omaha, NE" |
| `USTPA` | Tampa | 坦帕 | USA | North America | WPE IPI "Tampa, FL" |
| `USCRA` | Crandall | 克兰德尔 | USA | North America | WPE IPI "Crandall" |
| `USGRR` | Greer | 格里尔 | USA | North America | WPE IPI "Greer" |

**总计：9 条 ports 必须新增**（含 PORT_ALIAS_MAP §4.3 中映射但 seed 已有的 5 个 — Cebu、Manila、Huangpu、Xingang 4 个海港、Laredo、Omaha、Tampa、Crandall、Greer 5 个内陆/小镇）。

**操作**：在 `seed_data.py:91`（IDOKI 行）后追加 PHCEB / PHMNL / CNHUA / CNXIN，在 line 172（USSLC 行）后追加 USLDO / USOMA / USTPA / USCRA / USGRR。用户在 Windows 上 `D:\Anaconda3\envs\py310\python.exe scripts/seed_data.py` 重跑。

**注意**：上面 INHZA / INCCU / INCOK / INIXE / INPAV / PKBQM / LKCMB / BDCGP（WPE 主段 LOCODE origin）— 共 8 个 5 字符 LOCODE 在 seed 中不存在，会导致 activator `_resolve_port` 走 5 字符精确匹配 → None → 软失败 skip。**业务决策（下个闭环再补）**：先记入 `metadata.unseeded_origin_locodes` 列表 + warning，本闭环不补（这些是印度次大陆和孟加拉国/斯里兰卡的小港，不是 Demo 范围客户需求）。**测试验收 V-N09 必须验证这点不阻塞激活、warnings 显式列出该列表**。

### 4.5 Step1RateRow 字段映射（USA/Canada 主段一行）

| Step1RateRow 字段 | 来源 | 类型 |
|---|---|---|
| `record_kind` | 字面量 `"ocean_ngb_fcl"` | str |
| `carrier_name` | 字面量 `"NVO_FAK"` | str |
| `origin_port_name` | `_clean_origin_locode(part)` for each in `_split_origins(row[0])` | str |
| `origin_port_id` | None | None |
| `destination_port_name` | `_clean_destination(row[2] 或 row[1])` | str |
| `destination_port_id` | None | None |
| `service_code` | row[4]（"WIN" / "SUM" / None） | str \| None |
| `container_20gp` | `_nvo_safe_decimal(row[5])` | Decimal\|None |
| `container_40gp` | `_nvo_safe_decimal(row[6])` | Decimal\|None |
| `container_40hq` | `_nvo_safe_decimal(row[7])` | Decimal\|None |
| `container_45` | `_nvo_safe_decimal(row[8])` | Decimal\|None |
| `currency` | 字面量 `"USD"`（NVO 全表 USD） | str |
| `valid_from` | 当前 sheet 的 effective_from | date\|None |
| `valid_to` | 当前 sheet 的 effective_to | date\|None |
| `transit_days` | None（NVO 表无此列） | None |
| `is_direct` | True（NVO 默认直达） | bool |
| `remarks` | None | None |
| `source_type` | 字面量 `"excel"` | str |
| `source_file` | path.name | str |
| `extras` | dict（见 §4.6） | dict |

### 4.6 extras 字段定义

```python
extras = {
    "sheet_name": "TPE",                  # 'TPE' / 'WPE' / 'Hawaii'
    "row_index": 6,                        # 1-based
    "section_label": "USA / Inclusive of OBS",  # 上一行 region label
    "section_kind": "main_us",            # 'main_us' / 'main_ca' / 'hawaii'（IPI/Africa 不出 record）
    "origin_raw": "KRPUS,KRKAN",          # 拆分前原文
    "pod_raw": "Los Angeles, Long Beach ", # row[1]
    "destination_raw": "Los Angeles, Long Beach ", # row[2]
    "coast": "USWC(PS)",                  # row[3]
    "rad_raw": "2400",                    # row[9] str 原文（数值或 ''）
    "container_20gp_raw": "1920",         # 数值原文
    "container_40gp_raw": "2400",
    "container_40hq_raw": "2400",
    "container_45_raw": "2650",
}
```

### 4.7 metadata（ParsedRateBatch.metadata）

```python
metadata = {
    "file_name": path.name,
    "source_type": "excel",
    "carrier_code": "NVO_FAK",
    "parser_version": "nvo_fak_v1",
    "adapter_key": "nvo_fak",
    "base_ports": ["SGSIN","KRPUS","VNSGN","VNCMP","HKHKG","TWKHH","THLCH",
                   "CNNGB","CNTAO","CNSHA","CNXMN","CNYTN","TWTPE"],  # 从 R3 'All Base Ports' 解析
    "sheets": [
        {
            "sheet_name": "TPE",
            "total_rows": <int>,           # 该 sheet 出 record 数（含 origin 拆分后）
            "ipi_addon_count": <int>,      # 不出 record 但记数（IPI 段）
            "africa_count": <int>,
            "effective_from": <date>,
            "effective_to": <date>,
        },
        {"sheet_name": "WPE", ...},
        {"sheet_name": "Hawaii", ...},
        {"sheet_name": "Arbitrary", "skipped": true,
         "skip_reason": "inland arbitrary fees, not freight rate"},
    ],
    "record_kind_distribution": {"ocean_ngb_fcl": <total>},
    "unseeded_origin_locodes": ["INHZA","INCCU","INCOK","INIXE","INPAV","PKBQM","LKCMB","BDCGP"],  # 提示监工/seed 维护
    "section_notes": [
        # 每个 IPI / Africa 段记一条文本备份，不入 records
        {"sheet": "WPE", "section_label": "IPI / RIPI Add-Ons ...", "row_count": 56},
        {"sheet": "TPE", "section_label": "FAK - Africa to USA / Canada", "row_count": ~5},
    ],
}
```

---

## 5. NvoFakAdapter 接口契约

```python
# backend/app/services/step1_rates/adapters/nvo_fak.py

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.services.rate_parser import PORT_ALIAS_MAP, _safe_decimal
from app.services.step1_rates.entities import ParsedRateBatch, ParsedRateRecord, Step1FileType


@dataclass(frozen=True)
class _Section:
    sheet_name: str
    header_row: int
    end_row: int                      # 包含
    layout: dict[str, int]            # 1-based col index, e.g. {origin:1, dest:3, c20:6, ...}
    section_label: str | None
    section_kind: str                 # 'main_us' / 'main_ca' / 'ipi' / 'africa'


def _clean_destination(name_raw: str | None) -> str | None:
    """destination：去 ', ST'、去括号、查 alias → LOCODE 或 纯英文。"""
    ...


def _clean_origin_locode(name_raw: str | None) -> str | None:
    """origin：5 字符全大写 → 直接返回；否则同 _clean_destination。"""
    ...


def _split_origins(s: str) -> list[str]:
    """'KRPUS,KRKAN' → ['KRPUS','KRKAN']。"""
    ...


def _nvo_safe_decimal(value: Any) -> Decimal | None:
    """扩展 _safe_decimal — 处理 '$4,160' 风格 + '' → None。"""
    ...


class NvoFakAdapter:
    """Step1 NVO FAK parser (4 sheets, multi-section headers, USD)."""

    key: str = "nvo_fak"
    file_type: Step1FileType = Step1FileType.ocean   # 复用 ocean 枚举（§0.2）
    priority: int = 5                                  # 最先 detect

    _CARRIER_NAME: str = "NVO_FAK"
    _CURRENCY: str = "USD"
    _PARSER_VERSION: str = "nvo_fak_v1"

    _SHEET_TPE: str = "TPE"
    _SHEET_WPE: str = "WPE"
    _SHEET_HAWAII: str = "Hawaii"
    _SHEET_ARBITRARY: str = "Arbitrary"

    _DETECT_NAME_KEYWORDS_LOWER: tuple[str, ...] = ("nvo", "fak")
    _DETECT_SHEET_KEYWORDS: tuple[str, ...] = ("TPE", "WPE", "Hawaii")

    _EFFECTIVE_RE = re.compile(
        r"[Ee]ffective\s+(?:from\s+)?(\d{1,2})[/\-](\d{1,2})\s+to\s+(\d{1,2})[/\-](\d{1,2})"
    )
    _YEAR_RE = re.compile(r"20\d{2}")
    _BASE_PORTS_RE = re.compile(r"All Base Ports[:\s]+(.*)")
    _STATE_SUFFIX_RE = re.compile(r",\s*[A-Z]{2}\s*$")

    # ---------- detect / parse ----------
    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool: ...
    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch: ...

    # ---------- sheet 路由 ----------
    def _parse_main_sheet(self, ws, sheet_name: str, eff_from, eff_to) -> tuple[list[ParsedRateRecord], list[str], dict]: ...
    def _parse_hawaii_sheet(self, ws, eff_from, eff_to) -> tuple[list[ParsedRateRecord], list[str], dict]: ...

    # ---------- 段头识别 ----------
    def _iter_sections(self, ws, sheet_name: str) -> Iterable[_Section]: ...
    def _is_section_header(self, ws, row_index: int) -> bool: ...
    def _locate_columns_at_header_row(self, ws, header_row: int) -> dict[str, int] | None: ...
    def _classify_section(self, label: str | None, layout: dict[str, int]) -> str: ...

    # ---------- 行处理 ----------
    def _build_records_from_main_row(
        self, row, row_index, layout, sheet_name, section_kind, section_label, eff_from, eff_to, source_file
    ) -> list[ParsedRateRecord]: ...
    def _build_hawaii_record(self, row, row_index, eff_from, eff_to, source_file) -> ParsedRateRecord | None: ...
    def _should_skip_main(self, row, layout) -> bool: ...
    def _should_break_hawaii(self, row) -> bool: ...

    # ---------- helpers ----------
    def _extract_effective_dates(self, ws) -> tuple[date | None, date | None]: ...
    def _extract_base_ports(self, ws) -> list[str]: ...
    def _normalize_text(self, value: Any) -> str | None: ...
    def _is_numeric(self, value: Any) -> bool: ...
    def _dedupe_warnings(self, warnings: Iterable[str]) -> list[str]: ...
    def _empty_batch(self, path: Path, warnings: list[str]) -> ParsedRateBatch: ...
```

**关键私有方法行为约定**：

| 方法 | 入参 | 出参 | 备注 |
|---|---|---|---|
| `_iter_sections` | ws, sheet_name | iterable[_Section] | 扫所有段头（A 列 == "Origin" 不分大小写 / IPI 特征行）；末段 end_row 取 ws.max_row |
| `_is_section_header` | ws, ri | bool | A 列 strip().lower() == "origin" → True；或 A 列含 "Location" 且 B 列含 "Via" → True |
| `_locate_columns_at_header_row` | ws, header_row | dict 或 None | 在该行扫前 12 列；按表头文本（含 "origin"/"port of discharge"/"destination"/"coast"/"service"/"20"/"40"/"hc"/"45"/"rad"/"location"/"via"/"rate"）建 layout |
| `_classify_section` | label, layout | str | label 含 "USA" → main_us；含 "Canada" → main_ca；含 "IPI" / "Add-On" 或 layout 不含 origin → ipi；含 "Africa" → africa |
| `_should_skip_main` | row, layout | bool | A 列空 + 整行空 → skip；A 列文本含 "remark"/"note"/"effective"/"t&c"/"for "/"rate"/"surcharge" 等 → skip；layout.c20 列非数字 → skip |
| `_should_break_hawaii` | row | bool | A 列含 "REMARK"/"COMMODITY"/"APPLICABLE"/"Rates are" → True（停止扫整个 Hawaii sheet） |
| `_extract_effective_dates` | ws | (from, to) | 前 5 行扫；正则 `_EFFECTIVE_RE`；年份 `_YEAR_RE`；都失败 → (None, None) |
| `_extract_base_ports` | ws | list[str] | 前 5 行扫 `_BASE_PORTS_RE`，逗号拆分清 |
| `_nvo_safe_decimal` | value | Decimal\|None | str → strip()；去前缀 `$`，去 `,`；空串 → None；调 `app.services.rate_parser._safe_decimal` |

**parse() 主方法约定**：

```
def parse(self, path, db=None):
    1. wb = load_workbook(path, data_only=True)
    2. all_records, all_warnings = [], []
       sheets_summary = []
       for sname in wb.sheetnames:
         ws = wb[sname]
         if sname.lower() == 'arbitrary':
             sheets_summary.append({'sheet_name': sname, 'skipped': True,
                                    'skip_reason': 'inland arbitrary fees, not freight rate'})
             continue
         if sname == 'Hawaii':
             eff_from, eff_to = _extract_effective_dates(ws)
             recs, warns, summary = _parse_hawaii_sheet(ws, eff_from, eff_to)
         elif sname in ('TPE', 'WPE'):
             eff_from, eff_to = _extract_effective_dates(ws)
             recs, warns, summary = _parse_main_sheet(ws, sname, eff_from, eff_to)
         else:
             all_warnings.append(f"unexpected sheet '{sname}' skipped")
             continue
         all_records.extend(recs); all_warnings.extend(warns)
         sheets_summary.append(summary)
    3. base_ports = _extract_base_ports(wb['TPE']) if 'TPE' in wb.sheetnames else []
    4. effective_from = min((s['effective_from'] for s in sheets_summary if s.get('effective_from')), default=None)
       effective_to = max((s['effective_to'] for s in sheets_summary if s.get('effective_to')), default=None)
    5. metadata = {...}（见 §4.7）
    6. return ParsedRateBatch(file_type=Step1FileType.ocean, source_file=path.name,
                              effective_from=effective_from, effective_to=effective_to,
                              records=all_records, warnings=_dedupe_warnings(all_warnings),
                              adapter_key="nvo_fak", metadata=metadata)
```

---

## 6. 风险 / 坑 / 边界（开发大师必须知道的"前人踩过的雷"）

| ID | 风险描述 | 兜底策略 |
|---|---|---|
| **R-N01** | **多区段表头错位** — 老 parser 用 `pd.read_excel(header=N)` 一次性读，无法处理 TPE/WPE 的 R107 / R127 / R146 第二/三/四段表头。会把 'Origin' 行当数据 / 列号错位 | 必须用 openpyxl + `_iter_sections` 段头扫描；每段独立 `layout`。**这是与老 parser 最大的实现差异**，开发大师千万不要回退到 read_excel 模式 |
| **R-N02** | **'' 空字符串 vs None** — TPE/WPE col 9 (RAD)、col 8 (HC)、col 4 (Service) 大量出现 `''`（不是 None）。如 R9 col 9 是 `''`、R11 col 4 是 None | `_nvo_safe_decimal` 必须把 `''` 当 `None`；`_normalize_text` 同样把 `''` strip 后 → None；不要把 `''` 当数据停止信号 |
| **R-N03** | **Hawaii 数值带 `$` 和 `,`** — 全 32 行都是 `'$4,160'` 风格，不是裸数值 | `_nvo_safe_decimal` 在调 `_safe_decimal` 前必须 `str.lstrip('$').replace(',','')`；老 parser 没处理这点（实际 Hawaii 多数行会被 `_safe_decimal` 拒掉 → 0 入库的潜在 bug） |
| **R-N04** | **Origin 多 LOCODE 拆分** — `"KRPUS,KRKAN"` / `"PKBQM,PKKHI"` 一行展开成 N 条 record，rate 完全相同 | `_split_origins` 必须 strict 按 `,` 拆分 + strip；warning 不需要（这是常态）。注意 dest 不要拆（dest "Los Angeles, Long Beach" 是单个多港描述，不是真多目的地） |
| **R-N05** | **`to_freight_rate_from_ngb` 不写 container_45 / BAF/LSS** — 见 `activator_mappers.py:173-191`，构造 FreightRate 时 `container_45=None` 写死，BAF/LSS 字段不写 | **本闭环不修 mapper**（红线 3）。container_45 / RAD 数值会丢失到 freight_rates 表，但保留在 record.extras（前端可读 batch detail preview_rows）。如业务要求 NVO 的 45ft 入库，下个闭环改 `to_freight_rate_from_ngb` 把 `container_45=record.container_45` 改正（兼容 NGB/KMTC — 它们 container_45 本就是 None） |
| **R-N06** | **R3 "All Base Ports" 行不含数据** — 仅是声明"以下 USA 段对所有 base ports 均价相同"。老 parser 也没据此展开行 | adapter 把 base ports 列表抽到 `metadata.base_ports`；不要展开为 13 条 record。FAK 业务模型：base ports 集合中的任一 origin 都用同一价 — 但 Excel 里每段第一区段（USA/Canada/Africa）已显式列出 origin（KRPUS,KRKAN 等），不需要展开 |
| **R-N07** | **Service 列偶尔含 'WIN'/'SUM' 季节代码** — R11 col 4 是 'WIN'，但其他行为 None。WIN/SUM 的同一 origin/dest 行价格不同 | `service_code = row[4] strip 后` 直接落 record；同一 (origin, dest, service_code) 不同价正好用 service_code 区分。落库后 freight_rates 表 service_code 字段会写入 |
| **R-N08** | **destination 含 ", state"** — "Norfolk, VA" 不去后缀直接落 ilike 会命中错（'%Norfolk, VA%' 不会命中 Port.name_en='Norfolk'） | `_clean_destination` 必须先去 `, [A-Z]{2}$` 再查 alias / 落库；与 KMTC `_clean_and_resolve_port` 模式一致 |
| **R-N09** | **WPE LOCODE origins 有 8 个不在 seed**（INHZA / INCCU / INCOK / INIXE / INPAV / PKBQM / LKCMB / BDCGP） | adapter 不阻塞；activator 阶段走 LOCODE 精确匹配 None → 软失败 skip。warnings 列出该 8 条；**metadata.unseeded_origin_locodes 显式记录**；本闭环不补 seed（不在 Demo 客户范围）。若用户要求，下个闭环按 §4.4 模式补 seed |
| **R-N10** | **多港 destination "Los Angeles, Oakland, Tacoma, Vancouver"**（TPE R57） | 取 `,` 第一段 → "Los Angeles" → ilike 命中 USLAX；warnings 收 `"row N: multi-port destination simplified to first port"` 提醒人工核对（业务侧用同一价是合理的，但 dest 唯一化后查询时需要客户走"任一港都查 USLAX"约定） |
| **R-N11** | **detect 与 ocean 冲突** — ocean.py:45 `"ocean" in normalized_name`；NVO 文件名 "NVO FAK 2026 ..." 不含 "ocean"，不冲突；但若用户改名为 "nvo ocean.xlsx" 可能被 ocean 抢先 | 设 `priority=5` 比 ocean=20 / kmtc=15 / ocean_ngb=30 都低；registry resolve 升序遍历，命中即返回 |
| **R-N12** | **Hawaii col 1 (COUNTRY) 经常 None** — 仅每段第一行有值（如 R7 'KOREA'），后续行 col 1 = None。如果误把 col 1 None 当 break 信号会少解 80% | `_should_break_hawaii` 仅检查 A 列文本含 "REMARK"/"COMMODITY"/"APPLICABLE"/"Rates are"/"For "；不要把 col 1 None 当 break |
| **R-N13** | **TPE/WPE 末段 IPI / Africa 段虽是 'Origin' 行起头但实际不是干线 origin** — IPI 段 col 1 是 "Memphis, TN"（destination），Africa 段 col 1 是 "Maputo / Beira, Mozambique"（地理区域） | `_classify_section` + section_kind 区分；`ipi` / `africa` 段**不出 record**，仅记 `metadata.section_notes` + `metadata.sheets[i].ipi_addon_count / africa_count` |
| **R-N14** | **WPE R124 IPI 段表头列布局完全不同**（`Location/Via/Rate20/Rate40/Rate40H/Rate45H` 6 列） | `_locate_columns_at_header_row` 在该行返回 layout 时不会有 'origin' 键 → `_classify_section` 据此判 ipi → 路由到不出 record 分支；**不要尝试解 IPI 段** |
| **R-N15** | **fixture Excel 路径含中文 + 空格** — `资料/2026.03.31/NVO FAK 2026 (Mar 20 to Mar 31).xlsx` | pytest fixture 用 `pathlib.Path(__file__).parents[5] / "资料" / "2026.03.31" / "NVO FAK 2026 (Mar 20 to Mar 31).xlsx"`，断言 `path.exists()` 提前 fail |
| **R-N16** | **rate_batch_service AI fallback 兜底** — 若 detect 没注册，registry.resolve 抛 LookupError，触发 `_try_ai_fallback_on_excel`（rate_batch_service.py:96-109），用 AI 解析 NVO（耗时/可能错） | adapter 必须在 `service.py:13-21` 注册；测试 V-N01 验证 detect 命中（不走 fallback） |

---

## 7. 验收点（V-N01..V-N15，交给测试大师）

每个验收点必须可独立观察、给出明确判定（pass/fail），不能写"运行正常"。

| ID | 验收点描述 | 期望观察值 |
|---|---|---|
| **V-N01** | **detect 命中**：把 `NVO FAK 2026 (Mar 20 to Mar 31).xlsx` 路径喂 `DEFAULT_RATE_ADAPTER_REGISTRY.resolve(path)`，应返回 `NvoFakAdapter` 实例 | `isinstance(adapter, NvoFakAdapter) == True` |
| **V-N02** | **4 sheet 正确路由**：解析后 `metadata.sheets` 列表长度 == 4；`Arbitrary` 项 `skipped == True`；`TPE`/`WPE`/`Hawaii` 项均无 `skipped` 字段；warnings 含 `"sheet 'Arbitrary' skipped (inland arbitrary fees, not freight rate)"` | 4 sheet 全部出现且分类正确 |
| **V-N03** | **TPE 多区段识别**：解析 TPE 后 records 中至少包含 `extras.section_kind in {'main_us','main_ca'}`；`metadata.sheets[TPE].ipi_addon_count > 0`（IPI 段计数）和 `africa_count > 0`（Africa 段计数）；records 中**不存在** `extras.row_index in {127, 146}`（这两行是段头不是数据） | 段类型分布正确，段头未误入 records |
| **V-N04** | **Origin 多港拆分**（TPE R6 "KRPUS,KRKAN"）：records 中 `extras.row_index == 6` 应有 2 条；分别 `origin_port_name == "KRPUS"` 和 `origin_port_name == "KRKAN"`；其他字段（destination_port_name / container_20gp / container_40gp / container_40hq / container_45 / coast）完全相同 | 2 条 record，origin 拆开，其余克隆 |
| **V-N05** | **5 容器规格抽取**（TPE R6）：找 `extras.row_index == 6` & `origin_port_name == "KRPUS"` record：`container_20gp == Decimal("1920")`、`container_40gp == Decimal("2400")`、`container_40hq == Decimal("2400")`、`container_45 == Decimal("2650")`、`extras.rad_raw == "2400"` | 5 字段全命中 |
| **V-N06** | **Hawaii `$` 价格清洗**（Hawaii R7 PUSAN）：record `origin_port_name == "PUSAN"`（清洗 alias 后 LOCODE "KRPUS"）、`container_20gp == Decimal("4160")`、`container_40gp == Decimal("5200")`、`container_40hq == Decimal("5200")`、`container_45 == Decimal("6585")` | `$` `,` 已剥离正确 |
| **V-N07** | **空字符串 vs None**（TPE R9 col 10 `''` RAD）：record `extras.rad_raw == ""` 或 `extras.rad_raw is None`（二者均接受）；不抛 InvalidOperation | 不报错；rad_raw 落 ''/None 之一 |
| **V-N08** | **Service 列处理**（WPE R11 'WIN'）：record `service_code == "WIN"`；同 origin/dest 但无 service 的行 `service_code is None` | service_code 字段正确隔离 |
| **V-N09** | **未 seed origin 软失败**：解析后 `metadata.unseeded_origin_locodes` 列表至少含 `"INHZA"`；激活后 warnings 中含 `"port 'INHZA' not found"` 类似文本；**整批未 fail**，imported_rows 仍 ≥ 80（USA/Canada 主段绝大部分 origin 是 KRPUS/CNNGB/CNSHA 等已 seed） | unseeded_origin_locodes 非空；激活仍成功；imported_rows ≥ 80 |
| **V-N10** | **Effective 日期抽取**：TPE/WPE/Hawaii 三 sheet 各自 effective_from/to 抽取成功（TPE: 2026-3-20→3-31；WPE: 2026-3-20→3-31；Hawaii: 2026-3-1→3-31）；batch 级 effective_from = `date(2026,3,1)`、effective_to = `date(2026,3,31)` | 3 sheet 日期各自正确 + batch 范围正确 |
| **V-N11** | **records 总数**：解析全文件，`len(batch.records)` 应在 `[260, 320]` 区间（TPE 主段 ~52 行 × origin 拆分平均 1.3 = ~70；WPE 主段 ~120 行 × 平均 1.5 = ~180；Hawaii ~32 行；合计 ~280±20） | 260 ≤ len(records) ≤ 320 |
| **V-N12** | **destination_port_name 全是 LOCODE 或纯英文（无逗号州缩写、无斜杠多港）**：遍历 records，全部 `destination_port_name` 既不含 `,` 也不含 `/`，且不含中文；同时 origin 5 字符 LOCODE 行的 origin_port_name 严格 5 字符大写字母 | 100% 通过格式断言 |
| **V-N13** | **detect 优先级**：手动构造一个文件名为 `nvo_ocean.xlsx` 的副本，`registry.resolve` 仍返回 NvoFakAdapter（不是 OceanAdapter） | priority=5 < ocean=20 生效 |
| **V-N14** | **base_ports 抽取**：`metadata.base_ports` 列表长度 == 13；包含 `"SGSIN"`、`"KRPUS"`、`"CNSHA"`、`"TWTPE"` 等 | 13 个 base ports 全抽取 |
| **V-N15 (D 项 — 端到端 sqlite 激活链)** | **必须用 sqlite memory in-process** 跑 detect → parse → create_draft_batch_from_upload → activate_rate_batch(dry_run=False)；返回 `{"activation_status": "activated", "imported_rows": >= 240}`；DB 中 `freight_rates.batch_id == 该 batch_id` 行数 ≥ 240；`carriers.code='NVO_FAK'` 命中；任意 KRPUS origin 的 record 入库后 `origin_port.un_locode='KRPUS'` 命中 ✗ **不能因 mac 无 PG 跳过**：测试用 sqlite memory + 在 setUp 中用 `Base.metadata.create_all(engine)` 建表 + 跑 seed_data.PORTS / CARRIERS 子集（只 seed NVO 用得到的 ~30 个 ports + NVO_FAK carrier）。监工会跑此测试 | 全 4 个断言通过；测试在 mac 上能跑 |

---

## 8. 实施顺序（开发大师按此推进，每步可独立 commit）

| 步 | 动作 | 验收 |
|---|---|---|
| 1 | `seed_data.py` 加 §4.4 的 9 条 ports；`rate_parser.py` PORT_ALIAS_MAP 加 §4.3 的 14 条 alias；用户在 Windows 重跑 seed | DB ports 表新增 9 行；alias map import 不报错 |
| 2 | 新建 `nvo_fak.py` 骨架（class + 字段 + detect 文件名/sheet 名实现 + parse 返回空 batch + warning） | import 不报错；detect 单元测试 V-N01 通过 |
| 3 | 实现 `_extract_effective_dates` + `_extract_base_ports` + `_nvo_safe_decimal`；单元测试 V-N06/V-N10/V-N14 | 通过 |
| 4 | 实现 `_iter_sections` + `_is_section_header` + `_locate_columns_at_header_row` + `_classify_section` 多区段识别 + 单元测试 V-N03 | 通过 |
| 5 | 实现 `_parse_main_sheet` + `_build_records_from_main_row` + `_split_origins` + `_clean_origin_locode` + `_clean_destination`；单元测试 V-N04/V-N05/V-N07/V-N08/V-N12 | 通过 |
| 6 | 实现 `_parse_hawaii_sheet` + `_build_hawaii_record` + `_should_break_hawaii`；单元测试 V-N06 | 通过 |
| 7 | 实现 records 总数验收 V-N11 + 4 sheet 路由 V-N02 + warnings 去重 | 通过 |
| 8 | 在 `adapters/__init__.py` 导出 + `service.py` 注册；端到端 V-N15 sqlite 测试（含 setUp 建表 + seed 子集） | V-N01/V-N09/V-N13/V-N15 全通过 |
| 9 | 监工抽查：file:line 真实性、3 个红线无违反、9-15 个 warning 都有去重、前端 batch detail 能显示 NVO records 含 container_45 / rad_raw / coast / service_code | pass |

**预估总工时**：开发大师 10-14 人时（4 sheet + 多段表头复杂度高于 KMTC）；测试大师 4-6 人时；监工抽查 1 人时。

---

## 9. 自检清单（架构大师）

- [x] `/tmp/old_parser/rate_parser.py:486-629` 的 `parse_nvo_fak_excel` 已读完，列号映射、effective_dates、ORIGIN_CODE_MAP 已对齐
- [x] `/tmp/old_parser/rate_parser.py:458-483` `_extract_effective_dates` 已读完，正则已抄录到 §3.9
- [x] `backend/app/services/step1_rates/adapters/__init__.py:1-11` 真实存在，注册位 line 4 + line 6-11 `__all__`
- [x] `backend/app/services/step1_rates/adapters/kmtc.py:23-59` `_clean_and_resolve_port` 真实存在；NVO 沿用此模式
- [x] `backend/app/services/step1_rates/activator_mappers.py:148-191` `to_freight_rate_from_ngb` 真实存在；§6 R-N05 风险（不写 container_45 / BAF/LSS）已核实（line 173-191 构造时 container_45=None / 无 BAF/LSS 字段）
- [x] `backend/app/services/step1_rates/activator_mappers.py:194-223` `_lookup_carrier` 精确匹配 `Carrier.code` 优先真实存在（line 203）
- [x] `backend/app/services/step1_rates/activator_mappers.py:226-241` `_resolve_port` 弱版本（5 字符精确 / name_en ilike / name_cn ilike）真实存在
- [x] `scripts/seed_data.py:205` `("NVO_FAK", "NVO FAK (Consolidated)", "NVO FAK整合", CarrierType.nvo, "USA")` 真实存在
- [x] `scripts/seed_data.py:91-93` IDOKI 已在 KMTC 闭环加上；§4.4 新增 9 条 ports 落点位置已规划清楚
- [x] `backend/app/services/rate_parser.py:19-131` PORT_ALIAS_MAP 真实存在；§4.3 14 条 alias 缺口已逐条核实
- [x] `backend/app/services/step1_rates/service.py:13-21` `build_default_registry` 真实存在，新 adapter 注册位明确
- [x] `backend/app/services/step1_rates/registry.py:18-30` priority 升序遍历真实存在；NVO=5 排第一
- [x] `backend/app/services/step1_rates/entities.py:54-108` `Step1RateRow` 字段 `container_45` (line 68) / `service_code` (line 64) / `valid_to` (line 101) 真实存在
- [x] 4 sheet 用 openpyxl 真打开看了前 12 行 + 全量收集了 origin/destination 集合，§4.3/§4.4 缺口逐字段核实
- [x] 多区段表头（TPE 4 段 / WPE 3 段）已实测确认，§3.7 决策有真实数据依据（R5/R107/R124/R127/R146 行号真实）
- [x] 15 条验收点 V-N01..V-N15，每条都给出可观察判定，含 V-N15 D 项端到端 sqlite 激活链
- [x] 16 条风险 R-N01..R-N16，每条都给出兜底策略
- [x] 不写代码（只给签名 + 字段映射 + 数据流），由开发大师落键盘
- [x] 不抽公共基类（红线 6）
- [x] 不修 entities / activator dispatch / 前端（红线）
- [x] adapter 不接 db（红线 7，沿用 KMTC hot fix 后模式）

---

## 10. 与团队协作

- **业务大师**：本次需求口述清晰，无需打回；后续如出"4/30 NVO FAK 新版"，直接复用本 adapter（detect 关键字 "nvo"/"fak" 可通用）
- **开发大师**：按 §8 顺序推进；§5 接口契约、§4 字段映射不要二次发明；遇到新风险（§6 没列到的）立即停下质疑架构大师；**特别留意 §3.7 多区段扫描，这是与老 parser 最大的实现差异**
- **测试大师**：按 §7 V-N01..V-N15 写用例；fixture 路径见 §6 R-N15；V-N15 D 项必须用 sqlite memory，不能因 mac 无 PG 跳过；如发现 §7 哪条不可观察立即打回
- **监工**：抽查 §9 自检清单的 file:line（每条至少抽 4 条）；抽查是否违反 §0.2 / §3.1 / §3.7 红线；抽查 §4.3/§4.4 alias/seed 数量是否真等于 14/9；跑 V-N15 验证激活链
