from app.services.step1_rates.sheet_builder import orchestrator


def _ocr_rows():
    return {"parsed_rows": [{"destination": "PIRAEUS", "container_20gp": 4000.0,
                             "carrier": "ONE", "needs_review": False}],
            "total_rows": 1, "source_type": "ocean_image", "file_name": "g.png"}


def test_sea_image_uses_ocr_when_grid(monkeypatch, tmp_path):
    img = tmp_path / "g.png"
    img.write_bytes(b"x")
    called = {"vlm": 0}
    monkeypatch.setattr(orchestrator.ocean_ocr_extractor, "parse_ocean_grid",
                        lambda *a, **k: _ocr_rows())
    monkeypatch.setattr(orchestrator.ocean_ai_extractor, "parse_ocean_image",
                        lambda *a, **k: called.__setitem__("vlm", called["vlm"] + 1) or {"parsed_rows": []})
    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "g.png", str(img), None)
    assert res.status == "parsed" and res.row_count == 1
    assert called["vlm"] == 0  # 命中 OCR,没调 VLM


def test_sea_image_falls_back_to_vlm_when_not_grid(monkeypatch, tmp_path):
    img = tmp_path / "f.png"
    img.write_bytes(b"x")
    called = {"vlm": 0}
    monkeypatch.setattr(orchestrator.ocean_ocr_extractor, "parse_ocean_grid",
                        lambda *a, **k: {"parsed_rows": [], "error": "未检测到规整表头"})
    def _vlm(*a, **k):
        called["vlm"] += 1
        return {"parsed_rows": [{"destination": "HCM", "container_20gp": 525.0,
                                 "carrier": "ANX", "needs_review": False}], "total_rows": 1}
    monkeypatch.setattr(orchestrator.ocean_ai_extractor, "parse_ocean_image", _vlm)
    sess = orchestrator.create_session("sea")
    res = orchestrator.add_file(sess.session_id, "f.png", str(img), None)
    assert called["vlm"] == 1  # OCR 0 行 → 回落 VLM
    assert res.status == "parsed" and res.row_count == 1
