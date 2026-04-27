# Step1 KMTC adapter — 架构任务单

- **版本**：v1.0
- **发布日期**：2026-04-27
- **作者**：架构大师
- **业务依据**：用户口述 — 追加第 4 个固定 adapter，处理 `资料/2026.03.31/kmtc 运价表 0319.xlsx`，参考 `/tmp/old_parser/rate_parser.py:261-452` 的 `parse_kmtc_excel`
- **同类参考**：
  - `docs/Step1_NGB解析器_架构任务单_20260423.md`（结构、In/Out 边界、§10 验收点风格）
  - `backend/app/services/step1_rates/adapters/ocean.py:17-825`（最接近 KMTC 的形态：单 sheet + 表头定位 + openpyxl）
  - `backend/app/services/step1_rates/adapters/ocean_ngb.py:17-612`（records 输出格式、warnings 收集、metadata 约定）
- **读者**：开发大师（按本单直接动手，不二次决策）、测试大师（按 §7 验收点写用例）、监工（抽查 file:line 真实性）
- **红线**：
  - 不动 `entities.py` / `protocols.py` / `service.py` / `registry.py` / `normalizers.py`
  - 不动 air/ocean/ocean_ngb 三 adapter 的任何代码
  - 不给 `activator.py` / `activator_mappers.py` 加 KMTC 专属分支（必须走通用 `to_freight_rate_from_ngb` 路径，复用 `_lookup_carrier` / `_resolve_port`）
  - 不写 alembic migration（schema 不变）
  - 不动 `/tmp/old_parser/rate_parser.py`（参考资料）
  - 不做 NVO FAK adapter（下个闭环）
  - 不抽 `_BaseRateAdapter` 共用基类（CLAUDE.md「三份相似比过早抽象好」，本次落第 4 份就是底线）

---

## 0. 任务范围（in / out 边界）

### 0.1 IN（本任务做的）

- 新建 `backend/app/services/step1_rates/adapters/kmtc.py` — 实现 `KmtcAdapter`，单文件内实现，不抽公共基类
- 实现 `detect()`（文件名 / sheet 名 / 表头三策略）+ `parse()`（openpyxl + 行扫描 + 分组行跳过）
- 输出 `ParsedRateBatch`：`file_type=ocean`、`adapter_key="kmtc"`、`metadata={parser_version, sheets_summary, region_lss_defaults, kmtc_origin_assumption}`
- 每条 record `record_kind="ocean_ngb_fcl"`（复用 NGB 入库通道，避免改 activator dispatch；走 `to_freight_rate_from_ngb` 流程；详见 §3.1 决策）
- 修改 `backend/app/services/step1_rates/adapters/__init__.py:1-9` — 注册 `KmtcAdapter`
- 修改 `backend/app/services/step1_rates/service.py:13-23` — 在 `build_default_registry` 中加 `KmtcAdapter()`
- 修改 `scripts/seed_data.py:16-182` — 补 1 条缺失港口（`OKI MILL SITE JETTY`，详见 §4.3）
- 新建 `backend/tests/services/step1_rates/adapters/test_kmtc_adapter.py` — pytest 用例骨架（验收点见 §7）

### 0.2 OUT（本任务不做的）

- 不扩 `Step1FileType` 枚举（不加 `kmtc` 值）。复用 `Step1FileType.ocean`，理由：
  - `entities.py:18-22` `Step1FileType` 改动会引发 `ImportBatchFileType`、迁移、前端 enum 联动改造，超出本闭环
  - KMTC 数据落 `freight_rates` 表（与 ocean 一致），不需要新文件类型
  - 区分由 `adapter_key="kmtc"` 在 metadata 携带，前端如需筛选可读 `metadata.adapter_key`
- 不动 `Step1RateRow` schema — 现有字段（`carrier_name`/`origin_port_name`/`destination_port_name`/`container_20gp/40gp/40hq`/`baf_20/40`/`lss_20/40`/`valid_from`/`transit_days`/`is_direct`/`remarks`/`extras`）足以承载 KMTC 所有字段
- 不复用 `/tmp/old_parser/rate_parser.py` 的 `_resolve_port`/`_safe_decimal`（老 parser 在 `app.services.rate_parser` 也有副本，被 ocean adapter 引用 — 见 `backend/app/services/step1_rates/adapters/ocean.py:13`；KMTC adapter 同样从 `app.services.rate_parser` 直接 import 这两个 helper，不再复制）
- 不复用老 parser 的 `_match_carrier`（那个会自动建 carrier，违反新 adapter "只输出 records" 的约定）。Carrier 名称统一固定写 `"KMTC"`，由 `activator_mappers._lookup_carrier` 走精确匹配 `Carrier.code == "KMTC"`（seed 已有，见 `scripts/seed_data.py:189`）
- 不做"含" → 显式 0 转换。"含"=`None`（同老 parser `_safe_decimal` 行为，见 `/tmp/old_parser/rate_parser.py:217`），并把原文 `"含"` 写入 `extras.lss_20_raw / lss_40_raw / baf_20_raw / baf_40_raw` 供前端展示
- 不做"分组行 region LSS 默认值"自动回填到 records 的 LSS 字段（业务侧未要求，且老 parser 也没做）。把 region LSS 文本提取到 `metadata.region_lss_defaults` 供后续闭环参考
- 不做物理表落库（落库由 `activator.py` + `activator_mappers.py` 统一处理）
- 不做 NVO FAK（下个闭环）
- 不动前端 / API / Writer

---

## 1. 数据流图

