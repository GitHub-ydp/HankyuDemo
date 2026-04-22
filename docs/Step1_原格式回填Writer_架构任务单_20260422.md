# Step1 原格式回填 Writer — 架构任务单

- **版本**：v1.0
- **发布日期**：2026-04-22
- **作者**：架构大师
- **业务依据**：`docs/Step1_原格式回填Writer_业务需求_20260422.md`（323 行，唯一业务依据）
- **实施指令**：`docs/Step1_运费表Demo_实施指令_20260421.md` §1.1、§7
- **读者**：开发大师（按本单直接动手）、测试大师（按 V-Wn 写用例）、监工（抽查 file:line）
- **红线**：
  - 不动 `entities.py` / `protocols.py` / `registry.py`（adapter 侧）/ `service.py`（parse 服务）/ `normalizers.py` / 任何 adapter
  - 不动 DB 模型（`import_batch.py` 等）、不加 Alembic 迁移
  - 不改前端；API 只加一个下载路由
  - 不写实际代码，只给签名 / schema / 数据流 / 行级定位

---

## 0. Q-W4 决定性实测结论（openpyxl 公式保留）

**实测脚本**：`/tmp/ngb_formula_test.py`（已跑完，下次需要时复跑即可）
**实测对象**：`资料/2026.04.21/…/【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx` 的拷贝

**三阶段实测输出**：

```
[原始工作簿]
  sheet 'sample':              formulas=0    comments=0  merged=2  col_dims=46 freeze=AM19 print='sample'!$D$3:$BC$54
  sheet 'Rate':                formulas=1687 comments=0  merged=0  col_dims=3  freeze=None print=
  sheet 'Shipping line name':  formulas=0    comments=0  merged=2  col_dims=3  freeze=None print=
  formula sample: [('A3', '=A2'), ('E3', '=E2'), ('F3', '=F2')]

[load_workbook → 改 Rate!R3（原本是 =ROUNDUP(R2*1.1,-1)）为 99999.0 → save]

[保存后重新 load]
  sheet 'Rate': formulas=1686（少 1，正是被覆盖的 R3）
  diff 汇总：comments 全等、merged 全等、col_dims 全等、freeze_panes 全等、print_area 全等
  Rate!R4 = '=ROUNDUP(R2*1.2,-1)'（未动的相邻公式完好）
```

### 结论

1. **openpyxl 3.1.5 的 `load_workbook(keep_formulas 默认) → cell.value=X → wb.save()` 模式天然保留**：
   - 所有未被显式修改的 cell 的公式（Lv.2/Lv.3 的 1687 个）
   - 所有 merged_cells 区间
   - 所有 comments（含作者名 `Zhang Jieyi`）
   - column_dimensions（列宽、隐藏）
   - freeze_panes、print_area
2. **唯一纪律**：**writer 绝对不能对公式 cell 赋值**。一旦赋值，公式消失（变成静态值）。
3. **因此 OceanNgbWriter 的核心策略**（对 Q-W4）：
   - Lv.1 的运费、Surcharges 等**数值 cell** → writer 覆盖
   - Lv.2 / Lv.3 三行里**任何含公式的 cell**（无论是 `=R2`、`=A2` 还是 `=ROUNDUP(R2*1.1,-1)`）→ **writer 跳过**，保持公式不动
   - 实现层面靠"写前读 `cell.value`；若为 `str` 且以 `=` 开头，不写"的守卫

---

## 1. 技术路线（方案 A，不选 B/C）

### 1.1 方案 A — **原件即模板，load → 改 cell → save**（采用）

**做法**：writer 拿到批次时，打开批次上传时保留的原件副本（`rate_batch_service.DraftRateBatch.file_path`，见 §3.3），`openpyxl.load_workbook(path, data_only=False)` 加载，按入库 records 的 `extras.sheet_name + extras.row_index` 定位到对应单元格，**只改数值 cell**（公式 cell 守卫跳过），最后 `wb.save(BytesIO)` 输出字节流。

**为什么选 A**：
- 业务文档 R1-R8（§3 第 85–154 行）要求"表头逐字 / 合并 / 换行 / 竖排 / 批注 / 日期类型 / 冻结窗口 / 列宽"**全保留** → openpyxl 在 load/save 时天然继承（§0 实测证据）
- 不需要手工重建任何样式、合并、公式、批注
- 代码量最小，开发成本最低，符合 CLAUDE.md"三份相似比过早抽象好"

