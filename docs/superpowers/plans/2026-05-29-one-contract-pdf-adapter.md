# ONE 服务合约 PDF 运价适配器 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 pdfplumber 解析 ONE 服务合约 PDF 的 FCL 运价 + 元数据 + 附加费清单文本，经现有"做表"链路入库 FreightRate；不依赖 vLLM。

**Architecture:** 新增纯函数状态机 `parse_rate_blocks`(消费"按 y 分行、按 x 排序的词列表")+ 薄 pdfplumber 提取层 `parse_one_contract_pdf`；经 `detect_and_parse_pdf` 分流、orchestrator `.pdf` 分支接入 sea 进料口；`_normalize_sea` 与 `commit_ocean_rows` 纯追加几个字段透传，复用已修的双语 `_resolve_port`。不改表结构。

**Tech Stack:** Python 3.10, pdfplumber, FastAPI/SQLAlchemy(既有), pytest。

设计依据：`docs/superpowers/specs/2026-05-29-one-contract-pdf-adapter-design.md`

---

## 文件结构

| 文件 | 职责 | 动作 |
| --- | --- | --- |
| `backend/requirements.txt` | 依赖 | Modify：+pdfplumber |
| `backend/app/services/step1_rates/adapters/one_contract_pdf.py` | ONE 合约解析（港名清洗 + 状态机 + pdfplumber 提取层） | Create |
| `backend/app/services/rate_parser_pdf.py` | PDF 格式分流 `detect_and_parse_pdf`（与 Excel 的 rate_parser.py 平行） | Create |
| `backend/app/services/step1_rates/sheet_builder/orchestrator.py` | `add_file` 加 `.pdf` 分支；`_normalize_sea` 追加字段透传 | Modify |
| `backend/app/services/step1_rates/sheet_builder/db_writer.py` | `commit_ocean_rows` 追加写 valid_from/container_45/rate_level/service_code/via/is_direct/rmks | Modify |
| `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py` | 港名清洗 + 状态机单元测试 | Create |
| `backend/tests/services/step1_rates/test_rate_parser_pdf.py` | 分流单元测试 | Create |
| `backend/tests/sheet_builder/test_orchestrator.py` | `_normalize_sea` 透传 + `.pdf` 分支 | Modify |
| `backend/tests/sheet_builder/test_ocean_writer.py` | `commit_ocean_rows` 新字段落库 | Modify |

**约定的数据契约**（贯穿全计划）：

- **word**：`dict` 含键 `"text"`(str)、`"x0"`(float)。
- **line**：`list[word]`，按 `x0` 升序。
- **parsed_row**（解析器产出 / orchestrator 消费）键：`carrier_name`、`origin_port_name`、`destination_port_name`、`container_20gp`、`container_40gp`、`container_40hq`、`container_45`、`currency`、`valid_from`(ISO 字符串 `"YYYY-MM-DD"` 或 None)、`valid_to`、`rate_level`、`service_code`、`via`、`is_direct`(bool)、`commodity`、`remark`、`needs_review`(bool)。

所有命令在 `backend/` 目录下执行；测试用 `../.venv/bin/python -m pytest`。

---

## Task 1: 加入 pdfplumber 依赖

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 加依赖行**

在 `backend/requirements.txt` 末尾 `Pillow>=10.0.0` 之后追加：

```
pdfplumber>=0.11.0   # 解析船司服务合约 PDF(文字版);纯 Python,无系统二进制依赖
```

- [ ] **Step 2: 安装并验证导入**

Run:
```bash
../.venv/bin/python -m pip install "pdfplumber>=0.11.0"
../.venv/bin/python -c "import pdfplumber; print('pdfplumber', pdfplumber.__version__)"
```
Expected: 打印出 `pdfplumber 0.11.x`，无报错。

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "build(step1): 加入 pdfplumber 依赖(解析 ONE 服务合约 PDF)"
```

---

## Task 2: 港名清洗 `_clean_port_name`

**Files:**
- Create: `backend/app/services/step1_rates/adapters/one_contract_pdf.py`
- Test: `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`：

```python
"""ONE 服务合约 PDF 适配器单元测试。"""
from app.services.step1_rates.adapters.one_contract_pdf import _clean_port_name


def test_clean_port_name_strips_state_suffix():
    assert _clean_port_name("HONOLULU, HI") == "HONOLULU"


def test_clean_port_name_strips_country_and_parens():
    assert _clean_port_name("DALIAN, LIAONING, CHINA(CY)") == "DALIAN"
    assert _clean_port_name("TAIPEI, TAIWAN(CY)") == "TAIPEI"


