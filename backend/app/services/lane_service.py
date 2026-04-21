"""航线业务逻辑"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lane import Lane, TransportMode
from app.schemas.lane import LaneCreate, LaneUpdate


def get_lanes(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    origin: str | None = None,
    destination: str | None = None,
    transport_mode: TransportMode | None = None,
) -> tuple[list[Lane], int]:
    """获取航线列表（分页+筛选）"""
    query = select(Lane)

    if origin:
        query = query.where(
            (Lane.origin_code.ilike(f"%{origin}%")) | (Lane.origin_city.ilike(f"%{origin}%"))
        )
    if destination:
        query = query.where(
            (Lane.destination_code.ilike(f"%{destination}%")) | (Lane.destination_city.ilike(f"%{destination}%"))
        )
    if transport_mode:
        query = query.where(Lane.transport_mode == transport_mode)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    query = query.order_by(Lane.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(query).scalars().all())

    return items, total


def get_lane(db: Session, lane_id: int) -> Lane | None:
    return db.get(Lane, lane_id)


def create_lane(db: Session, data: LaneCreate) -> Lane:
    lane = Lane(**data.model_dump())
    db.add(lane)
    db.commit()
    db.refresh(lane)
    return lane


def update_lane(db: Session, lane_id: int, data: LaneUpdate) -> Lane | None:
    lane = db.get(Lane, lane_id)
    if not lane:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lane, key, value)
    db.commit()
    db.refresh(lane)
    return lane


def delete_lane(db: Session, lane_id: int) -> bool:
    lane = db.get(Lane, lane_id)
    if not lane:
        return False
    db.delete(lane)
    db.commit()
    return True
