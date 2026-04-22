# Step2 入札対応 — Customer A 端到端闭环 架构任务单

- **版本**: v1.0（Customer A 专用；Customer B/E/Nitori 仅留扩展点说明）
- **发布日期**: 2026-04-22
- **作者**: 架构大师
- **业务依据**: `docs/Step2_入札对应_业务需求_20260422.md`（499 行，60 条业务规则，23 条待确认）
- **上游数据依据**: `docs/Step1_Air解析器_架构任务单_20260422.md`（Step1 Air 已交付）、`backend/app/services/step1_rates/entities.py:54-165`（Step1RateRow 字段清单）
- **黄金样本**: `资料/2026.04.02/Customer A (Air)/Customer A (Air)/{2-①.xlsx, 2-②.xlsx, 2-④.xlsx, 1-①.msg … 1-③.msg}`
- **读者**: 开发大师（按本单直接动手）、测试大师（按"验收点"写用例）、监工（抽查 file:line）
- **红线**:
  1. 不得动 Step1 已交付代码（`backend/app/services/step1_rates/**`）；Step2 只能通过 `RateRepository` 接口消费
  2. 不得重新发明批次机制（`import_batch.status` / `effective_from/to` 保持不变）
  3. 不得在 query_rate 里调 AI 编价（禁止 RAG 幻觉；必须命中 DB 才返数）
  4. 不得保留旧 `pkg_parser.py / pkg_filler.py / rate_db.py` 的语义（这三个文件是去年 Demo 硬编码 stub，Step2 独立目录重写）
  5. 禁用 pandas 写 Excel（遵循 Step1 既有约定，使用 `openpyxl.load_workbook` 改单元格）
  6. Q1-Q7 未答时，使用本文件 §10 的"默认假设值"推进；楢崎回答后开发大师按回答值回修

---

## 0. 真实样本采样结果（必须先看）

采样命令：`.venv/bin/python -c "import openpyxl; wb=openpyxl.load_workbook('资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx', data_only=True); …"`。

### 0.1 文件结构

- 单 sheet `見積りシート`，`max_row=41, max_col=11`
- **无任何合并单元格**（与 Customer B/Nitori 完全不同，实现可简化）
- B1 = `"1月"`（入札期间；**非 B2-B3 标准位置**，解析器要单独读）

### 0.2 五段表头行（全部实测）

| 段号 | 表头行 | E 列币种列头原文 | 币种归一化 | 数据起止行 | 発地原文（B 列，数据行首列） |
|---|---|---|---|---|---|
| 1 | R3 | `'単価 (円/kg)'` | JPY | R4-R10 | `'日本  (成田)'` |
| 2 | R12 | `'単価 (CNY/kg)'` | CNY | R13-R19 | `'中国  (上海)'` ← 本项目唯一"本节点段" |
| 3 | R21 | `'単価 (ユーロ/kg)'` | EUR | R22-R23 | `'オランダ\n  (アムステルダム)'` |
| 4 | R25 | `'単価 （USD/kg)'`（全角括号） | USD | R26-R32 | `'台湾  (台北)'` |
| 5 | R34 | `'単価 （USD/kg)'` | USD | R35-R37 | `'韓国  (インチョン)'` |

- **R11/R20/R24/R33/R39-R41 是空白分隔行**（B-C-E 全 None）→ 段分隔检测依据
- **R38 整行**：`B38 = '※韓国→日本→ブラジルなどトランジット回数を抑え安いルートでも可'` → ICN 段的**客户硬约束原文**，必须保留原样、不当航线

### 0.3 PVG 段（本节点）数据行实测

| 行 | C 列（着地）原文 | 费用类型判定 | 客户已填（E 列） | S/R 版（2-④.xlsx）E 列目标值 |
|---|---|---|---|---|
| R13 | `'アメリカ  (アトランタ)\nAIR FREIGHT COST'` | AIR_FREIGHT | 0 | 49 |
| R14 | `'アメリカ  (アトランタ)\nLOCAL DELIVERY COST'` | LOCAL_DELIVERY | 0 | 0（保留原值）|
| R15 | `'アメリカ\n  (マイアミ)'` | AIR_FREIGHT（无后缀按默认）| 0 | 54 |
| R16 | `'オランダ  (アムステルダム) \nAIR FREIGHT COST'` | AIR_FREIGHT | 0 | 41 |
| R17 | `'オランダ  (アムステルダム) \nLOCAL DELIVERY COST'` | LOCAL_DELIVERY | 0 | 0（保留）|
| R18 | `'オーストラリア\n (シドニー)'` | AIR_FREIGHT | 0 | 25 |
| R19 | `'台湾\n(台北)'` | AIR_FREIGHT | 0 | 13 |

- **业务事实**：PVG 段 7 行中，5 行需填单价（ATL/MIA/AMS/SYD/TPE），2 行 LOCAL_DELIVERY 必须写 `'－'` 到 F/G 列（客户模板 R14/R17 F/G 原值就是 `'－'`）
- **2-②.xlsx（cost 版）PVG 段 H 列为空**；**2-④.xlsx（S/R 版）PVG 段 H 列全部写 `"ALL-in"`** → 业务语义见业务文档 §9 第 2 条

### 0.4 记入例行剔除规则

- R4（NRT 段首行）H 列 `"※記入例\nCarrier: 5X\nRoute: NRT-ANC-ATL"`、R5 H 列 `"※記入例\n左記は750kg/shipmentの貨物を…"`
- 规则：**只要 G 列或 H 列含 `"記入例"` 或 `"※"` 前缀 → 该行标为 `is_example=True`**
- NRT 段不是本节点段，理论上不会进入填入流程；但 parse 必须识别并标记

### 0.5 与业务文档 §3.4 偏差

- 业务文档说"Customer A 第 3 行是表头"→ **错**。Customer A 有 **5 个表头行**（每段独立）。R3 只是第一段的表头。架构必须按"多段独立表头"设计。
- 业务文档 §2.2 说"入札期间在顶部区"→ 实测在 **B1** 单元格，不是某个命名标签

---

## 1. 现有代码审计（动手前必读）

### 1.1 `backend/app/services/pkg_parser.py`（289 行）

- **判定：删除，不复用**。原因：
  - 该文件是去年 Demo 硬编码产物，`ORIGIN_CODE_MAP / DEST_CODE_MAP`（L58-84）仅覆盖 Customer A 5 段、7 个着地，缺乏扩展性
  - `_clean_destination`（L103-112）用正则剥"AIR FREIGHT COST / LOCAL DELIVERY COST" 把原文损坏，与业务文档 §9-3 "原文保留"相悖
  - 单 sheet `wb.active`（L174）假设仅对 Customer A 成立，Customer E/Nitori 多 sheet 会失效
  - 期间提取仅读 B1（L178），耦合死
- **迁移策略**：新建 `backend/app/services/step2_bidding/customer_profiles/customer_a.py`，**重新实现**，不 import 旧文件
- **删除时机**：本任务单 T-B11 完成后由开发大师 `git rm`；在此之前旧 `/api/v1/pkg` 路由继续跑，保底 Demo

### 1.2 `backend/app/services/pkg_filler.py`（227 行）

- **判定：删除，不复用**。原因：
  - 硬编码 E/F/G/H 四列（L166-183），Customer B 132 列、Nitori 多 sheet 根本不在这个坐标系
  - 费率来源 `from app.services.rate_db import AirRate, query_rate`（L16）是本地硬编码字典，**完全绕开了 Step1 入库**
  - `shutil.copy2` 打开 + `wb.save`（L71/97），保真度尚可但无差异报告
- **迁移策略**：新建 `backend/app/services/step2_bidding/pkg_filler.py`，只保留 `openpyxl.load_workbook` → 改单元格 → `wb.save` 这个骨架思路，其它重写

### 1.3 `backend/app/services/rate_db.py`（346 行）

