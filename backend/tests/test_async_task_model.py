"""AsyncTask 模型：建表 + 默认状态 pending + JSON 结果列。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _mk_session(tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401  确保所有表注册

    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_async_task_defaults_pending_and_stores_json(tmp_path):
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    db = _mk_session(tmp_path)
    try:
        t = AsyncTask(id="abc123", task_type="parse_email_text")
        db.add(t)
        db.commit()
        got = db.get(AsyncTask, "abc123")
        assert got.status == AsyncTaskStatus.pending
        assert got.result_json is None
        got.status = AsyncTaskStatus.succeeded
        got.result_json = {"batch_id": "b1", "preview_rows": []}
        db.commit()
        assert db.get(AsyncTask, "abc123").result_json["batch_id"] == "b1"
    finally:
        db.close()
