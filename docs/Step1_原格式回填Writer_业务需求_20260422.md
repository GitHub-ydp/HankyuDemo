# Step1 原格式回填 Writer — 业务需求梳理

- **版本**：v1.0
- **发布日期**：2026-04-22
- **作者**：业务大师
- **读者**：
  - 架构大师（据此拆 writer 技术任务单）
  - 开发大师 / 测试大师（验收依据）
  - 张东旭（业务复核，向楢崎集中提问用）
  - 监工（抽查"出处"字段）
- **红线（本文件不写的内容）**：
  - 不写字段名 / Schema / API 路由 / DB 结构
  - 不写 openpyxl API、样式保留实现细节、文件存储路径
  - 不写前端组件层级、样式
  - 不碰代码文件
- **依据文件（唯一业务依据，出处必须全部可回溯）**：
  - 客户来信：`邮件/2026.04.21/对方来信.txt`
  - Step1 总实施指令：`docs/Step1_运费表Demo_实施指令_20260421.md`
  - 项目总需求：`docs/项目需求分析文档.md`
  - 业务 FAQ：`docs/业务知识FAQ.md`
  - Air 业务需求（已交付）：`docs/Step1_Air运价_业务需求_20260421.md`
  - 真实 Excel 原件 3 份：
    - `资料/2026.04.21/RE_ 今後の進め方に関するご提案/【Air】 Market Price updated on  Apr 20.xlsx`
    - `资料/2026.04.21/RE_ 今後の進め方に関するご提案/【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx`
    - `资料/2026.04.21/RE_ 今後の進め方に関するご提案/【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx`

---

## 0. 一句话业务定义

> **"原格式回填"** = 把**已经入库的费率数据**，按**楢崎交付的 3 份 Excel 的完全相同版式**重新导出一份 Excel 文件，让**购买部门/营业部门拿到手的文件在肉眼层面与他们每天对着的原件无差别**，可以直接替代手工更新的版本使用。

- 业务出处：`docs/Step1_运费表Demo_实施指令_20260421.md` §1.1 第 32 行"输出运费表：按三份原文件格式回填（保留样式、合并、附注）"；§7 第 217 行"核心原则：用原文件作模板，只改数据单元格，不破坏结构"。
- 为什么不是"导出一份新格式的 Excel 就行"：营业部门每天用眼看的就是这 3 份原件的版式，换版式等于让他们重新学；楢崎邮件第 7 行"也希望由我司员工亲自进行实际操作体验"——操作体验的前提是**文件长得和他们自己维护的一模一样**。

---

## 1. 本轮 writer 的业务范围

### 1.1 必须做

| 业务功能 | 出处 |
|---|---|
| F1 导出【Air】周表 + Surcharges 的原格式 Excel（当前周批次） | 实施指令 §1.1、§7 |
| F2 导出【Ocean】JP FCL & LCL / 其他港 FCL / LCL 三 sheet 的原格式 Excel（当前月/半月批次） | 实施指令 §1.1、§2 |
| F3 导出【Ocean-NGB】Rate sheet 的原格式 Excel（当前月批次） | 实施指令 §1.1、§2 |
| F4 Lv.1/Lv.2/Lv.3 三级报价在【Ocean-NGB】回填文件中作为三条独立行保留 | 实施指令 §1.1 第 35 行 |
| F5 所有 Remark / RMKS / Must go / Case by case / "AT COST (COLLECT)" / Included / Subject to Destination Charges 等非数值文本**原文一字不差**出现在输出 Excel 对应单元格 | 实施指令 §7、Air 业务需求 §3.5 |
| F6 文件名能让楢崎肉眼区分"本次导出的是哪个批次"（含批次有效期窗口） | 楢崎 5/14 Demo 要"亲手操作"，必须能认出文件归属；实施指令 §6 批次键定义 |

### 1.2 明确不做

