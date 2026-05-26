import shutil
from pathlib import Path

from app.services.step2_bidding.bidding_orchestrator import run_auto_fill

NITORI_DIR = (
    Path(__file__).resolve().parents[4]
    / "资料"
    / "2026.05.26"
    / "_nitori_unzip"
    / "ニトリ様海上入札"
)


def test_nitori_end_to_end(tmp_path):
    work = tmp_path / "pkg"
    shutil.copytree(NITORI_DIR, work)
    quote = next(work.glob("*GLOBAL*.xlsm"))
    resp = run_auto_fill(quote, bid_id="bidN", bid_dir=work, db=None)
    assert resp.ok is True
    assert resp.identify.matched_customer == "nitori"
    assert resp.fill.filled_count > 0
    assert resp.download.cost_token and resp.download.sr_token
    assert (work / "cost_nitori_bidN.xlsm").exists()
    assert (work / "sr_nitori_bidN.xlsm").exists()
