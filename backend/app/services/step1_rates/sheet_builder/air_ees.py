"""百福东方(EES)空运报价解析 —— 自适应多档抽取。

EES 报价按多张航线 sheet(日本/亚太/欧洲/美国/中南美)组织，且**一张 sheet 内常有多个航司块**
(NH/MU/CX/CZ/OZ/VN/MH/GA…)，每块表头略有差异：目的港列叫「目的港」或「港口」(可能带后缀
如「港口(重板包板)」)，重量档列头是中文/带符号的文本(≧100KG / >100KGS / 100K / 100KGS)，
同一目的港下常有多条装载方式子行(平散货 / 平托盘 / 散货1:200…)，价格含「/」「议价」「单询」。

业务规则(福山 2026-05-28 定稿)：不再只取 100KG 一档，而是从每个运价块的**表头行**自适应
读出所有「数字+KG」列当档位(本文件实际 45/100/300/500/1000，不预设白名单)，每条线存稀疏
档位 dict `tier_prices={45:17,100:14,…}`(有哪档数字存哪档)。一条线**只要任一档是数字**就
保留该行(议价/单询的格留空，不算价)；service 填装载方式(无则填航班)；同目的港多条全部保留并
标 multi_flight_pick，交审核台人工选。封面/联系我们/杂费/查验费等非航线表自动跳过。

「无 100KG 列头」是排除卡车转运子表的判据：那种子表里的 `4000KGS/250KGS` 是单元格**值**
不是表头列名，且其块无 100KG 表头列 → `_is_header_row` 不认作运价块表头，整块不抽。

目的港单元格三种形态：纯港口码(KIX/BKK)、带航司前缀的包板(NH-DFW/包板→DFW、CK/MU-LAX→LAX)、
区域/多港组合(美国西部：SEA LAX…、MEX,MTY,CUN)。前两种精确还原，第三种取首个机场码(其余靠
审核台人工修正)。
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

import pandas as pd

_FILE_DATE = re.compile(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")
_AIRLINE_PREFIX = re.compile(r"^([A-Za-z]{1,3}/)*[A-Za-z]{1,3}-")  # NH- / CK/MU-
_IATA = re.compile(r"[A-Z]{3}")
# 重量档表头：纯「(可带比较符)数字+K/KG/KGS」。带后缀的「+100KG泡货」「37分泡比例1:100」
# 因尾部还有字符不匹配 $ → 不会被当成档位。
_TIER_HEADER = re.compile(r"^[≧≥>＞]?\s*(\d+)\s*[Kk](?:[Gg][Ss]?)?$")
_PURE_NUM = re.compile(r"^\d+(?:\.\d+)?$")  # 纯数字价，排除 +2/42-42/议价/单询/"/"
# EES 价多为含油 All-in(各 sheet 表头多注「报价已含燃油战险」)，统一写入备注；
# 净价/含油拆分等真有入札要求再做(见 memory step1-air-ees-format)。
_EES_FUEL_NOTE = "以上价格均已包含附加费（燃油/战险/地面操作），但不含杂费"


def parse_ees(file_path: str) -> dict[str, Any]:
    """解析 EES 多航线报价 → {parsed_rows, warnings}。无可识别航线块时返回空 parsed_rows。"""
    xls = pd.ExcelFile(file_path)
    source_file = os.path.basename(file_path)
    # 模板/下游按周改写日期表头；EES 各航线 EFF 不一，取文件名报价日做全表统一报价日(已与用户确认)。
    effective = _filename_effective_date(source_file)
    parsed_rows: list[dict[str, Any]] = []
    covered: list[str] = []
    skipped: list[str] = []

    for sheet_name in xls.sheet_names:
        rows = pd.read_excel(file_path, sheet_name=sheet_name, header=None).values.tolist()
        header_idxs = [i for i, r in enumerate(rows) if _is_header_row(r)]
        if not header_idxs:
            skipped.append(sheet_name.strip())
            continue
        sheet_rows = _parse_sheet(rows, header_idxs, source_file, effective)
        if sheet_rows:
            covered.append(sheet_name.strip())
            parsed_rows.extend(sheet_rows)
        else:
            skipped.append(sheet_name.strip())

    warnings: list[str] = []
    if covered:
        warnings.append("已抽取航线表(多档)：" + "/".join(covered))
    if skipped:
        warnings.append("未覆盖(封面/杂费/非航线表)：" + "/".join(skipped))
    return {"parsed_rows": parsed_rows, "warnings": warnings}


def _is_header_row(row: list[Any]) -> bool:
    cells = [_clean(c) for c in row]
    has_dest = any(_is_dest_label(c) for c in cells)
    has_p100 = any(_is_p100_label(c) for c in cells)
    return has_dest and has_p100


def _is_dest_label(c: str | None) -> bool:
    return bool(c) and ("目的港" in c or "港口" in c)


def _is_p100_label(c: str | None) -> bool:
    return _tier_kg(c) == 100


def _is_flight_label(c: str | None) -> bool:
    return bool(c) and "航班" in re.sub(r"\s", "", c)


def _tier_kg(value: str | None) -> int | None:
    """表头单元格 → 重量档 KG 整数；只认纯档位写法(可带 ≧/≥/> 比较符)，如
    ≧100KG / >1000KGS / 45K / 100KGS。「+100KG泡货」「37分泡比例1:100」这类尾部还带
    字符的不是档位，返回 None。(注：仅对表头行调用；卡车子表的 4000KGS 是数据单元格值，
    其块因无 100KG 表头列不会进到这里。)"""
    c = _clean(value)
    if not c:
        return None
    m = _TIER_HEADER.match(c)
    return int(m.group(1)) if m else None


def _column_map(header: list[Any]) -> dict[str, int | dict[int, int]]:
    """从表头行定位关键列：dest / flight / tiers(所有重量档列 {KG: 列号}) /
    first_tier(最靠左的档位列号，用来圈定装载方式列的搜索范围)。"""
    cmap: dict[str, Any] = {}
    tiers: dict[int, int] = {}
    for j, cell in enumerate(header):
        c = _clean(cell)
        if not c:
            continue
        kg = _tier_kg(c)
        if kg is not None:
            tiers.setdefault(kg, j)  # 同一档重复出现时取最左列
        elif "dest" not in cmap and _is_dest_label(c):
            cmap["dest"] = j
        elif "flight" not in cmap and _is_flight_label(c):
            cmap["flight"] = j
    if tiers:
        cmap["tiers"] = tiers
        cmap["first_tier"] = min(tiers.values())
    return cmap


def _parse_sheet(
    rows: list[list[Any]],
    header_idxs: list[int],
    source_file: str,
    effective: date | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    header_set = set(header_idxs)
    cmap: dict[str, Any] = {}
    current_dest: str | None = None

    for i, row in enumerate(rows):
        if i in header_set:
            cmap = _column_map(row)
            current_dest = None  # 新航司块重置，避免把上一块的港口串到本块
            continue
        if "dest" not in cmap or not cmap.get("tiers"):
            continue

        raw_dest = _clean(row[cmap["dest"]]) if cmap["dest"] < len(row) else None
        if raw_dest:
            code = _clean_dest(raw_dest)
            if code:
                current_dest = code

        tier_prices = _row_tier_prices(row, cmap["tiers"])
        if current_dest is None or not tier_prices:
            continue

        out.append(
            {
                "destination_port_name": current_dest,
                "service_desc": _row_service(row, cmap),
                # 稀疏档位 dict(KG 升序)：有哪档数字存哪档，取代单价×7天。
                "tier_prices": tier_prices,
                "remarks": _EES_FUEL_NOTE,  # 含油说明进备注(档位表「备注」列)
                "multi_flight_pick": True,  # 同港多条 → 交审核台人工选一条
                "source_file": source_file,
                "effective_week_start": effective,  # 文件名报价日 → 下游改写表头/sheet 名
            }
        )
    return out


def _row_tier_prices(row: list[Any], tiers: dict[int, int]) -> dict[int, float]:
    """按表头档位列逐档取价，只收正的纯数字；议价/单询/「/」留空(不入 dict)。KG 升序。"""
    out: dict[int, float] = {}
    for kg in sorted(tiers):
        col = tiers[kg]
        if col < len(row):
            price = _to_price(row[col])
            if price is not None:
                out[kg] = price
    return out


def _row_service(row: list[Any], cmap: dict[str, Any]) -> str | None:
    """service 优先取装载方式(平散货/平托盘/散货1:200，区分同港多条)，无则取航班列。"""
    load = _row_load_type(row, cmap)
    if load:
        return load
    flight = cmap.get("flight")
    if flight is not None and flight < len(row):
        return _clean(row[flight])
    return None


def _row_load_type(row: list[Any], cmap: dict[str, Any]) -> str | None:
    dest = cmap.get("dest", -1)
    first_tier = cmap.get("first_tier")
    flight = cmap.get("flight")
    if first_tier is None:
        return None
    for j in range(dest + 1, first_tier):
        if j == flight:
            continue
        c = _clean(row[j]) if j < len(row) else None
        if c and c != "/" and _to_float(c) is None:  # 非数字、非"/"的文本即装载方式
            return c
    return None


def _filename_effective_date(name: str) -> date | None:
    """从文件名取报价日(2026-5-21 / 2026/05/09 / 2026.5.1 / 2026年5月1日)；认不出返回 None。"""
    m = _FILE_DATE.search(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _clean_dest(raw: str) -> str | None:
    """目的港单元格 → 机场三字码：先去航司前缀(NH- / CK/MU-)，再取首个三字码。"""
    s = _AIRLINE_PREFIX.sub("", raw.strip())
    m = _IATA.search(s)
    return m.group(0) if m else None


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


def _to_price(value: Any) -> float | None:
    """价格单元格：只认正的纯数字。Excel 原生数字直接用；文本须形如 49 / 43.5，
    把附加费写法(+2)、双值(42/42)、议价/单询/"/" 一律判为非价格。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = str(value).strip()
    if not _PURE_NUM.match(s):
        return None
    f = float(s)
    return f if f > 0 else None