### 1.2 方案 B — **保存 upload 字节直接返回**（不选）

把上传的原始 xlsx 字节原封发回去。**问题**：完全忽略了"把入库数据回填到单元格"这一核心诉求——导出的是上次上传的原件，不是当前入库批次的数据。业务文档 §2.2 要求"数据已回填"。直接 PASS。

### 1.3 方案 C — **从零用 openpyxl 重绘**（不选）

新建 Workbook，手工 `ws.merge_cells` / `ws.column_dimensions` / `ws.freeze_panes` / 批注、公式、样式全部程序化重建。**问题**：
- 3 份原件合计 2000+ merged_cells 单元格、若干批注、1687 个公式、多处 `\n` 竖排、日期样式——手写重建每一行都是错的来源
- 购买部门的"眼熟"阈值极低（业务需求 §6.2 第 243 行：少一个空格都被识别）
- 工作量是方案 A 的 10 倍以上，而且任何一处漏写都不符合 R1-R8

---

## 2. "原格式" R1-R8 与实现策略映射（权威表）

| 业务规则（§3 引用） | openpyxl 实现策略 | 兜底 |
|---|---|---|
| R1 表头逐字保留 | 不改 row 1（Air/Ocean 周表/JP/其他港/LCL）/row 1-4（Surcharges）；writer 从数据区起始行开始写 | 守卫：若当前 cell 在"表头保护区"内，跳过写 |
| R2 合并单元格位置与范围 | `load_workbook` 默认保留 `ws.merged_cells.ranges` | 测试校验 before/after 集合相等 |
| R3 换行/空格/半角全角 | 覆盖值从 `extras.raw_*`（raw_remark / raw_service / raw_destination）取 | 若 extras 无 raw_*，降级用规整字段 + warning |
| R4 非数值文本原文（AT COST / Included / `-` / MBL CC / Must go / Case by case / BFS TERMINAL / `关封货物…`） | 每个文本单元格 parser 已在 `extras.raw_cell_value`（若 parser 保留）或通过 `remarks` / `airline_codes` / `raw_remark` 携带原文；writer 用原文覆盖 | 若入库时丢失 → fallback 保留模板原值（不写） |
| R5 数值类型（number vs str） | writer 按 row 类型写：Decimal→float 保留 2 位、`-` 写字符串 `"-"`、`"10/CBM, 18/TON"` 等复合写字符串 | 守卫：`isinstance` 判断 |
| R6 批注 | `load_workbook` 默认保留；writer 不碰 `cell.comment` | Q-W1 默认"保留所有批注"→ 不做任何批注操作 |
| R7 日期类型 | 用 `datetime.datetime` 赋值（不是 `str`），openpyxl 会按单元格原 number_format 渲染 | 守卫：覆盖日期 cell 前 `isinstance(value, (date, datetime))` 断言 |
| R8 冻结窗口 / 打印区域 / 列宽 / 行高 | `load_workbook` 默认保留 `freeze_panes / print_area / column_dimensions / row_dimensions` | 测试校验 |

---

## 3. 文件级改动清单（到函数签名）

### 3.1 新增目录：`backend/app/services/step1_rates/writers/`

| 文件 | 职责 | 关键签名 |
|---|---|---|
| `__init__.py` | 导出 `AirWriter / OceanWriter / OceanNgbWriter / get_writer` | `from .registry import get_writer` |
| `protocols.py` | `RateWriter` Protocol | `write(batch_id: str) -> tuple[bytes, str]`（返回字节流 + 建议文件名） |
| `templates.py` | 原件模板路径解析 | `resolve_template_path(batch_id: str) -> Path`（从 `_draft_batches[batch_id].file_path` 取） |
| `base.py` | 共享 helper（**只放 3 个函数**，不抽共用基类，遵循 CLAUDE.md 三份分开） | `is_formula_cell(cell) -> bool`；`safe_set(cell, value, *, allow_overwrite_formula=False) -> bool`；`pick_raw(record, *keys)`（按优先顺序取 raw_*） |
| `naming.py` | 文件命名（Q-W6 默认） | `build_filename(file_type, effective_from, effective_to, *, now=None) -> str` |
| `air.py` | AirWriter | `AirWriter.write(batch_id) -> tuple[bytes, str]` |
| `ocean.py` | OceanWriter | 同 |
| `ocean_ngb.py` | OceanNgbWriter | 同 |
| `registry.py` | `get_writer(file_type: Step1FileType) -> RateWriter` | 路由 |

