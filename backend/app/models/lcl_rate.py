"""Step1 拼箱海运费率模型。"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LclRate(Base):
    __tablename__ = "lcl_rates"
    __table_args__ = (
        Index("ix_lcl_rate_origin_dest_valid", "origin_port_id", "destination_port_id", "valid_from"),
        Index("ix_lcl_rate_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), comment="起运港")
    destination_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), comment="目的港")
    freight_per_cbm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="每 CBM 运费")
    freight_per_ton: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="每 TON 运费")
    currency: Mapped[str] = mapped_column(String(5), default="USD", comment="币种")
    lss: Mapped[str | None] = mapped_column(String(50), comment="LSS")
    ebs: Mapped[str | None] = mapped_column(String(50), comment="EBS")
    cic: Mapped[str | None] = mapped_column(String(50), comment="CIC")
    ams_aci_ens: Mapped[str | None] = mapped_column(String(50), comment="AMS/ACI/ENS")
    sailing_day: Mapped[str | None] = mapped_column(String(50), comment="开船日")
    via: Mapped[str | None] = mapped_column(String(100), comment="中转港")
    transit_time_text: Mapped[str | None] = mapped_column(String(100), comment="航程文本")
    remarks: Mapped[str | None] = mapped_column(Text, comment="备注")
    valid_from: Mapped[date | None] = mapped_column(Date, comment="生效日期")
    valid_to: Mapped[date | None] = mapped_column(Date, comment="失效日期")
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id"),
        comment="所属导入批次",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    origin_port = relationship("Port", foreign_keys=[origin_port_id], lazy="joined")
    destination_port = relationship("Port", foreign_keys=[destination_port_id], lazy="joined")
    import_batch = relationship("ImportBatch", back_populates="lcl_rates")
