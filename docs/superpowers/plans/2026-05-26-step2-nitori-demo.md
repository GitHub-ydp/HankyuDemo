# Step2 Nitori 投标自动填写（Demo 级）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让系统吃进 Nitori 投标包里的【to GLOBAL 报价表 + 成本 Excel】，自动把中国发航线的运价/附加费填进报价表，产出「成本版 + 报价版」两个 .xlsm 给营业下载。

**Architecture:** 新增一个独立的 `NitoriProfile`（detect/parse/fill）+ 一个 `NitoriCostBook`（读成本 Excel）+ orchestrator 里一个 **Nitori 分支**（与 customer_a 完全隔离，customer_a 代码零改动）。Nitori 的成本来源是 bid 自带的成本 Excel，**不走 Step1 运价库、不走 RateMatcher**。匹配在 profile 内部完成，复用现有 `ParsedPkg/PkgRow/PerRowReport` 实体。

**Tech Stack:** Python 3.10 / openpyxl（`keep_vba=True` 保宏）/ extract-msg（从 .msg 取成本附件）/ pytest。

---

## 背景与关键事实（实施前必读）

本计划基于对真实文件的实测，事实如下，**不要重新假设**：

- **输入包**（`资料/2026.05.26/ニトリ様海上入札.zip` 解压后）：
  - `_【to GLOBAL】2026年7月～9月_見積り書.xlsm` —— 要填的报价表（**.xlsm 带宏**）。sheet：`お客様案内（TO Global)` / **`Quotation (Global) Jul-Sep`**（数据表）/ `所要日数 ` / `Bid Lane Check` / `通貨単位マスタ`(隐藏)。
  - `【to JAPAN】`/`【to TAIWAN】` —— **Demo 不做**。
  - `①…入札.msg`、`【2Q入札案内】…pdf` —— 规则书，**系统不解析**（规则固化进 profile 常量）。
  - 成本 Excel `Nitori _ 2026 7-9.xlsx` —— **藏在 `②（Cost）….msg` 的附件里**，需用 extract-msg 取出。
- **成本表结构**（`Nitori _ 2026 7-9.xlsx`）：
  - sheet `FCL`：表头 `POL | DESTINATION | CARRIER | 20GP | 40HC | BAF | YAS | LSS | ETD | Transit Port | T/T | Dest Free Time | REMARK`。有效行：`SHANGHAI`→PORT KELANG(N)/TANJUNG PELEPAS/LAEM CHABANG/HO CHI MINH/MANILA；`TAICANG`→LAEM CHABANG/HO CHI MINH（其余 `NO SERVICE`）。运价单位 USD。LSS 多为 `Included`。
  - sheet `FCL` 下方有三段 **ORIGIN FEE 文本块**（按船司）：`Booking: RMB250` / `THC: RMB630/20G…` / `DOC: RMB450/BL` / `EIR…` / `Manifest…`。
  - sheet `Sheet1`：表头 `港口（Discharge） | DEM（Free Time） | DET（Free Time） | Combine`，各港 28/7/35 天。
- **报价表 `Quotation (Global) Jul-Sep` 结构**：三行表头（r6 主、r7 次、r8 三级），**数据从 r9 起**。关键列（1-based）：
  - 航线键：`D(4)=CARRIER` `E(5)=COUNTRY(export)` `F(6)=POL` `G(7)=COUNTRY(import)` `H(8)=POD` `I(9)=SIZE`
  - 待填核心列（cur/amount 成对）：`Q(17)=T/T` `R(18)/S(19)=OCEAN FREIGHT cur/amount` `T(20)/U(21)=LSS` `Z(26)/AA(27)=THC` `AB(28)/AC(29)=DOC` `CY(103)=DEM FREE` `CZ(104)=DET FREE`
  - 中国发（SHANGHAI/TAICANG）行共 **48 行**（lane×size）。例：r114-116 SHANGHAI→PORT KLANG(NORTH) 20F/40F/40HC；r120-122 TAICANG→PORT KLANG(NORTH)（成本是 NO SERVICE → 应判 no_rate）。
- **归一难点**（已确认）：
  - POD 拼写：成本 `PORT KELANG` ↔ 报价 `PORT KLANG`；且报价把 KLANG 拆 `(NORTH)`/`(WEST)`，成本只有 `(N…)`。
  - SIZE：报价 `20F/40F/40HC`，成本只有 `20GP/40HC`（**无 40F**）。
  - `MANILA (N or S)`(成本) ↔ 报价 `MANILA` 系列。
- **.xlsm 回填实测结论**（已 spike 预验，见 Task 0 复核）：openpyxl `keep_vba=True` round-trip **保留宏、保留 5 个 sheet、公式重算正确**；但**丢部分数据验证下拉**、公式存储被改写。Demo 可接受，需 Task 0 用真 Excel 终确认宏可跑。

