# 统一运价入库口 — 设计文档（2026-06-05）

## 背景

step1 的代码是「先做下游、后补上游」长出来的，现在有**两个数据入库口**：

- **口①　做表页**（`RateSheetBuilder` → `/rate-sheet/*`）：审核台有 `下载` 和 `入库`
  两个出口。`入库` 走 `db_writer.commit_ocean_rows` / `commit_tier_rows` 从内存 session
  **直接落库**。这是后补上游时加的第二入口。
- **口②　运价导入页**（`RateUpload` → `/rate-batches/upload` + activate）：上传 Excel →
  建 draft → `activator.activate` → adapters 落库。这是原本的下游正口。

邓老师会议要求：**入库统一在运价导入页做**。流程改为——用户把杂七杂八的数据在做表页
生成运价表 → 本地调整 → 回运价导入页导入回去形成数据。即砍掉口①入库，做表只产表。

## 现状盘点：三类运价的「回流」可行性

「回流」= 做表生成的表，能否被导入页的 adapter 重新认出并正确落库。逐类验证结论：

| 运价类型 | 生成表 | 导入页能否回流 | 关键事实 |
|---|---|---|---|
| 海运 FCL | 填 `sea_blank.xlsx`（3 sheet 齐全） | ✅ 结构可行 | `OceanAdapter` 正是读这套模板、认 20FT/40FT 双行。**但** 它靠文件名含 `ocean` 才自动识别，生成文件名 `sea_rate_sheet_filled.xlsx` → 不会自动路由 |
| 空运周报 Market Price | 填 `air_blank.xlsx` | ✅ 已如此 | `AirAdapter` 按文件名含 `air` 自动认；`db_writer` 本就**跳过周报**（`skipped_weekly`），周报从来只走导入口，天然对齐 |
| 空运档位 EES/唯凯重量档 | 程序生成档位表 | ❌ **无任何导入路径** | adapters/normalizers/activator 里 grep `air_tier` 全空。入 `AirTierRate` 的唯一通道就是口①的 commit；而 **step2 投标（`rate_matcher`/`rate_repository`）依赖 `AirTierRate`** |

**共性坑——往返有损**：口① commit 从内存整行落库（带 currency / 生效日 / carrier /
cargo_class / rate_level 等）；导入口只看文件里的列。而生成表里**没有这些列**：

- 海运缺：currency、valid_from、valid_to、rate_level、service_code；且模板把
  40GP 与 40HQ 合成一行 `40FT/40HQ`，往返无法区分两个箱型价。
- 空运档位缺：currency、effective_from、effective_to、carrier、cargo_class、packing、density
  （step2 日本段 NRT/JPY 正靠这些）。

下载→人工调→重新导入会丢掉这些字段、回落默认值（如币种丢成 CNY）。

## 本次会议拍板的决策

1. **全做**：补一个空运档位（air-tier）导入适配器，让三类运价都能从导入页回流。
2. **补列保证不丢**：给生成的运价表补齐 DB 需要的字段列，往返无损、人工仍可调。
3. **40GP/40HQ 拆开**：海运生成表把两个箱型分开（不再合并），往返保留两个箱型价。
4. **顺手收敛老入库路径**：把 `import_parsed_rates`（`/rates/upload/confirm` +
   `/ai/confirm` 共用的直写）收敛到 `draft→activate` 一条管道。

## 范围拆分：两期

两块活相互独立，分两期，各自独立验收：

- **Phase 1（核心，直接满足会议诉求）**：做表停止入库 + 三类运价从导入页无损回流。
- **Phase 2（技术债收敛）**：把老入库直写路并入 `draft→activate` 单管道。

---

## Phase 1 设计：做表只产表，导入页无损回流

### 数据流（改造后）

```
做表页：杂料上传 → AI/parser 抽取 → 审核台勾选/编辑 → [下载]（唯一出口，不入库）
                                                          ↓ 人工本地调整 xlsx
运价导入页：上传 xlsx → 内容识别 adapter → 建 draft → 预览/diff → activate → 落库
            ├─ 海运 sea 表      → OceanAdapter（扩展读新列 + 40GP/40HQ 双列）→ FreightRate
            ├─ 空运周报 air 表  → AirAdapter（已通；补读 currency 列）        → AirFreightRate
            └─ 空运档位 tier 表 → AirTierAdapter（新）                         → AirTierRate
```

