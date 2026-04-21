"""海运费率 Schema"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.freight_rate import RateStatus, SourceType
from app.schemas.carrier import CarrierResponse
from app.schemas.port import PortResponse


class FreightRateBase(BaseModel):
    carrier_id: int
    origin_port_id: int
    destination_port_id: int
    service_code: str | None = None
    container_20gp: Decimal | None = None
    container_40gp: Decimal | None = None
    container_40hq: Decimal | None = None
    container_45: Decimal | None = None
    baf_20: Decimal | None = None
    baf_40: Decimal | None = None
    lss_20: Decimal | None = None
    lss_40: Decimal | None = None
    currency: str = "USD"
    valid_from: date | None = None
    valid_to: date | None = None
    transit_days: int | None = None
    is_direct: bool = True
    remarks: str | None = None
    source_type: SourceType = SourceType.manual
    source_file: str | None = None
    upload_batch_id: str | None = None
    status: RateStatus = RateStatus.draft


class FreightRateCreate(FreightRateBase):
    pass


class FreightRateUpdate(BaseModel):
    carrier_id: int | None = None
    origin_port_id: int | None = None
    destination_port_id: int | None = None
    service_code: str | None = None
    container_20gp: Decimal | None = None
    container_40gp: Decimal | None = None
    container_40hq: Decimal | None = None
    container_45: Decimal | None = None
    baf_20: Decimal | None = None
    baf_40: Decimal | None = None
    lss_20: Decimal | None = None
    lss_40: Decimal | None = None
    currency: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    transit_days: int | None = None
    is_direct: bool | None = None
    remarks: str | None = None
    status: RateStatus | None = None


class FreightRateResponse(FreightRateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FreightRateDetail(FreightRateResponse):
    """包含关联对象的详细响应"""
    carrier: CarrierResponse | None = None
    origin_port: PortResponse | None = None
    destination_port: PortResponse | None = None


class FreightRateBulkCreate(BaseModel):
    """批量创建（解析导入用）"""
    rates: list[FreightRateCreate]


class RateCompareItem(BaseModel):
    """航线比价条目"""
    carrier_code: str
    carrier_name: str
    container_20gp: Decimal | None = None
    container_40gp: Decimal | None = None
    container_40hq: Decimal | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    transit_days: int | None = None
    source_type: str | None = None


class RateCompareResponse(BaseModel):
    """航线比价响应"""
    origin: PortResponse
    destination: PortResponse
    rates: list[RateCompareItem]
    total: int
