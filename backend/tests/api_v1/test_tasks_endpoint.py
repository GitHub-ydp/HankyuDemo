"""轮询端点：未知 id → 404；已存在 → 返回 status/result/error。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def _client(tmp_path):
    from app.models.base import Base
    import app.models as _models  # noqa: F401  确保所有表注册，用别名避免覆盖全局 app

    eng = create_engine(
        f"sqlite:///{tmp_path/'tasks.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app), TestSession


def test_unknown_task_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    try:
        resp = client.get("/api/v1/tasks/doesnotexist")
        assert resp.status_code == 200
        assert resp.json()["code"] == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_known_task_returns_status_and_result(tmp_path):
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    client, TestSession = _client(tmp_path)
    try:
        db = TestSession()
        db.add(AsyncTask(
            id="t1", task_type="unit",
            status=AsyncTaskStatus.succeeded, result_json={"batch_id": "b1"},
        ))
        db.commit()
        db.close()

        resp = client.get("/api/v1/tasks/t1")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "succeeded"
        assert body["data"]["result"]["batch_id"] == "b1"
    finally:
        app.dependency_overrides.pop(get_db, None)