### A. 做表页瘦身 —— 去掉第二入口

- `frontend/src/pages/RateSheetBuilder.tsx`：删 `入库` 按钮、`handleCommit`、
  `showCommit` 逻辑；下载后加引导文案「请到运价导入页导入此表形成数据」。
- `frontend/src/services/api.ts`：删 `rateSheetApi.commitToDb`。
- `backend/app/api/v1/rate_sheet.py`：删 `/{session_id}/commit` 端点与
  `_has_ocean_price`。
- `backend/app/services/step1_rates/sheet_builder/db_writer.py`：其字段映射是新适配器的
  参照，迁移完成后**删除**（连同相关测试改写）。
- i18n：移除 `rateSheet.commit*` 文案；新增引导文案，zh/ja/en 三份齐。

### B. 生成表补列 —— 往返无损 + 40GP/40HQ 拆开

- `sheet_builder/template_registry.py` + `template_filler.py`：
  - **海运** `_fill_sea`：用模板空列（13–16 区段）补写 currency / valid_from /
    valid_to / rate_level / service_code；把 `_SEA_CONTAINER_ROWS` 由
    `("20FT","freight_20"),("40FT/40HQ","freight_40")` 改为
    **`20FT / 40GP / 40HQ` 三行**（每条运价展开为 3 行 container-label 块，沿用现模板
    “每箱型一行”的风格，是对现结构最小的改动）。需求是「40GP 与 40HQ 分别表示、往返不丢」；
    行/列的最终物理形以实现计划锁定，并以 D 的 OceanAdapter 回归为闸门。
  - **空运档位** `_build_tier_sheet`：表头补 currency / effective_from /
    effective_to / carrier / cargo_class / packing / density 列，逐行写入。
  - **空运周报** `_fill_air`：补 currency 列（解决 `air_blank` 无 Surcharges sheet
    导致币种回落 CNY 的坑）。
- 生成文件命名：海运改为含 `ocean`（如 `ocean_sea_rate_sheet_filled.xlsx`）以便
  OceanAdapter 文件名识别；或统一改走内容识别（见 E），命名仅作可读性。

### C. 新增空运档位导入适配器（工作量大头）

- `entities.py`：新增 `Step1FileType.air_tier`；`ParsedRateRecord` 增加档位字段
  （tier_prices、cargo_class、packing、density、carrier、effective_from/to、currency 等），
  新 `record_kind = "air_tier"`。
- `adapters/air_tier.py`（新）：
  - `detect()`：**按 sheet 表头内容识别**——存在表头形如
    `Origin/Destination/Service + 若干 \d+KG 列` 的 sheet 即认（不靠文件名，因为档位
    文件名也含 `air` 会被 AirAdapter 抢）；非档位文件安全返回 False。
  - `parse()`：把档位表每行解析为 `ParsedRateRecord(record_kind="air_tier")`，
    KG 列归一为 `tier_prices: {int(kg): float}`，读 B 补的元数据列。
  - 注册到 adapter 列表，**优先级高于 AirAdapter**（先于其 detect 被尝试）。
- `activator_mappers.py`：`to_air_tier_rate(record, batch_uuid) → AirTierRate`
  （参照 `db_writer.commit_tier_rows` 的字段映射 + 默认值）。
- `activator.py`：`_FILE_TYPE_MAP` 加 `air_tier → ImportBatchFileType.air_tier`
  （枚举已存在）；dispatch 循环加 `kind == "air_tier"` 分支收集 `AirTierRate`；
  supersede 仅作用于 `air_tier` 批次（与现 db_writer 语义一致，不碰 weekly air）；
  `imported_detail["air_tier_rates"]` 计数。

### D. 扩展 OceanAdapter

