# SP2 · 海运(ocean) 图片/文本 AI 抽取重写 + 结构化附加费 — 设计

> 日期：2026-06-02 ｜ 分支：`feature/step1-sp2-ocean-ai-extraction`
> 前置：SP1（air 图片/文本 AI 抽取）已实装并合入 main（merge `40651a7`）。本棒沿用 SP1 的链路与工具。

## 1. 背景与目标

step1 做表流水线里，**海运运价从微信图 / 邮件文本进来**时，当前走 `wechat_image_parser` /
`email_text_parser`——它们是**固定箱型 schema**，把附加费（LSS/BAF/EIS…）一股脑塞进 `remarks`，
信息丢失、无法结构化核对。

SP2 像 SP1 对 air 做的那样，**为做表 sea 路径新建一个结构化 AI 抽取器**，把海运报价（箱型价 +
**结构化附加费列表**）抽成多维行，在审核台展示给人核对。

**真实数据形态（已抽样 `资料/2026.05.27/image001.png`、`image002.png` 两张真实海运微信图）：**

- image001：SHA → ICD Ahmedabad，20'/40' = USD 1650/1700 **含LSS**，**目的港 EIS 150/300 到付**，
  NHAVA SHEVA 中转 —— 附加费是**不规则自由文本**（含/到付/稍等）。
- image002：→ NEW YORK，OOCL TULIP/003E，USD 3150 / 40HQ，有效期 3/31 —— 只有运费、无附加费。

结论：海运附加费**不是规整矩阵**，有任意 code（EIS 都不是 FreightRate 现有列）、按箱型分额、
到付/included/TBD 等修饰。固定命名列装不下 → 必须结构化列表保真。

## 2. 范围

### 2.1 本棒做（in scope）
- 新建 `backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py`，提供
  `parse_ocean_image` / `parse_ocean_text`，复用 `ai_extract_util`。
- orchestrator 的 **sea 图片 / sea 文本** 两个分支改指向新抽取器。
- 抽取行 DTO 增加 **结构化附加费列表** `surcharges`。
- `_normalize_sea` 透传新字段（附加费列表、vessel_voyage、via 等）。
- 前端海运审核台增加「附加费」展示列（紧凑多行 + 缺失/TBD 标黄）；i18n 三语。
- 单测（fixture + monkeypatch AI）+ 真机实走 smoke 脚本 `smoke_ocean_ai_extract.py`。

### 2.2 本棒不做（out of scope，明确边界）
- **DB 入库 / 迁移**：附加费不落库，留给 **SP3**。`commit_ocean_rows` 不在本棒改附加费映射。
- **step2 消费附加费**：留给 **SP4**。
- **删除 / 改写旧解析器**：`wechat_image_parser` / `email_text_parser` 原样保留（见 §3）。
- **Excel 路径**：KMTC / NVO / ONE 合约仍走 `rate_parser` / adapters，不碰。

## 3. 关键勘察发现（决定"重写"= 新建而非改旧）

旧解析器**不是只服务做表**，删不得：

- `app/api/v1/ai_parse.py` 的旧「运价导入页」端点 `api_parse_wechat_image` /
  `api_parse_email_text` / .msg 附件路径，直接调 `parse_wechat_image` / `parse_email_text`。
- `wechat_image_parser` 从 `email_text_parser` import `_match_carrier` / `_parse_date_str`。
- `rate_parser.py` import `email_text_parser._match_carrier` / `_create_carrier`。
- `rate_batch_service.py` 用 `parse_email_text` 做 Excel 纯文本兜底（第 2 段）。

因此 SP2 **照搬 SP1 模式**：新增 `ocean_ai_extractor`（与 `air_ai_extractor` 平行），
只改 orchestrator 的 sea 分支路由（`orchestrator.py:110` 图片、`:119-120` 文本）。
旧文件、旧端点、共享 helper 全部不动。

## 4. 设计

### 4.1 抽取器接口（镜像 air_ai_extractor）

```python
# backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py
def parse_ocean_image(image_path: str, db: Session | None = None, extra_context: str = "") -> dict[str, Any]
def parse_ocean_text(text: str, db: Session | None = None) -> dict[str, Any]
```

返回与 air 同构：

```python
{
  "parsed_rows": list[dict],   # 多维行 DTO（见 4.2）
  "total_rows": int,
  "warnings": list[str],
  "source_type": str,          # "ocean_image" | "ocean_text"
  "file_name": str,
}
```

- 复用 `ai_extract_util.chat_json_with_retry(call, retries=1)` + `parse_json_array`。
- AI 调用：图片 `ai_client.chat_with_image(...)`，文本 `ai_client.chat(...)`，`temperature=0.0`。
- **异常不抛**：解析失败 / AI 异常 → 返回 `_empty()`（空行 + warning），orchestrator 标 `skipped`。

### 4.2 抽取行 DTO（每条「航线×箱型组」一行）

```python
{
  "origin": "SHANGHAI",          # POL
  "destination": "ICD AHMEDABAD",# POD（含内陆点）
  "carrier": "KMTC" | None,      # 船司，缺则 None → needs_review
  "vessel_voyage": "OOCL TULIP/003E" | None,
  "via": "NHAVA SHEVA" | None,   # 中转港；直达则 None
  "is_direct": bool,
  "container_20gp": 1650.0 | None,
  "container_40gp": 1700.0 | None,
  "container_40hq": 3150.0 | None,
  "container_45": None,
  "currency": "USD",
  "valid_from": "2026-03-22" | None,
  "valid_to": "2026-03-31" | None,
  "transit_days": int | None,
  "surcharges": [               # ★ 结构化附加费列表（本棒核心）
    {
      "code": "EIS",            # 附加费代码/名（任意，原样）
      "amount_20": 150.0 | None,
      "amount_40": 300.0 | None,
      "currency": "USD" | None,
      "payment": "collect" | "prepaid" | None,  # 到付/预付
      "included": bool,         # 是否已含在运价里（如"含LSS"）
      "note": "稍等/TBD" | None
    },
  ],
  "remark": str | None,
  "needs_review": bool,
  "source_file": str,
  "source_type": "ocean_image" | "ocean_text",
}
```

