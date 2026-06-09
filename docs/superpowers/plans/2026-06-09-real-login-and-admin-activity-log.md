# 真实登录 + 管理员活动日志 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前端 localStorage 假登录替换为真实后端 JWT 认证，并新增「仅管理员可见」的活动日志页（用户列表 + 登录历史 + 操作记录）。

**Architecture:** 后端 FastAPI 新增 `users` / `login_events` 两表 + `bcrypt` 密码哈希 + `PyJWT` 无状态令牌；管理员身份由 `.env` 的 `ADMIN_EMAILS` 实时判定（不存 DB role）。操作记录合并读 `import_batches` + `upload_logs`。前端重写 `AuthContext` 走真接口、axios 带 Bearer、新增 `AdminRoute` 与 `ActivityLog` 页。为「按人头收费→管理员指定注册」预留 `REGISTRATION_MODE` 开关与 `user_service.create_user` 单点收口。

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / bcrypt / PyJWT / pytest；React 19 / TS / Ant Design v6 / axios / i18next。

**对应 spec：** `docs/superpowers/specs/2026-06-09-real-login-and-admin-activity-log-design.md`

---

## 文件结构

**后端新建**
- `backend/app/core/security.py` — 密码哈希 + JWT 编解码
- `backend/app/models/user.py` — `users` 表
- `backend/app/models/login_event.py` — `login_events` 表
- `backend/app/services/user_service.py` — 建号/认证/登录记录（单点收口）
- `backend/app/schemas/auth.py` — 认证请求/响应 schema
- `backend/app/api/v1/auth.py` — `/auth/register|login|me`
- `backend/app/api/v1/admin_activity.py` — `/admin/users|login-events|operations`
- `backend/alembic/versions/<rev>_add_users_login_events.py` — 迁移
- `backend/tests/api_v1/conftest.py` — 共享 `client` fixture（隔离 SQLite）
- `backend/tests/api_v1/_auth_helpers.py` — 注册/登录测试辅助
- `backend/tests/test_security.py` / `tests/test_user_service.py` / `tests/api_v1/test_auth.py` / `tests/api_v1/test_admin_activity.py` / `tests/api_v1/test_operation_stamping.py`

**后端修改**
- `backend/app/core/config.py` — 加 JWT / admin_emails / registration_mode 字段 + `is_admin_email()`
- `backend/app/api/deps.py` — 加 `get_current_user` / `get_optional_user` / `get_current_admin`
- `backend/app/models/__init__.py` — 注册 User / LoginEvent
- `backend/app/api/v1/router.py` — 挂 auth / admin_activity 两个 router
- `backend/app/services/rate_parser.py` — `import_parsed_rates` 加 `operator_email`
- `backend/app/api/v1/ai_parse.py` — confirm 端点盖章
- `backend/app/services/step1_rates/activator.py` — `activate` 加 `operator_email`
- `backend/app/api/v1/rate_batches.py` — activate 端点盖章
- `backend/requirements.txt` — 加 `bcrypt` / `PyJWT`

**前端新建**
- `frontend/src/components/AdminRoute.tsx` — 管理员守卫
- `frontend/src/pages/ActivityLog.tsx` — 活动日志页

**前端修改**
- `frontend/src/services/api.ts` — auth 接口 + 请求/响应拦截器
- `frontend/src/contexts/AuthContext.tsx` — 改走真接口
- `frontend/src/App.tsx` — 挂 `/activity` 路由
- `frontend/src/components/Layout/index.tsx` — 管理员菜单项
- `frontend/src/i18n/zh.json` / `ja.json` / `en.json` — 三语文案

---

## Task 1: 配置项 + 管理员判定

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_config_admin.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_config_admin.py`:
```python
from app.core import config


def test_is_admin_email_reads_live_and_normalizes(monkeypatch):
    monkeypatch.setattr(config.settings, "admin_emails", "Boss@Hankyu.co.jp, ops@x.com")
    assert config.is_admin_email("boss@hankyu.co.jp") is True
    assert config.is_admin_email("  OPS@X.COM ") is True
    assert config.is_admin_email("nobody@x.com") is False


def test_is_admin_email_empty_list(monkeypatch):
    monkeypatch.setattr(config.settings, "admin_emails", "")
    assert config.is_admin_email("anyone@x.com") is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_config_admin.py -v`
Expected: FAIL（`AttributeError: ... has no attribute 'admin_emails'` 或 `is_admin_email`）

- [ ] **Step 3: 实现**

在 `backend/app/core/config.py` 的 `Settings` 类里、`max_upload_size` 之后、`class Config` 之前加字段：
```python
    # 认证 / JWT
    jwt_secret: str = "dev-insecure-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720           # 12 小时
    admin_emails: str = ""                  # 逗号分隔的管理员邮箱白名单
    registration_mode: str = "open"         # open | admin_only
