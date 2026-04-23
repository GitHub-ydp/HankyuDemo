# Step2 T-B8 — customer_identifier 架构任务单

- **版本**：v1.0（2026-04-23）
- **作者**：架构大师
- **拆分依据**：
  - 业务需求：`docs/Step2_入札対応_T-B8_customer_identifier_业务需求_20260423.md`（v1.0 双分类 only：Customer A vs unknown；§2 维度 / §3 优先级 / §4 边界 / §5 输出 / §6 抽样）
  - 总架构任务单：`docs/Step2_入札対応_Customer_A_架构任务单_20260422.md` §17 第 1033 行（T-B8 在 5 步流的位置）
  - 同类粒度参考：`docs/Step2_入札対応_T-B5_RateMatcher_架构任务单_20260423.md`
- **本任务单单独面向开发大师 + 测试大师**。
- **强制约束**：
  - 不写实际函数体（只给签名 + 注释级别伪步骤）
  - 不引入新依赖（仅用既有 `openpyxl / dataclasses / pathlib`）
  - **禁止为 Customer B / E / Nitori 留任何 stub 字段或 stub 函数**（业务大师明令；推翻总架构任务单 §17 T-B8 中"stub profile 注册（B/E/Nitori 留 NotImplementedError）"那条旧表述）
  - **禁止**为维度 A（邮件域名）/ 维度 C（文件名）留 stub 字段、配置项、白名单（v1.0 不启用即彻底不写）
  - 凡 file:line 必须真实存在，监工抽查

---

## 0. 上下文复盘（开发大师必读 30 秒）

- 上游 = 前端上传一份 `.xlsx`；service.py（T-B9 待建）调用 `identify(path)` 拿到结论后再决定是否进 `CustomerAProfile.parse`
- 下游 = T-B9 service 编排；本任务**不**改 service.py、不调 AI、不写 DB、不写 Excel
- 现有 `CustomerAProfile.detect`（`backend/app/services/step2_bidding/customer_profiles/customer_a.py:93-115`）已实现"维度 B + 维度 D 的 B/C 双关键字命中 ≥2"；本任务两件事：
  1. **新建 `customer_identifier.py`** 作为对外统一入口，输出业务需求 §5 规定的 `IdentifierResult`
  2. **升级 `CustomerAProfile.detect`** 在第 108-113 行循环内追加 G 列 `主要キャリアとルート` 校验，提高 Customer E 误判抵抗力（业务需求 §2-D）

---

## 1. 任务范围（in / out）

### 1.1 in（v1.0 必做）

- 实现 v1.0 双分类：返回 `customer_a` 或 `unknown`，**禁止其它取值**
- 实现维度 B（sheet 名等值 `見積りシート` 且单 sheet）
- 实现维度 D（表头第 1~10 行内浮动扫描，找到一行同时满足 B 列等于 `発地` ∧ C 列包含 `着地` ∧ G 列等于 `主要キャリアとルート`）
- 维度 B / D 是 **OR 关系**（业务需求 §3 关键约束 1）
- 升级 `customer_a.py:108-113` 的 detect 循环，追加 G 列校验
- 输出 `IdentifierResult` dataclass（字段见 §3.2）

### 1.2 out（v1.0 不做，且不留 stub）

- 维度 A（邮件域名）：v1.0 输入对象只有 xlsx 文件，邮件不在范围
- 维度 C（文件名关键字）：客户原始文件名样本未提供
- Customer B / E / Nitori 的识别（全部走 unknown 路径）
- 同义词表 / 模糊关键字（如 `発地|出発地`）
- 历史偏好记忆 / LLM 辅助识别
- 二次确认提示（手选 vs 自动识别冲突弹窗）—— 留 T-B10 前端
- service 编排里"营业手选优先级 > 自动识别"的逻辑 —— 留 T-B9

### 1.3 与 T-B9 service 编排的边界