def test_clean_port_name_plain_passthrough():
    assert _clean_port_name("BUSAN") == "BUSAN"
    assert _clean_port_name("") == ""
    assert _clean_port_name(None) == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py -v`
Expected: FAIL — `ModuleNotFoundError: ... one_contract_pdf`（模块还没建）。

- [ ] **Step 3: 写最小实现**

创建 `backend/app/services/step1_rates/adapters/one_contract_pdf.py`：

```python
"""ONE(Ocean Network Express) 服务合约 PDF 运价解析。

文字版 PDF（pdftotext/pdfplumber 可抽），第 6 节 "CONTRACT RATES OR RATE SCHEDULE(S)"
按 COMMODITY 块组织：每块有 ORIGIN、目的港运价表(20'/40'/40HC/45')、NOTE(生效日 + 附加费清单)。
本模块只懂 ONE 这一种版式；纯解析，不依赖 vLLM。
"""
from __future__ import annotations

import re
from typing import Any

_CARRIER = "ONE"


def _clean_port_name(raw: Any) -> str:
    """港名清洗：去括号注解(如 "(CY)")、取逗号前主名 → 供 _resolve_port 匹配。"""
    if not raw:
        return ""
    s = re.sub(r"\(.*?\)", "", str(raw))   # 去 (CY)/(via …) 等括号注解
    s = s.split(",")[0]                     # "HONOLULU, HI" → "HONOLULU"
    return s.strip()
```

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py -v`
Expected: PASS（3 个测试全过）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/adapters/one_contract_pdf.py backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py
git commit -m "feat(step1): one_contract_pdf 港名清洗 _clean_port_name"
```

---

## Task 3: 状态机 `parse_rate_blocks` — 干净运价块

**Files:**
- Modify: `backend/app/services/step1_rates/adapters/one_contract_pdf.py`
- Test: `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`

- [ ] **Step 1: 写失败测试**

向 `test_one_contract_pdf.py` 追加（顶部 import 改为同时导入 `parse_rate_blocks`）：

```python
from app.services.step1_rates.adapters.one_contract_pdf import (
    _clean_port_name,
    parse_rate_blocks,
)


def _line(*pairs):
    """构造一行：pairs 为 (text, x0) 序列。"""
    return [{"text": t, "x0": float(x)} for t, x in pairs]


def _clean_block_lines():
    # 列坐标：Destination=10, Cntry=200, Term=350, Type=400, Cur=450,
    #         20'=500, 40'=560, 40HC=620, 45'=680, Note=740
    return [
        _line(("6.", 5), ("CONTRACT", 30), ("RATES", 120), ("OR", 200), ("RATE", 240), ("SCHEDULE(S)", 300)),
        _line(("211)", 5), ("COMMODITY", 40), (":", 150), ("TPE1-FAK", 170)),
        _line(("ORIGIN", 5), (":", 150), ("DALIAN,", 170), ("LIAONING,", 230), ("CHINA(CY)", 300)),
        _line(("Destination", 10), ("Cntry", 200), ("Term", 350), ("Type", 400),
              ("Cur", 450), ("20'", 500), ("40'", 560), ("40HC", 620), ("45'", 680), ("Note", 740)),
        _line(("HILO,", 10), ("HI", 60), ("US", 200), ("CY", 350), ("Dry", 400),
              ("USD", 450), ("5240", 500), ("7100", 560), ("7200", 620)),
        _line(("HONOLULU,", 10), ("HI", 90), ("US", 200), ("CY", 350), ("Dry", 400),
              ("USD", 450), ("3840", 500), ("4800", 560), ("4800", 620), ("6075", 680)),
        _line(("<", 5), ("NOTE", 20), ("FOR", 60), ("COMMODITY", 100), (">", 200)),
        _line(("Rates", 10), ("are", 50), ("valid", 80), ("from", 120), ("20260203", 160), ("to", 230), ("20260228", 260)),
        _line(("Rates", 10), ("are", 50), ("inclusive", 80), ("of", 140), ("the", 160),
              ("ADEN", 190), ("GULF", 230), ("SURCHARGE(AGS)", 280)),
    ]