## 前置业务输入（由业务侧确认；本计划已给"Demo 默认值"，可直接跑，确认后改常量即可）

> 这些是 §需求未定项。计划用下列默认值实现，**全部集中在 `nitori_profile.py` 顶部常量区**，业务确认后改常量、跑测试即可，无需改逻辑。

| 项 | Demo 默认值（assumption） | 待业务确认 |
|---|---|---|
| 加价率 markup | `Decimal("1.15")`（沿用 customer_a） | Nitori 实际加价口径 |
| SIZE 映射 | `20F←20GP`、`40HC←40HC`、`40F←40HC`（同 40 价） | 40F 是否等于 40HC，还是留空 |
| POD `PORT KELANG (N…)` | 归一到 `PORT KLANG`，报价的 `(NORTH)` 和 `(WEST)` 两行**都填同一成本价**（成本未区分 N/W） | NORTH/WEST 是否应不同价 |
| LSS=`Included` 落法 | amount 写 `0`、cur 写 `USD`，备注另记 | 是否写文字 "Included" |
| 回填费目范围 | OCEAN FREIGHT / LSS / THC / DOC / T/T / DEM FREE / DET FREE | Booking/EIR/Manifest/BAF 等是否本期填、落哪列 |
| 输出版本 | 成本版 + 报价版 两个文件 | 是否只要报价版 |

---

## 文件结构

| 文件 | 职责 | 新建/改 |
|---|---|---|
| `backend/app/services/step2_bidding/customer_profiles/nitori.py` | NitoriProfile：detect / parse(报价表) / match(对成本) / fill(回填+加价) | 新建 |
| `backend/app/services/step2_bidding/nitori_cost_book.py` | NitoriCostBook：读成本 Excel（FCL+free time+origin费），提供 (POL,POD,SIZE)→成本 查询 | 新建 |
| `backend/app/services/step2_bidding/nitori_bundle.py` | 从 zip/目录定位 GLOBAL 报价表 + 从 .msg 取成本 Excel | 新建 |
| `backend/app/services/step2_bidding/customer_identifier.py` | 扩 `identify()` 增加 Nitori 识别（现仅 customer_a vs unknown） | 改 |
| `backend/app/services/step2_bidding/bidding_orchestrator.py` | identify 后增加 Nitori 分支 `_run_nitori(...)`；customer_a 路径不动 | 改 |
| `backend/tests/services/step2_bidding/test_nitori_cost_book.py` | 成本表解析用例 | 新建 |
| `backend/tests/services/step2_bidding/test_nitori_profile.py` | profile parse/match/fill 用例 | 新建 |
| `backend/tests/services/step2_bidding/test_nitori_identifier.py` | 识别用例 | 新建 |
| `backend/tests/services/step2_bidding/test_nitori_integration.py` | 真实文件端到端 | 新建 |

测试真实文件根目录常量（所有测试复用）：
```python
from pathlib import Path
NITORI_DIR = (
    Path(__file__).resolve().parents[4]
    / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
)
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"
COST_MSG = NITORI_DIR / "②（Cost）回复 HHESHA内部　転送 ニトリ海上運賃入札（2026年2Q7－９月）.msg"
```

---

## Phase 0 — Spike：.xlsm 回填可行性终确认（非 TDD，半天，最先做）

**目的：** 干掉最大技术风险——openpyxl 回填后宏/验证/公式在真 Excel 里是否还正常。这步**不写生产代码**，产出是一个 go/no-go 结论。

### Task 0: .xlsm round-trip 人工验证

**Files:**
- Create: `backend/scripts/nitori_xlsm_spike.py`（临时脚本，验证后可删）

- [ ] **Step 1: 写 spike 脚本**——copy2 GLOBAL → `load_workbook(keep_vba=True)` → 在 `Quotation (Global) Jul-Sep` 的 r114 写入 OCEAN FREIGHT 20F = 580、r116 40HC=1160 → save。

```python
import shutil
from pathlib import Path
from openpyxl import load_workbook

SRC = Path("资料/2026.05.26/_nitori_unzip/ニトリ様海上入札/_【to GLOBAL】2026年7月～9月_見積り書.xlsm")
OUT = Path("backend/uploads/nitori_spike_out.xlsm")
shutil.copy2(SRC, OUT)
wb = load_workbook(OUT, data_only=False, keep_vba=True)
ws = wb["Quotation (Global) Jul-Sep"]
ws.cell(114, 19).value = 580      # S列 OCEAN FREIGHT amount, 20F
ws.cell(116, 19).value = 1160     # 40HC
ws.cell(114, 18).value = "USD"    # R列 cur
wb.save(OUT)
print("saved", OUT)
```

- [ ] **Step 2: 跑脚本**

