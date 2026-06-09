# 指定数据下载（按客户模板回填海运运价）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做表页新增「指定数据下载」按钮，上传带目的港的海运模板，系统只把当前会话抽取的运价按目的港名匹配回填进模板的 `FCL N RATE OF OTHER PORTS` 页（以数据为准动态重排行、保留版式），其余港留空后下载。

**Architecture:** 新增一个纯函数核心 `template_refill.refill_into_template(template_bytes, rows)`（读上传 workbook → 扫 A 列目的港 → canonicalize 匹配当前 rows → 清数据区 → 按抓到的样式重排船司×箱型行 → 保存 bytes），一个薄 HTTP 端点 `POST /rate-sheet/{id}/download-into-template`（multipart：模板文件 + rows JSON），一个前端弹窗按钮。完全不动现有 `fill_template`（顺序填内置模板）的「下载」链路。

**Tech Stack:** Python 3.10 / FastAPI / openpyxl / pytest；React 19 / TS / Ant Design v6 / axios / i18next。

**Spec:** `docs/superpowers/specs/2026-06-09-specified-data-download-design.md`

---

## 文件结构

新增：
- `backend/app/services/step1_rates/sheet_builder/template_refill.py` — 核心回填器（profile + RefillError + 匹配/附加费/扫港/重排）
- `backend/tests/fixtures/sea_other_ports_template.xlsx` — 客户模板副本（测试夹具）
- `backend/tests/sheet_builder/test_template_refill.py` — 核心单测
- `backend/tests/api_v1/test_rate_sheet_download_into_template.py` — 端点测

改动：
- `backend/app/api/v1/rate_sheet.py` — 加端点
- `frontend/src/services/api.ts` — 加 `rateSheetApi.downloadIntoTemplate`
- `frontend/src/pages/RateSheetBuilder.tsx` — 加按钮 + 弹窗 + 处理
- `frontend/src/i18n/{zh,ja,en}.json` — 三语文案

---

## Task 1: 核心回填器 `template_refill.py`（纯函数，TDD）

**Files:**
- Create: `backend/tests/fixtures/sea_other_ports_template.xlsx`
- Create: `backend/tests/sheet_builder/test_template_refill.py`
- Create: `backend/app/services/step1_rates/sheet_builder/template_refill.py`

- [ ] **Step 1: 复制客户模板做夹具**

Run（在仓库根目录）:
```bash
mkdir -p backend/tests/fixtures
cp "资料/2026.06.08/Sea Net Rate_2026_May.15th - May.31st (空白　着地あり).xlsx" \
   backend/tests/fixtures/sea_other_ports_template.xlsx
ls -l backend/tests/fixtures/sea_other_ports_template.xlsx
```
Expected: 文件存在，约 42KB。

- [ ] **Step 2: 写失败测试 `test_template_refill.py`**

