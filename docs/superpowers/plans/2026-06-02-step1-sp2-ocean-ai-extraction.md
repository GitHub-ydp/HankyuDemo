# SP2 海运 AI 抽取重写 + 结构化附加费 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 step1 做表 sea 路径新建结构化 AI 抽取器，把海运微信图/邮件文本抽成「航线×箱型价 + 结构化附加费列表」多维行，在审核台只读预览（不入库）。

**Architecture:** 镜像 SP1 的 air 抽取链路——新建 `ocean_ai_extractor`（复用 `ai_extract_util`），只改 orchestrator 的 sea 图片/文本两处路由 + `_normalize_sea` 透传新字段；旧 `wechat_image_parser`/`email_text_parser` 不动（仍服务 `ai_parse.py` 旧端点与共享 helper）。前端海运审核台加一个只读「附加费」动态列。

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy（后端）；React 19 + TS + Ant Design v6 + i18next（前端）；pytest（后端测试，前端无单测走 `npm run build` + `lint`）。

**Spec:** `docs/superpowers/specs/2026-06-02-step1-sp2-ocean-ai-extraction-design.md`

**分支:** `feature/step1-sp2-ocean-ai-extraction`（已创建，off main `65133f6`）。**全程在此分支，不碰 main**（Codex 在部署 main）。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py` | 创建 | 海运图片/文本 → 多维行 DTO（箱型价 + `surcharges` 列表）。镜像 `air_ai_extractor`。 |
| `backend/tests/sheet_builder/test_ocean_ai_extractor.py` | 创建 | 抽取器单测（happy + 文本同构 + AI 失败返空）。 |
| `backend/app/services/step1_rates/sheet_builder/orchestrator.py` | 修改 | sea 图片/文本分支改指向 ocean 抽取器；`_normalize_sea` 加 origin/carrier 兜底 + 透传 surcharges/vessel_voyage。 |
| `backend/tests/sheet_builder/test_orchestrator.py` | 修改 | 把旧 `test_sea_image_still_routes_to_wechat_parser` 改成 ocean 路由测试。 |
| `backend/scripts/smoke_ocean_ai_extract.py` | 创建 | 通网机器对 image001/002 真实图跑真 AI，肉眼验。 |
| `frontend/src/pages/RateSheetBuilder.tsx` | 修改 | PreviewRow 加 `surcharges` 类型 + 只读「附加费」动态列 + 格式化。 |
| `frontend/src/i18n/{zh,ja,en}.json` | 修改 | 加 `rateSheet.colSurcharges` 三语。 |

---

## Task 1: ocean_ai_extractor —— 海运图片/文本抽取（箱型价 + 结构化附加费）

**Files:**
- Create: `backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py`
- Test: `backend/tests/sheet_builder/test_ocean_ai_extractor.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/sheet_builder/test_ocean_ai_extractor.py`:

```python
# backend/tests/sheet_builder/test_ocean_ai_extractor.py
import json
from app.services import ai_client
from app.services.step1_rates.sheet_builder import ocean_ai_extractor

# 取自真实样本 资料/2026.05.27/image001(含LSS+EIS到付+转运稍等)/image002(纯运费)
_FAKE = json.dumps([
    {"origin": "SHANGHAI", "destination": "ICD AHMEDABAD", "carrier": "KMTC",
     "via": "NHAVA SHEVA", "container_20gp": 1650, "container_40gp": 1700,
     "currency": "USD", "valid_to": "2026-03-22",
     "surcharges": [
         {"code": "LSS", "included": True},
         {"code": "EIS", "amount_20": 150, "amount_40": 300, "payment": "collect"},
         {"code": "转运费", "note": "稍等"},
     ]},
    {"destination": "NEW YORK", "carrier": "OOCL", "vessel_voyage": "OOCL TULIP/003E",
     "container_40hq": 3150, "currency": "USD", "valid_to": "2026-03-31", "surcharges": []},
    {"destination": "", "container_20gp": 1000},   # 无目的港 → 跳过
    {"destination": "LAX"},                          # 无箱型价 → 跳过
])


