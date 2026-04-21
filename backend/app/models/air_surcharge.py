"""Step1 空运附加费模型。"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AirSurcharge(Base):
    __tablename__ = "air_surcharges"
    __table_args__ = (
        Index("ix_air_surcharge_effective", "effective_date", "airline_code"),
        Index("ix_air_surcharge_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    area: Mapped[str | None] = mapped_column(String(50), comment="区域")
    from_region: Mapped[str | None] = mapped_column(String(50), comment="起运区域")
    airline_code: Mapped[str | None] = mapped_column(String(20), comment="航司代码")
    effective_date: Mapped[date | None] = mapped_column(Date, comment="生效日期")
    myc_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="MYC 最低收费")
    myc_fee_per_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        comment="MYC 每公斤收费",
    )
    msc_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="MSC 最低收费")
    msc_fee_per_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        comment="MSC 每公斤收费",
    )
    destination_scope: Mapped[str | None] = mapped_column(String(200), comment="目的地范围")
    remarks: Mapped[str | None] = mapped_column(Text, comment="备注")
    currency: Mapped[str] = mapped_column(String(5), default="CNY", comment="币种")
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id"),
        comment="所属导入批次",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    import_batch = relationship("ImportBatch", back_populates="air_surcharges")