```
xlsx (KMTC-专刊 sheet, 126 行 × 15 列, max_row=126)
  ↓ openpyxl.load_workbook(path, data_only=True)
  ↓ KmtcAdapter.parse(path, db)
  ↓
 _parse_kmtc_sheet(ws):
  ├─ _locate_headers(ws) → main_header_row=3, sub_header_row=4
  │     （主表头关键字 "港口"/"O/F"/"BAF"/"LSS"/"生效"/"备注"，子表头关键字 "20GP"/"40GP"/"40HQ"）
  ├─ _build_column_layout(main_header_row, sub_header_row) → dict {
  │     port=1, schedule=2, company=3, route=4,
  │     of_20=5, of_40=6, of_hq=7,
  │     baf_20=8, baf_40=9,
  │     lss_20=10, lss_40=11,
  │     date=12, remark=13
  │  }
  ├─ origin_port_id = _resolve_port("Shanghai", db).id  # 固定上海，见 §3.2
  ├─ region_lss_defaults: dict[str, str] = {}
  ├─ for row_index in range(sub_header_row+1, ws.max_row+1):
  │     ├─ row = [ws.cell(r, c).value for c in range(1, 16)]
  │     ├─ if _is_region_header(row): 抽取 region LSS → region_lss_defaults; continue
  │     │   （A 列含"航线"+冒号 且 B~O 均 None，见 R5/R13/R70/R88/R95/R99；正则提取 LSS 文本）
  │     ├─ if _is_remark_or_note(row): continue
  │     │   （R102 起 "PS:" / "印度东:" / "危险品" / 单元格 None 的尾部说明区；判据：A 列非数字、E 列(O/F 20GP)非数字、且 A 不像港口名）
  │     ├─ port_name = row[port_col-1]  # 例 "BUSAN/釜山"
  │     ├─ of_20_value = row[of_20-1]
  │     ├─ if not _is_numeric(of_20_value): continue   # 跳过分组行/说明行
  │     ├─ dest_port = _resolve_port(port_name, db)  # 走 app.services.rate_parser._resolve_port
  │     ├─ if dest_port is None: warnings.append("Row {i}: 无法识别港口 '{port_name}'"); continue
  │     ├─ record = _build_record(row, dest_port, origin_port, ...)
  │     │     ├─ container_20gp/40gp/40hq = _safe_decimal(of_20/40/hq)
  │     │     ├─ baf_20/40 = _safe_decimal(...)（"含"→None；0 保持 0）
  │     │     ├─ lss_20/40 = _safe_decimal(...)（同上）
  │     │     ├─ valid_from = _to_date(date_col_value)  （兼容 datetime / date / "2026/3/5" 字符串）
  │     │     ├─ transit_days, is_direct = _parse_transit_days(remark)
  │     │     ├─ extras 装入：sheet_name/row_index/schedule/route/raw "含" 标记
  │     │     └─ ParsedRateRecord(record_kind="ocean_ngb_fcl", ...)
  │     └─ records.append(record)
  ↓
 records (~90 条) + warnings (去重) + metadata
  ↓
 ParsedRateBatch (file_type=ocean, adapter_key="kmtc")
  ↓ rate_batch_service._build_draft_batch → DraftRateBatch
  ↓ activator.activate(draft, db, dry_run/真激活)
       └─ for record in dispatchable: kind == "ocean_ngb_fcl"
            → to_freight_rate_from_ngb(record, batch_uuid, db)
                 ├─ _lookup_carrier(db, "KMTC") → 命中 Carrier.code='KMTC'
                 ├─ _resolve_port(db, origin_port_name="Shanghai") → CNSHA
                 ├─ _resolve_port(db, destination_port_name="BUSAN/釜山") → KRPUS
                 └─ FreightRate(... rate_level=None ...)
```

---

## 2. 文件级改动清单

| 动作 | 路径 | 说明 |
|---|---|---|
| 新增 | `backend/app/services/step1_rates/adapters/kmtc.py` | 单文件内实现 KmtcAdapter；约 280-340 行，参考 `ocean.py` 的代码组织（detect/parse/_locate_headers/_build_column_layout/_build_record/_is_region_header/_is_remark_or_note/_to_date/_parse_transit_days/_dedupe_warnings） |
| 修改 | `backend/app/services/step1_rates/adapters/__init__.py:1-9` | 第 4 行加 `from app.services.step1_rates.adapters.kmtc import KmtcAdapter`；第 8 行 `__all__` 列表加 `"KmtcAdapter"` |
| 修改 | `backend/app/services/step1_rates/service.py:13-23` | `build_default_registry` 第 17 行 adapters 列表追加 `KmtcAdapter()`（顺序无关，detect 优先级由 `priority` 决定） |
| 修改 | `scripts/seed_data.py:91` | `IDBJM` 行后追加一条：`("IDOKI", "Oki Mill Site Jetty", "OKI 米仓码头", "Indonesia", "Southeast Asia"),` — 见 §4.3 |
| 新增 | `backend/tests/services/step1_rates/adapters/test_kmtc_adapter.py` | pytest；fixture 用 `资料/2026.03.31/kmtc 运价表 0319.xlsx`；本任务单只定义验收点（§7），实际用例由测试大师写 |
| 不动 | `backend/app/services/step1_rates/entities.py` | `Step1FileType.ocean` 复用；`Step1RateRow` 字段足够 |
| 不动 | `backend/app/services/step1_rates/activator.py:182-188` | `kind == "ocean_ngb_fcl"` 已分流到 `to_freight_rate_from_ngb`，KMTC 直接复用 |
| 不动 | `backend/app/services/step1_rates/activator_mappers.py:148-191` | `to_freight_rate_from_ngb` 已用通用 `_lookup_carrier` / `_resolve_port`，KMTC 走通；注意此函数不写 `baf_20/40 / lss_20/40`（见 §6 风险 R-K05） |
| 不动 | `backend/app/services/rate_batch_service.py:64-118` | `create_draft_batch_from_upload` 走 `parse_excel_file` → `registry.resolve(path)` → `KmtcAdapter.detect()` 命中 |
| 不动 | `backend/app/services/step1_rates/registry.py:18-30` | priority 数值越小越先 detect；KMTC 设 priority=15（低于 ocean=20，避免 `kmtc 运价表 0319.xlsx` 被 ocean detect 误命中 — `ocean.py:45` 的 `"ocean" in normalized_name and "ngb" not in normalized_name` 不会命中 "kmtc"，但仍以 15 显式优先） |

