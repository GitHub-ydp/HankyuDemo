"""用户服务：建号 / 认证 / 登录记录。

建号逻辑单点收口（create_user）：自助注册与未来「管理员建号」共用，
切换 REGISTRATION_MODE 时只换调用方，不改这里。
"""
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.login_event import LoginEvent
from app.models.user import User

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class EmailExistsError(Exception):
    """邮箱已注册。"""


class InvalidUserInputError(Exception):
    """注册输入不合法。"""


def create_user(db: Session, email: str, password: str, name: str) -> User:
    email = email.strip().lower()
    name = name.strip()
    # 校验输入合法性（统一在服务层，管理员建号与自助注册共用同一校验）
    if not _EMAIL_RE.match(email):
        raise InvalidUserInputError("邮箱格式不正确")
    if len(password) < 6:
        raise InvalidUserInputError("密码至少需要 6 位")
    if not name:
        raise InvalidUserInputError("请填写姓名")
    if db.query(User).filter(User.email == email).first() is not None:
        raise EmailExistsError(email)
    user = User(email=email, name=name, password_hash=hash_password(password), is_active=True)
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