Run: `cd backend && ../.venv/bin/python scripts/nitori_xlsm_spike.py`
Expected: 打印 `saved ...`，无异常。

- [ ] **Step 3: 用真 Excel 打开 `nitori_spike_out.xlsm` 人工确认三件事**（需 Windows/Mac Excel；可发对方或本地）：
  1. 宏是否还在、能否启用运行（开发者→宏）；
  2. r114/r116 的运价是否正确显示、相关合计公式是否重算正确；
  3. 丢失的数据验证下拉是否影响"提交投标"（多为辅助下拉，通常不影响）。

- [ ] **Step 4: 记录结论**——在本计划末尾「Spike 结论」处填 PASS / 需换策略。
  - **PASS** → 继续 Phase 1（fill 用 openpyxl keep_vba=True）。
  - **FAIL（宏坏/公式错）** → 停下找人对齐：改用「只改目标 cell 的 zip-level XML 注入」或 xlwings 方案；后续 fill 任务需重写。

- [ ] **Step 5: 删除临时产物**

```bash
rm -f backend/uploads/nitori_spike_out.xlsm backend/scripts/nitori_xlsm_spike.py
```

---

## Phase 1 — NitoriCostBook：读成本 Excel

### Task 1: 成本表 FCL 行解析

**Files:**
- Create: `backend/app/services/step2_bidding/nitori_cost_book.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_cost_book.py`

数据结构（放 `nitori_cost_book.py` 顶部）：
```python
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook

@dataclass(slots=True)
class CostLane:
    pol: str            # 规整后大写，如 "SHANGHAI"
    pod_raw: str        # 成本表原文，如 "PORT KELANG (N or..."
    pod_norm: str       # 归一后，如 "PORT KLANG"
    carrier: str        # "EMC"
    rate_20gp: Decimal | None
    rate_40hc: Decimal | None
    lss: str            # "Included" 等原文
    transit_time: str   # "11 DAYS"
    no_service: bool    # True 表示该行 NO SERVICE
```

POD 归一函数（**关键归一逻辑**）：
```python
def normalize_pod(raw: str) -> str:
    s = (raw or "").strip().upper()
    s = s.replace("KELANG", "KLANG")          # 拼写统一
    # 去括号注解，留主名： "PORT KLANG (N or..." -> "PORT KLANG"
    s = s.split("(")[0].strip()
    return s
```

- [ ] **Step 1: 写失败测试**

```python
from decimal import Decimal
from pathlib import Path
import extract_msg
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook

NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
COST_MSG = NITORI_DIR / "②（Cost）回复 HHESHA内部　転送 ニトリ海上運賃入札（2026年2Q7－９月）.msg"

def _extract_cost(tmp_path):
    m = extract_msg.Message(str(COST_MSG))
    for a in m.attachments:
        name = a.longFilename or a.shortFilename or ""
        if name.lower().endswith(".xlsx"):
            p = tmp_path / name
            p.write_bytes(a.data)
            m.close()
            return p
    raise AssertionError("cost xlsx not found in msg")

def test_cost_book_parses_shanghai_lanes(tmp_path):
    cost_path = _extract_cost(tmp_path)
    book = NitoriCostBook.from_xlsx(cost_path)
    lane = book.lookup(pol="SHANGHAI", pod="PORT KLANG", carrier=None)
    assert lane is not None
    assert lane.rate_20gp == Decimal("580")
    assert lane.rate_40hc == Decimal("1160")
    assert lane.no_service is False

def test_cost_book_marks_taicang_klang_no_service(tmp_path):
    book = NitoriCostBook.from_xlsx(_extract_cost(tmp_path))
    lane = book.lookup(pol="TAICANG", pod="PORT KLANG", carrier=None)
    assert lane is not None and lane.no_service is True
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_nitori_cost_book.py -v`
Expected: FAIL `ModuleNotFoundError: nitori_cost_book` 或 `AttributeError: NitoriCostBook`。

- [ ] **Step 3: 实现 `NitoriCostBook`**

