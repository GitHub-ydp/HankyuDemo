"""用户服务：建号 / 认证 / 登录记录。

建号逻辑单点收口（create_user）：自助注册与未来「管理员建号」共用，
切换 REGISTRATION_MODE 时只换调用方，不改这里。
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.login_event import LoginEvent
from app.models.user import User


class EmailExistsError(Exception):
    """邮箱已注册。"""


def create_user(db: Session, email: str, password: str, name: str) -> User:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise EmailExistsError(email)
    user = User(email=email, name=name.strip(), password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def record_login(db: Session, user: User, ip: str | None) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    db.add(LoginEvent(user_id=user.id, email=user.email, ip=ip))
    db.commit()
