"""海运费率主表"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SourceType(str, enum.Enum):
    excel = "excel"
    pdf = "pdf"
    email_text = "email_text"
    wechat_image = "wechat_image"
    manual = "manual"


class RateStatus(str, enum.Enum):
    draft = "draft"        # AI 解析结果，待人工确认
    active = "active"      # 已确认，有效
    expired = "expired"    # 已过期


class FreightRate(Base):
    __tablename__ = "freight_rates"
    __table_args__ = (
        Index("ix_rate_origin_dest", "origin_port_id", "destination_port_id"),
        Index("ix_rate_carrier", "carrier_id"),
        Index("ix_rate_valid", "valid_from", "valid_to"),
        Index("ix_rate_batch", "upload_batch_id"),
        Index("ix_rate_batch_uuid", "batch_id"),
        Index("ix_rate_level", "rate_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id"), comment="船司/供应商")
    origin_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), comment="起运港")
    destination_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), comment="目的港")

    service_code: Mapped[str | None] = mapped_column(String(20), comment="航线/服务代码")

    # 集装箱费率 (USD)
    container_20gp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="20尺柜运费")
    container_40gp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="40尺柜运费")
    container_40hq: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="40尺高柜运费")
    container_45: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="45尺柜运费")

    # 附加费
    baf_20: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="BAF 20尺")
    baf_40: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="BAF 40尺")
    lss_20: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="LSS 20尺")
    lss_40: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="LSS 40尺")
    lss_cic: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="LSS+CIC")
    baf: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="BAF")
    ebs: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="EBS")
    yas_caf: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="YAS/CAF")
    booking_charge: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="订舱费")
    thc: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="THC")
    doc: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="DOC")
    isps: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="ISPS")
    equipment_mgmt: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), comment="用箱管理费")

    currency: Mapped[str] = mapped_column(String(5), default="USD", comment="币种")
    valid_from: Mapped[date | None] = mapped_column(Date, comment="生效日期")
    valid_to: Mapped[date | None] = mapped_column(Date, comment="失效日期")
    transit_days: Mapped[int | None] = mapped_column(Integer, comment="航行天数")
    rate_level: Mapped[str | None] = mapped_column(String(10), comment="费率等级")
    is_direct: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否直达")
    sailing_day: Mapped[str | None] = mapped_column(String(50), comment="开船日")
    via: Mapped[str | None] = mapped_column(String(100), comment="中转港")
    transit_time_text: Mapped[str | None] = mapped_column(String(100), comment="航程文本")
    rmks: Mapped[str | None] = mapped_column(Text, comment="原表备注")
    remarks: Mapped[str | None] = mapped_column(Text, comment="备注")

    # 数据溯源
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType), default=SourceType.manual, comment="数据来源类型"
    )
    source_file: Mapped[str | None] = mapped_column(String(255), comment="来源文件名")
    upload_batch_id: Mapped[str | None] = mapped_column(String(50), comment="上传批次ID")
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id"),
        comment="Step1 导入批次 UUID",
    )

    status: Mapped[RateStatus] = mapped_column(
        Enum(RateStatus), default=RateStatus.draft, comment="状态"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    carrier = relationship("Carrier", lazy="joined")
    origin_port = relationship("Port", foreign_keys=[origin_port_id], lazy="joined")
    destination_port = relationship("Port", foreign_keys=[destination_port_id], lazy="joined")
    import_batch = relationship("ImportBatch", back_populates="freight_rates")
