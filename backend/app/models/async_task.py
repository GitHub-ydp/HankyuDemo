"""AI 长任务的异步任务信令表。

只存「进度信令 + 完成后的 HTTP 响应体(result_json)」，不存大中间态。
AI 全量解析结果仍在内存 _parse_cache（单 worker 假设下安全）。
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AsyncTaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AsyncTask(Base):
    __tablename__ = "async_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="任务 UUID hex")
    task_type: Mapped[str] = mapped_column(String(50), comment="任务类型")
    status: Mapped[AsyncTaskStatus] = mapped_column(
        Enum(AsyncTaskStatus, native_enum=False),
        default=AsyncTaskStatus.pending,
        comment="任务状态",
    )
    result_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="成功时的响应体（=原 HTTP data）"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