- **判定：删除，不复用**。原因：
  - 硬编码 30+ 条 Customer A 的销售价（`RATE_DB` L29-293），**这是"AI 伪造数据" 的典型坑**，Step2 v1.0 必须切断此链路
  - Step1 入库后，费率来源只应该是 `air_freight_rates / air_surcharges / freight_rates / lcl_rates` 四张表
- **迁移策略**：新建 `backend/app/services/step2_bidding/rate_repository.py`（纯 DB 查询，无硬编码）

### 1.4 `backend/app/services/ai_client.py`（152 行）

- **判定：保留，复用 `chat()` 和 `extract_json()`**。原因：
  - Claude / Qwen 双 provider 回退已就绪（L14-20），Step2 AI 列识别可直接用
  - `chat_with_image` Step2 用不到（本轮不做 OCR）
- **Step2 用法**：
  - `parse_pkg` 的列识别/表头定位一旦"规则法失败" → fallback 调 `ai_client.chat(system_prompt, user_message)`，让 Claude 返回 JSON 列映射
  - temperature=0.0，max_tokens=2048
  - **不得用于编价**（只做列识别 / 客户约束摘要）

### 1.5 `backend/app/api/v1/pkg.py`（146 行）

- **判定：保留旧路由共存，新增 `/api/v1/bidding` 路由**。原因：
  - 旧路由前端 `frontend/src/pages/PkgAutoFill.tsx` 仍在用（L485 行级存在），**Demo 当天若新路由挂了旧路由可兜底**
  - 新路由路径独立，无 URL 冲突
- **迁移时机**：Demo 过后（5/14+）再迁 PkgAutoFill.tsx 前端；本任务单不动前端代码

### 1.6 Step1 已交付可消费接口

- `backend/app/services/step1_rates/entities.py:54` `Step1RateRow`（45 个字段，含 `airline_code/effective_week_start/price_day1..7/record_kind/currency/extras`）
- `backend/app/models/air_freight_rate.py:12` `AirFreightRate`（物理表 `air_freight_rates`，索引 `origin+destination+effective_week_start`）
- `backend/app/models/air_surcharge.py:12` `AirSurcharge`（`air_surcharges`，索引 `effective_date+airline_code`）
- `backend/app/models/import_batch.py:18` `ImportBatchStatus = {draft, active, superseded}`（Step2 检索**只用 `status == active`** 的批次）
- `backend/app/services/rate_batch_service.py:160` `activate_rate_batch`（把批次切到 active；Step2 不动这里）

### 1.7 "站在 Step1 已交付地基上，Step2 技术地基要补什么"

| 补什么 | 理由 |
|---|---|
| RateRepository（跨三张物理表的查询层） | Step1 只 parse+入库，无检索 API；Step2 必须有"按 origin/dest/effective_on 过滤 active 批次记录"的薄查询层 |
| PKG 适配器注册表（按客户分流） | Customer A/B/E/Nitori 解析规则差异量级 10 倍（业务文档 §9-3），必须按客户独立 adapter（同 Step1 三份文件三 adapter 的做法） |
| 客户识别器 | 上传时需要判定"这是哪家客户"；默认"营业手选 + 发件人域名兜底"（Q6） |
| 销售价计算器（Markup） | Step1 只入成本价，Step2 填入客户 PKG 必须是销售价；Q2 加价规则待答，先用"× 1.15"默认值 |
| 填入报告 + 审核状态流 | Step1 只产 ParsedRateBatch，Step2 要产"每行待审核项 + 客户硬约束提醒 + 追溯链" |
| 人工审核 API | Step1 是后端服务，Step2 要暴露 `/api/bidding/{id}` GET/PATCH 给前端审核页 |

---

## 2. 数据流设计（全流程一张图）

```
[上传接口]
  POST /api/v1/bidding/pkg
    multipart: file (.xlsx), customer_code (可空), period_hint (可空), uploader

      │ 1. 保存到 settings.upload_dir/bidding/{bid_id}/original.xlsx
      │ 2. 运行 CustomerIdentifier（§7）→ customer_code
      │ 3. 查 CustomerProfileRegistry → 得 CustomerAProfile
      ▼
[Step 2.1 PKG 接收]  service.receive_pkg()
  返回 BiddingRequest(id=bid_id, customer='customer_a', period='2026-01',
                     status=PARSING, file_path=..., uploader=...)
      │
      ▼
[Step 2.2 PKG 解析]  CustomerAProfile.parse(path) → ParsedPkg
  - 用 openpyxl(data_only=True)
  - 扫 41 行识别 5 段表头（含币种）
  - 每段数据行 → PkgRow(row_idx, section_code, origin_text, origin_code,
                         destination_text, destination_code, cost_type,
                         currency, volume_desc, existing_price, is_example,
                         client_constraint_text)
  - 段级 `客户硬约束原文`（如 R38）归入 section_level_remarks
  - 输出 ParsedPkg(customer='customer_a', sections=[...], rows=[...],
                  skip_reasons={row: reason}, warnings=[])
      │
      ▼
[Step 2.3 费率检索]  RateMatcher(repository).match(row) for each row
  - 预过滤：row.section_code != 'PVG' → 标 skip_reason='non_shanghai_leg'
  - row.is_example → 标 skip_reason='example_row'
  - cost_type == 'LOCAL_DELIVERY' → 标 skip_reason='local_delivery_manual'（v1.0 不查，直接保留'－'）
  - 主查询：repository.query_air_weekly(origin='PVG', destination=row.destination_code,
                                       effective_on=period_etd, currency=row.currency)
      → list[Step1RateRow] 候选
  - Surcharges 叠加：同 active 批次里取 airline_code ∈ 候选 airline_codes 的 surcharge
      组合成 QuoteCandidate(base_price, myc, msc, total_cost_price, airline, via, remarks_from_step1)
  - 排序（Q默认: 最低价优先）
      │
      ▼
[Step 2.4 自动填入]  MarkupApplier.apply + PkgFiller.fill
  - 对每个 row 取 top1 candidate
  - MarkupApplier: sell_price = cost_price × 1.15 (Q2 默认；ceil 到整数 CNY)
  - 若无候选：sell_price=None, status='no_rate'
  - 若客户约束冲突（"只走 NH" × 候选无 NH）：status='constraint_block'
  - PkgFiller 打开 original.xlsx 副本：
      * 只改 PVG 段 R13-R19，且仅 status=='filled' 的行
      * E 列 = sell_price（数字）
      * F 列 = carrier_route.lead_time_text（文本）
      * G 列 = carrier_route.carrier_text（文本；LOCAL_DELIVERY 写'－'）
      * H 列 = "ALL-in"（仅 S/R 版；cost 版为空；见 §8.2）
      * **不覆盖非 PVG 段、不覆盖 is_example、不覆盖 existing_price != 0**
  - 生成两份输出：
      * cost_版.xlsx（用 cost_price，H 列空）
      * sr_版.xlsx（用 sell_price，H 列"ALL-in"）
  - 返回 FillReport(bid_id, rows=[PerRowReport(row_idx, status, cost_price,
                    sell_price, candidate_source={batch_id, record_id},
                    constraint_hit, confidence)], files={'cost': path, 'sr': path})
      │
      ▼
[Step 2.5 营业审核]  status=AWAITING_REVIEW
  - GET /api/v1/bidding/{id} → 返回 ParsedPkg + FillReport
  - PATCH /api/v1/bidding/{id}/rows/{row_idx}  { sell_price, carrier_route, ... }
      → 修改保存，重新渲染 sr_版.xlsx
  - GET /api/v1/bidding/{id}/download?variant=sr  → 下载
  - POST /api/v1/bidding/{id}/submit → status=SUBMITTED（business finalize）
  - validate_rate: 对比上期同航线价（Q11 默认 ±30% 标黄）
```

---

## 3. 文件级改动清单

### 3.1 新增文件（全部在 `backend/app/services/step2_bidding/` 下，对齐 Step1 风格）

