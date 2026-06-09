"""认证请求 / 响应 schema。"""
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserInfo(BaseModel):
    email: str
    name: str
    is_admin: bool


class AuthData(BaseModel):
    token: str
    user: UserInfo