| 不做项 | 原因 / 出处 |
|---|---|
| 合并多批次导出（例如同时导出 4 月和 5 月 Ocean） | 实施指令 §6 第 208 行"新批次 active、旧同键批次 superseded"是一次一个 active；楢崎邮件未提"差异对比导出" |
| 翻译日文/中文附注后导出 | 实施指令 §1.2、§8.2 仅要求 UI 日文优先，未要求表内容翻译；翻译会毁原格式 |
| 对解析 warning 在输出 Excel 内标色/加批注 | ❓ 待楢崎确认（推断：本轮走"看日志不看 Excel 批注"更稳妥），见 §7-R2 |
| 将入库后新增的 `batch_id / parser_version / imported_at` 等系统元字段写入输出 Excel | 原件无此列；写进去就破坏格式 |
| 把 Ocean-NGB 原件 Rate sheet 里 1687 个 Excel 公式（`=A2`、`=ROUNDUP(R2*1.1,-1)` 等）逐个保留 | ❓ 详见 §5.3-R3，必须向楢崎确认 |
| 回填【Air】上周 sheet（`Apr 13 to Apr 19`） | ❓ 上周 sheet 是否入库本身仍未确认（Air 业务需求 Q1）；本轮建议只回填本周 sheet，见 §4.1-R5 |
| 回填 Ocean-NGB 的 `sample` sheet 和 `Shipping line name` sheet | 实施指令 §3.3 明确 `sample` 跳过不导；`Shipping line name` 是船司字典，不是费率数据 |
| Step2 入札对应、Step3 个别报价、邮件检索、会议纪要相关的任何导出 | 实施指令 §1.2 |
| 多语言版本切换的表内容 | 客户未提 |
| 回填文件带水印 / 密级标识 / 公司 logo 图片 | 3 份原件本身就不含任何图片（已实测 zip 内无 media 目录），不应凭空添加 |

---

## 2. Writer 的输入与输出（业务侧）

### 2.1 输入（用户角度）

- 用户（楢崎 / 营业部门）在系统里选中**一个已入库的 active 批次**（例如 "Ocean 2026-04-21 ~ 2026-04-30"），触发"导出/下载"动作。
- 业务推断（❓ 待楢崎确认）：若同一文件类型下同时有多个批次（例如刚上传了下一月但尚未切换 active），默认导出当前 active 批次；其他批次需要用户**显式切换**才能导出。
- 出处：实施指令 §6 第 207 行的批次 active/superseded 机制 + §8.1 `/export` 页面描述 "选批次 + 选模板 → 下载原格式回填的 Excel"。

### 2.2 输出（用户角度）

- 一份可直接用 Excel 打开的 `.xlsx` 文件。
- 视觉上必须让**一个熟悉原件的人（楢崎/购买部门）打不出"这不是我每天看的那张表"的判断**。
- 不附加任何"导出说明"页、"系统生成"水印、"数据来源"脚注。
- 出处：实施指令 §7 "核心原则：用原文件作模板，只改数据单元格，不破坏结构"。

---

## 3. "原格式"的 8 条硬业务规则（writer 合格判定）

> 以下每条规则都有真实 Excel 单元格出处，违反任一条即为不合格。

### R1 — 表头与元信息区必须逐字保留

- **规则**：表头文本、元信息文本、文件号、`Effective from … to …` 标题的**原文、换行符、单元格位置**与原件一致。
- **Air 出处**：`Apr 20 to Apr 26!B1="Service/+100KG"`（含 `/`）、`C1="2026/4/20   (Mon)"`（中间有 3 个空格，不是 1 个）、`J1="Remark (Selling)"`。
- **Ocean 出处**：`JP N RATE FCL & LCL!A1="HEC-SE-QF-01"` (文件号)、`A2="HHE/SHA  Sea Export Net rate"`（中间两个空格）、`A5="Vsl SKD & T/T subject to carrier & Co-loader's change."`（带撇号）、`D8="Freight\n(USD)"`（含换行）。
- **Ocean-NGB 出处**：`Rate!D1="Rate Valid until\nYYYY/MM/DD"`（换行）、`J1="\nPort of\nDischarge"`（前导换行）、`N1="Place of Delivery               (full)                 "`（尾随大量空格）。
- **业务含义**：购买部门就靠这些小怪癖识别"这是我们的表"；任何"顺手规整"都会引起"这不是我的表"的第一眼质疑。

### R2 — 合并单元格的位置与范围必须一致

- **Air 周表**：每行 `J{n}:K{n}` Remark 列合并共 42 条（2–43 行）+ `J1:K1` 表头合并 —— 必须全部保留，不能 flatten 为单格。
- **Air Surcharges**：`C5:C67` 一个超大纵向合并（63 行高），值为 `"CHINA / SHA \n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n注\n意\n生\n效\n日\n期"` —— 注意**竖排"注意生效日期"六个字是靠字与字之间插 `\n` + 单元格 wrap_text 实现的**（不是 textRotation），换行符一个都不能少。
- **Ocean JP**：`L7:P7` CNY 段横向合并；`A45:A54` Destination 纵向合并；B 列 `(Destination, Shipping Line)` 每组 2 行合并（如 `B43:B44`、`B29:B30` 等数十条）。
- **Ocean JP 底部 LCL 段**：`E131:F131`、`I131:J131`、`K131:L131` 最后一行多处横向合并。
- **Ocean FCL 其他港**：存在 **3 行一组**（20FT/40FT/40HQ）的区域（R100–R110 区段，美线 ONE 船司），目的地单元格随之合并 3 行 —— **与 JP sheet 的 2 行结构不同**，不能假设所有 FCL 都是 2 行配对。
- **Ocean LCL**：`C33:C37` 将 FELIXSTOWE/SOUTHAMPTON、LOS ANGELES/LONG BEACH、OAKLAND/SAN FRANCISCO、CHICAGO、NEW YORK 5 行的某列合并。
- **业务含义**：合并单元格的格局就是费率表的"视觉骨架"；一旦错位，营业拿到的是一张看起来眼熟但每个格子都错了半行的表，会直接报错。