- 本任务**只**实现 `identify(path) -> IdentifierResult`；service 是否信任 `IdentifierResult`、是否被营业手选覆盖、是否走二次确认 —— 全部归 T-B9
- service 调用本模块的入口签名：`result = identify(xlsx_path); if result.matched_customer == "customer_a": CustomerAProfile().parse(...)`

---

## 2. 数据流（4 行说清）

```
xlsx 文件路径 ──► identify(path)
                    │
                    ├─ openpyxl.load_workbook(read_only=True, data_only=True) ─► 异常 / 空 / 多 sheet → unknown + warning
                    │
                    ├─ 维度 B 检查（sheetnames == ['見積りシート']） ──┐
                    │                                                  ├─ B OR D ─► matched_customer='customer_a'
                    └─ 维度 D 检查（行 1~10 扫 B/C/G 三关键字）  ──────┘  否则 'unknown'
                                                                          │
                                                                          ▼
                                                              IdentifierResult(matched_customer, matched_dimensions, source, confidence, unmatched_reason, warnings)
```

---

## 3. 文件级改动清单

### 3.1 改动表

| 路径 | 行号提示 | 新建/修改 | 做什么 |
|---|---|---|---|
| `backend/app/services/step2_bidding/customer_identifier.py` | 全文（约 130 行含注释） | **新建** | T-B8 唯一新增源文件；模块级 `identify()` 函数 + `IdentifierResult` dataclass |
| `backend/app/services/step2_bidding/customer_profiles/customer_a.py` | **第 108-113 行**（detect 内部循环） | **修改** | 在判定 `b_val == _HEADER_ORIGIN_LABEL and _HEADER_DEST_LABEL in c_val` 处追加 `and _norm_text(ws.cell(r, _COL_CARRIER).value) == _HEADER_CARRIER_LABEL`；并在第 27 行下方新增模块常量 `_HEADER_CARRIER_LABEL = "主要キャリアとルート"` |
| `backend/app/services/step2_bidding/__init__.py` | 第 19 行后追加 `from .customer_identifier import IdentifierResult, identify`；第 22-36 行 `__all__` 列表追加 `"IdentifierResult", "identify"` | **修改** | 暴露公共入口 |
| `backend/tests/services/step2_bidding/test_customer_identifier.py` | 全文（约 200 行） | **新建** | 见 §6 测试用例 |

### 3.2 IdentifierResult 字段设计（架构大师拍板）

放在 `customer_identifier.py` 模块内（**不**放进 `entities.py`：业务上仅本模块产出，下游 service 透传，不参与跨模块共享）。

```python
@dataclass(frozen=True, slots=True)
class IdentifierResult:
    matched_customer: str            # "customer_a" | "unknown"，禁止其他取值
    matched_dimensions: tuple[str, ...]  # 子集 ⊆ ("B", "D")；unknown 路径为 ()
    source: str                      # "auto"（本模块所有判定）；"manual" / "default_unknown" 留 service 层用，本模块不输出
    confidence: str                  # "high" | "medium" | "low"
    unmatched_reason: str | None     # matched_customer == "unknown" 时必填业务可读文本；customer_a 时为 None
    warnings: tuple[str, ...] = ()   # 异常文本数组（业务需求 §5 字段定义）
```

**字段拍板理由**：
- `matched_dimensions` 用 `tuple` 而不是 `list`：dataclass `frozen=True` 要求字段可哈希，便于日志去重 / 对比
- `source` 仅取 `"auto"`：业务需求 §5 表格里的 `manual / default_unknown` 是 service 层语义，本模块不该越权
- `confidence` 业务需求明确"业务标签，不是数值"，用 str 而非 float
- 不另设 `error_code` 字段：损坏 / 加密等场景用 `warnings` 文本 + 约定前缀（`WBOPEN_FAIL: ...`）即可，避免错误码枚举膨胀

### 3.3 是否引入新 Protocol？

