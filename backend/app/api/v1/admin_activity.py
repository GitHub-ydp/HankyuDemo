"""管理员活动日志 API：用户列表 / 登录历史 / 操作记录。

全挂 get_current_admin（仅 ADMIN_EMAILS 名单可访问）。
操作记录合并读 import_batches（文件导入/做表）+ upload_logs（AI confirm）。
"""
from datetime import datetime, timezone

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


def _iso_utc(dt: datetime | None) -> str | None:
    """库内时间统一按 UTC 序列化（SQLite 读出是 naive UTC，补上时区标记前端才能正确换算）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@router.get("/users", response_model=ApiResponse)
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    items = [
        {
            "email": u.email,
            "name": u.name,
            "is_admin": is_admin_email(u.email),
            "is_active": u.is_active,
            "last_login_at": _iso_utc(u.last_login_at),
            "created_at": _iso_utc(u.created_at),
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
        {"email": r.email, "ip": r.ip, "time": _iso_utc(r.created_at)}
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
                "time": _iso_utc(b.imported_at),
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
                "time": _iso_utc(u.created_at),
                "file": u.file_name,
                "file_type": u.file_type,
                "status": _enum_val(u.status),
                "parsed": u.records_parsed,
                "imported": u.records_imported,
            }
        )

    ops.sort(key=lambda x: x["time"] or "", reverse=True)
    return ApiResponse(data={"items": ops[offset : offset + limit], "total": len(ops)})
