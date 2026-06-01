# SP1 设计：Air AI 抽取实走（图片 + 文本，结构化多维行）

- 日期：2026-06-01
- 分支：`feature/step1-review-desk`（沿用）
- 状态：设计已与用户对齐，待落实现计划
- 关联记忆：`step1-ai-extraction-path-status`、`step1-air-ees-format`、`step2-air-bid-format`、`mvp-minimal-scope-remind`（2026-06-01 已去掉 MVP，改完整实现）

## 0. 背景与定位

step1「做表」(RateSheetBuilder) 链路里，**唯一用到 AI 的两条入料是图片与文本**：

| 入料 | 路由到 | 用 AI | 现状 |
| ---- | ------ | ----- | ---- |
| Excel(air) | `air_extractor.extract_air_rates` | 否（纯解析） | tier/周表 ✓ |
| Excel(sea) | `rate_parser.detect_and_parse` | 否 | 箱型 ✓ |
| PDF | `rate_parser_pdf.detect_and_parse_pdf` | 否 | 箱型 ✓ |
| **图片** | `wechat_image_parser.parse_wechat_image` | **是（视觉）** | **只海运箱型** |
| **文本/邮件** | `email_text_parser.parse_email_text` | **是（文本）** | **只海运箱型** |

两个 AI 抽取器的 prompt 与输出 schema **全是海运箱型**（`container_20gp/40gp/40hq/45`），没有 air 的重量档。`orchestrator.add_file` 路由图片/文本时**不分 air/sea**。结果：air session 上传图片/邮件 → 被当海运解析 → `_normalize_air` 拿到空壳行。这就是「air 图片/文本抽取未对接」。

测试期 AI provider 已切到**阿里云百炼 Qwen-VL**（`.env`：`AI_PROVIDER=vllm` 走 OpenAI 兼容路径 + dashscope base_url + key + `chat_template_kwargs=false` + `no_think=false`；DB `app_settings.vllm_base_url` 覆盖项已清空）。正式上线换回本地 vLLM（`.env` 注释块保留）。**本机当前 dashscope 不可达（DNS fake-IP），实走验证由用户在通网机器完成**；开发期全程 mock AI 做 TDD。

### 整体目标分解（本 spec 只做 SP1）

用户要求把 AI 抽取做全、一路到入库 + step2。完整链路跨 step1+step2，是 4~5 个子系统，超出单个 spec，故拆分：

| # | 子项目 | 依赖 | 本 spec |
| - | ------ | ---- | ------- |
| **SP1** | **Air AI 抽取实走**（图片+文本 → 结构化多维行 → 审核台 → 入库 air_tier） | 无（下游已通） | ✅ 本文 |
| SP2 | Ocean AI 抽取重写 + 附加费矩阵 | SP1 地基 | 后续 |
| SP3 | 附加费入库（Surcharge/FreightRate 持久化） | SP2 | 后续 |
| SP4 | step2 投标包消费附加费 | SP3 | 后续 |

SP1 自包含：下游 `air_tier` 入库（`commit_tier_rows`）、step2 Customer A 按货量取价已在前阶段做通，air 抽取器一接上即端到端可跑。

## 1. 范围

**做（SP1）**
- air session 上传的**图片**（微信图/截图）与**文本/邮件**（`.txt/.md` 及粘贴正文）的 AI 抽取。
- 方案 A：**结构化多维行** —— 把 air 元料金图（重量档 × 泡比 × 货类/包装）保真建模。
- 共享健壮性地基：稳健 JSON 解析 + 一次重试、百炼 max_tokens 调大、币种默认、air/sea 路由分流。
- 打通到：归一 → 审核台（动态列）→ 入库 `air_tier`（新列）→ 仪表盘计数。

**不做（defer 到 SP2~SP4）**
- ocean 图片/文本 prompt 重写、附加费矩阵抽取。
- 附加费持久化。
- step2 按泡比/货类/包装选价（本轮只保证 step2 现状不被打破）。
- 扫描件 OCR、Excel/PDF 抽取改动（已是纯解析，不动）。

## 2. 关键决策（已与用户确认）

1. **建模 = 方案 A 结构化多维行**：泡比/货类/包装/航司作为**结构化字段**挂在行上，重量维仍用 `tier_prices`。同目的港多行 → 复用 `multi_flight_pick` → 审核台展开人工确认。保真、不丢数据、为 SP4 按泡比选价留好结构。
2. **air_tier 加列**（非塞 JSON extras）：`AirTierRate` 加 `cargo_class / packing / density / carrier` 四个 nullable 列 + alembic 迁移。代价是迁移，换来 step2 future 可查询。
3. **air 抽取器图片+文本合一个模块**：`air_ai_extractor.py` 两入口共享 prompt/schema，省重复。
4. **`.env` max_tokens 直接调大**（百炼上下文足够）。