| 文件 | 行数（估） | 作用 |
|---|---|---|
| `__init__.py` | 10 | 导出公共入口 |
| `entities.py` | 150 | dataclass: BiddingRequest / ParsedPkg / PkgSection / PkgRow / QuoteCandidate / PerRowReport / FillReport / CostType / BiddingStatus |
| `protocols.py` | 40 | Protocol: `CustomerProfile`（parse/fill 两方法）、`RateRepository` |
| `customer_profiles/__init__.py` | 20 | CustomerProfileRegistry + identify_customer |
| `customer_profiles/customer_a.py` | 300 | Customer A parse + fill 实现 |
| `customer_profiles/customer_b_stub.py` | 30 | 仅留 detect+抛 NotImplementedError，架构扩展点 |
| `customer_profiles/customer_e_stub.py` | 30 | 同上 |
| `customer_profiles/nitori_stub.py` | 30 | 同上 |
| `rate_repository.py` | 200 | 三张物理表的薄查询层（只读） |
| `rate_matcher.py` | 180 | 航线 → 候选费率，含 Surcharges 叠加 |
| `markup.py` | 60 | 成本→销售加价（Q2 默认 ×1.15） |
| `validator.py` | 100 | 与上期对比、异常波动标记（Q11 默认 ±30%） |
| `service.py` | 250 | 5 步编排入口，状态机，会话持久化 |
| `customer_identifier.py` | 80 | 客户识别（Q6 默认: 营业手选 + 文件特征兜底） |

### 3.2 新增 API 路由

| 文件 | 行数 | 内容 |
|---|---|---|
| `backend/app/api/v1/bidding.py` | 200 | 7 个 endpoint，详见 §9 |
| `backend/app/api/v1/router.py:10-21` | 修改 | 追加 `from app.api.v1.bidding import router as bidding_router` + `router.include_router(bidding_router)` |

### 3.3 新增数据表（Alembic 迁移）

| 表 | 作用 | 是否 v1.0 必须 |
|---|---|---|
| `bidding_requests` | 入札流水线记录（bid_id, customer_code, period, status, file_path, uploader, created/updated） | **是** |
| `bidding_row_reports` | 每行填入/审核状态（bid_id FK, row_idx, section_code, status, cost_price, sell_price, airline_code, candidate_batch_id, overridden_by, overridden_at） | **是** |

- 迁移脚本：`backend/alembic/versions/20260423_0001_step2_bidding_models.py`（紧邻 Step1 的 `20260421_0001`）
- **不新增索引以外的字段到 `air_freight_rates / air_surcharges`**（Step2 只读 Step1 表）
- **不对 `import_batches` 表加字段**

### 3.4 删除文件（T-B11 最后统一 `git rm`，在前端迁移后）

- `backend/app/services/pkg_parser.py`
- `backend/app/services/pkg_filler.py`
- `backend/app/services/rate_db.py`

### 3.5 不动的文件（本轮禁止修改）

- `backend/app/services/step1_rates/**`（全部）
- `backend/app/models/{air_freight_rate.py, air_surcharge.py, import_batch.py, freight_rate.py, lcl_rate.py}`
- `backend/app/services/rate_batch_service.py`
- `frontend/src/**`（本任务单只定 API 契约，不写前端）
- `backend/alembic/versions/20260421_0001_step1_rate_models.py`

---

## 4. entities.py 接口契约（dataclass 签名）

```python
# backend/app/services/step2_bidding/entities.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class BiddingStatus(str, Enum):
    CREATED = "created"
    PARSING = "parsing"
    PARSED = "parsed"
    QUOTING = "quoting"
    QUOTED = "quoted"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTED = "submitted"
    FAILED = "failed"


class CostType(str, Enum):
    AIR_FREIGHT = "air_freight"
    LOCAL_DELIVERY = "local_delivery"
    UNKNOWN = "unknown"


class RowStatus(str, Enum):
    FILLED = "filled"
    NO_RATE = "no_rate"
    ALREADY_FILLED = "already_filled"
    EXAMPLE = "example"
    NON_LOCAL_LEG = "non_local_leg"   # 非上海段，跳过
    LOCAL_DELIVERY_MANUAL = "local_delivery_manual"  # LOCAL_DELIVERY 保留 '－'，v1.0 不查
    CONSTRAINT_BLOCK = "constraint_block"
    OVERRIDDEN = "overridden"         # 营业改过价


@dataclass(slots=True)
class PkgSection:
    section_index: int                # 0..4
    section_code: str                 # 'NRT' / 'PVG' / 'AMS' / 'TPE' / 'ICN'
    header_row: int                   # R3 / R12 / R21 / R25 / R34
    origin_text_raw: str              # '中国  (上海)'
    origin_code: str                  # 'PVG'
    currency: str                     # 'JPY' / 'CNY' / 'EUR' / 'USD'
    currency_header_raw: str          # '単価 (CNY/kg)'
    is_local_section: bool            # section_code == 'PVG' (v1.0 Customer A)
    section_level_remarks: list[str] = field(default_factory=list)  # R38 这种段级客户硬约束原文


@dataclass(slots=True)
class PkgRow:
    row_idx: int                      # Excel 行号（R13..R19 等）
    section_index: int                # 所属段
    section_code: str
    origin_code: str
    origin_text_raw: str
    destination_text_raw: str         # 'アメリカ  (アトランタ)\nAIR FREIGHT COST'
    destination_code: str             # 'ATL'（映射失败填 'UNKNOWN'）
    cost_type: CostType
    currency: str
    volume_desc: str                  # D 列原文
    existing_price: Decimal | None    # E 列原值（非零则视为"已填"）
    existing_lead_time: str | None
    existing_carrier: str | None
    existing_remark: str | None
    is_example: bool                  # True → 不处理
    client_constraint_text: str | None  # H 列客户硬约束（非 '※記入例'）
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedPkg:
    bid_id: str
    customer_code: str                # 'customer_a'
    period: str                       # '2026-01'
    sheet_name: str
    source_file: str
    sections: list[PkgSection]
    rows: list[PkgRow]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuoteCandidate:
    # 来自 Step1 air_weekly 的 base
    base_price: Decimal               # 按 Q5 默认=期望起飞日对应 price_dayN
    base_price_day_index: int | None  # 1..7
    airline_codes: list[str]          # 从 Step1 extras.airline_codes
    service_desc: str
    via: str | None                   # 解析 service_desc 里的 "via XXX"
    # 来自 Step1 air_surcharges 的叠加
    myc_fee_per_kg: Decimal | None
    msc_fee_per_kg: Decimal | None
    myc_applied: bool                 # all_fees_dash 则 False
    msc_applied: bool
    # 合计
    cost_price: Decimal               # base + myc + msc（若 applied）
    currency: str
    # 追溯
    source_batch_id: str              # Step1 批次 UUID
    source_weekly_record_id: int
    source_surcharge_record_id: int | None
    remarks_from_step1: str | None    # 合并 weekly.remarks + surcharge.remarks
    step1_must_go: bool
    step1_case_by_case: bool
    match_score: float                # 0.0-1.0（维度匹配分）


@dataclass(slots=True)
class PerRowReport:
    row_idx: int
    section_code: str
    destination_code: str
    status: RowStatus
    cost_price: Decimal | None
    sell_price: Decimal | None
    markup_ratio: Decimal | None
    lead_time_text: str | None
    carrier_text: str | None
    remark_text: str | None
    selected_candidate: QuoteCandidate | None
    constraint_hits: list[str] = field(default_factory=list)
    validator_warnings: list[str] = field(default_factory=list)   # 从 validator.py 来的
    confidence: float = 0.0
    overridden_by: str | None = None
    overridden_at: datetime | None = None


@dataclass(slots=True)
class FillReport:
    bid_id: str
    generated_at: datetime
    row_reports: list[PerRowReport]
    filled_count: int
    no_rate_count: int
    skipped_count: int
    cost_file_path: str
    sr_file_path: str
    global_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BiddingRequest:
    bid_id: str
    customer_code: str
    period: str
    status: BiddingStatus
    source_file_path: str
    uploader: str | None
    created_at: datetime
    updated_at: datetime
    parsed_pkg: ParsedPkg | None = None
    fill_report: FillReport | None = None
```

