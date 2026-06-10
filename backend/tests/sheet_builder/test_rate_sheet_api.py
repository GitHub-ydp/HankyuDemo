"""rate_sheet API 端到端测试：session → 上传(mock parser) → preview → download。

parser mock，不打真实 AI；db 用 None override（mock parser 不读 db）。
"""
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app
from app.services import rate_parser


@pytest.fixture
def client():
    def _override_get_db():
        yield None

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_rate_sheet_end_to_end(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models as _models  # noqa: F401
    import app.services.async_runner as ar

    eng = create_engine(
        f"sqlite:///{tmp_path / 'rs_e2e.db'}", connect_args={"check_same_thread": False}
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

    fake = {
        "parsed_rows": [
            {
                "destination_port_name": "BUSAN",
                "carrier_name": "SJJ",
                "container_20gp": 130,
                "container_40gp": 260,
            }
        ],
        "carrier_code": "KMTC",
        "warnings": [],
    }
    monkeypatch.setattr(rate_parser, "detect_and_parse", lambda p, db: fake)

    try:
        client = TestClient(app)

        # 1) 建会话
        r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        session_id = body["data"]["session_id"]
        assert body["data"]["template_type"] == "sea"

        # 2) 上传文件（mock parser）—— 异步化后立即返回 task_id，task 在后台线程执行
        r = client.post(
            f"/api/v1/rate-sheet/{session_id}/files",
            files=[("files", ("kmtc.xlsx", b"fake-bytes", "application/vnd.ms-excel"))],
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["task_id"]

        # 等后台 task 完成（同进程 ThreadPoolExecutor，轮询 /tasks/{id}）
        task_id = data["task_id"]
        tr = None
        for _ in range(30):
            tr = client.get(f"/api/v1/tasks/{task_id}")
            if tr.json()["data"]["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert tr is not None and tr.json()["data"]["status"] == "succeeded"

        # 3) 预览
        r = client.get(f"/api/v1/rate-sheet/{session_id}/preview")
        rows = r.json()["data"]["rows"]
        assert rows[0]["destination"] == "BUSAN"
        assert rows[0]["freight_20"] == 130

        # 4) 下载填好的模板（xlsx = zip，magic PK）
        r = client.get(f"/api/v1/rate-sheet/{session_id}/download")
        assert r.status_code == 200
        assert r.content[:2] == b"PK"
        assert len(r.content) > 2000
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_session_bad_type(client):
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "rail"})
    assert r.json()["code"] == 400


def test_preview_unknown_session_404(client):
    r = client.get("/api/v1/rate-sheet/does-not-exist/preview")
    assert r.json()["code"] == 404


def test_download_post_fills_given_rows(client):
    from io import BytesIO

    from openpyxl import load_workbook

    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    sid = r.json()["data"]["session_id"]

    rows = [{"destination": "OSAKA", "carrier": "ONE",
             "container_20gp": 111, "container_40gp": 222, "container_40hq": 225}]
    r = client.post(f"/api/v1/rate-sheet/{sid}/download", json={"rows": rows})

    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx = zip
    ws = load_workbook(BytesIO(r.content))["JP N RATE FCL & LCL"]
    assert ws.cell(9, 1).value == "OSAKA"   # 数据起始行 r9, A=目的港
    assert ws.cell(9, 3).value == "20FT"
    assert ws.cell(9, 4).value == 111       # D=运费, 20FT 取 container_20gp
    assert ws.cell(10, 3).value == "40GP"
    assert ws.cell(10, 4).value == 222
    assert ws.cell(11, 3).value == "40HQ"
    assert ws.cell(11, 4).value == 225


def test_download_post_unknown_session_404(client):
    r = client.post("/api/v1/rate-sheet/does-not-exist/download", json={"rows": []})
    assert r.json()["code"] == 404
