"""POST /rate-sheet/{sid}/commit：审核后的行直接入库(save-from-session)。

验证 HTTP 接线：建会话 → 提交档位行+周表行 → 返回 batch_id/入库数/跳过数；档位行落 air_tier 表。
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'commit.db'}",
        connect_args={"check_same_thread": False},
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _new_air_session(client: TestClient) -> str:
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "air"})
    assert r.status_code == 200
    return r.json()["data"]["session_id"]


def test_commit_persists_tier_rows(client):
    sid = _new_air_session(client)
    rows = [
        {"origin": "PVG", "destination": "KIX", "service": "CK/MU",
         "tier_prices": {"45": 17, "100": 14}, "remark": "含油",
         "effective_week_start": "2026-05-21"},
        {"origin": "PVG", "destination": "BKK", "service": "平散货",
         "tier_prices": {"100": 16, "300": 16}},
        {"origin": "PVG", "destination": "NRT", "service": "CK", "day1": 14},  # 周表行→跳过
    ]
    r = client.post(f"/api/v1/rate-sheet/{sid}/commit", json={"rows": rows})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["tier_rows"] == 2
    assert data["skipped_weekly"] == 1
    assert data["batch_id"]


def test_commit_unknown_session_returns_404(client):
    r = client.post("/api/v1/rate-sheet/nope/commit", json={"rows": []})
    assert r.status_code == 200
    assert r.json()["code"] == 404


def _new_sea_session(client: TestClient) -> str:
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    assert r.status_code == 200
    return r.json()["data"]["session_id"]


def test_commit_dispatches_ocean_path(client):
    sid = _new_sea_session(client)
    rows = [{"origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC",
             "container_20gp": 250, "container_40hq": 500, "transit_days": 3}]
    r = client.post(f"/api/v1/rate-sheet/{sid}/commit", json={"rows": rows})
    assert r.status_code == 200
    data = r.json()["data"]
    assert "fcl_rows" in data                    # 走了 ocean 分流
    assert data["skipped_unresolved"] == 1       # 测试 DB 未 seed 港口/船司 → 解析不到
