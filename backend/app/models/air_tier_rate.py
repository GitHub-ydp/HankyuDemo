"""Step1 空运重量档运价模型（做表→入库的落地表）。

与 air_freight_rates(周报价 day1-7) 区别：这里价格是**重量档**(EES/唯凯式)，按稀疏 dict
`tier_prices={45:17,100:14,…}` 存进一个 JSON 列(与 import_batches.diff_summary 同款)。
step2 投标包按货量(想定平均重量)从这些档里选一档取价。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AirTierRate(Base):
    __tablename__ = "air_tier_rates"
    __table_args__ = (
        Index("ix_air_tier_rate_origin_dest", "origin", "destination"),
        Index("ix_air_tier_rate_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(20), comment="起运港/机场代码")
    destination: Mapped[str] = mapped_column(String(100), comment="目的地")
    service_desc: Mapped[str | None] = mapped_column(String(100), comment="服务/航班/装载方式")
    tier_prices: Mapped[dict[str, object]] = mapped_column(
        JSON,
        comment="重量档稀疏价 {KG: 单价}",
    )
    effective_from: Mapped[date | None] = mapped_column(Date, comment="报价生效开始")
    effective_to: Mapped[date | None] = mapped_column(Date, comment="报价生效结束")
    currency: Mapped[str] = mapped_column(String(5), default="CNY", comment="币种")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
    cargo_class: Mapped[str | None] = mapped_column(String(20), comment="货类(普货/快件/9610-9710)")
    packing: Mapped[str | None] = mapped_column(String(20), comment="包装(托/散/托散/混装)")
    density: Mapped[str | None] = mapped_column(String(20), comment="泡比(如1:167)")
    carrier: Mapped[str | None] = mapped_column(String(100), comment="航司代码")
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id"),
        comment="所属导入批次",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    import_batch = relationship("ImportBatch", back_populates="air_tier_rates")