---

## 3. 关键设计决策（开发大师必须按此落，不要改）

### 3.1 record_kind 复用 `"ocean_ngb_fcl"`

**决策**：每条 KMTC record 的 `record_kind` 字段写 `"ocean_ngb_fcl"`，不新增 kind。

**理由**：
- `activator.py:172-195` 的 dispatch 表只认 4 个 kind：`air_weekly`/`air_surcharge`/`fcl`/`ocean_ngb_fcl`；新增 kind 必须改 `activator.py` + `_plan_imported_detail`（违反红线"不给 activator 加 KMTC 专属分支"）
- `to_freight_rate_from_ngb`（`activator_mappers.py:148-191`）的行为正符合 KMTC 需求：carrier 走 `_lookup_carrier(name="KMTC")`，origin/dest 走 `_resolve_port` 做名称→port 解析（KMTC 的 origin/dest 都是字符串名，没有 port_id）
- `to_freight_rate_from_ocean`（`activator_mappers.py:85-145`）要求 `origin_port_id` / `destination_port_id` 已在 record 中预解析（见 `ocean.py:678-686` `_resolve_port_ref`）— 而 KMTC adapter 也可以照做，但走 ngb 路径更省事且与 NGB 行为完全对齐

**副作用**：`metadata.record_kind_distribution` 中 KMTC 的行会和 NGB 的行混在 `ocean_ngb_fcl` 计数下；通过 `metadata.adapter_key="kmtc"` 区分。前端如要分别展示，按 adapter_key 过滤 batch 即可。

### 3.2 origin_port 固定为 "Shanghai"

**决策**：所有 KMTC record 的 `origin_port_name = "Shanghai"`；不从文件名/表头自动检测。

**理由**：
- 老 parser（`/tmp/old_parser/rate_parser.py:374-379`）尝试从前 5 行内容匹配"宁波"/"青岛"，但样本文件中没有这种字样，测试也没法验证；过度设计
- KMTC 上海发是绝大多数情况；如果客户后续给宁波/青岛版本，按"再来一个 adapter / 再加 detect 关键字"处理（CLAUDE.md：三份相似比过早抽象好）
- `_lookup_carrier` 期望 carrier 名字为字符串，`to_freight_rate_from_ngb` 走 `_resolve_port(db, "Shanghai")` 命中 `Port.name_en ilike '%Shanghai%'` → CNSHA（seed 已有，`scripts/seed_data.py:34`）

**副作用**：将来宁波/青岛 KMTC 文件来时，需要在 detect 中按文件名/sheet 名增加分支，origin 字符串改为 "Ningbo"/"Qingdao"。本闭环不做。

### 3.3 detect 三策略 + priority

**优先级**：`priority=15`（更低 = 更先 detect）

**detect 策略**（在 `KmtcAdapter.detect(path, file_type_hint)` 中按顺序尝试，命中即返回 True）：

1. **file_type_hint**（与现有 adapter 一致）：`if file_type_hint == self.file_type: return True`（self.file_type = `Step1FileType.ocean`，但 ocean adapter 也用 ocean — 因此 hint 命中只用于 detect 不冲突；正常上传不带 hint，走文件名）
2. **文件名关键字**（大小写不敏感）：`"kmtc" in path.name.lower()` 或 `"高丽" in path.name` 或 `"高麗" in path.name`
3. **sheet 名关键字**（兜底，需打开 workbook，仅在文件名未命中时执行；性能可接受 — KMTC 文件就 126 行）：用 `openpyxl.load_workbook(path, read_only=True, data_only=True).sheetnames`，看是否含 `"KMTC"` 或 `"高丽"` 或 `"高麗"`；命中后立刻 close 并返回 True

**风险隔离**：策略 3 不做"读 5 行内容找 'QUOTATION FM KMTC' 关键字"那种深度内容嗅探（老 parser `rate_parser.py:646-657` 干过，但有性能/异常隐患）。如样本文件名异常（如 `0319.xlsx`），用户应提供 parser_hint 或重命名文件。

### 3.4 effective_from / effective_to

- `effective_from`：取所有 record `valid_from` 字段的 **min（非空值）**
- `effective_to`：固定为 `None`（KMTC 表无失效日期列；老 parser 同样置 None，见 `rate_parser.py:435`）
- 若所有行 valid_from 都为空：`effective_from = None`，warning：`"KMTC workbook: no valid effective dates extracted from L column"`
- 该范围塞入 `ParsedRateBatch.effective_from / effective_to` + `metadata.sheets[0].effective_from / effective_to`

### 3.5 carrier_name 固定 "KMTC"

每条 record `carrier_name = "KMTC"`（字符串字面量，不是 carrier_id）。

**注意**：原表 C 列"船公司"有时是 "高丽海运"、有时是 None（见 R6 vs R14）— 都忽略。KMTC 表里所有行都是 KMTC 自家的运价，这一列用于船司侧内部分流，与 carrier 字典解析无关。

`_lookup_carrier` 命中规则（`activator_mappers.py:194-223`）：精确 `Carrier.code == "KMTC"` 一击命中 seed 行。

---

## 4. 字段映射表（开发大师按此填）

### 4.1 列号 → 业务含义（基于 R3/R4 表头实拍，1-based）

