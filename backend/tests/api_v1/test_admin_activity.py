from app.core.config import settings
from tests.api_v1._auth_helpers import login_headers, register


def test_non_admin_forbidden(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "user@x.com")
    headers = login_headers(client, "user@x.com")
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403


def test_no_token_unauthorized(client):
    assert client.get("/api/v1/admin/users").status_code == 401


def test_admin_lists_users_with_summary(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "boss@x.com")
    register(client, "u1@x.com")
    headers = login_headers(client, "boss@x.com")
    r = client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["active"] == 2
    emails = {row["email"] for row in data["items"]}
    assert emails == {"boss@x.com", "u1@x.com"}
    boss_row = next(r for r in data["items"] if r["email"] == "boss@x.com")
    assert boss_row["is_admin"] is True
    assert boss_row["last_login_at"] is not None


def test_admin_login_events(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "boss@x.com")
    headers = login_headers(client, "boss@x.com")
    r = client.get("/api/v1/admin/login-events", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 2
    assert data["items"][0]["email"] == "boss@x.com"


def test_admin_operations_merges_two_tables(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "boss@x.com")
    headers = login_headers(client, "boss@x.com")
    import uuid
    from app.api.deps import get_db
    from app.main import app
    from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
    from app.models.upload_log import UploadLog, UploadStatus
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    db.add(UploadLog(batch_id="b1", file_name="a.xlsx", file_type="xlsx",
                     source_type="excel", records_parsed=10, records_imported=9,
                     status=UploadStatus.completed, uploaded_by="boss@x.com"))
    db.add(ImportBatch(batch_id=uuid.uuid4(), file_type=ImportBatchFileType.ocean,
                       source_file="c.xlsx", row_count=5,
                       status=ImportBatchStatus.active, imported_by="boss@x.com"))
    db.commit()
    r = client.get("/api/v1/admin/operations", headers=headers)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    sources = {it["source"] for it in items}
    assert sources == {"ai_confirm", "import"}
