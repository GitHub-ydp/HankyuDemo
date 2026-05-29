# ONE 服务合约 PDF 运价适配器 — 设计 (MVP)

日期: 2026-05-29
分支: feature/step1-review-desk（下一轮开发）
关联记忆: step1-pdf-one-contract-adapter / step1-true-requirement-make-not-import / mvp-minimal-scope-remind

## 背景与目标

客户（阪急阪神）的海运成本文件除 Excel 外，还有**船司服务合约 PDF**。样例 = ONE(Ocean
Network Express) 给 HANKYU HANSHIN EXPRESS (USA) 的 **372 页 FMC 服务合约 LAX0751N25 Amd.93**。

福山已确认运价输入格式边界 = **Excel / 图片 / 邮件(.msg) / PDF** 四种，其中 **PDF 是当前唯一缺口**
（Excel、图片、邮件均已支持）。pptx 确认**非运价输入**（那份 pptx 是需求说明书）。

**目标**：把 ONE 合约 PDF 里的 **FCL 运价 + 可用元数据 + 附加费"含哪些"清单文本**，经现有"做表"
（RateSheetBuilder）流程抽取 → 预览审核 → 入库 `FreightRate`。**文字版 PDF 纯解析，不依赖 vLLM。**

## 关键决策

1. **抽取库 = `pdfplumber`(pip)**。自带在 venv、不依赖系统二进制（部署干净，不踩 poppler 系统依赖坑）；
   提供词/字符 x 坐标，对脏行/编码格子按列切分比纯文本稳。
2. **接入"做表"的 sea 进料口**；**air 不碰**（本轮明确不做 air PDF）。
3. **复用现有链路**：adapter 产 `parsed_rows`（kmtc 兼容形态）→ orchestrator → `_normalize_sea`
   → 预览台 → `commit_ocean_rows`（写 `FreightRate`）。
4. **v1 不改表结构**：`FreightRate` 现有列已够用（`container_45 / valid_from / valid_to /
   rate_level / service_code / via / rmks / remarks`），无需 alembic 迁移。
5. **脏行不硬猜**：编码(`R5/2400`)/RF(冷藏)/塌列格子 → 保留原始文本 + `needs_review=true`，
   交审核台人工改（做表流程本就有勾选 + 行内编辑）。
6. **附加费金额不在文档中 → 不抽**；只把"本价已含 AGS/ALM/OBS/…/PSS"这串清单文本落 `remarks`。

## 架构 / 数据流

```
ONE 合约 PDF
   │  orchestrator.add_file: ext==".pdf" 分支(仅 sea 模板)
   ▼
detect_and_parse_pdf(file_path, db)            # 按内容签名分流，留多船司扩展位
   │  认到 "SERVICE CONTRACT" + "ONE/Ocean Network Express"
   ▼
parse_one_contract_pdf(file_path, db)          # adapters/one_contract_pdf.py
   │  pdfplumber 抽词(带坐标) → 状态机扫 COMMODITY 块
   ▼
{"parsed_rows":[{carrier_name:"ONE", origin_port_name, destination_port_name,
                 container_20gp/40gp/40hq/45, valid_from, valid_to, rate_level,
                 service_code, via, is_direct, commodity, surcharge_note, needs_review}...],
 "carrier_code":"ONE", "warnings":[...]}
   │  orchestrator._normalize_sea(追加透传新字段)
   ▼
预览台(勾选/行内编辑/needs_review 高亮)  →  commit_ocean_rows(追加写新字段) → FreightRate(status=active)
```

## 组件（各自单一职责）

- **`adapters/one_contract_pdf.py` · `parse_one_contract_pdf(file_path, db)`**：pdfplumber 取词
  + 状态机解析 commodity 块，产 `parsed_rows`。唯一懂 ONE 合约版式的地方。
- **`rate_parser_pdf.py` · `detect_and_parse_pdf(file_path, db)`**（与 Excel 的 `rate_parser.py` 平行）：
  PDF 格式分流，现仅路由 ONE，预留别家船司合约分支。
- **`orchestrator.add_file`**：新增 `.pdf` 进料分支（沿用现有"单文件失败不崩、标状态"约定）。
- **`_normalize_sea` + `commit_ocean_rows`**：各**纯追加**几个字段透传（`valid_from/to`、
  `container_45`、`rate_level`、`service_code`、`via`、`is_direct`）；老行 `.get()` 取不到为 None，无影响。
- **港名清洗**：复用/抽取 kmtc `_clean_and_resolve_port` 风格（去括号、取逗号前段），
  叠加现有 `activator_mappers._resolve_port`（双语港名已修）。

