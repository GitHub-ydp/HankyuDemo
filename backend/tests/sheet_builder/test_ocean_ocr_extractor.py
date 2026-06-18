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


import pytest


@pytest.mark.parametrize("text,expected", [
    ("$275", 275.0), ("$1,000", 1000.0), ("S1000", 1000.0),   # $ 误读成 S
    ("￥900", 900.0), ("6150", 6150.0), ("-", None), ("", None),
    ("0", None), ("咨询", None),
])
def test_norm_price(text, expected):
    assert ocr._norm_price(text) == expected


def test_assign_token_to_column():
    bands = {"destination": (0, 100), "carrier": (100, 200), "c20": (200, 300)}
    assert ocr._assign(150, bands) == "carrier"
    assert ocr._assign(250, bands) == "c20"


def _grid_with_two_rows():
    blocks = list(_header_row())  # y=30
    # 第1行 y≈90:目的港/船司/三价/两段日期(上下两行) + 水印数字
    blocks += [
        _blk("PIRAEUS", 200, 90), _blk("ONE", 500, 90),
        _blk("$4000", 700, 90), _blk("$6150", 800, 90), _blk("$6150", 900, 90),
        _blk("2026-06-15", 1300, 84), _blk("2026-06-30", 1300, 98),
        _blk("4432", 650, 90),  # 水印,落在 c20/船司之间,应被列绑定丢弃或不入价
    ]
    # 第2行 y≈160
    blocks += [
        _blk("PIRAEUS", 200, 160), _blk("MSC", 500, 160),
        _blk("$4720", 700, 160), _blk("$6640", 800, 160), _blk("$6640", 900, 160),
        _blk("2026-06-15", 1300, 154), _blk("2026-06-30", 1300, 168),
    ]
    return blocks


def test_rows_from_ocr_extracts_correct_fields():
    rows_clustered = ocr._cluster_rows(ocr._blocks_from_result(_grid_with_two_rows()))
    idx, bands = ocr._detect_grid_header(rows_clustered)
    rows, _warns = ocr._rows_from_ocr(rows_clustered, idx, bands, "x.png")
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["destination"] == "PIRAEUS"
    assert r0["carrier"] == "ONE"
    assert (r0["container_20gp"], r0["container_40gp"], r0["container_40hq"]) == (4000.0, 6150.0, 6150.0)
    assert r0["valid_from"] == "2026-06-15" and r0["valid_to"] == "2026-06-30"
    assert r0["currency"] == "USD" and r0["surcharges"] == []
    assert rows[1]["carrier"] == "MSC" and rows[1]["container_20gp"] == 4720.0


class _FakeEngine:
    def __init__(self, result):
        self._result = result
    def __call__(self, _path):
        return self._result, 0.0


def test_parse_ocean_grid_happy(monkeypatch):
    monkeypatch.setattr(ocr, "_get_engine", lambda: _FakeEngine(_grid_with_two_rows()))
    res = ocr.parse_ocean_grid("x.png")
    assert res["total_rows"] == 2
    assert "error" not in res
    assert res["parsed_rows"][0]["destination"] == "PIRAEUS"
    assert res["source_type"] == "ocean_image" and res["file_name"] == "x.png"


def test_parse_ocean_grid_freetext_returns_error(monkeypatch):
    freetext = [_blk("南星船公司上海港出东南亚价格含LSS", 400, 30),
                _blk("Karachi USD2650/2750", 400, 70)]
    monkeypatch.setattr(ocr, "_get_engine", lambda: _FakeEngine(freetext))
    res = ocr.parse_ocean_grid("y.png")
    assert res["parsed_rows"] == [] and "error" in res


def test_parse_ocean_grid_engine_error_returns_error(monkeypatch):
    def _boom():
        raise RuntimeError("no model")
    monkeypatch.setattr(ocr, "_get_engine", _boom)
    res = ocr.parse_ocean_grid("z.png")
    assert res["parsed_rows"] == [] and "error" in res
