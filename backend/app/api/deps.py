"""API 依赖注入"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import is_admin_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# 重新导出，方便 API 路由引用
__all__ = ["get_db", "get_current_user", "get_optional_user", "get_current_admin"]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """硬鉴权：无/失效 token → 401；停用 → 401。"""
    if creds is None:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """软鉴权：有合法 token 返回用户，否则 None（不抛 401）。用于给业务端点盖章不破坏现有调用。"""
    if creds is None:
        return None
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """在 get_current_user 基础上要求邮箱 ∈ ADMIN_EMAILS，否则 403。"""
    if not is_admin_email(user.email):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