**不引入**。理由：
1. v1.0 只有一个识别器（B/D 两维度都靠 openpyxl 读 xlsx），没有第二实现做对比抽象的对象
2. 业务大师禁止为 Customer B/E/Nitori 留 stub，未来即便 v2.0 加同义词表 / 邮件域名 / LLM 辅助，扩展是在**同一个 identify 函数体内追加分支**，不是另一个实现替换
3. 遵循 `CLAUDE.md` "Three similar lines is better than a premature abstraction"
4. 入口形式定为**模块级函数** `identify(path) -> IdentifierResult`，**不**包成 class（无状态、无依赖注入需求）

### 3.4 禁止改动

- `backend/app/services/step2_bidding/entities.py`（IdentifierResult 不放这里）
- `backend/app/services/step2_bidding/protocols.py`（不加 CustomerIdentifier Protocol）
- `backend/app/services/step2_bidding/customer_profiles/customer_a.py` 中 detect 之外的任何函数（`parse / fill / _scan_headers / _parse_sections_and_rows / _build_pkg_row` 全部不改）
- `backend/app/services/step2_bidding/rate_repository.py / rate_matcher.py`

---

## 4. customer_identifier.py 接口骨架（不写函数体）

```python
# backend/app/services/step2_bidding/customer_identifier.py
"""Step2 T-B8 customer_identifier 实现。

业务依据：docs/Step2_入札対応_T-B8_customer_identifier_业务需求_20260423.md
v1.0 双分类 only：customer_a vs unknown。
禁止为 Customer B / E / Nitori / 维度 A / 维度 C 留 stub。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

# -------- 模块级常量 --------
_CUSTOMER_A = "customer_a"
_UNKNOWN = "unknown"

_SHEET_NAME_CUSTOMER_A = "見積りシート"      # 维度 B 等值匹配
_HEADER_ORIGIN = "発地"                       # 维度 D - B 列等值
_HEADER_DEST_KEYWORD = "着地"                 # 维度 D - C 列包含
_HEADER_CARRIER = "主要キャリアとルート"      # 维度 D - G 列等值（新增）

_COL_B = 2
_COL_C = 3
_COL_G = 7

_HEADER_SCAN_FIRST_ROW = 1
_HEADER_SCAN_LAST_ROW = 10                    # 业务需求 §2-D：1~10 行浮动


@dataclass(frozen=True, slots=True)
class IdentifierResult:
    """customer_identifier 唯一输出契约。字段语义见业务需求 §5。"""
    matched_customer: str
    matched_dimensions: tuple[str, ...]
    source: str
    confidence: str
    unmatched_reason: str | None
    warnings: tuple[str, ...] = ()


def identify(xlsx_path: Path) -> IdentifierResult:
    """v1.0 双分类入口。

    步骤：
      1. load_workbook(read_only=True, data_only=True)
         - OSError / InvalidFileException / zipfile.BadZipFile → _make_unknown(reason="文件无法打开", warnings=("WBOPEN_FAIL: ...",))
      2. 若 wb.sheetnames == [] → _make_unknown(reason="工作簿无 sheet", warnings=("EMPTY_WB",))
      3. 维度 B 判断：dim_b = (len(sheetnames) == 1 and _normalize_sheet_name(sheetnames[0]) == _SHEET_NAME_CUSTOMER_A)
      4. 维度 D 判断：
         - 选取扫描 sheet：dim_b 命中时用 sheetnames[0]；
                          dim_b 不命中且 len(sheetnames) > 1 时遍历每个 sheet，任一命中即 dim_d=True
                          （满足业务需求 §4 表"多 sheet 但其中一个 sheet 名等于 見積りシート"行的"若 D 在那个 sheet 命中则仍返 customer_a"语义；
                           但同时按业务需求 §4 + §需求 2-B 第 1 条：B 维度恒不中，warnings 追加 "MULTI_SHEET"）
         - 单 sheet 内扫描行 1~10，对每行判断 _row_matches_dim_d(ws, row)
      5. 组装：
         - dim_b or dim_d → matched_customer=customer_a
                          confidence = "high" if (dim_b and dim_d) else "medium"
                          warnings 追加：dim_b ^ dim_d 时给业务需求 §3 关键约束 3/4 的提示文本
         - 都不中 → matched_customer=unknown
                  confidence = "low"
                  unmatched_reason = _build_unmatched_reason(sheetnames, dim_d_scan_summary)
      6. source 恒为 "auto"
    """
    ...


# -------- 私有辅助 --------

def _normalize_sheet_name(name: str | None) -> str:
    """业务需求 §4：strip 前后空白；不做大小写折叠；不做半角全角折叠。"""
    ...


def _normalize_header_cell(value: object) -> str:
    """业务需求 §2-D normalize 规则：strip 前后空白 + 去全角空格；不剥括号注解；不做大小写折叠 / 半角全角折叠。

    注意：`_HEADER_DEST_KEYWORD` 仅做 `in` 包含判断，不要把括号剥掉。
    """
    ...


def _row_matches_dim_d(ws, row_idx: int) -> bool:
    """同一行 (row_idx) 上：B 列==発地 ∧ C 列⊇着地 ∧ G 列==主要キャリアとルート。任一不中即 False。"""
    ...


def _make_unknown(*, reason: str, warnings: tuple[str, ...] = ()) -> IdentifierResult:
    """统一构造 unknown 结果。matched_dimensions=()、source='auto'、confidence='low'。"""
    ...


def _build_unmatched_reason(sheetnames: list[str], dim_d_summary: str) -> str:
    """unknown 时给营业看的业务可读原因。

    示例输出："sheet 名 'AIR入力フォーム'，非 Customer A 模板；表头行 1-10 未找到 (発地, 着地, 主要キャリアとルート) 三关键字组合"
    """
    ...
```

