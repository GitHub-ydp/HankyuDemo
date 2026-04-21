"""Step1 空运周报价模型。"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AirFreightRate(Base):
    __tablename__ = "air_freight_rates"
    __table_args__ = (
        Index(
            "ix_air_freight_rate_origin_dest_week",
            "origin",
            "destination",
            "effective_week_start",
        ),
        Index("ix_air_freight_rate_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(20), comment="起运港/机场代码")
    destination: Mapped[str] = mapped_column(String(100), comment="目的地")
    airline_code: Mapped[str | None] = mapped_column(String(20), comment="航司代码")
    service_desc: Mapped[str | None] = mapped_column(String(100), comment="服务描述")
    effective_week_start: Mapped[date | None] = mapped_column(Date, comment="周报价生效开始")
    effective_week_end: Mapped[date | None] = mapped_column(Date, comment="周报价生效结束")
    price_day1: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 1 天报价")
    price_day2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 2 天报价")
    price_day3: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 3 天报价")
    price_day4: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 4 天报价")
    price_day5: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 5 天报价")
    price_day6: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 6 天报价")
    price_day7: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="第 7 天报价")
    currency: Mapped[str] = mapped_column(String(5), default="CNY", comment="币种")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id"),
        comment="所属导入批次",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    import_batch = relationship("ImportBatch", back_populates="air_freight_rates")
