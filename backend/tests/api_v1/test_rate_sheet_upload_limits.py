"""运价表生成上传限制（2026-06-10 需求）：单次最多 4 个文件、总大小 ≤ 3MB，超出拒绝。

空运/海运共用同一端点，限制对两种模板一体生效。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models as _models  # noqa: F401
    import app.services.async_runner as ar
    from app.core.config import settings

    eng = create_engine(
        f"sqlite:///{tmp_path/'rs.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    monkeypatch.setattr(ar, "SessionLocal", TestSession)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def session_id(monkeypatch):
    from app.services.step1_rates.sheet_builder import orchestrator

    monkeypatch.setattr(
        orchestrator,
        "add_file",
        lambda *a, **k: orchestrator.FileResult(
            name="a.xlsx", source_type="excel", status="parsed"
        ),
    )
    return orchestrator.create_session("air").session_id


def _post_files(client, session_id, files):
    return client.post(f"/api/v1/rate-sheet/{session_id}/files", files=files)


def test_reject_more_than_4_files(client, session_id):
    files = [
        ("files", (f"f{i}.xlsx", b"x", "application/octet-stream")) for i in range(5)
    ]
    resp = _post_files(client, session_id, files)
    body = resp.json()
    assert body["code"] == 400
    assert "4" in body["message"]


def test_reject_total_size_over_3mb(client, session_id):
    big = b"x" * (2 * 1024 * 1024)  # 2MB × 2 = 4MB > 3MB
    files = [
        ("files", ("a.xlsx", big, "application/octet-stream")),
        ("files", ("b.xlsx", big, "application/octet-stream")),
    ]
    resp = _post_files(client, session_id, files)
    body = resp.json()
    assert body["code"] == 400
    assert "3" in body["message"]  # 提示里带上限 3MB


def test_accept_4_small_files(client, session_id):
    files = [
        ("files", (f"f{i}.xlsx", b"x" * 1024, "application/octet-stream"))
        for i in range(4)
    ]
    resp = _post_files(client, session_id, files)
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["task_id"]


def test_reject_leaves_no_orphan_files(client, session_id, tmp_path):
    """拒绝时不留落盘垃圾文件。"""
    big = b"x" * (4 * 1024 * 1024)
    resp = _post_files(
        client, session_id, [("files", ("a.xlsx", big, "application/octet-stream"))]
    )
    assert resp.json()["code"] == 400
    assert list(tmp_path.glob("ratesheet_*")) == []