## 3. 抽取行 schema（parsed_rows 元素）

```python
{
  "origin": "PVG",                  # 默认按文件(图头"PVG始发")；内容明示则覆盖
  "destination": "LAX",             # IATA 三字码(沿用 air_ees 的 _clean_dest 思路)
  "carrier": "CK/CA/D0/5Y/KE",      # 航司代码列原文
  "cargo_class": "普货",            # 货类: 普货 / 快件 / 9610-9710
  "packing": "托",                  # 包装: 托 / 散 / 托散 / 混装
  "density": "1:167",               # 泡比(结构化字符串)
  "tier_prices": {45: 60.0, 100: 60.0, 500: 60.0, 1000: 60.0},  # 重量档→价，自适应表头档
  "currency": "CNY",                # air 默认随起运港: PVG→CNY / NRT→JPY；内容明示则覆盖
  "effective_week_start": "2026-05-26",  # 图头 Effective Date 起；沿用既有键名(下游已认)
  "effective_to": "2026-05-29",     # 可选
  "remark": "...",                  # 含油/全程时效/操作代码说明等
  "multi_flight_pick": True,        # 同目的港多行 → 审核台人工选/确认
  "source_file": "Weixin Image_xxx.png",
  "source_type": "air_image",       # 或 "air_text"
}
```

说明：
- `tier_prices` 键随图自适应（图一为 100/500/1000；图二为 45/100/500/1000），沿用 air_ees「任一档有价即留行、议价/`/`/留空不入 dict」规则。
- 字段命名尽量与 `_normalize_air` / air_ees 既有键对齐（`destination_port_name` 由归一兜底；抽取器直接给 `destination` IATA 码，归一读 `destination`）。

## 4. 组件清单

### 新增
- `backend/app/services/step1_rates/sheet_builder/air_ai_extractor.py`
  - `parse_air_image(image_path, db, extra_context="") -> dict`（走 `ai_client.chat_with_image`）
  - `parse_air_text(text, db) -> dict`（走 `ai_client.chat`）
  - 共享 `SYSTEM_PROMPT`（多维 air schema）、共享行构建/清洗（IATA 码、币种默认、tier 归一、`multi_flight_pick`）。
  - 返回结构与现有 parser 一致：`{batch_id, parsed_rows, total_rows, warnings, source_type, file_name, ai_raw_response}`，识别失败不抛、返回空 `parsed_rows` + warning。
- `backend/app/services/ai_extract_util.py`
  - `parse_json_array(raw: str) -> list`：去 markdown 壳 → 抓首个 `[…]` → 容尾逗号/截断尽力修复 → `json.loads`；失败抛 `JsonExtractError`。
  - `chat_json_with_retry(call: Callable[[], str], *, retries=1) -> list`：调一次抽取→解析；解析失败重试一次（同 prompt）；仍失败抛。
  - air（SP1）与 ocean（SP2）都复用。

### 改动
- `orchestrator.add_file`：
  - 图片：`template_type=="air"` → `air_ai_extractor.parse_air_image`（`source_type="air_image"`）；否则 `wechat_image_parser.parse_wechat_image`。
  - 文本：`template_type=="air"` → `air_ai_extractor.parse_air_text`（`source_type="air_text"`）；否则 `email_text_parser.parse_email_text`。
- `orchestrator._normalize_air`：透传 `carrier / cargo_class / packing / density`（None 安全；EES/周表行无这些键 → None，不影响）。
- `backend/app/models/air_tier_rate.py`：加 `cargo_class / packing / density / carrier`（均 `String`，nullable）。
- alembic 迁移：`backend/alembic/versions/20260601_xxxx_air_tier_dims.py`（add_column 四列；链对上一个 head）。注：团队 sqlite 走 `init_db`/`create_all`（模型改了自动生效），alembic 迁移供 PG。
- `db_writer.commit_tier_rows`：`AirTierRate(... cargo_class=r.get("cargo_class"), packing=..., density=..., carrier=...)`；同时把 `effective_to=_to_date(r.get("effective_to"))` 写上（模型已有该列，现状未写；air 图头 Effective Date 带终止日）。
- `rate_repository.query_air_tier` / `_tier_to_step1_row`：新字段塞进 `Step1RateRow.extras`（step2 future 用；本轮只保证不破）。
- 前端 `frontend/src/pages/RateSheetBuilder.tsx`：
  - `PreviewRow` 加 `cargo_class / packing / density`（`carrier` 已有）。
  - air 列加**动态列** 货类/包装/泡比/航司（复用现有 present-if-any 判定：全表至少一行有值才渲染；EES/周表行无值 → 列自动隐藏）。
  - i18n：`rateSheet.colCargoClass / colPacking / colDensity` 三语（zh/ja/en）；`colCarrier` 已存在则复用。