### 3.2 新增文件：`backend/app/api/v1/rate_downloads.py`

```
router = APIRouter(prefix="/rate-batches", tags=["rate-batches"])

@router.get("/{batch_id}/download")
def download_rate_batch(batch_id: str):
    """导出原格式回填 Excel。"""
    # 1. 从 rate_batch_service 取 draft（内存 stub，见 rate_batch_service.py:50）
    # 2. get_writer(Step1FileType(draft.legacy_payload["file_type"])).write(batch_id)
    # 3. StreamingResponse(content, media_type="application/vnd.openxmlformats...",
    #                      headers={"Content-Disposition": f'attachment; filename="{name}"'})
```

**错误码**：
- `404` — `batch_id` 不存在于 `_draft_batches`
- `422` — `draft.file_path` 为空或文件不存在（批次上传文件已被清理）
- `422` — `draft.legacy_payload["file_type"]` 无对应 writer（不应该发生，保护性）
- `500` — writer 内部异常（含 openpyxl save 失败）

### 3.3 修改文件：`backend/app/api/v1/router.py`

- 第 9 行起新增 `from app.api.v1.rate_downloads import router as rate_downloads_router`
- 第 21 行起新增 `router.include_router(rate_downloads_router)`
- **不合并到 `rate_batches.py`**：职责分离，便于后续扩展（批量导出走同前缀）

### 3.4 不改清单（防止开发大师误动）

- `backend/app/services/step1_rates/adapters/*` — parser 已交付，writer 不反向依赖
- `backend/app/services/step1_rates/entities.py` — Step1RateRow / ParsedRateBatch 字段完全够用
- `backend/app/services/step1_rates/service.py` — parse_rate_file 与 writer 无关
- `backend/app/services/rate_batch_service.py` — 读 `_draft_batches` 即可，不新增接口；若必须（例如想把 writer 调用封装为 service），允许新增 `get_draft_batch(batch_id)` 只读 getter，**不改现有函数签名**
- `backend/app/models/*` — 无需新字段
- `backend/alembic/*` — 无迁移

---

## 4. `RateWriter` 契约

### 4.1 Protocol 签名（`writers/protocols.py`）

```python
class RateWriter(Protocol):
    key: str                 # "air" / "ocean" / "ocean_ngb"
    file_type: Step1FileType

    def write(self, batch_id: str) -> tuple[bytes, str]:
        """
        输入：内存 draft batch_id（rate_batch_service._draft_batches 的 key）
        输出：
          - bytes: 回填后的 .xlsx 字节流
          - str:   建议文件名（含后缀，见 §7）
        抛：
          - KeyError("batch_id 不存在")
          - FileNotFoundError(f"模板文件不存在: {path}")
          - ValueError("batch file_type 与 writer 不匹配")
        """
```

### 4.2 `is_formula_cell` / `safe_set`（`writers/base.py`）

```python
def is_formula_cell(cell) -> bool:
    """判断 cell 是否为 Excel 公式（以 '=' 开头的字符串）。"""
    v = cell.value
    return isinstance(v, str) and v.startswith("=")

def safe_set(cell, value, *, allow_overwrite_formula: bool = False) -> bool:
    """
    写入守卫：
    - 如果 cell 当前是公式且 allow_overwrite_formula=False → 不写，返回 False
    - 如果 value 是 None 且 cell 当前有值 → 不写（不清空模板），返回 False
    - 否则写入，返回 True
    """
```

### 4.3 `pick_raw`（`writers/base.py`）

```python
def pick_raw(record: dict, *keys: str, default=None):
    """按 keys 顺序从 record（legacy dict）取第一个非 None 值。
    用于优先拿 raw_remark / raw_service / raw_destination，fallback 到规整字段。"""
```

---

## 5. 3 份 writer 的核心算法（伪代码 ≤20 行）