---

## 5. protocols.py — 接口契约

```python
# backend/app/services/step2_bidding/protocols.py

from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable
from app.services.step2_bidding.entities import (
    ParsedPkg, PkgRow, QuoteCandidate, FillReport
)
from app.services.step1_rates.entities import Step1RateRow


@runtime_checkable
class CustomerProfile(Protocol):
    customer_code: str        # 'customer_a'
    display_name: str         # 'ミマキエンジニアリング'
    priority: int             # 识别器 tiebreak（越大越优先）

    def detect(self, path: Path, hint: str | None = None) -> bool: ...
    def parse(self, path: Path, bid_id: str, period: str) -> ParsedPkg: ...
    def fill(
        self,
        source_path: Path,
        parsed: ParsedPkg,
        row_reports: list,           # list[PerRowReport]
        variant: str,                # 'cost' | 'sr'
        output_path: Path,
    ) -> None: ...


@runtime_checkable
class RateRepository(Protocol):
    """Step2 只读 Step1 入库数据；本接口是 Step2 唯一访问 Step1 的入口。"""

    def query_air_weekly(
        self,
        *,
        origin: str,                           # 'PVG'
        destination: str,                      # 'ATL' 或原文
        effective_on: date,                    # 按期望起飞日
        currency: str | None = None,           # 过滤条件
        airline_code_in: list[str] | None = None,
    ) -> list[Step1RateRow]: ...

    def query_air_surcharges(
        self,
        *,
        airline_code: str,
        effective_on: date,
        currency: str | None = None,
    ) -> list[Step1RateRow]: ...

    # 本轮 Customer A 只需 Air；Ocean 接口先留占位，v2.0 再实
    def query_ocean_fcl(self, **kwargs) -> list[Step1RateRow]: ...
    def query_lcl(self, **kwargs) -> list[Step1RateRow]: ...
```

**RateRepository 的物理实现**（`rate_repository.py`）约束：
- 只查 `import_batches.status == 'active'` 的批次的记录
- 对 `AirFreightRate`：过滤 `origin == origin AND destination LIKE '%{dest}%' AND effective_week_start <= effective_on <= effective_week_end`
- 对 `AirSurcharge`：过滤 `airline_code == airline_code AND effective_date <= effective_on`
- **返回转换为 `Step1RateRow`**（而不是 SQLAlchemy model），保持 Step1 的统一契约；转换逻辑参照 `Step1RateRow` 字段一一赋值，`extras` 字段暂填空 dict（v2.0 补充 airline_codes 等 extras 需要重跑 parse 时回写到 DB 的 JSON 字段，目前 AirFreightRate 没有 extras 列，**此处是 v2.0 债务记录**）

---

## 6. Customer A 解析规则（customer_a.py 伪代码）

### 6.1 detect()

```python
def detect(self, path: Path, hint: str | None = None) -> bool:
    if hint == "customer_a":
        return True
    # Q6 默认：营业手选；此处只做文件特征兜底
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception:
        return False
    if len(wb.sheetnames) != 1:
        return False
    ws = wb[wb.sheetnames[0]]
    if ws.title.strip() != "見積りシート":
        return False
    # 必须有 5 段"発地/着地"表头
    count = sum(
        1 for r in range(1, min(ws.max_row, 50) + 1)
        if str(ws.cell(r, 2).value or "").strip() == "発地"
        and "着地" in str(ws.cell(r, 3).value or "")
    )
    return count >= 2
```

### 6.2 parse()

**算法步骤**（单文件死磕 Customer A）：

1. `wb = load_workbook(path, data_only=True)`；`ws = wb["見積りシート"]`
2. **扫表头行**：遍历 R1..R50，当 B 列 strip == `'発地'` 且 C 列 strip 含 `'着地'` → 记为 header_row
   - 对每个 header_row，读 E 列原文（`'単価 (CNY/kg)'`）→ `_parse_currency(header_text)` 归一化
   - 币种映射：`'円' or 'JPY' → 'JPY'`；`'CNY' → 'CNY'`；`'ユーロ' or 'EUR' → 'EUR'`；`'USD' → 'USD'`
3. **扫数据行**：header_row + 1 到 下一个 header_row - 1（或下一个空白行 break）
   - B 列首个非空值 → 本段 origin_text_raw；映射 origin_code（用 `_ORIGIN_MAP`，见 §6.3）
   - C 列非空 → 一条 PkgRow
     - 判定 cost_type：`'AIR FREIGHT COST' in C → AIR_FREIGHT`；`'LOCAL DELIVERY COST' in C → LOCAL_DELIVERY`；否则默认 AIR_FREIGHT
     - 判定 is_example：G 列或 H 列含 `'記入例'`
     - 提取 destination_code：对 C 列原文按 `_DEST_KEYWORDS` 命中第一个（见 §6.3；无命中填 'UNKNOWN'）
     - 读 D (volume_desc), E (existing_price), F (existing_lead_time), G (existing_carrier), H (existing_remark)
     - client_constraint_text = H 列值 剔除 `'※記入例...'`（用 `re.sub` 删掉）
4. **段级约束**：B 列有值但非 `'発地'` 开头且不属于任何数据行（比如 R38 `'※韓国→...'`）→ 添加到当前 section 的 `section_level_remarks`
5. **空白行 break**：连续 2 行 B-C-E 全 None → 认为该段结束
6. 最终产出 ParsedPkg

### 6.3 origin / destination 映射表（硬编码在 customer_a.py）

```python
_ORIGIN_MAP = {
    # 关键字 → 港口代码；按 keyword 长度降序匹配
    'インチョン': 'ICN', '韓国': 'ICN',
    'アムステルダム': 'AMS', 'オランダ': 'AMS',
    '台北': 'TPE', '台湾': 'TPE',
    '成田': 'NRT', '日本': 'NRT',
    '上海': 'PVG', '中国': 'PVG',
}

_DEST_KEYWORDS = {
    'アトランタ': 'ATL',
    'マイアミ': 'MIA',
    'アムステルダム': 'AMS',
    'サンパウロ': 'GRU',
    'シドニー': 'SYD',
    '台北': 'TPE',
    '上海': 'PVG',
}
```

**三份文件各一个 adapter** 的原则体现：这份映射表**只写 Customer A 的 7 个着地**；Customer B/E/Nitori 自己写自己的。不抽公共 `PortMap` 类。

### 6.4 fill(variant='cost' | 'sr')

**算法步骤**：

1. `shutil.copy2(source_path, output_path)` → 复制原文件为模板
2. `wb = load_workbook(output_path, data_only=False)`（**必须 data_only=False 才能保留公式**）
3. `ws = wb["見積りシート"]`
4. 遍历 row_reports，对 `section_code == 'PVG'` 且 `status == FILLED` 的行：
   - E 列 = cost_price（variant='cost'）或 sell_price（variant='sr'）
   - F 列 = lead_time_text
   - G 列 = carrier_text（LOCAL_DELIVERY 行 → `'－'`；但 LOCAL_DELIVERY 已在 §7 §3 阶段标 `LOCAL_DELIVERY_MANUAL`，不会进 FILLED）
   - H 列 = variant == 'sr' ? `"ALL-in"` : `None`（cost 版 H 留空，符合 §0.3 实测）
5. `wb.save(output_path)` + `wb.close()`
6. **不动样式 / 合并（本文件本来无合并）/ 字体 / 列宽**

### 6.5 v1.0 放弃 & 扩展点

- `parse` 内 **禁止调 AI**（规则法足够，5 段表头位置固定）
- **未来扩展**：若客户 PKG 发生"非预期列序"→ T-B13（v2.0）接 `ai_client.chat`，让 Claude 返回列映射 JSON

---

## 7. RateMatcher（rate_matcher.py 伪代码）

### 7.1 签名

