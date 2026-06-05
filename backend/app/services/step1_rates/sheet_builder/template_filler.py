"""配置驱动的模板填充器。

输入统一的 normalized rate dict 列表，按 template_registry 的列映射，从数据起始行
逐行写进空白模板（保留表头/格式/公式）。复用 writers/base.safe_set 的写入守卫
（None 不写、公式格不覆盖）。不入库——产物就是填好的 xlsx。

空白模板的数据区预设了合并单元格（如目的港/船司列每 2 行合并），其从属格 value 只读。
填充前先解除「数据起始行及以后」的合并（表头区合并保留），再逐格写。

normalized rate dict 字段约定：
  通用:  destination, carrier, remark
  sea :  container_20gp, container_40gp, container_40hq, lss_cic, baf, ebs, yas_caf, sailing, via, transit, booking
  air(周表源 Market Price):  service, day1..day7
  air(档位源 EES/唯凯):       service, tier_prices(稀疏 KG→价)

档位源的列是动态的(全表档位并集)，套不进固定 air_blank.xlsx → 程序从零生成档位表
(起运港|目的港|服务|动态 KG 列|备注)，报价日入 sheet 名。
"""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook

from app.services.step1_rates.sheet_builder.entities import SheetFillConfig
from app.services.step1_rates.sheet_builder.template_registry import get_template_config
from app.services.step1_rates.writers.base import safe_set

# Sea FCL 一条运价展开为三行：(箱型标签, 取运费用的字段名)
_SEA_CONTAINER_ROWS = (
    ("20FT", "container_20gp"),
    ("40GP", "container_40gp"),
    ("40HQ", "container_40hq"),
)

# (表头标签, 列键, 行字段) —— 新增海运元数据列(模板无表头,填充时一并写第8行表头)
_SEA_META_COLS = (
    ("Currency", "currency", "currency"),
    ("Valid From", "valid_from", "valid_from"),
    ("Valid To", "valid_to", "valid_to"),
    ("Rate Level", "rate_level", "rate_level"),
    ("Service Code", "service_code", "service_code"),
)

# 档位表元数据列：(表头标签, 取值的字段名)。顺序即列序，必须与 AirTierAdapter 解析契约一致。
_TIER_META_COLS = (
    ("Currency", "currency"),
    ("Effective From", "effective_week_start"),
    ("Effective To", "effective_to"),
    ("Carrier", "carrier"),
    ("Cargo Class", "cargo_class"),
    ("Packing", "packing"),
    ("Density", "density"),
)


def fill_template(template_type: str, rows: list[dict[str, Any]]) -> tuple[bytes, str]:
    """把 rows 填进对应空白模板，返回 (xlsx_bytes, 建议文件名)。"""
    cfg = get_template_config(template_type)  # 校验类型；未知抛 ValueError

    # air 档位源(行带 tier_prices)：列动态 → 程序生成档位表，不套固定 air_blank.xlsx。
    if template_type == "air" and any(r.get("tier_prices") for r in rows):
        return _build_tier_sheet(rows)

    workbook = load_workbook(cfg.template_path, data_only=False)
    if template_type == "air":
        _fill_air(workbook, cfg.sheets[0], rows)
    elif template_type == "sea":
        _fill_sea(workbook, cfg.sheets[0], rows)
    else:  # pragma: no cover — registry 已保证只有 air/sea
        raise ValueError(f"unsupported template_type {template_type!r}")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), f"{template_type}_rate_sheet_filled.xlsx"


def _row_tiers(row: dict[str, Any]) -> dict[int, Any]:
    """取行的档位 dict，键归一为 int(KG)——JSON 往返后键可能是字符串('45')。"""
    raw = row.get("tier_prices") or {}
    return {int(kg): price for kg, price in raw.items()}


def _tier_sheet_name(rows: list[dict[str, Any]]) -> str:
    """报价日(effective_week_start)入 sheet 名；无则用通用名。"""
    for row in rows:
        value = row.get("effective_week_start")
        if value:
            return f"Air Rates {str(value)[:10]}"
    return "Air Tier Rates"


def _build_tier_sheet(rows: list[dict[str, Any]]) -> tuple[bytes, str]:
    """程序生成档位表：起运港|目的港|服务|动态 KG 列|元数据列|备注。"""
    tiers = sorted({kg for row in rows for kg in _row_tiers(row)})
    wb = Workbook()
    ws = wb.active
    ws.title = _tier_sheet_name(rows)

    header = (
        ["Origin (POL)", "Destination", "Service"]
        + [f"{kg}KG" for kg in tiers]
        + [label for label, _ in _TIER_META_COLS]
        + ["Remark"]
    )
    for c, label in enumerate(header, start=1):
        ws.cell(1, c).value = label

    meta_start = 4 + len(tiers)  # KG 列之后第一列
    r = 2
    for row in rows:
        ws.cell(r, 1).value = row.get("origin")
        ws.cell(r, 2).value = row.get("destination")
        ws.cell(r, 3).value = row.get("service")
        row_tiers = _row_tiers(row)
        for i, kg in enumerate(tiers):
            price = row_tiers.get(kg)
            if price is not None:
                ws.cell(r, 4 + i).value = price
        for j, (_, field_name) in enumerate(_TIER_META_COLS):
            ws.cell(r, meta_start + j).value = row.get(field_name)
        ws.cell(r, meta_start + len(_TIER_META_COLS)).value = row.get("remark")
        r += 1

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), "air_tier_rate_sheet_filled.xlsx"