```python
class NitoriCostBook:
    def __init__(self, lanes: list[CostLane], origin_fees: dict, free_time: dict):
        self._lanes = lanes
        self.origin_fees = origin_fees      # {carrier: {"booking":250,"thc_20":630,...}}
        self.free_time = free_time          # {pod_norm: {"dem":28,"det":7}}
        self._index = {(l.pol, l.pod_norm): l for l in lanes}

    @classmethod
    def from_xlsx(cls, path: Path) -> "NitoriCostBook":
        wb = load_workbook(path, data_only=True)
        ws = wb["FCL"]
        lanes: list[CostLane] = []
        for r in range(2, ws.max_row + 1):
            pol = ws.cell(r, 1).value
            dest = ws.cell(r, 2).value
            carrier = ws.cell(r, 3).value
            if not pol or not dest:
                continue
            pol_s = str(pol).strip().upper()
            if pol_s not in ("SHANGHAI", "TAICANG"):
                continue                     # 越过 origin fee 文本块等非航线行
            no_service = (str(carrier).strip().upper() == "NO SERVICE")
            lanes.append(CostLane(
                pol=pol_s, pod_raw=str(dest), pod_norm=normalize_pod(str(dest)),
                carrier="" if no_service else str(carrier).strip(),
                rate_20gp=_dec(ws.cell(r, 4).value) if not no_service else None,
                rate_40hc=_dec(ws.cell(r, 5).value) if not no_service else None,
                lss=str(ws.cell(r, 8).value or ""), transit_time=str(ws.cell(r, 11).value or ""),
                no_service=no_service,
            ))
        free_time = cls._parse_free_time(wb)
        wb.close()
        return cls(lanes, origin_fees={}, free_time=free_time)

    def lookup(self, *, pol: str, pod: str, carrier: str | None = None) -> CostLane | None:
        return self._index.get((pol.strip().upper(), normalize_pod(pod)))

    @staticmethod
    def _parse_free_time(wb) -> dict:
        out = {}
        if "Sheet1" in wb.sheetnames:
            ws = wb["Sheet1"]
            for r in range(2, ws.max_row + 1):
                port = ws.cell(r, 1).value
                if not port:
                    continue
                out[normalize_pod(str(port))] = {
                    "dem": _first_int(ws.cell(r, 2).value),
                    "det": _first_int(ws.cell(r, 3).value),
                }
        return out
```

辅助：
```python
import re
def _dec(v):
    if v is None: return None
    try: return Decimal(str(v))
    except Exception: return None
def _first_int(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_nitori_cost_book.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step2_bidding/nitori_cost_book.py backend/tests/services/step2_bidding/test_nitori_cost_book.py
git commit -m "feat(step2): Nitori 成本表解析 NitoriCostBook（FCL+free time+POD归一）"
```

### Task 2: free time 查询

**Files:**
- Modify: `backend/app/services/step2_bidding/nitori_cost_book.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_cost_book.py`

- [ ] **Step 1: 追加失败测试**

```python
def test_cost_book_free_time(tmp_path):
    book = NitoriCostBook.from_xlsx(_extract_cost(tmp_path))
    ft = book.free_time_for("PORT KLANG")
    assert ft == {"dem": 28, "det": 7}
```

- [ ] **Step 2: 跑测试看失败** — Run: `pytest tests/services/step2_bidding/test_nitori_cost_book.py::test_cost_book_free_time -v` → FAIL `AttributeError: free_time_for`。

- [ ] **Step 3: 实现** —在 `NitoriCostBook` 加：
```python
    def free_time_for(self, pod: str) -> dict | None:
        return self.free_time.get(normalize_pod(pod))
```

- [ ] **Step 4: 跑测试看通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): NitoriCostBook free time 查询"`

---

## Phase 2 — NitoriProfile：识别 / 解析 / 匹配 / 回填

### Task 3: customer_identifier 识别 Nitori

**Files:**
- Modify: `backend/app/services/step2_bidding/customer_identifier.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_identifier.py`

识别规则（demo）：sheet 名里同时含 `お客様案内` 前缀 **且** 含以 `Quotation` 开头的 sheet → Nitori。新增常量：
```python
_NITORI = "nitori"
_NITORI_SHEET_PREFIX_QUOTE = "Quotation"
_NITORI_SHEET_PREFIX_GUIDE = "お客様案内"
```

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path
from app.services.step2_bidding.customer_identifier import identify
NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"

def test_identify_nitori_global():
    res = identify(QUOTE_GLOBAL)
    assert res.matched_customer == "nitori"
```

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL，返回 `unknown`（现逻辑只认 customer_a）。

- [ ] **Step 3: 实现**——在 `identify()` 组装结果**之前**插入 Nitori 判定（不破坏 customer_a 分支）：
```python
        has_quote = any(n.startswith(_NITORI_SHEET_PREFIX_QUOTE) for n in normalized_names)
        has_guide = any(n.startswith(_NITORI_SHEET_PREFIX_GUIDE) for n in normalized_names)
        if has_quote and has_guide:
            return IdentifierResult(
                matched_customer=_NITORI, matched_dimensions=("NITORI_SHEETS",),
                source="auto", confidence="high", unmatched_reason=None, warnings=(),
            )
```
放在「维度 B / 维度 D」扫描**之前**返回即可。

- [ ] **Step 4: 跑测试看通过** + 跑回归确认 customer_a 识别没坏：

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/test_nitori_identifier.py tests/services/step2_bidding/ -k "identif" -v`
Expected: 新用例 PASS，既有 identifier 用例全绿。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): customer_identifier 增加 Nitori 识别分支"`

### Task 4: NitoriProfile.detect + parse（报价表 → ParsedPkg）