| Col | R3 主表头 | R4 子表头 | 业务字段 | record 字段 | 备注 |
|---|---|---|---|---|---|
| 1 | 港口 | — | destination_port_name 原文 | `destination_port_name` | 例 "BUSAN/釜山"；`_resolve_port` 拆解 |
| 2 | 船期 | — | sailing_day_text | `extras.schedule_text` | 例 "周二三四六日" |
| 3 | 船公司 | — | shipping_line_text | `extras.shipping_line_text` | 例 "高丽海运" 或 None |
| 4 | 航线 | — | route_code | `extras.route_code` 或 `service_code` 留空 | 例 "ISS2"、"KCM/VTX" |
| 5 | O/F | 20GP | container_20gp | `container_20gp` | Decimal；"含"→None；0→0 |
| 6 | O/F | 40GP | container_40gp | `container_40gp` | 同上 |
| 7 | O/F | 40HQ | container_40hq | `container_40hq` | 同上 |
| 8 | BAF/WRS | 20GP | baf_20 | `baf_20` | "含"→None；0→0 |
| 9 | BAF/WRS | 40GP/HQ | baf_40 | `baf_40` | 同上（KMTC 表中 40GP/HQ 共一列） |
| 10 | LSS | 20GP | lss_20 | `lss_20` | 同上 |
| 11 | LSS | 40GP/HQ | lss_40 | `lss_40` | 同上 |
| 12 | 生效日（实际开航日） | — | valid_from | `valid_from` | datetime / date / "2026/3/5" 字符串三态兜底 |
| 13 | 备注 | — | remarks | `remarks` | 原文；同时抽 transit_days / is_direct |

### 4.2 Step1RateRow 字段映射

| Step1RateRow 字段 | 来源 | 类型 |
|---|---|---|
| `record_kind` | 字面量 `"ocean_ngb_fcl"` | str |
| `carrier_name` | 字面量 `"KMTC"` | str |
| `origin_port_name` | 字面量 `"Shanghai"` | str |
| `origin_port_id` | None（让 `_resolve_port` 在 activator 阶段查） | None |
| `destination_port_name` | row[0]（"BUSAN/釜山" 原文） | str |
| `destination_port_id` | None | None |
| `service_code` | None（路由码 `route_code` 放 extras） | None |
| `container_20gp` | _safe_decimal(row[4]) | Decimal\|None |
| `container_40gp` | _safe_decimal(row[5]) | Decimal\|None |
| `container_40hq` | _safe_decimal(row[6]) | Decimal\|None |
| `baf_20` | _safe_decimal(row[7]) | Decimal\|None |
| `baf_40` | _safe_decimal(row[8]) | Decimal\|None |
| `lss_20` | _safe_decimal(row[9]) | Decimal\|None |
| `lss_40` | _safe_decimal(row[10]) | Decimal\|None |
| `currency` | 字面量 `"USD"`（KMTC 全表 USD） | str |
| `valid_from` | _to_date(row[11]) | date\|None |
| `valid_to` | None（业务无失效日列） | None |
| `transit_days` | _parse_transit_days(remark)[0] | int\|None |
| `is_direct` | _parse_transit_days(remark)[1] | bool |
| `remarks` | row[12] | str\|None |
| `source_type` | 字面量 `"excel"` | str |
| `source_file` | path.name | str |
| `extras` | dict（见 §4.4） | dict |

### 4.3 seed_data.py 港口缺口

对 126 行所有目的港逐个核对 `seed_data.py:16-182` 的 PORTS 列表（覆盖检查）：

| KMTC 表中港口 | seed 是否存在 | 备注 |
|---|---|---|
| BUSAN/KWANGYANG/ULSAN/POHANG/INCHON/GUNSAN | ✅ KRPUS/KRKWA/KRULS/KRPOH/KRINC/KRKAN | seed:45-50 |
| HONGKONG | ✅ HKHKG | seed:53 |
| HAIPHONG / HOCHIMINH | ✅ VNHPH/VNSGN | seed:60-61 |
| PHNOM PENH | ✅ KHPNH | seed:65 |
| BANGKOK / BKK / LAEM CHABANG / LAT KRABANG | ✅ THBKK/THLCH/THLKR | seed:69-71；终端后缀 PAT/UNITHAI/TCTB/BMT/SCT 由 `_resolve_port` 剥离 |
| SINGAPORE | ✅ SGSIN | seed:74 |
| PASIR GUDANG / PENANG / PORT KELANG | ✅ MYPGU/MYPEN/MYPKG | seed:77-79；PORT KELANG (N) 和 (W) 都映射到 MYPKG，由 `_resolve_port` 去括号处理 |
| JAKARTA / SEMARANG / SURABAYA / BELAWAN / PANJANG / PALEMBANG / PONTIANAK / BATAM / BANJARMAISEN | ✅ IDJKT/IDSMG/IDSUB/IDBLW/IDPNJ/IDPLM/IDPTK/IDBTM/IDBJM | seed:84-92 |
| **OKI MILL SITE JETTY** | ❌ **缺！** | R68；本任务必须在 seed 加 1 条 `("IDOKI", "Oki Mill Site Jetty", "OKI 米仓码头", "Indonesia", "Southeast Asia")` |
| NHAVE SHEVA / MUNDRA / HAZIRA / KARACHI / CHENNAI / KATTUPALLI / VIZAG / TUTICORIN | ✅ INNSA/INMUN/INHAZ/PKKHI/INMAA/INKTP/INVTZ/INTUT | seed:95-101, 105 |
| MOMBASA / DAR ES SALAAM | ✅ KEMBA/TZDAR | seed:121-122 |
| JEBEL ALI / SOHAR / ABU DHABI / KUWAI(科威特) / UMM QASAR / KHALIFABIN SALMAN PORT | ✅ AEJEA/OMSOH/AEAUH/KWKWI/IQUQR/BHKBS | seed:108-113；KMTC 写 "KUWAI" 缺 T，但中文"科威特"由 `_resolve_port` 第 3 步中文匹配命中 |
| JEDDAH / SOKHNA / AQABA | ✅ SAJED/EGSOK/JOAQJ | seed:116-118 |
| MANZANILLO | ✅ MXMAN | seed:125 |

