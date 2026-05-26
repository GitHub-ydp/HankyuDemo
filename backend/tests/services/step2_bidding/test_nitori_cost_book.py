from decimal import Decimal
from pathlib import Path
import extract_msg
from app.services.step2_bidding.nitori_cost_book import NitoriCostBook

NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
COST_MSG = NITORI_DIR / "②（Cost）回复 HHESHA内部　転送 ニトリ海上運賃入札（2026年2Q7－９月）.msg"

def _extract_cost(tmp_path):
    m = extract_msg.Message(str(COST_MSG))
    for a in m.attachments:
        name = a.longFilename or a.shortFilename or ""
        if name.lower().endswith(".xlsx"):
            p = tmp_path / name
            p.write_bytes(a.data)
            m.close()
            return p
    raise AssertionError("cost xlsx not found in msg")

def test_cost_book_parses_shanghai_lanes(tmp_path):
    book = NitoriCostBook.from_xlsx(_extract_cost(tmp_path))
    lane = book.lookup(pol="SHANGHAI", pod="PORT KLANG")
    assert lane is not None
    assert lane.rate_20gp == Decimal("580")
    assert lane.rate_40hc == Decimal("1160")
    assert lane.no_service is False

def test_cost_book_marks_taicang_klang_no_service(tmp_path):
    book = NitoriCostBook.from_xlsx(_extract_cost(tmp_path))
    lane = book.lookup(pol="TAICANG", pod="PORT KLANG")
    assert lane is not None and lane.no_service is True

def test_cost_book_free_time(tmp_path):
    book = NitoriCostBook.from_xlsx(_extract_cost(tmp_path))
    assert book.free_time_for("PORT KLANG") == {"dem": 28, "det": 7}
