"""船司/供应商模型"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CarrierType(str, enum.Enum):
    shipping_line = "shipping_line"  # 船公司
    co_loader = "co_loader"          # 混载业者/联运商
    agent = "agent"                   # 代理商
    nvo = "nvo"                       # 无船承运人


class Carrier(Base):
    __tablename__ = "carriers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, comment="船司代码 (KMTC, ONE, EMC)")
    name_en: Mapped[str] = mapped_column(String(200), comment="英文名称")
    name_cn: Mapped[str | None] = mapped_column(String(200), comment="中文名称")
    name_ja: Mapped[str | None] = mapped_column(String(200), comment="日文名称")
    carrier_type: Mapped[CarrierType] = mapped_column(
        Enum(CarrierType), default=CarrierType.shipping_line, comment="类型"
    )
    country: Mapped[str | None] = mapped_column(String(100), comment="所在国家")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
