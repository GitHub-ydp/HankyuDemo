"""航线模型 — 起运地到目的地的路线"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TransportMode(str, enum.Enum):
    air = "air"
    ocean = "ocean"
    truck = "truck"
    multimodal = "multimodal"


class Lane(Base):
    __tablename__ = "lanes"
    __table_args__ = (
        UniqueConstraint("origin_code", "destination_code", "transport_mode", name="uq_lane_route"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_city: Mapped[str] = mapped_column(String(100), comment="起运城市")
    origin_country: Mapped[str] = mapped_column(String(100), comment="起运国家")
    origin_code: Mapped[str] = mapped_column(String(10), comment="机场/港口代码")
    destination_city: Mapped[str] = mapped_column(String(100), comment="目的城市")
    destination_country: Mapped[str] = mapped_column(String(100), comment="目的国家")
    destination_code: Mapped[str] = mapped_column(String(10), comment="机场/港口代码")
    transport_mode: Mapped[TransportMode] = mapped_column(Enum(TransportMode), comment="运输方式")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    tariffs = relationship("Tariff", back_populates="lane")