### R3 — 换行与内部空格必须保留

- **Air 周表 Service 列**：`B17="Transfer NH 2 to 3 days"`（末尾空格）、`B22="MH/FM 3 days servcie "`（末尾空格 + 拼写错误 `servcie`）、`B27="BR/SQ 3-4 days\nservice"`（含换行）。
- **Air 周表 Remark 列**：`J15="TG663 D2457"\n"TG665 DAILY"` 两段之间换行。
- **Ocean 表头**：`D8="Freight\n(USD)"`、`I8="Sailing\nDay"`、`L8="Booking Charge\n(per Cont)"`，所有带单位的表头字段都是"字段名\n(单位)"两行式。
- **Ocean LCL 多机场目的地**：`LCL N RATE!A32="FELIXSTOWE\nSOUTHAMPTON"`、`A33="LOS ANGELES\nLONG BEACH"`、`A34="OAKLAND\nSAN FRANCISCO"` —— 两个机场名靠 `\n` 分两行显示在同一单元格。
- **Ocean-NGB Rate**：`C35` 单元格值 `"CNY20/20'\nCNY30/40'"`（ISPS 费按柜型两行显示）。
- **业务含义**：parser 的 extras 里已经保留了 `raw_service / raw_destination / raw_remark` 这种带换行和 strip 前状态的原文（见 `docs/Step1_Air解析器_架构任务单_20260422.md` §0.4）；writer 必须用这些原文字段回填，不能用规整后的值。

### R4 — "非数值文本单元格"原文保留（AT COST / Included / Subject to / COLLECT / MBL CC / - 等）

- **"AT COST (COLLECT)" 在 `JP N RATE FCL & LCL` 第 5 列（LSS+CIC）出现 60 次**（R9–R100 附近多数日本港口行），业务含义为"目的地到付、按实际成本结算"（业务 FAQ Q2 + 行业常识）。
- **"Included" / "-" / "COLLECT" / "MBL CC" / "Incl." / "Subject to Destination Charges" / "subject to Destination BAF" / "Subject to Destination PSS" / "Subject to Destination surcharge"**：Ocean JP / FCL 其他港 / LCL 中遍布 —— 业务含义各异（Included=已包含在主运费、`-`=不适用、COLLECT=目的港到付、MBL CC=主单到付、Subject to=到港后按目的地规则另行核收）。
- **"Must go NN"**（Air 周表 J18/J19/J20/J21/J24）、**"Case by case"**（Air J22、J27 及整个欧美线段）、**"Not accept battery goods"**（Air J3）、**"BFS TERMINAL"**（Air J16）、**"EES：1ST D5+2ND D5（1M）"**（Air J17，含全角冒号和全角括号）。
- **Ocean LCL 中的中文注释**：`LCL N RATE!L27="关封货物只接受新加坡转拼的服务，运费另询"`（第 27 行 YANGON 之后的 CHATTOGRAM 行）。
- **规则**：以上所有文本**不得**被翻译、简化、替换为枚举值、替换为 0/NULL；必须原文写入对应单元格。
- **业务含义**：营业根据这些文本决定能不能报价、要不要加钱、要不要回购买部门再确认（Air 业务需求 §3.5）；任何一处文本改写都可能导致营业误报。

### R5 — 数值单元格的类型（数字 vs 字符串）必须与原件匹配

- 原件中 `15.5`、`200`、`10` 是数字类型（会右对齐、可参与公式）。
- 原件中 `"-"` 是字符串类型，不是数字 0 / 非 null。
- 原件中 `"10/CBM, 18/TON"`（LCL 双单位报价，R10 HONGKONG、R32–R37 欧美线段）是字符串。
- 原件中 `"65/CBM+USD50"`（R26 YANGON）是字符串，含加法表达但不是 Excel 公式。
- **规则**：数字单元格写数字，字符串单元格写字符串；不得混淆（例如不得把 `-` 写成数字 0、不得把 `15.5` 写成字符串 `"15.5"`，否则样式对齐会全部错乱）。

### R6 — Excel 批注（cell comments）的回填策略需明确

