# backend/tests/sheet_builder/test_ocean_ai_extractor.py
import json
from app.services import ai_client
from app.services.step1_rates.sheet_builder import ocean_ai_extractor

# 取自真实样本 资料/2026.05.27/image001(含LSS+EIS到付+转运稍等)/image002(纯运费)
_FAKE = json.dumps([
    {"origin": "SHANGHAI", "destination": "ICD AHMEDABAD", "carrier": "KMTC",
     "via": "NHAVA SHEVA", "container_20gp": 1650, "container_40gp": 1700,
     "currency": "USD", "valid_to": "2026-03-22",
     "surcharges": [
         {"code": "LSS", "included": True},
         {"code": "EIS", "amount_20": 150, "amount_40": 300, "payment": "collect"},
         {"code": "转运费", "note": "稍等"},
     ]},
    {"destination": "NEW YORK", "carrier": "OOCL", "vessel_voyage": "OOCL TULIP/003E",
     "container_40hq": 3150, "currency": "USD", "valid_to": "2026-03-31", "surcharges": []},
    {"destination": "", "container_20gp": 1000},   # 无目的港 → 跳过
    {"destination": "LAX"},                          # 无箱型价 → 跳过
])


def test_parse_ocean_image_builds_rows_with_surcharges(monkeypatch):
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: _FAKE)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)

    assert out["source_type"] == "ocean_image"
    rows = out["parsed_rows"]
    assert len(rows) == 2            # 两条坏行跳过

    r0 = rows[0]
    assert r0["origin"] == "SHANGHAI"
    assert r0["destination"] == "ICD AHMEDABAD"
    assert r0["carrier"] == "KMTC"
    assert r0["via"] == "NHAVA SHEVA"
    assert r0["is_direct"] is False              # 有中转港 → 非直达
    assert r0["container_20gp"] == 1650.0
    assert r0["container_40gp"] == 1700.0
    assert all(isinstance(r0[k], float) for k in ("container_20gp", "container_40gp"))
    sc = r0["surcharges"]
    assert sc[0] == {"code": "LSS", "amount_20": None, "amount_40": None,
                     "currency": None, "payment": None, "included": True, "note": None}
    assert sc[1]["code"] == "EIS" and sc[1]["amount_20"] == 150.0 and sc[1]["amount_40"] == 300.0
    assert sc[1]["payment"] == "collect" and sc[1]["included"] is False
    assert sc[2]["code"] == "转运费" and sc[2]["note"] == "稍等"
    assert r0["needs_review"] is True            # 附加费含 note(转运稍等) → 标黄

    r1 = rows[1]
    assert r1["destination"] == "NEW YORK"
    assert r1["container_40hq"] == 3150.0
    assert r1["vessel_voyage"] == "OOCL TULIP/003E"
    assert r1["surcharges"] == []
    assert r1["is_direct"] is True               # 无中转
    assert r1["needs_review"] is False           # carrier+valid_to 全, 无 note


def test_parse_ocean_text_same_shape(monkeypatch):
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: _FAKE)
    out = ocean_ai_extractor.parse_ocean_text("一些海运报价文本", db=None)
    assert out["source_type"] == "ocean_text"
    assert len(out["parsed_rows"]) == 2


def test_parse_ocean_image_ai_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("网络炸")
    monkeypatch.setattr(ai_client, "chat_with_image", boom)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)
    assert out["parsed_rows"] == []
    assert any("失败" in w for w in out["warnings"])


def test_missing_carrier_marks_needs_review(monkeypatch):
    fake = json.dumps([{"destination": "BUSAN", "container_20gp": 130, "valid_to": "2026-04-01"}])
    monkeypatch.setattr(ai_client, "chat_with_image", lambda *a, **k: fake)
    out = ocean_ai_extractor.parse_ocean_image("/tmp/o.png", db=None)
    assert out["parsed_rows"][0]["needs_review"] is True   # 缺 carrier
