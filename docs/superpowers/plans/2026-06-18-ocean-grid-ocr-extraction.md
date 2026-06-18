# 规整表格 OCR 抽取（海运图像）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 海运图像里"规整网格表"（订舱网站导出）走本地 RapidOCR 确定性抽取，替掉慢/会幻觉/会截断的 VLM；判定不命中/0行/异常自动回落现有 VLM 路。

**Architecture:** 新增单一职责模块 `ocean_ocr_extractor.py`，三步：OCR→检测表头（学每列 X 区间）→按 X 把数据 token 绑到列→归一为与 `parse_ocean_image` 同构的行 dict。`orchestrator.add_file` 的 sea+图像分支先试 OCR、空则回落 VLM。下游 `_normalize_sea`/审核台/入库零改动。

**Tech Stack:** Python 3.10 / RapidOCR(rapidocr_onnxruntime, PP-OCRv4/v5 ONNX, 无 torch) / pytest。

**Spec:** `docs/superpowers/specs/2026-06-18-ocean-grid-ocr-extraction-design.md`

---

## 文件结构

- **Create** `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py` — OCR 网格抽取，唯一公开 `parse_ocean_grid()`。
- **Modify** `backend/app/services/step1_rates/sheet_builder/orchestrator.py` — sea+图像分支加 OCR 优先 + 回落。
- **Modify** `backend/requirements.txt` — 加 `rapidocr_onnxruntime`。
- **Create** `backend/tests/sheet_builder/test_ocean_ocr_extractor.py` — 纯函数单测（合成 OCR 块，不跑真引擎）+ mock 引擎的管线测。
- **Create** `backend/tests/sheet_builder/test_ocean_ocr_integration.py` — 真图集成测，文件缺失则 skip（真图不入 git）。

**测试约定**：单测全部用"合成 OCR 块"（`[box, text, score]` 列表）喂内部函数，确定性、无引擎依赖、不含客户数据。真图只在本地集成测试里跑。所有命令在 `backend/` 下用 `../.venv/bin/python`（Windows 换 `D:\Anaconda3\envs\py310\python.exe`）。

测试共用的合成块工具（每个测试文件顶部各放一份）：

```python
def _blk(text, xc, yc, w=44, h=18):
    """造一个 RapidOCR 风格的 [box, text, score]。box=四点。"""
    x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, 0.99
```

---

## Task 1: 依赖 + 引擎单例 + 块归一

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 加依赖**

在 `backend/requirements.txt` 末尾追加一行：

```
rapidocr_onnxruntime
```

安装：`cd backend && ../.venv/bin/python -m pip install rapidocr_onnxruntime`
预期：`Successfully installed rapidocr_onnxruntime-...`（POC 已验证可装，CPU 离线）。

- [ ] **Step 2: 写失败测试（块归一）**

创建 `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`：

```python
from app.services.step1_rates.sheet_builder import ocean_ocr_extractor as ocr


def _blk(text, xc, yc, w=44, h=18):
    x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, 0.99


def test_blocks_from_result_normalizes_and_drops_empty():
    result = [_blk("ONE", 100, 50), _blk("  ", 200, 50), _blk("$275", 300, 50)]
    blocks = ocr._blocks_from_result(result)
    assert [b["text"] for b in blocks] == ["ONE", "$275"]
    assert blocks[0]["xc"] == 100 and blocks[0]["yc"] == 50
    assert blocks[0]["xl"] < blocks[0]["xc"] < blocks[0]["xr"]
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: FAIL（`ModuleNotFoundError` 或 `AttributeError: _blocks_from_result`）。

- [ ] **Step 4: 写最小实现**

创建 `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`：

```python
"""Ocean(海运) 规整网格截图 → 行：本地 RapidOCR 确定性抽取，替 VLM 处理订舱网站导出的表格图。

检测不到表头 / 抽 0 行 / 引擎异常 → 返回带 error 的空结果（不抛），由 orchestrator 回落 VLM。
对外只暴露 parse_ocean_grid，返回结构与 ocean_ai_extractor.parse_ocean_image 同构。
"""
from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy.orm import Session

_PRICE_COLS = ("c20", "c40gp", "c40hq", "c45")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

_engine = None


