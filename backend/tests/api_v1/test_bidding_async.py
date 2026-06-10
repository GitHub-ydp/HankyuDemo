"""bidding /auto-fill 异步化守卫：提交立即返回 task_id。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def test_auto_fill_returns_task_id(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models as _models  # noqa: F401
    import app.api.v1.bidding as bidding
    import app.services.async_runner as ar

    eng = create_engine(
        f"sqlite:///{tmp_path/'bid.db'}", connect_args={"check_same_thread": False}
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
    monkeypatch.setattr(bidding, "_process_auto_fill",
                        lambda content, lower, db: {"ok": True})

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/bidding/auto-fill",
            files={"file": ("bid.xlsx", b"x", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
