# SP1 Air AI 抽取实走 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 air 做表会话上传的图片/文本走 AI 抽取，产出「重量档 × 泡比 × 货类/包装」结构化多维行，经审核台落库 air_tier。

**Architecture:** 新增 `air_ai_extractor`（图片+文本两入口，共享多维 prompt/schema）+ `ai_extract_util`（稳健 JSON 解析+重试）；orchestrator 按 `template_type` 把图片/文本分流到 air 抽取器；`_normalize_air` 透传新结构化字段；`AirTierRate` 加 4 列 + 迁移；commit/repo/前端列/i18n/.env 跟进。开发期全程 mock AI 做 TDD，真实图片实走验证待通网机器。

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / Alembic / pytest；React 19 / TS / AntD v6 / i18next。AI = 阿里云百炼 Qwen-VL（OpenAI 兼容，走 `ai_client` 的 vllm 路径）。

**关联：** spec `docs/superpowers/specs/2026-06-01-step1-air-ai-extraction-design.md`。分支 `feature/step1-review-desk`。

**运行环境备忘：** 后端命令一律在 `backend/` 目录下用 `../.venv/bin/python`。全后端基线 378 passed（3 个 `test_ai_client` 失败是本机无 vLLM 服务/环境项，与本计划无关）。

---

## File Structure

| 文件 | 责任 | 动作 |
| ---- | ---- | ---- |
| `backend/app/services/ai_extract_util.py` | 模型文本 → JSON 数组的稳健解析 + 一次重试 | 新建 |
| `backend/app/services/step1_rates/sheet_builder/air_ai_extractor.py` | air 图片/文本 → 多维行（复用 util + ai_client） | 新建 |
| `backend/app/services/step1_rates/sheet_builder/orchestrator.py` | 图片/文本按模板分流 + `_normalize_air` 透传新字段 | 改 |
| `backend/app/models/air_tier_rate.py` | air_tier 落地表加 4 列 | 改 |
| `backend/alembic/versions/20260601_0001_air_tier_dims.py` | 迁移：add_column ×4 | 新建 |
| `backend/app/services/step1_rates/sheet_builder/db_writer.py` | `commit_tier_rows` 写新列 + effective_to | 改 |
| `backend/app/services/step2_bidding/rate_repository.py` | `_tier_to_step1_row` extras 带新字段 | 改 |
| `frontend/src/pages/RateSheetBuilder.tsx` | air 加动态列 航司/货类/包装/泡比 | 改 |
| `frontend/src/i18n/{zh,ja,en}.json` | 新增 3 个列名键 | 改 |
| `backend/.env` | 百炼 max_tokens 调大（gitignore，不提交） | 改 |
| `backend/scripts/smoke_air_ai_extract.py` | 通网机器实走 2 张真实微信图 | 新建 |
| 对应 `backend/tests/...` | 各任务 TDD 测试 | 新建/改 |

---

## Task 1: ai_extract_util —— 稳健 JSON 解析 + 重试

