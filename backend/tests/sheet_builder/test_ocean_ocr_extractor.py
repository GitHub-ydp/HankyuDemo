from app.services.step1_rates.sheet_builder import ocean_ocr_extractor as ocr


def _blk(text, xc, yc, w=44, h=18):
    x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, 0.99


def test_blocks_from_result_normalizes_and_drops_empty():
    result = [_blk("ONE", 100, 50), _blk("  ", 200, 50), _blk("$275", 300, 50)]
    blocks = ocr._blocks_from_result(result)
    assert [b["text"] for b in blocks] == ["ONE", "$275"]
    assert blocks[0]["xc"] == 100 and blocks[0]["yc"] == 50
    assert blocks[0]["xl"] < blocks[0]["xc"] < blocks[0]["xr"]
