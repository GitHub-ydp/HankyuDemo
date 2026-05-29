"""rate_sheet API 端到端测试：session → 上传(mock parser) → preview → download。

parser mock，不打真实 AI；db 用 None override（mock parser 不读 db）。
"""
import pytest
from fastapi.testclient import TestClient

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


def test_rate_sheet_end_to_end(client, monkeypatch):
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

    # 1) 建会话
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    session_id = body["data"]["session_id"]
    assert body["data"]["template_type"] == "sea"

    # 2) 上传文件（mock parser）
    r = client.post(
        f"/api/v1/rate-sheet/{session_id}/files",
        files=[("files", ("kmtc.xlsx", b"fake-bytes", "application/vnd.ms-excel"))],
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["files"][0]["status"] == "parsed"
    assert data["summary"]["total_rows"] == 1

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

    rows = [{"destination": "OSAKA", "carrier": "ONE", "freight_20": 111, "freight_40": 222}]
    r = client.post(f"/api/v1/rate-sheet/{sid}/download", json={"rows": rows})

    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx = zip
    ws = load_workbook(BytesIO(r.content))["JP N RATE FCL & LCL"]
    assert ws.cell(9, 1).value == "OSAKA"  # 数据起始行 r9, A=目的港
    assert ws.cell(9, 4).value == 111      # D=运费, 20FT 行取 freight_20


def test_download_post_unknown_session_404(client):
    r = client.post("/api/v1/rate-sheet/does-not-exist/download", json={"rows": []})
    assert r.json()["code"] == 404