```python
"""按客户模板回填海运运价（OTHER PORTS 页）核心测试。

纯函数 refill_into_template：给模板 bytes + 当前会话 rows，返回填好的 xlsx bytes。
夹具 = 客户真实「空白 着地あり」模板（保留目的港名、价格留空）。
"""
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.services.step1_rates.sheet_builder.template_refill import (
    RefillError,
    refill_into_template,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sea_other_ports_template.xlsx"
SHEET = "FCL N RATE OF OTHER PORTS"


def _tpl_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _refill(rows):
    content = refill_into_template(_tpl_bytes(), rows)
    assert content[:2] == b"PK"  # xlsx = zip
    return load_workbook(BytesIO(content), data_only=False)


def test_basic_fill_carrier_and_container_rows():
    rows = [
        {"destination": "HONG KONG", "carrier": "SJJ",
         "container_20gp": 230, "container_40gp": 460, "container_40hq": 460,
         "via": "DIRECT", "transit": "4days"},
        {"destination": "HONG KONG", "carrier": "ASL",
         "container_20gp": 240, "container_40hq": 480},
        {"destination": "BUSAN", "carrier": "EAS",
         "container_20gp": 160, "container_40hq": 320},
    ]
    ws = _refill(rows)[SHEET]
    # HONG KONG 从数据起始行 r9 开始，2 船司 × 2 箱型 = 4 行
    assert ws.cell(9, 1).value == "HONG KONG"
    assert ws.cell(9, 2).value == "SJJ"
    assert ws.cell(9, 3).value == "20FT"
    assert ws.cell(9, 4).value == 230
    assert ws.cell(10, 3).value == "40FT/40HQ"
    assert ws.cell(10, 4).value == 460
    assert ws.cell(11, 2).value == "ASL"
    assert ws.cell(11, 4).value == 240
    assert ws.cell(12, 4).value == 480
    # A 列港名竖向合并整块 r9:r12
    assert any(str(m) == "A9:A12" for m in ws.merged_cells.ranges)
    # BUSAN 紧接 r13，1 船司 × 2 行
    assert ws.cell(13, 1).value == "BUSAN"
    assert ws.cell(13, 2).value == "EAS"
    assert ws.cell(14, 3).value == "40FT/40HQ"
    assert ws.cell(14, 4).value == 320


def test_40_row_takes_40hq_when_differ():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40gp": 300, "container_40hq": 320}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(9, 4).value == 160      # 20FT
    assert ws.cell(10, 4).value == 320     # 40 行取 40HQ（≠40GP 时）


def test_40_row_falls_back_to_40gp_when_no_40hq():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40gp": 300}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(10, 4).value == 300     # 40HQ 空 → 回退 40GP


def test_surcharges_map_to_lss_baf_cic_caf():
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40hq": 320,
             "surcharges": [
                 {"code": "LSS", "included": True},
                 {"code": "BAF", "payment": "collect"},
                 {"code": "CIC", "amount_20": 50, "amount_40": 100},
                 {"code": "CAF", "note": "subject to dest"},
             ]}]
    ws = _refill(rows)[SHEET]
    # 20FT 行：E=LSS F=BAF G=CIC H=CAF
    assert ws.cell(9, 5).value == "Incl."
    assert ws.cell(9, 6).value == "Collect"
    assert ws.cell(9, 7).value == 50
    assert ws.cell(9, 8).value == "subject to dest"
    # 40 行 CIC 取 amount_40
    assert ws.cell(10, 7).value == 100


def test_surcharge_falls_back_to_flat_lss_cic():
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160,
             "lss_cic": "Incl.", "baf": 30}]
    ws = _refill(rows)[SHEET]
    assert ws.cell(9, 5).value == "Incl."   # 无 surcharges → 用扁平 lss_cic 落 LSS 列
    assert ws.cell(9, 6).value == 30        # 扁平 baf 落 BAF 列


def test_empty_port_keeps_name_one_blank_row():
    # SINGAPORE 在模板里，rows 没有它 → 留港名 + 1 空行
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    ws = _refill(rows)[SHEET]
    col_a = [ws.cell(r, 1).value for r in range(9, 40)]
    assert "SINGAPORE" in col_a
    # SINGAPORE 那一行价格列(D)为空
    sg_row = 9 + col_a.index("SINGAPORE")
    assert ws.cell(sg_row, 4).value in (None, "")


def test_alias_and_multiname_matching():
    rows = [
        {"destination": "PUSAN", "carrier": "EAS", "container_20gp": 160},       # PUSAN↔BUSAN
        {"destination": "CHENNAI", "carrier": "X", "container_20gp": 700},       # ↔ MADRAS / CHENNAI
        {"destination": "LOS ANGELES", "carrier": "Y", "container_20gp": 800},   # ↔ LONG BEACH⏎LOS ANGELES
        {"destination": "CHICAGO", "carrier": "Z", "container_20gp": 900},       # ↔ CHICAGO (via LAX)
    ]
    ws = _refill(rows)[SHEET]
    cells = {(ws.cell(r, 1).value, ws.cell(r, 2).value): ws.cell(r, 4).value
             for r in range(9, ws.max_row + 1)}
    assert ("BUSAN", "EAS") in cells and cells[("BUSAN", "EAS")] == 160
    assert ("MADRAS / CHENNAI", "X") in cells and cells[("MADRAS / CHENNAI", "X")] == 700
    assert ("LONG BEACH\nLOS ANGELES", "Y") in cells and cells[("LONG BEACH\nLOS ANGELES", "Y")] == 800
    assert ("CHICAGO (via LAX)", "Z") in cells and cells[("CHICAGO (via LAX)", "Z")] == 900


def test_unlisted_port_is_filtered_out():
    rows = [{"destination": "DALIAN", "carrier": "EAS", "container_20gp": 999},
            {"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    ws = _refill(rows)[SHEET]
    col_a = [ws.cell(r, 1).value for r in range(9, ws.max_row + 1)]
    assert "DALIAN" not in col_a       # 模板没列 → 不输出


def test_fidelity_other_sheets_and_header_untouched():
    rows = [{"destination": "BUSAN", "carrier": "EAS", "container_20gp": 160}]
    wb = _refill(rows)
    assert wb.sheetnames == [
        "JP N RATE FCL & LCL", "FCL N RATE OF OTHER PORTS", "LCL N RATE",
    ]
    # 表头 8 行不变
    assert wb[SHEET].cell(8, 1).value == "TO"
    # JP 页原样保留（她模板里 JP 页留了 TOKYO/OSAKA）
    assert wb["JP N RATE FCL & LCL"].cell(9, 1).value == "TOKYO\nYOKOHAMA"


def test_empty_rows_produce_blank_ports_no_crash():
    wb = _refill([])
    ws = wb[SHEET]
    # 所有港留名、价格空
    assert ws.cell(9, 1).value == "HONG KONG"
    assert ws.cell(9, 4).value in (None, "")


def test_missing_sheet_raises_refill_error():
    from openpyxl import Workbook
    buf = BytesIO()
    Workbook().save(buf)            # 全新空 workbook，无 OTHER PORTS 页
    with pytest.raises(RefillError):
        refill_into_template(buf.getvalue(), [])
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_template_refill.py -q`
Expected: FAIL（`ModuleNotFoundError: ...template_refill` 或导入错误）