- `backend/.env`：`AI_MAX_TOKENS_EXTRACT_JSON` 1024→4096、`AI_MAX_TOKENS_CAP` 1536→8192（百炼多维多行防截断）。

## 5. 数据流

```
图片/文本(air session)
  → air_ai_extractor (ai_client + ai_extract_util 稳健JSON+重试)
  → parsed_rows(§3)
  → orchestrator._normalize_air (带新结构化字段)
  → 同目的港多行标 needs_review (multi_flight_pick → needs_review_by_destination)
  → 审核台 (动态列展示 货类/包装/泡比/航司 + 档位价；人工改/删/确认)
  → POST /rate-sheet/{sid}/commit → commit_tier_rows → air_tier 入库(新列)
  → 仪表盘计数(get_rate_stats 已计 air_tier)
  → step2 query_air_tier 可见(泡比选价 = SP4)
```

## 6. 错误处理 / 健壮性

- **JSON 截断/脏**：`ai_extract_util.parse_json_array` 去壳+抓数组+尽力修复；`chat_json_with_retry` 失败重试一次；仍失败 → 该批 `parsed_rows` 空 + warning 透传审核台（**不抛、不丢整会话**，沿用现有 try/except 风格）。
- **max_tokens**：百炼调大，规避「多行被截断 → JSON 不完整 → 整批丢」（当前最易炸点）。
- **币种**：air 默认随起运港（PVG→CNY、NRT→JPY）；图/文本明示币种则覆盖。
- **识别不全**：某格留空/议价/`/` → 不入 `tier_prices`；只要任一档有价该行保留（沿用 air_ees）。
- **多维缺失**：cargo_class/packing/density 缺 → None（不阻断；审核台对应列对该行空）。
- **网络**：dashscope 实走对 2 张真实微信图的验证 = 用户在通网机器跑；开发期 mock AI，逻辑零依赖真调用。

## 7. 测试策略（TDD，mock AI）

- **air_ai_extractor**（mock `ai_client`）：喂固定 JSON（含 LAX 多泡比 1:100/1:167/1:1000、ORD、AMS）→ 断言行 schema 正确（destination/carrier/cargo_class/packing/density/tier_prices/currency/multi_flight_pick）；图片与文本两入口共用断言。
- **ai_extract_util**：markdown 去壳、抓首个数组、尾逗号修复、截断容错、彻底坏 → 抛 + 重试路径。
- **_normalize_air**：新字段透传；EES/周表行无新键 → None 不报错（回归）。
- **commit_tier_rows**：写入四个新列；周表行仍跳过计数（回归）。
- **query_air_tier**：同 dest 多行（不同泡比）返回多行不崩；新字段进 extras。
- **路由**：image+air→air 抽取器、image+sea→海运抽取器、text 同理。
- **回归**：全后端 `pytest` 绿（既有 378 passed 基线，3 个 vLLM 环境失败无关）；前端 `npm run build` 过。
- **实走 smoke（待网络）**：留脚本/说明，对 `资料/2026.05.27/air/Weixin Image_*.png` 端到端跑通，交用户在通网机器验。

## 8. 验收标准

- 后端单元/回归测试全绿；前端 build 过。
- 代码审计确认：air session 的图片/文本走 air 抽取器、产结构化多维行、归一带新字段、审核台显新动态列、commit 写新列、step2 不破。
- 交付一份「实走 smoke 说明」：通网机器上对 2 张真实微信图跑通后，审核台能看到 LAX 等的多泡比行 + 档位价。

## 9. 未决 / 后续（非 SP1 阻塞）

- **泡比 → 计费选价**（SP4）：step2 投标包按货物密度选对应泡比行的规则，待福山确认；SP1 只把泡比结构化存好。
- **含油/净价**：air 价多为含油 All-in，净价拆分等真有入札要求再做（沿用 air_ees 既有结论）。
- **区域/多港单元格**：沿用 air_ees「取首三字码、其余审核台人工补」的既有边界。
- **air 文本真实样本缺失**：现有真实样本只有图片（长荣那段是 ocean）；air 文本入口先按设计做 + mock 测，真实样本到位后再校准 prompt。
