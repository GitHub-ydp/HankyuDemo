# 指定数据下载（按客户模板回填海运运价）— 设计

- 日期：2026-06-09
- 状态：设计已确认，待写实现计划
- 相关分支：feature/step1-sp2-ocean-ai-extraction
- 提出方：福山（阪急阪神）；拍板：邓总 → 张东旭
- 需求原始记录：`资料/2026.06.08/新要求.txt`
- 客户模板样本：`资料/2026.06.08/Sea Net Rate_2026_May.15th - May.31st (空白　着地あり).xlsx`
- 填好数据的对照样本：`资料/2026.05.26/Sea Net Rate_2026_May.15th - May.31st (Ocean).xlsx`

## 1. 背景与需求

做表（运价表生成）现有下载链路：用户选 sea/air 模板 → 上传报价杂料 → AI 抽取 → 审核/编辑 →
点「下载」，系统用**内置空白模板** `sea_blank.xlsx` 顺序填**全部**目的港后下载。

福山的新需求：她在一份**保留了目的港名、价格留空**的模板（"着地あり"=有目的港）上，
只想拿到她**指定的那些目的港**的报价。即：
- 运价表生成页**新增一个按钮「指定数据下载」**；
- 点开后弹窗，让她**上传自己的模板文件**；
- 系统**只把她模板里列出的目的港**的价格填进去，其它港不输出；
- 下载回来的就是**她那份模板**（保留她的版式）。

她这次特别要用模板的**第 2 个 sheet**：`FCL N RATE OF OTHER PORTS`（上海出口 → 非日本港的整箱 FCL 净价）。

### 该模板三个 sheet 的业务含义
- `JP N RATE FCL & LCL`（第 1 页）：上海 → **日本港**（东京/横滨、大阪/神户）整箱 FCL 净价。
- `FCL N RATE OF OTHER PORTS`（第 2 页，**本次目标**）：上海 → **非日本港**整箱 FCL 净价
  （香港、台湾、韩国、东南亚、欧美等 28 个目的港）。
- `LCL N RATE`（第 3 页）：拼箱 LCL 净价，按重量/体积计费，结构与列完全不同（另一种运价类型）。

## 2. 已确认的需求决策

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 数据来源 | **当前会话刚抽取/审核好的 rows**（= 现有「下载」用的 `buildFinalRows()`） |
| 2 | 输出忠实度 | **忠实回填她上传的模板**（保留她的三个 sheet/表头/列含义/格式） |
| 3 | 行槽位规则 | **以数据为准，按港动态生成行**；她预留的行数不作约束（标签已被她删空，行数是原件残留） |
| 4 | 匹配反馈 | **对不上/无数据 → 留空，不额外报告**；但尽量用别名归一+多名拆分把能对上的都对上 |
| 5 | sheet 范围 | **只做 sheet2 / OTHER PORTS**；sheet/列映射做成配置，以后扩 JP/LCL 只改配置 |
| 6 | 40 箱型 | 40GP 与 40HQ 合成一行「40FT/40HQ」，**取 40HQ 价**（40HQ 空则回退 40GP） |
| 7 | 无数据的港 | **保留港名 + 1 行空行**（让她看到这个港没报到价） |

### 两个事实约束（先讲明）
- **结构化附加费正好对得上 sheet2**：抽取出的海运行带 `surcharges` 结构（每项 `code`=LSS/BAF/CIC/CAF…
  + 按箱型金额 `amount_20`/`amount_40` + `included`/`payment:collect`/`note` 标记），可逐项映射到
  sheet2 的 E=LSS / F=BAF / G=CIC / H=CAF 四列，连原始样本的 `Incl.`/`Collect` 写法都能还原。
- **只能填抽到的东西**：sheet2 后半段的目的港当地杂费（Booking/THC/DOC/ISPS/设备费，L–P 列）
  属固定杂费、**不在报价抽取范围内** → 这些列留空（与"只留空不报告"一致）。

## 3. 架构与组件边界

新增 3 个相互隔离的单元，**完全不动**现有"顺序填内置模板"的下载链路：