**总缺口**：1 条（OKI MILL SITE JETTY）。

**操作**：
- 在 `scripts/seed_data.py:91`（IDBJM 那一行）后追加 `("IDOKI", "Oki Mill Site Jetty", "OKI 米仓码头", "Indonesia", "Southeast Asia"),`
- 用户在 Windows 上重跑 `D:\Anaconda3\envs\py310\python.exe scripts/seed_data.py`（监工自己跑 mac 镜像验证）

### 4.4 extras 字段定义

```python
extras = {
    "sheet_name": "KMTC-专刊",
    "row_index": 6,                      # 1-based, 与 openpyxl 一致
    "schedule_text": "周二三四六日",      # row[1]
    "shipping_line_text": "高丽海运",    # row[2] 或 None
    "route_code": "ISS2",                # row[3] 或 None
    "container_20gp_raw": "130",         # str 原文，便于前端展示
    "container_40gp_raw": "260",
    "container_40hq_raw": "260",
    "baf_20_raw": "220",
    "baf_40_raw": "440",
    "lss_20_raw": "含",                  # "含" 原文保留（lss_20 数值字段为 None）
    "lss_40_raw": "含",
    "valid_from_raw": "2026-03-23T00:00:00",  # 用 str() 兜底
    "remark_raw": "直达2天 含  LSS",      # row[12] 原文
    "destination_port_raw": "BUSAN/釜山", # row[0] 原文
}
```

### 4.5 metadata（ParsedRateBatch.metadata）

```python
metadata = {
    "file_name": path.name,
    "source_type": "excel",
    "carrier_code": "KMTC",
    "parser_version": "kmtc_v1",
    "kmtc_origin_assumption": "default origin = Shanghai for all rows",
    "sheets": [
        {
            "sheet_name": "KMTC-专刊",
            "total_rows": <int, 期望 90 ±2>,
            "effective_from": <date>,
            "effective_to": None,
        }
    ],
    "region_lss_defaults": {
        # 解析每个 region 分组行（R5/R13/R70/R88/R95/R99）抽出 LSS 文本
        # 例：
        # "R5_韩国航线": "USD 14/100",
        # "R13_东南亚航线": "75/150",
        # "R13_东南亚_香港": "USD60/120",
        # "R70_印巴航线": "USD 160/320",
        # "R70_肯尼亚": "USD210/420",
        # "R88_中东航线": "USD 180/360",
        # "R99_墨西哥航线": "USD60/120",
        # 提取规则：A 列字符串中匹配 "LSS：USD?\s?(\d+/\d+)" 或 "LSS：USD?\s?(\d+)/(\d+)"
        # 抓不到也不报错，置空字符串
    },
    "record_kind_distribution": {"ocean_ngb_fcl": <count>},
}
```

---

## 5. KmtcAdapter 接口契约

```python
# backend/app/services/step1_rates/adapters/kmtc.py

from __future__ import annotations
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.services.rate_parser import _resolve_port, _safe_decimal
from app.services.step1_rates.entities import ParsedRateBatch, ParsedRateRecord, Step1FileType


class KmtcAdapter:
    """Step1 KMTC parser for the Sea专刊 workbook (上海发, USD)."""

    key: str = "kmtc"
    file_type: Step1FileType = Step1FileType.ocean   # 复用 ocean 枚举（见 §0.2）
    priority: int = 15                                # 比 ocean=20 优先

    _SHEET_NAME: str = "KMTC-专刊"
    _DEFAULT_ORIGIN_NAME: str = "Shanghai"
    _CARRIER_NAME: str = "KMTC"
    _CURRENCY: str = "USD"
    _MAX_COL: int = 15

    # 数据行起始候选（动态找表头，期望 main=R3, sub=R4，data 起 R5+）
    _HEADER_SCAN_LIMIT: int = 10

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        ...

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        ...

    # 私有方法（按粒度拆，单元测试可独立 patch）
    def _locate_headers(self, ws) -> tuple[int | None, int | None]: ...
    def _build_column_layout(self, ws, main_row: int, sub_row: int) -> dict[str, int] | None: ...
    def _is_region_header(self, row: list[Any]) -> bool: ...
    def _is_remark_or_note(self, row: list[Any], layout: dict[str, int]) -> bool: ...
    def _extract_region_lss(self, text: str) -> dict[str, str]: ...
    def _build_record(
        self,
        row: list[Any],
        row_index: int,
        layout: dict[str, int],
        source_file: str,
    ) -> tuple[ParsedRateRecord | None, list[str]]: ...
    def _to_date(self, value: Any) -> date | None: ...
    def _parse_transit_days(self, remark: str | None) -> tuple[int | None, bool]: ...
    def _normalize_text(self, value: Any) -> str | None: ...
    def _is_numeric(self, value: Any) -> bool: ...
    def _dedupe_warnings(self, warnings: Iterable[str]) -> list[str]: ...
```

**关键私有方法行为约定**：

