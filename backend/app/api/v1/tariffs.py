"""费率 API — 核心接口"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.tariff import TariffCreate, TariffDetailResponse, TariffResponse, TariffUpdate
from app.services import tariff_service

router = APIRouter(prefix="/tariffs", tags=["tariffs"])


@router.get("", response_model=ApiResponse[PaginatedData[TariffResponse]])
def list_tariffs(
    page: int = 1,
    page_size: int = 20,
    lane_id: int | None = None,
    carrier_id: int | None = None,
    effective_after: date | None = None,
    effective_before: date | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
):
    """获取费率列表"""
    items, total = tariff_service.get_tariffs(
        db, page=page, page_size=page_size,
        lane_id=lane_id, carrier_id=carrier_id,
        effective_after=effective_after, effective_before=effective_before,
        is_active=is_active,
    )
    return ApiResponse(data=PaginatedData(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.post("", response_model=ApiResponse[TariffResponse])
def create_tariff(data: TariffCreate, db: Session = Depends(get_db)):
    """新增费率"""
    tariff = tariff_service.create_tariff(db, data)
    return ApiResponse(data=tariff)


@router.get("/{tariff_id}", response_model=ApiResponse[TariffDetailResponse])
def get_tariff(tariff_id: int, db: Session = Depends(get_db)):
    """获取费率详情（含航线、承运人、附加费）"""
    tariff = tariff_service.get_tariff(db, tariff_id)
    if not tariff:
        raise HTTPException(status_code=404, detail="费率不存在")
    return ApiResponse(data=tariff)


@router.put("/{tariff_id}", response_model=ApiResponse[TariffResponse])
def update_tariff(tariff_id: int, data: TariffUpdate, db: Session = Depends(get_db)):
    """更新费率"""
    tariff = tariff_service.update_tariff(db, tariff_id, data)
    if not tariff:
        raise HTTPException(status_code=404, detail="费率不存在")
    return ApiResponse(data=tariff)


@router.delete("/{tariff_id}", response_model=ApiResponse)
def delete_tariff(tariff_id: int, db: Session = Depends(get_db)):
    """删除费率"""
    if not tariff_service.delete_tariff(db, tariff_id):
        raise HTTPException(status_code=404, detail="费率不存在")
    return ApiResponse(message="删除成功")
