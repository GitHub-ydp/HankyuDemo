import time

from app.core import security


def test_password_hash_roundtrip():
    h = security.hash_password("pw123456")
    assert h != "pw123456"               # 不落明文
    assert security.verify_password("pw123456", h) is True
    assert security.verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = security.create_access_token(user_id=42)
    assert security.decode_access_token(token) == 42


def test_jwt_invalid_returns_none():
    assert security.decode_access_token("not-a-token") is None


def test_jwt_expired_returns_none():
    token = security.create_access_token(user_id=7, expires_minutes=-1)
    assert security.decode_access_token(token) is None