```
前端 RateSheetBuilder.tsx
  └─[新] 「指定数据下载」按钮 → 弹窗(选她的模板.xlsx + 确认)
         │  POST multipart: template 文件 + rows(当前会话审核后最终行)
         ▼
后端 api/v1/rate_sheet.py
  └─[新] POST /rate-sheet/{session_id}/download-into-template   ← 薄 HTTP 适配
         │  校验 session → 读上传 bytes + rows → 调回填器(run_in_threadpool) → 流式 xlsx
         ▼
services/step1_rates/sheet_builder/template_refill.py           ← [新] 纯函数核心
  refill_into_template(template_bytes, rows, *, profile) -> (bytes, filename)
     ├─ _scan_ports(ws, profile)            扫 A 列拿目的港(按序) + 数据区范围
     ├─ _group_rows_by_port(rows)           canonicalize 归并
     ├─ _rebuild_other_ports_sheet(...)     以数据为准重排行块 + 重建合并/样式
     └─ _surcharge_cell(surcharges,...)     结构化附加费 → LSS/BAF/CIC/CAF 单元格
         │  复用：port_normalizer.canonicalize / writers.base.safe_set
         ▼
填好的 workbook bytes（她的三个 sheet 都在，只有 OTHER PORTS 数据区被重写）
```

| 单元 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `template_refill.py`（核心） | 把 rows 忠实回填进上传模板的 OTHER PORTS 页 | 模板 bytes、rows、sheet profile | 填好 xlsx bytes + 文件名 | openpyxl / port_normalizer / safe_set；**无 HTTP/DB/session** |
| `rate_sheet` 新端点 | HTTP 适配 | multipart(file+rows) | StreamingResponse | 校验 session、调核心 |
| 前端 Modal + api 方法 | 选文件 + 触发下载 | 用户选的 .xlsx | 浏览器下载 blob | antd Upload/Modal、axios |

- 核心 `refill_into_template` 是**纯函数**（bytes + rows 即可跑），可用 fixture 脱离 HTTP/DB 单测。
- **sheet profile 做成配置**（sheet 名/表头行/数据起始行/列映射/箱型行规则），本次只配 OTHER PORTS。
- 与现有 `template_filler.fill_template` **并存、零改动**，老「下载」按钮行为不变。

## 4. 数据流与端点契约

### 链路
1. 用户走完做表：选 sea 模板 → 上传报价 → AI 抽取 → 审核/编辑（勾选+改值）。
2. 点「指定数据下载」→ 弹窗。
3. 弹窗用 antd Upload 选她的模板 .xlsx（`beforeUpload` 返回 false，仅暂存 state、不自动传）。
4. 点「确认下载」：前端组 FormData：`template` = 她选的文件，`rows` = `JSON.stringify(buildFinalRows())`；
   `POST /rate-sheet/{session}/download-into-template`（responseType=blob，timeout=180s）。
5. 后端校验 → 回填 → 流式返回 xlsx。
6. 前端拿 blob 触发浏览器下载（文件名 = 她上传名去扩展名 + `_filled.xlsx`），关弹窗、成功提示。

### 端点
```
POST /rate-sheet/{session_id}/download-into-template
Content-Type: multipart/form-data
  template: UploadFile  (.xlsx)
  rows:     str         (Form 字段，JSON 编码的 list[dict]，= buildFinalRows())

成功: 200, application/vnd...spreadsheetml.sheet
      Content-Disposition: attachment; filename*=UTF-8''{原名}_filled.xlsx
      Body: 填好的 workbook（三个 sheet 都在，只有 OTHER PORTS 数据区被重写）
```
- `rows` 走 Form 字段（JSON 字符串）而非 JSON body：multipart 要同时带文件 + 结构化数据；服务端
  `rows: str = Form(...)` 后 `json.loads`。与现有 `POST /download` 的 `body.rows` 是同一份数据。
- 前端按钮可见性：仅 `templateType === 'sea'` 且 `summary && keptCount > 0` 时显示；端点兜底校验
  `session.template_type == 'sea'`。

### 错误响应（统一 ApiResponse）
| 场景 | 返回 |
|---|---|
| session 不存在/过期 | 404 "会话不存在或已过期，请重新创建" |
| 不是 .xlsx / openpyxl 打不开 | 400 "模板文件无法解析，请上传 .xlsx 模板" |
| 缺 `FCL N RATE OF OTHER PORTS` 页 | 400 "模板缺少 'FCL N RATE OF OTHER PORTS' 工作表" |
| rows JSON 解析失败 | 400 "提交的运价数据格式有误" |
| 非 sea 会话 | 400 "指定数据下载仅支持海运模板" |

成功提示用通用文案（如"已生成并下载"），不弹匹配明细。

## 5. 核心回填算法