- **Air Surcharges `K5` 有批注**：`"AA will implement variable airfreight surcharge (PSC)\n0.34/kg, MIN 568"`（AA 航司即将执行变动附加费的业务提醒）。
- **Ocean LCL `L10` 和 `B26` 各有批注**：L10 = `"Zhang Jieyi:\nBased on global rule, when it comes to HHE own Consol box, the actual cost need to be decided by actual shared FCL freight cost. It means own consol LCL final freight cost is different each time by actual vanning condition."`（HHE 自拼箱成本说明）；B26 = `"Zhang Jieyi:\n+THE TERMINAL DOC CHARGE USD50/BL"`（YANGON 的额外码头文件费）。
- **业务含义**：这些批注是采购部门同事（Zhang Jieyi）**留给营业的口头补充说明**，不是表正式内容，但打开 Excel 时会悬浮显示。
- ❓ 待楢崎确认（Q-W1）：回填文件是否需要保留这些批注？如保留，是否需要保留作者名 `Zhang Jieyi`？
  - **推断（需确认）**：批注代表"某个人对某条数据的补充解释"；入库时 parser 并未采集批注（Air 业务需求未覆盖，`docs/Step1_Air解析器_架构任务单_20260422.md` 也未列采集批注），因此 writer 原样从模板复制即可（模板法）；**不建议**根据入库数据动态生成批注。

### R7 — 日期单元格必须是 Excel 日期类型

- 原件 `JP N RATE FCL & LCL!B3 / D3` 是 `datetime.datetime(2026, 4, 1)` / `datetime.datetime(2026, 4, 30)`，显示为日期格式。
- 原件 `Surcharges!E5..E67` 所有 `EFFECTIVE DATE` 是 `datetime.datetime`。
- 原件 `Ocean-NGB Rate!C2..C104 / D2..D104`（Rate Valid from / until）是 `datetime.datetime`。
- **规则**：输出文件里这些单元格必须是 Excel 日期值（会按单元格数字格式显示），不能是字符串 `"2026-04-01"`，否则排序、筛选、对比会失灵。

### R8 — 冻结窗口、打印区域、列宽、行高必须保留

- **Air 周表**：`freeze_panes = "A2"`（表头锁定）；列宽 B=19.9、C=11.0、K=15.5；行 1 高 34.5，行 7 高 28.75。
- **Ocean JP**：`print_area = "'JP N RATE FCL & LCL'!$A$1:$M$109"` —— 即使数据到第 131 行，打印区只覆盖 FCL 段（A1:M109），LCL 段 116 行以下靠人眼滚动查看。
- **Ocean FCL 其他港**：`freeze_panes = "A9"`、`print_area = "'FCL N RATE OF OTHER PORTS'!$A$3:$G$77"`。
- **Ocean LCL**：`freeze_panes = "A10"`。
- **业务含义**：冻结窗口和打印区域决定了营业打开这张表是"低头就看到表头和前几行"还是"需要滚半屏才看到内容"，以及打印成 PDF 发给客户时是否截住尾部空行；这是日常体验层面的差异。

---

## 4. 3 份文件各自的回填场景

### 4.1 【Air】Market Price（每周更新）

- **业务节奏**：楢崎邮件第 19 行未单独说明 Air 节奏，但 Step1 实施指令 §2 明确"每周 1 次"。
- **场景**：周一购买部门收到本周新价 → 上传入库 → 营业在系统里点"导出 Air 本周"→ 下载一份文件，打开和原件一样有 3 个 sheet（上周 / 本周 / Surcharges）。
- **R5 — 上周表如何填**：
  - 选项 A（推荐，与本轮不做清单 §1.2 呼应）：上周 sheet 维持**模板里的空白或模板里的上周原始值**，不从数据库回填（因为上周数据本身尚未确认是否入库，见 Air 业务需求 Q1）。
  - 选项 B：如果下个里程碑客户明确要入库上周，上周 sheet 用入库数据回填。
  - **本轮建议**：选项 A，即上周 sheet 只还原模板静态内容，数据行走"空 or 原件样例"两种之一，由架构大师结合前端提示选定，但**业务侧要求该 sheet 存在且 Tab 名称为原件的 `Apr 13 to Apr 19`**（下周变成 `Apr 20 to Apr 26`，再下周递推）。
  - ❓ 待楢崎确认（Q-W2）：上周 sheet 是"填数据"、"留模板静态值"、还是"整 sheet 隐藏但保留"？

### 4.2 【Ocean】Sea Net Rate（每月 2 次，月底月初 + 月中）

