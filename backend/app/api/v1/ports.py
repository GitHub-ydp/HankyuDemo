"""港口 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.port import PortResponse
from app.services import port_service

router = APIRouter(prefix="/ports", tags=["ports"])


@router.get("", response_model=ApiResponse[PaginatedData[PortResponse]])
def list_ports(
    keyword: str | None = Query(None, description="搜索关键词（名称/代码）"),
    region: str | None = Query(None, description="区域筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items, total = port_service.get_ports(db, keyword=keyword, region=region, page=page, page_size=page_size)
    return ApiResponse(data=PaginatedData(
        items=[PortResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.get("/regions")
def list_regions(db: Session = Depends(get_db)):
    """获取所有区域列表"""
    from app.models import Port
    regions = db.query(Port.region).filter(Port.region != None).distinct().all()
    return ApiResponse(data=sorted([r[0] for r in regions]))


@router.get("/{port_id}", response_model=ApiResponse[PortResponse])
def get_port(port_id: int, db: Session = Depends(get_db)):
    port = port_service.get_port(db, port_id)
    if not port:
        return ApiResponse(code=404, message="港口不存在")
    return ApiResponse(data=PortResponse.model_validate(port))