### 5.1 Sheet Profile（配置，本次只配 OTHER PORTS）
```python
OTHER_PORTS_PROFILE = {
  "sheet_name": "FCL N RATE OF OTHER PORTS",
  "header_row": 8, "data_start_row": 9,
  "cols": {                      # 1-based 列号
    "destination":1, "carrier":2, "container":3, "freight":4,
    "lss":5, "baf":6, "cic":7, "caf":8,
    "sailing":9, "via":10, "transit":11,                       # sailing 不抽取→留空
    "booking":12,"thc":13,"doc":14,"isps":15,"equipment":16,   # 本地杂费→全留空
    "rmks":17,
  },
  "container_rows": [            # 每船司固定 2 行
    {"label":"20FT",      "freight":["container_20gp"],                  "amt":"amount_20"},
    {"label":"40FT/40HQ", "freight":["container_40hq","container_40gp"], "amt":"amount_40"},
  ],  # 40 行：先取 40HQ，空则回退 40GP
  "surcharge_cols": {"lss":"LSS","baf":"BAF","cic":"CIC","caf":"CAF"},
}
```

### 5.2 五步
**① 扫港**：从 A9 往下，A 列非空即一个目的港，按序得 `whitelist`（样本 28 个）。由 A 列合并范围算
`data_end_row`（最后一个港块末行），界定要清空的数据区 `[data_start_row, data_end_row]`；表头 1–8 行、
页脚区不碰（已确认该页 109 行起无内容、无页脚备注）。

**② 抓样式**：她把值删了但格式（边框/字体/对齐/数字格式）还在。从 row 9（20FT 行）、row 10（40 行）
各列抓一份单元格样式做"行模板"。列宽是列级属性，重排行不影响。
> 不用 `insert_rows`：openpyxl 的 `insert_rows` 不会正确搬移合并格与行样式（公认的坑）。
> 用"清空→按抓到的样式顺序重写"确定性强，规避整类合并/样式损坏 bug。

**③ 清数据区**：unmerge 掉 `[data_start_row, data_end_row]` 内所有合并格，清空这些单元格的值
（样式已在 ② 抓走）。

**④ 按港归并数据**：`by_port[canonicalize(dest)] = [row, ...]`（一港可能多船司多行）。

**⑤ 顺序重排（以数据为准）**
```
r = data_start_row
for port in whitelist:
    matched = by_port.get(canonicalize(port), [])   # 含多名拆分见 6.2
    block_start = r
    if not matched:                                 # 报价无该港
        A(r)=port; r += 1; continue                 # 港名占 1 行，价格留空
    for row in matched:                             # 每船司 2 行
        # 20FT 行
        A(r)=港名(块首); B(r)=carrier; C(r)="20FT"
        D(r)=container_20gp
        E/F/G/H(r)=_surcharge_cell(row.surcharges, LSS/BAF/CIC/CAF, container=20)
        J(r)=via; K(r)=transit; Q(r)=remark; 套 20FT 行样式
        # 40FT/40HQ 行
        C(r+1)="40FT/40HQ"; D(r+1)= 40HQ or 40GP
        E/F/G/H(r+1)=_surcharge_cell(..., container=40); 套 40 行样式
        合并 B/I/J/K/Q 跨这 2 行(复刻她每船司合并样式)
        r += 2
    合并 A 跨 [block_start, r-1]                     # 港名竖向合并整个港块
# 本地杂费列 L–P 全程不写 → 留空
```

### 5.3 附加费 → 单元格（`_surcharge_cell`，还原原始样本写法）
按 code 在 `row.surcharges` 里找 LSS/BAF/CIC/CAF：
- `included:true` → 写 `"Incl."`
- `payment:"collect"` → 写 `"Collect"`
- 有金额 → 20FT 行取 `amount_20`、40 行取 `amount_40`（无分箱型则取单值）
- 只有 `note`（如 "subject to…/稍等"）→ 写该文本
- 都没有 → 留空
- 兜底：`surcharges` 为空的老行 → 用扁平 `lss_cic` 落到 LSS 列

## 6. 错误处理与边界

### 6.1 入口/文件
- 只收 `.xlsx`（.xlsm 拒收）；模板无任何港（whitelist 空）→ 不报错，原样返回。
- 其余见 §4 错误响应表。

### 6.2 匹配边界（全部 → 留空，不报告）
| 情况 | 处理 |
|---|---|
| 别名/大小写/`PUSAN`·`KAOHSIUNG CITY` | `port_normalizer.canonicalize` 归一后匹配 |
| 双名/带括号：`MADRAS / CHENNAI`、`LONG BEACH⏎LOS ANGELES`、`CHICAGO (via LAX)` | 匹配前按 `/`、换行、`()` 拆候选子名，逐个 canonicalize，命中任一即填 |
| 仍对不上 | 留空（文件里该港只剩港名） |
| 一港多船司 | 全部按 船司×2 行展开 |
| 同港同船司重复行 | 不去重，如实展开 |
| 某船司只有 20FT 无 40 价 | 保留 2 行结构（"40FT/40HQ"标签照写、D 留空） |
| 40HQ 空、40GP 有 | 取 40GP |