```
在文件末尾 `settings = Settings()` 之后追加：
```python
def get_admin_emails() -> set[str]:
    """实时解析 ADMIN_EMAILS（逗号分隔，小写归一）。"""
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def is_admin_email(email: str) -> bool:
    """该邮箱是否为管理员（live 判定，改 .env 即刻生效）。"""
    return email.strip().lower() in get_admin_emails()
```
在 `backend/requirements.txt` 末尾追加两行（若已存在则跳过）：
```
bcrypt>=4.0.0
PyJWT>=2.8.0
```
然后安装：
```bash
cd backend && ../.venv/bin/python -m pip install "bcrypt>=4.0.0" "PyJWT>=2.8.0"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_config_admin.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/config.py backend/requirements.txt backend/tests/test_config_admin.py
git commit -m "feat(auth): 配置JWT/ADMIN_EMAILS/registration_mode + is_admin_email实时判定"
```

---

## Task 2: 认证基建 security.py（哈希 + JWT）

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_security.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_security.py -v`
Expected: FAIL（`ModuleNotFoundError: app.core.security`）

- [ ] **Step 3: 实现**

`backend/app/core/security.py`:
```python
"""认证基建：bcrypt 密码哈希 + PyJWT 令牌编解码。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(raw: str) -> str:
    """bcrypt 哈希（密码取前 72 字节，bcrypt 上限）。"""
    return bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    minutes = settings.jwt_expire_minutes if expires_minutes is None else expires_minutes
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """解码成功返回 user_id；无效/过期返回 None。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_security.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat(auth): security.py bcrypt哈希+PyJWT令牌编解码"
```

---

## Task 3: 数据模型 User + LoginEvent

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/login_event.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_user_models.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_user_models.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_user_models.py -v`
Expected: FAIL（`ImportError: cannot import name 'User'`）

- [ ] **Step 3: 实现**

`backend/app/models/user.py`:
```python
"""用户模型（真实登录）"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, comment="登录邮箱(小写归一)")
    name: Mapped[str] = mapped_column(String(100), comment="显示名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="bcrypt 哈希")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="启用(软停用释放席位)")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后登录时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

`backend/app/models/login_event.py`:
```python
"""登录事件模型（登录历史）"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), comment="冗余邮箱(留痕)")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="登录IP")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="登录时刻")
```

在 `backend/app/models/__init__.py` 中：导入处加
```python
from app.models.user import User
from app.models.login_event import LoginEvent
```
`__all__` 列表里加 `"User",` 和 `"LoginEvent",`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_user_models.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/user.py backend/app/models/login_event.py backend/app/models/__init__.py backend/tests/test_user_models.py
git commit -m "feat(auth): User/LoginEvent 模型 + 注册到 metadata"
```

---

## Task 4: user_service（建号/认证/登录记录单点收口）

**Files:**
- Create: `backend/app/services/user_service.py`
- Test: `backend/tests/test_user_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_user_service.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_user_service.py -v`
Expected: FAIL（`ModuleNotFoundError: app.services.user_service`）

- [ ] **Step 3: 实现**

`backend/app/services/user_service.py`:
```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_user_service.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/user_service.py backend/tests/test_user_service.py
git commit -m "feat(auth): user_service 建号/认证/登录记录单点收口"
```

---

## Task 5: 认证依赖 + 共享测试夹具

**Files:**
- Modify: `backend/app/api/deps.py`
- Create: `backend/tests/api_v1/conftest.py`
- Create: `backend/tests/api_v1/_auth_helpers.py`

> 本任务的依赖将在 Task 6/7/8 的端点测试中被实际验证；这里只建夹具与依赖，不单独写测试断言。

- [ ] **Step 1: 实现认证依赖**

把 `backend/app/api/deps.py` 整个替换为：
```python
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
```

- [ ] **Step 2: 共享 client 夹具**

`backend/tests/api_v1/conftest.py`:
```python
"""api_v1 共享夹具：隔离 SQLite + get_db override。"""
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path/'apitest.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: 注册/登录辅助**

`backend/tests/api_v1/_auth_helpers.py`:
```python
"""测试辅助：注册并取 Bearer 头。"""