def test_parse_clean_block_yields_rows_with_prices():
    rows = parse_rate_blocks(_clean_block_lines())
    assert len(rows) == 2

    r0 = rows[0]
    assert r0["carrier_name"] == "ONE"
    assert r0["origin_port_name"] == "DALIAN"            # 已清洗
    assert r0["destination_port_name"] == "HILO"         # "HILO, HI" → "HILO"
    assert r0["container_20gp"] == 5240.0
    assert r0["container_40gp"] == 7100.0
    assert r0["container_40hq"] == 7200.0
    assert r0["container_45"] is None
    assert r0["currency"] == "USD"
    assert r0["needs_review"] is False
    # NOTE 回填
    assert r0["valid_from"] == "2026-02-03"
    assert r0["valid_to"] == "2026-02-28"
    assert "inclusive of" in (r0["remark"] or "")
    assert r0["commodity"] == "TPE1-FAK"

    assert rows[1]["destination_port_name"] == "HONOLULU"
    assert rows[1]["container_45"] == 6075.0
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py::test_parse_clean_block_yields_rows_with_prices -v`
Expected: FAIL — `ImportError: cannot import name 'parse_rate_blocks'`。

- [ ] **Step 3: 写最小实现**

向 `one_contract_pdf.py` 追加（在 `_clean_port_name` 之后）：

```python
_TOL = 25.0  # 列对齐容差(pt)
_PRICE_HEADERS = [
    ("container_20gp", "20'"),
    ("container_40gp", "40'"),
    ("container_40hq", "40HC"),
    ("container_45", "45'"),
]


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _after_colon(text: str) -> str:
    return text.split(":", 1)[1].strip() if ":" in text else text.strip()


def _is_number(s: str) -> bool:
    return bool(re.fullmatch(r"\d{2,7}", s.replace(",", "")))


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _word_at(line: list[dict], x: float, tol: float = _TOL) -> dict | None:
    """返回 x0 最接近 x 且在容差内的词；无则 None。"""
    best, best_d = None, tol
    for w in line:
        d = abs(w["x0"] - x)
        if d <= best_d:
            best, best_d = w, d
    return best


def _parse_header(line: list[dict]) -> tuple[dict, float | None]:
    """从列头行取各价列 x0 + 目的港右边界(第一个 Cntry 的 x0)。"""
    cols: dict[str, float] = {}
    for w in line:
        for key, label in _PRICE_HEADERS:
            if w["text"] == label:
                cols[key] = w["x0"]
    dest_right = next((w["x0"] for w in line if w["text"] == "Cntry"), None)
    return cols, dest_right


def _parse_note(note_lines: list[str]) -> tuple[str | None, str | None, str | None]:
    text = " ".join(note_lines)
    vf = vt = None
    m = re.search(r"valid from (\d{8}) to (\d{8})", text, re.I)
    if m:
        vf, vt = _iso(m.group(1)), _iso(m.group(2))
    else:
        m_to = re.search(r"valid to (\d{8})", text, re.I)
        m_from = re.search(r"valid from (\d{8})", text, re.I)
        vt = _iso(m_to.group(1)) if m_to else None
        vf = _iso(m_from.group(1)) if m_from else None
    sn = None
    m_inc = re.search(r"(inclusive of .+?)(?:Rates are subject|$)", text, re.I)
    if m_inc:
        sn = m_inc.group(1).strip()
    return vf, vt, sn


def _parse_data_row(line: list[dict], price_cols: dict, dest_right: float | None, ctx: dict) -> dict | None:
    if not dest_right:
        return None
    dest_raw = " ".join(w["text"] for w in line if w["x0"] < dest_right - _TOL).strip()
    destination = _clean_port_name(dest_raw)
    if not destination:
        return None
    row: dict[str, Any] = {
        "carrier_name": _CARRIER,
        "origin_port_name": ctx.get("origin"),
        "destination_port_name": destination,
        "container_20gp": None, "container_40gp": None,
        "container_40hq": None, "container_45": None,
        "currency": "USD",
        "valid_from": None, "valid_to": None,
        "rate_level": None,
        "service_code": ctx.get("service_code"),
        "via": None, "is_direct": True,
        "commodity": ctx.get("commodity"),
        "remark": None,
        "needs_review": False,
    }
    has_price = False
    for key, x in price_cols.items():
        w = _word_at(line, x)
        if w is None:
            continue
        if _is_number(w["text"]):
            row[key] = _to_float(w["text"])
            has_price = True
        else:
            row["rate_level"] = w["text"]      # 编码格子(如 R5/2400)
            row["needs_review"] = True
    if not has_price and not row["needs_review"]:
        return None                            # 既无价也无编码 → 非数据行
    if not has_price:
        row["needs_review"] = True
    return row


