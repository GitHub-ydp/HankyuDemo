"""船司/供应商业务逻辑"""
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.carrier import Carrier, CarrierType
from app.models.freight_rate import FreightRate
from app.schemas.carrier import CarrierCreate, CarrierUpdate


def get_carriers(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    carrier_type: CarrierType | None = None,
    keyword: str | None = None,
    only_used: bool = False,
) -> tuple[list[Carrier], int]:
    """获取船司列表（分页+筛选）。

    only_used=True 时只返回"被运价引用过"的船司——通过 freight_rates.carrier_id
    EXISTS 反查。用于"一键清空后页面看起来空 / 导入运价后只显示命中"的 UX。
    air_freight_rates / lcl_rates / domestic_rates 不挂 carrier_id 外键，故只查 freight_rates。
    """
    query = select(Carrier)

    if carrier_type:
        query = query.where(Carrier.carrier_type == carrier_type)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(
            Carrier.code.ilike(like),
            Carrier.name_en.ilike(like),
            Carrier.name_cn.ilike(like),
        ))
    if only_used:
        query = query.where(
            exists().where(FreightRate.carrier_id == Carrier.id)
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    query = query.order_by(Carrier.id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(query).scalars().all())

    return items, total


def get_carrier(db: Session, carrier_id: int) -> Carrier | None:
    return db.get(Carrier, carrier_id)


def create_carrier(db: Session, data: CarrierCreate) -> Carrier:
    carrier = Carrier(**data.model_dump())
    db.add(carrier)
    db.commit()
    db.refresh(carrier)
    return carrier


def update_carrier(db: Session, carrier_id: int, data: CarrierUpdate) -> Carrier | None:
    carrier = db.get(Carrier, carrier_id)
    if not carrier:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(carrier, key, value)
    db.commit()
    db.refresh(carrier)
    return carrier


def delete_carrier(db: Session, carrier_id: int) -> bool:
    carrier = db.get(Carrier, carrier_id)
    if not carrier:
        return False
    db.delete(carrier)
    db.commit()
    return True