- **业务节奏**：楢崎邮件第 19 行"Ocean 表每月 2 次（月底/月初一次，月中一次）"；实施指令 §2 同。
- **Demo 当天（5/14 或 15）就是节后第一次更新窗口**（邮件第 22 行）——意味着楢崎要当场看到"上传 4 月下→5 月上新价 → 导出 → 原格式 Excel"这一连串动作。
- **场景**：购买部门每月 2 次上传新价 → 入库成新批次 → 营业端导出一份**带新有效期**的 Excel（`B3="Effective from <新起日>"`、`D3="<新止日>"`）；三个 sheet 全部回填。
- **有效期 asymmetry（实证发现）**：当前 4 月原件里，JP sheet 的 `Effective from 2026-04-01 to 2026-04-30`（整月），但 FCL 其他港和 LCL sheet 的 `Effective from 2026-04-21 to 2026-04-30`（半月）。——**3 个 sheet 的生效期可能不同**。
- **业务规则**：writer 按**每个 sheet 在入库批次里记录的 effective_from / to** 回填，而不是全文件用同一个日期。
- ❓ 待楢崎确认（Q-W3）：新批次导出时，JP / 其他港 / LCL 三个 sheet 如果处于"月初更新了 JP、月中再更新其他港"的过渡期，怎么组合导出？是"以触发导出的那个 sheet 为准，其他 sheet 用各自最新批次"还是"等 3 个 sheet 都更新完再统一导出"？

### 4.3 【Ocean-NGB】FCL rate sheet（每月 1 次）

- **业务节奏**：实施指令 §2 "每月"。
- **场景**：购买部门每月把 HHENGB（阪急阪神宁波）从船司拿到的价上传 → 入库时把 Lv.1/Lv.2/Lv.3 作为三行独立记录 → 导出 Excel 时必须恢复为三行。
- **Lv.1/Lv.2/Lv.3 规则**：实施指令 §1.1 第 35 行明确"分级报价 Lv.1 / Lv.2 / Lv.3 作为 Ocean-NGB 的一等数据保留"。
- **原件关键事实（实证）**：Rate sheet 共 **1687 个 Excel 公式**——Lv.2 的 20GP 运费是 `=ROUNDUP(R2*1.1,-1)`（Lv.1 × 1.1 向上取整十）、Lv.3 是 `=ROUNDUP(R2*1.2,-1)`（Lv.1 × 1.2）；其他大部分列用 `=A2 / =E2 / =V3` 等公式把 Lv.1 的值复制到 Lv.2/Lv.3。
- **业务含义**：原件里 Lv.1 是"采购成本价"，Lv.2/Lv.3 是"对外 +10% / +20% 的报价档"，用公式保证改 Lv.1 一个数字，Lv.2/Lv.3 自动联动。
- ❓ 待楢崎确认（Q-W4，**最重要的一问**）：writer 回填时：
  - （a）恢复原公式（Lv.2/Lv.3 单元格写 `=ROUNDUP(R2*1.1,-1)`）——优点：营业拿到文件后改 Lv.1 能联动；缺点：若数据库存的 Lv.2/Lv.3 是 parser 独立解析出来的具体数值，可能和公式算出来的不一致。
  - （b）全部写成已计算的数值（Lv.1/Lv.2/Lv.3 三行都是硬编码数字）——优点：与数据库完全一致、Demo 现场数据对得上；缺点：营业后续改 Lv.1 不再联动，破坏他们原工作流。
  - **推断**（需确认）：如果 parser 把 Lv.1 / Lv.2 / Lv.3 当三条独立记录入库（实施指令第 35 行语义支持），那么 writer 走（b）更合理；但这改变了表的活性。
- ❓ 待楢崎确认（Q-W5）：`sample` sheet 和 `Shipping line name` sheet 是否需要原样保留（即使不填数据）？
  - 推断：`Shipping line name` 是日文船司字典（`＊船社・CO-LOADER一覧`），营业参考用，建议原样保留。
  - `sample` sheet 按实施指令 §3.3 "跳过不导"，**但"不导入数据库"和"不写入输出文件"是两回事**。输出文件是否该有这张模板示例 sheet，需明确。

---

## 5. 跨文件的业务共性规则

### 5.1 文件命名（R-NAME）

- ❓ 待楢崎确认（Q-W6）：命名约定。业务侧给出**建议命名模板**（架构大师定最终格式）：
  - 【Air】`【Air】 Market Price updated on <本周一 MMM DD>.xlsx`（例：`【Air】 Market Price updated on Apr 20.xlsx`，与原件完全一致）。
  - 【Ocean】`【Ocean】 Sea Net Rate_<YYYY>_<MMM DD> - <MMM DD>.xlsx`（例：`【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx`）。
  - 【Ocean-NGB】`【Ocean-NGB】 Ocean FCL rate sheet  HHENGB <YYYY> <MMM>.xlsx`（例：`【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx`，注意 "sheet" 和 "HHENGB" 之间是两个空格）。
