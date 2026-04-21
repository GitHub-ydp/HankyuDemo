"""WeChat/QQ 截图运价解析 — 使用 AI Vision 从聊天截图中提取费率"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Port, Carrier
from app.services import ai_client
from app.services.rate_parser import _resolve_port, _safe_decimal
from app.services.email_text_parser import _match_carrier, _parse_date_str


SYSTEM_PROMPT = """你是一个海运费率数据提取专家。你的任务是从微信/QQ聊天截图中精确识别并提取海运费率信息。

## 截图特征
- 图片是 WeChat 或 QQ 的聊天界面截图
- 运价信息可能分散在多条消息气泡中
- 可能包含中文口语化表达
- 数字精度很重要，必须准确识别

## 输出格式

必须输出一个 JSON 数组，每个元素代表一条费率：
```json
[
  {
    "carrier": "船司名（如 KMTC、OOCL）或 null",
    "vessel_voyage": "船名/航次（如 OOCL TULIP/003E）或 null",
    "origin": "起运港（如 上海/Shanghai）",
    "destination": "目的港",
    "container_20gp": 数字或null,
    "container_40gp": 数字或null,
    "container_40hq": 数字或null,
    "container_45": 数字或null,
    "currency": "USD",
    "valid_from": "YYYY-MM-DD 或 null",
    "valid_to": "YYYY-MM-DD 或 null",
    "transit_days": 天数或null,
    "is_direct": true/false/null,
    "remarks": "其他信息（含LSS、中转信息、EIS等）"
  }
]
```

## 解析规则

1. **费率格式**：
   - "USD 1650/1700" → 20GP=1650, 40GP=1700（如无40HQ则默认=40GP）
   - "USD 3150 / 40HQ" → 40HQ=3150
   - "375/750" → 20GP=375, 40GP=750
2. **"含LSS"** → 记入 remarks
3. **起运港**：通常是 "POL: Shanghai" 或从对话上下文推断
4. **目的港**：如 "POD: ICD Ahmedabad", "NEW YORK"
5. **有效期**：如 "价格有效期到 3/31", "运价只到3.22"
6. **"到付"** = 记入 remarks
7. **"中转"** → is_direct=false，提取中转港（如 "NHAVA SHEVA 中转"）
8. **EIS** = 目的港附加费，记入 remarks
9. **当前年份**: {year}

## 注意
- 只输出 JSON，不要输出其他文字
- 数字必须从图片中精确读取，不要猜测
- 如果图片模糊或信息不完整，在 remarks 中说明
- 一张截图可能包含多条不同航线的报价
"""


def parse_wechat_image(image_path: str, db: Session, extra_context: str = "") -> dict:
    """
    从微信截图中 AI 提取费率数据
    返回格式与 Excel 解析器一致: {batch_id, parsed_rows, warnings, ...}
    """
    batch_id = f"WECHAT-{uuid.uuid4().hex[:8]}"
    warnings = []

    current_year = date.today().year
    system = SYSTEM_PROMPT.replace("{year}", str(current_year))
    user_text = "请从这张微信/QQ聊天截图中提取所有海运费率信息。"
    if extra_context:
        user_text += f"\n\n补充背景信息：{extra_context}"

    try:
        raw_response = ai_client.chat_with_image(
            system, user_text, image_path,
            temperature=0.0, max_tokens=1200,
        )
        rates_json = ai_client.extract_json(raw_response)
    except Exception as e:
        return {
            "batch_id": batch_id,
            "parsed_rows": [],
            "total_rows": 0,
            "warnings": [f"AI 图片识别失败: {str(e)}"],
            "source_type": "wechat_image",
            "file_name": image_path.split("/")[-1].split("\\")[-1],
            "ai_raw_response": str(e),
        }

    if not isinstance(rates_json, list):
        rates_json = [rates_json]

    parsed_rows = []
    for idx, item in enumerate(rates_json):
        # 起运港
        origin_name = item.get("origin", "上海")
        origin_port = _resolve_port(origin_name, db)
        if not origin_port:
            origin_port = db.query(Port).filter(Port.un_locode == "CNSHA").first()
            warnings.append(f"Rate {idx}: 起运港 '{origin_name}' 未识别，默认上海")

        # 目的港
        dest_name = item.get("destination", "")
        dest_port = _resolve_port(dest_name, db)
        if not dest_port:
            warnings.append(f"Rate {idx}: 目的港 '{dest_name}' 未识别")
            continue

        # 船司
        carrier_name = item.get("carrier", "")
        carrier = _match_carrier(carrier_name, db)

        # 组合 remarks
        remarks_parts = []
        if item.get("vessel_voyage"):
            remarks_parts.append(f"V/V: {item['vessel_voyage']}")
        if item.get("remarks"):
            remarks_parts.append(item["remarks"])
        remarks = "; ".join(remarks_parts) if remarks_parts else None

        valid_from = _parse_date_str(item.get("valid_from"))
        valid_to = _parse_date_str(item.get("valid_to"))

        parsed_rows.append({
            "carrier_id": carrier.id if carrier else None,
            "carrier_name": carrier_name or "UNKNOWN",
            "origin_port_id": origin_port.id if origin_port else None,
            "origin_port_name": f"{origin_port.name_en}/{origin_port.name_cn}" if origin_port else origin_name,
            "destination_port_id": dest_port.id,
            "destination_port_name": f"{dest_port.name_en}/{dest_port.name_cn}",
            "container_20gp": _safe_decimal(item.get("container_20gp")),
            "container_40gp": _safe_decimal(item.get("container_40gp")),
            "container_40hq": _safe_decimal(item.get("container_40hq")),
            "container_45": _safe_decimal(item.get("container_45")),
            "baf_20": None,
            "baf_40": None,
            "lss_20": None,
            "lss_40": None,
            "currency": item.get("currency", "USD"),
            "valid_from": valid_from,
            "valid_to": valid_to,
            "transit_days": item.get("transit_days"),
            "is_direct": item.get("is_direct", True) if item.get("is_direct") is not None else True,
            "remarks": remarks,
            "service_code": None,
            "source_type": "wechat_image",
            "source_file": image_path.split("/")[-1].split("\\")[-1],
            "upload_batch_id": batch_id,
        })

    return {
        "batch_id": batch_id,
        "file_name": image_path.split("/")[-1].split("\\")[-1],
        "source_type": "wechat_image",
        "carrier_code": _detect_carrier_from_items(rates_json),
        "parsed_rows": parsed_rows,
        "total_rows": len(parsed_rows),
        "warnings": warnings,
        "ai_raw_response": raw_response if 'raw_response' in dir() else "",
    }


def _detect_carrier_from_items(items: list) -> str:
    """从解析结果中提取主要船司"""
    carriers = [i.get("carrier", "") for i in items if i.get("carrier")]
    if carriers:
        return carriers[0]
    return "UNKNOWN"