**Files:**
- Create: `backend/app/services/ai_extract_util.py`
- Test: `backend/tests/test_ai_extract_util.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_extract_util.py
import pytest
from app.services.ai_extract_util import parse_json_array, chat_json_with_retry, JsonExtractError


def test_parse_plain_array():
    assert parse_json_array('[{"a": 1}]') == [{"a": 1}]

def test_parse_strips_markdown_fence():
    assert parse_json_array("```json\n[{\"a\": 1}]\n```") == [{"a": 1}]

def test_parse_extracts_array_from_prose():
    assert parse_json_array("结果如下：\n[{\"a\": 1}]\n以上。") == [{"a": 1}]

def test_parse_repairs_trailing_comma():
    assert parse_json_array('[{"a": 1},]') == [{"a": 1}]

def test_parse_wraps_single_object():
    assert parse_json_array('{"a": 1}') == [{"a": 1}]

def test_parse_garbage_raises():
    with pytest.raises(JsonExtractError):
        parse_json_array("完全不是 JSON")

def test_retry_succeeds_on_second_attempt():
    calls = iter(["截断的坏响应{", '[{"a": 1}]'])
    assert chat_json_with_retry(lambda: next(calls), retries=1) == [{"a": 1}]

def test_retry_exhausted_raises():
    with pytest.raises(JsonExtractError):
        chat_json_with_retry(lambda: "坏", retries=1)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/test_ai_extract_util.py -q`
Expected: FAIL（`ModuleNotFoundError: app.services.ai_extract_util`）

- [ ] **Step 3: 写实现**

```python
# backend/app/services/ai_extract_util.py
"""AI 抽取通用工具：把模型返回文本稳健解析成 JSON 数组。

模型常在 JSON 外包 markdown 代码块、前后带说明文字，或因 max_tokens 截断留下尾逗号/
不完整结构。这里集中：去壳 → 抓首个 [..] → 尽力修复尾逗号 → json.loads。air(SP1)/ocean(SP2) 共用。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


class JsonExtractError(ValueError):
    """文本无法解析为 JSON 数组。"""


def parse_json_array(raw: str | None) -> list[Any]:
    """从模型文本解析 JSON 数组；失败抛 JsonExtractError。单对象自动包成单元素数组。"""
    if not raw:
        raise JsonExtractError("空响应")
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    for candidate in (text, _TRAILING_COMMA.sub(r"\1", text)):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            continue
    raise JsonExtractError(f"无法解析为 JSON 数组: {raw[:200]}")


def chat_json_with_retry(call: Callable[[], str], *, retries: int = 1) -> list[Any]:
    """调 call() 取模型文本并解析；仅在「解析失败」时按 retries 重试（provider 异常不在此吞）。"""
    last: Exception | None = None
    for _ in range(retries + 1):
        raw = call()
        try:
            return parse_json_array(raw)
        except JsonExtractError as e:
            last = e
    raise last if last else JsonExtractError("无响应")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/test_ai_extract_util.py -q`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/ai_extract_util.py backend/tests/test_ai_extract_util.py
git commit -m "feat(step1): 新增 ai_extract_util 稳健 JSON 解析+重试(air/ocean 共用)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: air_ai_extractor —— air 图片/文本多维抽取

**Files:**
- Create: `backend/app/services/step1_rates/sheet_builder/air_ai_extractor.py`
- Test: `backend/tests/sheet_builder/test_air_ai_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/sheet_builder/test_air_ai_extractor.py
import json
from app.services import ai_client
from app.services.step1_rates.sheet_builder import air_ai_extractor

_FAKE = json.dumps([
    {"origin": "PVG", "destination": "LAX", "carrier": "CK/CA/KE",
     "cargo_class": "普货", "packing": "托", "density": "1:167",
     "tier_prices": {"45": 60, "100": 60, "500": 60, "1000": 60},
     "currency": "CNY", "effective_from": "2026-05-26", "effective_to": "2026-05-29",
     "remark": "全程2-4天"},
    {"origin": "PVG", "destination": "LAX", "carrier": "CK/CA/KE",
     "cargo_class": "普货", "packing": "托", "density": "1:1000",
     "tier_prices": {"100": 36}, "currency": "CNY"},
    {"destination": "", "tier_prices": {"100": 50}},   # 无目的港 → 跳过
    {"destination": "ORD", "tier_prices": {}},          # 无档位价 → 跳过
])


def test_parse_air_image_builds_multidim_rows(monkeypatch):
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: _FAKE)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)

    assert out["source_type"] == "air_image"
    rows = out["parsed_rows"]
    assert len(rows) == 2          # 两条坏行被跳过
    r0 = rows[0]
    assert r0["destination"] == "LAX"
    assert r0["carrier"] == "CK/CA/KE"
    assert r0["cargo_class"] == "普货"
    assert r0["packing"] == "托"
    assert r0["density"] == "1:167"
    assert r0["tier_prices"] == {45: 60.0, 100: 60.0, 500: 60.0, 1000: 60.0}
    assert all(isinstance(v, float) for v in r0["tier_prices"].values())
    assert r0["currency"] == "CNY"
    assert r0["origin"] == "PVG"
    assert r0["effective_week_start"] == "2026-05-26"
    assert r0["effective_to"] == "2026-05-29"
    assert r0["multi_flight_pick"] is True
    assert rows[1]["density"] == "1:1000" and rows[1]["tier_prices"] == {100: 36.0}


def test_parse_air_text_same_shape(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: _FAKE)
    out = air_ai_extractor.parse_air_text("一些空运报价文本", db=None)
    assert out["source_type"] == "air_text"
    assert len(out["parsed_rows"]) == 2


def test_parse_air_image_ai_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)
    assert out["parsed_rows"] == []
    assert any("失败" in w for w in out["warnings"])


def test_default_currency_japan_origin(monkeypatch):
    fake = json.dumps([{"origin": "NRT", "destination": "PVG", "tier_prices": {"100": 500}}])
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: fake)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)
    assert out["parsed_rows"][0]["currency"] == "JPY"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_air_ai_extractor.py -q`
Expected: FAIL（`ModuleNotFoundError: ...air_ai_extractor`）

- [ ] **Step 3: 写实现**

```python
# backend/app/services/step1_rates/sheet_builder/air_ai_extractor.py
"""Air 运价表生成：从图片/文本元料金 AI 抽取「重量档 × 泡比 × 货类/包装」多维行。

与海运的 wechat_image_parser/email_text_parser 区别：那两个是海运箱型 schema；air 元料金
（微信图/邮件）是多维空运价，输出结构化多维行 + 稀疏重量档 tier_prices，接 orchestrator._normalize_air。
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

SYSTEM_PROMPT = """你是空运（航空货运）运价识别专家。从图片/文本中精确提取**多维**空运运价并输出 JSON 数组。

## 背景
- 起运港通常是上海 PVG（表头常写「PVG始发」），除非另有说明。
- 空运价按多个维度拆分：
  - 目的港（IATA 三字码，如 LAX/ORD/AMS/NRT）
  - 航司代码（如 CK/CA/KE/KZ；多个用 / 连接，原样保留）
  - 货类（普货 / 快件 / 9610-9710 等）
  - 包装种类（托 / 散 / 托散 / 混装）
  - 货型即泡比（如 1:100、1:167、1:1000）
  - 重量档（表头如 45K / 100KG+ / 500KG+ / 1000KG+），每档一个单价

## 输出格式（只输出 JSON 数组，不要其他文字）
[
  {
    "origin": "PVG",
    "destination": "LAX",
    "carrier": "CK/CA/D0/5Y/KE",
    "cargo_class": "普货",
    "packing": "托",
    "density": "1:167",
    "tier_prices": {"45": 60, "100": 60, "500": 60, "1000": 60},
    "currency": "CNY",
    "effective_from": "2026-05-26",
    "effective_to": "2026-05-29",
    "remark": "全程2-4天"
  }
]

## 规则
1. 每个「目的港 × 航司 × 货类 × 包装 × 泡比」组合输出一行；价随泡比变就分多行，不要合并。
2. tier_prices 的键是重量档数字（去掉 K/KG/+ 单位），值是该档单价；某档为「/」「议价」「单询」或空 → 不写该档。
3. 一行只要任一重量档有数字就保留；全空则不输出该行。
4. 起运港默认 PVG；币种默认人民币 CNY（日本段如 NRT 为 JPY）。
5. 含油/全程时效/操作代码等说明写进 remark。
6. 数字必须精确，不要猜测。"""


def parse_air_image(image_path: str, db: Session | None = None, extra_context: str = "") -> dict[str, Any]:
    """air 图片 → 多维行。db 预留（air 用 IATA 码不解析 Port）。"""
    source_file = os.path.basename(image_path)
    user_text = "请从这张空运报价图片中提取所有航线的多维运价（重量档×泡比×货类/包装）。"
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
        return _empty(source_file, "air_image", f"AI 图片识别失败: {e}")
    return _result(rates_json, source_file, "air_image")


def parse_air_text(text: str, db: Session | None = None) -> dict[str, Any]:
    """air 文本/邮件正文 → 多维行。"""
    source_file = "air_text_input"
    user_msg = f"请从以下空运报价文本中提取所有航线的多维运价：\n\n{text}"
    try:
        rates_json = chat_json_with_retry(
            lambda: ai_client.chat(
                SYSTEM_PROMPT, user_msg,
                temperature=0.0, max_tokens=settings.ai_max_tokens_extract_json,
            ),
            retries=1,
        )
    except Exception as e:  # noqa: BLE001
        return _empty(source_file, "air_text", f"AI 文本识别失败: {e}")
    return _result(rates_json, source_file, "air_text")


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
        tiers = _norm_tier_prices(item.get("tier_prices") or {})
        dest = str(item.get("destination") or "").strip()
        if not dest:
            warnings.append(f"第{idx + 1}条无目的港，跳过")
            continue
        if not tiers:
            warnings.append(f"第{idx + 1}条({dest})无有效档位价，跳过")
            continue
        origin = str(item.get("origin") or "PVG").strip() or "PVG"
        currency = str(item.get("currency") or _default_currency(origin)).strip()
        rows.append({
            "origin": origin,
            "destination": dest,
            "carrier": item.get("carrier"),
            "cargo_class": item.get("cargo_class"),
            "packing": item.get("packing"),
            "density": item.get("density"),
            "tier_prices": tiers,
            "currency": currency,
            "effective_week_start": item.get("effective_from"),
            "effective_to": item.get("effective_to"),
            "remark": item.get("remark"),
            "multi_flight_pick": True,
            "source_file": source_file,
            "source_type": source_type,
        })
    return rows, warnings


def _norm_tier_prices(tp: dict[Any, Any]) -> dict[int, float]:
    out: dict[int, float] = {}
    for kg, price in (tp or {}).items():
        try:
            k, v = int(kg), float(price)
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[k] = v
    return out


def _default_currency(origin: str) -> str:
    return "JPY" if (origin or "").upper() in {"NRT", "HND", "KIX", "TYO"} else "CNY"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_air_ai_extractor.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/air_ai_extractor.py backend/tests/sheet_builder/test_air_ai_extractor.py
git commit -m "feat(step1): 新增 air_ai_extractor 图片/文本多维抽取(重量档×泡比×货类/包装)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: orchestrator 路由分流 + _normalize_air 透传新字段

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py`（import 行 25-26；add_file 图片/文本分支 105-114；`_normalize_air` 244-279）
- Test: `backend/tests/sheet_builder/test_orchestrator.py`（追加）

- [ ] **Step 1: 写失败测试（追加到文件末尾）**

```python
# 追加到 backend/tests/sheet_builder/test_orchestrator.py 末尾

def test_air_image_routes_to_air_ai_extractor(monkeypatch):
    from app.services.step1_rates.sheet_builder import air_ai_extractor
    fake = {"parsed_rows": [{
        "origin": "PVG", "destination": "LAX", "carrier": "CK/CA",
        "cargo_class": "普货", "packing": "托", "density": "1:167",
        "tier_prices": {45: 60.0, 100: 60.0}, "currency": "CNY",
        "effective_week_start": "2026-05-26", "effective_to": "2026-05-29",
        "multi_flight_pick": True,
    }], "warnings": [], "source_type": "air_image"}
    monkeypatch.setattr(air_ai_extractor, "parse_air_image", lambda p, db: fake)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "air.png", "/tmp/air.png", db=None)

    assert fr.status == "parsed"
    assert fr.source_type == "air_image"
    row = s.rows[0]
    assert row["destination"] == "LAX"
    assert row["carrier"] == "CK/CA"
    assert row["cargo_class"] == "普货"
    assert row["packing"] == "托"
    assert row["density"] == "1:167"
    assert row["currency"] == "CNY"
    assert row["effective_to"] == "2026-05-29"
    assert row["tier_prices"] == {45: 60.0, 100: 60.0}
    assert row["needs_review_by_destination"] is True


