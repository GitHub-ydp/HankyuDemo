"""PDF 格式分流测试。"""
import app.services.rate_parser_pdf as rpp


def test_dispatch_one_contract(monkeypatch):
    # 首页文本含 ONE 合约签名 → 路由到 parse_one_contract_pdf
    monkeypatch.setattr(rpp, "_first_page_text", lambda path: "ONE SERVICE CONTRACT NO. LAX0751N25")
    monkeypatch.setattr(rpp, "parse_one_contract_pdf",
                        lambda path, db: {"parsed_rows": [{"x": 1}], "carrier_code": "ONE", "warnings": []})
    out = rpp.detect_and_parse_pdf("/fake.pdf", db=None)
    assert out["carrier_code"] == "ONE"
    assert out["parsed_rows"] == [{"x": 1}]


def test_dispatch_unknown_returns_error(monkeypatch):
    monkeypatch.setattr(rpp, "_first_page_text", lambda path: "SOME UNRELATED INVOICE")
    out = rpp.detect_and_parse_pdf("/fake.pdf", db=None)
    assert "error" in out
    assert out.get("parsed_rows", []) == []