### 5.1 AirWriter（`writers/air.py`）

```
def write(batch_id):
    draft = _draft_batches[batch_id]
    tpl = resolve_template_path(batch_id)   # uploads/step1_batch_xxx_.xlsx
    wb = load_workbook(tpl, data_only=False)

    # 1) 周表：按 sheet_name（extras.sheet_name = "Apr 20 to Apr 26"）分组
    weekly = [r for r in draft.row_payloads if r["record_kind"] == "air_weekly"]
    for sheet_name, group in groupby(weekly, key=lambda r: r["sheet_name"]):
        ws = wb[sheet_name]                  # sheet_name 必须已在工作簿内
        for r in group:
            row = r["row_index"]             # parser extras 已给出（air 任务单 §3.12）
            safe_set(ws.cell(row, 1), pick_raw(r, "raw_destination", "destination_port_name"))
            safe_set(ws.cell(row, 2), pick_raw(r, "raw_service", "service_desc"))
            for n in range(1, 8):
                safe_set(ws.cell(row, 2+n), _decimal_or_str(r.get(f"price_day{n}"), r.get(f"price_day{n}_raw")))
            safe_set(ws.cell(row, 10), pick_raw(r, "raw_remark", "remarks"))

    # 2) Surcharges：record_kind == "air_surcharge"
    ws = wb["Surcharges"]
    for r in filter(lambda x: x["record_kind"] == "air_surcharge", draft.row_payloads):
        row = r["row_index"]
        # AREA(B) / FROM(C) 是合并区，不重写（保留模板）
        safe_set(ws.cell(row, 4), r.get("airline_code_raw"))
        safe_set(ws.cell(row, 5), _date_or_raw(r.get("valid_from"), r.get("effective_date_raw")))
        for col, val_key, dash_key in [(6,"myc_min_value","myc_min_is_dash"), (7,"myc_fee_per_kg","myc_fee_is_dash"),
                                        (8,"msc_min_value","msc_min_is_dash"), (9,"msc_fee_per_kg","msc_fee_is_dash")]:
            safe_set(ws.cell(row, col), "-" if r.get(dash_key) else r.get(val_key))
        safe_set(ws.cell(row, 10), r.get("destination_scope"))
        safe_set(ws.cell(row, 11), pick_raw(r, "raw_remark", "remarks"))

    return _save_to_bytes(wb), build_filename(Step1FileType.air, draft.effective_from, draft.effective_to)
```

**关键决策（AirWriter）**：
- AREA/FROM 合并区（业务需求 §3-R2 Air Surcharges 第 100 行；Air 解析器任务单 §4.4）**不重写**——因为 parser 只在首行 anchor cell 有值，writer 写在非 anchor 会是 no-op 或破坏合并；直接让模板保留
- `price_dayN_raw` 是 parser 保留的非数字原文（Air 解析器任务单 §3.4 W-A06），写字符串；正常值写 Decimal
- 上周 sheet（Q-W2 默认值"保留 sheet 结构，数据区留空与模板一致"）：weekly 只遍历**当前周的记录**（`draft.effective_from == r["effective_week_start"]` 的那些），上周 sheet 数据区不写

### 5.2 OceanWriter（`writers/ocean.py`）

```
def write(batch_id):
    draft = _draft_batches[batch_id]
    wb = load_workbook(resolve_template_path(batch_id), data_only=False)

    # 按 extras.sheet_name 分三组分派（Ocean 解析器按 sheet 名入库）
    by_sheet = groupby(draft.row_payloads, key=lambda r: r["sheet_name"])

    for sheet_name, group in by_sheet:
        ws = wb[sheet_name]
        for r in group:
            row = r["row_index"]
            _write_ocean_row(ws, row, r, sheet_kind=_classify_ocean_sheet(sheet_name))

    # 生效期：每个 sheet 单独写各自的 B3/D3（Q-W3 默认：按 sheet 自己的 effective_from/to）
    for sheet_name in ("JP N RATE FCL & LCL", "FCL N RATE OF OTHER PORTS", "LCL N RATE"):
        if sheet_name in wb.sheetnames:
            _write_effective_dates(wb[sheet_name], draft, sheet_name)

    return _save_to_bytes(wb), build_filename(Step1FileType.ocean, draft.effective_from, draft.effective_to)
```