def _get_engine():
    """RapidOCR 进程内单例懒加载（避免每张图重载模型）。"""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _blocks_from_result(result: Any) -> list[dict[str, Any]]:
    """RapidOCR 结果(list[[box,text,score]] 或 None) → 归一文本块；丢空文本。"""
    blocks: list[dict[str, Any]] = []
    for box, text, _score in (result or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        t = str(text).strip()
        if not t:
            continue
        blocks.append({
            "text": t,
            "xc": sum(xs) / 4.0, "yc": sum(ys) / 4.0,
            "xl": min(xs), "xr": max(xs), "h": max(ys) - min(ys),
        })
    return blocks
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（1 passed）。

- [ ] **Step 6: 提交**

```bash
git add backend/requirements.txt backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 抽取脚手架(依赖+引擎单例+块归一)"
```

---

## Task 2: 行聚类 `_cluster_rows`

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 写失败测试**

追加到测试文件：

```python
def test_cluster_rows_groups_by_y_band():
    # 两行,行内多列同 Y;行间 Y 差远大于行内字高
    blocks = ocr._blocks_from_result([
        _blk("ONE", 100, 50), _blk("$275", 300, 52),
        _blk("MSC", 100, 120), _blk("$472", 300, 118),
    ])
    rows = ocr._cluster_rows(blocks)
    assert len(rows) == 2
    assert {b["text"] for b in rows[0]} == {"ONE", "$275"}
    assert {b["text"] for b in rows[1]} == {"MSC", "$472"}
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py::test_cluster_rows_groups_by_y_band -q`
Expected: FAIL（`AttributeError: _cluster_rows`）。

- [ ] **Step 3: 写最小实现**

在 `ocean_ocr_extractor.py` 追加：

```python
def _cluster_rows(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 Y 把块聚成行：相邻块 Y 间隔 > 中位字高×0.8 视为新行（POC 验证过的口径）。"""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b["yc"])
    heights = sorted(b["h"] for b in ordered)
    med_h = heights[len(heights) // 2] or 20
    rows: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    last_y: float | None = None
    for b in ordered:
        if last_y is not None and b["yc"] - last_y > med_h * 0.8:
            rows.append(cur)
            cur = []
        cur.append(b)
        last_y = b["yc"]
    if cur:
        rows.append(cur)
    return rows
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 按Y聚行"
```

---

## Task 3: 表头检测 `_classify_header` / `_cols_to_bands` / `_detect_grid_header`

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
def _header_row():
    # 完整表头(含中间未知列),X 递增。返回 RapidOCR result。
    cols = ["起运港/码头", "目的港/码头", "舱位", "船期", "船司", "航线",
            "20'GP", "40'GP", "40'HQ", "45'HQ", "40'NOR", "历史", "有效期", "操作"]
    return [_blk(c, 100 + i * 100, 30) for i, c in enumerate(cols)]


def test_detect_grid_header_returns_bands():
    rows = ocr._cluster_rows(ocr._blocks_from_result(_header_row()))
    found = ocr._detect_grid_header(rows)
    assert found is not None
    idx, bands = found
    assert idx == 0
    for col in ("destination", "carrier", "c20", "c40gp", "c40hq", "valid"):
        assert col in bands


def test_detect_grid_header_bands_separate_neighbors():
    # carrier 列的 X 落进 carrier band,不串到 destination
    rows = ocr._cluster_rows(ocr._blocks_from_result(_header_row()))
    _idx, bands = ocr._detect_grid_header(rows)
    carrier_xc = 100 + 4 * 100  # 船司在第5个(idx4)
    l, r = bands["carrier"]
    assert l <= carrier_xc < r


def test_detect_grid_header_none_on_freetext():
    rows = ocr._cluster_rows(ocr._blocks_from_result([
        _blk("南星船公司上海港出东南亚价格含LSS", 400, 30),
        _blk("Karachi USD2650/2750 巴生中转", 400, 70),
    ]))
    assert ocr._detect_grid_header(rows) is None
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -k detect_grid_header -q`
Expected: FAIL（`AttributeError: _detect_grid_header`）。

- [ ] **Step 3: 写最小实现**

追加：

```python
def _classify_header(text: str) -> str | None:
    """单个表头单元 → 规范列名；认不出返回 None。OCR 轻微变形做容错。"""
    if "起运港" in text or "起運港" in text:
        return "origin"
    if "目的港" in text or "目的" in text:
        return "destination"
    if "船司" in text:
        return "carrier"
    if "有效期" in text:
        return "valid"
    t = text.upper().replace(" ", "").replace("'", "").replace("’", "")
    if "45" in t and "HQ" in t:
        return "c45"
    if "40" in t and "HQ" in t:
        return "c40hq"
    if "40" in t and "GP" in t:
        return "c40gp"
    if "20" in t and "GP" in t:
        return "c20"
    return None


def _cols_to_bands(cells: list[tuple[str, float]]) -> dict[str, tuple[float, float]]:
    """(列名, x中心) 列表 → 每列 X 区间(相邻中心取中点;首尾开放)。"""
    cells = sorted(cells, key=lambda c: c[1])
    bands: dict[str, tuple[float, float]] = {}
    for i, (col, xc) in enumerate(cells):
        left = float("-inf") if i == 0 else (cells[i - 1][1] + xc) / 2.0
        right = float("inf") if i == len(cells) - 1 else (xc + cells[i + 1][1]) / 2.0
        bands[col] = (left, right)
    return bands


def _detect_grid_header(
    rows: list[list[dict[str, Any]]]
) -> tuple[int, dict[str, tuple[float, float]]] | None:
    """找表头行(≥4 已知列 + 含目的港 + ≥1 价格列)。返回 (行号, 列X区间)。

    用整行所有单元(未知列给占位名 _xN)切 band,使中间列(舱位/船期/历史等)各占自己的带,
    不污染目标列。未命中返回 None(交路由回落 VLM)。
    """
    for idx, row in enumerate(rows):
        ordered = sorted(row, key=lambda d: d["xc"])
        known = [_classify_header(b["text"]) for b in ordered]
        known_set = {k for k in known if k}
        if len(known_set) >= 4 and "destination" in known_set and (known_set & set(_PRICE_COLS)):
            cells: list[tuple[str, float]] = []
            used: set[str] = set()
            for i, b in enumerate(ordered):
                col = known[i]
                if not col or col in used:
                    col = f"_x{i}"
                used.add(col)
                cells.append((col, b["xc"]))
            return idx, _cols_to_bands(cells)
    return None
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（5 passed）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 表头检测+列X区间(含未知列占位防污染)"
```

---

## Task 4: 价格归一 `_norm_price` + 列分配 `_assign`

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
import pytest


@pytest.mark.parametrize("text,expected", [
    ("$275", 275.0), ("$1,000", 1000.0), ("S1000", 1000.0),   # $ 误读成 S
    ("￥900", 900.0), ("6150", 6150.0), ("-", None), ("", None),
    ("0", None), ("咨询", None),
])
def test_norm_price(text, expected):
    assert ocr._norm_price(text) == expected


def test_assign_token_to_column():
    bands = {"destination": (0, 100), "carrier": (100, 200), "c20": (200, 300)}
    assert ocr._assign(150, bands) == "carrier"
    assert ocr._assign(250, bands) == "c20"
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -k "norm_price or assign" -q`
Expected: FAIL（`AttributeError: _norm_price`）。

- [ ] **Step 3: 写最小实现**

追加：

```python
def _norm_price(text: str) -> float | None:
    """金额文本 → float。去 $ ¥ 逗号空格;修 OCR 把 $ 误读成的前导 S(S1000);取首个数字。"""
    t = text.strip().replace(",", "").replace(" ", "").lstrip("$¥￥")
    t = re.sub(r"^[Ss](?=\d)", "", t)
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        v = float(m.group())
    except ValueError:
        return None
    return v if v > 0 else None


def _assign(xc: float, bands: dict[str, tuple[float, float]]) -> str | None:
    """token 的 x 中心落到哪个列区间。"""
    for col, (left, right) in bands.items():
        if left <= xc < right:
            return col
    return None
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（全绿）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 金额归一($/S/水印)+列分配"
```

---

## Task 5: 行抽取 `_first_price` + `_rows_from_ocr`

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 写失败测试**

追加（合成一张含表头 + 2 数据行的网格，含水印 token、多行日期）：

```python
def _grid_with_two_rows():
    blocks = list(_header_row())  # y=30
    # 第1行 y≈90:目的港/船司/三价/两段日期(上下两行) + 水印数字
    blocks += [
        _blk("PIRAEUS", 200, 90), _blk("ONE", 500, 90),
        _blk("$4000", 700, 90), _blk("$6150", 800, 90), _blk("$6150", 900, 90),
        _blk("2026-06-15", 1300, 84), _blk("2026-06-30", 1300, 98),
        _blk("4432", 650, 90),  # 水印,落在 c20/船司之间,应被列绑定丢弃或不入价
    ]
    # 第2行 y≈160
    blocks += [
        _blk("PIRAEUS", 200, 160), _blk("MSC", 500, 160),
        _blk("$4720", 700, 160), _blk("$6640", 800, 160), _blk("$6640", 900, 160),
        _blk("2026-06-15", 1300, 154), _blk("2026-06-30", 1300, 168),
    ]
    return blocks


def test_rows_from_ocr_extracts_correct_fields():
    rows_clustered = ocr._cluster_rows(ocr._blocks_from_result(_grid_with_two_rows()))
    idx, bands = ocr._detect_grid_header(rows_clustered)
    rows, _warns = ocr._rows_from_ocr(rows_clustered, idx, bands, "x.png")
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["destination"] == "PIRAEUS"
    assert r0["carrier"] == "ONE"
    assert (r0["container_20gp"], r0["container_40gp"], r0["container_40hq"]) == (4000.0, 6150.0, 6150.0)
    assert r0["valid_from"] == "2026-06-15" and r0["valid_to"] == "2026-06-30"
    assert r0["currency"] == "USD" and r0["surcharges"] == []
    assert rows[1]["carrier"] == "MSC" and rows[1]["container_20gp"] == 4720.0
```

注意：水印 `4432` 的 X(650) 处于 `c20`(xc≈700) 左侧、船司(xc≈500) 右侧的某个 `_xN`(航线列) band 内 → 不进 carrier/价列；即便落到某价列，`_first_price` 取该列首个能解析且 >0 的数，价列里真值 `$4000` 仍优先（同列水印数与真值不同列，X 已分开）。该测试断言价格正确即验证了隔离。

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py::test_rows_from_ocr_extracts_correct_fields -q`
Expected: FAIL（`AttributeError: _rows_from_ocr`）。

- [ ] **Step 3: 写最小实现**

追加：

```python
def _first_price(blocks_in_col: list[dict[str, Any]] | None) -> float | None:
    for b in sorted(blocks_in_col or [], key=lambda d: d["xl"]):
        p = _norm_price(b["text"])
        if p is not None:
            return p
    return None


def _join_col(blocks_in_col: list[dict[str, Any]] | None) -> str:
    return " ".join(
        t["text"] for t in sorted(blocks_in_col or [], key=lambda d: (d["yc"], d["xl"]))
    ).strip()


def _rows_from_ocr(
    rows: list[list[dict[str, Any]]],
    header_idx: int,
    bands: dict[str, tuple[float, float]],
    source_file: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """表头之下每行 → 按列 X 绑 token → 归一为 ocean 行 dict(与 ocean_ai_extractor 同构)。"""
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for row in rows[header_idx + 1:]:
        binned: dict[str, list[dict[str, Any]]] = {}
        for b in row:
            col = _assign(b["xc"], bands)
            if col:
                binned.setdefault(col, []).append(b)
        dest = _join_col(binned.get("destination"))
        if not dest:
            continue
        c20 = _first_price(binned.get("c20"))
        c40gp = _first_price(binned.get("c40gp"))
        c40hq = _first_price(binned.get("c40hq"))
        c45 = _first_price(binned.get("c45"))
        if not any((c20, c40gp, c40hq, c45)):
            continue  # 无价行(分隔/空行)跳过
        carrier = None
        if binned.get("carrier"):
            carrier = sorted(binned["carrier"], key=lambda d: d["xl"])[0]["text"].strip() or None
        dates = sorted({
            m.group()
            for b in binned.get("valid", [])
            for m in [_DATE_RE.search(b["text"])]
            if m
        })
        valid_from = dates[0] if dates else None
        valid_to = dates[-1] if len(dates) >= 2 else (dates[0] if dates else None)
        origin = _join_col(binned.get("origin")) or "NINGBO"
        needs_review = (not carrier) or (not valid_to) or (not (c20 and c40gp))
        out.append({
            "origin": origin,
            "destination": dest,
            "carrier": carrier,
            "vessel_voyage": None,
            "via": None,
            "is_direct": True,
            "container_20gp": c20,
            "container_40gp": c40gp,
            "container_40hq": c40hq,
            "container_45": c45,
            "currency": "USD",
            "valid_from": valid_from,
            "valid_to": valid_to,
            "transit_days": None,
            "surcharges": [],
            "remark": None,
            "needs_review": needs_review,
            "source_file": source_file,
            "source_type": "ocean_image",
        })
    return out, warnings
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（全绿）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 按列绑定抽行(目的港/船司/箱价/有效期+needs_review)"
```

---

## Task 6: 公开 `parse_ocean_grid` + `_empty`（mock 引擎测全管线）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_extractor.py`

- [ ] **Step 1: 写失败测试**

追加（用 monkeypatch 把 `_get_engine` 换成返回合成 result 的假引擎，不跑真 OCR）：

```python
class _FakeEngine:
    def __init__(self, result):
        self._result = result
    def __call__(self, _path):
        return self._result, 0.0


def test_parse_ocean_grid_happy(monkeypatch):
    monkeypatch.setattr(ocr, "_get_engine", lambda: _FakeEngine(_grid_with_two_rows()))
    res = ocr.parse_ocean_grid("x.png")
    assert res["total_rows"] == 2
    assert "error" not in res
    assert res["parsed_rows"][0]["destination"] == "PIRAEUS"
    assert res["source_type"] == "ocean_image" and res["file_name"] == "x.png"


def test_parse_ocean_grid_freetext_returns_error(monkeypatch):
    freetext = [_blk("南星船公司上海港出东南亚价格含LSS", 400, 30),
                _blk("Karachi USD2650/2750", 400, 70)]
    monkeypatch.setattr(ocr, "_get_engine", lambda: _FakeEngine(freetext))
    res = ocr.parse_ocean_grid("y.png")
    assert res["parsed_rows"] == [] and "error" in res


def test_parse_ocean_grid_engine_error_returns_error(monkeypatch):
    def _boom():
        raise RuntimeError("no model")
    monkeypatch.setattr(ocr, "_get_engine", _boom)
    res = ocr.parse_ocean_grid("z.png")
    assert res["parsed_rows"] == [] and "error" in res
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -k parse_ocean_grid -q`
Expected: FAIL（`AttributeError: parse_ocean_grid`）。

- [ ] **Step 3: 写最小实现**

追加：

```python
def _empty(source_file: str, msg: str) -> dict[str, Any]:
    return {
        "parsed_rows": [], "total_rows": 0, "error": msg,
        "source_type": "ocean_image", "file_name": source_file,
    }


def parse_ocean_grid(image_path: str, db: Session | None = None) -> dict[str, Any]:
    """规整网格海运截图 → 行。未检测到表头/0行/引擎异常 → 带 error 的空结果(交路由回落 VLM)。"""
    source_file = os.path.basename(image_path)
    try:
        engine = _get_engine()
        result, _elapse = engine(image_path)
    except Exception as e:  # noqa: BLE001 — 引擎缺失/异常不抛,回落 VLM
        return _empty(source_file, f"OCR 引擎不可用: {e}")
    rows_clustered = _cluster_rows(_blocks_from_result(result))
    header = _detect_grid_header(rows_clustered)
    if header is None:
        return _empty(source_file, "未检测到规整表头(非网格表)")
    header_idx, bands = header
    rows, warnings = _rows_from_ocr(rows_clustered, header_idx, bands, source_file)
    if not rows:
        return _empty(source_file, "检测到表头但未抽出有效运价行")
    return {
        "parsed_rows": rows, "total_rows": len(rows),
        "warnings": warnings, "source_type": "ocean_image", "file_name": source_file,
    }
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_extractor.py -q`
Expected: PASS（全绿）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ocr_extractor.py backend/tests/sheet_builder/test_ocean_ocr_extractor.py
git commit -m "feat(sheet-builder): ocean OCR 公开 parse_ocean_grid(表头/0行/异常→error 交回落)"
```

---

## Task 7: orchestrator 路由（OCR 优先 + 回落 VLM）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`
- Test: `backend/tests/sheet_builder/test_ocean_ocr_routing.py`（新建，避免与现有大测试文件混）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/sheet_builder/test_ocean_ocr_routing.py`：

```python
from app.services.step1_rates.sheet_builder import orchestrator


def _ocr_rows():
    return {"parsed_rows": [{"destination": "PIRAEUS", "container_20gp": 4000.0,
                             "carrier": "ONE", "needs_review": False}],
            "total_rows": 1, "source_type": "ocean_image", "file_name": "g.png"}


def test_sea_image_uses_ocr_when_grid(monkeypatch, tmp_path):
    img = tmp_path / "g.png"
    img.write_bytes(b"x")
    called = {"vlm": 0}
    monkeypatch.setattr(orchestrator.ocean_ocr_extractor, "parse_ocean_grid",
                        lambda *a, **k: _ocr_rows())
    monkeypatch.setattr(orchestrator.ocean_ai_extractor, "parse_ocean_image",
                        lambda *a, **k: called.__setitem__("vlm", called["vlm"] + 1) or {"parsed_rows": []})
    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "g.png", str(img), None)
    assert res.status == "parsed" and res.row_count == 1
    assert called["vlm"] == 0  # 命中 OCR,没调 VLM


def test_sea_image_falls_back_to_vlm_when_not_grid(monkeypatch, tmp_path):
    img = tmp_path / "f.png"
    img.write_bytes(b"x")
    called = {"vlm": 0}
    monkeypatch.setattr(orchestrator.ocean_ocr_extractor, "parse_ocean_grid",
                        lambda *a, **k: {"parsed_rows": [], "error": "未检测到规整表头"})
    def _vlm(*a, **k):
        called["vlm"] += 1
        return {"parsed_rows": [{"destination": "HCM", "container_20gp": 525.0,
                                 "carrier": "ANX", "needs_review": False}], "total_rows": 1}
    monkeypatch.setattr(orchestrator.ocean_ai_extractor, "parse_ocean_image", _vlm)
    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "f.png", str(img), None)
    assert called["vlm"] == 1  # OCR 0 行 → 回落 VLM
    assert res.status == "parsed" and res.row_count == 1
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_routing.py -q`
Expected: FAIL（`AttributeError: module 'orchestrator' has no attribute 'ocean_ocr_extractor'`）。

- [ ] **Step 3: 改实现**

在 `orchestrator.py` 顶部导入处（约 34 行）把 import 改为包含新模块：

```python
from app.services.step1_rates.sheet_builder import (
    air_extractor,
    air_ai_extractor,
    ocean_ai_extractor,
    ocean_ocr_extractor,
)
```

在 `add_file` 的图像分支（约 162-167 行）改为：

```python
        elif ext in _IMAGE_EXTS:
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_image(file_path, db)
                source_type = "air_image"
            else:
                # 规整网格表先走本地 OCR(快/确定/不幻觉);未命中表头或 0 行 → 回落 VLM。
                parsed = ocean_ocr_extractor.parse_ocean_grid(file_path, db)
                if not parsed.get("parsed_rows"):
                    parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)
                source_type = "ocean_image"
