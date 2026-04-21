"""Step1 导入批次模型。"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ImportBatchFileType(str, enum.Enum):
    air = "air"
    ocean = "ocean"
    ocean_ngb = "ocean_ngb"


class ImportBatchStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    superseded = "superseded"


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        Index("ix_import_batch_file_effective", "file_type", "effective_from", "effective_to"),
        Index("ix_import_batch_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        comment="批次 UUID",
    )
    file_type: Mapped[ImportBatchFileType] = mapped_column(
        Enum(ImportBatchFileType, native_enum=False),
        comment="文件类型",
    )
    source_file: Mapped[str | None] = mapped_column(String(255), comment="来源文件名")
    sheet_name: Mapped[str | None] = mapped_column(String(100), comment="来源 Sheet")
    effective_from: Mapped[date | None] = mapped_column(Date, comment="生效开始日期")
    effective_to: Mapped[date | None] = mapped_column(Date, comment="生效结束日期")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="导入时间",
    )
    row_count: Mapped[int] = mapped_column(Integer, default=0, comment="记录数")
    status: Mapped[ImportBatchStatus] = mapped_column(
        Enum(ImportBatchStatus, native_enum=False),
        default=ImportBatchStatus.draft,
        comment="批次状态",
    )
    imported_by: Mapped[str | None] = mapped_column(String(100), comment="导入人")
    diff_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        comment="差异摘要",
    )

    freight_rates = relationship("FreightRate", back_populates="import_batch")
    air_freight_rates = relationship("AirFreightRate", back_populates="import_batch")
    air_surcharges = relationship("AirSurcharge", back_populates="import_batch")
    lcl_rates = relationship("LclRate", back_populates="import_batch")