```python
class RateMatcher:
    def __init__(self, repo: RateRepository, markup: MarkupApplier):
        self._repo = repo
        self._markup = markup

    def match(
        self,
        row: PkgRow,
        *,
        effective_on: date,                    # Q7 默认 = period 当月 1 日所在周
        carrier_preference: list[str] | None = None,
        max_candidates: int = 5,
    ) -> tuple[RowStatus, list[QuoteCandidate]]: ...
```

### 7.2 匹配流程

```
1. 预过滤：
   if row.section_code != 'PVG': return (NON_LOCAL_LEG, [])
   if row.is_example:           return (EXAMPLE, [])
   if row.cost_type == LOCAL_DELIVERY: return (LOCAL_DELIVERY_MANUAL, [])
   if row.existing_price not None and row.existing_price != 0:
       return (ALREADY_FILLED, [])    # 客户已填，不覆盖
   if row.destination_code == 'UNKNOWN': return (NO_RATE, [])

2. 查周表：
   weekly_rows = repo.query_air_weekly(
       origin='PVG',
       destination=row.destination_code,
       effective_on=effective_on,
       currency=row.currency,   # Q4 默认不换汇；若 Step1 入库币种 != row.currency 本行标 NO_RATE
   )
   if not weekly_rows: return (NO_RATE, [])

3. 对每个 weekly_row：
   a. 取 price_day = _pick_price_by_etd(weekly_row, effective_on)  # Q5 默认：对应 day_index
      若该 day_index 价格为 None → 尝试周内均价 → 仍 None 则跳过
   b. 从 extras.airline_codes 取候选航司
   c. 查 Surcharges：对每个 airline_code
      surcharges = repo.query_air_surcharges(airline_code=ac, effective_on=effective_on)
      取 all_fees_dash == False 的第一条
   d. 合并 QuoteCandidate:
        cost_price = price_day
                   + (surcharge.myc_fee_per_kg if myc_applied else 0)
                   + (surcharge.msc_fee_per_kg if msc_applied else 0)
   e. match_score 计算（维度加权）：
        + 0.4 目的地精确匹配
        + 0.2 币种匹配
        + 0.2 有效期覆盖
        + 0.1 航司在 carrier_preference 中
        + 0.1 无 must_go / case_by_case

4. 约束过滤：
   if carrier_preference and no candidate.airline in carrier_preference:
       return (CONSTRAINT_BLOCK, [])

5. 排序（Q9 默认：最低价优先）+ 截断：
   candidates.sort(key=lambda c: c.cost_price)
   return (FILLED, candidates[:max_candidates])
```

### 7.3 _pick_price_by_etd 策略（Q5 默认实现）

- `effective_on` 落在周内第 N 天（weekly_row.effective_week_start 到 end 的 0..6 offset + 1）
- `price_day{N}` 为 None → 退化到"同周内非 None 的平均"
- 全部 None → 返回 None（该 weekly_row 不产生候选）

### 7.4 Must go / Case by case 处理

- `step1_must_go == True` 且 `must_go_value is not None` → candidate 照常返回，但 `constraint_hits.append("Step1 Must go X")`，审核界面必须提示
- `step1_case_by_case == True` → 候选仍返回，**但 match_score × 0.5 降权**，`constraint_hits.append("Step1 Case by case — 请购买部确认")`
- 不静默填入；营业审核时可见

---

## 8. MarkupApplier & Validator

### 8.1 markup.py

```python
class MarkupApplier:
    def __init__(self, *, ratio: Decimal = Decimal("1.15"), ceiling: str = "ceil_int"):
        self.ratio = ratio
        self.ceiling = ceiling    # 'ceil_int' / 'round_int' / 'raw'

    def apply(self, cost: Decimal, *, currency: str, carrier_route: str | None = None) -> Decimal:
        """Q2 默认 × 1.15，ceiling 向上取整到整数币种单位。"""
        # v1.0 不区分航线；v2.0 若 Q3 回复为"按客户×航线"则改为查加价表
```

- 默认常量 `_MARKUP_RATIO = Decimal("1.15")`，写在 markup.py 顶部，Q2 回复后只改此常量
- **对比黄金样本 2-④.xlsx 实证**：PVG 段 cost(45/50/38/22/12) → sr(49/54/41/25/13)，加价比例 ~1.08-1.09；**与 ×1.15 有偏差**，Demo 时必须在 UI 明确标 "加价系数待业务确认"
- ceil_int 策略：`Decimal(cost) * ratio` → `math.ceil` → 整数

### 8.2 H 列 "ALL-in" 业务常量

- 位于 `customer_a.py` 顶部 `_SR_FIXED_REMARK = "ALL-in"`
- variant='sr' 时写入；variant='cost' 时不写
- 若 row 有 `client_constraint_text`（非空且非記入例）→ H 列写 `f"ALL-in / {client_constraint_text}"`（追加而不是覆盖）

### 8.3 validator.py

```python
class HistoricalRateValidator:
    def __init__(self, repo: RateRepository):
        self._repo = repo

    def validate(
        self,
        row: PkgRow,
        sell_price: Decimal,
        *,
        previous_sell_prices: dict[str, Decimal] | None = None,  # 上期同航线报价 (Q11 无数据则跳过)
        threshold_pct: Decimal = Decimal("0.30"),                # Q11 默认 ±30%
    ) -> list[str]:
        """返回 warning list，不阻止填入，只高亮。"""
```

- v1.0 实现：仅当 `previous_sell_prices` 被显式传入才校验（Q16 未答，v1.0 不自建上期费率库）
- 输出 warning 字符串 → `PerRowReport.validator_warnings`

---

## 9. API 契约（`backend/app/api/v1/bidding.py`）

### 9.1 POST /api/v1/bidding/pkg（上传 + 解析 + 自动检索 + 填入，同步）

**请求**：
```
multipart/form-data:
  file: .xlsx
  customer_code: 'customer_a' (可空，空则走 CustomerIdentifier)
  period: '2026-01' (可空，默认当月 YYYY-MM)
  effective_on: '2026-01-15' (可空，默认 period 月份第 15 日)
  uploader: 'narazaki@hhe.co.jp' (可空)
```

**响应**：
```json
{
  "code": 0,
  "message": "pkg parsed and filled",
  "data": {
    "bid_id": "bid_a1b2c3",
    "customer_code": "customer_a",
    "period": "2026-01",
    "status": "awaiting_review",
    "parsed_pkg": {<ParsedPkg 序列化>},
    "fill_report": {<FillReport 序列化>},
    "download_urls": {
      "cost": "/api/v1/bidding/bid_a1b2c3/download?variant=cost",
      "sr": "/api/v1/bidding/bid_a1b2c3/download?variant=sr"
    }
  }
}
```

- 状态机：`CREATED → PARSING → PARSED → QUOTING → QUOTED → AWAITING_REVIEW`
- 任一步异常 → status=FAILED，返回 warning 列表，**不抛 500**（前端需显示错误）

### 9.2 GET /api/v1/bidding/{bid_id}

返回完整 BiddingRequest（含 parsed_pkg + fill_report），用于审核页渲染。

### 9.3 PATCH /api/v1/bidding/{bid_id}/rows/{row_idx}

**请求**：
```json
{
  "sell_price": 49,
  "lead_time_text": "3-4DAYS",
  "carrier_text": "OZ via ICN / NH via NRT",
  "remark_text": "ALL-in",
  "overridden_by": "narazaki"
}
```

**响应**：更新后的 PerRowReport + 重新渲染 sr_版.xlsx 的 md5 / updated_at。

- 服务端：更新 `bidding_row_reports` 表，status 变 OVERRIDDEN，写 overridden_by/at
- 重新打开 sr_版.xlsx（openpyxl）改单元格保存

### 9.4 GET /api/v1/bidding/{bid_id}/download?variant={cost|sr}

`FileResponse` 返回 .xlsx；文件名 `filled_{variant}_{source_filename}`。

### 9.5 POST /api/v1/bidding/{bid_id}/submit

