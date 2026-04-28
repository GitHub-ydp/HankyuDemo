"""承运人 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.carrier import CarrierType
from app.schemas.carrier import CarrierCreate, CarrierResponse, CarrierUpdate
from app.schemas.common import ApiResponse, PaginatedData
from app.services import carrier_service

router = APIRouter(prefix="/carriers", tags=["carriers"])


@router.get("", response_model=ApiResponse[PaginatedData[CarrierResponse]])
def list_carriers(
    page: int = 1,
    page_size: int = 20,
    type: CarrierType | None = None,
    keyword: str | None = None,
    only_used: bool = False,
    db: Session = Depends(get_db),
):
    """获取承运人列表。only_used=true 只返回被运价引用过的船司（前端管理页默认值）。"""
    items, total = carrier_service.get_carriers(
        db,
        page=page,
        page_size=page_size,
        carrier_type=type,
        keyword=keyword,
        only_used=only_used,
    )
    return ApiResponse(data=PaginatedData(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.post("", response_model=ApiResponse[CarrierResponse])
def create_carrier(data: CarrierCreate, db: Session = Depends(get_db)):
    """新增承运人"""
    carrier = carrier_service.create_carrier(db, data)
    return ApiResponse(data=carrier)


@router.get("/{carrier_id}", response_model=ApiResponse[CarrierResponse])
def get_carrier(carrier_id: int, db: Session = Depends(get_db)):
    """获取承运人详情"""
    carrier = carrier_service.get_carrier(db, carrier_id)
    if not carrier:
        raise HTTPException(status_code=404, detail="承运人不存在")
    return ApiResponse(data=carrier)


@router.put("/{carrier_id}", response_model=ApiResponse[CarrierResponse])
def update_carrier(carrier_id: int, data: CarrierUpdate, db: Session = Depends(get_db)):
    """更新承运人"""
    carrier = carrier_service.update_carrier(db, carrier_id, data)
    if not carrier:
        raise HTTPException(status_code=404, detail="承运人不存在")
    return ApiResponse(data=carrier)


@router.delete("/{carrier_id}", response_model=ApiResponse)
def delete_carrier(carrier_id: int, db: Session = Depends(get_db)):
    """删除承运人"""
    if not carrier_service.delete_carrier(db, carrier_id):
        raise HTTPException(status_code=404, detail="承运人不存在")
    return ApiResponse(message="删除成功")
