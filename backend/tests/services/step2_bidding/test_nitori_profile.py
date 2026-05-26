from decimal import Decimal
from pathlib import Path

import extract_msg

from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
from app.services.step2_bidding.entities import RowStatus
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook

NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"
COST_MSG = NITORI_DIR / "②（Cost）回复 HHESHA内部　転送 ニトリ海上運賃入札（2026年2Q7－９月）.msg"


def _cost_book(tmp_path):
    m = extract_msg.Message(str(COST_MSG))
    for a in m.attachments:
        n = a.longFilename or a.shortFilename or ""
        if n.lower().endswith(".xlsx"):
            p = tmp_path / n
            p.write_bytes(a.data)
            m.close()
            return NitoriCostBook.from_xlsx(p)
    raise AssertionError("no cost xlsx")


def test_nitori_detect():
    assert NitoriProfile().detect(QUOTE_GLOBAL) is True


def test_nitori_parse_china_rows():
    parsed = NitoriProfile().parse(QUOTE_GLOBAL, bid_id="b1", period="2026Q2")
    china = [r for r in parsed.rows if r.origin_code in ("SHANGHAI", "TAICANG")]
    assert len(china) == 48
    r114 = next(r for r in parsed.rows if r.row_idx == 114)
    assert r114.origin_code == "SHANGHAI"
    assert r114.destination_code == "PORT KLANG"
    assert r114.extras["size"] == "20F"
    assert r114.extras["pod_raw"] == "PORT KLANG (NORTH)"
    assert r114.extras["is_china"] is True


def test_nitori_match_filled_and_norate(tmp_path):
    prof = NitoriProfile(cost_book=_cost_book(tmp_path))
    parsed = prof.parse(QUOTE_GLOBAL, bid_id="b1", period="2026Q2")
    reports = prof.match(parsed)
    by_row = {rp.row_idx: rp for rp in reports}
    # r114 SHANGHAI->PORT KLANG(NORTH) 20F 命中 580
    assert by_row[114].status == RowStatus.FILLED
    assert by_row[114].cost_price == Decimal("580")
    assert by_row[114].sell_price == Decimal("667")          # 580*1.15=667
    # r120 TAICANG->PORT KLANG 成本 NO SERVICE → no_rate
    assert by_row[120].status == RowStatus.NO_RATE
    # 非中国发行不进 report（如第 9 行 OSAKA）
    assert 9 not in by_row