### 6.3 数据/币种
- rows 为空：前端 `keptCount>0` 已挡；端点兜底产出全港留空文件，不崩。
- destination 缺失行：canonicalize 得空串 → 不归任何港 → 忽略。
- 币种：sheet2 海运费/附加费区固定 USD（表头写死），本地杂费 CNY 区不碰 → 不写币种、无冲突。

### 6.4 保真/工程
- 其他两个 sheet（JP/LCL）：全程不碰，原样保留在输出。
- 嵌图：已确认无 `xl/media`、无图表；仅一个 vmlDrawing（批注框）可能被 openpyxl 丢，影响可忽略。
- 并发/性能：回填是同步 CPU 活，按现有 upload 模式甩 `run_in_threadpool`；28 港规模毫秒级。
- 文件名：原名去扩展名 + `_filled.xlsx`；含全角括号/中日文 → `Content-Disposition: filename*=UTF-8''…` 编码。

## 7. 测试策略（实现按 TDD，测试先行）

### 7.1 核心回填器单测（`tests/sheet_builder/test_template_refill.py`，重点）
fixture：复制她的"空白 着地あり"到 `tests/fixtures/sea_other_ports_template.xlsx`；rows 代码构造。

| # | 用例 | 断言 |
|---|---|---|
| 1 | 基础填充 HK(2船司)+BUSAN(1船司) | HK 块=4 行、A 列竖向合并、C 列箱型标签、B 列船司、D 列 freight |
| 2 | 40 取 40HQ | 40gp≠40hq → 40 行 D==40hq；40hq 空 → ==40gp |
| 3 | 附加费映射 | included→`Incl.`；collect→`Collect`；amount→按箱型；note→文本 落 E/F/G/H |
| 4 | 无数据的港 | 模板有、rows 无 → 占 1 行、价格空 |
| 5 | 别名/双名 | PUSAN↔BUSAN、CHENNAI↔MADRAS/CHENNAI、LOS ANGELES↔LONG BEACH⏎LOS ANGELES 命中 |
| 6 | 过滤 | rows 含模板没有的港 → 输出不含 |
| 7 | 保真 | 输出仍 3 sheet；JP/LCL 不变；表头 1–8 不变；数据行有边框/数字格式 |
| 8 | 空 rows | 全港留空，不抛异常 |
| 9 | 异常 | 缺 OTHER PORTS 页 / 非 xlsx → 抛特定异常 |

### 7.2 端点测（`tests/api_v1/`）
- multipart 上传 fixture 模板 + rows JSON → 200、xlsx 可被 openpyxl 打开、OTHER PORTS 页有预期数据。
- session 不存在→404；非 sea 会话→400；缺页模板→400。

### 7.3 回归与真实对数
- 跑全量 `pytest`，守住 ≈457 基线不回退；现有「下载」端点行为不变。
- 前端：`npm run lint` + `npm run build`；可选 Playwright MCP 跑 UI 流程不报错。
- **交付前必做真实对数**：她真实模板 + 一份真实报价端到端，人眼抽样核对 OTHER PORTS 页 1~2 个港数值/附加费。

## 8. 文件改动清单（预估）

新增：
- `backend/app/services/step1_rates/sheet_builder/template_refill.py`（核心回填器 + OTHER_PORTS_PROFILE）
- `backend/tests/sheet_builder/test_template_refill.py`
- `backend/tests/api_v1/test_rate_sheet_download_into_template.py`
- `backend/tests/fixtures/sea_other_ports_template.xlsx`（复制客户模板）
- 前端弹窗组件（或内联进 RateSheetBuilder）

改动：
- `backend/app/api/v1/rate_sheet.py`：加 `POST /{session_id}/download-into-template` 端点
- `frontend/src/services/api.ts`：加 `rateSheetApi.downloadIntoTemplate(sessionId, file, rows)`
- `frontend/src/pages/RateSheetBuilder.tsx`：加按钮 + 弹窗 + 处理
- `frontend/src/i18n/{zh,ja,en}*`：新增文案三语

## 9. 不在本次范围（YAGNI）
- JP（日本港）页、LCL（拼箱）页的回填 —— 留待后续，只需加 profile。
- 匹配明细报告/未填充清单 UI —— 用户明确选"只留空不报告"。
- 本地目的港杂费（Booking/THC/DOC/ISPS/设备费）填充 —— 不在抽取范围。
- 从历史批次/DB 取数的"指定数据下载" —— 本次只基于当前会话。