**`_write_ocean_row` 分 sheet_kind 行为**（JP 2 行配对 / 其他港存在 3 行 20FT/40FT/40HQ 组 / LCL 单行单位）：
- **JP**：按 `record_kind` 路由，freight / lss_cic / baf / ebs / booking / thc / doc 每个字段对应的列索引由 parser 的 `extras.column_index_map`（若有）或固定列表驱动；"AT COST (COLLECT)" / "Included" / "MBL CC" 从 `extras.raw_cell_value`（parser 需保留）覆盖
- **FCL 其他港**：同 JP，但容忍 3 行合并
- **LCL**：freight_per_cbm / freight_per_ton、`"10/CBM, 18/TON"` 字符串、`关封货物…` 中文注释从 `extras.raw_remark` 原样写
- **Remark 区段（业务 Q-W12 默认"不动"）**：writer 只写 `extras.row_index` 落在"数据区"的记录；"数据区"由 parser 侧标注 `extras.section_kind="data"`（若 parser 未标注，fallback：row < 115 为 JP data，其余走模板）

### 5.3 OceanNgbWriter（`writers/ocean_ngb.py`）

```
def write(batch_id):
    draft = _draft_batches[batch_id]
    wb = load_workbook(resolve_template_path(batch_id), data_only=False)
    ws = wb["Rate"]

    for r in draft.row_payloads:
        if r["sheet_name"] != "Rate":    # sample / Shipping line name → 跳过（Q-W5 默认保留模板原样）
            continue
        row = r["row_index"]
        # 关键纪律：每个写入都走 safe_set，is_formula_cell 守卫
        # Lv.1 行：20GP / 40GP / 40HQ 等运费列可写
        # Lv.2/Lv.3 行：写前检查 cell 是否为公式；是则跳过（1687 个公式保留）
        for col_idx, val in _iter_ngb_columns(r):  # parser 的 extras.column_index_map
            safe_set(ws.cell(row, col_idx), val)    # 内部 is_formula_cell 守卫

    return _save_to_bytes(wb), build_filename(Step1FileType.ocean_ngb, draft.effective_from, draft.effective_to)
```

**Q-W4 纪律**：Lv.2/Lv.3 行的 cell 可能有两类——纯公式（`=R2`、`=ROUNDUP(R2*1.1,-1)`）和非公式（少数，比如文本 `"Lv.2"` 标签、日期 cell）。`safe_set` 只写非公式。开发大师可以加 assert log：每个 `safe_set` 返回 False 的次数应≈1687 × (入库行比例)。

---

## 6. Q-W1..Q-W12 技术默认值清单

| Q | 业务默认值 | writer 技术默认行为 |
|---|---|---|
| Q-W1 批注保留 / 作者名 | 保留全部 | writer 不触碰 `cell.comment`；load/save 透传 |
| Q-W2 Air 上周 sheet | 保留结构，数据区留空 | 遍历 weekly 时只写 `effective_week_start == draft.effective_from` 的那组；上周 sheet 数据区不 safe_set |
| Q-W3 Ocean 三 sheet 日期不一致 | 各 sheet 按自己的 effective 写 | 每个 sheet 分别 `_write_effective_dates`；不统一 |
| **Q-W4 Ocean-NGB 1687 公式** | **公式保留**（实测证实） | **writer 写前 is_formula_cell 守卫；公式 cell 一律跳过** |
| Q-W5 sample + 船司字典 sheet | 全保留原样 | writer 跳过这两个 sheet_name，不做任何写入 |
| Q-W6 命名 | 沿用原件模板 + 同日重复加 `_HHmmss` | `build_filename` 见 §7 |
| Q-W7 文件属性留档 | 写 Document Properties | `wb.properties.title = batch_id`；`wb.properties.subject = f"exported {datetime.utcnow().isoformat()}"`；**不写进单元格** |
| Q-W8 warning 视觉标记 | 不标记 | writer 不做；warnings 已在前端 / 日志展示；**不新增 Warnings sheet**（与原任务书要求"不破坏格式"冲突） |
| Q-W9 多候选批次 | 导出 active | router 从 `draft.activation_status` 过滤；非 active 直接 422 |
| Q-W10 单 sheet 导出 | 本轮只整文件 | router 无 sheet 参数 |
| Q-W11 验收方式 | 眼看 + 自检报告 | 测试大师在 pytest 里产出 before/after diff 文本；见 §9 |
| Q-W12 Remark 区段 | 只改数据区，Remark 区不动 | `safe_set` 的调用范围由 parser 的 `extras.row_index`（只存数据区行号）限定；Remark 区行号不会进入 row_payloads |