> 与业务需求 §5 字段一一对照：开发大师在 `_make_unknown` / `identify` 末尾构造 IdentifierResult 时**必须填全所有字段**；customer_a 路径 `unmatched_reason` 必为 None。

---

## 5. 核心识别步骤（按业务需求 §2 + §3 翻译）

### 5.1 步骤 1：打开 workbook（异常即 unknown）

```
try:
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
except (OSError, InvalidFileException, BadZipFile, KeyError) as e:
    return _make_unknown(reason="文件无法打开", warnings=(f"WBOPEN_FAIL: {type(e).__name__}",))
```

- 业务依据：业务需求 §4 边界规则表第 2 行（损坏文件不抛异常）
- 兜底覆盖加密文件场景（业务需求 §4 第 3 行 + Q-T-B8-03）：openpyxl 打开加密 xlsx 抛 InvalidFileException，被同一 except 接住

### 5.2 步骤 2：空 workbook

```
if not wb.sheetnames:
    return _make_unknown(reason="工作簿无 sheet", warnings=("EMPTY_WB",))
```

- 业务依据：业务需求 §4 边界规则表第 7 行

### 5.3 步骤 3：维度 B 判定

```
sheetnames = wb.sheetnames
dim_b = (len(sheetnames) == 1 and _normalize_sheet_name(sheetnames[0]) == _SHEET_NAME_CUSTOMER_A)
warnings_acc: list[str] = []
if not dim_b and len(sheetnames) > 1 and _SHEET_NAME_CUSTOMER_A in [_normalize_sheet_name(n) for n in sheetnames]:
    # 多 sheet 但含 見積りシート：B 维度按业务需求 §需求 2-B 第 1 条不中；记 MULTI_SHEET 警告
    warnings_acc.append(f"MULTI_SHEET: 工作簿含 {len(sheetnames)} 个 sheet，含 '見積りシート' 但非单 sheet 模板")
```

- 业务依据：业务需求 §需求 2-B 第 1 条 "工作簿恰好 1 个 sheet" 且 "sheet 名等值"
- 业务需求 §4 表第 9 行：多 sheet 含 `見積りシート` 时，B 维度不中；若 D 在那个 sheet 命中仍 customer_a + warning「附加 sheet」（这条已被本步 + 步骤 4 联合实现）

### 5.4 步骤 4：维度 D 判定（行 1~10 浮动扫描）

