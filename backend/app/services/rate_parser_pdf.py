"""PDF 运价文件格式分流（与 Excel 的 rate_parser.detect_and_parse 平行）。

现仅识别 ONE 服务合约；别家船司合约 PDF 各自加签名分支。
"""
from __future__ import annotations

import pdfplumber
from sqlalchemy.orm import Session

from app.services.step1_rates.adapters.one_contract_pdf import parse_one_contract_pdf


def _first_page_text(file_path: str) -> str:
    with pdfplumber.open(file_path) as pdf:
        if not pdf.pages:
            return ""
        return (pdf.pages[0].extract_text() or "")


def detect_and_parse_pdf(file_path: str, db: "Session | None" = None) -> dict:
    head = _first_page_text(file_path).upper()
    if "SERVICE CONTRACT" in head and ("ONE" in head or "OCEAN NETWORK EXPRESS" in head):
        return parse_one_contract_pdf(file_path, db)
    return {"error": "无法识别的 PDF 运价格式（当前仅支持 ONE 服务合约）", "parsed_rows": []}