| 方法 | 入参 | 出参 | 备注 |
|---|---|---|---|
| `_locate_headers` | ws | (main_row, sub_row) | 在前 10 行扫；main 行需含 "港口" 或 ("o/f" + ("baf" 或 "lss"))；sub 行需在 main_row 之后、含任意 "20" 或 "40"；找不到返回 (None, None) |
| `_build_column_layout` | ws, main_row, sub_row | dict 或 None | 按 §4.1 列号映射；返回 None 时 parse 应返回空 records + warning |
| `_is_region_header` | row | bool | A 列字符串含 "航线" 且含 "："/":"，且 B 至 O 列**全 None** → True |
| `_is_remark_or_note` | row, layout | bool | A 列非空但 of_20 列为 None 或非数字 → True（含 R102+ 的尾部说明） |
| `_extract_region_lss` | text | dict[str, str] | 用正则 `r"LSS[：:]\s*USD?\s*(\d+\s*/\s*\d+)"` 抽出键值；同一行可能多个匹配（如 R13） |
| `_build_record` | row, row_index, layout, source_file | (record, row_warnings) | 若港口未识别，返回 (None, [warning])；若 of_20 非数字，调用方应已跳过 |
| `_to_date` | value | date \| None | datetime → .date()；date → 原值；str（"2026/3/5"）→ datetime.strptime 三态尝试（"%Y/%m/%d", "%Y-%m-%d"）；其他 → None |
| `_parse_transit_days` | remark | (int \| None, bool) | 复用老 parser 逻辑（`/tmp/old_parser/rate_parser.py:232-242`）：正则 `(\d+)\s*天` + "直达"/"中转" 判断 |
| `_is_numeric` | value | bool | int/float（非 NaN）→ True；str 可转 float → True；其他 → False |

**parse() 主方法约定**：

```
def parse(self, path, db=None):
    1. wb = load_workbook(path, data_only=True)
    2. if "KMTC-专刊" not in wb.sheetnames: 返回空 batch + warning
    3. ws = wb["KMTC-专刊"]
    4. main_row, sub_row = _locate_headers(ws)
       if None: 返回空 batch + warning
    5. layout = _build_column_layout(ws, main_row, sub_row)
       if None: 返回空 batch + warning
    6. origin_port_name = "Shanghai"
    7. region_lss_defaults = {}
    8. records, warnings = [], []
    9. for row_index in range(sub_row+1, ws.max_row+1):
         row = [ws.cell(row_index, c).value for c in range(1, _MAX_COL+1)]
         if 整行空: continue
         if _is_region_header(row):
             region_lss_defaults.update(...)
             continue
         if _is_remark_or_note(row, layout): continue
         record, row_warnings = _build_record(row, row_index, layout, path.name)
         warnings.extend(row_warnings)
         if record is not None: records.append(record)
   10. effective_from = min((r.valid_from for r in records if r.valid_from), default=None)
       effective_to = None
   11. metadata = {...}（见 §4.5）
   12. return ParsedRateBatch(file_type=Step1FileType.ocean, source_file=path.name,
                              effective_from=effective_from, effective_to=None,
                              records=records, warnings=_dedupe_warnings(warnings),
                              adapter_key="kmtc", metadata=metadata)
```

---

## 6. 风险 / 坑 / 边界（开发大师必须知道的"前人踩过的雷"）

