"""后台执行器：work 成功→succeeded+result_json；抛错→failed+error。

用 tmp-file SQLite + monkeypatch SessionLocal，保证后台线程与测试线程
看到同一个库（file 库跨线程可见）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _patch_sessionlocal(monkeypatch, tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401

    eng = create_engine(
        f"sqlite:///{tmp_path/'runner.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)

    import app.services.async_runner as ar
    monkeypatch.setattr(ar, "SessionLocal", TestSession)
    return TestSession


def test_submit_success_marks_succeeded(monkeypatch, tmp_path):
    import app.services.async_runner as ar
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    TestSession = _patch_sessionlocal(monkeypatch, tmp_path)
    db = TestSession()
    task_id = ar.create_task(db, "unit")
    db.close()

    fut = ar.submit(task_id, lambda task_db: {"ok": True})
    fut.result(timeout=5)

    check = TestSession()
    t = check.get(AsyncTask, task_id)
    assert t.status == AsyncTaskStatus.succeeded
    assert t.result_json == {"ok": True}
    check.close()


def test_submit_failure_marks_failed(monkeypatch, tmp_path):
    import app.services.async_runner as ar
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    TestSession = _patch_sessionlocal(monkeypatch, tmp_path)
    db = TestSession()
    task_id = ar.create_task(db, "unit")
    db.close()

    def boom(task_db):
        raise ValueError("explode")

    fut = ar.submit(task_id, boom)
    fut.result(timeout=5)

    check = TestSession()
    t = check.get(AsyncTask, task_id)
    assert t.status == AsyncTaskStatus.failed
    assert "explode" in (t.error or "")
    check.close()
