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


def _header_row():
    # 完整表头(含中间未知列),X 递增。返回 RapidOCR result。
    cols = ["起运港/码头", "目的港/码头", "舱位", "船期", "船司", "航线",
            "20'GP", "40'GP", "40'HQ", "45'HQ", "40'NOR", "历史", "有效期", "操作"]
    return [_blk(c, 100 + i * 100, 30) for i, c in enumerate(cols)]


def test_detect_grid_header_returns_bands():
    rows = ocr._cluster_rows(ocr._blocks_from_result(_header_row()))
    found = ocr._detect_grid_header(rows)
    assert found is not None
    idx, bands = found
    assert idx == 0
    for col in ("destination", "carrier", "c20", "c40gp", "c40hq", "valid"):
        assert col in bands


def test_detect_grid_header_bands_separate_neighbors():
    # carrier 列的 X 落进 carrier band,不串到 destination
    rows = ocr._cluster_rows(ocr._blocks_from_result(_header_row()))
    _idx, bands = ocr._detect_grid_header(rows)
    carrier_xc = 100 + 4 * 100  # 船司在第5个(idx4)
    l, r = bands["carrier"]
    assert l <= carrier_xc < r


def test_detect_grid_header_none_on_freetext():
    rows = ocr._cluster_rows(ocr._blocks_from_result([
        _blk("南星船公司上海港出东南亚价格含LSS", 400, 30),
        _blk("Karachi USD2650/2750 巴生中转", 400, 70),
    ]))
    assert ocr._detect_grid_header(rows) is None