- 校验：所有 `status in {NO_RATE, CONSTRAINT_BLOCK}` 的行必须有 `overridden_by` 才能 submit
- 成功 → status=SUBMITTED，返回最终文件路径
- 不发邮件（v1.0 不做）

### 9.6 GET /api/v1/bidding（列表）

分页；支持 status / customer_code 过滤；给管理页用。

### 9.7 GET /api/v1/bidding/{bid_id}/rows/{row_idx}/candidates

返回 QuoteCandidate 列表（前端手动切换候选时用），可选 API。

---

## 10. Q1-Q7 技术默认值（楢崎未答时推进）

| 编号 | 业务问题 | 默认值（代码常量） | 代码位置 | 楢崎回答后改哪里 |
|---|---|---|---|---|
| Q1 | Demo 范围 | Customer A + Air 周表 + Surcharges + Ocean 基础费率（**v1.0 实际只实现 Customer A+Air**）| `customer_profiles/__init__.py` 注册表 | 追加其它 profile |
| Q2 | 成本→销售加价 | `Decimal("1.15")` × ceil_int | `markup.py:_MARKUP_RATIO` | 改常量或改为查表 |
| Q3 / Q5 | 周价粒度 | `effective_on` 落在周内 day_index → price_dayN；空值退化周均 | `rate_matcher.py:_pick_price_by_etd` | 改策略函数 |
| Q4 | 换汇 | 不换；`row.currency != weekly_row.currency` → 本行 NO_RATE + warning | `rate_matcher.py` 第 2 步过滤 | 加 FX 服务或改默认 "按发地固定" |
| Q5 / Q7 | 入札期间跨周 | `effective_on = period_YYYY-MM 的第 15 日`（取覆盖该日的 active 批次周表） | `service.py:_default_effective_on` | 改默认算法 |
| Q6 | 客户标识 | 优先用请求中的 `customer_code`；空则走 `CustomerIdentifier`：① 文件特征（sheet 名 + 列头）→ ② 上传者历史偏好 → ③ 默认 customer_a 兜底 | `customer_identifier.py` | 增加发件人域名白名单 |
| Q7 | 已有数据判定 | 非零即不覆盖（`existing_price != 0 and existing_price is not None`）| `rate_matcher.py` 预过滤 | 改为关键字检测 |

**所有默认值必须在 `config.py` 或各 service 顶部以 `_XXX_DEFAULT = ...` 常量存放**，楢崎回答后改常量 + 回归测试。

---

## 11. Customer A 字段映射表（业务层 → 技术层）

| Customer A 列 | Excel 位置 | ParsedPkg 字段 | Step1 对应查询字段 | 回填到谁 |
|---|---|---|---|---|
| 入札期间 | B1 | `ParsedPkg.period` | — | `bidding_requests.period` |
| 発地 | B 列（段首行） | `PkgSection.origin_text_raw`、`PkgRow.origin_code` | `RateRepository.query_air_weekly(origin=...)` | 不回填 |
| 着地 | C 列 | `PkgRow.destination_text_raw`、`PkgRow.destination_code` | `query_air_weekly(destination=...)` | 不回填 |
| 想定物量 | D 列 | `PkgRow.volume_desc` | 不作为检索维度（Q 未问） | 不回填（客户已填） |
| 単価 | E 列（段首行含币种） | `PkgRow.currency` + `PkgRow.existing_price` | `query_air_weekly(currency=...)` | **sell_price / cost_price 写回 E** |
| Lead Time | F 列 | `PkgRow.existing_lead_time` | Step1 无独立字段；从 `service_desc` 文本抽 (`'3-4 days'`) | **lead_time_text 写回 F**；LOCAL_DELIVERY 保留 `'－'` |
| 主要キャリアとルート | G 列 | `PkgRow.existing_carrier` | `airline_code` + extras.via | **carrier_text 写回 G**；LOCAL_DELIVERY 保留 `'－'` |
| 備考 | H 列 | `PkgRow.client_constraint_text`（剔除記入例）| Step1 `remarks` + `extras.has_must_go` | variant='sr' → `"ALL-in"`；有 client_constraint 则追加 |

### 11.1 查不到费率时的回填规则

| 场景 | E 列 | F 列 | G 列 | H 列 | status |
|---|---|---|---|---|---|
| 非 PVG 段 | 保持原值 | 保持 | 保持 | 保持 | NON_LOCAL_LEG |
| is_example | 保持原值 | 保持 | 保持 | 保持 | EXAMPLE |
| LOCAL_DELIVERY | 保持（0/原值） | `'－'` | `'－'` | 空 | LOCAL_DELIVERY_MANUAL |
| existing_price != 0 | 保持 | 保持 | 保持 | 保持 | ALREADY_FILLED |
| 周表无命中 | 空（None） | 空 | 空 | 空 | NO_RATE（审核页红色高亮）|
| 约束拦截 | 空 | 空 | 空 | `client_constraint_text` | CONSTRAINT_BLOCK |
| 营业改过价 | sell_price_new | lead_time_new | carrier_new | 按 variant | OVERRIDDEN |

### 11.2 cost 版 vs S/R 版差异

| 差异点 | cost 版 | S/R 版 |
|---|---|---|
| 文件名 | `cost_{original}.xlsx` | `sr_{original}.xlsx` |
| E 列单价 | `QuoteCandidate.cost_price` | `MarkupApplier.apply(cost_price)` |
| H 列备注 | 空（实证 2-②.xlsx） | `"ALL-in"`（+ client_constraint_text）|
| 交付对象 | 购买部门 Nakamura 审批 | 日本本部关根（最终客户版） |
| 下载 URL | `?variant=cost` | `?variant=sr` |

---

## 12. 异常 & 人工介入点（5 类）

| 类型 | 判定条件 | UI 占位 JSON schema（status 字段值） | 要求营业做什么 |
|---|---|---|---|
| 无费率命中 | `status == NO_RATE` | `{ "level": "error", "badge": "要手工询购买部", "color": "#ff4d4f" }` | 在审核页点"追问购买部" / 手工填入 |
| Must go | `selected_candidate.step1_must_go == True` | `{ "level": "warn", "badge": "Must go {value}", "tooltip": "..." }` | 确认本票是否达量 |
| Case by case | `selected_candidate.step1_case_by_case == True` | `{ "level": "warn", "badge": "CBC", "color": "#faad14" }` | 找购买部确认是否可报 |
| 多候选（>1 条 score 差 ≤0.1）| `len(candidates) > 1 and abs(c[0].score - c[1].score) < 0.1` | `{ "level": "info", "badge": "{N} 个候选", "dropdown": [...] }` | 切换候选 |
| 客户约束冲突 | `constraint_hits != []`（如 PKG 要求 NH 但候选无 NH）| `{ "level": "error", "badge": "约束冲突", "detail": ["PKG 要求 NH direct，周表无 NH"] }` | 手工填 + 邮件购买部 |

前端组件实现在 v1.5，本轮只定 schema。

---

## 13. Alembic 迁移（`20260423_0001_step2_bidding_models.py`）

### 13.1 `bidding_requests`

```sql
id PK
bid_id VARCHAR(32) UNIQUE NOT NULL
customer_code VARCHAR(32) NOT NULL
period VARCHAR(16) NOT NULL
status ENUM(BiddingStatus 8 个取值)
source_file_path VARCHAR(512)
cost_file_path VARCHAR(512)
sr_file_path VARCHAR(512)
uploader VARCHAR(100)
created_at DATETIME DEFAULT NOW()
updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
parsed_pkg_json JSON               -- 序列化 ParsedPkg（便于 GET 接口直接返回）
INDEX (customer_code, period), INDEX (status)
```

### 13.2 `bidding_row_reports`