def test_sea_image_still_routes_to_wechat_parser(monkeypatch):
    from app.services import wechat_image_parser
    fake = {"parsed_rows": [{"destination_port_name": "BUSAN", "carrier_name": "KMTC",
            "container_20gp": 130}], "carrier_code": "KMTC", "warnings": []}
    monkeypatch.setattr(wechat_image_parser, "parse_wechat_image", lambda p, db: fake)

    s = orchestrator.create_session("sea")
    fr = orchestrator.add_file(s.session_id, "ocean.png", "/tmp/ocean.png", db=None)

    assert fr.source_type == "wechat_image"
    assert s.rows[0]["destination"] == "BUSAN"


def test_air_text_routes_to_air_ai_extractor(tmp_path, monkeypatch):
    from app.services.step1_rates.sheet_builder import air_ai_extractor
    f = tmp_path / "air.txt"
    f.write_text("空运报价文本", encoding="utf-8")
    fake = {"parsed_rows": [{"origin": "PVG", "destination": "AMS",
            "tier_prices": {100: 40.0}, "currency": "CNY", "multi_flight_pick": True}],
            "warnings": [], "source_type": "air_text"}
    monkeypatch.setattr(air_ai_extractor, "parse_air_text", lambda text, db: fake)

    s = orchestrator.create_session("air")
    fr = orchestrator.add_file(s.session_id, "air.txt", str(f), db=None)

    assert fr.source_type == "air_text"
    assert s.rows[0]["destination"] == "AMS"


