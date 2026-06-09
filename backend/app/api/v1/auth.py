"""认证 API：register / login / me。

- register 受 REGISTRATION_MODE 控制（open 开放；admin_only 返回 403）
- 登录/注册成功写 last_login_at + login_event（带 IP）
- 管理员标记由 ADMIN_EMAILS 实时判定，不入 DB
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import is_admin_email, settings
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import AuthData, LoginRequest, RegisterRequest, UserInfo
from app.schemas.common import ApiResponse
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _auth_data(user: User) -> AuthData:
    token = create_access_token(user.id)
    info = UserInfo(email=user.email, name=user.name, is_admin=is_admin_email(user.email))
    return AuthData(token=token, user=info)


@router.post("/register", response_model=ApiResponse[AuthData])
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if settings.registration_mode != "open":
        raise HTTPException(status_code=403, detail="注册已关闭，请联系管理员开通账号")
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="请填写姓名")
    try:
        user = user_service.create_user(db, email, body.password, body.name)
    except user_service.EmailExistsError:
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    user_service.record_login(db, user, _client_ip(request))
    return ApiResponse(data=_auth_data(user))


@router.post("/login", response_model=ApiResponse[AuthData])
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = user_service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    user_service.record_login(db, user, _client_ip(request))
    return ApiResponse(data=_auth_data(user))


@router.get("/me", response_model=ApiResponse[UserInfo])
def me(user: User = Depends(get_current_user)):
    return ApiResponse(
        data=UserInfo(email=user.email, name=user.name, is_admin=is_admin_email(user.email))
    )