```sql
id PK
bid_id VARCHAR(32) FK -> bidding_requests.bid_id
row_idx INT NOT NULL
section_code VARCHAR(8)
destination_code VARCHAR(16)
status ENUM(RowStatus 8 个取值)
cost_price NUMERIC(10,2)
sell_price NUMERIC(10,2)
markup_ratio NUMERIC(6,4)
lead_time_text VARCHAR(64)
carrier_text VARCHAR(255)
remark_text TEXT
candidate_batch_id UUID             -- 追溯 Step1 批次
candidate_source_record_id INT      -- AirFreightRate.id
candidate_surcharge_record_id INT   -- AirSurcharge.id
match_score NUMERIC(4,3)
constraint_hits JSON
validator_warnings JSON
confidence NUMERIC(4,3)
overridden_by VARCHAR(100)
overridden_at DATETIME
UNIQUE (bid_id, row_idx)
INDEX (bid_id, status)
```

### 13.3 回滚

- `downgrade()`：`op.drop_table('bidding_row_reports')` → `op.drop_table('bidding_requests')`
- 不动 Step1 表
- 不动 `freight_rates / air_freight_rates` 等

---

## 14. 扩展点（v2.0 不动本轮代码）

| 扩展点 | 如何追加 |
|---|---|
| Customer B 适配器 | `customer_profiles/customer_b.py` 实现 `CustomerProfile` + 注册表追加；**不改 customer_a.py** |
| Customer E / Nitori | 同上；Nitori 要加 `.xlsm` 宏保留逻辑，`load_workbook(keep_vba=True)` |
| 发件人域名识别 | `customer_identifier.py` 追加 `_DOMAIN_MAP`；不改 service.py |
| 上海一次填多段 | `rate_matcher.py` 预过滤放开；加 `profile.local_sections: list[str]` |
| 自动发邮件 | 新增 `backend/app/services/step2_bidding/notifier.py` + `/submit` 后调用 |
| 上期费率对比 | `validator.py` 加 `fetch_previous_sr(bid_id)`；依赖 v2.0 的入札历史表 |
| AI 列识别 fallback | `customer_a.py` _parse 失败 → `ai_client.chat(prompt=...)`；**只在 v2.0 新客户时用** |

---

## 15. AI Skills 技术形态

| Skill | 实现方式 | 理由 |
|---|---|---|
| `parse_pkg` | **规则法为主，AI 为备**。Customer A 规则法 100% 够用（5 段表头位置固定）；v2.0 新客户接 AI fallback | Customer A 结构稳定；AI 不稳定可能把表头识别错 |
| `query_rate` | **纯 SQL，禁用 AI** | 业务文档 §3.5 "禁止 AI 编价"；Step1 入库即可穷举候选，不需要语义检索 |
| `fill_pkg` | **纯 openpyxl 写单元格** | 格式保真是硬约束 |
| `validate_rate` | 规则法（阈值对比） | 阈值明确，无需 AI |

### 15.1 Prompt 模板骨架（仅 parse_pkg fallback；本轮**不实现**，作为扩展点预留）

```
System:
  你是物流入札 Excel 结构识别助手。输出 JSON，不加任何额外文字。

User:
  【客户】{customer_code}
  【Sheet 名】{sheet_name}
  【前 10 行原文】
  {first_10_rows_as_csv}

  请识别：
  1. 表头行号（可能多个）
  2. 每个表头下"发地 / 目的地 / 币种 / 需填单价列 / 需填 lead time 列 / 需填 carrier 列" 在哪一列
  3. 哪些行是"記入例"或"示范"行

  输出 JSON:
  {
    "header_rows": [3, 12, ...],
    "column_map": {
      "origin": "B",
      "destination": "C",
      "unit_price": "E",
      ...
    },
    "example_rows": [4, 5]
  }
```

- 调用：`ai_client.chat(system_prompt, user_message, temperature=0.0, max_tokens=2048)`
- 返回 → `ai_client.extract_json(text)` → dict
- 失败重试 1 次；再失败 → parse 抛 `PkgParseAmbiguousError`，API 返回 400 + warning

---

## 16. 验收点（V-B01..V-B25）

### 16.1 解析验收（黄金样本：`资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①.xlsx`）

| V-B01 | `CustomerIdentifier.identify(path)` 返回 `customer_code='customer_a'` |
| V-B02 | `CustomerAProfile.parse(path)` 返回 `ParsedPkg.sections` 长度 = 5 |
| V-B03 | 五段 `section_code` 分别为 `['NRT','PVG','AMS','TPE','ICN']` |
| V-B04 | 五段 `currency` 分别为 `['JPY','CNY','EUR','USD','USD']` |
| V-B05 | `PVG` 段 `rows` 长度 = 7（R13..R19）|
| V-B06 | R14 / R17 `cost_type == LOCAL_DELIVERY` |
| V-B07 | R4 / R5 `is_example == True`；PVG 段无 is_example |
| V-B08 | ICN 段（section_code='ICN'）`section_level_remarks` 包含 R38 原文 `'※韓国→日本→ブラジル...'` |
| V-B09 | R13 `destination_code == 'ATL'`；R19 `destination_code == 'TPE'` |

### 16.2 检索验收（假定 Step1 入库已有 Apr 20-26 周表 + Surcharges active 批次）

| V-B10 | `RateRepository.query_air_weekly(origin='PVG', destination='ATL', effective_on=date(2026,4,22))` 返回 ≥1 条，且所有返回 `record_kind == 'air_weekly'` |
| V-B11 | `RateMatcher.match(PVG-ATL row)` 返回 `(RowStatus.FILLED, candidates)`，`candidates[0].cost_price is not None` |
| V-B12 | `RateMatcher.match(NRT-ATL row)` 返回 `(RowStatus.NON_LOCAL_LEG, [])` |
| V-B13 | `RateMatcher.match(LOCAL_DELIVERY row)` 返回 `(RowStatus.LOCAL_DELIVERY_MANUAL, [])` |
| V-B14 | `RateMatcher.match(existing_price=100 的行)` 返回 `(RowStatus.ALREADY_FILLED, [])` |
| V-B15 | candidate 中 must_go / case_by_case 透传到 `constraint_hits` |

### 16.3 填入验收（对标 `资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-④.xlsx`）

| V-B16 | `service.run(path, customer_code='customer_a', effective_on=date(2026,1,15))` 生成两个文件 `cost_xxx.xlsx` 和 `sr_xxx.xlsx` |
| V-B17 | 打开 sr_xxx.xlsx，`ws["E13"].value`（PVG-ATL）是数字；`ws["F13"].value` 是字符串；`ws["G13"].value` 是字符串；`ws["H13"].value == "ALL-in"` |
| V-B18 | sr_xxx.xlsx 的 `ws["E14"]`（LOCAL_DELIVERY 行）= 0（保留原值）；`ws["F14"].value == '－'`；`ws["G14"].value == '－'` |
| V-B19 | sr_xxx.xlsx 的 NRT 段（R4-R10）E/F/G/H 列与原文件完全一致（未被修改） |
| V-B20 | cost_xxx.xlsx 的 `ws["H13"].value` 为 None 或空（不含 ALL-in）|
| V-B21 | 黄金样本比对：sr_xxx.xlsx PVG 段 E13/E15/E16/E18/E19 的填入值 与 2-④.xlsx 对应单元格的**类型**一致（数字，不是字符串），**值差异**允许（因 Step1 真实周表 vs 历史 S/R 不同源） |
| V-B22 | `ws.merged_cells` 与原文件一致（无破坏）|

### 16.4 API 验收

| V-B23 | `POST /api/v1/bidding/pkg` 上传 2-①.xlsx 返回 `status == 'awaiting_review'`，`bid_id` 非空 |
| V-B24 | `GET /api/v1/bidding/{bid_id}` 返回 ParsedPkg.sections 长度 = 5 |
| V-B25 | `PATCH /api/v1/bidding/{bid_id}/rows/13` `{"sell_price": 49}` 后，再 `GET /api/v1/bidding/{bid_id}/download?variant=sr` 下载的 Excel `ws["E13"].value == 49` |

### 16.5 Demo 硬基线（5/14）

