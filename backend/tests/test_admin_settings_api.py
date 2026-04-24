"""admin_settings API 集成测试（T-ST-08）。

覆盖：4 个端点的正常/异常路径；PATCH 后下次 chat 用新配置（拦 httpx）。
"""
import json
from typing import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models import Base
from app.models.app_settings import AppSettings
from app.services import ai_client, config_service


@pytest.fixture
def client_with_isolated_db(monkeypatch, tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "admin_settings_api.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(config_service, "SessionLocal", TestSession)
    monkeypatch.setattr(settings, "vllm_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    config_service.invalidate_cache()

    yield TestClient(app)

    app.dependency_overrides.pop(get_db, None)
    config_service.invalidate_cache()


def test_get_empty_db_all_env(client_with_isolated_db):
    r = client_with_isolated_db.get("/api/v1/admin/settings/ai")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ai_provider"]["source"] == "env"
    assert data["ai_provider"]["value"] == "vllm"
    assert data["vllm_api_key"]["value"]["is_set"] is False
    assert data["vllm_api_key"]["source"] == "env"


def test_patch_updates_and_masks_secret(client_with_isolated_db):
    r = client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai",
        json={"ai_provider": "anthropic", "vllm_api_key": "sk-abc1234XYZW"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ai_provider"]["value"] == "anthropic"
    assert data["ai_provider"]["source"] == "db"
    assert data["vllm_api_key"]["value"]["masked"] == "••••XYZW"
    # 响应里绝无明文
    assert "sk-abc1234XYZW" not in json.dumps(data)


def test_patch_field_not_in_body_keeps_value(client_with_isolated_db):
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai",
        json={"vllm_api_key": "sk-keep1234"},
    )
    # 只改 timeout
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"ai_timeout_seconds": 200}
    )
    r = client_with_isolated_db.get("/api/v1/admin/settings/ai")
    data = r.json()["data"]
    assert data["vllm_api_key"]["value"]["is_set"] is True
    assert data["ai_timeout_seconds"]["value"] == 200


def test_patch_sensitive_null_clears(client_with_isolated_db):
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"vllm_api_key": "sk-xyz"}
    )
    r = client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"vllm_api_key": None}
    )
    data = r.json()["data"]
    assert data["vllm_api_key"]["value"]["is_set"] is False


def test_patch_invalid_value_returns_422(client_with_isolated_db):
    # timeout 超范围
    r = client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"ai_timeout_seconds": 5}
    )
    assert r.status_code == 422

    # base_url 非 http
    r = client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"vllm_base_url": "ftp://x"}
    )
    assert r.status_code == 422

    # 未知字段（extra forbid）
    r = client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"unknown_field": "x"}
    )
    assert r.status_code == 422


def test_test_connection_returns_shape(client_with_isolated_db):
    """当前 provider 无 key → ok=False，结构体字段齐全。"""
    r = client_with_isolated_db.post("/api/v1/admin/settings/ai/test-connection")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"ok", "provider", "latency_ms", "detail"}
    assert data["provider"] in ("vllm", "anthropic")
    # env 里 vllm_api_key 空 → vllm health_check url 仍会请求，但真发出去；这里只断结构不断值
    assert isinstance(data["latency_ms"], int)


def test_reset_deletes_row_and_fallback_env(client_with_isolated_db):
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai",
        json={"ai_provider": "anthropic", "vllm_api_key": "sk-xyz"},
    )
    r = client_with_isolated_db.post("/api/v1/admin/settings/ai/reset")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ai_provider"]["source"] == "env"
    assert data["ai_provider"]["value"] == "vllm"


def test_patch_then_next_chat_uses_new_config(client_with_isolated_db, monkeypatch):
    """核心闭环：PATCH vllm_model 后下次 chat 的 body.model 跟随。"""
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai",
        json={"vllm_model": "test-model-xyz", "vllm_api_key": "sk-fake1234"},
    )

    captured: dict = {}

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

        @property
        def text(self):
            return "OK"

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        captured["auth"] = headers.get("Authorization", "") if headers else ""
        return _FakeResp()

    monkeypatch.setattr(httpx, "post", _fake_post)

    # 下一次 chat 应读到 PATCH 后的新配置
    out = ai_client.chat("sys", "hi", max_tokens=16)
    assert out == "OK"
    assert captured["body"]["model"] == "test-model-xyz", captured["body"]
    assert captured["auth"] == "Bearer sk-fake1234"


def test_patch_then_chat_vllm_key_null_raises(client_with_isolated_db):
    """PATCH vllm_api_key=null 后下次 chat 抛 ProviderUnavailableError."""
    client_with_isolated_db.patch(
        "/api/v1/admin/settings/ai", json={"vllm_api_key": None}
    )
    with pytest.raises(ai_client.ProviderUnavailableError):
        ai_client.chat("sys", "hi", max_tokens=16)