def parse_rate_blocks(lines: list[list[dict]]) -> list[dict]:
    """状态机：扫 COMMODITY 块 → 产 parsed_rows。纯函数，不读 PDF。"""
    results: list[dict] = []
    ctx: dict[str, Any] = {}
    block_rows: list[dict] = []
    note_buf: list[str] = []
    price_cols: dict[str, float] = {}
    dest_right: float | None = None
    in_section = False
    in_note = False

    def flush_block() -> None:
        nonlocal block_rows, note_buf
        if note_buf:
            vf, vt, sn = _parse_note(note_buf)
            for r in block_rows:
                r["valid_from"], r["valid_to"] = vf, vt
                if sn:
                    r["remark"] = sn
        results.extend(block_rows)
        block_rows, note_buf = [], []

    for line in lines:
        text = _line_text(line).strip()
        if not text:
            continue
        if "CONTRACT RATES OR RATE SCHEDULE" in text.upper():
            in_section = True
            continue
        if not in_section:
            continue
        if "NOTE FOR COMMODITY" in text.upper():
            in_note = True
            note_buf = []
            continue
        is_commodity = bool(re.match(r"^\d+\)\s*COMMODITY", text))
        if in_note and not is_commodity:
            note_buf.append(text)
            continue
        if is_commodity:
            in_note = False
            flush_block()
            ctx = {"commodity": _after_colon(text) or None, "origin": None, "service_code": None}
            price_cols, dest_right = {}, None
            continue
        if text.upper().startswith("ORIGIN VIA"):
            continue
        if text.upper().startswith("ORIGIN"):
            ctx["origin"] = _clean_port_name(_after_colon(text))
            continue
        if "Destination" in text and "Cntry" in text and "Cur" in text:
            price_cols, dest_right = _parse_header(line)
            continue
        if price_cols:
            row = _parse_data_row(line, price_cols, dest_right, ctx)
            if row:
                block_rows.append(row)
    flush_block()
    return results
```

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py -v`
Expected: PASS（含新测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/adapters/one_contract_pdf.py backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py
git commit -m "feat(step1): one_contract_pdf 状态机解析干净运价块(含NOTE生效日+附加费清单)"
```

---

## Task 4: 状态机 — 编码/RF 脏行标 needs_review

**Files:**
- Test: `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`
（实现已在 Task 3 的 `_parse_data_row` 覆盖编码格子分支；本任务用测试锁定行为，必要时微调。）

- [ ] **Step 1: 写失败测试**

向 `test_one_contract_pdf.py` 追加：

```python
def _coded_block_lines():
    return [
        _line(("6.", 5), ("CONTRACT", 30), ("RATES", 120), ("OR", 200), ("RATE", 240), ("SCHEDULE(S)", 300)),
        _line(("212)", 5), ("COMMODITY", 40), (":", 150), ("TPE1-FAK", 170)),
        _line(("ORIGIN", 5), (":", 150), ("TAIPEI,", 170), ("TAIWAN(CY)", 240)),
        _line(("Destination", 10), ("Cntry", 200), ("Term", 350), ("Type", 400),
              ("Cur", 450), ("20'", 500), ("40'", 560), ("40HC", 620), ("45'", 680), ("Note", 740)),
        # 冷藏 RF + 编码价 R2/2400(落在 40' 列)
        _line(("USLAX", 10), ("USLGB", 70), ("US", 200), ("CY", 350), ("RF", 400),
              ("USD", 450), ("R2/2400", 560)),
    ]


def test_parse_coded_row_flagged_needs_review():
    rows = parse_rate_blocks(_coded_block_lines())
    assert len(rows) == 1
    r = rows[0]
    assert r["needs_review"] is True
    assert r["rate_level"] == "R2/2400"      # 编码原文保留
    assert r["container_40gp"] is None        # 非数字 → 不当价
    assert r["origin_port_name"] == "TAIPEI"
```

- [ ] **Step 2: 运行确认（先看是否已通过）**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py::test_parse_coded_row_flagged_needs_review -v`
Expected：大概率直接 PASS（Task 3 已实现编码分支）。**若 FAIL**，按报错微调 `_parse_data_row` 的编码格子分支直到 PASS（如调整 `_is_number` 或 `_word_at` 容差），不要改测试期望。

- [ ] **Step 3: 全量该文件回归**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py -v`
Expected: PASS（干净块 + 编码块 + 港名清洗共 5+ 测试）。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py backend/app/services/step1_rates/adapters/one_contract_pdf.py
git commit -m "test(step1): one_contract_pdf 编码/RF 脏行标 needs_review 回归锁定"
```