**Files:**
- Create: `backend/app/services/step2_bidding/customer_profiles/nitori.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_profile.py`

常量区（业务可调）：
```python
from decimal import Decimal
_QUOTE_SHEET = "Quotation (Global) Jul-Sep"
_DATA_START_ROW = 9
_COL = dict(carrier=4, country_exp=5, pol=6, country_imp=7, pod=8, size=9,
            tt=17, of_cur=18, of_amt=19, lss_cur=20, lss_amt=21,
            thc_cur=26, thc_amt=27, doc_cur=28, doc_amt=29, dem_free=103, det_free=104)
_CHINA_POLS = {"SHANGHAI", "TAICANG"}
_SIZE_TO_COST = {"20F": "20gp", "40HC": "40hc", "40F": "40hc"}   # 40F←40HC（assumption）
_MARKUP = Decimal("1.15")
```

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path
from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"

def test_nitori_detect():
    assert NitoriProfile().detect(QUOTE_GLOBAL) is True

def test_nitori_parse_china_rows():
    parsed = NitoriProfile().parse(QUOTE_GLOBAL, bid_id="b1", period="2026Q2")
    china = [r for r in parsed.rows if r.origin_code in ("SHANGHAI", "TAICANG")]
    assert len(china) == 48
    r114 = next(r for r in parsed.rows if r.row_idx == 114)
    assert r114.origin_code == "SHANGHAI"
    assert r114.destination_code == "PORT KLANG"           # 已归一
    assert r114.extras["size"] == "20F"
    assert r114.extras["pod_raw"] == "PORT KLANG (NORTH)"
```

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL `ModuleNotFoundError`。

- [ ] **Step 3: 实现 detect + parse**

```python
from __future__ import annotations
import shutil
from pathlib import Path
from openpyxl import load_workbook
from app.services.step1_rates.writers.base import is_formula_cell, safe_set, stamp_document_properties
from app.services.step2_bidding.entities import ParsedPkg, PkgRow, PkgSection, PerRowReport, RowStatus, CostType
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook, normalize_pod

class NitoriProfile:
    customer_code = "nitori"
    display_name = "ニトリ (Nitori) TO GLOBAL"
    priority = 20

    def __init__(self, cost_book: NitoriCostBook | None = None, markup_ratio=_MARKUP):
        self._cost = cost_book
        self._markup = markup_ratio

    def detect(self, path: Path, hint: str | None = None) -> bool:
        if hint == self.customer_code:
            return True
        try:
            wb = load_workbook(path, data_only=True, read_only=True)
        except Exception:
            return False
        try:
            return _QUOTE_SHEET in wb.sheetnames
        finally:
            wb.close()

    def parse(self, path: Path, bid_id: str, period: str) -> ParsedPkg:
        wb = load_workbook(path, data_only=True)
        try:
            ws = wb[_QUOTE_SHEET]
            rows: list[PkgRow] = []
            for r in range(_DATA_START_ROW, ws.max_row + 1):
                pol = ws.cell(r, _COL["pol"]).value
                pod = ws.cell(r, _COL["pod"]).value
                size = ws.cell(r, _COL["size"]).value
                if not pol or not pod:
                    continue
                pol_s = str(pol).strip().upper()
                rows.append(PkgRow(
                    row_idx=r, section_index=0, section_code="GLOBAL",
                    origin_code=pol_s, origin_text_raw=str(pol),
                    destination_text_raw=str(pod), destination_code=normalize_pod(str(pod)),
                    cost_type=CostType.UNKNOWN, currency="USD",
                    volume_desc=None, existing_price=None, existing_lead_time=None,
                    existing_carrier=str(ws.cell(r, _COL["carrier"]).value or "") or None,
                    existing_remark=None, is_example=False, client_constraint_text=None,
                    extras={"size": str(size).strip() if size else "",
                            "pod_raw": str(pod), "is_china": pol_s in _CHINA_POLS},
                ))
            section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
            return ParsedPkg(bid_id=bid_id, customer_code=self.customer_code, period=period,
                             sheet_name=_QUOTE_SHEET, source_file=path.name,
                             sections=[section], rows=rows, warnings=[])
        finally:
            wb.close()
```

- [ ] **Step 4: 跑测试看通过** — Expected: PASS（detect + parse 共 2 用例）。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): NitoriProfile detect + parse 报价表航线"`

### Task 5: NitoriProfile.match（对成本表生成 PerRowReport）

**Files:**
- Modify: `backend/app/services/step2_bidding/customer_profiles/nitori.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_profile.py`

匹配规则：只处理 `is_china` 行；按 `(POL, POD归一, SIZE→cost字段)` 查 `NitoriCostBook`：
- 命中且有价 → `FILLED`，cost_price = 对应箱型价；sell_price = cost × markup。
- 命中但 `no_service` 或该箱型价为空 → `NO_RATE`。
- 非中国发行 → 不进 report（Demo 不投）。