```
dim_d = False
target_sheets = [sheetnames[0]] if dim_b else sheetnames   # dim_b 命中时只扫该 sheet；否则全扫
for sn in target_sheets:
    ws = wb[sn]
    last_scan = min(ws.max_row or 0, _HEADER_SCAN_LAST_ROW)
    for r in range(_HEADER_SCAN_FIRST_ROW, last_scan + 1):
        if _row_matches_dim_d(ws, r):
            dim_d = True
            break
    if dim_d:
        break
```

- 业务依据：业务需求 §需求 2-D 第 1 条 + §4 表第 9 行

### 5.5 步骤 5：组装 IdentifierResult

```
dims = tuple(d for d, hit in (("B", dim_b), ("D", dim_d)) if hit)
if dims:
    matched = _CUSTOMER_A
    confidence = "high" if len(dims) == 2 else "medium"
    if dim_b and not dim_d:
        warnings_acc.append("HEADER_MISMATCH: sheet 名命中但表头三关键字未全中，解析可能失败")
    if dim_d and not dim_b:
        warnings_acc.append(f"SHEET_NAME_VARIANT: 表头命中但 sheet 名异常: {sheetnames!r}")
    return IdentifierResult(matched, dims, "auto", confidence, None, tuple(warnings_acc))

# 都不中
reason = _build_unmatched_reason(sheetnames, ...)
return IdentifierResult(_UNKNOWN, (), "auto", "low", reason, tuple(warnings_acc))
```

- 业务依据：业务需求 §3 优先级表 + 关键约束 1/2/3/4

### 5.6 步骤 6：升级 customer_a.py:108-113 detect 循环

**真实 file:line**：`backend/app/services/step2_bidding/customer_profiles/customer_a.py` 第 108-113 行（grep 已核：第 93 行 `def detect(...)`，第 108 行 `for r in range(1, scan_limit + 1):`，第 113 行 `return header_count >= 2`）。

改动 ≤ 5 行：
1. 第 27 行下追加常量 `_HEADER_CARRIER_LABEL = "主要キャリアとルート"`（无新增导入）
2. 第 108-112 行循环体：判断条件追加 `and _norm_text(ws.cell(r, _COL_CARRIER).value) == _HEADER_CARRIER_LABEL`（`_COL_CARRIER` 已在第 36 行定义为 7）
3. 不动 `header_count >= 2` 阈值（保持向后兼容现有 14 条 pytest）

> 业务依据：业务需求 §需求 2-D 第 110 行明确"现行 detect 用 B+C 双关键字 + 计数 ≥2，本规则在此基础上追加 G 列校验"

---

## 6. normalize 规则汇总（业务需求 §4）

| 对象 | 操作 | 不做 |
|---|---|---|
| sheet 名 | `name.strip()`（去前后空白） | 不做大小写折叠；不做半角全角折叠 |
| 表头单元格（B/C/G） | `str(value).strip()`，再 `replace("　", "")`（去全角空格） | 不剥圆括号 / 注解（C3 的 `(到着空港)` 保留，因匹配只要求 `in`）；不做大小写折叠；不做半角全角折叠 |
| `_HEADER_DEST_KEYWORD` 匹配 | `_HEADER_DEST_KEYWORD in normalized_c` | 不做等值匹配（C3 含括号注解） |

---

## 7. 错误处理 / 边界（与业务需求 §4 一一对应）

