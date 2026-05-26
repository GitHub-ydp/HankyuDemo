from pathlib import Path

from app.services.step2_bidding.customer_identifier import identify

NITORI_DIR = (
    Path(__file__).resolve().parents[4]
    / "资料"
    / "2026.05.26"
    / "_nitori_unzip"
    / "ニトリ様海上入札"
)
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"


def test_identify_nitori_global():
    res = identify(QUOTE_GLOBAL)
    assert res.matched_customer == "nitori"
    assert res.confidence == "high"