- [ ] **Step 1: 写失败测试**

```python
from decimal import Decimal
import extract_msg
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook
COST_MSG = NITORI_DIR / "②（Cost）回复 HHESHA内部　転送 ニトリ海上運賃入札（2026年2Q7－９月）.msg"

def _cost_book(tmp_path):
    m = extract_msg.Message(str(COST_MSG))
    for a in m.attachments:
        n = a.longFilename or a.shortFilename or ""
        if n.lower().endswith(".xlsx"):
            p = tmp_path / n; p.write_bytes(a.data); m.close()
            return NitoriCostBook.from_xlsx(p)
    raise AssertionError("no cost xlsx")

def test_nitori_match_filled_and_norate(tmp_path):
    prof = NitoriProfile(cost_book=_cost_book(tmp_path))
    parsed = prof.parse(QUOTE_GLOBAL, bid_id="b1", period="2026Q2")
    reports = prof.match(parsed)
    by_row = {rp.row_idx: rp for rp in reports}
    # r114 SHANGHAI->PORT KLANG(NORTH) 20F 命中 580
    assert by_row[114].status.value == "filled"
    assert by_row[114].cost_price == Decimal("580")
    assert by_row[114].sell_price == Decimal("667")          # 580*1.15=667
    # r120 TAICANG->PORT KLANG 成本 NO SERVICE → no_rate
    assert by_row[120].status.value == "no_rate"
```

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL `AttributeError: match`。

- [ ] **Step 3: 实现 match**

```python
    def match(self, parsed: ParsedPkg) -> list[PerRowReport]:
        assert self._cost is not None, "NitoriProfile.match 需要 cost_book"
        reports: list[PerRowReport] = []
        for row in parsed.rows:
            if not row.extras.get("is_china"):
                continue
            lane = self._cost.lookup(pol=row.origin_code, pod=row.destination_code)
            cost_field = _SIZE_TO_COST.get(row.extras.get("size", ""))
            cost_price = None
            if lane and not lane.no_service and cost_field:
                cost_price = getattr(lane, f"rate_{cost_field}")
            if cost_price is None:
                reports.append(PerRowReport(
                    row_idx=row.row_idx, section_code="GLOBAL",
                    destination_code=row.destination_code, status=RowStatus.NO_RATE,
                    cost_price=None, sell_price=None, markup_ratio=None,
                    lead_time_text=None, carrier_text=None, remark_text=None,
                    selected_candidate=None))
                continue
            sell = (cost_price * self._markup).quantize(Decimal("1"))
            reports.append(PerRowReport(
                row_idx=row.row_idx, section_code="GLOBAL",
                destination_code=row.destination_code, status=RowStatus.FILLED,
                cost_price=cost_price, sell_price=sell, markup_ratio=self._markup,
                lead_time_text=lane.transit_time, carrier_text=lane.carrier,
                remark_text=None, selected_candidate=None))
        return reports
```

> 注：`sell` 用 `quantize(Decimal("1"))` 取整（580×1.15=667）。若业务要四舍五入到其它精度，改这里。

- [ ] **Step 4: 跑测试看通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): NitoriProfile.match 对成本表生成行报告"`

### Task 6: NitoriProfile.fill（回填 .xlsm，成本版/报价版）

**Files:**
- Modify: `backend/app/services/step2_bidding/customer_profiles/nitori.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_profile.py`

**关键：`keep_vba=True`**（与 customer_a 的 `keep_vba=False` 不同，否则丢宏）。

- [ ] **Step 1: 写失败测试**

```python
from openpyxl import load_workbook

def test_nitori_fill_cost_and_sr(tmp_path):
    prof = NitoriProfile(cost_book=_cost_book(tmp_path))
    parsed = prof.parse(QUOTE_GLOBAL, bid_id="b1", period="2026Q2")
    reports = prof.match(parsed)
    cost_out = tmp_path / "cost.xlsm"
    sr_out = tmp_path / "sr.xlsm"
    prof.fill(QUOTE_GLOBAL, parsed, reports, "cost", cost_out)
    prof.fill(QUOTE_GLOBAL, parsed, reports, "sr", sr_out)

    wbc = load_workbook(cost_out, keep_vba=True)["Quotation (Global) Jul-Sep"]
    wbs = load_workbook(sr_out, keep_vba=True)["Quotation (Global) Jul-Sep"]
    assert wbc.cell(114, 19).value == 580       # 成本版 OCEAN FREIGHT amount
    assert wbs.cell(114, 19).value == 667       # 报价版 = 580*1.15
    assert wbc.cell(114, 18).value == "USD"     # cur
    # no_rate 行不写运价
    assert wbc.cell(120, 19).value in (None, 0, "")
    # 宏保留
    import zipfile
    assert any("vbaProject" in n for n in zipfile.ZipFile(cost_out).namelist())
```

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL `AttributeError: fill`。