- **业务理由**：楢崎每天看的文件名就是这个格式，系统导出的文件名若不一致，邮件发送 / 文件夹归档会对不上。
- **变体处理**：若同日多次导出，建议在扩展名前追加 `_<HHmmss>` 时间戳（例：`…Apr 20_153022.xlsx`），避免重名覆盖——这是业务容错需求，不是客户要求。

### 5.2 批次元信息"不写进表里"原则

- **业务规则**：`batch_id`、`parser_version`、`imported_at`、`imported_by` 这些系统元数据**不得出现在输出 Excel 的任何单元格、任何 sheet、任何批注、任何脚注中**。
- **出处**：实施指令 §7 "核心原则：用原文件作模板，只改数据单元格，不破坏结构"；原件不含系统字段。
- **业务推断（❓ Q-W7）**：如果楢崎事后要追"这份文件是哪一次导出的"，系统层应在**文件属性（Excel Document Properties）** 或**服务器日志**留档，而不是在单元格里。

### 5.3 Parser → Writer 字段对称性（业务层视角）

- parser 已经在 extras 里保留了以下"原文证据"字段（见 `docs/Step1_Air解析器_架构任务单_20260422.md` §0.4、Air 业务需求 §6.2）：
  - `raw_remark` / `raw_service` / `raw_destination`
  - `currency_assumption` / `airline_codes` / `has_must_go` / `must_go_value` / `is_case_by_case` / `density_hint` / `airports` / `from_region` / `area` / `*_is_dash` / `all_fees_dash`
- **业务规则 R-SYM**：凡是**肉眼可见在原件里存在**的字段（换行、空格、拼写错、全角字符、`-`、`Included`、`AT COST (COLLECT)`、`Must go 22`），writer **必须用 `raw_*` 原文字段回填**，不得用规整后的值。
  - 正例：`B22="MH/FM 3 days servcie "`（servcie + 尾空格）原样回填。
  - 反例：不得把它改成 `"MH/FM 3 days service"`（改拼写）或 `"MH/FM 3 days servcie"`（去尾空格）。
- **业务规则 R-SYM-2**：规整化字段（`destination_airport`、`airline_codes`、`has_must_go`、`must_go_value` 等）在回填时**忽略**，仅供系统内部检索 / 筛选使用。
- ❓ 待楢崎确认（Q-W8）：parser 对个别字段打过 warning（例如"EFFECTIVE DATE 宽松解析后值可疑"、"service 列含未识别航司代码"），writer 是否在对应单元格做标记？推断：本轮 **不做**（避免破坏视觉格式），warning 列表在系统日志 / 前端界面展示即可（§7-R2）。

---

## 6. 5/14 Demo 现场的业务场景（楢崎亲手操作）

> 以下是业务层对"那天楢崎要做什么"的推断，**推断来源**：楢崎邮件第 7 行"希望由我司员工亲自进行实际操作体验" + 实施指令 §8.1 四页面。

### 6.1 现场剧本（推断，需与张东旭对齐后再确认）

1. 楢崎点 `/upload` 页面，拖入**一份新的 Ocean 费率表**（文件名类似 `【Ocean】 Sea Net Rate_2026_May.01 - May.14.xlsx`，由阪急阪神当天给出）。
2. 系统自动识别是 Ocean 类型，解析预览，显示"行数 / warnings / 元信息"。
3. 楢崎进 `/batches`，点新批次，看差异（vs 当前 active 的 4 月批次），确认"新增 N 条 / 变更 M 条 / 消失 K 条"。
4. 确认入库，新批次变 active，旧批次 superseded。
5. 楢崎进 `/rates`，按目的地/船司过滤一条看看。
6. **楢崎进 `/export` 页面，选"Ocean · 2026-05-01 ~ 05-14"批次 → 点击"导出"按钮 → 浏览器下载一份 `.xlsx` 文件 → 楢崎用本地 Excel 打开 → 肉眼比对，文件结构、合并、附注、竖排字、AT COST 文本、Lv.1/2/3、中文注释 全部完好。**
7. 楢崎说 "OK"。Demo 通过。

### 6.2 Demo 的业务验收判定（楢崎说 "OK" 的判据）