- `adapters/ocean.py`：
  - 读 B 给海运补的列（currency / valid_from / valid_to / rate_level / service_code）。
  - 适配 40GP/40HQ 拆开后的列形（双列或三行），分别落 `container_40gp` /
    `container_40hq`。⚠️ 这是成熟复杂解析器，改动**必须配回归测试**（用三份真实费率
    文件抽样对数）。

### E. 导入页识别

- 主路：靠 C 的内容识别自动路由（海运/空运周报/空运档位三类各自 detect）。
- 兜底：`RateUpload` Excel tab 暴露 `parser_hint` 下拉（auto / ocean / air /
  air_tier），传给 `/rate-batches/upload`，识别不确定时人工指定。
- `BatchesPanel` 的 diff：air_tier 是另一张表，对 FreightRate 的 diff 无意义 →
  air_tier 批次跳过 diff（或仅展示行数预览）。

### F. 测试（round-trip 为核心）

- 三类各一条 round-trip 测试：做表生成 → 下载 xlsx → 经导入 adapter 重新解析 →
  断言关键字段（含 currency / 生效日 / 40GP≠40HQ / tier_prices）与原始一致、无丢失。
- air_tier 适配器单测：detect 命中/不命中、parse 字段映射、稀疏档位。
- activator air_tier 入库单测：建批次、supersede 仅档位、计数。
- OceanAdapter 回归：三份真实海运费率文件抽样对数不退化。

---

## Phase 2 设计：收敛老入库路径（技术债）

### 现状

- `/rates/upload/parse` + `/rates/upload/confirm`（`rates.py`）与 `/ai/confirm`
  （`ai_parse.py`）**共用** `rate_parser.import_parsed_rates`：解析结果缓存在内存
  `_parse_cache`，confirm 时直写 DB。与 `draft→activate` 是两套写库逻辑（各自的
  supersede / ImportBatch 语义）。RateUpload 的 wechat tab 正用 `/ai/confirm`，在跑 demo。
- `/import/tariffs`（`import_service.py`）写老表 `Tariff`，与主流程脱钩。

### 方案

- 把 AI/邮件/微信解析结果统一转成 `DraftRateBatch` / `ParsedRateRecord`，confirm
  改走 `activator.activate`，删除 `import_parsed_rates` 直写分支。统一 supersede 与
  ImportBatch 语义，入库口逻辑单一。
- `/import/tariffs` + `import_service`：确认无前端在用后**下线**（或标 deprecated）；
  若仍需保留，独立评估，不并入本期。
- ⚠️ 行为保持型重构，回归风险集中在 **AI 解析路（demo 在用）**，需对 email / wechat /
  inbox 三条解析→入库做回归。

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| OceanAdapter 加列/拆箱型引入回归 | 改动配三份真实海运文件抽样对数回归测试 |
| air_tier 与 air 文件名都含 `air`，detect 冲突 | air_tier 按 sheet 内容识别 + 优先级高于 air |
| 往返仍有损（漏补某字段） | round-trip 测试逐字段断言；以 db_writer 现有落库字段为「不丢清单」 |
| Phase 2 动到在用的 AI 解析路 | 拆为独立第二期；email/wechat/inbox 回归先行 |
| 做表内存 session 重启即失 | 不变（demo 可接受）；下载是唯一持久产物，符合新流程 |

## 工作量与里程碑

- **Phase 1**：约 2–3 人日。大头在 C（档位适配器接线）+ D（OceanAdapter 加列+拆箱型+回归）。
  A/B/E 小改，F 占稳。**先交付，直接满足会议诉求。**
- **Phase 2**：约 1–2 人日。`import_parsed_rates` 收敛 + AI 解析路回归。**后置交付。**

## 验收标准

- 做表页无任何入库入口；下载产出的运价表，原样上传运价导入页能成功落库。
- 三类运价（海运 FCL / 空运周报 / 空运档位）round-trip 后关键字段无丢失，
  40GP 与 40HQ 可区分，币种/生效日保留。
- step2 投标仍能从 `AirTierRate` 取到档位价（链路不断）。
- 全量 pytest 通过；三份真实海运费率文件抽样对数不退化。
- （Phase 2）AI 解析路 email/wechat/inbox 入库行为与改造前一致。
