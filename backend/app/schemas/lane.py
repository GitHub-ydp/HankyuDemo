"""航线 Schema"""
from datetime import datetime

from pydantic import BaseModel

from app.models.lane import TransportMode


class LaneBase(BaseModel):
    origin_city: str
    origin_country: str
    origin_code: str
    destination_city: str
    destination_country: str
    destination_code: str
    transport_mode: TransportMode
    is_active: bool = True


class LaneCreate(LaneBase):
    pass


class LaneUpdate(BaseModel):
    origin_city: str | None = None
    origin_country: str | None = None
    origin_code: str | None = None
    destination_city: str | None = None
    destination_country: str | None = None
    destination_code: str | None = None
    transport_mode: TransportMode | None = None
    is_active: bool | None = None


class LaneResponse(LaneBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