---

## 7. 文件命名（`writers/naming.py`）

```python
def build_filename(file_type, effective_from, effective_to, *, now=None) -> str:
    """
    Air:        【Air】 Market Price updated on <MMM dd>.xlsx
    Ocean:      【Ocean】 Sea Net Rate_<YYYY>_<MMM.dd> - <MMM.dd>.xlsx
    Ocean-NGB:  【Ocean-NGB】 Ocean FCL rate sheet  HHENGB <YYYY> <MMM_UPPER>.xlsx
    同日重复导出：若 now 非 None，在后缀前追加 _<HHmmss>（业务文档 §5.1 第 205 行）
    """
```

- `<MMM dd>` 使用英文缩写月 + 日（`Apr 20`）；`<MMM.dd>` 是 `Apr.21`
- 业务文档 §5.1（第 200–205 行）给出模板，writer 严格遵守（"sheet" 和 "HHENGB" 之间两空格等细节）
- 文件名只能 ASCII + 空格 + `【】`；**不清洗** `【】`（原件就是这样）

---

## 8. 与 parser 的对称性自检表

列出 parser 在 extras 里保留的字段 → writer 是否使用 / 如何使用：

| parser extras 字段（来源：Air 任务单 §3.12 + Ocean/NGB parser 产出） | writer 用法 | 不用时的风险 |
|---|---|---|
| `row_index` | **必用**（定位行） | 无法回填 |
| `sheet_name` | **必用**（定位 sheet） | 写错 sheet |
| `raw_destination` | Air 周表 A 列、Ocean JP A 列 | §3-R3 换行丢失 |
| `raw_service` | Air 周表 B 列 | §3-R3 `servcie` 拼写错 / 末尾空格丢失 |
| `raw_remark` | 所有 Remark 列、LCL 中文注释 `L27` | §3-R4 业务文本丢失 |
| `raw_cell_value`（Ocean parser 需保留，若缺要补） | Ocean JP 的 `AT COST (COLLECT)` / `Included` / `MBL CC` / `-` | §3-R4 大面积被误写 |
| `airline_code_raw` | Air Surcharges D 列 | 单纯用 `airline_code` 会丢 `/` 和 `-` 细节 |
| `airline_codes`（list） | **不用**（仅供检索） | — |
| `has_must_go / must_go_value / is_case_by_case` | **不用**（原文已在 `raw_remark`） | — |
| `density_hint / airports / from_region / area` | **不用**（原文已在 `raw_*`） | — |
| `*_is_dash` | 必用（决定写 `"-"` 还是数值） | §3-R5 类型混淆 |
| `price_day{n}_raw` | Air 周表非数字 day 列 | §3-R5 字符串被当 None |
| `effective_date_raw` | Air Surcharges E 列 | §3-R7 原件若是 str 会退化为 None |
| `currency_assumption / parser_version` | **不用**（内部元数据） | — |
| `all_fees_dash / all_fees_empty` | **不用**（检索层用） | — |

### 8.1 若 Ocean parser 未保留 `raw_cell_value`（关键补漏点）

**架构判断**：Ocean JP 的 `AT COST (COLLECT)` / `Included` / `-` / `MBL CC` / `Subject to …` 这些字符串如果 parser 没原封保留在 extras，writer 无法正确回填。

- **检查动作**（开发大师在 T-W1 前做）：`grep -rn "raw_cell_value" backend/app/services/step1_rates/adapters/ocean.py`
- **若缺失**：不在本任务单范围，需要回头补 Ocean parser（提给业务大师 + 架构大师评估是否另开 T-WX0）
- **若已在**：直接用；writer 按字段名取

开发大师在实现 T-W3（OceanWriter）前**必须确认这一点**，若缺失则本任务单的 T-W3 阻塞，提回架构大师。

---

## 9. 任务拆分（T-W1..T-W7）