- [ ] **Step 3: 实现 fill**

```python
    def fill(self, source_path: Path, parsed: ParsedPkg,
             row_reports: list[PerRowReport], variant: str, output_path: Path):
        if variant not in ("cost", "sr"):
            raise ValueError(f"variant 必须 cost/sr，实际 {variant!r}")
        shutil.copy2(source_path, output_path)
        wb = load_workbook(output_path, data_only=False, keep_vba=True)   # 保宏
        try:
            ws = wb[_QUOTE_SHEET]
            row_by_idx = {r.row_idx: r for r in parsed.rows}
            for rep in row_reports:
                if rep.status != RowStatus.FILLED:
                    continue
                price = rep.cost_price if variant == "cost" else rep.sell_price
                self._set(ws, rep.row_idx, "of_cur", "USD")
                self._set(ws, rep.row_idx, "of_amt", float(price))
                self._set(ws, rep.row_idx, "lss_cur", "USD")
                self._set(ws, rep.row_idx, "lss_amt", 0)          # Included→0（assumption）
                if rep.lead_time_text:
                    self._set(ws, rep.row_idx, "tt", rep.lead_time_text)
                ft = self._cost.free_time_for(rep.destination_code) if self._cost else None
                if ft:
                    self._set(ws, rep.row_idx, "dem_free", ft.get("dem"))
                    self._set(ws, rep.row_idx, "det_free", ft.get("det"))
            stamp_document_properties(wb, batch_id=f"{parsed.bid_id}:nitori:{variant}")
            wb.save(output_path)
        finally:
            wb.close()

    @staticmethod
    def _set(ws, row_idx: int, col_key: str, value):
        if value is None:
            return
        cell = ws.cell(row_idx, _COL[col_key])
        if is_formula_cell(cell):
            return
        safe_set(cell, value)
```

> THC/DOC 列（待业务确认 origin fee 落法）本期先不写——`origin_fees` 解析留待 Task 9 扩展，避免在未确认列上落错值。

- [ ] **Step 4: 跑测试看通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): NitoriProfile.fill 回填运价(成本/报价版, keep_vba 保宏)"`

---

## Phase 3 — 接入编排器 + 端到端

### Task 7: nitori_bundle 定位 quote + cost

**Files:**
- Create: `backend/app/services/step2_bidding/nitori_bundle.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_integration.py`

职责：给一个目录（已解压的投标包），返回 `(quote_global_path, cost_path)`。cost 若是 .msg 附件则抽出到该目录。

- [ ] **Step 1: 写失败测试**

```python
import shutil
from pathlib import Path
from app.services.step2_bidding.nitori_bundle import resolve_bundle
NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"

def test_resolve_bundle(tmp_path):
    work = tmp_path / "pkg"; shutil.copytree(NITORI_DIR, work)
    quote, cost = resolve_bundle(work)
    assert "GLOBAL" in quote.name
    assert cost.suffix == ".xlsx" and cost.exists()
```

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL `ModuleNotFoundError`。

- [ ] **Step 3: 实现**

```python
from __future__ import annotations
from pathlib import Path
import extract_msg

def resolve_bundle(folder: Path) -> tuple[Path, Path]:
    quote = next(p for p in folder.glob("*GLOBAL*.xlsm"))
    # 先找散落 cost.xlsx
    loose = [p for p in folder.glob("*.xlsx") if "nitori" in p.name.lower() or "cost" in p.name.lower()]
    if loose:
        return quote, loose[0]
    # 否则从任意 .msg 抽含 FCL sheet 的 xlsx
    for msg in folder.glob("*.msg"):
        m = extract_msg.Message(str(msg))
        for a in m.attachments:
            name = a.longFilename or a.shortFilename or ""
            if name.lower().endswith(".xlsx"):
                out = folder / name
                out.write_bytes(a.data)
                m.close()
                return quote, out
        m.close()
    raise FileNotFoundError("cost xlsx not found in bundle")
```

- [ ] **Step 4: 跑测试看通过** — Expected: PASS。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): nitori_bundle 定位 quote 与 cost(含 .msg 抽取)"`

### Task 8: orchestrator 增加 Nitori 分支

**Files:**
- Modify: `backend/app/services/step2_bidding/bidding_orchestrator.py`
- Test: `backend/tests/services/step2_bidding/test_nitori_integration.py`

在 `run_auto_fill` 中，`identify` 后、构造 `CustomerAProfile` 前插入：
```python
    if identify_result.matched_customer == "nitori":
        return _run_nitori(input_path, bid_id, bid_dir, identify_block)
```
新增 `_run_nitori`（customer_a 路径**完全不动**）：parse → match → fill×2 → token。