- Demo 成功 = 第 6 步打开的 Excel 让楢崎**无法一眼挑刺**。
- 不成功（Demo 翻车）示例：
  - 打开的 Excel 表头少一个空格 / 换行 → 楢崎立刻说"这不是我们的表"。
  - `AT COST (COLLECT)` 变成 `0` 或 `null` → 营业立刻指出"这会被误报为免费"。
  - Lv.1/Lv.2/Lv.3 三行变成一行 → 楢崎问"那 +10% +20% 的档呢"。
  - 竖排"注意生效日期"六个字变成横排或消失 → 购买部门不接受。
  - 底部 LCL 段的 `关封货物只接受新加坡转拼的服务，运费另询` 中文消失 → 业务合规性丢失。

---

## 7. 业务风险与边界

### 7.1 业务风险（Demo 现场可能暴露）

| 风险编号 | 场景 | 影响 |
|---|---|---|
| BR1 | 楢崎在现场上传的**不是**本文档提到的 3 份文件，而是版式略有变动的"下一版"（表头多一列 / 少一行） | writer 按旧模板回填，新数据无处落位；楢崎当场发现表头错配 |
| BR2 | 上传了数据但 parser warning 高（例如半数行未识别航司），writer 仍照填 | 输出的表"格式对但数据假"，比不导还危险 |
| BR3 | 【Ocean-NGB】回填走了"全数值不要公式"路线（R3-选项 b），但楢崎习惯性改 Lv.1 去看 Lv.2/Lv.3 联动 | 联动失效 → 楢崎说"我们的表是活的你这张是死的" |
| BR4 | 同一文件类型有多个未切换 active 的批次，楢崎误选到 superseded 的旧批次导出 | 下载的是上月的表，对外报价全错 |
| BR5 | Ocean JP / 其他港 / LCL 三个 sheet 的 `Effective from` 日期在当月不一致（实测就是这种情况），writer 统一按"导出时刻选的批次"一个日期填三个 sheet | 两个 sheet 的日期被错误回填 |
| BR6 | Air Surcharges 的 CNY 币种声明（`F2`）写成别的位置 / 变成普通表头 | 报价币种混乱（周表无币种声明，Air 业务需求 Q2 未确认） |
| BR7 | Excel 批注被 writer 误写入"系统生成"等文字 | 楢崎发现批注作者不是 Zhang Jieyi，质疑数据来源可信度 |

### 7.2 边界（本轮不处理的场景）

- **不处理**：原件发生结构性变更（表头加列、sheet 拆分）。本轮 writer 假设 3 份原件的结构在 Demo 前**冻结**（和实施指令 §1 "Demo 范围（冻结）" 一致）。
- **不处理**：跨语言/多语言版本导出。
- **不处理**：PDF 预览 / 打印设置的非 `.xlsx` 输出。
- **不处理**：导出文件的数字签名 / 水印 / 防篡改。

---

## 8. 待业务确认清单（向楢崎 / 张东旭一次问清）

| 编号 | 问题 | 影响 | 默认值（未确认时 writer 按此执行） |
|---|---|---|---|
| Q-W1 | Excel 批注（cell comments）是否需要在回填文件中保留？包括作者名 `Zhang Jieyi` 是否保留？ | R6、BR7 | 保留（模板法直接复制） |
| Q-W2 | 【Air】的"上周 sheet"在回填文件中如何处理？填数据 / 留空模板 / 整 sheet 隐藏？ | §4.1-R5 | 保留 sheet 结构，数据区留空（与模板一致） |
| Q-W3 | 【Ocean】三个 sheet 的 `Effective from`/`to` 日期当前就不一致（JP 整月 / 其他港半月），未来每次导出时如何统一？ | §4.2、BR5 | 每个 sheet 按自己所在批次的日期回填，不强制统一 |
| Q-W4（**最重要**） | 【Ocean-NGB】Lv.2/Lv.3 的 1687 个 Excel 公式是否保留？ | §4.3-R3 | 公式保留；Lv.1 的数值用入库数据，Lv.2/Lv.3 单元格写回公式。**必须确认**，否则 Demo 会翻车 |
| Q-W5 | 【Ocean-NGB】的 `sample` 和 `Shipping line name` sheet 在回填文件中是否保留？ | §4.3 | 都保留原样（`sample` 是阪急阪神自己给购买部门的填表示例，`Shipping line name` 是字典） |
| Q-W6 | 文件命名约定，是否接受"与原件完全一致的命名模板 + 选填时间戳"？ | §5.1 | 沿用原件命名模板；同日重复导出加 `_HHmmss` |
| Q-W7 | 导出文件是否需要在"文件属性"里记录 `batch_id / 导出时刻 / 导出人`？ | §5.2 | 是，写入 Document Properties，不写入单元格 |
| Q-W8 | parser 有 warning 的行，writer 是否在 Excel 里做视觉标记（颜色 / 批注）？ | §5.3、BR2 | 不在 Excel 里标记；warning 在前端列表 + 后端日志展示 |
| Q-W9 | 楢崎 5/14 现场如果同一文件类型下有两个批次都是 active 候选（新上传但没切换），默认导出哪一个？ | §2.1、BR4 | 导出"当前 active"；未 active 的需用户显式点"先切换再导出" |
| Q-W10 | 楢崎 5/14 现场，要不要额外允许"只导出某一个 sheet（例如只要 JP FCL）"？ | 导出粒度 | 本轮只支持整文件导出（"原格式"= 全文件包括所有 sheet） |
| Q-W11 | 楢崎对回填 Excel 的视觉验收，走"并排打开比对眼看"还是"给出一个具体差异清单"？ | 验收方式 | 眼看；Codex 同时提供"writer 自检报告"作辅助（差异计数 + 样本摘录） |
| Q-W12 | 3 份原件的**数据下方的 Remark/Note 区段**（Ocean JP 第 116 行起的"LCL 段"就是一个例子）在回填时是否被触动？ | Ocean 结构 | 只改入库数据对应的区段；Remark 区段按模板原样保留 |