| ID | 标题 | 工时 | 依赖 |
|---|---|---|---|
| T-W1 | writers/{protocols.py, base.py, templates.py, naming.py, registry.py, __init__.py} + 单元测试（is_formula_cell / safe_set / build_filename） | 0.5 天 | 无 |
| T-W2 | AirWriter 实现 + round-trip 测试（周表 + Surcharges） | 1 天 | T-W1 |
| T-W3 | OceanWriter 实现（JP / 其他港 / LCL 三 sheet 分派 + 生效期写入） | 1 天 | T-W1；**前置检查 §8.1 raw_cell_value** |
| T-W4 | OceanNgbWriter 实现（Q-W4 公式纪律 + sample/Shipping line name 跳过） | 0.5 天 | T-W1 |
| T-W5 | API 路由 `rate_downloads.py` + router.py 注册 + 4 种错误码 | 0.25 天 | T-W2/3/4 任一先交付即可上线单类型 |
| T-W6 | pytest round-trip 验收（V-W01..V-W15） | 1 天 | T-W2/3/4 全部完成 |
| T-W7 | （可选）warning 视觉标记 | — | **本轮不做**（Q-W8 默认"不做"，Demo 后若客户要再开） |

**总计 4.25 人日**，与 4/28 里程碑对齐。T-W2/T-W3/T-W4 可并行，由 3 位开发大师分担或 1 位串行 2.5 天交付。

---

## 10. 验收点（V-W01..V-W15，交给测试大师）

### 10.1 通用 round-trip 验收（3 份文件各跑一次）

| ID | 断言 |
|---|---|
| V-W01 | round-trip 完整性：原件 → upload → parse → writer → 再 load；除入库 record 对应的数据 cell 外，其余 cell 的 `.value` 与原件**完全一致**（字符串比较，含 `\n` 与尾空格） |
| V-W02 | `ws.merged_cells.ranges` 集合（转 `set(str(r))`）before/after 相等（3 份文件、每个 sheet 分别断言） |
| V-W03 | `cell.comment` 全保留：遍历原件所有有 comment 的 cell，after 同位置 `cell.comment.text` 完全相等（含作者名 `Zhang Jieyi`） |
| V-W04 | `column_dimensions` 所有 key 的 `.width` / `.hidden` 不变 |
| V-W05 | `freeze_panes` / `print_area` 不变 |
| V-W06 | 所有原件中的 `datetime` cell，writer 输出仍是 `datetime`（不是 str） |

### 10.2 Air 专项

| V-W07 | 【Air】Apr 20 to Apr 26 的 R22 `B22` 回填后等于 `"MH/FM 3 days servcie "`（含 servcie 拼写 + 末尾空格，bytes 级比较） |
| V-W08 | 【Air】R27 `B27` 等于 `"BR/SQ 3-4 days\nservice"`（含 `\n`） |
| V-W09 | 【Air】Surcharges C5:C67 合并区 value 等于原件 `"CHINA / SHA \n\n\n…注\n意\n生\n效\n日\n期"` 字符串；合并范围仍是 `C5:C67` |
| V-W10 | 【Air】Surcharges K5 批注原样保留（含 `"AA will implement variable airfreight surcharge (PSC)\n0.34/kg, MIN 568"`） |
| V-W11 | 【Air】上周 sheet `Apr 13 to Apr 19` 数据区为空或与模板一致（Q-W2 默认） |

### 10.3 Ocean 专项

| V-W12 | 【Ocean】JP `A45:A54` Destination 纵向合并保留；FCL 其他港 3 行组合并保留 |
| V-W13 | 【Ocean】LCL `L27` = `"关封货物只接受新加坡转拼的服务，运费另询"`（中文原样） |
| V-W14 | 【Ocean】LCL `L10` 和 `B26` 两处批注（Zhang Jieyi）保留 |

### 10.4 Ocean-NGB 专项（**最关键**）