- **端到端重演**：楢崎上传 `2-①.xlsx` → 系统产出 sr 版 → 与 `2-④.xlsx` PVG 段逐单元格对比（允许价格偏差由 Step1 当期 active 批次决定；但**字段有无、类型、行列位置必须 100% 一致**）
- **失败定义**：任一单元格类型错（本该数字写成字符串）、任一单元格越权（填了非 PVG 段）、格式破坏（任何列宽/合并/字体异常）

---

## 17. 任务拆分 T-B1..T-B12

| 编号 | 标题 | 前置 | 工时（人天） |
|---|---|---|---|
| T-B1 | entities.py + protocols.py 骨架 | — | 0.5 |
| T-B2 | Alembic 迁移（bidding_requests + bidding_row_reports） | T-B1 | 0.5 |
| T-B3 | RateRepository 实现（query_air_weekly + query_air_surcharges，含 active 批次过滤） | T-B1 | 1.0 |
| T-B4 | CustomerAProfile.parse（§6.1-6.3）+ 单元测试 5 段识别 | T-B1 | 1.0 |
| T-B5 | RateMatcher（§7 全流程，含 Surcharges 叠加、排序、约束过滤） | T-B3 | 1.0 |
| T-B6 | MarkupApplier + HistoricalRateValidator 骨架 | T-B5 | 0.5 |
| T-B7 | CustomerAProfile.fill（§6.4）+ cost 版 / sr 版双文件生成 | T-B4, T-B5 | 1.0 |
| T-B8 | CustomerIdentifier（§Q6 默认策略）+ stub profile 注册（B/E/Nitori 留 NotImplementedError） | T-B1 | 0.5 |
| T-B9 | service.py 5 步编排 + 状态机 + 会话持久化到 bidding_requests | T-B4,B5,B7 | 1.0 |
| T-B10 | API `/api/v1/bidding` 7 个 endpoint（§9）+ router 注册 | T-B9 | 1.0 |
| T-B11 | 删除旧 `pkg_parser.py / pkg_filler.py / rate_db.py` + 保留旧 `/api/v1/pkg` 路由的最小 stub（兜底 Demo） | T-B10 | 0.5 |
| T-B12 | pytest 验收用例 V-B01..V-B25（测试大师主导，开发大师搭骨架） | T-B10 | 1.0 |

**总计约 9.5 人天**；Demo 5/14 倒推 4/23 启动，留出 1-2 天 buffer。

---

## 18. 三大技术风险

### 18.1 风险 1：Customer A 闭环能否 100% 用现有 Step1 数据覆盖？

- **风险**：黄金样本 2-④.xlsx 的 PVG 段 5 条 S/R（49/54/41/25/13 CNY）是 2025-12 的 Nakamura 人工销售价；Step1 入库的是 2026-04 的 cost 周表 + Surcharges。**两者时间线完全不重叠**，验收时 V-B21 无法用"数值相等"比对，只能比"字段有无、类型、位置"。
- **兜底**：
  1. V-B21 明确允许价格偏差；验收只比结构
  2. Demo 当天要求楢崎用"2026-04 active 批次"的数据，临时运行一次 Step1 Air parser 入库，再跑 Step2 → 能跑出非空价格（哪怕不是 49，也证明链路通）
  3. 若 5/14 前楢崎无新数据：Demo 前 1 天开发大师手工造一份 `Apr 20 to Apr 26` 的 mock 周表，含 PVG-ATL/MIA/AMS/SYD/TPE 五条

### 18.2 风险 2：Q2 加价规则若楢崎给复杂公式（按客户×航线×周 加价表）如何兜底？

- **风险**：黄金样本实证的加价比例（1.08-1.09）与默认 1.15 **偏差 5-7%**，若 Demo 时用 1.15 会比真实 S/R 高 5 块钱，客户或楢崎一眼看出。
- **兜底**：
  1. `markup.py` 内预留 `MarkupStrategy` Protocol，`_MARKUP_RATIO` 只是 `FixedMarkupStrategy` 的实例；若 Q2 回复"按表查" → 新增 `TableMarkupStrategy(lookup_table)` 且不改 service.py
  2. 审核页 UI 必须标注"销售价 = 成本价 × 1.15（系统默认，业务请核对）"，让营业一眼看到
  3. **退路**：若楢崎 5/14 前不答 Q2 → Demo 演 cost 版 + 人工改单元格变 sr 版，完全规避加价议题

### 18.3 风险 3：营业自由改价后，Excel 回写的 sr_版文件与数据库 row_report 不一致

- **风险**：PATCH 接口改了 DB 但 Excel 回写失败（文件锁、磁盘 IO、字符编码）；或反之。前端下载时可能拿到过期数据。
- **兜底**：
  1. `service.apply_override()` 必须"DB 事务 + 文件写"两者均成功才 return；任一失败 rollback 并返回 409
  2. 每次 PATCH 后给 sr_文件重新计算 md5，存 `bidding_requests.sr_file_md5`；GET download 时带 md5 头让前端可验证
  3. 任务单 V-B25 是冒烟：修改后再下载，若 E13 不是新值 → 流程硬 bug

---

## 19. 本轮不做清单（对齐业务文档 §6）

| 不做项 | 原因 |
|---|---|
| Customer B / E / Nitori 字段映射 | 业务文档 §3.2 v1.0 只演 Customer A；§9-3 4 家结构差 10 倍 |
| `.xlsm` 宏保留 | Nitori 才有；v2.0 用 `load_workbook(keep_vba=True)` |
| 自动发邮件 | §6 明确"下载 Excel，回信由营业客户端发" |
| 异常阻止提交 | §6 明确"仅高亮不阻止" |
| PKG 中 AI 编价 | §4.1 明确"费率必须来自 Step1 入库" |
| Ocean / LCL 全量接入 | Customer A 全为 Air；RateRepository 留占位方法 |
| 前端组件开发 | 本任务单只定 JSON API 契约；前端迁移由前端 owner 后续 |
| 多段同时填入（上海填 NRT 段） | 业务文档 §9-1 "上海只填 PVG 段" |
| 合并多地回传 | §1.3 "日本本部工作，不在本项目" |
| PDF / Word PKG | 样本均为 Excel |
| 邮件自动抓取 PKG | 实施指令书 §1.2 延后 |
| FX 换汇服务 | Q4 默认不换；v2.0 加 |
| 加价表 UI 维护 | Q2 默认固定比例；v2.0 加 |

---

## 20. 开发大师自检清单（提交 T-B12 前回答）

- [ ] 每个 T-B 任务产出的文件路径 是否都在 §3.1 列表里？
- [ ] 有没有 import `app.services.pkg_parser / pkg_filler / rate_db`？如有 → 违规
- [ ] 有没有 import `app.services.step1_rates.adapters.air` 等非 entities 的内部模块？如有 → 违规（只许 import `entities` 和通过 `RateRepository` 间接查）
- [ ] 有没有硬编码任何具体价格数字？（Customer A 的 49/54 等只能出现在测试 mock 里）
- [ ] openpyxl 是否都是 `load_workbook(..., data_only=True)` 读、`data_only=False` 改？
- [ ] pytest 覆盖了 V-B01..V-B25 的全部 25 条？
- [ ] Q1-Q7 默认值都作为常量写在各 service 顶部并加 `# TODO(Q2): 待楢崎回复后改为 ...` 注释？

---

## 21. 变更记录

| 版本 | 日期 | 作者 | 摘要 |
|---|---|---|---|
| v1.0 | 2026-04-22 | 架构大师 | 首版；基于业务文档 v1.0 + Customer A 黄金样本 + Step1 已交付接口；拆 12 个任务，25 条验收点，明确 Q1-Q7 默认值，复用 ai_client，废弃旧 pkg_parser/pkg_filler/rate_db |

---

**架构任务单完成。开发大师按 §3.1 新建目录，按 §17 顺序动手；测试大师按 §16 写用例；监工抽查 §1.1-1.6 的 file:line 真实性。**