def test_normalize_air_carries_multidim_fields():
    from app.services.step1_rates.sheet_builder.orchestrator import _normalize_air
    row = {
        "origin": "PVG", "destination": "LAX", "carrier": "CK/CA",
        "cargo_class": "普货", "packing": "托", "density": "1:167",
        "tier_prices": {45: 60.0}, "currency": "CNY",
        "effective_week_start": "2026-05-26", "effective_to": "2026-05-29",
        "multi_flight_pick": True,
    }
    out = _normalize_air(row, "")
    assert out["origin"] == "PVG"
    assert out["carrier"] == "CK/CA"
    assert out["cargo_class"] == "普货"
    assert out["packing"] == "托"
    assert out["density"] == "1:167"
    assert out["currency"] == "CNY"
    assert out["effective_to"] == "2026-05-29"
    assert out["tier_prices"] == {45: 60.0}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -q -k "air_image or sea_image or air_text or normalize_air_carries"`
Expected: FAIL（air 图片仍走 wechat / `_normalize_air` 无 carrier 等键）

- [ ] **Step 3a: 改 import（orchestrator.py 行 25-26）**

把
```python
from app.services import rate_parser, wechat_image_parser
from app.services.step1_rates.sheet_builder import air_extractor
```
改为
```python
from app.services import rate_parser, wechat_image_parser
from app.services.step1_rates.sheet_builder import air_extractor, air_ai_extractor
```

- [ ] **Step 3b: 改 add_file 图片/文本分支（orchestrator.py 行 105-114）**

把
```python
        elif ext in _IMAGE_EXTS:
            parsed = wechat_image_parser.parse_wechat_image(file_path, db)
            source_type = "wechat_image"
        else:  # 文本
            from app.services.email_text_parser import parse_email_text

            with open(file_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            parsed = parse_email_text(text, db)
            source_type = "email_text"
```
改为
```python
        elif ext in _IMAGE_EXTS:
            if session.template_type == "air":
                parsed = air_ai_extractor.parse_air_image(file_path, db)
                source_type = "air_image"
            else:
                parsed = wechat_image_parser.parse_wechat_image(file_path, db)
                source_type = "wechat_image"
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

- [ ] **Step 3c: 改 _normalize_air（orchestrator.py 行 244-279 整体替换）**

```python
def _normalize_air(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    """air_extractor/air_ai_extractor 产多形态，映射到模板字段：
      - 周表源(Market Price)：price_dayN → day1..day7；
      - 档位源(EES/唯凯/air 图片/文本)：tier_prices(稀疏 KG→价)原样透传(值转 float)。
    air 图片/文本另带结构化多维字段(carrier/cargo_class/packing/density/currency/effective_to)，
    EES/周表行无这些键 → None，不影响。Decimal 转 float 便于写表与 JSON。
    """
    normalized: dict[str, Any] = {
        # 起运港：air 图片行带 origin；否则默认上海 PVG。
        "origin": row.get("origin_port_name") or row.get("origin") or "PVG",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "service": (
            row.get("service_desc")
            or row.get("airline_code")
            or row.get("service_code")
            or row.get("service")
            or carrier_fallback
        ),
        # 结构化多维字段(air 图片/文本)；EES/周表行无 → None。
        "carrier": row.get("carrier"),
        "cargo_class": row.get("cargo_class"),
        "packing": row.get("packing"),
        "density": row.get("density"),
        "currency": row.get("currency"),
        "remark": row.get("remarks") or row.get("remark"),
        "source_file": row.get("source_file"),
        "effective_week_start": _to_week_str(row.get("effective_week_start")),
        "effective_to": _to_week_str(row.get("effective_to")),
        "needs_review_by_destination": bool(row.get("multi_flight_pick")),
    }
    tier_prices = row.get("tier_prices")
    if tier_prices:
        normalized["tier_prices"] = {
            int(kg): float(price)
            for kg, price in tier_prices.items()
            if price is not None
        }
    else:
        for day in range(1, 8):
            normalized[f"day{day}"] = _to_number(row.get(f"price_day{day}"))
    return normalized
```

- [ ] **Step 3d: 修 `_review_key` 的 sea/air 判别（orchestrator.py 行 298-314 内）**

Step 3c 给 air 行新增了 `carrier` 键，而 `_review_key` 原用 `if "carrier" in row`（键存在性）区分 sea/air 聚合分支——air 行现在也带 carrier 键，会被误判进 sea 分支，使同目的港不同 service 的 air 周报行被误标 needs_review（打破既有测试 `test_air_same_dest_different_service_not_marked_review`）。改用 air 专属的 `"service"` 键判别（air 行由 `_normalize_air` 恒设 service，即使空串；sea 行从不设 service）。

把
```python
    if "carrier" in row:
        return (
            row.get("origin"),
            row.get("destination"),
            row.get("carrier"),
            row.get("via"),
            row.get("commodity"),
            row.get("valid_from"),
        )
    return (row.get("destination"), row.get("service"))
```
改为
```python
    # air 行有 "service" 键(由 _normalize_air 恒设, 即使空串); sea 行从不设 → 用它区分聚合分支。
    # 不能再用 "carrier" in row 判别——air 行现也带 carrier 键(会误判进 sea 分支)。
    if "service" in row:
        return (row.get("destination"), row.get("service"))
    return (
        row.get("origin"),
        row.get("destination"),
        row.get("carrier"),
        row.get("via"),
        row.get("commodity"),
        row.get("valid_from"),
    )
```

注：hand-built 的 coded-row（带 carrier 但无 service 键）仍落入 sea 分支，行为与原来一致；air 周报/图片行（有 service 键）落 air 分支。

- [ ] **Step 4: 跑测试确认通过（含回归既有 orchestrator 测试）**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -q`
Expected: PASS（既有全部 + 新增 4 条）。其中 `test_air_same_dest_different_service_not_marked_review` 因 Step 3d 修复保持 PASS（若漏做 3d 它会 FAIL）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): orchestrator 按模板把图片/文本分流到 air 抽取器 + _normalize_air 透传多维字段

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: AirTierRate 加 4 列 + alembic 迁移

**Files:**
- Modify: `backend/app/models/air_tier_rate.py`（在 currency/remark 后加列）
- Create: `backend/alembic/versions/20260601_0001_air_tier_dims.py`
- Test: `backend/tests/sheet_builder/test_db_writer.py`（追加列存在性断言）

- [ ] **Step 1: 写失败测试（追加到 test_db_writer.py 末尾）**

```python
def test_air_tier_rate_has_multidim_columns():
    from app.models.air_tier_rate import AirTierRate
    cols = set(AirTierRate.__table__.columns.keys())
    assert {"cargo_class", "packing", "density", "carrier"} <= cols
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_db_writer.py::test_air_tier_rate_has_multidim_columns -q`
Expected: FAIL（AssertionError，列不存在）

- [ ] **Step 3a: 加模型列（air_tier_rate.py，在 `remark` 行之后、`batch_id` 行之前插入）**

```python
    cargo_class: Mapped[str | None] = mapped_column(String(20), comment="货类(普货/快件/9610-9710)")
    packing: Mapped[str | None] = mapped_column(String(20), comment="包装(托/散/托散/混装)")
    density: Mapped[str | None] = mapped_column(String(20), comment="泡比(如1:167)")
    carrier: Mapped[str | None] = mapped_column(String(100), comment="航司代码")
```

- [ ] **Step 3b: 新建迁移文件**

```python
# backend/alembic/versions/20260601_0001_air_tier_dims.py
"""air_tier_rates 增加多维字段(货类/包装/泡比/航司)

Revision ID: 20260601_0001
Revises: 20260528_0001
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0001"
down_revision: Union[str, None] = "20260528_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("air_tier_rates", sa.Column("cargo_class", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("packing", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("density", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("carrier", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("air_tier_rates", "carrier")
    op.drop_column("air_tier_rates", "density")
    op.drop_column("air_tier_rates", "packing")
    op.drop_column("air_tier_rates", "cargo_class")
```

- [ ] **Step 4: 跑测试确认通过 + 迁移链体检**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_db_writer.py -q`
Expected: PASS（列存在 + 既有 commit 测试仍绿，因 create_all 自动建新列）

Run: `../.venv/bin/python -m alembic heads`
Expected: 输出含 `20260601_0001 (head)`，且无多 head 报错

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/air_tier_rate.py backend/alembic/versions/20260601_0001_air_tier_dims.py backend/tests/sheet_builder/test_db_writer.py
git commit -m "feat(step1): AirTierRate 增 cargo_class/packing/density/carrier 四列 + alembic 迁移

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: commit_tier_rows 写新列 + effective_to

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/db_writer.py`（`commit_tier_rows` 的 `AirTierRate(...)` 块，行 78-90）
- Test: `backend/tests/sheet_builder/test_db_writer.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 test_db_writer.py 末尾）**

```python
def test_commit_persists_multidim_fields(db_session):
    row = _tier_row(
        "LAX", {"45": 60, "100": 60},
        cargo_class="普货", packing="托", density="1:167",
        carrier="CK/CA", currency="CNY", effective_to="2026-05-29",
    )
    res = db_writer.commit_tier_rows([row], db_session)
    assert res.tier_rows == 1

    rate = db_session.execute(select(AirTierRate)).scalars().one()
    assert rate.cargo_class == "普货"
    assert rate.packing == "托"
    assert rate.density == "1:167"
    assert rate.carrier == "CK/CA"
    assert rate.currency == "CNY"
    assert rate.effective_to == date(2026, 5, 29)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_db_writer.py::test_commit_persists_multidim_fields -q`
Expected: FAIL（`TypeError: ... unexpected keyword 'cargo_class'` 不会发生——是 AttributeError/None，因 commit 没传这些列 → rate.cargo_class is None）

- [ ] **Step 3: 改 commit_tier_rows 的 AirTierRate(...) 块**

把
```python
        db.add(
            AirTierRate(
                origin=r.get("origin") or "PVG",
                destination=r.get("destination") or "",
                service_desc=r.get("service"),
                tier_prices=_norm_tiers(r["tier_prices"]),
                effective_from=_to_date(r.get("effective_week_start")),
                currency=r.get("currency") or "CNY",
                remark=r.get("remark"),
                batch_id=batch_uuid,
            )
        )
```
改为
```python
        db.add(
            AirTierRate(
                origin=r.get("origin") or "PVG",
                destination=r.get("destination") or "",
                service_desc=r.get("service"),
                tier_prices=_norm_tiers(r["tier_prices"]),
                effective_from=_to_date(r.get("effective_week_start")),
                effective_to=_to_date(r.get("effective_to")),
                currency=r.get("currency") or "CNY",
                remark=r.get("remark"),
                cargo_class=r.get("cargo_class"),
                packing=r.get("packing"),
                density=r.get("density"),
                carrier=r.get("carrier"),
                batch_id=batch_uuid,
            )
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_db_writer.py -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/db_writer.py backend/tests/sheet_builder/test_db_writer.py
git commit -m "feat(step1): commit_tier_rows 写入多维字段(货类/包装/泡比/航司)+effective_to

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: query_air_tier extras 带新字段（step2 不破）

**Files:**
- Modify: `backend/app/services/step2_bidding/rate_repository.py`（`_tier_to_step1_row` 的 extras，行 245-251）
- Test: `backend/tests/step2_bidding/test_repo_tier_multidim.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/step2_bidding/test_repo_tier_multidim.py
"""query_air_tier：同港多泡比多行不崩 + extras 带结构化多维字段(SP4 用)。"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.base import Base
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed(db):
    bid = uuid.uuid4()
    db.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.air_tier,
                       status=ImportBatchStatus.active, row_count=2))
    db.add(AirTierRate(origin="PVG", destination="LAX", tier_prices={"45": 60, "100": 60},
                       currency="CNY", cargo_class="普货", packing="托", density="1:167",
                       carrier="CK/CA", batch_id=bid))
    db.add(AirTierRate(origin="PVG", destination="LAX", tier_prices={"100": 36},
                       currency="CNY", cargo_class="普货", packing="托", density="1:1000",
                       carrier="CK/CA", batch_id=bid))
    db.commit()