- [ ] **Step 4: 实现 `template_refill.py`**

```python
"""按客户上传的模板回填海运运价（仅 FCL N RATE OF OTHER PORTS 页）。

与 template_filler.fill_template（顺序填内置空白模板）并存、互不影响。
本模块：读上传 workbook → 扫 A 列保留的目的港 → 按 canonicalize 匹配当前会话 rows →
以数据为准重排「船司 × {20FT, 40FT/40HQ}」行（抓原模板样式重铺、保留版式）→ 返回 bytes。
对不上/无数据的港留空（不报告）。其余 sheet（JP/LCL）原样保留。
"""
from __future__ import annotations

import re
from copy import copy
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.services.step1_rates.port_normalizer import canonicalize
from app.services.step1_rates.writers.base import safe_set, save_workbook_to_bytes


class RefillError(Exception):
    """模板不满足回填前提（如缺目标工作表）。端点据此返回 400。"""


# 本次只配 OTHER PORTS 一份；以后扩 JP/LCL 只加 profile，不改算法。
OTHER_PORTS_PROFILE: dict[str, Any] = {
    "sheet_name": "FCL N RATE OF OTHER PORTS",
    "header_row": 8,
    "data_start_row": 9,
    "cols": {
        "destination": 1, "carrier": 2, "container": 3, "freight": 4,
        "lss": 5, "baf": 6, "cic": 7, "caf": 8,
        "sailing": 9, "via": 10, "transit": 11,
        "booking": 12, "thc": 13, "doc": 14, "isps": 15, "equipment": 16,
        "rmks": 17,
    },
    "container_rows": [
        {"label": "20FT", "freight": ["container_20gp"], "container": 20},
        {"label": "40FT/40HQ", "freight": ["container_40hq", "container_40gp"], "container": 40},
    ],
    "surcharge_cols": {"lss": "LSS", "baf": "BAF", "cic": "CIC", "caf": "CAF"},
    # 每船司块内跨 2 行合并的列（复刻原模板：船司/船期/中转/航程/备注竖向合并）
    "merge_cols": ("carrier", "sailing", "via", "transit", "rmks"),
}

_SPLIT_RE = re.compile(r"[/\n]")


def refill_into_template(
    template_bytes: bytes,
    rows: list[dict[str, Any]],
    *,
    profile: dict[str, Any] = OTHER_PORTS_PROFILE,
) -> bytes:
    """把 rows 回填进上传模板的目标页，返回填好的 xlsx bytes。

    非 .xlsx/损坏 → openpyxl 抛异常（端点转 400）；缺目标页 → RefillError。
    """
    wb = load_workbook(BytesIO(template_bytes), data_only=False)
    name = profile["sheet_name"]
    if name not in wb.sheetnames:
        raise RefillError(f"模板缺少 '{name}' 工作表")
    ws = wb[name]

    ports = _scan_ports(ws, profile)
    styles = _capture_row_styles(ws, profile)
    _clear_data_area(ws, profile)
    by_port = _group_rows_by_port(rows)
    _write_ports(ws, profile, ports, by_port, styles)
    return save_workbook_to_bytes(wb)


def _scan_ports(ws, profile: dict[str, Any]) -> list[str]:
    """从数据起始行往下扫 A 列，非空即一个目的港，按出现顺序返回。"""
    col = profile["cols"]["destination"]
    ports: list[str] = []
    for r in range(profile["data_start_row"], ws.max_row + 1):
        v = ws.cell(r, col).value
        if v is not None and str(v).strip() != "":
            ports.append(str(v).strip())
    return ports


def _capture_row_styles(ws, profile: dict[str, Any]) -> dict[str, dict[int, Any]]:
    """抓数据区前两行（20FT 行 / 40 行）每列样式，作为重铺新行的样式模板。"""
    start = profile["data_start_row"]
    maxc = ws.max_column
    return {
        "c20": {c: copy(ws.cell(start, c)._style) for c in range(1, maxc + 1)},
        "c40": {c: copy(ws.cell(start + 1, c)._style) for c in range(1, maxc + 1)},
    }


def _clear_data_area(ws, profile: dict[str, Any]) -> None:
    """unmerge 数据区所有合并格并清值（样式已被 _capture_row_styles 抓走）。

    该模板目的港后无页脚（已确认），故清到 max_row。
    """
    start = profile["data_start_row"]
    for rng in [str(m) for m in ws.merged_cells.ranges if m.min_row >= start]:
        ws.unmerge_cells(rng)
    for r in range(start, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None


def _group_rows_by_port(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        key = canonicalize(row.get("destination"))
        if not key:
            continue
        out.setdefault(key, []).append(row)
    return out


def _port_candidates(name: str) -> set[str]:
    """模板港名 → 候选 canonical 集合：去括号、按 / 与换行拆名，提升命中率。

    例：'MADRAS / CHENNAI'→{MADRAS,CHENNAI,MADRASCHENNAI}；
        'CHICAGO (via LAX)'→{CHICAGO}；'LONG BEACH\\nLOS ANGELES'→{LONGBEACH,LOSANGELES,...}
    """
    base = re.sub(r"\([^)]*\)", " ", str(name or ""))
    cands: set[str] = set()
    whole = canonicalize(base)
    if whole:
        cands.add(whole)
    for part in _SPLIT_RE.split(base):
        cp = canonicalize(part)
        if cp:
            cands.add(cp)
    return cands


def _match_rows(port_name: str, by_port: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for cand in _port_candidates(port_name):
        matched.extend(by_port.get(cand, []))
    return matched


def _freight(row: dict[str, Any], crow: dict[str, Any]) -> Any:
    for key in crow["freight"]:
        v = row.get(key)
        if v is not None:
            return v
    return None


def _surcharge_cell(row: dict[str, Any], code: str, container: int) -> Any:
    """结构化附加费 → 单元格值，还原原始样本写法（Incl./Collect/数值/备注）。"""
    amt_key = "amount_20" if container == 20 else "amount_40"
    for item in (row.get("surcharges") or []):
        if str(item.get("code") or "").strip().upper() != code:
            continue
        if item.get("included"):
            return "Incl."
        if str(item.get("payment") or "").strip().lower() == "collect":
            return "Collect"
        amt = item.get(amt_key)
        if amt is None:
            amt = item.get("amount")
        if amt is not None:
            return amt
        if item.get("note"):
            return item.get("note")
        return None
    # 兜底：surcharges 无此项 → 用扁平字段（老 Excel 行）
    if code == "LSS":
        return row.get("lss_cic")
    if code == "BAF":
        return row.get("baf")
    return None


def _apply_style(ws, r: int, style_map: dict[int, Any]) -> None:
    for c, st in style_map.items():
        ws.cell(r, c)._style = copy(st)


def _write_ports(ws, profile, ports, by_port, styles) -> None:
    col = profile["cols"]
    crows = profile["container_rows"]
    scol = profile["surcharge_cols"]
    r = profile["data_start_row"]
    for port in ports:
        matched = _match_rows(port, by_port)
        block_start = r
        if not matched:
            _apply_style(ws, r, styles["c20"])
            safe_set(ws.cell(r, col["destination"]), port)
            r += 1
            continue
        for row in matched:
            top, bot = crows[0], crows[1]
            # 20FT 行
            _apply_style(ws, r, styles["c20"])
            safe_set(ws.cell(r, col["destination"]), port)
            safe_set(ws.cell(r, col["carrier"]), row.get("carrier"))
            ws.cell(r, col["container"]).value = top["label"]
            safe_set(ws.cell(r, col["freight"]), _freight(row, top))
            safe_set(ws.cell(r, col["lss"]), _surcharge_cell(row, scol["lss"], 20))
            safe_set(ws.cell(r, col["baf"]), _surcharge_cell(row, scol["baf"], 20))
            safe_set(ws.cell(r, col["cic"]), _surcharge_cell(row, scol["cic"], 20))
            safe_set(ws.cell(r, col["caf"]), _surcharge_cell(row, scol["caf"], 20))
            safe_set(ws.cell(r, col["via"]), row.get("via"))
            safe_set(ws.cell(r, col["transit"]), row.get("transit") or row.get("transit_days"))
            safe_set(ws.cell(r, col["rmks"]), row.get("remark"))
            # 40FT/40HQ 行
            _apply_style(ws, r + 1, styles["c40"])
            ws.cell(r + 1, col["container"]).value = bot["label"]
            safe_set(ws.cell(r + 1, col["freight"]), _freight(row, bot))
            safe_set(ws.cell(r + 1, col["lss"]), _surcharge_cell(row, scol["lss"], 40))
            safe_set(ws.cell(r + 1, col["baf"]), _surcharge_cell(row, scol["baf"], 40))
            safe_set(ws.cell(r + 1, col["cic"]), _surcharge_cell(row, scol["cic"], 40))
            safe_set(ws.cell(r + 1, col["caf"]), _surcharge_cell(row, scol["caf"], 40))
            # 每船司块跨 2 行合并（复刻原模板竖向合并）
            for key in profile["merge_cols"]:
                ws.merge_cells(start_row=r, end_row=r + 1,
                               start_column=col[key], end_column=col[key])
            r += 2
        # 港名（A 列）竖向合并整块
        if r - 1 > block_start:
            ws.merge_cells(start_row=block_start, end_row=r - 1,
                           start_column=col["destination"], end_column=col["destination"])
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_template_refill.py -q`
Expected: PASS（11 个测试全过）

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/template_refill.py \
        backend/tests/sheet_builder/test_template_refill.py \
        backend/tests/fixtures/sea_other_ports_template.xlsx