---

## Task 5: pdfplumber 提取层 + `parse_one_contract_pdf` 包装

**Files:**
- Modify: `backend/app/services/step1_rates/adapters/one_contract_pdf.py`
- Test: `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`

- [ ] **Step 1: 写失败测试**（用 monkeypatch 替掉真实 PDF 读取）

向 `test_one_contract_pdf.py` 追加：

```python
import app.services.step1_rates.adapters.one_contract_pdf as ocp


def test_parse_one_contract_pdf_wraps_blocks(monkeypatch):
    monkeypatch.setattr(ocp, "_extract_word_lines", lambda path: _clean_block_lines())
    out = ocp.parse_one_contract_pdf("/fake/path.pdf", db=None)
    assert out["carrier_code"] == "ONE"
    assert len(out["parsed_rows"]) == 2
    assert out["parsed_rows"][0]["destination_port_name"] == "HILO"
    assert isinstance(out.get("warnings"), list)
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py::test_parse_one_contract_pdf_wraps_blocks -v`
Expected: FAIL — `AttributeError: ... has no attribute '_extract_word_lines'` 或 `parse_one_contract_pdf`。

- [ ] **Step 3: 写最小实现**

向 `one_contract_pdf.py` 追加：

```python
import pdfplumber
from sqlalchemy.orm import Session


def _extract_word_lines(file_path: str) -> list[list[dict]]:
    """pdfplumber 抽词 → 按页、按行(top 聚类)分组，每行按 x0 升序。"""
    lines: list[list[dict]] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            buckets: dict[int, list[dict]] = {}
            for w in words:
                key = round(float(w["top"]) / 3.0)   # 3pt 容差聚成一行
                buckets.setdefault(key, []).append({"text": w["text"], "x0": float(w["x0"])})
            for key in sorted(buckets):
                lines.append(sorted(buckets[key], key=lambda d: d["x0"]))
    return lines


def parse_one_contract_pdf(file_path: str, db: "Session | None" = None) -> dict:
    """ONE 合约 PDF → parsed_rows(kmtc 兼容形态)。db 仅为签名一致,本层不解析港口。"""
    lines = _extract_word_lines(file_path)
    rows = parse_rate_blocks(lines)
    warnings: list[str] = []
    if not rows:
        warnings.append("未在该 PDF 中识别到 ONE 合约运价表")
    return {"parsed_rows": rows, "carrier_code": _CARRIER, "warnings": warnings}
```

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/adapters/test_one_contract_pdf.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/adapters/one_contract_pdf.py backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py
git commit -m "feat(step1): one_contract_pdf pdfplumber 提取层 + parse_one_contract_pdf 包装"
```

---

## Task 6: PDF 分流 `detect_and_parse_pdf`

**Files:**
- Create: `backend/app/services/rate_parser_pdf.py`
- Test: `backend/tests/services/step1_rates/test_rate_parser_pdf.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/services/step1_rates/test_rate_parser_pdf.py`：

```python
"""PDF 格式分流测试。"""
import app.services.rate_parser_pdf as rpp


def test_dispatch_one_contract(monkeypatch):
    # 首页文本含 ONE 合约签名 → 路由到 parse_one_contract_pdf
    monkeypatch.setattr(rpp, "_first_page_text", lambda path: "ONE SERVICE CONTRACT NO. LAX0751N25")
    monkeypatch.setattr(rpp, "parse_one_contract_pdf",
                        lambda path, db: {"parsed_rows": [{"x": 1}], "carrier_code": "ONE", "warnings": []})
    out = rpp.detect_and_parse_pdf("/fake.pdf", db=None)
    assert out["carrier_code"] == "ONE"
    assert out["parsed_rows"] == [{"x": 1}]


def test_dispatch_unknown_returns_error(monkeypatch):
    monkeypatch.setattr(rpp, "_first_page_text", lambda path: "SOME UNRELATED INVOICE")
    out = rpp.detect_and_parse_pdf("/fake.pdf", db=None)
    assert "error" in out
    assert out.get("parsed_rows", []) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/test_rate_parser_pdf.py -v`
Expected: FAIL — `ModuleNotFoundError: ... rate_parser_pdf`。

- [ ] **Step 3: 写最小实现**

创建 `backend/app/services/rate_parser_pdf.py`：

```python
"""PDF 运价文件格式分流（与 Excel 的 rate_parser.detect_and_parse 平行）。

现仅识别 ONE 服务合约；别家船司合约 PDF 各自加签名分支。
"""
from __future__ import annotations

