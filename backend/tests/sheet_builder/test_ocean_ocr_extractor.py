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


def test_cluster_rows_groups_by_y_band():
    # 两行,行内多列同 Y;行间 Y 差远大于行内字高
    blocks = ocr._blocks_from_result([
        _blk("ONE", 100, 50), _blk("$275", 300, 52),
        _blk("MSC", 100, 120), _blk("$472", 300, 118),
    ])
    rows = ocr._cluster_rows(blocks)
    assert len(rows) == 2
    assert {b["text"] for b in rows[0]} == {"ONE", "$275"}
    assert {b["text"] for b in rows[1]} == {"MSC", "$472"}
