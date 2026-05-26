from pathlib import Path

from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile

NITORI_DIR = Path(__file__).resolve().parents[4] / "资料" / "2026.05.26" / "_nitori_unzip" / "ニトリ様海上入札"
QUOTE_GLOBAL = NITORI_DIR / "_【to GLOBAL】2026年7月～9月_見積り書.xlsm"


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