import pdfplumber
from sqlalchemy.orm import Session

from app.services.step1_rates.adapters.one_contract_pdf import parse_one_contract_pdf


def _first_page_text(file_path: str) -> str:
    with pdfplumber.open(file_path) as pdf:
        if not pdf.pages:
            return ""
        return (pdf.pages[0].extract_text() or "")


def detect_and_parse_pdf(file_path: str, db: "Session | None" = None) -> dict:
    head = _first_page_text(file_path).upper()
    if "SERVICE CONTRACT" in head and ("ONE" in head or "OCEAN NETWORK EXPRESS" in head):
        return parse_one_contract_pdf(file_path, db)
    return {"error": "无法识别的 PDF 运价格式（当前仅支持 ONE 服务合约）", "parsed_rows": []}
```

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step1_rates/test_rate_parser_pdf.py -v`
Expected: PASS（2 个测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rate_parser_pdf.py backend/tests/services/step1_rates/test_rate_parser_pdf.py
git commit -m "feat(step1): rate_parser_pdf.detect_and_parse_pdf 分流(现仅 ONE 合约)"
```

---

## Task 7: orchestrator `.pdf` 进料分支（仅 sea）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`
- Test: `backend/tests/sheet_builder/test_orchestrator.py`

- [ ] **Step 1: 写失败测试**

向 `backend/tests/sheet_builder/test_orchestrator.py` 追加（若文件无相关 import，按其现有风格补 `from app.services.step1_rates.sheet_builder import orchestrator` 与 `import app.services.rate_parser_pdf`）：

```python
def test_add_pdf_file_routes_to_pdf_parser(tmp_path, monkeypatch):
    import app.services.rate_parser_pdf as rpp
    from app.services.step1_rates.sheet_builder import orchestrator

    # 假 PDF（内容无所谓，分流被 monkeypatch）
    fake = tmp_path / "ONE_contract.pdf"
    fake.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        rpp, "detect_and_parse_pdf",
        lambda path, db: {"parsed_rows": [{
            "carrier_name": "ONE", "origin_port_name": "DALIAN",
            "destination_port_name": "HILO", "container_20gp": 5240.0,
            "container_40gp": 7100.0, "container_40hq": 7200.0,
        }], "carrier_code": "ONE", "warnings": []},
    )

    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "ONE_contract.pdf", str(fake), db=None)

    assert res.status == "parsed"
    assert res.row_count == 1
    rows = orchestrator.get_session(sess.session_id).rows
    assert rows[0]["destination"] == "HILO"            # _normalize_sea 已映射
    assert rows[0]["container_20gp"] == 5240.0
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py::test_add_pdf_file_routes_to_pdf_parser -v`
Expected: FAIL —— `.pdf` 当前不在受理扩展名内，`res.status == "skipped"`（消息含"暂不支持"）。

- [ ] **Step 3: 写实现**

在 `orchestrator.py`：

(a) 顶部扩展名常量旁新增（在 `_TEXT_EXTS = {...}` 之后）：

```python
_PDF_EXTS = {".pdf"}
```

(b) `add_file` 里把受理判断与解析分支改为含 PDF。将原：

```python
    if ext not in _EXCEL_EXTS and ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS:
```
改为：
```python
    if ext not in _EXCEL_EXTS and ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS and ext not in _PDF_EXTS:
```

(c) 在 `if ext in _EXCEL_EXTS:` 那段的解析分支里，新增 PDF 分支（放在 `elif ext in _IMAGE_EXTS:` 之前）：

```python
        elif ext in _PDF_EXTS:
            from app.services.rate_parser_pdf import detect_and_parse_pdf
            parsed = detect_and_parse_pdf(file_path, db)
            source_type = "pdf"
```

> 说明：sea 模板下 PDF 走 ONE 合约解析；air 模板上传 PDF 时，`detect_and_parse_pdf` 返回的行会经 `_normalize_air` 但无 tier/day 字段，预览为空——本轮不支持 air PDF，符合设计。无需额外分支。

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -v`
Expected: PASS（含新测试，且原有 orchestrator 测试不破）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): orchestrator 受理 .pdf 进料(sea→ONE 合约解析)"
```

---

