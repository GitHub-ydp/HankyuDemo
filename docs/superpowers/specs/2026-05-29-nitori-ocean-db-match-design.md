# Nitori 海运按 DB 运价匹配 — 设计 (MVP)

- 日期：2026-05-29
- 分支：feature/step1-review-desk
- 状态：范围已与用户对齐，待转实现计划 (writing-plans)
- 关联：福山确认(`邮件/2026.05.27/微信沟通.md`)、记忆 step2-air-bid-format、mvp-minimal-scope-remind

## 背景与目标
福山确认：step2 投标包按**我们的运价数据(DB)**匹配，不用投标包 zip 内的成本文件。
- Air(Customer A) 已合规：`rate_matcher` → `query_air_tier` 走 DB。
- **Nitori(海运)现仍读 zip 内成本表(`NitoriCostBook`，含 FCL sheet 的 xlsx)** → 本设计把它切到 DB 运价数据。

## 关键决策
1. **落表 = 复用 `FreightRate`(FCL)**。理由：`Sea Net Rate(空白)` 模板的 FCL 列 ≈ FreightRate 列(模型本就照此模板设计)；不新建表。LCL 本版不做。
2. **范围 = Nitori 倒逼**：只覆盖 Nitori 投标包用到的 lane/箱型，不做通用全量海运做表。
3. 运费币种按 **USD**(FreightRate 默认)；CNY 杂费本版不入。
4. 多起运港单元格只取**上海(CNSHA)**(起运港按文件)。
5. 箱型映射：Nitori `20F`→`container_20gp`、`40HC`/`40F`→`container_40hq`(40HC=40HQ=HC 同物)。

## 架构 / 数据流
```
做表(已有 Sea Excel 链路：kmtc/NVO → rate_parser)
 → _normalize_sea【增强】：保留结构化三箱型价(20gp/40gp/40hq)+carrier+transit
     (上游 parsed row 本就有；现被合并成 freight_40/丢弃 → 改为不丢)
 → commit_ocean_rows【新，仿 db_writer.commit_tier_rows】：
     港口 text→port_id(_resolve_port)、carrier→id；写 FreightRate；批次 supersede 旧 active
 → query_ocean_fcl【新，实现 rate_repository 现有 stub】：
     origin=上海 / dest(+箱型) 查 active FreightRate → Step1RateRow
 → NitoriProfile.match()【改】：调 query_ocean_fcl 取代 NitoriCostBook；箱型映射；×1.15 markup
```

## 组件（各自单一职责）
- `_normalize_sea`(改)：parsed sea row → 保留 dest/carrier/container_20gp/40gp/40hq/transit/effective。
- `commit_ocean_rows(rows, db)`(新)：会话/审核行 → FreightRate；返回 batch_id + 计数；仅写有箱型价的行；supersede 同类旧 active 批。
- `RateRepository.query_ocean_fcl(*, origin, destination, effective_on=None, ...)`(实现)：active FreightRate 候选 → Step1RateRow(箱型价进 extras)。
- `NitoriProfile`(改)：注入 `repo`；match 用 query_ocean_fcl；cost-book 回退仅作兜底/旧测试(保留与否待福山验收)。

## 本版最小收口（MVP 边界 — 重要，面向客户必须说明）
**做**：上述 backend 闭环(FCL，Nitori 用到的 lane)——归一增强 + 入库 FreightRate + query_ocean_fcl + Nitori 切 DB。
**不做(defer，"往上加")**：
- Arbitrary / 内陆附加费(NVO `Arbitrary` sheet)
- LAX PDF 源抽取
- 全附加费矩阵(EBS / YAS / CAF / ISPS / Equipment / Booking / THC / DOC)
- CNY 杂费(混币种存储)
- LCL(`LclRate`)
- 前端审核台 ocean 列(可视化勾选/编辑)——本版入库走 commit 接口/最小触发

⚠️ demo/交付/讲解时务必复述上述边界，避免客户把"未做"当缺陷(见记忆 mvp-minimal-scope-remind)。

## 测试策略 (TDD)
- `commit_ocean_rows`：港口/carrier 解析、箱型价写入、supersede、跳过无价行。
- `query_ocean_fcl`：active 过滤、origin/dest 匹配、箱型返回。
- `NitoriProfile.match` 走 repo：filled/no_rate、40HC→40hq、markup ×1.15。
- 真实文件：2026.05.27 Sea 元料金 做表→入库→Nitori 投标包取价 端到端抽样对数。

## 风险 / 开放(非阻塞)
- 多港单元格("Los Angeles, Long Beach")港口解析可能丢副港 → 沿用 air 首码策略，审核补。
- Nitori 投标包实际 lane 与 DB 覆盖的差集 → no_rate，属正常。
- cost-book 回退是否保留：倾向保留兜底，福山验收再定。
