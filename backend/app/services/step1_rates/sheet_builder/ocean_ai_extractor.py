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