## 解析状态机

pdfplumber 逐页取词（带 x 坐标）。**先定位运价段**：第 6 节 "CONTRACT RATES OR RATE SCHEDULE(S)"
之后才开始扫，跳过前面法律条款（省时 + 避免误抽）。状态机：

```
"NNN) COMMODITY :"            → 开新块，记 commodity 文本
"ORIGIN :" / "ORIGIN VIA :"   → 记起运港 / 中转
列头行(Destination|Cntry|Destination Via|Cntry|Term|Type|Cur|20'|40'|40HC|45'|Note)
                              → 锁定各列 x 坐标(后续数据行按坐标切)
数据行                         → 按列 x 坐标切字段；纯数字→入价列；编码/RF/塌列→raw+needs_review
"< NOTE FOR COMMODITY >"      → 解析 "valid from/to YYYYMMDD" + "inclusive of …" 附加费清单 → 收束本块
"BLANK" / 跨页重复列头         → 跳过
```

## 字段映射 → FreightRate

| 合约内容 | FreightRate 列 |
| --- | --- |
| 起运港 / 目的港（清洗后经 _resolve_port） | origin_port_id / destination_port_id |
| 船司 ONE（字典已有 code=ONE） | carrier_id |
| 20'/40'/40HC/45' 价 | container_20gp / 40gp / 40hq / container_45 |
| 币种 | currency = "USD" |
| 块生效起止("valid from 20260203 to 20260228") | valid_from / valid_to |
| 费率码 R5/R2 | rate_level（不解码语义，存码 + raw） |
| Service Lane(EC3/TPE1) | service_code |
| Destination Via / Direct·Call | via / is_direct |
| commodity 描述 | rmks |
| "本价含 AGS/ALM/OBS/…/PSS" 附加费清单 + 合约号 | remarks |

合约级元数据（合约号 LAX0751N25 Amd.93、MQC、carrier、整体生效日 16 Mar 2026）
→ 落 `ImportBatch`（source_file + diff_summary JSON），file_type=ocean。

## 错误处理与脏数据

- **干净数字行**（如夏威夷 5240/7100/7200）→ 正常解析入价列。
- **编码/异常格子**（`R5/2400`、`RF` 冷藏、塌列）→ **不硬猜、不崩**：保留原始文本 + `needs_review=true`，
  审核台人工处理。
- **港名清洗**："HONOLULU, HI"→"HONOLULU"、"DALIAN, LIAONING, CHINA(CY)"→"DALIAN"；
  港口不在字典 → 现有 commit 逻辑 `skipped_unresolved` 计数（数据完整性，非缺陷）。
- **非 ONE / 认不出版式的 PDF** → 返回 `{"error":...}`，orchestrator 标该文件 skipped 并把原因显示给用户。
- **372 页性能**：只扫运价段，跳过法律前言。

## 本版最小收口（MVP 边界 — 面向客户必须说明）

1. **仅支持 ONE 一家合约版式**；别家船司合约 PDF 版式不同，各需新适配器（同 Excel 每家一个 adapter）。
2. **不抽附加费金额**（文档没有）；只存"本价含哪些附加费"清单文本。
3. **air PDF 不支持**（本轮明确不碰）。
4. **编码/RF/异常运价格子不自动解码**，标 needs_review 交人工。
5. **港口不在字典 → 该行跳过并计数**（不是 bug，是字典完整性）。
6. **.msg 进料口、各进料口统一化**不在本轮范围。

## 测试策略 (TDD)

- **单元**：解析状态机喂构造文本（1 个干净块 + 1 个编码块）→ 断言 parsed_rows 字段
  （干净块出数字价、编码块标 needs_review）。
- **单元**：港名清洗（"HONOLULU, HI" / "DALIAN, LIAONING, CHINA(CY)" 能解析到港口）。
- **集成**：跑真实 ONE PDF（本地）→ 断言解析出 >0 行，且干净数字块解析率达标
  （具体阈值实现时按真实文件标定）。
- ⚠️ **真实合约 PDF 不入仓**（2.9MB + 客户机密）；用**裁剪文本 fixture**，真实文件仅本地 dev 验证。

## 风险 / 开放（非阻塞）

- pdfplumber 列坐标在跨页/合并单元格时可能漂移 → 用列头 x 坐标 + 容差匹配；不行再降级到整行正则。
- 费率码 `R5/2400` 语义未知 → v1 存 `rate_level` + raw，不解码（需要时再找 ONE 费率码表）。
- 合约整体生效日(16 Mar) 与块级 valid 日期可能不一致 → 以**块级为准**入 valid_from/to，合约级入 batch。
