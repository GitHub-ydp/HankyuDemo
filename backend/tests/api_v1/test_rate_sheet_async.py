"""rate-sheet /files 异步化守卫：提交立即返回 task_id。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def test_rate_sheet_files_returns_task_id(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models as _models  # noqa: F401
    from app.services.step1_rates.sheet_builder import orchestrator
    import app.services.async_runner as ar

    eng = create_engine(
        f"sqlite:///{tmp_path/'rs.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    monkeypatch.setattr(ar, "SessionLocal", TestSession)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db

    session = orchestrator.create_session("air")
    monkeypatch.setattr(orchestrator, "add_file", lambda *a, **k: orchestrator.FileResult(
        name="a.xlsx", source_type="excel", status="parsed"))

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rate-sheet/{session.session_id}/files",
            files={"files": ("a.xlsx", b"x", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
