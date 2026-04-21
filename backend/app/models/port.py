"""港口字典模型"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Port(Base):
    __tablename__ = "ports"

    id: Mapped[int] = mapped_column(primary_key=True)
    un_locode: Mapped[str] = mapped_column(String(10), unique=True, comment="UN/LOCODE (如 CNSHA)")
    name_en: Mapped[str] = mapped_column(String(100), comment="英文名")
    name_cn: Mapped[str | None] = mapped_column(String(100), comment="中文名")
    name_ja: Mapped[str | None] = mapped_column(String(100), comment="日文名")
    country: Mapped[str | None] = mapped_column(String(50), comment="国家")
    region: Mapped[str | None] = mapped_column(String(50), comment="区域")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
