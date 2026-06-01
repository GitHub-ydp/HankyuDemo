# backend/tests/sheet_builder/test_air_ai_extractor.py
import json
from app.services import ai_client
from app.services.step1_rates.sheet_builder import air_ai_extractor

_FAKE = json.dumps([
    {"origin": "PVG", "destination": "LAX", "carrier": "CK/CA/KE",
     "cargo_class": "普货", "packing": "托", "density": "1:167",
     "tier_prices": {"45": 60, "100": 60, "500": 60, "1000": 60},
     "currency": "CNY", "effective_from": "2026-05-26", "effective_to": "2026-05-29",
     "remark": "全程2-4天"},
    {"origin": "PVG", "destination": "LAX", "carrier": "CK/CA/KE",
     "cargo_class": "普货", "packing": "托", "density": "1:1000",
     "tier_prices": {"100": 36}, "currency": "CNY"},
    {"destination": "", "tier_prices": {"100": 50}},   # 无目的港 → 跳过
    {"destination": "ORD", "tier_prices": {}},          # 无档位价 → 跳过
])


def test_parse_air_image_builds_multidim_rows(monkeypatch):
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: _FAKE)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)

    assert out["source_type"] == "air_image"
    rows = out["parsed_rows"]
    assert len(rows) == 2          # 两条坏行被跳过
    r0 = rows[0]
    assert r0["destination"] == "LAX"
    assert r0["carrier"] == "CK/CA/KE"
    assert r0["cargo_class"] == "普货"
    assert r0["packing"] == "托"
    assert r0["density"] == "1:167"
    assert r0["tier_prices"] == {45: 60.0, 100: 60.0, 500: 60.0, 1000: 60.0}
    assert all(isinstance(v, float) for v in r0["tier_prices"].values())
    assert r0["currency"] == "CNY"
    assert r0["origin"] == "PVG"
    assert r0["effective_week_start"] == "2026-05-26"
    assert r0["effective_to"] == "2026-05-29"
    assert r0["multi_flight_pick"] is True
    assert rows[1]["density"] == "1:1000" and rows[1]["tier_prices"] == {100: 36.0}


def test_parse_air_text_same_shape(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: _FAKE)
    out = air_ai_extractor.parse_air_text("一些空运报价文本", db=None)
    assert out["source_type"] == "air_text"
    assert len(out["parsed_rows"]) == 2


def test_parse_air_image_ai_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)
    assert out["parsed_rows"] == []
    assert any("失败" in w for w in out["warnings"])


def test_default_currency_japan_origin(monkeypatch):
    fake = json.dumps([{"origin": "NRT", "destination": "PVG", "tier_prices": {"100": 500}}])
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: fake)
    out = air_ai_extractor.parse_air_image("/tmp/air.png", db=None)
    assert out["parsed_rows"][0]["currency"] == "JPY"
