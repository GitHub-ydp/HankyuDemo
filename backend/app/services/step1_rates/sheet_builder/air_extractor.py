"""Air 运价表生成：从「Market Price (Air)」周报抽取每日价行。

复用导入链路里已实地校准的 AirAdapter 解析 air_weekly 记录（destination /
service / 每日价 day1-7），转成 sheet_builder 统一的 parsed dict
（parsed_rows + warnings），交给 orchestrator 归一/填模板。不入库——只为做表。

识别不了(文件名/结构不匹配、无周表 sheet)时返回 {error, parsed_rows: []}，
不抛异常——交由 orchestrator 标 skipped 并把原因透传给审核台。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.sheet_builder import air_ees, air_weight_break


def extract_air_rates(file_path: str, db: Session | None) -> dict[str, Any]:
    path = Path(file_path)

    # 1) 标准周报 Market Price（按星期几给价，直接对模板 day1-7）
    market = _try_market_price(path, db)
    if market is not None:
        return market

    # 2) 重量档报价（阪急唯凯式联运商报价，取 +100KG 价填 day1-7）
    try:
        weight_break = air_weight_break.parse_weight_break(str(path))
    except Exception as exc:  # noqa: BLE001 — 非 Excel/解析失败不抛，透传原因
        return {"error": f"Air 文件解析失败: {exc}", "parsed_rows": []}
    if weight_break["parsed_rows"]:
        return weight_break

    # 3) 百福东方(EES)式多航线表（目的港/港口 + KG 档 + 平散货子行，取 100KG 价填 day1-7）
    try:
        ees = air_ees.parse_ees(str(path))
    except Exception as exc:  # noqa: BLE001 — 同上，解析失败透传原因不抛
        return {"error": f"Air 文件解析失败: {exc}", "parsed_rows": []}
    if ees["parsed_rows"]:
        return ees

    return {
        "error": "既不是 Air Market Price 周报，也未识别到重量档航线表（请确认是 Air 运价资料）",
        "parsed_rows": [],
    }


def _try_market_price(path: Path, db: Session | None) -> dict[str, Any] | None:
    """标准周报路径：识别+解析出 weekly 行则返回 parsed dict，否则 None（交给重量档兜底）。"""
    adapter = AirAdapter()
    if not adapter.detect(path):
        return None
    try:
        batch = adapter.parse(path, db)
    except Exception:  # noqa: BLE001 — 解析失败时回退到重量档路径
        return None

    legacy = batch.to_legacy_dict()
    weekly = [
        r for r in legacy.get("records", []) if r.get("record_kind") == "air_weekly"
    ]
    if not weekly:
        return None

    weekly = _keep_latest_week(weekly)
    return {"parsed_rows": weekly, "warnings": list(legacy.get("warnings", []) or [])}


def _keep_latest_week(weekly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """周报常含多周 sheet；模板只针对一周，只保留 effective_week_start 最新的那一周。

    无日期信息时（解析不到周范围）原样返回，不丢数据。
    """
    dated = [r for r in weekly if r.get("effective_week_start")]
    if not dated:
        return weekly
    latest = max(r["effective_week_start"] for r in dated)
    return [r for r in weekly if r.get("effective_week_start") == latest]