```

注意：原 import 行若是 `from ... import air_extractor, air_ai_extractor, ocean_ai_extractor`，按上面多行形式替换；确保 `ocean_ai_extractor` 仍在导入里（回落用）。

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_routing.py -q`
Expected: PASS（2 passed）。

- [ ] **Step 5: 回归（orchestrator 既有测试不破）**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/ -q`
Expected: PASS（全绿；既有 ocean_ai/air_ai 测试不受影响）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_ocean_ocr_routing.py
git commit -m "feat(sheet-builder): 海运图像路由先OCR规整表、0行/未命中回落VLM"
```

---

## Task 8: 真图集成测试（skippable，真图不入 git）

**Files:**
- Create: `backend/tests/sheet_builder/test_ocean_ocr_integration.py`

- [ ] **Step 1: 写集成测试**

创建 `backend/tests/sheet_builder/test_ocean_ocr_integration.py`：

```python
"""真图集成测试:跑真 RapidOCR 引擎。真图不入 git,放本地 OCR_SAMPLE_DIR(默认见下),缺失则 skip。"""
import os
import pytest

from app.services.step1_rates.sheet_builder import ocean_ocr_extractor as ocr

SAMPLE_DIR = os.environ.get(
    "OCEAN_OCR_SAMPLE_DIR",
    os.path.expanduser("~/Desktop/未命名文件夹"),
)

# (文件名, 期望行数, {船司: (20gp,40gp,40hq)})
CASES = [
    ("231c95611ea3bb8efec64812a78fed1c.png", 2,
     {"ONE": (4000, 6150, 6150), "MSC": (4720, 6640, 6640)}),
    ("efdc45ac4ed47e77dae30910693ccb22.png", 6,
     {"JJ": (275, 500, 500), "YML": (475, 900, 900)}),
    ("fac4e0b719c8f0840804f054fa6e5aa6.png", 5,
     {"JJ": (475, 900, 900), "YML": (575, 1150, 1150)}),
]


@pytest.mark.parametrize("fname,n_rows,checks", CASES)
def test_real_grid_images(fname, n_rows, checks):
    path = os.path.join(SAMPLE_DIR, fname)
    if not os.path.exists(path):
        pytest.skip(f"真图样本缺失,跳过: {path}")
    res = ocr.parse_ocean_grid(path)
    assert "error" not in res, res.get("error")
    assert res["total_rows"] == n_rows
    by_carrier = {r["carrier"]: r for r in res["parsed_rows"]}
    for carrier, (c20, c40gp, c40hq) in checks.items():
        assert carrier in by_carrier, f"缺船司 {carrier}"
        r = by_carrier[carrier]
        assert (r["container_20gp"], r["container_40gp"], r["container_40hq"]) == (c20, c40gp, c40hq)
```