def test_query_air_tier_returns_multidim_rows(db_session):
    _seed(db_session)
    rows = Step1RateRepository(db_session).query_air_tier(origin="PVG", destination="LAX")

    assert len(rows) == 2, "同港多泡比应都返回，不崩"
    densities = {r.extras.get("density") for r in rows}
    assert densities == {"1:167", "1:1000"}
    r0 = next(r for r in rows if r.extras["density"] == "1:167")
    assert r0.extras["cargo_class"] == "普货"
    assert r0.extras["packing"] == "托"
    assert r0.extras["carrier"] == "CK/CA"
    assert r0.extras["tier_prices"] == {45: 60, 100: 60}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/step2_bidding/test_repo_tier_multidim.py -q`
Expected: FAIL（`KeyError: 'density'` —— extras 没带新字段）

- [ ] **Step 3: 改 _tier_to_step1_row 的 extras（rate_repository.py 行 245-251）**

把
```python
            extras={
                "tier_prices": tiers,
                "step2_record_id": rate.id,
                "step2_batch_status": batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status),
            },
```
改为
```python
            extras={
                "tier_prices": tiers,
                "cargo_class": rate.cargo_class,
                "packing": rate.packing,
                "density": rate.density,
                "carrier": rate.carrier,
                "step2_record_id": rate.id,
                "step2_batch_status": batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status),
            },