git commit -m "feat(step1): 指定数据下载核心回填器 template_refill

读上传模板的 OTHER PORTS 页, 按目的港名(canonicalize+多名拆分)匹配当前
会话 rows, 以数据为准重排船司×箱型行+保留版式, 其余港留空。纯函数, 11 测试。"
```

---

## Task 2: 后端端点 `POST /rate-sheet/{id}/download-into-template`（TDD）

**Files:**
- Create: `backend/tests/api_v1/test_rate_sheet_download_into_template.py`
- Modify: `backend/app/api/v1/rate_sheet.py`

- [ ] **Step 1: 写失败的端点测试**

```python
"""指定数据下载端点：multipart(模板 + rows JSON) → 回填后的 xlsx。"""
import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.api.deps import get_db
from app.main import app

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sea_other_ports_template.xlsx"
)


@pytest.fixture
def client():
    def _override_get_db():
        yield None

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _new_sea_session(client) -> str:
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    return r.json()["data"]["session_id"]


def test_download_into_template_fills_other_ports(client):
    sid = _new_sea_session(client)
    rows = [{"destination": "BUSAN", "carrier": "EAS",
             "container_20gp": 160, "container_40hq": 320}]
    r = client.post(
        f"/api/v1/rate-sheet/{sid}/download-into-template",
        data={"rows": json.dumps(rows)},
        files={"template": ("tpl.xlsx", FIXTURE.read_bytes(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    ws = load_workbook(BytesIO(r.content))["FCL N RATE OF OTHER PORTS"]
    assert ws.cell(9, 1).value == "HONG KONG"   # 未匹配港留名
    # BUSAN 被填（在表里某行）
    a = [ws.cell(rr, 1).value for rr in range(9, ws.max_row + 1)]
    assert "BUSAN" in a


def test_unknown_session_returns_404(client):
    r = client.post(
        "/api/v1/rate-sheet/nope/download-into-template",
        data={"rows": "[]"},
        files={"template": ("tpl.xlsx", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert r.json()["code"] == 404


def test_bad_rows_json_returns_400(client):
    sid = _new_sea_session(client)
    r = client.post(
        f"/api/v1/rate-sheet/{sid}/download-into-template",
        data={"rows": "not-json"},
        files={"template": ("tpl.xlsx", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert r.json()["code"] == 400


def test_non_xlsx_template_returns_400(client):
    sid = _new_sea_session(client)
    r = client.post(
        f"/api/v1/rate-sheet/{sid}/download-into-template",
        data={"rows": "[]"},
        files={"template": ("x.txt", b"not a zip", "text/plain")},
    )
    assert r.json()["code"] == 400


def test_air_session_returns_400(client):
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "air"})
    sid = r.json()["data"]["session_id"]
    r = client.post(
        f"/api/v1/rate-sheet/{sid}/download-into-template",
        data={"rows": "[]"},
        files={"template": ("tpl.xlsx", FIXTURE.read_bytes(), "application/octet-stream")},
    )
    assert r.json()["code"] == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_download_into_template.py -q`
Expected: FAIL（404/405：端点不存在）

- [ ] **Step 3: 加端点到 `rate_sheet.py`**

在 `import` 区加（与现有 import 同块）：
```python
import json
from urllib.parse import quote

from app.services.step1_rates.sheet_builder.template_refill import (
    RefillError,
    refill_into_template,
)
```

在文件末尾（`download_rate_sheet_post` 之后）追加端点：
```python
@router.post("/{session_id}/download-into-template")
async def download_into_template(
    session_id: str,
    template: UploadFile = File(...),
    rows: str = Form(...),
):
    """指定数据下载：把当前会话 rows 按目的港回填进用户上传的模板（仅 OTHER PORTS 页）。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")
    if session.template_type != "sea":
        return ApiResponse(code=400, message="指定数据下载仅支持海运模板")

    try:
        parsed_rows = json.loads(rows)
        if not isinstance(parsed_rows, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return ApiResponse(code=400, message="提交的运价数据格式有误")

    template_bytes = await template.read()
    try:
        content = await run_in_threadpool(
            refill_into_template, template_bytes, parsed_rows
        )
    except RefillError as exc:
        return ApiResponse(code=400, message=str(exc))
    except Exception:
        return ApiResponse(code=400, message="模板文件无法解析，请上传 .xlsx 模板")

    stem = (template.filename or "rate").rsplit(".", 1)[0] or "rate"
    download_name = f"{stem}_filled.xlsx"
    disposition = (
        "attachment; filename=rate_filled.xlsx; "
        f"filename*=UTF-8''{quote(download_name)}"
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )
```

> 注：`UploadFile / File / Form / run_in_threadpool / StreamingResponse / ApiResponse / orchestrator` 在本文件已 import（见文件头）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_download_into_template.py -q`
Expected: PASS（5 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/rate_sheet.py \
        backend/tests/api_v1/test_rate_sheet_download_into_template.py
git commit -m "feat(step1): 指定数据下载端点 POST /rate-sheet/{id}/download-into-template

multipart(模板+rows JSON)→回填器→流式 xlsx; session/类型/JSON/文件 校验返回 400/404;
回填甩 run_in_threadpool 避免冻 event loop; 文件名 UTF-8 编码。5 测试。"
```

---

## Task 3: 前端 API 方法 `rateSheetApi.downloadIntoTemplate`

**Files:**
- Modify: `frontend/src/services/api.ts`（`rateSheetApi` 对象内，`downloadFilled` 之后）

- [ ] **Step 1: 加方法**

在 `api.ts` 的 `downloadFilled` 定义之后、`rateSheetApi` 的 `}` 之前插入：
```typescript
  // 指定数据下载：上传带目的港的模板 + 当前会话最终行，后端只回填指定港。
  downloadIntoTemplate: (
    sessionId: string,
    template: File,
    rows: unknown[],
  ): Promise<Blob> => {
    const fd = new FormData();
    fd.append('template', template);
    fd.append('rows', JSON.stringify(rows));
    return api.post<unknown, Blob>(
      `/rate-sheet/${sessionId}/download-into-template`,
      fd,
      {
        responseType: 'blob',
        timeout: 180000,
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    );
  },
```

- [ ] **Step 2: 编译校验**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: 无报错（或与改动无关的既有报错不增加）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(step1): 前端 rateSheetApi.downloadIntoTemplate（指定数据下载）"
```

---

## Task 4: 前端按钮 + 弹窗 + 处理（RateSheetBuilder）

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`

- [ ] **Step 1: 引入 Modal**

把第 2 行的 antd import 改为加上 `Modal`：
```typescript
import { Upload, Input, InputNumber, Table, Tooltip, message, Select, Spin, Modal } from 'antd';
```

- [ ] **Step 2: 加状态（在 `const [downloading, setDownloading] = useState(false);` 附近）**

```typescript
  const [specOpen, setSpecOpen] = useState(false);
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [specDownloading, setSpecDownloading] = useState(false);
```

- [ ] **Step 3: 加处理函数（在 `handleDownload` 之后）**

```typescript
  const handleSpecifiedDownload = async () => {
    if (!sessionId || !specFile || specDownloading) return;
    setSpecDownloading(true);
    try {
      const blob = await rateSheetApi.downloadIntoTemplate(
        sessionId,
        specFile,
        buildFinalRows(),
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${specFile.name.replace(/\.[^.]+$/, '')}_filled.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(t('rateSheet.specifiedDownloadDone'));
      setSpecOpen(false);
      setSpecFile(null);
    } catch {
      message.error(t('rateSheet.downloadFailed'));
    } finally {
      setSpecDownloading(false);
    }
  };
```

- [ ] **Step 4: 加按钮（在「下载」按钮 `</button>` 之后、`card-head` 的 `</div>` 之前）**

定位 `frontend/src/pages/RateSheetBuilder.tsx` 中 step3 卡片头部的下载按钮（`onClick={handleDownload}` 那个）。在它的闭合 `</button>` 之后插入：
```tsx
          {templateType === 'sea' && (
            <button
              type="button"
              className="btn btn-sm"
              style={{ marginLeft: 8 }}
              disabled={!summary || keptCount === 0}
              onClick={() => setSpecOpen(true)}
            >
              <Icon name="download" size={14} />
              {t('rateSheet.specifiedDownload')}
            </button>
          )}
```

- [ ] **Step 5: 加弹窗（在组件最外层 return 的根元素内末尾、最后一个 `</div>` 之前）**

```tsx
      <Modal
        open={specOpen}
        title={t('rateSheet.specifiedDownload')}
        onCancel={() => {
          setSpecOpen(false);
          setSpecFile(null);
        }}
        onOk={handleSpecifiedDownload}
        okText={t('rateSheet.specifiedDownloadConfirm')}
        okButtonProps={{ disabled: !specFile, loading: specDownloading }}
        confirmLoading={specDownloading}
      >
        <p style={{ marginBottom: 12 }}>{t('rateSheet.specifiedDownloadHint')}</p>
        <Upload
          accept=".xlsx"
          maxCount={1}
          beforeUpload={(file) => {
            setSpecFile(file as unknown as File);
            return false;
          }}
          onRemove={() => setSpecFile(null)}
          fileList={
            specFile
              ? ([{ uid: '-1', name: specFile.name } as UploadFile])
              : []
          }
        >
          <button type="button" className="btn btn-sm">
            {t('rateSheet.specifiedDownloadPick')}
          </button>
        </Upload>
      </Modal>
```

- [ ] **Step 6: 编译校验**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: 无新增报错

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx
git commit -m "feat(step1): 做表页加「指定数据下载」按钮+上传模板弹窗（仅海运）"
```

---

## Task 5: i18n 三语文案

**Files:**
- Modify: `frontend/src/i18n/zh.json`、`ja.json`、`en.json`（均在 `rateSheet` 段内）

- [ ] **Step 1: zh.json — 在 `rateSheet` 段加 5 个键**

在 `"rateSheet": { ... }` 内（如 `"download"` 附近）加：
```json
    "specifiedDownload": "指定数据下载",
    "specifiedDownloadHint": "上传你保留了目的港的模板，系统只把这些目的港的运价填进去（其余港留空）。",
    "specifiedDownloadPick": "选择模板文件（.xlsx）",
    "specifiedDownloadConfirm": "确认下载",
    "specifiedDownloadDone": "已按指定目的港生成并下载",
```

- [ ] **Step 2: ja.json — 同位置加**

```json
    "specifiedDownload": "指定データダウンロード",
    "specifiedDownloadHint": "仕向港を残したテンプレートをアップロードしてください。指定の仕向港のみレートを記入します（他港は空欄）。",
    "specifiedDownloadPick": "テンプレートを選択（.xlsx）",
    "specifiedDownloadConfirm": "ダウンロード",
    "specifiedDownloadDone": "指定の仕向港で作成・ダウンロードしました",
```

- [ ] **Step 3: en.json — 同位置加**

```json
    "specifiedDownload": "Specified-port download",
    "specifiedDownloadHint": "Upload your template with the destination ports kept; the system fills rates only for those ports (others left blank).",
    "specifiedDownloadPick": "Choose template (.xlsx)",
    "specifiedDownloadConfirm": "Download",
    "specifiedDownloadDone": "Generated and downloaded for the specified ports",
```

- [ ] **Step 4: 校验 JSON 合法 + 编译/构建**

Run:
```bash
cd frontend
node -e "['zh','ja','en'].forEach(f=>JSON.parse(require('fs').readFileSync('src/i18n/'+f+'.json')))"
npm run build
```
Expected: JSON 解析无错；`npm run build` 成功（无新增报错）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "i18n(step1): 指定数据下载 三语文案"
```

---

## Task 6: 回归与收尾

**Files:** 无（验证 + lint）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全绿（基线 ≈457 + 本次新增 16 = ≈473 passed），无 FAIL

- [ ] **Step 2: 前端 lint**

Run: `cd frontend && npm run lint`
Expected: 无新增 error（既有 warning 不计）

- [ ] **Step 3: 前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 4: 真实对数（交付前必做，手动）**

1. 启动后端 + 前端（见 CLAUDE.md 本地启动）。
2. 做表页选 **海运(sea)** → 上传一份真实「其他港」报价 → 等抽取 → 审核台勾选/核对。
3. 点「指定数据下载」→ 上传 `资料/2026.06.08/Sea Net Rate_...(空白　着地あり).xlsx` → 确认下载。
4. 打开下载文件的 `FCL N RATE OF OTHER PORTS` 页，人眼抽样核对 1~2 个目的港：港名/船司/20FT/40 价/附加费(LSS/BAF/CIC/CAF) 是否与报价一致；未在报价里的港是否留名留空；本地杂费列是否留空。
5. 记录「通过 + 证据（截图/对数）」。

- [ ] **Step 5: 无新增改动则跳过提交**（前面各 Task 已分别提交）

---

## 自检（spec 覆盖 / 占位符 / 类型一致）

- **spec 覆盖**：数据来源(当前会话 rows，Task 2 端点读 rows)✓；忠实回填(Task 1 保留 wb/样式)✓；以数据为准动态行(Task 1 `_write_ports`)✓；只留空不报告(空港 1 行/未匹配过滤，无报告)✓；只做 OTHER PORTS(profile)✓；40 取 40HQ(`container_rows[1].freight=[40hq,40gp]`)✓；无数据港留名+1空行(`if not matched`)✓；别名/多名(`_port_candidates`)✓；附加费映射(`_surcharge_cell`)✓；本地杂费留空(从不写 booking/thc/doc/isps/equipment)✓；错误响应 404/400(Task 2)✓；按钮仅 sea(Task 4)✓；三语文案(Task 5)✓；回归+真实对数(Task 6)✓。
- **占位符扫描**：无 TBD/TODO；每个 code step 均为完整可粘贴代码。
- **类型一致**：`refill_into_template(template_bytes, rows, *, profile)->bytes`、`RefillError`、`OTHER_PORTS_PROFILE`、`_scan_ports/_capture_row_styles/_clear_data_area/_group_rows_by_port/_port_candidates/_match_rows/_freight/_surcharge_cell/_apply_style/_write_ports` 在 Task 1 内自洽；端点 import 的 `refill_into_template/RefillError` 与 Task 1 导出名一致；前端 `downloadIntoTemplate(sessionId, template, rows)` 与 Task 4 调用一致；i18n 键 `specifiedDownload/Hint/Pick/Confirm/Done` 与 Task 4 引用一致。
