"""config_service 单元测试（T-ST-08）。

覆盖：get / update / invalidate / TTL / reset / mask_secret / 敏感字段三态。
用独立 SQLite DB 文件，避免串台。
"""
import os
import tempfile
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Base
from app.models.app_settings import AppSettings
from app.schemas.app_settings import AIConfigPatch
from app.services import config_service


@pytest.fixture
def isolated_db(monkeypatch, tmp_path) -> Iterator:
    """给每个测试单独的 SQLite DB + SessionLocal，避免串台。"""
    db_path = tmp_path / "config_service_test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    # Monkey-patch config_service 的 SessionLocal，让 get_ai_config(db=None) 也读这个库
    monkeypatch.setattr(config_service, "SessionLocal", TestSession)

    # 清空 env 敏感字段，方便测 source
    monkeypatch.setattr(settings, "vllm_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    config_service.invalidate_cache()
    yield TestSession
    config_service.invalidate_cache()


def test_get_ai_config_empty_db_returns_env_defaults(isolated_db):
    cfg = config_service.get_ai_config()
    assert cfg.ai_provider == settings.ai_provider
    assert cfg.vllm_model == settings.vllm_model
    assert cfg.vllm_api_key == ""  # env 已清空


def test_get_ai_config_empty_db_response_sources_all_env(isolated_db):
    db = isolated_db()
    resp = config_service.get_ai_config_response(db)
    for field_name in [
        "ai_provider", "ai_timeout_seconds", "vllm_base_url",
        "vllm_api_key", "anthropic_api_key", "ai_max_tokens_cap",
    ]:
        fws = getattr(resp, field_name)
        assert fws.source == "env", f"{field_name} should be env, got {fws.source}"
    db.close()


def test_get_ai_config_partial_db_fallback(isolated_db):
    """DB 里只写 ai_provider，其他字段 source=env。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(ai_provider="anthropic"), db=db)
    resp = config_service.get_ai_config_response(db)
    assert resp.ai_provider.source == "db"
    assert resp.ai_provider.value == "anthropic"
    assert resp.ai_timeout_seconds.source == "env"
    assert resp.vllm_base_url.source == "env"
    db.close()


def test_update_sensitive_field_encoded_in_db(isolated_db):
    """敏感字段 DB 落盘必须 base64，不可明文。"""
    db = isolated_db()
    plaintext = "sk-secret9999xyz"
    config_service.update_ai_config(AIConfigPatch(vllm_api_key=plaintext), db=db)

    row = db.query(AppSettings).filter_by(id=1).first()
    assert row.vllm_api_key_encoded is not None
    assert row.vllm_api_key_encoded != plaintext
    import base64
    assert base64.b64decode(row.vllm_api_key_encoded).decode() == plaintext
    db.close()


def test_update_sensitive_null_clears(isolated_db):
    """先 set 再 null → 清空（is_set=False，source 回 env）。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(vllm_api_key="sk-xyz1234"), db=db)
    assert config_service.get_ai_config().vllm_api_key == "sk-xyz1234"

    config_service.update_ai_config(AIConfigPatch(vllm_api_key=None), db=db)
    resp = config_service.get_ai_config_response(db)
    assert resp.vllm_api_key.value.is_set is False
    assert resp.vllm_api_key.source == "env"
    assert config_service.get_ai_config().vllm_api_key == ""
    db.close()


def test_update_field_not_in_set_keeps_original(isolated_db):
    """未 set 的字段保持 DB 原值。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(ai_provider="anthropic", vllm_api_key="sk-abc"), db=db)
    # 只改 timeout
    config_service.update_ai_config(AIConfigPatch(ai_timeout_seconds=200), db=db)
    resp = config_service.get_ai_config_response(db)
    assert resp.ai_provider.value == "anthropic"
    assert resp.vllm_api_key.value.is_set is True
    assert resp.ai_timeout_seconds.value == 200
    db.close()


def test_invalidate_cache_forces_reload(isolated_db):
    """缓存命中后手改 DB；未 invalidate 读旧值，invalidate 后读新值。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(ai_provider="anthropic"), db=db)
    # 命中
    assert config_service.get_ai_config().ai_provider == "anthropic"

    # 手改 DB 绕过 update_ai_config
    row = db.query(AppSettings).filter_by(id=1).first()
    row.ai_provider = "vllm"
    db.commit()

    # 未 invalidate 应仍 anthropic
    assert config_service.get_ai_config().ai_provider == "anthropic"

    # invalidate 后读到 vllm
    config_service.invalidate_cache()
    assert config_service.get_ai_config().ai_provider == "vllm"
    db.close()


def test_ttl_auto_reload_after_30s(isolated_db):
    """TTL 过期后自动重读 DB（用直接改 loaded_at 模拟）。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(ai_provider="anthropic"), db=db)
    config_service.get_ai_config()  # 命中缓存
    assert config_service._cache is not None

    # 手改 DB
    row = db.query(AppSettings).filter_by(id=1).first()
    row.ai_provider = "vllm"
    db.commit()

    # 拉老 loaded_at
    config_service._cache.loaded_at -= 60
    assert config_service.get_ai_config().ai_provider == "vllm"
    db.close()


def test_reset_to_defaults_deletes_row(isolated_db):
    """reset 后 DB 无行，所有 source=env。"""
    db = isolated_db()
    config_service.update_ai_config(
        AIConfigPatch(ai_provider="anthropic", vllm_api_key="sk-xyz"), db=db
    )
    assert db.query(AppSettings).filter_by(id=1).first() is not None

    resp = config_service.reset_to_defaults(db=db)
    assert db.query(AppSettings).filter_by(id=1).first() is None
    assert resp.ai_provider.source == "env"
    assert resp.vllm_api_key.source == "env"
    assert resp.vllm_api_key.value.is_set is False
    db.close()


def test_mask_secret_shows_last_4():
    m = config_service.mask_secret("sk-abcdef1234VwH7")
    assert m.masked == "••••VwH7"
    assert m.is_set is True


def test_mask_secret_short_string():
    m = config_service.mask_secret("abc")
    assert m.masked == "••••abc"
    assert m.is_set is True


def test_mask_secret_empty_not_set():
    m = config_service.mask_secret("")
    assert m.masked == ""
    assert m.is_set is False


def test_update_ai_config_invalidates_cache_after_commit(isolated_db):
    """commit 成功才 invalidate；读后立即看到新值。"""
    db = isolated_db()
    config_service.update_ai_config(AIConfigPatch(ai_provider="vllm"), db=db)
    config_service.get_ai_config()  # 缓存
    config_service.update_ai_config(AIConfigPatch(ai_provider="anthropic"), db=db)
    # update 后第一次 get 应读到新值（说明 invalidate 有效）
    assert config_service.get_ai_config().ai_provider == "anthropic"
    db.close()