```

- [ ] **Step 4: 跑测试确认通过 + step2 回归**

Run: `../.venv/bin/python -m pytest tests/step2_bidding -q`
Expected: PASS（新测试 + 既有 step2 全绿）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step2_bidding/rate_repository.py backend/tests/step2_bidding/test_repo_tier_multidim.py
git commit -m "feat(step2): query_air_tier extras 带多维字段(泡比/货类/包装/航司, SP4 选价用); 多行不破

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: 前端 air 审核台动态列（航司/货类/包装/泡比）+ i18n

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`（`PreviewRow` 接口 行 17-49；`airCols` 行 387-395）
- Modify: `frontend/src/i18n/zh.json`、`ja.json`、`en.json`（rateSheet 块，`colService` 行 47 附近）

说明：复用现有泛型动态列判定函数 `seaHas(field)`（行 302，按「全表至少一行该字段非空」决定是否渲染列），air 列直接调用它即可——EES/周报行无这些字段 → 列自动隐藏。

- [ ] **Step 1: PreviewRow 接口加字段（行 17-49 内，`carrier?` 已存在，补三个）**

在 `interface PreviewRow { ... }` 内（`service?: string;` 附近）加：
```typescript
  cargo_class?: string | null;
  packing?: string | null;
  density?: string | null;
```

