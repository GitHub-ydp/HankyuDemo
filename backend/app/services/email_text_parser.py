"""邮件文本运价解析 — 使用 AI 从非结构化邮件文本中提取费率数据"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Port, Carrier
from app.services import ai_client
from app.services.rate_parser import _resolve_port, _safe_decimal


# AI 系统提示词 — 海运费率提取专家
SYSTEM_PROMPT = """你是一个海运费率数据提取专家。你的任务是从邮件文本中精确提取海运费率信息，输出标准化 JSON。

## 输出格式

必须输出一个 JSON 数组，每个元素代表一条航线费率：
```json
[
  {
    "carrier": "船司名称（如 EMC/长荣、KMTC/高丽海运）",
    "service_code": "航线代码（如 JCH 0364，没有则为 null）",
    "origin": "起运港（通常从上下文推断，如上海）",
    "destination": "目的港中文名",
    "container_20gp": 费率数字或null,
    "container_40gp": 费率数字或null,
    "container_40hq": 费率数字或null,
    "container_45": 费率数字或null,
    "currency": "USD",
    "valid_from": "YYYY-MM-DD 或 null",
    "valid_to": "YYYY-MM-DD 或 null",
    "transit_days": 天数或null,
    "is_direct": true/false,
    "remarks": "附加信息（DG附加费、中转等备注）"
  }
]
```

## 解析规则

1. **费率格式 "375/750"**：斜杠前是 20GP，斜杠后是 40GP。40HQ 默认等于 40GP（除非另有说明）
2. **"含"** 表示已包含在基本运费中
3. **"直达"** → is_direct=true，**"中转"** → is_direct=false
4. **起运港**：如果文本没有明确说明，通常是上海（CNSHA）
5. **有效期**：从 "12周（3/22-3/28）" 这样的表述中提取日期范围（注意推断年份）
6. **"45尺报价在高箱基础+600"**：计算 45ft = 40HQ + 600
7. **"DG附加费200/400"**：记入 remarks，不影响基本费率
8. **同一目的港多个别名用 / 分隔**（如 "巴生西/北港"）：视为同一目的港
9. **船司判断**：从上下文中判断是哪家船司的报价（如"长荣"=EMC/Evergreen）

