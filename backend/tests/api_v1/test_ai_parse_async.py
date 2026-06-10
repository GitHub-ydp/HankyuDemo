"""AI 端点异步化守卫：提交立即返回 task_id，真正解析在后台执行器跑。"""
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def _client(tmp_path):
    from app.models.base import Base
    import app.models as _models  # noqa: F401  确保所有表注册（别名避免 shadow app）

    eng = create_engine(
        f"sqlite:///{tmp_path/'aip.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    import app.services.async_runner as ar
    ar_session = sessionmaker(bind=eng)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app), TestSession, ar, ar_session


def test_parse_email_text_returns_task_id_then_polls(tmp_path, monkeypatch):
    import app.api.v1.ai_parse as ai_parse

    client, TestSession, ar, ar_session = _client(tmp_path)
    monkeypatch.setattr(ar, "SessionLocal", ar_session)

    def fake_parse(text, db):
        return {
            "batch_id": "b1", "total_rows": 1, "parsed_rows": [{"x": 1}],
            "carrier_code": "C", "warnings": [],
        }

    monkeypatch.setattr(ai_parse, "parse_email_text", fake_parse)

    try:
        submit = client.post("/api/v1/ai/parse-email-text", data={"text": "hi"})
        assert submit.status_code == 200
        task_id = submit.json()["data"]["task_id"]
        assert task_id

        poll = None
        for _ in range(50):
            poll = client.get(f"/api/v1/tasks/{task_id}").json()["data"]
            if poll["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert poll["status"] == "succeeded"
        assert poll["result"]["batch_id"] == "b1"
        assert poll["result"]["total_rows"] == 1
        assert len(poll["result"]["preview_rows"]) == 1  # parsed_rows 1 行 → preview 1 行
    finally:
        app.dependency_overrides.pop(get_db, None)