def test_parse_ocean_image_builds_rows_with_surcharges(monkeypatch):
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: _FAKE)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)

    assert out["source_type"] == "ocean_image"
    rows = out["parsed_rows"]
    assert len(rows) == 2            # 两条坏行跳过

    r0 = rows[0]
    assert r0["origin"] == "SHANGHAI"
    assert r0["destination"] == "ICD AHMEDABAD"
    assert r0["carrier"] == "KMTC"
    assert r0["via"] == "NHAVA SHEVA"
    assert r0["is_direct"] is False              # 有中转港 → 非直达
    assert r0["container_20gp"] == 1650.0
    assert r0["container_40gp"] == 1700.0
    assert all(isinstance(r0[k], float) for k in ("container_20gp", "container_40gp"))
    sc = r0["surcharges"]
    assert sc[0] == {"code": "LSS", "amount_20": None, "amount_40": None,
                     "currency": None, "payment": None, "included": True, "note": None}
    assert sc[1]["code"] == "EIS" and sc[1]["amount_20"] == 150.0 and sc[1]["amount_40"] == 300.0
    assert sc[1]["payment"] == "collect" and sc[1]["included"] is False
    assert sc[2]["code"] == "转运费" and sc[2]["note"] == "稍等"
    assert r0["needs_review"] is True            # 附加费含 note(转运稍等) → 标黄

    r1 = rows[1]
    assert r1["destination"] == "NEW YORK"
    assert r1["container_40hq"] == 3150.0
    assert r1["vessel_voyage"] == "OOCL TULIP/003E"
    assert r1["surcharges"] == []
    assert r1["is_direct"] is True               # 无中转
    assert r1["needs_review"] is False           # carrier+valid_to 全, 无 note


def test_parse_ocean_text_same_shape(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: _FAKE)
    out = ocean_ai_extractor.parse_ocean_text("一些海运报价文本", db=None)
    assert out["source_type"] == "ocean_text"
    assert len(out["parsed_rows"]) == 2


def test_parse_ocean_image_ai_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)
    assert out["parsed_rows"] == []
    assert any("失败" in w for w in out["warnings"])


def test_missing_carrier_marks_needs_review(monkeypatch):
    fake = json.dumps([{"destination": "BUSAN", "container_20gp": 130, "valid_to": "2026-04-01"}])
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: fake)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)
    assert out["parsed_rows"][0]["needs_review"] is True   # 缺 carrier
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ai_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: ... ocean_ai_extractor`（模块还没建）

- [ ] **Step 3: 实现抽取器**

Create `backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py`:

```python
"""Ocean(海运) 运价表生成：从图片/文本 AI 抽取「航线 × 箱型价 + 结构化附加费」多维行。

与旧 wechat_image_parser/email_text_parser 区别：那两个是固定箱型 schema、把附加费塞进
remarks，且仍服务 ai_parse 旧端点与共享 helper（不动）；这里是做表 sea 路径的新抽取器，
输出结构化箱型价 + surcharges 列表，接 orchestrator._normalize_sea。
图片走 ai_client.chat_with_image，文本走 ai_client.chat，共享 SYSTEM_PROMPT 与行构建。
识别失败不抛——返回空 parsed_rows + warning（沿用既有 parser 风格）。
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import ai_client
from app.services.ai_extract_util import chat_json_with_retry

SYSTEM_PROMPT = """你是海运（集装箱海运）运价识别专家。从图片/文本中精确提取海运运价并输出 JSON 数组。

## 背景
- 起运港（POL）通常是上海 SHANGHAI，除非另有说明。
- 一条报价含：目的港（POD，可为内陆点如 ICD AHMEDABAD）、船司、船名航次、箱型价、附加费。
- 附加费是**不规则自由文本**：可能写「含LSS」（已含运价里）、「EIS 150/300 到付」（按 20'/40' 分额、到付）、「转运费稍等」（金额未定）。