**image001 期望抽取**（一行，20'+40' 同一报价）：
`surcharges = [{code:"LSS", included:true}, {code:"EIS", amount_20:150, amount_40:300, payment:"collect", included:false}, {code:"转运费", note:"稍等/TBD", included:false}]`，
该行 `needs_review=true`（转运费 TBD + 目的港为内陆点）。

**image002 期望抽取**：`container_40hq=3150, carrier="OOCL", vessel_voyage="OOCL TULIP/003E", valid_to="2026-03-31", surcharges=[]`。

### 4.3 Prompt 要点（system prompt）

- 输出**纯 JSON 数组**，无任何说明文字。
- 每条「目的港 × 船司 × 箱型组」一行；同图多目的港 / 多船司拆多行。
- 箱型价：键 `container_20gp/40gp/40hq/45`，无则不写（None）。
- **附加费**：抽成 `surcharges` 列表，每项给 `code`；金额按箱型分 `amount_20/amount_40`；
  "含X"→`included:true`；"到付/prepaid"→`payment`；"稍等/议价/TBD"→`note` 且不要瞎填金额。
- 不确定/缺失**留空，不猜**。
- 起运港默认按上下文（多为 SHANGHAI/PVG），但原文有写以原文为准。

### 4.4 orchestrator 改动

```python
# orchestrator.py  add_file() 内
elif ext in _IMAGE_EXTS:
    if session.template_type == "air":
        parsed = air_ai_extractor.parse_air_image(file_path, db)
    else:
        parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)   # was wechat_image_parser
elif ext in _TEXT_EXTS:
    if session.template_type == "air":
        parsed = air_ai_extractor.parse_air_text(text, db)
    else:
        parsed = ocean_ai_extractor.parse_ocean_text(text, db)         # was parse_email_text
```

`_normalize_sea` 增加透传：`surcharges`、`vessel_voyage`、`via`、`is_direct`（air 行无这些键 → None，不影响）。
现有 `freight_20/40`、`lss_cic/baf`、`container_*` 兼容字段保留不动（前端旧列不破）。

### 4.5 审核台改动（前端，仅预览）

- 海运审核台已是动态列（A4）。新增一列 **「附加费」**：单元格把 `surcharges` 渲染成紧凑多行，
  例：`LSS 含 · EIS 150/300 到付 · 转运 TBD`。
- 任一附加费 `note` 含 TBD/稍等 或 `needs_review=true` → 该单元格/行标黄。
- i18n：zh/ja/en 三份补「附加费 / 付加料金 / Surcharges」等键。
- **不入库**：审核台只展示，不提供附加费的"采用入库"（箱型价仍走现有 `commit_ocean_rows`，
  附加费列在本棒只读预览，SP3 再接入库）。

### 4.6 needs_review 规则（沿用 SP1）

行标黄当满足任一：缺 carrier / 缺有效期 / 箱型价全空 / 任一附加费 `note` 含「稍等/议价/TBD/到付未定」
/ 目的港疑似内陆点（via 非空且 POD 非标准港）。

## 5. 测试策略

### 5.1 单测（CI 可跑，不依赖真 AI）
- `test_ocean_ai_extractor.py`：monkeypatch `ai_client.chat_with_image` / `chat` 返回**手写 JSON**
  （含 image001 那种不规则附加费），断言 DTO（箱型价、surcharges 列表各字段、needs_review）。
- `test_ocean_ai_extractor.py`：JSON 解析失败 → 返回 `_empty()` + warning（不抛）。
- `test_orchestrator.py`：sea 图片/文本分支路由到新抽取器（monkeypatch），`_normalize_sea` 透传 surcharges。
- 回归：全后端 pytest 维持绿（除 3 个本机无 vLLM 端点的 `test_ai_client::test_vllm_*`，老基线）。

### 5.2 真机实走（留服务器，开发机连不上百炼）
- 新增 `backend/scripts/smoke_ocean_ai_extract.py`：对 `image001.png` / `image002.png` 跑真 AI，
  肉眼核对抽出的箱型价 + 附加费列表是否对。与 SP1 的 `smoke_air_ai_extract.py` 同形态。
- 列入 Codex 部署后的验收项（或用户在通网机器自测）。

## 6. 风险与边界

- **附加费 code 不规范**：原样保留 code（EIS/转运费/中文都行），不强行归一——归一留给 SP3 入库时再定。
- **多目的港/多箱型一图**：靠 prompt 拆行；拆错由审核台人工兜底（needs_review）。
- **真机未验**：本棒单测充分但真 AI 行为只有 2 张样本，prompt 可能需按真机结果微调（同 SP1 经验）。
- **前端附加费列只读**：刻意不做入库，避免与 SP3 的 schema 决策冲突；审核台改价仍只对箱型价生效。

## 7. 与 SP3 / SP4 的衔接

- DTO 的 `surcharges` 结构即为 SP3 入库的输入契约；SP3 决定落库形态（稀疏 JSON 列 or 独立
  `OceanSurcharge` 表）时直接消费本结构。
- SP4（step2 投标包消费附加费 + 按泡比/箱型选价）依赖 SP3 入库后的数据，不依赖本棒。