| ID | 风险描述 | 兜底策略 |
|---|---|---|
| **R-K01** | **04-24 NGB 软失败 0 行入库重演**：seed 端口缺 OKI MILL SITE JETTY → activator 阶段 `_resolve_port` 返回 None → 整行 PORT_NOT_FOUND → 走软失败 skip 但不 fail 整批，最终 `imported_rows < total_rows` | 必须按 §4.3 在 seed 加 IDOKI；并在测试 V-K09 验证整批 90 行至少 89 行入库（容错 1 行因 OKI 未提前 seed 也算通过） |
| **R-K02** | **"含" / 数值 / 0 三态混用**：BAF/LSS 列同时出现 "含"（R6）、220（R6）、0（R14） — 不能把 "含" 当 0（业务侧 "含" = 该港口已包含在主运费里，0 = 此项不收）| `_safe_decimal` 已正确处理（`/tmp/old_parser/rate_parser.py:217` 把 "含" 映射 None；0 走 `Decimal('0')` 保留）。adapter 把原文 "含" 写 `extras.lss_20_raw / lss_40_raw / baf_20_raw / baf_40_raw`，前端展示原文 |
| **R-K03** | **生效日 3 态**：L 列既有 datetime（R6 `datetime(2026,3,23)`），又有 str（R90 `"2026/3/5"`），还可能为 None | `_to_date` 三态尝试：datetime → date()；date → 原值；str → strptime("%Y/%m/%d") fallback strptime("%Y-%m-%d")；都失败 → None + 不报错（不阻塞整行） |
| **R-K04** | **港名带 (N)/(W) 括号变体 / 终端后缀 / 连字符**：R46 "PORT KELANG（N)/巴生北港"、R34 "BKK - BMT"、R22 "BANGKOK/曼谷 PAT" — 直接走 `_resolve_port` 才能拆解 | 不要自己写解析；直接调 `app.services.rate_parser._resolve_port`，已含 `_TERMINAL_SUFFIXES` / `_TERMINAL_CONNECTORS` 处理（见 `/tmp/old_parser/rate_parser.py:143-208`，本项目副本路径为 `backend/app/services/rate_parser.py` — 由 ocean.py:13 已 import 验证可用）。失败时记 warning，但不 raise |
| **R-K05** | **`to_freight_rate_from_ngb` 不写 baf_20/40 / lss_20/40**：见 `activator_mappers.py:173-191`，该函数构造 FreightRate 时**只写** carrier/origin/dest/container_20gp/40gp/40hq/currency/valid_from/to/remarks/source/batch_id/status/rate_level，**不写** BAF/LSS 字段 | **本闭环不修 mapper**（红线）。BAF/LSS 数值会丢失到 freight_rates 表，但保留在 record.extras（前端可读 batch detail 中 preview_rows）。如果业务要求 KMTC 的 BAF/LSS 入库，下个闭环改 `to_freight_rate_from_ngb` 加 baf_20/40/lss_20/40 字段拷贝（兼容 NGB — NGB 本就没填，加了也是 None） |
| **R-K06** | **R102 起的尾部说明区把脏数据当数据行**：R102-R126 是 PS / 适用航次 / 危险品 等纯文本说明（A 列非 None，B-O 列大多 None），E 列 None | `_is_remark_or_note(row, layout)`：A 列非空 + of_20 列 None 或非数字 → True 跳过。注意不能用 `_is_region_header` 判（那个要求"航线"+冒号），R102 "PS:" 是另一种形态 |
| **R-K07** | **分组行下沉默契**：R5/R13/R70/R88/R95/R99 是 region 头，下面紧跟港口数据；R5 含韩国航线 LSS 默认值 → 老 parser 没塞回 record（业务也没要求），本闭环也不要塞 | 仅抽 `metadata.region_lss_defaults` 字符串原文供未来参考；不要自动 fill 到 lss_20/40 |
| **R-K08** | **R-only 表格**：openpyxl `data_only=True` 模式必须用，否则单元格会拿到公式字符串（KMTC 表本身没有公式，但模板可能有；保守起见加） | `load_workbook(path, data_only=True)`（不要 `read_only=True`，read_only 与 merged_cells 配合不稳；ocean.py:48 / ocean_ngb.py:117 都没用 read_only） |
| **R-K09** | **detect 与 ocean 冲突**：ocean.py:45 `"ocean" in normalized_name and "ngb" not in normalized_name` — KMTC 文件名 `kmtc 运价表 0319.xlsx` 不含 "ocean"，不会冲突；但若用户改名为 `kmtc ocean rate.xlsx`，可能被 ocean adapter 抢先 | 设 `priority=15` 比 ocean=20 优先；KmtcAdapter detect 第 1 优先 file_type_hint，第 2 文件名 "kmtc"/"高丽"，第 3 sheet 名 "KMTC"。registry resolve 按 priority 升序遍历，命中即返回（registry.py:22-30） |
| **R-K10** | **承运商列 C 是 None 不要当错误**：R6/R7/R8 等行 C 列为 None；`/tmp/old_parser/rate_parser.py:404` 没据此跳行 | adapter 也不据此跳行；C 列只塞 `extras.shipping_line_text`，carrier_name 永远是 "KMTC" |
| **R-K11** | **测试 fixture Excel 路径中文 + 空格**：`资料/2026.03.31/kmtc 运价表 0319.xlsx` | pytest fixture 用 `pathlib.Path(__file__).parents[5] / "资料" / "2026.03.31" / "kmtc 运价表 0319.xlsx"`，断言 `path.exists()` 提前 fail 而非加载报错 |
| **R-K12** | **rate_batch_service.create_draft_batch_from_upload 走 LookupError 兜底 → AI fallback**：若 KmtcAdapter detect 没注册，`registry.resolve` 抛 LookupError，触发 `_try_ai_fallback_on_excel`（rate_batch_service.py:96-109）— 会用 AI 解析 KMTC 表，可能出错或耗时 | adapter 必须在 `service.py:13-23 build_default_registry` 中注册；测试 V-K01 验证 detect 命中（不走 fallback） |

---

## 7. 验收点（V-K01..V-K12，交给测试大师）

每个验收点都必须可以独立观察、给出明确判定（pass/fail），不能写"运行正常"。

| ID | 验收点描述 | 期望观察值 |
|---|---|---|
| **V-K01** | **detect 命中**：把 `kmtc 运价表 0319.xlsx` 路径喂 `DEFAULT_RATE_ADAPTER_REGISTRY.resolve(path)`，应返回 `KmtcAdapter` 实例 | `isinstance(adapter, KmtcAdapter) == True` |
| **V-K02** | **表头定位**：`adapter._locate_headers(ws)` 返回 `(3, 4)` | `(main_row, sub_row) == (3, 4)` |
| **V-K03** | **列布局**：`adapter._build_column_layout(ws, 3, 4)["of_20"] == 5` 且 `["lss_40"] == 11` 且 `["date"] == 12` 且 `["remark"] == 13` | 至少这 4 个 key 等于上述值 |
| **V-K04** | **分组行跳过**：解析后 records 中**不存在** `extras.row_index in {5, 13, 70, 88, 95, 99}` 的行（这些是 region 头） | 全部 False |
| **V-K05** | **单容器规格抽取**（R6 釜山）：找到 `extras.row_index == 6` 的 record，`container_20gp == Decimal("130")`、`container_40gp == Decimal("260")`、`container_40hq == Decimal("260")`、`baf_20 == Decimal("220")`、`baf_40 == Decimal("440")`、`lss_20 is None`、`lss_40 is None`、`extras.lss_20_raw == "含"` | 字段值全部命中 |
| **V-K06** | **"含"/0 / 数值 三态区分**（R14 香港）：`baf_20 is None`、`extras.baf_20_raw == "含"`、`lss_20 == Decimal("0")`、`extras.lss_20_raw == "0"` | 数值字段与 raw 字段区分正确 |
| **V-K07** | **生效日 datetime 抽取**（R6）：`valid_from == date(2026, 3, 23)`；**str 形态**（R90）：`valid_from == date(2026, 3, 5)` | 两种形态都成功 |
| **V-K08** | **transit_days 抽取**（R6 "直达2天 含 LSS"）：`transit_days == 2` 且 `is_direct == True`；（R19 "HCM中转+2天"）：`transit_days == 2` 且 `is_direct == False` | 两个 case 同时通过 |
| **V-K09** | **未知港口软失败**：临时把 seed 中 IDOKI 港删除（或手动制造 1 个未知港行），整批解析依然完成，warnings 中含 `"无法识别港口 'OKI MILL SITE JETTY'"`（或类似），records 数量 = 总行数 - 1 | 不抛异常；warnings 含该字符串；records 至少 89 条 |
| **V-K10** | **整文件 records 计数**：解析 `kmtc 运价表 0319.xlsx`，`len(batch.records) == 90 ± 2`（基于 §1 数据流 R6-R100 排除分组行后的有效行数；±2 容错 region 边缘行） | 88 ≤ len(batch.records) ≤ 92 |
| **V-K11** | **激活链端到端**：上传该文件 → `parse_excel_file` → `create_draft_batch_from_upload` → `activate_rate_batch(dry_run=False)` → 返回 `{"activation_status": "activated", "imported_rows": >=89}`；DB 中 `freight_rates.batch_id == 该 batch_id` 的行数 >= 89；`carriers.code='KMTC'` 命中且 `origin_port.un_locode='CNSHA'` 全部正确 | imported_rows >= 89；DB 行数 >= 89；carrier_id / origin_port_id 全部非 NULL |
| **V-K12** | **detect 优先级**：手动构造一个文件名为 `kmtc_ocean.xlsx` 的副本，`registry.resolve` 仍返回 KmtcAdapter（不是 OceanAdapter） | priority=15 < 20 生效 |