def _unmerge_data_area(ws, data_start_row: int) -> None:
    """解除「数据起始行及以后」的合并单元格，让数据区每格可写。表头合并保留。"""
    targets = [
        str(rng) for rng in ws.merged_cells.ranges if rng.min_row >= data_start_row
    ]
    for rng in targets:
        ws.unmerge_cells(rng)


def _first_week_start(rows: list[dict[str, Any]]) -> date | None:
    """取第一条带 effective_week_start 的行的周起始日（ISO 字符串 / date 均可）；无则 None。"""
    for row in rows:
        value = row.get("effective_week_start")
        if not value:
            continue
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return None


def _apply_week_headers(ws, sheet_cfg: SheetFillConfig, rows: list[dict[str, Any]]) -> None:
    """有周信息时，按该周改写 day1-7 日期表头 + sheet 名（一份模板通吃任意周）；无则不动。"""
    week_start = _first_week_start(rows)
    if week_start is None:
        return
    col = sheet_cfg.columns
    for i in range(7):
        d = week_start + timedelta(days=i)
        ws.cell(sheet_cfg.header_row, col[f"day{i + 1}"]).value = (
            f"{d.year}/{d.month}/{d.day} ({d:%a})"
        )
    week_end = week_start + timedelta(days=6)
    ws.title = f"{week_start:%b} {week_start.day} to {week_end:%b} {week_end.day}"


def _fill_air(workbook, sheet_cfg: SheetFillConfig, rows: list[dict[str, Any]]) -> None:
    ws = workbook[sheet_cfg.sheet_name]
    _unmerge_data_area(ws, sheet_cfg.data_start_row)
    _apply_week_headers(ws, sheet_cfg, rows)
    col = sheet_cfg.columns
    ws.cell(sheet_cfg.header_row, col["currency"]).value = "Currency"
    r = sheet_cfg.data_start_row
    for row in rows:
        safe_set(ws.cell(r, col["origin"]), row.get("origin"))
        safe_set(ws.cell(r, col["destination"]), row.get("destination"))
        safe_set(ws.cell(r, col["service"]), row.get("service"))
        for day in range(1, 8):
            safe_set(ws.cell(r, col[f"day{day}"]), row.get(f"day{day}"))
        safe_set(ws.cell(r, col["remark"]), row.get("remark"))
        safe_set(ws.cell(r, col["currency"]), row.get("currency"))
        r += 1


def _fill_sea(workbook, sheet_cfg: SheetFillConfig, rows: list[dict[str, Any]]) -> None:
    ws = workbook[sheet_cfg.sheet_name]
    _unmerge_data_area(ws, sheet_cfg.data_start_row)
    col = sheet_cfg.columns
    # 模板无这些新列表头 → 填充时在表头行写英文标签，供重新导入时 OceanAdapter 按表头识别
    for label, col_key, _ in _SEA_META_COLS:
        ws.cell(sheet_cfg.header_row, col[col_key]).value = label
    r = sheet_cfg.data_start_row
    for row in rows:
        for container_label, freight_key in _SEA_CONTAINER_ROWS:
            safe_set(ws.cell(r, col["destination"]), row.get("destination"))
            safe_set(ws.cell(r, col["carrier"]), row.get("carrier"))
            safe_set(ws.cell(r, col["container"]), container_label)
            safe_set(ws.cell(r, col["freight"]), row.get(freight_key))
            safe_set(ws.cell(r, col["lss_cic"]), row.get("lss_cic"))
            safe_set(ws.cell(r, col["baf"]), row.get("baf"))
            safe_set(ws.cell(r, col["ebs"]), row.get("ebs"))
            safe_set(ws.cell(r, col["yas_caf"]), row.get("yas_caf"))
            safe_set(ws.cell(r, col["sailing"]), row.get("sailing"))
            safe_set(ws.cell(r, col["via"]), row.get("via"))
            safe_set(ws.cell(r, col["transit"]), row.get("transit"))
            safe_set(ws.cell(r, col["booking"]), row.get("booking"))
            safe_set(ws.cell(r, col["rmks"]), row.get("remark"))
            for _, col_key, field_name in _SEA_META_COLS:
                safe_set(ws.cell(r, col[col_key]), row.get(field_name))
            r += 1
