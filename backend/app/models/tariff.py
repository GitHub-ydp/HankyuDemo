"""费率模型 — 核心数据表"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (
        Index("ix_tariff_lane_carrier_date", "lane_id", "carrier_id", "effective_date"),
        Index("ix_tariff_date_range", "effective_date", "expiry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lane_id: Mapped[int] = mapped_column(ForeignKey("lanes.id"), index=True, comment="所属航线")
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id"), index=True, comment="承运人")
    service_level: Mapped[str | None] = mapped_column(String(50), comment="服务等级")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="基础费率")
    unit: Mapped[str] = mapped_column(String(20), default="per_kg", comment="计费单位")
    min_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), comment="最低收费")
    transit_days: Mapped[int | None] = mapped_column(Integer, comment="中转天数")
    effective_date: Mapped[date] = mapped_column(Date, comment="生效日期")
    expiry_date: Mapped[date | None] = mapped_column(Date, comment="失效日期")
    remarks: Mapped[str | None] = mapped_column(Text, comment="备注")
    source: Mapped[str | None] = mapped_column(String(100), comment="数据来源")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    lane = relationship("Lane", back_populates="tariffs")
    carrier = relationship("Carrier", back_populates="tariffs")
    surcharges = relationship("Surcharge", back_populates="tariff", cascade="all, delete-orphan")
