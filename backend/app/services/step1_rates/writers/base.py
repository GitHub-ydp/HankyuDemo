from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import Cell


WRITER_VERSION = "step1-writer-0.1.0"


def is_formula_cell(cell: Cell) -> bool:
    """判断 cell 是否为 Excel 公式（以 '=' 开头的字符串）。"""
    value = cell.value
    if cell.data_type == "f":
        return True
    return isinstance(value, str) and value.startswith("=")


def safe_set(
    cell: Cell,
    value: Any,
    *,
    allow_overwrite_formula: bool = False,
) -> bool:
    """写入守卫。

    规则：
    - 若当前 cell 是公式且未显式允许覆盖 → 不写，返回 False
    - 若 value 为 None → 不写（保留模板原值），返回 False
    - 否则写入，返回 True
    """
    if value is None:
        return False
    if is_formula_cell(cell) and not allow_overwrite_formula:
        return False
    cell.value = _coerce_value(value)
    return True


def _coerce_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def pick_raw(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """按 keys 顺序返回第一个非 None/非空字符串的 value。"""
    for key in keys:
        if key not in record:
            continue
        val = record[key]
        if val is None:
            continue
        if isinstance(val, str) and val == "":
            continue
        return val
    return default


def save_workbook_to_bytes(workbook: Workbook) -> bytes:
    """把 Workbook 保存到内存字节流。"""
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def stamp_document_properties(
    workbook: Workbook,
    *,
    batch_id: str,
    exported_at: datetime | None = None,
) -> None:
    """按 Q-W7 默认：把 batch_id / 导出时刻 / writer 版本写入 Document Properties。"""
    exported_at = exported_at or datetime.utcnow()
    props = workbook.properties
    props.title = f"Step1 batch {batch_id}"
    props.subject = f"exported {exported_at.isoformat()}"
    props.description = WRITER_VERSION


def to_date_or_none(value: Any) -> date | datetime | None:
    """把常见日期表达（date/datetime/str）转成 openpyxl 可写入的对象。"""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value
    return None