- [ ] **Step 2: airCols 加动态列（行 387-395 整体替换）**

把
```typescript
  const airCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colService'), 'service'),
    // 档位模式 → 动态 KG 列；否则 day1-7 周表列(Market Price 周报)。
    ...(tierColumns.length > 0 ? tierColumns.map((kg) => tierCol(kg)) : airDayCols),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
```
改为
```typescript
  const airCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination'),
    // air 图片/文本多维列：该字段全表至少一行有值才显(seaHas 是泛型判定)；EES/周报行无 → 隐藏。
    ...(seaHas('carrier') ? [textCol(t('rateSheet.colCarrier'), 'carrier')] : []),
    ...(seaHas('cargo_class') ? [textCol(t('rateSheet.colCargoClass'), 'cargo_class')] : []),
    ...(seaHas('packing') ? [textCol(t('rateSheet.colPacking'), 'packing')] : []),
    ...(seaHas('density') ? [textCol(t('rateSheet.colDensity'), 'density')] : []),
    textCol(t('rateSheet.colService'), 'service'),
    // 档位模式 → 动态 KG 列；否则 day1-7 周表列(Market Price 周报)。
    ...(tierColumns.length > 0 ? tierColumns.map((kg) => tierCol(kg)) : airDayCols),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
```

- [ ] **Step 3: i18n 三语加键（每个文件的 rateSheet 块，`"colService": ...` 之后插入）**

`frontend/src/i18n/zh.json`：
```json
    "colCargoClass": "货类",
    "colPacking": "包装",
    "colDensity": "泡比",
```
`frontend/src/i18n/ja.json`：
```json
    "colCargoClass": "貨種",
    "colPacking": "梱包",
    "colDensity": "容積比",
```
`frontend/src/i18n/en.json`：
```json
    "colCargoClass": "Cargo type",
    "colPacking": "Packing",
    "colDensity": "Density ratio",
```

- [ ] **Step 4: 构建校验**

Run: `cd frontend && npm run build`
Expected: tsc + vite build 成功，无 TS 报错（`cd` 回根目录后继续）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "feat(step1): air 审核台加动态列 航司/货类/包装/泡比 + i18n 三语

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: .env 百炼 max_tokens 调大（本地配置，不提交）

