"""Step1 空运重量档(air_tier)导入适配器。

解析「做表」生成的档位表（程序生成的统一格式，见表头契约），回流入 AirTierRate。
按 sheet 表头内容识别（不靠文件名——档位文件名常含 'air' 会被 AirAdapter 抢）。
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.services.step1_rates.entities import (
    ParsedRateBatch,
    ParsedRateRecord,
    Step1FileType,
)

_TIER_HEADER_RE = re.compile(r"^(\d+)\s*KG$", re.IGNORECASE)
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}


class AirTierAdapter:
    """识别并解析做表生成的空运重量档表。"""

    key = "air_tier"
    file_type = Step1FileType.air_tier
    priority = 5  # 必须先于 AirAdapter(10)

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        if file_type_hint is not None:
            return file_type_hint == self.file_type
        if path.suffix.lower() not in _EXCEL_EXTS:
            return False
        try:
            wb = load_workbook(path, data_only=True, read_only=True)
        except Exception:
            return False
        try:
            for ws in wb.worksheets:
                if self._tier_sheet_headers(ws) is not None:
                    return True
        finally:
            wb.close()
        return False

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        wb = load_workbook(path, data_only=True)
        records: list[ParsedRateRecord] = []
        for ws in wb.worksheets:
            headers = self._tier_sheet_headers(ws)
            if headers is None:
                continue
            records.extend(self._parse_sheet(ws, headers))
        return ParsedRateBatch(
            file_type=Step1FileType.air_tier,
            source_file=path.name,
            records=records,
            adapter_key=self.key,
        )

    def _tier_sheet_headers(self, ws) -> dict[str, Any] | None:
        """读第 1 行表头；命中档位表契约时返回 {name→col_index, "tiers":[(kg,col)]}，否则 None。"""
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not first_row:
            return None
        named: dict[str, int] = {}
        tiers: list[tuple[int, int]] = []
        for idx, cell in enumerate(first_row):
            text = str(cell).strip() if cell is not None else ""
            if not text:
                continue
            m = _TIER_HEADER_RE.match(text)
            if m:
                tiers.append((int(m.group(1)), idx))
            else:
                named[text.lower()] = idx
        has_origin = any(k.startswith("origin") for k in named)
        if has_origin and "destination" in named and tiers:
            return {"named": named, "tiers": tiers}
        return None

    def _parse_sheet(self, ws, headers: dict[str, Any]) -> list[ParsedRateRecord]:
        named: dict[str, int] = headers["named"]
        tiers: list[tuple[int, int]] = headers["tiers"]

        def col(*names: str) -> int | None:
            for n in names:
                if n in named:
                    return named[n]
            for key, idx in named.items():
                if key.startswith(names[0]):
                    return idx
            return None

        c_origin = col("origin (pol)", "origin")
        c_dest = col("destination")
        c_service = col("service")
        c_currency = col("currency")
        c_from = col("effective from")
        c_to = col("effective to")
        c_carrier = col("carrier")
        c_cargo = col("cargo class")
        c_pack = col("packing")
        c_density = col("density")
        c_remark = col("remark")

        out: list[ParsedRateRecord] = []
        for row_index, row in enumerate(
            ws.iter_rows(min_row=2, values_only=True), start=2
        ):
            def v(i: int | None) -> Any:
                return row[i] if i is not None and i < len(row) else None

            origin = v(c_origin)
            dest = v(c_dest)
            tier_prices: dict[int, float] = {}
            for kg, ci in tiers:
                price = row[ci] if ci < len(row) else None
                if price is not None and str(price).strip() != "":
                    tier_prices[kg] = float(price)
            if not origin and not dest and not tier_prices:
                continue  # 跳过空行
            out.append(
                ParsedRateRecord(
                    record_kind="air_tier",
                    origin_port_name=str(origin).strip() if origin else None,
                    destination_port_name=str(dest).strip() if dest else None,
                    service_desc=(str(v(c_service)).strip() if v(c_service) else None),
                    currency=(str(v(c_currency)).strip() if v(c_currency) else "CNY"),
                    valid_from=self._to_date(v(c_from)),
                    valid_to=self._to_date(v(c_to)),
                    remarks=(str(v(c_remark)).strip() if v(c_remark) else None),
                    source_type="excel",
                    extras={
                        "tier_prices": tier_prices,
                        "cargo_class": (str(v(c_cargo)).strip() if v(c_cargo) else None),
                        "packing": (str(v(c_pack)).strip() if v(c_pack) else None),
                        "density": (str(v(c_density)).strip() if v(c_density) else None),
                        "carrier": (str(v(c_carrier)).strip() if v(c_carrier) else None),
                        "row_index": row_index,
                    },
                )
            )
        return out

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if not value:
            return None
        if hasattr(value, "isoformat") and not isinstance(value, str):
            try:
                return value.date() if hasattr(value, "date") else value
            except Exception:
                return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
