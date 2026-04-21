"""附加费模型 — FSC、SSC、THC 等"""
import enum
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CalculationType(str, enum.Enum):
    fixed = "fixed"
    per_kg = "per_kg"
    percentage = "percentage"


class Surcharge(Base):
    __tablename__ = "surcharges"

    id: Mapped[int] = mapped_column(primary_key=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"), index=True, comment="所属费率")
    name: Mapped[str] = mapped_column(String(100), comment="附加费名称")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="金额")
    currency: Mapped[str] = mapped_column(String(3), default="CNY", comment="币种")
    calculation_type: Mapped[CalculationType] = mapped_column(
        Enum(CalculationType), default=CalculationType.fixed, comment="计算方式"
    )
    remarks: Mapped[str | None] = mapped_column(Text, comment="备注")

    # 关联
    tariff = relationship("Tariff", back_populates="surcharges")