## 输出格式（只输出 JSON 数组，不要其他文字）
[
  {
    "origin": "SHANGHAI",
    "destination": "ICD AHMEDABAD",
    "carrier": "KMTC",
    "vessel_voyage": "OOCL TULIP/003E",
    "via": "NHAVA SHEVA",
    "container_20gp": 1650,
    "container_40gp": 1700,
    "container_40hq": null,
    "container_45": null,
    "currency": "USD",
    "valid_from": "2026-03-22",
    "valid_to": "2026-03-31",
    "transit_days": null,
    "surcharges": [
      {"code": "LSS", "included": true},
      {"code": "EIS", "amount_20": 150, "amount_40": 300, "payment": "collect"},
      {"code": "转运费", "note": "稍等"}
    ],
    "remark": "..."
  }
]

## 规则
1. 每个「目的港 × 船司」组合输出一行；同图多目的港/多船司拆多行，不要合并。
2. 箱型价键 container_20gp/40gp/40hq/45；某箱型无价 → 该键写 null 或不写。
3. 一行至少有一个箱型价才保留；全无 → 不输出该行。
4. 附加费抽进 surcharges 列表，每项必给 code（原样保留，如 EIS/LSS/转运费）；
   金额按箱型分 amount_20/amount_40；「含X」→ included:true 且不写金额；
   「到付/prepaid」→ payment："collect"/"prepaid"；「稍等/议价/未定」→ note 且不要瞎填金额。
