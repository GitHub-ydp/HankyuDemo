"""国内配送/集荷费模型"""
import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DomesticRateType(str, enum.Enum):
    delivery = "delivery"  # 配送料
    pickup = "pickup"      # 集荷料


class DomesticRate(Base):
    __tablename__ = "domestic_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(100), comment="城市")
    province: Mapped[str | None] = mapped_column(String(100), comment="省份")
    rate_type: Mapped[DomesticRateType] = mapped_column(Enum(DomesticRateType), comment="类型")
    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="费率")
    unit: Mapped[str] = mapped_column(String(20), default="per_kg", comment="计费单位")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    min_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), comment="最低收费")
    effective_date: Mapped[date] = mapped_column(Date, comment="生效日期")
    expiry_date: Mapped[date | None] = mapped_column(Date, comment="失效日期")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