## Task 8: `_normalize_sea` 追加字段透传

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`
- Test: `backend/tests/sheet_builder/test_orchestrator.py`

- [ ] **Step 1: 写失败测试**

向 `test_orchestrator.py` 追加：

```python
def test_normalize_sea_passes_through_pdf_fields():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea
    raw = {
        "carrier_name": "ONE", "destination_port_name": "HILO",
        "container_20gp": 5240.0, "container_40gp": 7100.0, "container_40hq": 7200.0,
        "container_45": 6075.0, "valid_from": "2026-02-03", "valid_to": "2026-02-28",
        "rate_level": "R5", "service_code": "EC3", "via": "BUSAN", "is_direct": False,
        "commodity": "TPE1-FAK", "remark": "inclusive of AGS",
    }
    out = _normalize_sea(raw, carrier_fallback="")
    assert out["container_45"] == 6075.0
    assert out["valid_from"] == "2026-02-03"
    assert out["valid_to"] == "2026-02-28"
    assert out["rate_level"] == "R5"
    assert out["service_code"] == "EC3"
    assert out["via"] == "BUSAN"
    assert out["is_direct"] is False
    assert out["commodity"] == "TPE1-FAK"
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py::test_normalize_sea_passes_through_pdf_fields -v`
Expected: FAIL — `KeyError: 'container_45'`（当前 `_normalize_sea` 不输出这些键）。

- [ ] **Step 3: 写实现**

在 `orchestrator.py` 的 `_normalize_sea` 返回 dict 末尾（`"source_file": row.get("source_file"),` 之后、闭合 `}` 之前）追加：

```python
        # PDF(ONE 合约)透传字段：老 Excel 行无这些键 → None/默认，无影响
        "container_45": row.get("container_45"),
        "valid_from": row.get("valid_from"),
        "valid_to": row.get("valid_to"),
        "rate_level": row.get("rate_level"),
        "service_code": row.get("service_code"),
        "via": row.get("via"),
        "is_direct": row.get("is_direct", True),
        "commodity": row.get("commodity"),
```

> 注意：`remark` 键 `_normalize_sea` 已有（`"remark": row.get("remarks")`）。ONE 解析行用的是 `remark` 键，需保证 note 文本能进 remark——把该行改为 `"remark": row.get("remark") or row.get("remarks"),`。

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -v`
Expected: PASS（含新测试，原有不破）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): _normalize_sea 透传 PDF 合约字段(45/生效日/rate_level/service/via 等)"
```

---

## Task 9: `commit_ocean_rows` 落库新字段

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/db_writer.py`
- Test: `backend/tests/sheet_builder/test_ocean_writer.py`

- [ ] **Step 1: 写失败测试**

向 `backend/tests/sheet_builder/test_ocean_writer.py` 追加（沿用该文件已有的 db fixture；若无独立 fixture，参照 `tests/services/step1_rates/test_commit_ocean_bilingual.py` 的内存库 + 灌 KMTC/港口写法，这里用 ONE + DALIAN/HILO）：

```python
def test_commit_ocean_writes_pdf_fields():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base, Carrier, CarrierType, Port
    from app.models.freight_rate import FreightRate
    from app.services.step1_rates.sheet_builder.db_writer import commit_ocean_rows

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Carrier(code="ONE", name_en="Ocean Network Express",
                   carrier_type=CarrierType.shipping_line, country="SG"))
    db.add(Port(un_locode="CNDLC", name_en="Dalian", name_cn="大连", country="CN", region="East Asia"))
    db.add(Port(un_locode="USHIL", name_en="Hilo", name_cn="希洛", country="US", region="North America"))
    db.commit()

    rows = [{
        "origin": "DALIAN", "destination": "HILO", "carrier": "ONE",
        "container_20gp": 5240, "container_40gp": 7100, "container_40hq": 7200,
        "container_45": 6075, "valid_from": "2026-02-03", "valid_to": "2026-02-28",
        "rate_level": "R5", "service_code": "EC3", "via": "BUSAN", "is_direct": False,
        "commodity": "TPE1-FAK", "remark": "inclusive of AGS",
    }]
    result = commit_ocean_rows(rows, db)
    assert result.fcl_rows == 1

    fr = db.query(FreightRate).one()
    assert fr.container_45 == 6075
    assert str(fr.valid_from) == "2026-02-03"
    assert str(fr.valid_to) == "2026-02-28"
    assert fr.rate_level == "R5"
    assert fr.service_code == "EC3"
    assert fr.via == "BUSAN"
    assert fr.is_direct is False
    assert fr.rmks == "TPE1-FAK"
    assert fr.remarks == "inclusive of AGS"
    db.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_writer.py::test_commit_ocean_writes_pdf_fields -v`