| 业务场景 | 行为 | 业务依据 |
|---|---|---|
| 文件不存在（FileNotFoundError） | 走 §5.1 except 分支 → unknown + warning `WBOPEN_FAIL: FileNotFoundError` | 业务安全（业务需求 §4 第 2 行同性质） |
| xlsx 损坏 / 非 zip | unknown + warning `WBOPEN_FAIL: BadZipFile` | 业务需求 §4 第 2 行 |
| 加密 / 设密码 | unknown + warning `WBOPEN_FAIL: InvalidFileException`（openpyxl 抛此异常） | 业务需求 §4 第 3 行 + Q-T-B8-03 |
| `.xlsm`（带宏） | 当普通 xlsx 走完整流程；命中即 customer_a | 业务需求 §4 第 4 行 |
| 空 workbook（0 sheet） | unknown + warning `EMPTY_WB` | 业务需求 §4 第 7 行 |
| 多 sheet（含 `見積りシート`） | B 维度不中（B 要求单 sheet）+ warning `MULTI_SHEET`；D 仍扫所有 sheet，命中则 customer_a | 业务需求 §4 第 9 行 + §需求 2-B 第 1 条 |
| 多 sheet（不含 `見積りシート`） | B 维度不中（不写 MULTI_SHEET 警告，避免误导）；D 仍扫所有 sheet | 业务需求 §需求 2-B 反例（Customer E / Nitori） |
| 表头扫描 1~10 行无命中 | 维度 D=False（不报 warning，正常路径） | 业务需求 §需求 2-D 第 1 条 |
| sheet 名前后带空白 | normalize 后等值即 B 中（`'  見積りシート  '` → 中） | 业务需求 §需求 2-B 第 2 条 |
| sheet 名半角全角混用 | 不做折叠 → 不中（业务无样本，保守） | 业务需求 §需求 2-B 第 2 条 |

---

## 8. 测试用例点位（交测试大师独立验证）

测试文件 `backend/tests/services/step2_bidding/test_customer_identifier.py`，沿用 T-B4 测试同款 `GOLDEN_SAMPLE = Path(__file__).resolve().parents[4] / "资料" / ...` 路径模式（参考 `test_customer_a_parse.py:17-24`），**不**用 mock，直接走真实文件 + 临时损坏文件夹。

共 **12 条 + 1 条回归** 验收用例：

| ID | 名称 | 输入构造 | 期望 | 覆盖 |
|---|---|---|---|---|
| V-T-B8-01 | customer_a_sample_1 | `资料/.../Customer A (Air)/Customer A (Air)/2-①.xlsx` | matched_customer="customer_a"，matched_dimensions=("B","D")，confidence="high"，warnings=() | §5.3+§5.4 happy path |
| V-T-B8-02 | customer_a_sample_2 | `2-②.xlsx` | 同上 | §5.3+§5.4 |
| V-T-B8-03 | customer_a_sample_4 | `2-④.xlsx` | 同上 | §5.3+§5.4 |
| V-T-B8-04 | customer_b_unknown | `资料/.../Customer B (Ocean,LCL)/Customer B (Ocean,LCL)/2-①.xlsx` | matched_customer="unknown"，matched_dimensions=()，confidence="low"，unmatched_reason 文本含 sheet 名 `2025 LCL RATE` 字样 | §5.5 unknown 路径 |
| V-T-B8-05 | customer_e_unknown | `资料/.../Customer E (Air & Ocean)/Customer E (Air & Ocean)/2-①.xlsx` | matched_customer="unknown"；warnings 不含 MULTI_SHEET（因不含 見積りシート）；unmatched_reason 包含 `AIR入力フォーム` | §5.3 多 sheet 但不含目标 sheet |
| V-T-B8-06 | nitori_unknown | `资料/.../ニトリ様海上入札/ニトリ様海上入札/阪急阪神【to GLOBAL】2026年1月～3月_見積り書.xlsx` | matched_customer="unknown"；matched_dimensions=() | §5.3 多 sheet |
| V-T-B8-07 | corrupted_xlsx | tmp_path 下写入 1KB 随机字节，文件名 `bad.xlsx` | matched_customer="unknown"；warnings=("WBOPEN_FAIL: BadZipFile",) 或类似前缀 | §5.1 异常分支 |
| V-T-B8-08 | multi_sheet_with_target | tmp_path 用 openpyxl 造 2 sheet：`['見積りシート', 'Notes']`；見積りシート 表头第 3 行填齐 B/C/G 三关键字 | matched_customer="customer_a"（D 在第一 sheet 命中）；matched_dimensions=("D",)；warnings 含前缀 `MULTI_SHEET`；confidence="medium" | §5.3+§5.4 多 sheet 边界 |
| V-T-B8-09 | header_in_row_5 | tmp_path 造单 sheet，名 `見積りシート`；前 4 行填公告文本，第 5 行填 B=`発地` C=`着地 (到着空港)` G=`主要キャリアとルート` | matched_customer="customer_a"；matched_dimensions=("B","D")；confidence="high" | §5.4 浮动扫描 |
| V-T-B8-10 | only_dim_b | tmp_path 造单 sheet，名 `見積りシート`；表头 B/C/G 填错（如 G=空） | matched_customer="customer_a"；matched_dimensions=("B",)；confidence="medium"；warnings 含 `HEADER_MISMATCH` 前缀 | §3 关键约束 4 |
| V-T-B8-11 | only_dim_d | tmp_path 造单 sheet，名 `Quote Sheet 2026-01`；表头第 3 行 B/C/G 填齐 | matched_customer="customer_a"；matched_dimensions=("D",)；confidence="medium"；warnings 含 `SHEET_NAME_VARIANT` 前缀 | §3 关键约束 3 |
| V-T-B8-12 | sheet_name_with_whitespace | tmp_path 造单 sheet，名 `'  見積りシート  '`（前后各 2 空格）；表头不填 | matched_customer="customer_a"；matched_dimensions=("B",)；confidence="medium" | §6 normalize 规则 |