5. 有中转港写 via；缺失/不确定一律留空，不要猜。
6. 起运港默认 SHANGHAI；币种默认 USD。数字必须精确。"""


def parse_ocean_image(image_path: str, db: Session | None = None, extra_context: str = "") -> dict[str, Any]:
    """海运图片 → 多维行。db 预留（本棒不解析 Port，入库归 SP3）。"""
    source_file = os.path.basename(image_path)
    user_text = "请从这张海运报价图片中提取所有航线的箱型价与结构化附加费。"
    if extra_context:
        user_text += f"\n\n补充背景：{extra_context}"
    try:
        rates_json = chat_json_with_retry(
            lambda: ai_client.chat_with_image(
                SYSTEM_PROMPT, user_text, image_path,
                temperature=0.0, max_tokens=settings.ai_max_tokens_extract_json,
            ),
            retries=1,
        )
    except Exception as e:  # noqa: BLE001 — 识别失败不抛，交审核台
        return _empty(source_file, "ocean_image", f"AI 图片识别失败: {e}")
    return _result(rates_json, source_file, "ocean_image")


def parse_ocean_text(text: str, db: Session | None = None) -> dict[str, Any]:
    """海运文本/邮件正文 → 多维行。"""
    source_file = "ocean_text_input"
    user_msg = f"请从以下海运报价文本中提取所有航线的箱型价与结构化附加费：\n\n{text}"
    try:
        rates_json = chat_json_with_retry(
            lambda: ai_client.chat(
                SYSTEM_PROMPT, user_msg,
                temperature=0.0, max_tokens=settings.ai_max_tokens_extract_json,
            ),
            retries=1,
        )
    except Exception as e:  # noqa: BLE001
        return _empty(source_file, "ocean_text", f"AI 文本识别失败: {e}")
    return _result(rates_json, source_file, "ocean_text")


def _result(rates_json: Any, source_file: str, source_type: str) -> dict[str, Any]:
    if not isinstance(rates_json, list):
        rates_json = [rates_json]
    rows, warnings = _build_rows(rates_json, source_file, source_type)
    return {
        "parsed_rows": rows,
        "total_rows": len(rows),
        "warnings": warnings,
        "source_type": source_type,
        "file_name": source_file,
    }


def _empty(source_file: str, source_type: str, msg: str) -> dict[str, Any]:
    return {
        "parsed_rows": [], "total_rows": 0, "warnings": [msg],
        "source_type": source_type, "file_name": source_file,
    }


def _build_rows(items: list[Any], source_file: str, source_type: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        dest = str(item.get("destination") or "").strip()
        if not dest:
            warnings.append(f"第{idx + 1}条无目的港，跳过")
            continue
        c20 = _to_price(item.get("container_20gp"))
        c40gp = _to_price(item.get("container_40gp"))
        c40hq = _to_price(item.get("container_40hq"))
        c45 = _to_price(item.get("container_45"))
        if not any((c20, c40gp, c40hq, c45)):
            warnings.append(f"第{idx + 1}条({dest})无箱型价，跳过")
            continue
        surcharges = _norm_surcharges(item.get("surcharges"))
        carrier = (str(item.get("carrier")).strip() or None) if item.get("carrier") else None
        via = (str(item.get("via")).strip() or None) if item.get("via") else None
        valid_to = item.get("valid_to")
        needs_review = bool(
            not carrier
            or not valid_to
            or any(s.get("note") for s in surcharges)
        )
        rows.append({
            "origin": str(item.get("origin") or "SHANGHAI").strip() or "SHANGHAI",
            "destination": dest,
            "carrier": carrier,
            "vessel_voyage": (str(item.get("vessel_voyage")).strip() or None) if item.get("vessel_voyage") else None,
            "via": via,
            "is_direct": via is None,
            "container_20gp": c20,
            "container_40gp": c40gp,
            "container_40hq": c40hq,
            "container_45": c45,
            "currency": str(item.get("currency") or "USD").strip() or "USD",
            "valid_from": item.get("valid_from"),
            "valid_to": valid_to,
            "transit_days": _to_int(item.get("transit_days")),
            "surcharges": surcharges,
            "remark": item.get("remark"),
            "needs_review": needs_review,
            "source_file": source_file,
            "source_type": source_type,
        })
    return rows, warnings


def _norm_surcharges(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        out.append({
            "code": code,
            "amount_20": _to_price(item.get("amount_20")),
            "amount_40": _to_price(item.get("amount_40")),
            "currency": (str(item.get("currency")).strip() or None) if item.get("currency") else None,
            "payment": (str(item.get("payment")).strip() or None) if item.get("payment") else None,
            "included": bool(item.get("included", False)),
            "note": (str(item.get("note")).strip() or None) if item.get("note") else None,
        })
    return out


def _to_price(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_ai_extractor.py -v`
Expected: PASS（4 个测试全绿）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/ocean_ai_extractor.py \
        backend/tests/sheet_builder/test_ocean_ai_extractor.py
git commit -m "feat(step1): 新增 ocean_ai_extractor 海运图片/文本抽取(箱型价+结构化附加费)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: orchestrator —— sea 图片/文本改走 ocean 抽取器 + `_normalize_sea` 透传

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`（import / 第 105-121 行路由 / 第 185-219 行 `_normalize_sea`）
- Modify: `backend/tests/sheet_builder/test_orchestrator.py`（第 590-600 行旧测试改写）

- [ ] **Step 1: 改写旧路由测试 + 加新断言（先让它失败）**

In `backend/tests/sheet_builder/test_orchestrator.py`, 把 `test_sea_image_still_routes_to_wechat_parser`（第 590-600 行）整段替换为：

```python
def test_sea_image_routes_to_ocean_ai_extractor(monkeypatch):
    from app.services.step1_rates.sheet_builder import ocean_ai_extractor
    fake = {
        "parsed_rows": [{
            "origin": "NINGBO", "destination": "ICD AHMEDABAD", "carrier": "KMTC",
            "vessel_voyage": "X/1", "via": "NHAVA SHEVA", "is_direct": False,
            "container_20gp": 1650.0, "container_40gp": 1700.0, "container_40hq": None,
            "container_45": None, "currency": "USD", "valid_from": None, "valid_to": "2026-03-22",
            "transit_days": None,
            "surcharges": [{"code": "EIS", "amount_20": 150.0, "amount_40": 300.0,
                            "currency": None, "payment": "collect", "included": False, "note": None}],
            "remark": None, "needs_review": False,
            "source_file": "ocean.png", "source_type": "ocean_image",
        }],
        "warnings": [], "source_type": "ocean_image", "file_name": "ocean.png",
    }
    monkeypatch.setattr(ocean_ai_extractor, "parse_ocean_image", lambda p, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean.png", "/tmp/ocean.png", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "ocean_image"
    row = s.rows[0]
    assert row["origin"] == "NINGBO"               # _normalize_sea origin 兜底到 row['origin']
    assert row["destination"] == "ICD AHMEDABAD"
    assert row["carrier"] == "KMTC"                # carrier 兜底到 row['carrier']
    assert row["via"] == "NHAVA SHEVA"
    assert row["vessel_voyage"] == "X/1"           # 新透传字段
    assert row["surcharges"][0]["code"] == "EIS"   # 新透传字段
    assert row["currency"] == "USD"


def test_sea_text_routes_to_ocean_ai_extractor(tmp_path, monkeypatch):
    from app.services.step1_rates.sheet_builder import ocean_ai_extractor
    f = tmp_path / "ocean.txt"
    f.write_text("海运报价文本", encoding="utf-8")
    fake = {"parsed_rows": [{"origin": "SHANGHAI", "destination": "BUSAN", "carrier": "KMTC",
            "container_20gp": 130.0, "currency": "USD", "surcharges": []}],
            "warnings": [], "source_type": "ocean_text", "file_name": "ocean.txt"}
    monkeypatch.setattr(ocean_ai_extractor, "parse_ocean_text", lambda text, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean.txt", str(f), db=None)

    assert fr.source_type == "ocean_text"
    assert s.rows[0]["destination"] == "BUSAN"
    assert s.rows[0]["carrier"] == "KMTC"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -k ocean_ai_extractor -v`
Expected: FAIL — sea 图片仍走旧 wechat（`source_type == "wechat_image"`），且 `row["carrier"] == ""`、无 `surcharges`/`vessel_voyage` 键。

- [ ] **Step 3: 改 orchestrator import（第 25-26 行）**

把：
```python
from app.services import rate_parser, wechat_image_parser
from app.services.step1_rates.sheet_builder import air_extractor, air_ai_extractor
```
改为（去掉不再用的 `wechat_image_parser`，加 `ocean_ai_extractor`）：
```python
from app.services import rate_parser
from app.services.step1_rates.sheet_builder import air_extractor, air_ai_extractor, ocean_ai_extractor
```

- [ ] **Step 4: 改 sea 图片分支（第 105-111 行）**

把：
```python
        elif ext in _IMAGE_EXTS:
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_image(file_path, db)
                source_type = "air_image"
            else:
                parsed = wechat_image_parser.parse_wechat_image(file_path, db)
                source_type = "wechat_image"
```
改为：
```python
        elif ext in _IMAGE_EXTS:
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_image(file_path, db)
                source_type = "air_image"
            else:
                parsed = ocean_ai_extractor.parse_ocean_image(file_path, db)
                source_type = "ocean_image"
```

- [ ] **Step 5: 改 sea 文本分支（第 112-121 行）**

把：
```python
        else:  # 文本
            with open(file_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_text(text, db)
                source_type = "air_text"
            else:
                from app.services.email_text_parser import parse_email_text
                parsed = parse_email_text(text, db)
                source_type = "email_text"
```
改为：
```python
        else:  # 文本
            with open(file_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_text(text, db)
                source_type = "air_text"
            else:
                parsed = ocean_ai_extractor.parse_ocean_text(text, db)
                source_type = "ocean_text"
```

- [ ] **Step 6: 改 `_normalize_sea`（第 185-219 行）—— origin/carrier 兜底 + 透传 surcharges/vessel_voyage**

把第 191 行：
```python
        "origin": row.get("origin_port_name") or "SHANGHAI",
```
改为：
```python
        "origin": row.get("origin_port_name") or row.get("origin") or "SHANGHAI",
```
把第 193 行：
```python
        "carrier": row.get("carrier_name") or carrier_fallback,
```
改为：
```python
        "carrier": row.get("carrier_name") or row.get("carrier") or carrier_fallback,
```
在第 206 行 `"source_file": row.get("source_file"),` 之后**新增两行**：
```python
        # ocean AI 抽取新字段（旧 Excel/PDF 行无这些键 → None/[]，不影响）
        "surcharges": row.get("surcharges") or [],
        "vessel_voyage": row.get("vessel_voyage"),
```

- [ ] **Step 7: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -v`
Expected: PASS（含新两个 ocean 路由测试；旧 air 测试不受影响）

- [ ] **Step 8: 跑全 sheet_builder + 全后端回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/ -q && ../.venv/bin/python -m pytest -q`
Expected: PASS；全后端维持「3 failed（`test_ai_client::test_vllm_*`，本机无 vLLM 端点的老基线）+ 其余全绿」。新增/改动测试不引入新失败。

- [ ] **Step 9: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py \
        backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): orchestrator sea 图片/文本改走 ocean_ai_extractor + _normalize_sea 透传 surcharges/vessel_voyage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: smoke_ocean_ai_extract.py —— 真机 AI 实走脚本（手验，无单测）

**Files:**
- Create: `backend/scripts/smoke_ocean_ai_extract.py`

- [ ] **Step 1: 写脚本**

Create `backend/scripts/smoke_ocean_ai_extract.py`:

```python
"""通网机器上对真实海运微信图跑 AI 抽取，肉眼验证结果（含结构化附加费）。

