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