**附加回归用例**：

| V-T-B8-R01 | customer_a_detect_existing_pytest_pass | 直接重跑 `pytest backend/tests/services/step2_bidding/test_customer_a_parse.py -v` | 现有 14 条 pytest 全过（特别是 `test_v_b01_detect_returns_true`） | §5.6 升级 detect 不破坏 T-B4 |

> **不写**：service 编排测试 / API 测试 / 多语言 unmatched_reason 文案测试（不在本任务范围）。
> **测试 fixture 复用**：`GOLDEN_SAMPLE` 路径模式抄 `test_customer_a_parse.py:17-24`，不要新造工具。

---

## 9. 依赖 / 阻塞

### 9.1 内部依赖

| 依赖 | 来源 | 状态 |
|---|---|---|
| openpyxl `load_workbook` | 项目既有依赖 | 就绪 |
| `CustomerAProfile.detect` 升级（追加 G 列） | `customer_a.py:108-113` | 本任务内附带改 |
| 黄金样本 3 份 | `资料/2026.04.02/Customer A (Air)/Customer A (Air)/2-①ⅡⅣ.xlsx` | 就绪（业务需求 §0 已核） |
| 反例样本 3 份（B/E/Nitori 各 1 份） | `资料/2026.04.02/` 三子目录 | 就绪（grep find 已核，§1.2 路径） |

### 9.2 不阻塞的事项

- **T-B5 RateMatcher** / **T-B6 Markup** / **T-B7 fill**：本任务输出仅 IdentifierResult，与下游算法无耦合
- **T-B9 service**：本任务交付独立模块；service 编排是否引入本模块、如何与"营业手选"优先级合并 —— T-B9 范围
- **T-B10 API**：`unmatched_reason` 文案前端如何展示 —— T-B10 范围

### 9.3 P1 楢崎问题（不阻塞 v1.0 落地）

业务需求 §需求 8 列了 5 条 Q-T-B8-01..05，**全部 P1 不阻塞**：
- Q-T-B8-01（手选 vs 自动识别二次确认）：归 T-B9 + T-B10
- Q-T-B8-02（客户原始文件名特征）：v1.0 不启用维度 C，本模块零代码
- Q-T-B8-03（加密 xlsx）：本任务已用 §5.1 except 分支兜底为 unknown + WBOPEN_FAIL
- Q-T-B8-04（客户邮箱域名）：v1.0 不启用维度 A，本模块零代码
- Q-T-B8-05（客户改 sheet 名 / 表头日文写法回 unknown 还是 customer_a + 警告）：本任务按业务需求 §3 关键约束 1（OR 关系）默认"任一中即 customer_a + 警告"。楢崎若改"必须双中"，只需在 §5.5 改 1 行（`if dims and len(dims) == 2:`），不阻塞 v1.0

