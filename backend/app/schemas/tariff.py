"""费率 Schema"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.surcharge import CalculationType
from app.schemas.carrier import CarrierResponse
from app.schemas.lane import LaneResponse


# --- 附加费 ---
class SurchargeBase(BaseModel):
    name: str
    amount: Decimal
    currency: str = "CNY"
    calculation_type: CalculationType = CalculationType.fixed
    remarks: str | None = None


class SurchargeCreate(SurchargeBase):
    pass


class SurchargeResponse(SurchargeBase):
    id: int

    model_config = {"from_attributes": True}


# --- 费率 ---
class TariffBase(BaseModel):
    lane_id: int
    carrier_id: int
    service_level: str | None = None
    currency: str = "CNY"
    base_rate: Decimal
    unit: str = "per_kg"
    min_charge: Decimal | None = None
    transit_days: int | None = None
    effective_date: date
    expiry_date: date | None = None
    remarks: str | None = None
    source: str | None = None
    is_active: bool = True


class TariffCreate(TariffBase):
    surcharges: list[SurchargeCreate] = []


class TariffUpdate(BaseModel):
    lane_id: int | None = None
    carrier_id: int | None = None
    service_level: str | None = None
    currency: str | None = None
    base_rate: Decimal | None = None
    unit: str | None = None
    min_charge: Decimal | None = None
    transit_days: int | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    remarks: str | None = None
    source: str | None = None
    is_active: bool | None = None


class TariffResponse(TariffBase):
    id: int
    created_at: datetime
    updated_at: datetime
    surcharges: list[SurchargeResponse] = []

    model_config = {"from_attributes": True}


class TariffDetailResponse(TariffResponse):
    """费率详情（包含航线和承运人信息）"""
    lane: LaneResponse | None = None
    carrier: CarrierResponse | None = None
