"""港口 Schema"""
from datetime import datetime

from pydantic import BaseModel


class PortBase(BaseModel):
    un_locode: str
    name_en: str
    name_cn: str | None = None
    name_ja: str | None = None
    country: str | None = None
    region: str | None = None
    is_active: bool = True


class PortCreate(PortBase):
    pass


class PortUpdate(BaseModel):
    name_en: str | None = None
    name_cn: str | None = None
    name_ja: str | None = None
    country: str | None = None
    region: str | None = None
    is_active: bool | None = None


class PortResponse(PortBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
