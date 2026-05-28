"""重量档 Air 报价解析（如阪急唯凯联运商报价）。

这种报价按「重量档(+45/+100/+500/+1000KG)」给价，而非按星期几。业务规则(待福山最终确认)：
取每条航线的 **+100KG 价** 作为目标模板 day1~day7 的每日价（一周不变），service 填航班/航司。
同一目的港下多航班全部保留并标 needs_review（由审核台人工选一条）。

只解析「Effective / DEST / 重量档」这种规整块结构（覆盖亚洲/澳洲线那几张表）；
航司专属欧美线表布局完全不同、极不规则，本解析器不覆盖，计入 warnings 的"未覆盖"清单，
不报错——交由后续(可能 LLM 辅助)处理。
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

_FLIGHT_HEADERS = {"flight", "flight no", "flight no.", "carrier", "flt.nbr", "flt nbr"}


def parse_weight_break(file_path: str) -> dict[str, Any]:
    """解析重量档报价 → {parsed_rows, warnings}。无规整航线块时返回空 parsed_rows。"""
    xls = pd.ExcelFile(file_path)
    source_file = os.path.basename(file_path)
    parsed_rows: list[dict[str, Any]] = []
    covered: list[str] = []
    skipped: list[str] = []

    for sheet_name in xls.sheet_names:
        rows = pd.read_excel(file_path, sheet_name=sheet_name, header=None).values.tolist()
        header_idxs = [i for i, r in enumerate(rows) if _is_header_row(r)]
        if not header_idxs:
            skipped.append(sheet_name)
            continue
        sheet_rows = _parse_sheet(rows, header_idxs, source_file)
        if sheet_rows:
            covered.append(sheet_name)
            parsed_rows.extend(sheet_rows)
        else:
            skipped.append(sheet_name)

    warnings: list[str] = []
    if covered:
        warnings.append("已抽取航线表(+100KG)：" + "/".join(covered))
    if skipped:
        warnings.append("未覆盖(布局不同/非航线表)：" + "/".join(skipped))
    return {"parsed_rows": parsed_rows, "warnings": warnings}


def _is_header_row(row: list[Any]) -> bool:
    cells = [_clean(c) for c in row]
    has_effective = any(c and "effective" in c.lower() for c in cells)
    has_dest = any(c == "DEST" for c in cells)
    return has_effective and has_dest


def _column_map(header: list[Any]) -> dict[str, int]:
    cmap: dict[str, int] = {}
    for j, cell in enumerate(header):
        text = _clean(cell)
        if text is None:
            continue
        low = text.lower()
        if text == "DEST":
            cmap["dest"] = j
        elif low in _FLIGHT_HEADERS:
            cmap["flight"] = j
        elif _to_float(cell) == 100.0:
            cmap["p100"] = j
    return cmap


def _parse_sheet(
    rows: list[list[Any]], header_idxs: list[int], source_file: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    header_set = set(header_idxs)
    cmap: dict[str, int] = {}
    current_dest: str | None = None

    for i, row in enumerate(rows):
        if i in header_set:
            cmap = _column_map(row)
            current_dest = None
            continue
        if "dest" not in cmap or "p100" not in cmap:
            continue

        dest_val = _clean(row[cmap["dest"]]) if cmap["dest"] < len(row) else None
        if dest_val:
            current_dest = dest_val

        price = _to_float(row[cmap["p100"]]) if cmap["p100"] < len(row) else None
        flight = (
            _clean(row[cmap["flight"]])
            if "flight" in cmap and cmap["flight"] < len(row)
            else None
        )

        if price is not None and current_dest:
            record: dict[str, Any] = {
                "destination_port_name": current_dest,
                "service_desc": flight,
                "multi_flight_pick": True,  # 同港多航班 → 交审核台人工选一条
                "source_file": source_file,
            }
            for day in range(1, 8):
                record[f"price_day{day}"] = price
            out.append(record)
    return out


def _clean(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
