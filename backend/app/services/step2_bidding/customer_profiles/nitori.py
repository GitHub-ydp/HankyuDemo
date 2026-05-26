from __future__ import annotations
import shutil
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook
from app.services.step1_rates.writers.base import is_formula_cell, safe_set, stamp_document_properties
from app.services.step2_bidding.entities import (
    ParsedPkg, PkgRow, PkgSection, PerRowReport, RowStatus, CostType,
)
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook, normalize_pod

# ---- 常量（业务可调）----
_QUOTE_SHEET = "Quotation (Global) Jul-Sep"
_DATA_START_ROW = 9
_COL = dict(carrier=4, country_exp=5, pol=6, country_imp=7, pod=8, size=9,
            tt=17, of_cur=18, of_amt=19, lss_cur=20, lss_amt=21,
            thc_cur=26, thc_amt=27, doc_cur=28, doc_amt=29, dem_free=103, det_free=104)
_CHINA_POLS = {"SHANGHAI", "TAICANG"}
_SIZE_TO_COST = {"20F": "20gp", "40HC": "40hc", "40F": "40hc"}   # 40F←40HC（assumption）
_MARKUP = Decimal("1.15")


class NitoriProfile:
    customer_code = "nitori"
    display_name = "ニトリ (Nitori) TO GLOBAL"
    priority = 20

    def __init__(self, cost_book: NitoriCostBook | None = None, markup_ratio: Decimal = _MARKUP):
        self._cost = cost_book
        self._markup = markup_ratio

    def detect(self, path: Path, hint: str | None = None) -> bool:
        if hint == self.customer_code:
            return True
        try:
            wb = load_workbook(path, data_only=True, read_only=True)
        except Exception:
            return False
        try:
            return _QUOTE_SHEET in wb.sheetnames
        finally:
            wb.close()

    def parse(self, path: Path, bid_id: str, period: str) -> ParsedPkg:
        wb = load_workbook(path, data_only=True)
        try:
            ws = wb[_QUOTE_SHEET]
            rows: list[PkgRow] = []
            for r in range(_DATA_START_ROW, ws.max_row + 1):
                pol = ws.cell(r, _COL["pol"]).value
                pod = ws.cell(r, _COL["pod"]).value
                size = ws.cell(r, _COL["size"]).value
                if not pol or not pod:
                    continue
                pol_s = str(pol).strip().upper()
                rows.append(PkgRow(
                    row_idx=r, section_index=0, section_code="GLOBAL",
                    origin_code=pol_s, origin_text_raw=str(pol),
                    destination_text_raw=str(pod), destination_code=normalize_pod(str(pod)),
                    cost_type=CostType.UNKNOWN, currency="USD",
                    volume_desc=None, existing_price=None, existing_lead_time=None,
                    existing_carrier=str(ws.cell(r, _COL["carrier"]).value or "") or None,
                    existing_remark=None, is_example=False, client_constraint_text=None,
                    extras={"size": str(size).strip() if size else "",
                            "pod_raw": str(pod), "is_china": pol_s in _CHINA_POLS},
                ))
            section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
            return ParsedPkg(bid_id=bid_id, customer_code=self.customer_code, period=period,
                             sheet_name=_QUOTE_SHEET, source_file=path.name,
                             sections=[section], rows=rows, warnings=[])
        finally:
            wb.close()