- [ ] **Step 1: 写失败端到端测试**

```python
from app.services.step2_bidding.bidding_orchestrator import run_auto_fill

def test_nitori_end_to_end(tmp_path, db_session):     # db_session: 现有 conftest fixture
    import shutil
    work = tmp_path / "pkg"; shutil.copytree(NITORI_DIR, work)
    quote = next(work.glob("*GLOBAL*.xlsm"))
    resp = run_auto_fill(quote, bid_id="bidN", bid_dir=work, db=db_session)
    assert resp.ok is True
    assert resp.identify.matched_customer == "nitori"
    assert resp.fill.filled_count > 0
    assert resp.download.cost_token and resp.download.sr_token
```

> 若 `db_session` fixture 不存在，用 `None`——Nitori 分支不碰 DB。先确认现有 step2 测试如何拿 db。

- [ ] **Step 2: 跑测试看失败** — Expected: FAIL（现在 Nitori 走 customer_a 解析会 F3/F2 报错）。

- [ ] **Step 3: 实现 `_run_nitori`**

```python
def _run_nitori(input_path, bid_id, bid_dir, identify_block):
    from app.services.step2_bidding.nitori_bundle import resolve_bundle
    from app.services.step2_bidding.nitori_cost_book import NitoriCostBook
    from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
    quote_path, cost_path = resolve_bundle(Path(bid_dir))
    profile = NitoriProfile(cost_book=NitoriCostBook.from_xlsx(cost_path))
    parsed = profile.parse(quote_path, bid_id=bid_id, period="2026Q2")
    parse_block = _to_parse_block(parsed, sample_limit=5)
    reports = profile.match(parsed)
    cost_out = Path(bid_dir) / f"cost_nitori_{bid_id}.xlsm"
    sr_out = Path(bid_dir) / f"sr_nitori_{bid_id}.xlsm"
    profile.fill(quote_path, parsed, reports, "cost", cost_out)
    profile.fill(quote_path, parsed, reports, "sr", sr_out)
    fill_block = _to_fill_block(row_reports=reports,
                                fr_warnings=list(parsed.warnings), markup_ratio=_MARKUP_RATIO)
    cost_token = TOKEN_STORE.put(cost_out, cost_out.name, ttl=_TOKEN_TTL_SECONDS)
    sr_token = TOKEN_STORE.put(sr_out, sr_out.name, ttl=_TOKEN_TTL_SECONDS)
    expires_at = datetime.utcnow() + timedelta(seconds=_TOKEN_TTL_SECONDS)
    return BiddingAutoFillResponse(
        bid_id=bid_id, ok=True, error=None, identify=identify_block, parse=parse_block,
        fill=fill_block,
        download=DownloadTokens(cost_token=cost_token, sr_token=sr_token,
            cost_filename=cost_out.name, sr_filename=sr_out.name,
            expires_at=expires_at, one_time_use=True))
```

- [ ] **Step 4: 跑测试看通过** + 跑全 step2 回归：

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step2_bidding/ -v`
Expected: 新端到端 PASS；customer_a 既有用例全绿。

- [ ] **Step 5: 提交** — `git commit -m "feat(step2): orchestrator 增加 Nitori 分支 _run_nitori（customer_a 不变）"`

### Task 9: 全量回归 + 文档

- [ ] **Step 1: 全后端回归** — Run: `cd backend && ../.venv/bin/python -m pytest -q`，Expected: 仅遗留的 `test_ai_client.py`（PIL/vLLM 环境）失败，其余全绿。
- [ ] **Step 2: 在 `CLAUDE.md` 的 step2 段补一行**：`customer_profiles/` 已实装 customer_a + **nitori（TO GLOBAL demo，成本来自 bid 附带 Excel，不走 Step1）**。
- [ ] **Step 3: 提交** — `git commit -m "docs(step2): 记录 nitori profile 已实装(demo 级)"`

---

## 非本期范围（明确不做，避免范围蔓延）

- JAPAN（2475 行）/ TAIWAN 两张表
- Booking/EIR/Manifest/BAF/CAF 等 origin/附加费的精确落列（待业务确认列位后做 Task 9+ 扩展）
- Step1 运价库 → Step2 的成本接管（"两步打通"，未来）
- 前端 `PkgAutoFill` 对 .xlsm / Nitori 的 UI 适配（如需，另起前端任务）
- 数据验证下拉的保全（openpyxl 限制，Demo 接受）

## Spike 结论（Task 0 完成后填写）

- [ ] openpyxl `keep_vba=True` 回填后宏可运行：______
- [ ] 运价/公式在真 Excel 显示正确：______
- [ ] 丢失的下拉不影响投标提交：______
- [ ] 结论：PASS（继续）／ FAIL（需换 fill 策略，后续 Task 6/8 重写）
