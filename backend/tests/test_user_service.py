import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, LoginEvent
from app.services import user_service


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'s.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_user_hashes_and_normalizes(tmp_path):
    db = _session(tmp_path)
    u = user_service.create_user(db, "  A@X.COM ", "pw123456", " Alice ")
    assert u.email == "a@x.com"
    assert u.name == "Alice"
    assert u.password_hash != "pw123456"


def test_create_user_duplicate_raises(tmp_path):
    db = _session(tmp_path)
    user_service.create_user(db, "a@x.com", "pw123456", "A")
    with pytest.raises(user_service.EmailExistsError):
        user_service.create_user(db, "a@x.com", "pw999999", "A2")


def test_authenticate(tmp_path):
    db = _session(tmp_path)
    user_service.create_user(db, "a@x.com", "pw123456", "A")
    assert user_service.authenticate(db, "a@x.com", "pw123456") is not None
    assert user_service.authenticate(db, "a@x.com", "wrong") is None
    assert user_service.authenticate(db, "no@x.com", "pw123456") is None


def test_record_login_updates_and_logs(tmp_path):
    db = _session(tmp_path)
    u = user_service.create_user(db, "a@x.com", "pw123456", "A")
    user_service.record_login(db, u, "9.9.9.9")
    assert u.last_login_at is not None
    ev = db.query(LoginEvent).one()
    assert ev.ip == "9.9.9.9"
    assert ev.email == "a@x.com"
