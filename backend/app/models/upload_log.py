"""上传记录模型"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class UploadLog(Base):
    __tablename__ = "upload_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(50), unique=True, comment="批次ID")
    file_name: Mapped[str] = mapped_column(String(255), comment="文件名")
    file_type: Mapped[str] = mapped_column(String(20), comment="文件扩展名")
    source_type: Mapped[str] = mapped_column(String(20), comment="来源类型")
    records_parsed: Mapped[int] = mapped_column(Integer, default=0, comment="解析记录数")
    records_imported: Mapped[int] = mapped_column(Integer, default=0, comment="入库记录数")
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus), default=UploadStatus.processing, comment="状态"
    )
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    uploaded_by: Mapped[str | None] = mapped_column(String(100), comment="上传人")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
