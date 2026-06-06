"""海运费率 API"""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import RateStatus
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.freight_rate import (
    AirSurchargeResponse,
    AirWeeklyRateResponse,
    FreightRateDetail,
    LclRateResponse,
    RateType,
)
from app.schemas.upload_log import ImportResultResponse, ParsePreviewResponse, ParsePreviewRow
from app.services import freight_rate_service
from app.services.rate_parser import (
    parse_kmtc_excel,
    parse_nvo_fak_excel,
)

router = APIRouter(prefix="/rates", tags=["rates"])

# AI 解析(/ai/parse-*) 暂存解析结果供 /ai/confirm 入库；文件导入已改走 draft→activate
_parse_cache: dict[str, dict] = {}


# ========== 费率查询 ==========

@router.get("")
def list_rates(
    rate_type: RateType | None = Query(None, description="运价类型 (ocean_fcl/ocean_ngb/air_weekly/air_surcharge/lcl)；缺省走老海运路径"),
    origin_port_id: int | None = Query(None),
    destination_port_id: int | None = Query(None),
    carrier_id: int | None = Query(None),
    origin: str | None = Query(None, description="起运港关键词（海运）"),
    destination: str | None = Query(None, description="目的港关键词（海运）"),
    carrier: str | None = Query(None, description="船司关键词（海运）"),
    status: str | None = Query(None, description="状态: draft/active/expired"),
    origin_text: str | None = Query(None, description="起运地文本（空运）"),
    destination_text: str | None = Query(None, description="目的地文本（空运）"),
    airline_code: str | None = Query(None, description="航司代码（空运）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """按 rate_type 分派 5 tab。缺省时走老海运逻辑（向后兼容）。"""
    if rate_type is None:
        items, total = freight_rate_service.get_rates(
            db,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
            carrier_id=carrier_id,
            origin_keyword=origin,
            destination_keyword=destination,
            carrier_keyword=carrier,
            status=status,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(data=PaginatedData(
            items=[FreightRateDetail.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        ))

    items, total = freight_rate_service.list_rates_by_type(
        db,
        rate_type,
        origin_port_id=origin_port_id,
        destination_port_id=destination_port_id,
        carrier_id=carrier_id,
        origin_keyword=origin,
        destination_keyword=destination,
        carrier_keyword=carrier,
        status=status,
        origin_text=origin_text,
        destination_text=destination_text,
        airline_code=airline_code,
        page=page,
        page_size=page_size,
    )

    if rate_type in (RateType.ocean_fcl, RateType.ocean_ngb):
        serialized = [FreightRateDetail.model_validate(i) for i in items]
    elif rate_type == RateType.air_weekly:
        serialized = [AirWeeklyRateResponse.model_validate(i) for i in items]
    elif rate_type == RateType.air_surcharge:
        serialized = [AirSurchargeResponse.model_validate(i) for i in items]
    elif rate_type == RateType.lcl:
        serialized = [LclRateResponse.model_validate(i) for i in items]
    else:
        serialized = []

    return ApiResponse(data=PaginatedData(
        items=serialized,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.get("/stats")
def rate_stats(db: Session = Depends(get_db)):
    """费率统计"""
    return ApiResponse(data=freight_rate_service.get_rate_stats(db))


@router.get("/compare")
def compare_rates(
    rate_type: RateType | None = Query(None, description="比价类型 (ocean_fcl/ocean_ngb/air_weekly/lcl)；缺省走老海运路径"),
    origin_port_id: int | None = Query(None, description="起运港ID（ocean/lcl）"),
    destination_port_id: int | None = Query(None, description="目的港ID（ocean/lcl）"),
    origin_text: str | None = Query(None, description="起运地文本（air_weekly）"),
    destination_text: str | None = Query(None, description="目的地文本（air_weekly）"),
    db: Session = Depends(get_db),
):
    """同航线多供应商比价；按 rate_type 分派 4 tab，缺省海运保持向后兼容。"""
    if rate_type is None:
        if origin_port_id is None or destination_port_id is None:
            return ApiResponse(code=400, message="origin_port_id / destination_port_id 必填")
        from app.services.port_service import get_port
        origin = get_port(db, origin_port_id)
        destination = get_port(db, destination_port_id)
        if not origin or not destination:
            return ApiResponse(code=400, message="无效的港口ID")

        rates = freight_rate_service.compare_rates(db, origin_port_id, destination_port_id)
        return ApiResponse(data={
            "origin": {"id": origin.id, "un_locode": origin.un_locode, "name_en": origin.name_en, "name_cn": origin.name_cn},
            "destination": {"id": destination.id, "un_locode": destination.un_locode, "name_en": destination.name_en, "name_cn": destination.name_cn},
            "rates": rates,
            "total": len(rates),
        })

    if rate_type == RateType.air_surcharge:
        return ApiResponse(code=400, message="air_surcharge 不支持比价")

    try:
        result = freight_rate_service.compare_rates_by_type(
            db,
            rate_type,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
            origin_text=origin_text,
            destination_text=destination_text,
        )
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))

    origin_obj = result["origin"]
    destination_obj = result["destination"]
    origin_payload = None
    destination_payload = None
    if hasattr(origin_obj, "un_locode"):
        origin_payload = {
            "id": origin_obj.id,
            "un_locode": origin_obj.un_locode,
            "name_en": origin_obj.name_en,
            "name_cn": origin_obj.name_cn,
        }
    else:
        origin_payload = origin_obj
    if hasattr(destination_obj, "un_locode"):
        destination_payload = {
            "id": destination_obj.id,
            "un_locode": destination_obj.un_locode,
            "name_en": destination_obj.name_en,
            "name_cn": destination_obj.name_cn,
        }
    else:
        destination_payload = destination_obj

    return ApiResponse(data={
        "origin": origin_payload,
        "destination": destination_payload,
        "rates": result["rates"],
        "total": result["total"],
        "rate_type": rate_type.value,
    })


@router.get("/{rate_id}", response_model=ApiResponse[FreightRateDetail])
def get_rate(rate_id: int, db: Session = Depends(get_db)):
    rate = freight_rate_service.get_rate(db, rate_id)
    if not rate:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(data=FreightRateDetail.model_validate(rate))


@router.put("/{rate_id}/status")
def update_status(rate_id: int, status: str = Query(...), db: Session = Depends(get_db)):
    """更新费率状态（draft → active / expired）"""
    try:
        rate_status = RateStatus(status)
    except ValueError:
        return ApiResponse(code=400, message=f"无效状态: {status}")
    rate = freight_rate_service.update_rate_status(db, rate_id, rate_status)
    if not rate:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(data={"id": rate_id, "status": status})


@router.put("/batch/{batch_id}/status")
def batch_update_status(batch_id: str, status: str = Query(...), db: Session = Depends(get_db)):
    """批量更新同批次费率状态"""
    try:
        rate_status = RateStatus(status)
    except ValueError:
        return ApiResponse(code=400, message=f"无效状态: {status}")
    count = freight_rate_service.batch_update_status(db, batch_id, rate_status)
    return ApiResponse(data={"batch_id": batch_id, "status": status, "updated_count": count})


@router.delete("/{rate_id}")
def delete_rate(rate_id: int, db: Session = Depends(get_db)):
    ok = freight_rate_service.delete_rate(db, rate_id)
    if not ok:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(message="删除成功")
