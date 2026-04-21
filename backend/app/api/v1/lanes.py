"""航线 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.lane import TransportMode
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.lane import LaneCreate, LaneResponse, LaneUpdate
from app.services import lane_service

router = APIRouter(prefix="/lanes", tags=["lanes"])


@router.get("", response_model=ApiResponse[PaginatedData[LaneResponse]])
def list_lanes(
    page: int = 1,
    page_size: int = 20,
    origin: str | None = None,
    destination: str | None = None,
    transport_mode: TransportMode | None = None,
    db: Session = Depends(get_db),
):
    """获取航线列表"""
    items, total = lane_service.get_lanes(
        db, page=page, page_size=page_size,
        origin=origin, destination=destination, transport_mode=transport_mode,
    )
    return ApiResponse(data=PaginatedData(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.post("", response_model=ApiResponse[LaneResponse])
def create_lane(data: LaneCreate, db: Session = Depends(get_db)):
    """新增航线"""
    lane = lane_service.create_lane(db, data)
    return ApiResponse(data=lane)


@router.get("/{lane_id}", response_model=ApiResponse[LaneResponse])
def get_lane(lane_id: int, db: Session = Depends(get_db)):
    """获取航线详情"""
    lane = lane_service.get_lane(db, lane_id)
    if not lane:
        raise HTTPException(status_code=404, detail="航线不存在")
    return ApiResponse(data=lane)


@router.put("/{lane_id}", response_model=ApiResponse[LaneResponse])
def update_lane(lane_id: int, data: LaneUpdate, db: Session = Depends(get_db)):
    """更新航线"""
    lane = lane_service.update_lane(db, lane_id, data)
    if not lane:
        raise HTTPException(status_code=404, detail="航线不存在")
    return ApiResponse(data=lane)


@router.delete("/{lane_id}", response_model=ApiResponse)
def delete_lane(lane_id: int, db: Session = Depends(get_db)):
    """删除航线"""
    if not lane_service.delete_lane(db, lane_id):
        raise HTTPException(status_code=404, detail="航线不存在")
    return ApiResponse(message="删除成功")