Expected: FAIL — `assert None == 6075`（`commit_ocean_rows` 当前不写 container_45 等）。

- [ ] **Step 3: 写实现**

在 `db_writer.py` 的 `commit_ocean_rows` 内构造 `FreightRate(...)` 处，追加字段（在 `container_40hq=...` 之后、`batch_id=...` 之前）：

```python
                container_45=_to_decimal(r.get("container_45")),
                valid_from=_to_date(r.get("valid_from")),
                valid_to=_to_date(r.get("valid_to")),
                rate_level=r.get("rate_level"),
                service_code=r.get("service_code"),
                via=r.get("via"),
                is_direct=r.get("is_direct", True),
                rmks=r.get("commodity"),
```

> `_to_decimal`、`_to_date`、`_to_int` 已存在于 db_writer.py（tier 路径用）。`remarks` 行已存在（`remarks=r.get("remark")`），无需改。

- [ ] **Step 4: 运行确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_writer.py -v`
Expected: PASS（含新测试，原有海运入库测试不破）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step1_rates/sheet_builder/db_writer.py backend/tests/sheet_builder/test_ocean_writer.py
git commit -m "feat(step1): commit_ocean_rows 落库 PDF 合约字段(45/生效日/rate_level/service/via/commodity)"
```

---

## Task 10: 真实文件集成验证 + 全量回归

**Files:**
- Test: `backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py`

- [ ] **Step 1: 加"真实文件存在才跑"的集成测试**

向 `test_one_contract_pdf.py` 追加：

```python
import os
import pytest

_SAMPLE = "/Users/zhangdongxu/Desktop/project/阪急阪神/资料/2026.05.27/Sea Net Rete/LAX0751N25v93 (2).pdf"


@pytest.mark.integration
@pytest.mark.skipif(not os.path.exists(_SAMPLE), reason="真实 ONE 合约样例不在本机")
def test_real_one_contract_parses_rows():
    out = ocp.parse_one_contract_pdf(_SAMPLE, db=None)
    assert out["carrier_code"] == "ONE"
    assert len(out["parsed_rows"]) > 0          # 至少抽到运价行
    # 干净数字行应有价（不全是 needs_review）
    priced = [r for r in out["parsed_rows"]
              if r["container_20gp"] is not None or r["container_40gp"] is not None]
    assert len(priced) > 0
```

- [ ] **Step 2: 本机跑集成测试（有样例时）**

Run: `../.venv/bin/python -m pytest "tests/services/step1_rates/adapters/test_one_contract_pdf.py::test_real_one_contract_parses_rows" -v`
Expected: 本机有样例 → PASS 并抽到 >0 行；**若抽到 0 行或 priced=0**，回到 `parse_rate_blocks`/`_extract_word_lines` 调列容差 `_TOL` 或行聚类阈值（pdfplumber 实际坐标与构造 fixture 可能不同），重跑直到 PASS。CI/他人机器无样例 → 自动 skip。

- [ ] **Step 3: 全量回归**

Run: `../.venv/bin/python -m pytest -m "not integration" -q`
Expected: 全绿（在本计划之前的基线 338 passed 之上，新增本计划的单元测试数；0 failed）。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/services/step1_rates/adapters/test_one_contract_pdf.py
git commit -m "test(step1): ONE 合约 PDF 真实文件集成测试(本机跑/CI skip) + 全量回归"
```

---

## 完成标准（Definition of Done）

- 上传 ONE 合约 PDF 到"做表"sea 模板 → 预览台出现运价行（脏行标 needs_review）→ 勾选入库 → `FreightRate` 落库，含 valid_from/container_45/rate_level/service_code/via/commodity。
- `../.venv/bin/python -m pytest -m "not integration" -q` 全绿。
- 不依赖 vLLM；不改表结构；air PDF 不受理；附加费金额不抽（只存清单文本）。

## 相对 spec 的 v1 取舍（明确记录）

- **合约级元数据（MQC、合约号 LAX0751N25 Amd.93）暂不结构化入库**：它们在合约法律前言、不在运价块里，解析投入与价值不成比例。v1 仅 `ImportBatch.source_file`（文件名，常含合约号）+ 每条运价的**块级生效日**（比合约级整体生效日更准）。carrier=ONE 已落在每条 FreightRate。MQC/合约号留作后续迭代。其余 spec 内容全覆盖。
