"""真图集成测试:跑真 RapidOCR 引擎。真图不入 git,放本地 OCR_SAMPLE_DIR(默认见下),缺失则 skip。"""
import os
import pytest

from app.services.step1_rates.sheet_builder import ocean_ocr_extractor as ocr

SAMPLE_DIR = os.environ.get(
    "OCEAN_OCR_SAMPLE_DIR",
    os.path.expanduser("~/Desktop/未命名文件夹"),
)

# (文件名, 期望行数, {船司: (20gp,40gp,40hq)})
CASES = [
    ("231c95611ea3bb8efec64812a78fed1c.png", 2,
     {"ONE": (4000, 6150, 6150), "MSC": (4720, 6640, 6640)}),
    ("efdc45ac4ed47e77dae30910693ccb22.png", 6,
     {"JJ": (275, 500, 500), "YML": (475, 900, 900)}),
    ("fac4e0b719c8f0840804f054fa6e5aa6.png", 5,
     {"JJ": (475, 900, 900), "YML": (575, 1150, 1150)}),
]


@pytest.mark.parametrize("fname,n_rows,checks", CASES)
def test_real_grid_images(fname, n_rows, checks):
    path = os.path.join(SAMPLE_DIR, fname)
    if not os.path.exists(path):
        pytest.skip(f"真图样本缺失,跳过: {path}")
    res = ocr.parse_ocean_grid(path)
    assert "error" not in res, res.get("error")
    assert res["total_rows"] == n_rows
    by_carrier = {r["carrier"]: r for r in res["parsed_rows"]}
    for carrier, (c20, c40gp, c40hq) in checks.items():
        assert carrier in by_carrier, f"缺船司 {carrier}"
        r = by_carrier[carrier]
        assert (r["container_20gp"], r["container_40gp"], r["container_40hq"]) == (c20, c40gp, c40hq)
