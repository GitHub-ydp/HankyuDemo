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

    def match(self, parsed: ParsedPkg) -> list[PerRowReport]:
        assert self._cost is not None, "NitoriProfile.match 需要 cost_book"
        reports: list[PerRowReport] = []
        for row in parsed.rows:
            if not row.extras.get("is_china"):
                continue
            lane = self._cost.lookup(pol=row.origin_code, pod=row.destination_code)
            cost_field = _SIZE_TO_COST.get(row.extras.get("size", ""))
            cost_price = None
            if lane and not lane.no_service and cost_field:
                cost_price = getattr(lane, f"rate_{cost_field}")
            if cost_price is None:
                reports.append(PerRowReport(
                    row_idx=row.row_idx, section_code="GLOBAL",
                    destination_code=row.destination_code, status=RowStatus.NO_RATE,
                    cost_price=None, sell_price=None, markup_ratio=None,
                    lead_time_text=None, carrier_text=None, remark_text=None,
                    selected_candidate=None))
                continue
            sell = (cost_price * self._markup).quantize(Decimal("1"))
            reports.append(PerRowReport(
                row_idx=row.row_idx, section_code="GLOBAL",
                destination_code=row.destination_code, status=RowStatus.FILLED,
                cost_price=cost_price, sell_price=sell, markup_ratio=self._markup,
                lead_time_text=lane.transit_time, carrier_text=lane.carrier,
                remark_text=None, selected_candidate=None))
        return reports

    def fill(self, source_path: Path, parsed: ParsedPkg,
             row_reports: list[PerRowReport], variant: str, output_path: Path):
        if variant not in ("cost", "sr"):
            raise ValueError(f"variant 必须 cost/sr，实际 {variant!r}")
        shutil.copy2(source_path, output_path)
        wb = load_workbook(output_path, data_only=False, keep_vba=True)   # 保宏
        try:
            ws = wb[_QUOTE_SHEET]
            for rep in row_reports:
                if rep.status != RowStatus.FILLED:
                    continue
                price = rep.cost_price if variant == "cost" else rep.sell_price
                self._set(ws, rep.row_idx, "of_cur", "USD")
                self._set(ws, rep.row_idx, "of_amt", float(price))
                self._set(ws, rep.row_idx, "lss_cur", "USD")
                self._set(ws, rep.row_idx, "lss_amt", 0)          # Included→0（assumption）
                if rep.lead_time_text:
                    self._set(ws, rep.row_idx, "tt", rep.lead_time_text)
                ft = self._cost.free_time_for(rep.destination_code) if self._cost else None
                if ft:
                    self._set(ws, rep.row_idx, "dem_free", ft.get("dem"))
                    self._set(ws, rep.row_idx, "det_free", ft.get("det"))
            stamp_document_properties(wb, batch_id=f"{parsed.bid_id}:nitori:{variant}")
            wb.save(output_path)
        finally:
            wb.close()

    @staticmethod
    def _set(ws, row_idx: int, col_key: str, value):
        if value is None:
            return
        cell = ws.cell(row_idx, _COL[col_key])
        if is_formula_cell(cell):
            return
        safe_set(cell, value)
