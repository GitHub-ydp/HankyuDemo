"""船司/供应商 Schema"""
from datetime import datetime

from pydantic import BaseModel

from app.models.carrier import CarrierType


class CarrierBase(BaseModel):
    code: str
    name_en: str
    name_cn: str | None = None
    name_ja: str | None = None
    carrier_type: CarrierType = CarrierType.shipping_line
    country: str | None = None
    is_active: bool = True


class CarrierCreate(CarrierBase):
    pass


class CarrierUpdate(BaseModel):
    code: str | None = None
    name_en: str | None = None
    name_cn: str | None = None
    name_ja: str | None = None
    carrier_type: CarrierType | None = None
    country: str | None = None
    is_active: bool | None = None


class CarrierResponse(CarrierBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
