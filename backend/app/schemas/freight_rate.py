"""海运费率 Schema"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.freight_rate import RateStatus, SourceType
from app.schemas.carrier import CarrierResponse
from app.schemas.port import PortResponse


class RateType(str, enum.Enum):
    """运价类型（RateList 5 tab + RateCompare 4 tab 共用，前端 i18n key 的 snake value 与本 enum value 一致）。"""
    ocean_fcl = "ocean_fcl"
    ocean_ngb = "ocean_ngb"
    air_weekly = "air_weekly"
    air_surcharge = "air_surcharge"
    lcl = "lcl"


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


class OceanCompareItem(BaseModel):
    """海运 FCL / NGB 比价条目（原 RateCompareItem 扩容：加 rate_id / status / is_direct / baf / currency）。"""
    rate_id: int
    carrier_code: str
    carrier_name: str
    container_20gp: Decimal | None = None
    container_40gp: Decimal | None = None
    container_40hq: Decimal | None = None
    baf_20: Decimal | None = None
    baf_40: Decimal | None = None
    currency: str = "USD"
    valid_from: date | None = None
    valid_to: date | None = None
    transit_days: int | None = None
    is_direct: bool = True
    source_type: str | None = None
    status: str | None = None


# 兼容别名：前端 types/index.ts:130 仍可能 import RateCompareItem。保留到 v1.1 迁移完清理。
RateCompareItem = OceanCompareItem


class AirWeeklyCompareItem(BaseModel):
    """空运周价比价条目"""
    rate_id: int
    airline_code: str | None = None
    service_desc: str | None = None
    effective_week_start: date | None = None
    effective_week_end: date | None = None
    price_day1: Decimal | None = None
    price_day2: Decimal | None = None
    price_day3: Decimal | None = None
    price_day4: Decimal | None = None
    price_day5: Decimal | None = None
    price_day6: Decimal | None = None
    price_day7: Decimal | None = None
    currency: str = "CNY"
    remark: str | None = None


class LclCompareItem(BaseModel):
    """拼箱比价条目"""
    rate_id: int
    freight_per_cbm: Decimal | None = None
    freight_per_ton: Decimal | None = None
    currency: str = "USD"
    lss: str | None = None
    ebs: str | None = None
    cic: str | None = None
    ams_aci_ens: str | None = None
    sailing_day: str | None = None
    via: str | None = None
    transit_time_text: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class RateCompareResponse(BaseModel):
    """航线比价响应（保留老签名，仅海运链路使用）"""
    origin: PortResponse
    destination: PortResponse
    rates: list[OceanCompareItem]
    total: int


class AirWeeklyRateResponse(BaseModel):
    """空运周价列表响应（RateList air_weekly tab）"""
    id: int
    origin: str
    destination: str
    airline_code: str | None = None
    service_desc: str | None = None
    effective_week_start: date | None = None
    effective_week_end: date | None = None
    price_day1: Decimal | None = None
    price_day2: Decimal | None = None
    price_day3: Decimal | None = None
    price_day4: Decimal | None = None
    price_day5: Decimal | None = None
    price_day6: Decimal | None = None
    price_day7: Decimal | None = None
    currency: str = "CNY"
    remark: str | None = None
    batch_id: str

    @field_validator("batch_id", mode="before")
    @classmethod
    def _stringify_batch_id(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    class Config:
        from_attributes = True


class AirSurchargeResponse(BaseModel):
    """空运附加费列表响应（RateList air_surcharge tab）"""
    id: int
    airline_code: str | None = None
    from_region: str | None = None
    area: str | None = None
    destination_scope: str | None = None
    myc_min: Decimal | None = None
    myc_fee_per_kg: Decimal | None = None
    msc_min: Decimal | None = None
    msc_fee_per_kg: Decimal | None = None
    effective_date: date | None = None
    currency: str = "CNY"
    remarks: str | None = None
    batch_id: str

    @field_validator("batch_id", mode="before")
    @classmethod
    def _stringify_batch_id(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    class Config:
        from_attributes = True


class LclRateResponse(BaseModel):
    """拼箱列表响应（RateList lcl tab）"""
    id: int
    origin_port: PortResponse | None = None
    destination_port: PortResponse | None = None
    freight_per_cbm: Decimal | None = None
    freight_per_ton: Decimal | None = None
    currency: str = "USD"
    lss: str | None = None
    ebs: str | None = None
    cic: str | None = None
    ams_aci_ens: str | None = None
    sailing_day: str | None = None
    via: str | None = None
    transit_time_text: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    batch_id: str

    @field_validator("batch_id", mode="before")
    @classmethod
    def _stringify_batch_id(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    class Config:
        from_attributes = True