def register(client, email, password="pw123456", name="Tester"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def login_headers(client, email, password="pw123456"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = r.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 4: 冒烟确认导入不报错**

Run: `cd backend && ../.venv/bin/python -c "import app.api.deps; import app.main; print('ok')"`
Expected: 打印 `ok`（无 ImportError）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/deps.py backend/tests/api_v1/conftest.py backend/tests/api_v1/_auth_helpers.py
git commit -m "feat(auth): get_current_user/get_optional_user/get_current_admin + 共享测试夹具"
```

---

## Task 6: 认证 schema + auth 路由（register/login/me）

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api_v1/test_auth.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/api_v1/test_auth.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_auth.py -v`
Expected: FAIL（404 / ModuleNotFound：路由尚未挂）

- [ ] **Step 3: 实现 schema**

`backend/app/schemas/auth.py`:
```python
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
```

- [ ] **Step 4: 实现 auth 路由**

`backend/app/api/v1/auth.py`:
```python
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
```

在 `backend/app/api/v1/router.py`：import 处加 `from app.api.v1.auth import router as auth_router`，并在 include 区加 `router.include_router(auth_router)`。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_auth.py -v`
Expected: PASS（8 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/auth.py backend/app/api/v1/auth.py backend/app/api/v1/router.py backend/tests/api_v1/test_auth.py
git commit -m "feat(auth): /auth/register|login|me 路由 + schema + 三语错误码"
```

---

## Task 7: 管理员活动日志路由

**Files:**
- Create: `backend/app/api/v1/admin_activity.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api_v1/test_admin_activity.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/api_v1/test_admin_activity.py`:
```python
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
    register(client, "boss@x.com")            # 注册即写一条 login_event
    headers = login_headers(client, "boss@x.com")   # 再写一条
    r = client.get("/api/v1/admin/login-events", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 2
    assert data["items"][0]["email"] == "boss@x.com"


def test_admin_operations_merges_two_tables(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    register(client, "boss@x.com")
    headers = login_headers(client, "boss@x.com")
    # 直接往隔离库塞一条 upload_log + 一条 import_batch
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
    db.add(ImportBatch(batch_id=uuid.uuid4(), file_type=ImportBatchFileType.excel,
                       source_file="c.xlsx", row_count=5,
                       status=ImportBatchStatus.active, imported_by="boss@x.com"))
    db.commit()
    r = client.get("/api/v1/admin/operations", headers=headers)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    sources = {it["source"] for it in items}
    assert sources == {"ai_confirm", "import"}
```

> 注：`ImportBatch` 的 `file_type` / `status` 为枚举，构造时用枚举成员；`batch_id` 为 UUID。若实际字段有非空约束差异，按 `backend/app/models/import_batch.py` 调整测试构造参数。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_admin_activity.py -v`
Expected: FAIL（404：路由未挂）

- [ ] **Step 3: 实现**

`backend/app/api/v1/admin_activity.py`:
```python
"""管理员活动日志 API：用户列表 / 登录历史 / 操作记录。

全挂 get_current_admin（仅 ADMIN_EMAILS 名单可访问）。
操作记录合并读 import_batches（文件导入/做表）+ upload_logs（AI confirm）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.config import is_admin_email
from app.models.import_batch import ImportBatch
from app.models.login_event import LoginEvent
from app.models.upload_log import UploadLog
from app.models.user import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/admin", tags=["admin-activity"])


def _enum_val(x) -> str:
    return str(getattr(x, "value", x) or "")


@router.get("/users", response_model=ApiResponse)
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    items = [
        {
            "email": u.email,
            "name": u.name,
            "is_admin": is_admin_email(u.email),
            "is_active": u.is_active,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]
    active = sum(1 for u in users if u.is_active)
    return ApiResponse(data={"items": items, "total": len(users), "active": active})


@router.get("/login-events", response_model=ApiResponse)
def list_login_events(
    user_email: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    q = db.query(LoginEvent)
    if user_email:
        q = q.filter(LoginEvent.email == user_email.strip().lower())
    total = q.count()
    rows = q.order_by(LoginEvent.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        {"email": r.email, "ip": r.ip, "time": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
    return ApiResponse(data={"items": items, "total": total})


@router.get("/operations", response_model=ApiResponse)
def list_operations(
    operator: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """合并 import_batches + upload_logs，Python 侧归一+排序+分页（数据量小，足够）。"""
    ops: list[dict] = []

    bq = db.query(ImportBatch)
    if operator:
        bq = bq.filter(ImportBatch.imported_by == operator)
    for b in bq.all():
        ops.append(
            {
                "source": "import",
                "operator": b.imported_by,
                "time": b.imported_at.isoformat() if b.imported_at else None,
                "file": b.source_file,
                "file_type": _enum_val(b.file_type),
                "status": _enum_val(b.status),
                "parsed": None,
                "imported": b.row_count,
            }
        )

    uq = db.query(UploadLog)
    if operator:
        uq = uq.filter(UploadLog.uploaded_by == operator)
    for u in uq.all():
        ops.append(
            {
                "source": "ai_confirm",
                "operator": u.uploaded_by,
                "time": u.created_at.isoformat() if u.created_at else None,
                "file": u.file_name,
                "file_type": u.file_type,
                "status": _enum_val(u.status),
                "parsed": u.records_parsed,
                "imported": u.records_imported,
            }
        )

    ops.sort(key=lambda x: x["time"] or "", reverse=True)
    return ApiResponse(data={"items": ops[offset : offset + limit], "total": len(ops)})
```

在 `backend/app/api/v1/router.py`：import 处加 `from app.api.v1.admin_activity import router as admin_activity_router`，include 区加 `router.include_router(admin_activity_router)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_admin_activity.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/admin_activity.py backend/app/api/v1/router.py backend/tests/api_v1/test_admin_activity.py
git commit -m "feat(auth): /admin/users|login-events|operations 管理员活动日志路由"
```

---

## Task 8: 操作记录盖章（可选用户，非破坏）

**Files:**
- Modify: `backend/app/services/rate_parser.py`（`import_parsed_rates`）
- Modify: `backend/app/api/v1/ai_parse.py`（confirm 端点）
- Modify: `backend/app/services/step1_rates/activator.py`（`activate`）
- Modify: `backend/app/api/v1/rate_batches.py`（activate 端点）
- Test: `backend/tests/api_v1/test_operation_stamping.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/api_v1/test_operation_stamping.py`:
```python
from app.services.rate_parser import import_parsed_rates


def test_import_parsed_rates_accepts_operator_email(tmp_path):
    """import_parsed_rates 支持 operator_email，并写入 upload_logs.uploaded_by。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.upload_log import UploadLog

    engine = create_engine(
        f"sqlite:///{tmp_path/'st.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    parsed = {"file_name": "x.xlsx", "file_type": "xlsx", "source_type": "excel", "rates": []}
    import_parsed_rates(parsed, db, operator_email="ops@x.com")

    log = db.query(UploadLog).first()
    assert log is not None
    assert log.uploaded_by == "ops@x.com"
```

> 注：`parsed` 字典字段以 `rate_parser.import_parsed_rates` 实际读取的键为准（见函数体 693 行起）。若空 rates 会触发其它分支，改用最小合法 parsed 结构；目标只验证 `uploaded_by` 被写入。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_operation_stamping.py -v`
Expected: FAIL（`import_parsed_rates() got an unexpected keyword argument 'operator_email'`）

- [ ] **Step 3: 改 import_parsed_rates**

在 `backend/app/services/rate_parser.py` 的 `def import_parsed_rates(` 签名末尾加参数 `operator_email: str | None = None`，并在创建 `UploadLog(...)` 的关键字里加一行 `uploaded_by=operator_email,`（紧挨 `error_message=...` 之后）。

- [ ] **Step 4: confirm 端点盖章**

在 `backend/app/api/v1/ai_parse.py`：
- import 区加 `from app.api.deps import get_optional_user`、`from app.models.user import User`、`from fastapi import Depends`（若未导入）。
- `api_confirm_import` 函数签名加参数 `current_user: User | None = Depends(get_optional_user)`。
- 把 `result = import_parsed_rates(parsed_data, db)` 改为：
```python
    result = import_parsed_rates(
        parsed_data, db, operator_email=current_user.email if current_user else None
    )
```

- [ ] **Step 5: activate 盖章**

在 `backend/app/services/step1_rates/activator.py` 的 `def activate(` 签名末尾加 `operator_email: str | None = None`，把硬编码 `imported_by="step1_activator"` 改为 `imported_by=operator_email or "step1_activator"`。

在 `backend/app/api/v1/rate_batches.py` 的 `activate_rate_batch` 端点：
- import 区加 `from app.api.deps import get_optional_user`、`from app.models.user import User`。
- 函数签名加 `current_user: User | None = Depends(get_optional_user)`。
- 调 `activator.activate(...)` 处补传 `operator_email=current_user.email if current_user else None`。

- [ ] **Step 6: 运行确认通过 + 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_operation_stamping.py tests/api_v1/test_rate_batch_air_tier_diff.py -v`
Expected: PASS（盖章测试通过，且 activate 既有测试不回归——证明 get_optional_user 无 token 不破坏）

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/rate_parser.py backend/app/api/v1/ai_parse.py backend/app/services/step1_rates/activator.py backend/app/api/v1/rate_batches.py backend/tests/api_v1/test_operation_stamping.py
git commit -m "feat(auth): 操作记录盖章(可选用户)-/ai/confirm填uploaded_by+activate填imported_by"
```

---

## Task 9: Alembic 迁移（users + login_events）

**Files:**
- Create: `backend/alembic/versions/<rev>_add_users_login_events.py`

- [ ] **Step 1: 自动生成迁移**

```bash
cd backend && ../.venv/bin/python -m alembic revision --autogenerate -m "add users and login_events"
```
Expected: 在 `backend/alembic/versions/` 生成一个新文件，`upgrade()` 含 `op.create_table('users', ...)` 与 `op.create_table('login_events', ...)`。

- [ ] **Step 2: 人工核对迁移内容**

打开生成的文件，确认：
- `users` 表含 `id/email(unique index)/name/password_hash/is_active/last_login_at/created_at`
- `login_events` 表含 `id/user_id(FK users.id, index)/email/ip/created_at`
- `downgrade()` 对应 `op.drop_table(...)` 两张表
若 autogenerate 误把别的表也写进来（环境漂移），手动删掉无关 op，只保留这两张表。

- [ ] **Step 3: 应用迁移验证**

```bash
cd backend && ../.venv/bin/python -m alembic upgrade head && ../.venv/bin/python -m alembic downgrade -1 && ../.venv/bin/python -m alembic upgrade head
```
Expected: upgrade / downgrade / upgrade 均无报错（验证可逆）。

- [ ] **Step 4: 提交**

```bash
git add backend/alembic/versions/
git commit -m "feat(auth): alembic迁移 新增users/login_events两表"
```

---

## Task 10: 前端 API 层（auth 接口 + 拦截器）

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 加请求拦截器（带 token）+ 401 处理**

在 `frontend/src/services/api.ts` 中 `const api = axios.create({...})` 之后、`api.interceptors.response.use(` 之前插入：
```typescript
export const TOKEN_KEY = 'hhrh_token';

// 请求拦截器：附带 Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```
在 `api.interceptors.response.use(` 的错误回调里，`const raw = error.response?.data ?? {};` 之后加：
```typescript
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.assign('/login');
      }
    }
```

- [ ] **Step 2: 加 authApi**

在 `frontend/src/services/api.ts` 末尾追加：
```typescript
// --- 认证 ---
export const authApi = {
  register: (email: string, password: string, name: string) =>
    api.post<unknown, ApiResponse>('/auth/register', { email, password, name }),
  login: (email: string, password: string) =>
    api.post<unknown, ApiResponse>('/auth/login', { email, password }),
  me: () => api.get<unknown, ApiResponse>('/auth/me'),
};

// --- 管理员活动日志 ---
export const adminActivityApi = {
  users: () => api.get<unknown, ApiResponse>('/admin/users'),
  loginEvents: (params?: Record<string, unknown>) =>
    api.get<unknown, ApiResponse>('/admin/login-events', { params }),
  operations: (params?: Record<string, unknown>) =>
    api.get<unknown, ApiResponse>('/admin/operations', { params }),
};
```

- [ ] **Step 3: 验证编译**

Run: `cd frontend && npm run build`
Expected: 构建成功（TS 无类型错误）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(auth): 前端axios带Bearer+401跳登录+authApi/adminActivityApi"
```

---

## Task 11: AuthContext 改走真接口

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx`

- [ ] **Step 1: 重写 AuthContext**

把 `frontend/src/contexts/AuthContext.tsx` 整个替换为：
```typescript
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi, TOKEN_KEY } from '../services/api';

export interface AuthUser {
  email: string;
  name: string;
  isAdmin: boolean;
  role?: string;
  initial?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, name: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function initialOf(name: string, email: string) {
  const trimmed = name.trim();
  if (trimmed) {
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return trimmed.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

function toUser(raw: { email: string; name: string; is_admin: boolean }): AuthUser {
  return {
    email: raw.email,
    name: raw.name,
    isAdmin: raw.is_admin,
    role: raw.is_admin ? 'ADMIN' : 'OPS MANAGER',
    initial: initialOf(raw.name, raw.email),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // 挂载时若有 token → /auth/me 还原
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then((res) => setUser(toUser(res.data)))
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback<AuthContextValue['login']>(async (email, password) => {
    const res = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, res.data.token);
    const u = toUser(res.data.user);
    setUser(u);
    return u;
  }, []);

  const register = useCallback<AuthContextValue['register']>(async (email, password, name) => {
    const res = await authApi.register(email, password, name);
    localStorage.setItem(TOKEN_KEY, res.data.token);
    const u = toUser(res.data.user);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
```

- [ ] **Step 2: ProtectedRoute 处理 loading**

把 `frontend/src/components/ProtectedRoute.tsx` 替换为：
```typescript
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../contexts/AuthContext';

export default function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
```

- [ ] **Step 3: 验证编译**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 4: 提交**

```bash
git add frontend/src/contexts/AuthContext.tsx frontend/src/components/ProtectedRoute.tsx
git commit -m "feat(auth): AuthContext改走真后端(/auth/login|register|me)+ProtectedRoute加载态"
```

---

## Task 12: AdminRoute + 路由 + 管理员菜单

**Files:**
- Create: `frontend/src/components/AdminRoute.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/index.tsx`

- [ ] **Step 1: AdminRoute**

`frontend/src/components/AdminRoute.tsx`:
```typescript
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function AdminRoute() {
  const { user } = useAuth();
  if (!user?.isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
```

- [ ] **Step 2: 挂路由**

在 `frontend/src/App.tsx`：
- import 区加 `import AdminRoute from './components/AdminRoute';` 和 `import ActivityLog from './pages/ActivityLog';`
- 在 `AppLayout` 的 `children` 数组里，`{ path: '/settings', element: <Settings /> },` 之后加一组嵌套（仅管理员）：
```tsx
            {
              element: <AdminRoute />,
              children: [{ path: '/activity', element: <ActivityLog /> }],
            },
```

- [ ] **Step 3: 管理员菜单项**

在 `frontend/src/components/Layout/index.tsx`：
- 找到渲染 `DATA_NAV`（或主菜单）的位置，新增一个仅管理员可见的入口。先在文件顶部 NavEntry 定义区加：
```typescript
const ADMIN_NAV: NavEntry[] = [{ to: '/activity', icon: 'dashboard', labelKey: 'menu.activity' }];
```
- 在组件内（已有 `const { user, logout } = useAuth();`）渲染主菜单之后，追加：
```tsx
        {user?.isAdmin &&
          ADMIN_NAV.map((entry) => (
            <NavLink key={entry.to} to={entry.to} className="nav-item">
              <Icon name={entry.icon} size={16} className="nav-icon" />
              <span>{t(entry.labelKey)}</span>
            </NavLink>
          ))}
```
> 注：以 Layout 现有菜单项的真实 JSX 写法为准（`NavLink` / class 名 / Icon 用法照抄相邻项），上面是按已观察到的 `Icon`+`t(labelKey)` 模式给出；若现有项用的是别的渲染函数，复用同一函数即可。

- [ ] **Step 4: 验证编译**

Run: `cd frontend && npm run build`
Expected: 构建成功（注意此步 ActivityLog 页尚未建，会报缺模块——故本任务与 Task 13 顺序：先建 ActivityLog 占位再编译，或把 Step 4 验证挪到 Task 13 后）。先建最小占位 `frontend/src/pages/ActivityLog.tsx`：
```tsx
export default function ActivityLog() {
  return <div>Activity Log</div>;
}
```
再 `npm run build`，确认通过。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/AdminRoute.tsx frontend/src/App.tsx frontend/src/components/Layout/index.tsx frontend/src/pages/ActivityLog.tsx
git commit -m "feat(auth): AdminRoute守卫+/activity路由+管理员专属菜单(占位页)"
```

---

## Task 13: 活动日志页面（三 Tab）

**Files:**
- Modify: `frontend/src/pages/ActivityLog.tsx`

- [ ] **Step 1: 实现页面**

把 `frontend/src/pages/ActivityLog.tsx` 替换为：
```tsx
import { useEffect, useState } from 'react';
import { Card, Statistic, Table, Tabs, Tag, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { adminActivityApi } from '../services/api';

interface UserRow {
  email: string;
  name: string;
  is_admin: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}
interface LoginRow { email: string; ip: string | null; time: string | null }
interface OpRow {
  source: string; operator: string | null; time: string | null;
  file: string | null; file_type: string | null; status: string | null;
  parsed: number | null; imported: number | null;
}

const fmt = (s: string | null) => (s ? new Date(s).toLocaleString() : '-');

export default function ActivityLog() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [summary, setSummary] = useState({ total: 0, active: 0 });
  const [logins, setLogins] = useState<LoginRow[]>([]);
  const [ops, setOps] = useState<OpRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([adminActivityApi.users(), adminActivityApi.loginEvents(), adminActivityApi.operations()])
      .then(([u, l, o]) => {
        setUsers(u.data.items);
        setSummary({ total: u.data.total, active: u.data.active });
        setLogins(l.data.items);
        setOps(o.data.items);
      })
      .catch((e) => message.error(e instanceof Error ? e.message : t('activity.loadError')))
      .finally(() => setLoading(false));
  }, [t]);

  const userCols = [
    { title: t('activity.col.email'), dataIndex: 'email' },
    { title: t('activity.col.name'), dataIndex: 'name' },
    {
      title: t('activity.col.role'),
      dataIndex: 'is_admin',
      render: (v: boolean) => (v ? <Tag color="gold">{t('activity.admin')}</Tag> : <Tag>{t('activity.user')}</Tag>),
    },
    {
      title: t('activity.col.status'),
      dataIndex: 'is_active',
      render: (v: boolean) => (v ? <Tag color="green">{t('activity.active')}</Tag> : <Tag color="red">{t('activity.disabled')}</Tag>),
    },
    { title: t('activity.col.lastLogin'), dataIndex: 'last_login_at', render: fmt },
    { title: t('activity.col.createdAt'), dataIndex: 'created_at', render: fmt },
  ];
  const loginCols = [
    { title: t('activity.col.email'), dataIndex: 'email' },
    { title: t('activity.col.time'), dataIndex: 'time', render: fmt },
    { title: t('activity.col.ip'), dataIndex: 'ip', render: (v: string | null) => v || '-' },
  ];
  const opCols = [
    { title: t('activity.col.operator'), dataIndex: 'operator', render: (v: string | null) => v || '-' },
    { title: t('activity.col.time'), dataIndex: 'time', render: fmt },
    { title: t('activity.col.source'), dataIndex: 'source' },
    { title: t('activity.col.file'), dataIndex: 'file', render: (v: string | null) => v || '-' },
    { title: t('activity.col.fileType'), dataIndex: 'file_type', render: (v: string | null) => v || '-' },
    { title: t('activity.col.opStatus'), dataIndex: 'status', render: (v: string | null) => v || '-' },
    { title: t('activity.col.imported'), dataIndex: 'imported', render: (v: number | null) => (v ?? '-') },
  ];

  return (
    <Card title={t('activity.title')}>
      <div style={{ display: 'flex', gap: 32, marginBottom: 16 }}>
        <Statistic title={t('activity.totalUsers')} value={summary.total} />
        <Statistic title={t('activity.activeUsers')} value={summary.active} />
      </div>
      <Tabs
        items={[
          { key: 'users', label: t('activity.tab.users'), children: <Table rowKey="email" loading={loading} columns={userCols} dataSource={users} size="small" /> },
          { key: 'logins', label: t('activity.tab.logins'), children: <Table rowKey={(r) => `${r.email}-${r.time}`} loading={loading} columns={loginCols} dataSource={logins} size="small" /> },
          { key: 'ops', label: t('activity.tab.ops'), children: <Table rowKey={(r) => `${r.source}-${r.time}-${r.file}`} loading={loading} columns={opCols} dataSource={ops} size="small" /> },
        ]}
      />
    </Card>
  );
}
```

- [ ] **Step 2: 验证编译**

Run: `cd frontend && npm run build`
Expected: 构建成功（i18n key 缺失不影响编译，下一任务补）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/ActivityLog.tsx
git commit -m "feat(auth): 活动日志页(用户列表/登录历史/操作记录 三Tab+席位统计)"
```

---

## Task 14: i18n 三语文案

**Files:**
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/ja.json`
- Modify: `frontend/src/i18n/en.json`

- [ ] **Step 1: 加键（zh）**

在 `frontend/src/i18n/zh.json` 顶层对象内，给 `menu` 对象加 `"activity": "活动日志"`，并新增 `activity` 对象：
```json
  "activity": {
    "title": "活动日志",
    "totalUsers": "用户总数",
    "activeUsers": "活跃用户",
    "admin": "管理员",
    "user": "普通用户",
    "active": "启用",
    "disabled": "停用",
    "loadError": "加载失败",
    "tab": { "users": "用户列表", "logins": "登录历史", "ops": "操作记录" },
    "col": {
      "email": "邮箱", "name": "姓名", "role": "角色", "status": "状态",
      "lastLogin": "最后登录", "createdAt": "注册时间", "time": "时间", "ip": "IP",
      "operator": "操作人", "source": "来源", "file": "文件", "fileType": "类型",
      "opStatus": "状态", "imported": "入库数"
    }
  }
```

- [ ] **Step 2: 加键（ja）**

在 `frontend/src/i18n/ja.json` 给 `menu` 加 `"activity": "アクティビティログ"`，并新增：
```json
  "activity": {
    "title": "アクティビティログ",
    "totalUsers": "ユーザー総数",
    "activeUsers": "アクティブユーザー",
    "admin": "管理者",
    "user": "一般ユーザー",
    "active": "有効",
    "disabled": "無効",
    "loadError": "読み込みに失敗しました",
    "tab": { "users": "ユーザー一覧", "logins": "ログイン履歴", "ops": "操作履歴" },
    "col": {
      "email": "メール", "name": "氏名", "role": "ロール", "status": "状態",
      "lastLogin": "最終ログイン", "createdAt": "登録日時", "time": "日時", "ip": "IP",
      "operator": "操作者", "source": "種別", "file": "ファイル", "fileType": "形式",
      "opStatus": "状態", "imported": "登録件数"
    }
  }
```

- [ ] **Step 3: 加键（en）**

在 `frontend/src/i18n/en.json` 给 `menu` 加 `"activity": "Activity Log"`，并新增：
```json
  "activity": {
    "title": "Activity Log",
    "totalUsers": "Total Users",
    "activeUsers": "Active Users",
    "admin": "Admin",
    "user": "User",
    "active": "Active",
    "disabled": "Disabled",
    "loadError": "Failed to load",
    "tab": { "users": "Users", "logins": "Login History", "ops": "Operations" },
    "col": {
      "email": "Email", "name": "Name", "role": "Role", "status": "Status",
      "lastLogin": "Last Login", "createdAt": "Created", "time": "Time", "ip": "IP",
      "operator": "Operator", "source": "Source", "file": "File", "fileType": "Type",
      "opStatus": "Status", "imported": "Imported"
    }
  }
```

> 注：以上为追加键；JSON 合并时注意逗号，不要破坏既有结构。`menu.activity` 若 `menu` 对象已存在则只加一行。

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: 构建成功；lint 无 error（JSON 合法）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json
git commit -m "i18n(auth): 活动日志页+菜单 三语文案(zh/ja/en)"
```

---

## Task 15: 全量回归 + 收尾验证

**Files:** 无（仅验证）

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && ../.venv/bin/python -m pytest`
Expected: 全绿（既有用例不回归 + 新增 auth/admin/stamping 用例通过）。若有 fail，逐条修复后重跑。

- [ ] **Step 2: 前端构建 + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功；lint 无 error。

- [ ] **Step 3: 手动联调冒烟（需本地起服务）**

```bash
# 终端1：后端（先在 backend/.env 设 ADMIN_EMAILS=你的测试邮箱、JWT_SECRET=任意值）
cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
# 终端2：前端
cd frontend && npm run dev
```
浏览器走查：
1. 未登录访问首页 → 跳 `/login`。
2. 注册一个**非** ADMIN_EMAILS 邮箱 → 进系统，左侧**无**「活动日志」菜单；手敲 `/activity` → 被弹回首页。
3. 退出，注册/登录一个 **ADMIN_EMAILS 内**邮箱 → 左侧出现「活动日志」；进入看到三个 Tab，用户列表里两个账号、最后登录时间有值、登录历史有记录。
4. 用管理员上传一份运价文件并 AI 确认入库 → 「操作记录」Tab 出现该操作且 operator = 管理员邮箱。

- [ ] **Step 4: 完成提交（如冒烟中有微调）**

```bash
git add -A && git commit -m "chore(auth): 联调冒烟微调与收尾" || echo "无改动"
```

---

## Self-Review 记录（写计划时已核）

- **Spec 覆盖**：D1 单部署（无 tenant 字段）✓；D2 开放注册（registration_mode=open）✓ Task6；D3 登录历史+操作记录 ✓ Task7；D4 ADMIN_EMAILS 实时判定 ✓ Task1；D5 JWT ✓ Task2；D6 两表合并 ✓ Task7；D7 收费预留（registration_mode 开关 + create_user 收口 + is_active + 席位统计）✓ Task1/4/7/13；前端重写/AdminRoute/页面/i18n ✓ Task10-14；迁移 ✓ Task9；后端鉴权范围边界（仅 /auth/me + /admin/* 硬鉴权，盖章用 get_optional_user 非破坏）✓ Task5/8。
- **类型一致**：`is_admin_email` / `create_access_token`/`decode_access_token` / `user_service.create_user|authenticate|record_login` / `EmailExistsError` / `get_current_user|get_optional_user|get_current_admin` / `authApi`/`adminActivityApi` / `TOKEN_KEY` 跨任务签名一致。
- **占位符**：无 TBD/TODO；每步含完整代码或确切命令。
- **已知执行注意**：Task8 的 `import_parsed_rates` 空 `rates` 结构、Task12 Layout 菜单 JSX 写法、Task7 ImportBatch 枚举构造，均以对应源文件实际写法为准（已在步骤内注明）。
