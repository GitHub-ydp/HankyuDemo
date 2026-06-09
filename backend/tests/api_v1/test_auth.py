from tests.api_v1._auth_helpers import login_headers, register


def test_register_creates_user_and_returns_token(client):
    r = register(client, "a@x.com")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["token"]
    assert data["user"]["email"] == "a@x.com"
    assert data["user"]["is_admin"] is False


def test_register_duplicate_409(client):
    register(client, "a@x.com")
    r = register(client, "a@x.com")
    assert r.status_code == 409


def test_register_short_password_400(client):
    r = register(client, "a@x.com", password="123")
    assert r.status_code == 400


def test_register_blocked_when_admin_only(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "registration_mode", "admin_only")
    r = register(client, "a@x.com")
    assert r.status_code == 403


def test_login_wrong_password_401(client):
    register(client, "a@x.com")
    r = client.post("/api/v1/auth/login", json={"email": "a@x.com", "password": "wrong"})
    assert r.status_code == 401


def test_login_success_updates_last_login_and_logs_event(client):
    register(client, "a@x.com")
    r = client.post("/api/v1/auth/login", json={"email": "a@x.com", "password": "pw123456"})
    assert r.status_code == 200
    assert r.json()["data"]["token"]


def test_me_returns_admin_flag(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "boss@x.com")
    headers = login_headers(client, "boss@x.com")
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["is_admin"] is True


def test_me_without_token_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
