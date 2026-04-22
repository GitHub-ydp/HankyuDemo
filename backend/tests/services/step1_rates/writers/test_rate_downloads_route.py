"""T-W5 验收：rate_downloads 路由集成测试（含 404/422/200）。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.rate_downloads import router as rate_downloads_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(rate_downloads_router, prefix="/api/v1")
    return TestClient(app)


def test_download_returns_xlsx_for_valid_air_batch(air_batch_id):
    response = _client().get(f"/api/v1/rate-batches/{air_batch_id}/download")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "spreadsheetml.sheet" in content_type, content_type
    # V-W20: 文件名命中模板
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert "Air" in content_disposition or "%E3%80%90Air" in content_disposition
    assert len(response.content) > 1000  # xlsx 至少 1KB


def test_download_404_for_unknown_batch():
    response = _client().get("/api/v1/rate-batches/does-not-exist/download")
    assert response.status_code == 404


def test_download_422_when_template_file_missing(air_batch_id, tmp_path, monkeypatch):
    """V-W19: draft 存在但模板文件被清理 → 422。"""
    from app.services import rate_batch_service

    draft = rate_batch_service._draft_batches[air_batch_id]
    original_path = draft.file_path
    draft.file_path = str(tmp_path / "missing.xlsx")
    try:
        response = _client().get(f"/api/v1/rate-batches/{air_batch_id}/download")
        assert response.status_code == 422
    finally:
        draft.file_path = original_path


def test_download_succeeds_for_ocean_ngb(ocean_ngb_batch_id):
    response = _client().get(f"/api/v1/rate-batches/{ocean_ngb_batch_id}/download")
    assert response.status_code == 200
    assert len(response.content) > 50_000  # NGB 原件体积较大
