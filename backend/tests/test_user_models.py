from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, User, LoginEvent


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'m.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_user_and_login_event_persist(tmp_path):
    db = _session(tmp_path)
    u = User(email="a@x.com", name="A", password_hash="h", is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.id is not None
    assert u.created_at is not None
    assert u.last_login_at is None

    db.add(LoginEvent(user_id=u.id, email=u.email, ip="1.2.3.4"))
    db.commit()
    ev = db.query(LoginEvent).one()
    assert ev.user_id == u.id
    assert ev.email == "a@x.com"
    assert ev.created_at is not None