---

## 8. 实施顺序（开发大师按此推进，每步可独立 commit）

| 步 | 动作 | 验收 |
|---|---|---|
| 1 | 在 `seed_data.py:91` 加 IDOKI；用户在 Windows 重跑 seed | DB `ports.un_locode='IDOKI'` 存在 |
| 2 | 新建 `kmtc.py` 骨架（class + 字段 + detect 空实现 + parse 返回空 batch） | import 不报错 |
| 3 | 实现 `_locate_headers` + `_build_column_layout` + 单元测试 V-K02/V-K03 | 通过 |
| 4 | 实现 `_is_region_header` + `_is_remark_or_note` + `_to_date` + `_parse_transit_days` 四个 helper | 通过单元测试 |
| 5 | 实现 `_build_record` + parse 主循环；先不接 detect 注册 | 手动 `KmtcAdapter().parse(path)` 返回 records |
| 6 | 验证 V-K05/V-K06/V-K07/V-K08（数值字段、raw 字段、日期、transit_days） | 通过 |
| 7 | 在 `adapters/__init__.py` 导出 + `service.py:13-23 build_default_registry` 注册 | V-K01/V-K12 通过 |
| 8 | 端到端测试 V-K11（POST /api/v1/rate-batches → activate） | 通过 |
| 9 | V-K09 软失败（手工注掉 seed 验证） + V-K10 计数验收 | 通过 |
| 10 | 监工抽查：file:line 真实性、3 个红线无违反、9-12 个 warning 都有去重 | pass |

**预估总工时**：开发大师 6-8 人时（含测试用例）；测试大师 2-3 人时；监工抽查 0.5 人时。

---

## 9. 自检清单（架构大师）

- [x] `/tmp/old_parser/rate_parser.py:261-452` 的 `parse_kmtc_excel` 已读完，列号映射、表头定位、"含"处理、transit_days 抽取均已对齐
- [x] `backend/app/services/step1_rates/adapters/__init__.py:1-9` 真实存在，注册位 line 4 + line 8
- [x] `backend/app/services/step1_rates/adapters/ocean.py:48` openpyxl.load_workbook(path, data_only=True) 真实存在
- [x] `backend/app/services/step1_rates/adapters/ocean.py:13` `from app.services.rate_parser import _resolve_port, _safe_decimal` 真实存在
- [x] `backend/app/services/step1_rates/adapters/ocean_ngb.py:117` 同上
- [x] `backend/app/services/step1_rates/activator.py:182-188` `kind == "ocean_ngb_fcl"` 分流真实存在
- [x] `backend/app/services/step1_rates/activator_mappers.py:148-191` `to_freight_rate_from_ngb` 真实存在；§6 R-K05 风险（不写 BAF/LSS）已核实
- [x] `backend/app/services/step1_rates/activator_mappers.py:194-223` `_lookup_carrier` 精确匹配 `Carrier.code` 优先真实存在
- [x] `scripts/seed_data.py:189` `("KMTC", "KMTC Line", "高丽海运", ...)` 真实存在；§4.3 OKI 缺口已核实，对照 KMTC 表 126 行所有目的港逐个匹对
- [x] `backend/app/services/rate_batch_service.py:96-109` AI fallback 路径真实存在；§6 R-K12 风险已识别
- [x] `backend/app/services/step1_rates/service.py:13-23 build_default_registry` 真实存在，新 adapter 注册位明确
- [x] `backend/app/services/step1_rates/registry.py:22-30` priority 升序遍历真实存在
- [x] 12 条验收点 V-K01..V-K12，每条都给出可观察判定
- [x] 12 条风险 R-K01..R-K12，每条都给出兜底策略
- [x] 不写代码（只给签名 + 字段映射 + 数据流），由开发大师落键盘
- [x] 不抽公共基类（CLAUDE.md 红线）
- [x] 不修 entities / activator dispatch / 前端（红线）

---

## 10. 与团队协作

- **业务大师**：本次需求口述清晰，无需打回；后续如出"宁波 KMTC"/"青岛 KMTC"，再开新闭环
- **开发大师**：按 §8 顺序推进；§5 接口契约、§4 字段映射不要二次发明；遇到新风险（§6 没列到的）立即停下质疑架构大师
- **测试大师**：按 §7 V-K01..V-K12 写用例；fixture 路径见 §6 R-K11；如发现 §7 哪条不可观察立即打回
- **监工**：抽查 §9 自检清单的 file:line（每条至少抽 3 条）；抽查是否违反 §0.2 / §3.1 红线（不改 entities、不加 activator 分支）