## 注意
- 只输出 JSON，不要输出其他解释文本
- 数字必须精确，不要猜测
- 如果费率信息不完整，尽量提取已有信息，缺失字段设为 null
- 当前年份是 {year}
"""


def parse_email_text(text: str, db: Session) -> dict:
    """
    从邮件文本中 AI 提取费率数据
    返回格式与 Excel 解析器一致: {batch_id, parsed_rows, warnings, ...}
    """
    batch_id = f"EMAIL-{uuid.uuid4().hex[:8]}"
    warnings = []

    # 长邮件兜底：vLLM max_model_len=2048，粗略 6000 中文字符 ≈ 1500 tokens
    MAX_EMAIL_CHARS = 6000
    if len(text) > MAX_EMAIL_CHARS:
        warnings.append(f"邮件正文超长（{len(text)} 字），已截断到 {MAX_EMAIL_CHARS} 字符")
        text = text[:MAX_EMAIL_CHARS]

    # 调用 AI
    current_year = date.today().year
    system = SYSTEM_PROMPT.replace("{year}", str(current_year))
    user_msg = f"请从以下邮件文本中提取所有海运费率信息：\n\n{text}"

    try:
        raw_response = ai_client.chat(
            system, user_msg,
            temperature=0.0,
            max_tokens=settings.ai_max_tokens_extract_json,
        )
        rates_json = ai_client.extract_json(raw_response)
    except Exception as e:
        return {
            "batch_id": batch_id,
            "parsed_rows": [],
            "total_rows": 0,
            "warnings": [f"AI 解析失败: {str(e)}"],
            "source_type": "email_text",
            "file_name": "email_text_input",
            "ai_raw_response": str(e),
        }

    if not isinstance(rates_json, list):
        rates_json = [rates_json]

    # 将 AI 输出转换为标准 parsed_row 格式
    parsed_rows = []
    for idx, item in enumerate(rates_json):
        # 解析起运港
        origin_name = item.get("origin", "上海")
        origin_port = _resolve_port(origin_name, db)
        if not origin_port:
            origin_port = db.query(Port).filter(Port.un_locode == "CNSHA").first()
            warnings.append(f"Rate {idx}: 起运港 '{origin_name}' 未识别，默认使用上海")

        # 解析目的港
        dest_name = item.get("destination", "")
        dest_port = _resolve_port(dest_name, db)
        if not dest_port:
            warnings.append(f"Rate {idx}: 目的港 '{dest_name}' 未识别（将在导入时跳过）")
            continue

        # 解析船司
        carrier_name = item.get("carrier", "")
        carrier = _match_carrier(carrier_name, db)
        if not carrier:
            warnings.append(f"Rate {idx}: 船司 '{carrier_name}' 未找到，使用默认")

        # 解析日期
        valid_from = _parse_date_str(item.get("valid_from"))
        valid_to = _parse_date_str(item.get("valid_to"))

        parsed_rows.append({
            "carrier_id": carrier.id if carrier else None,
            "carrier_name": carrier_name,
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
            "is_direct": item.get("is_direct", True),
            "remarks": item.get("remarks"),
            "service_code": item.get("service_code"),
            "source_type": "email_text",
            "source_file": "email_text_input",
            "upload_batch_id": batch_id,
        })

    return {
        "batch_id": batch_id,
        "file_name": "email_text_input",
        "source_type": "email_text",
        "carrier_code": _detect_carrier_from_text(text),
        "parsed_rows": parsed_rows,
        "total_rows": len(parsed_rows),
        "warnings": warnings,
        "ai_raw_response": raw_response if 'raw_response' in dir() else "",
    }


_CARRIER_ALIAS = {
    "长荣": ("EMC", "Evergreen Marine", "长荣海运"),
    "evergreen": ("EMC", "Evergreen Marine", "长荣海运"),
    "emc": ("EMC", "Evergreen Marine", "长荣海运"),
    "高丽海运": ("KMTC", "KMTC Line", "高丽海运"),
    "kmtc": ("KMTC", "KMTC Line", "高丽海运"),
    "one": ("ONE", "Ocean Network Express", "海洋网联"),
    "ocean network": ("ONE", "Ocean Network Express", "海洋网联"),
    "阳明": ("YML", "Yang Ming Marine", "阳明海运"),
    "yang ming": ("YML", "Yang Ming Marine", "阳明海运"),
    "万海": ("WHL", "Wan Hai Lines", "万海航运"),
    "wan hai": ("WHL", "Wan Hai Lines", "万海航运"),
    "中远": ("COSCO", "COSCO Shipping", "中远海运"),
    "cosco": ("COSCO", "COSCO Shipping", "中远海运"),
    "马士基": ("MSK", "Maersk Line", "马士基"),
    "maersk": ("MSK", "Maersk Line", "马士基"),
    "地中海": ("MSC", "Mediterranean Shipping Company", "地中海航运"),
    "msc": ("MSC", "Mediterranean Shipping Company", "地中海航运"),
    "赫伯罗特": ("HPL", "Hapag-Lloyd", "赫伯罗特"),
    "hapag": ("HPL", "Hapag-Lloyd", "赫伯罗特"),
    "oocl": ("OOCL", "Orient Overseas Container Line", "东方海外"),
    "东方海外": ("OOCL", "Orient Overseas Container Line", "东方海外"),
    "现代": ("HMM", "HMM Co., Ltd.", "韩新海运"),
    "hmm": ("HMM", "HMM Co., Ltd.", "韩新海运"),
    "以星": ("ZIM", "ZIM Integrated Shipping", "以星航运"),
    "zim": ("ZIM", "ZIM Integrated Shipping", "以星航运"),
}


def _match_carrier(name: str, db: Session) -> Carrier | None:
    """模糊匹配船司，找不到时按识别名称自动建一条。

    设计动机：演示流程允许"清空数据后只导入即可"，因此 carriers 表可能为空。
    任何能从 AI / 表头里识别出来的船司名都应当落库，避免 freight_rates.carrier_id
    NOT NULL 约束失败。
    """
    if not name:
        return None
    name_lower = name.lower()

    # 1) 别名命中：先查已有，没有就用别名表里的标准代码/名称建一条
    for key, (code, name_en, name_cn) in _CARRIER_ALIAS.items():
        if key in name_lower:
            carrier = db.query(Carrier).filter(Carrier.code == code).first()
            if carrier:
                return carrier
            return _create_carrier(db, code=code, name_en=name_en, name_cn=name_cn)

    # 2) 直接用 code 查
    code_guess = name.strip().upper()[:20]
    carrier = db.query(Carrier).filter(Carrier.code == code_guess).first()
    if carrier:
        return carrier

    # 3) 完全没匹配上，用识别名称建一条最小记录
    return _create_carrier(db, code=code_guess, name_en=name.strip(), name_cn=name.strip())


def _create_carrier(db: Session, *, code: str, name_en: str, name_cn: str | None = None) -> Carrier:
    """新建一条船司记录并立即 commit。

    必须 commit：parse 阶段和 import 阶段是两个独立 HTTP 请求，
    用的是不同 Session。如果只 flush 不 commit，parse 请求结束时
    Session 关闭未提交，船司就丢了，import 阶段拿到的 carrier_id
    在 DB 里不存在 → FK 约束失败。
    """
    code = (code or "UNKNOWN").strip().upper()[:20] or "UNKNOWN"
    carrier = Carrier(
        code=code,
        name_en=name_en[:200],
        name_cn=(name_cn or name_en)[:200],
    )
    db.add(carrier)
    try:
        db.commit()
        db.refresh(carrier)
    except Exception:
        # 唯一键冲突等：回滚后再查一次
        db.rollback()
        existing = db.query(Carrier).filter(Carrier.code == code).first()
        if existing:
            return existing
        raise
    return carrier


def _detect_carrier_from_text(text: str) -> str:
    """从邮件文本中检测船司名称"""
    text_lower = text.lower()
    if "长荣" in text or "evergreen" in text_lower or "emc" in text_lower:
        return "EMC"
    if "kmtc" in text_lower or "高丽" in text:
        return "KMTC"
    if "one " in text_lower or "ocean network" in text_lower:
        return "ONE"
    return "UNKNOWN"


def _parse_date_str(val: str | None) -> date | None:
    """解析 AI 返回的日期字符串"""
    if not val or val == "null":
        return None
    try:
        # YYYY-MM-DD
        parts = val.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        pass
    return None