- [ ] **Step 2: 跑集成测试**

把那 3 张真图放进 `~/Desktop/未命名文件夹/`（或设 `OCEAN_OCR_SAMPLE_DIR` 指向真图目录）。

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ocr_integration.py -q`
Expected: 真图在 → 3 passed；真图缺失 → 3 skipped（CI 上即 skip，不挂）。

- [ ] **Step 3: 提交**

```bash
git add backend/tests/sheet_builder/test_ocean_ocr_integration.py
git commit -m "test(sheet-builder): ocean OCR 真图集成测试(skippable,真图不入git)"
```

---

## Task 9: 全量回归 + 收尾

- [ ] **Step 1: 全量测试**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 新增用例全绿；既有用例不回归（注意：PostgreSQL 未起的 async 路由用例、依赖未跟踪真实样本的 air 用例属环境失败，与本改动无关，对照 base 确认）。

- [ ] **Step 2: 确认引擎首次加载提示**

首次 `import` 后跑一张真图确认引擎单例只加载一次（人工观察日志/耗时；非阻断）。

- [ ] **Step 3: 更新记忆**

把"OCR 规整表抽取已实装"更新进记忆 `step1-ocean-image-truncation-and-ocr-poc`（把"立项/POC"状态推进到"已实装+测试绿+分支名+未合并未推"）。

---

## Self-Review

**Spec coverage（逐条对照 spec）：**
- §3.1 新模块 `parse_ocean_grid` 同构返回 → Task 1/6 ✓
- §3.2 三步(`_detect_grid_header`/`_rows_from_ocr`/`_build_rows`) → Task 3/5（`_build_rows` 的归一并入 `_rows_from_ocr`，等价且更少跨函数传参）✓
- §3.3 引擎单例懒加载 + 全分辨率原图 → Task 1（`_get_engine`）、Task 6（直接喂 image_path，不压缩）✓
- §4 路由(先OCR、0行/异常回落VLM、air不动) → Task 7 ✓
- §5 噪点($→数字/前导S/水印按列X滤) + 引擎异常不抛回落 → Task 4(_norm_price)/Task 5(列绑定隔离水印)/Task 6(异常→error) ✓
- §6 依赖 rapidocr_onnxruntime → Task 1 ✓
- §7 测试(表头检测/行重建/路由/噪点/兜底/合成单测+真图skippable) → Task 3/5/7/4/6/8 ✓
- §8 影响面(仅1新文件+路由分支+1依赖,下游零改动) → Task 7 仅改 import+图像分支 ✓

**Placeholder 扫描：** 无 TBD/TODO；每个 code step 均有完整代码与命令。

**类型/命名一致性：** `parse_ocean_grid`/`_get_engine`/`_blocks_from_result`/`_cluster_rows`/`_classify_header`/`_cols_to_bands`/`_detect_grid_header`(返回 `(idx,bands)`)/`_assign`/`_norm_price`/`_first_price`/`_join_col`/`_rows_from_ocr(rows,header_idx,bands,source_file)`/`_empty` —— 跨 Task 引用一致；行 dict 键与 `ocean_ai_extractor._build_rows`/`_normalize_sea` 对齐(origin/destination/carrier/container_20gp/40gp/40hq/45/currency/valid_from/valid_to/surcharges/needs_review/source_file/source_type)。

**说明（与 spec 的等价偏差）：** spec §3.2 把"归一 `_build_rows`"列为独立第三步；计划里把它并进 `_rows_from_ocr`（同一遍按列绑定直接产出行 dict），减少中间结构与跨函数传参，行为与字段完全一致。