---

## 9. 本轮 writer 业务侧"不覆盖清单"

| 不做项 | 出处 / 理由 |
|---|---|
| Step2 入札自动填客户 PKG | 实施指令 §1.2，楢崎邮件第 9 行将 Step2 明确排到 Step1 之后 |
| Step3 个别报价导出 | 同上 |
| 邮件 / WeChat / 截图 / PDF 的输出 | 实施指令 §1.2 不做邮件检索；3 份原件均为 xlsx |
| 翻译三语版本 | 楢崎未要求表内容翻译；实施指令 §8.2 仅要求 UI 日文优先 |
| 多批次合并 / 差异对比 Excel | 差异预览在 `/batches` 页面（实施指令 §8.1），不走 writer 产出 |
| 水印 / 机密标识 / logo | 3 份原件无此项；无客户要求 |
| 在回填 Excel 内展示 parser warnings | §5.3、Q-W8，推断不做 |
| 新建系统专属字段列（batch_id / imported_at 等） | 实施指令 §7 "不破坏结构"，破坏结构 |
| Ocean-NGB 的 `sample` sheet 里的公式重建 | `sample` 本就不是入库目标（实施指令 §3.3），模板复制即可 |
| 跨文件类型的"一键全导出" | 楢崎未提；每类文件单独触发更符合批次 active 切换的业务节奏 |

---

## 10. 架构大师做 writer 最易踩的 2 条业务坑

### 坑1 — 把【Ocean-NGB】的 Lv.2 / Lv.3 全写成"数值"而不保留公式

原件 Rate sheet **存在 1687 个公式**（实证），其中 Lv.2 = `=ROUNDUP(R2*1.1,-1)`、Lv.3 = `=ROUNDUP(R2*1.2,-1)` 是**业务定价逻辑的核心载体**——购买部门维护 Lv.1，营业直接用 Lv.2/Lv.3 对外报价，"改一个动三个"是他们日常用法。若 writer 把三行都写成硬编码数值，打开文件后 Lv.1 一改 Lv.2/Lv.3 不动，楢崎会立刻识别"这不是我们的活表"。但如果走"保留公式"路线，又必须保证入库的 Lv.1/Lv.2/Lv.3 与公式算出来一致（parser 独立解析出的 Lv.2 值 和 `Lv.1 × 1.1` 向上取整十可能对不上——要先问楢崎这种不一致怎么处理）。架构大师**必须在拆任务前让张东旭问清 Q-W4**，否则 5/14 现场选错策略直接翻车。

### 坑2 — 把"规整化字段"当作回填数据源

parser 做得好的一点是同时保留了 `raw_*` 原文和规整化字段（例如 `service_desc=strip 后原文`、`raw_service=未处理原文`；`has_must_go`、`must_go_value` 是从 remark 抽出的结构化值）。writer 最容易犯的错误是**图省事用规整化字段回填**——例如用 `service_desc` 回填 Service 列，就会把 `"MH/FM 3 days servcie "` 末尾的那个空格丢掉、把 `"BR/SQ 3-4 days\nservice"` 的换行压扁、甚至"顺手"把 `servcie` 纠错成 `service`。原件的这些小怪癖是购买部门识别"我的表"的标记，一旦被"改善"就是灾难。**R-SYM 规则**必须明确：凡是肉眼在原件里可见的字段，writer 走 `raw_*` 原文回填；规整化字段只对系统内部检索 / 前端筛选可见，不碰输出文件。

---

**业务需求梳理完。下一步：监工抽查"出处"字段 → 架构大师据此拆 writer 技术任务单。**