| V-W15 | 【Ocean-NGB】Rate sheet 公式数量 **≥ 1687 − N**（N = 入库 Lv.1 行数 × Lv.1 本身不应含公式的 cell 数，理论 N=0）；推荐严格断言 `len(after_formulas) == 1687` |
| V-W16 | 【Ocean-NGB】Lv.2 `=ROUNDUP(R2*1.1,-1)` 和 Lv.3 `=ROUNDUP(R2*1.2,-1)` 公式在 writer 输出后仍存在（按坐标 set 比较） |
| V-W17 | 【Ocean-NGB】`sample` 和 `Shipping line name` 两个 sheet 整 sheet 的所有 cell `.value` 与原件 bytes 级相等（writer 一行都不碰） |

### 10.5 API 层

| V-W18 | `GET /api/v1/rate-batches/{不存在}/download` 返回 404 |
| V-W19 | `GET /api/v1/rate-batches/{draft 但模板文件已删}/download` 返回 422 |
| V-W20 | 文件名符合 §7 命名模板（`【Air】 Market Price updated on Apr 20.xlsx` 等） |

---

## 11. 风险与兜底

| 风险 | 触发场景 | 兜底 |
|---|---|---|
| RW1 **Ocean parser 未保留 raw_cell_value** | T-W3 开工发现 AT COST/Included 等文本无法回填 | §8.1 前置检查；发现即停 T-W3，回炉 Ocean parser 加 `raw_cell_value` extras |
| RW2 NGB writer 误触 Lv.2/Lv.3 公式 cell | `safe_set` 未守卫、或 `column_index_map` 指错 | `is_formula_cell` 强制守卫 + V-W15/V-W16 红线验收 |
| RW3 原件模板被用户 rate_batch_service 清理（`saved_path.unlink`） | parser 失败路径（`rate_batch_service.py:85, 89`）会删文件；但 writer 需要活文件 | API 422 + 前端提示"请重新上传原件" |
| RW4 批次 `effective_from` 为 None | AirWriter `build_filename` 失败 | `build_filename` fallback：用 `now.date()` 作为 effective_from |
| RW5 sheet_name 不在工作簿内 | 历史版本 sheet 名变动（如 `Apr 20 to Apr 26` → `Week 17`） | writer 抛 warning，跳过该 sheet 的记录；不 fail-fast |
| RW6 memory_stub 重启丢失 draft | `_draft_batches` 是进程内字典（`rate_batch_service.py:50`） | 本轮不解决（Step1 Demo 期间可接受）；Phase 2 上 DB 持久化 |
| RW7 Q-W4 业务回复是"要公式 + 入库 Lv.2/Lv.3 实际值不一致" | 公式算 `=ROUNDUP(R2*1.1,-1)` 和入库值不等 | 本轮兜底：**保留公式**（尊重原件活性），不写 Lv.2/Lv.3 数值；若不一致发 warning 入日志 |
| RW8 Air Surcharges AREA/FROM 合并区被误写 | 直接对 C5 赋值会破坏 C5:C67 合并 | writer 跳过 B/C 两列（§5.1） |
| RW9 `safe_set` 的 `value is None` 判断误清模板文本 | 入库字段真的应该清空（业务真空）vs "我没收到数据" | 本轮规则：**None 一律不写**；真空由入库端用 `extras.*_is_empty=True` 显式标注后 writer 才清（本任务不实现，留给 Phase 2） |

---

## 12. 本轮不做（与业务需求 §9 对齐）

- 多批次合并导出（业务 §9）
- 换汇（未列入）
- 删除历史批次（本 writer 只读）
- PDF 导出（业务 §9）
- 前端下载按钮实现（前端大师另开任务；本单只给 API 契约）
- 新增 Warnings sheet（Q-W8 默认"不做"）
- 机场代码受控词表 / 船司字典查询（writer 只回填原文）
- 任何 DB schema / Alembic 变更

---

## 13. 开发大师开工前 Checklist

1. 读业务需求 `docs/Step1_原格式回填Writer_业务需求_20260422.md`（323 行）一遍
2. 读本任务单 §0（Q-W4 实测）、§2（R1-R8 映射）、§8.1（raw_cell_value 前置检查）
3. **跑一遍** `/tmp/ngb_formula_test.py` 自证公式保留（40 秒）
4. 按 §9 T-W1 顺序动手；遇到 §11 风险清单触发条件 → 立即停并回架构大师
5. 每交付一个 writer 立即跑对应 V-Wn（§10），不要等全部写完

---

**架构任务单拆解完。开发大师请按 §3 文件清单和 §9 顺序动手。**