### 9.4 监工警示

- 升级 `customer_a.py:108-113` 后，**测试大师必须重跑 T-B4 14 条 pytest**（`pytest backend/tests/services/step2_bidding/test_customer_a_parse.py -v`），确保 V-B01 `detect_returns_true` 等仍全过（黄金样本 `2-①.xlsx` G3 实测 = `主要キャリアとルート`，追加校验后仍命中）
- 不得为 v2.0 提前留任何字段：本任务单**禁止**在 IdentifierResult 加 `_reserved_for_dim_a` 等空字段；**禁止**在 `customer_profiles/` 下新建 `customer_b_stub.py` 等空 stub 文件（覆盖总架构任务单 §17 旧表述）

---

## 10. 预估人天

| 角色 | 工时 | 内容 |
|---|---|---|
| 开发大师（实现） | **0.5 人天** | customer_identifier.py 新建（约 130 行含注释）+ customer_a.py 第 108-113 行 ≤ 5 行修改 + __init__.py 1 行追加 |
| 测试大师（独立验证） | **0.5 人天** | 12 条 + 1 条回归 pytest，复用 `GOLDEN_SAMPLE` 路径模式 + tmp_path 造样本 |
| **合计** | **1.0 人天** | 可在 1 工作日内交付完成 |

---

## 11. 验收 Checklist（监工抽查）

- [ ] `backend/app/services/step2_bidding/customer_identifier.py` 新增；含 `IdentifierResult` dataclass + 模块级 `identify()` 函数 + 4 个私有辅助
- [ ] `backend/app/services/step2_bidding/__init__.py` 第 19 行后追加 `IdentifierResult, identify` 导出，`__all__` 同步追加
- [ ] `backend/app/services/step2_bidding/customer_profiles/customer_a.py:108-113` detect 循环条件追加 G 列等值判断；第 27 行下方追加 `_HEADER_CARRIER_LABEL` 常量
- [ ] **未新建** `customer_b_stub.py / customer_e_stub.py / nitori_stub.py`（grep `find backend/app/services/step2_bidding/customer_profiles -name '*stub*'` 应输出空）
- [ ] **未在 IdentifierResult 中加** 维度 A / 维度 C 相关字段（grep `dim_a\|dim_c\|domain\|filename_pattern` 应输出空）
- [ ] 13 条 pytest（12 + 1 回归）全过：`pytest backend/tests/services/step2_bidding/test_customer_identifier.py -v`
- [ ] T-B4 14 条 pytest 仍全过：`pytest backend/tests/services/step2_bidding/test_customer_a_parse.py -v`（无回归）
- [ ] 不引入新依赖：`backend/requirements.txt` 无 diff

---

## 12. 监工汇报小结

**拆出子任务数**：1 个新源文件（customer_identifier.py）+ 1 处现有文件 ≤ 5 行修改（customer_a.py:108-113 + 第 27 行常量）+ 1 处 `__init__.py` 1 行追加 + 1 个新测试文件（13 条用例）= **4 件改动**，开发可 0.5 天内完成、测试 0.5 天内完成。

**IdentifierResult 字段拍板**：6 字段（`matched_customer / matched_dimensions / source / confidence / unmatched_reason / warnings`），全部对应业务需求 §5；`matched_dimensions` 用 `tuple` 而非 `list` 以支持 `frozen=True` 哈希；`source` 本模块恒输出 `"auto"`；不为 v2.0 留任何空字段。

**Protocol 拍板**：**不引入** `CustomerIdentifier` Protocol；入口形式为模块级函数 `identify(path)`（无状态、无依赖注入需求；遵循 CLAUDE.md "三份文件各一个 Adapter 就够了，不要搞通用解析框架"）。

**预估总人天**：1.0 人天。

**建议**：直接交开发大师按本文档实施。**不需要回业务大师补需求** —— 业务需求 §1-§8 已覆盖 T-B8 全部规则，5 条 Q-T-B8-01..05 全 P1 不阻塞 v1.0 落地，已用本任务单 §5/§7 默认值兜底。