前置：backend/.env 已切百炼 Qwen-VL 且网络可达 dashscope。
用法（在 backend 目录）：
    ../.venv/bin/python scripts/smoke_ocean_ai_extract.py
"""
from app.services.step1_rates.sheet_builder import ocean_ai_extractor

IMAGES = [
    "../资料/2026.05.27/image001.png",   # SHA→ICD Ahmedabad, 含LSS + EIS 150/300 到付 + 转运稍等
    "../资料/2026.05.27/image002.png",   # →NEW YORK, OOCL, USD 3150/40HQ
]

for img in IMAGES:
    print("=" * 70)
    print("图片:", img)
    out = ocean_ai_extractor.parse_ocean_image(img, db=None)
    print("warnings:", out.get("warnings"))
    print(f"抽取 {len(out['parsed_rows'])} 行：")
    for r in out["parsed_rows"]:
        boxes = {k: r.get(k) for k in ("container_20gp", "container_40gp", "container_40hq", "container_45") if r.get(k)}
        scs = " / ".join(
            f"{s['code']}"
            + ("含" if s["included"] else "")
            + (f" {s['amount_20']}/{s['amount_40']}" if (s["amount_20"] or s["amount_40"]) else "")
            + (f" {s['payment']}" if s["payment"] else "")
            + (f" [{s['note']}]" if s["note"] else "")
            for s in r["surcharges"]
        ) or "-"
        print(
            f"  {r['destination']:>16} | {r.get('carrier') or '-':<8} | via {r.get('via') or '-':<12} | "
            f"{boxes} {r['currency']} | 附加费: {scs} | review={r['needs_review']}"
        )
```

- [ ] **Step 2: 本机能 import（不联网也应能跑到打印 warning，不报语法/导入错）**

Run: `cd backend && ../.venv/bin/python -c "import ast; ast.parse(open('scripts/smoke_ocean_ai_extract.py').read()); print('ok')"`
Expected: 打印 `ok`（仅语法检查；真 AI 实走留服务器，本机 dashscope 不可达）。

> ⚠️ 真机验证（不在本机做，列入 Codex 部署验收 / 用户通网机器自测）：在服务器 `backend/` 跑
> `../.venv/bin/python scripts/smoke_ocean_ai_extract.py`，肉眼核对 image001 抽出
> `LSS含 / EIS 150/300 collect / 转运[稍等]`、image002 抽出 `NEW YORK OOCL 3150/40HQ`。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/smoke_ocean_ai_extract.py
git commit -m "chore(step1): ocean AI 抽取实走 smoke 脚本(通网机器对 image001/002 验证)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 前端 —— 海运审核台只读「附加费」动态列 + i18n

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`
- Modify: `frontend/src/i18n/zh.json`、`ja.json`、`en.json`

> 前端无单测；本任务用 `npm run lint` + `npm run build` 验证。

- [ ] **Step 1: PreviewRow 加 surcharges 类型 + SeaSurcharge 接口**

In `RateSheetBuilder.tsx`，在 `interface PreviewRow {` 之前新增接口：

```ts
interface SeaSurcharge {
  code: string;
  amount_20?: number | null;
  amount_40?: number | null;
  currency?: string | null;
  payment?: string | null;
  included?: boolean;
  note?: string | null;
}
```
并在 `PreviewRow` 接口里、`remark?: string | null;`（第 53 行）之前新增一行：
```ts
  surcharges?: SeaSurcharge[];
```

- [ ] **Step 2: 加格式化 helper + 附加费列定义**

In `RateSheetBuilder.tsx`，在 `const seaCols = [`（第 367 行）**之前**新增：

```ts
  // 海运结构化附加费 → 紧凑串：LSS 含 · EIS 150/300 到付 · 转运 稍等
  const fmtSurcharge = (s: SeaSurcharge): string => {
    if (s.included) return `${s.code} 含`;
    if (s.note) return `${s.code} ${s.note}`;
    const amt = [s.amount_20, s.amount_40].filter((v) => v !== null && v !== undefined).join('/');
    const pay = s.payment === 'collect' ? ' 到付' : s.payment === 'prepaid' ? ' 预付' : '';
    return amt ? `${s.code} ${amt}${pay}` : s.code;
  };
  // 任一行有非空 surcharges 数组才显该列（seaHas 对空数组会误判，单独判定）
  const seaHasSurcharges = rows.some((r) => Array.isArray(r.surcharges) && r.surcharges.length > 0);
  const surchargeCol = {
    title: t('rateSheet.colSurcharges'),
    key: 'surcharges',
    width: 220,
    render: (_: unknown, r: PreviewRow) => {
      const list = (r.surcharges ?? []) as SeaSurcharge[];
      if (!list.length) return '';
      const hasTbd = list.some((s) => !!s.note);
      return (
        <span style={hasTbd ? { color: '#d46b08' } : undefined}>
          {list.map(fmtSurcharge).join(' · ')}
        </span>
      );
    },
  };
```

- [ ] **Step 3: 把附加费列插进 seaCols（baf 列之后、transit 之前）**

In `seaCols`，第 382 行 `...(seaHas('baf') ? [numCol(t('rateSheet.colBaf'), 'baf')] : []),` 之后新增一行：
```ts
    ...(seaHasSurcharges ? [surchargeCol] : []),
```

- [ ] **Step 4: i18n 三语加 colSurcharges**

三个文件都在 `"colBaf"` 键（第 45 行）之后新增一行：
- `frontend/src/i18n/zh.json`：`    "colSurcharges": "附加费",`
- `frontend/src/i18n/ja.json`：`    "colSurcharges": "付加料金",`
- `frontend/src/i18n/en.json`：`    "colSurcharges": "Surcharges",`

（注意保持上一行 `"colBaf": "BAF",` 末尾逗号，新行也带逗号——后面还有键。）

- [ ] **Step 5: lint + build 验证**

Run: `cd frontend && npm run lint && npm run build`
Expected: lint 0 error；build 成功产出 `dist/`（无 TS 类型错误，`r.surcharges` 已声明）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "feat(step1): 海运审核台加只读「附加费」动态列(结构化 surcharges)+i18n 三语

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 收尾验证（全部任务后）

- [ ] `cd backend && ../.venv/bin/python -m pytest -q` → 维持「3 vLLM 老基线失败 + 其余全绿」，无新失败。
- [ ] `cd frontend && npm run build` → 通过。
- [ ] `git log --oneline main..HEAD` → 4 个 feat/chore commit，全在 `feature/step1-sp2-ocean-ai-extraction`，main 未被触碰。
- [ ] 真机 AI 实走（smoke_ocean_ai_extract.py）仍未做 —— 列入 Codex 部署验收 / 用户通网机器自测，是本棒唯一未真机验证的一环（同 SP1）。

## 与 SP3/SP4 衔接（不在本棒）

- `surcharges` DTO 结构即 SP3 入库输入契约；SP3 决定落库形态（稀疏 JSON 列 or 独立 `OceanSurcharge` 表）。
- SP4 step2 消费附加费依赖 SP3 入库数据。