**Files:**
- Modify: `backend/.env`（gitignore，不进 git）

- [ ] **Step 1: 改两行**

把
```
AI_MAX_TOKENS_EXTRACT_JSON=1024
AI_MAX_TOKENS_CAP=1536
```
改为
```
AI_MAX_TOKENS_EXTRACT_JSON=4096
AI_MAX_TOKENS_CAP=8192
```
（说明：parser 用 `settings.ai_max_tokens_extract_json` 作 max_tokens，ai_client 用 `get_ai_config().ai_max_tokens_cap` 钳制；DB 这两项为 NULL → 全走 .env。`app/core/config.py` 默认值**不动**——上线回 vLLM 小模型时仍由保守默认兜底。)

- [ ] **Step 2: 校验生效（不依赖网络）**

Run: `../.venv/bin/python -c "from app.services.config_service import get_ai_config as g; c=g(); print(c.ai_max_tokens_extract_json, c.ai_max_tokens_cap)"`
Expected: `4096 8192`

- [ ] **Step 3: 不提交**（`.env` 已 gitignore；`git status` 不应出现它）

---

## Task 9: 全量回归 + 实走 smoke 脚本

**Files:**
- Create: `backend/scripts/smoke_air_ai_extract.py`

- [ ] **Step 1: 后端全量回归**

Run: `../.venv/bin/python -m pytest -q`
Expected: 之前基线 378 passed + 本计划新增（util 8 + air_ai 4 + orchestrator 4 + db_writer 2 + repo 1 = 19）≈ 397 passed；仍仅 3 个 `test_ai_client` 因本机无 vLLM 失败（无关）。

- [ ] **Step 2: 前端构建回归**

Run: `cd frontend && npm run build`
Expected: 成功（回根目录继续）

- [ ] **Step 3: 写实走 smoke 脚本**

```python
# backend/scripts/smoke_air_ai_extract.py
"""通网机器上对真实 air 微信图跑 AI 抽取，肉眼验证结果。

前置：backend/.env 已切百炼 Qwen-VL 且网络可达 dashscope。
用法（在 backend 目录）：
    ../.venv/bin/python scripts/smoke_air_ai_extract.py
"""
from app.services.step1_rates.sheet_builder import air_ai_extractor

IMAGES = [
    "../资料/2026.05.27/air/Weixin Image_20260527150724_2133_110.png",
    "../资料/2026.05.27/air/Weixin Image_20260527151753_2134_110.png",
]

for img in IMAGES:
    print("=" * 70)
    print("图片:", img)
    out = air_ai_extractor.parse_air_image(img, db=None)
    print("warnings:", out.get("warnings"))
    print(f"抽取 {len(out['parsed_rows'])} 行（前 20）：")
    for r in out["parsed_rows"][:20]:
        print(
            f"  {r['destination']:>5} | {r.get('carrier') or '-':<14} | "
            f"{r.get('cargo_class') or '-'}/{r.get('packing') or '-'}/{r.get('density') or '-'} | "
            f"{r['tier_prices']} {r['currency']}"
        )
```

- [ ] **Step 4: 提交 smoke 脚本**

```bash
git add backend/scripts/smoke_air_ai_extract.py
git commit -m "chore(step1): air AI 抽取实走 smoke 脚本(通网机器对 2 张真实微信图验证)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: 交付说明（给用户）**

告知用户：本计划开发期全程 mock AI，逻辑已 TDD 全绿；**实走验证**请在网络可达 dashscope 的机器上、`backend/` 目录跑 `../.venv/bin/python scripts/smoke_air_ai_extract.py`，肉眼核对 LAX 等多泡比行 + 档位价是否与原图一致；再走前端 air 做表 → 审核台（看新列）→ 确认入库 → 仪表盘计数。

---

## 自检（写完计划后对照 spec）

- **覆盖**：spec §4 组件逐项有任务 —— air_ai_extractor(T2)/ai_extract_util(T1)/orchestrator 路由+normalize(T3)/AirTierRate+迁移(T4)/commit_tier_rows(T5)/query_air_tier(T6)/前端列+i18n(T7)/.env(T8)；§7 测试分散各任务 + T9 回归；§6 健壮性 = T1 稳健 JSON + T2 失败兜底 + T8 max_tokens。✅
- **类型一致**：行 schema 字段名 `cargo_class/packing/density/carrier/tier_prices/currency/effective_week_start/effective_to/multi_flight_pick` 在 T2 产出、T3 归一、T5 入库、T6 extras、T7 前端列**全程同名**。✅
- **占位符**：无 TBD；每个代码步给完整代码与精确命令。✅
- **顺序依赖**：T1→T2(用 util)→T3(用 extractor)→T4(列)→T5(写列,依赖 T4)→T6(读列,依赖 T4)→T7(前端)→T8(配置)→T9(回归)。✅
