"""费率业务逻辑"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.surcharge import Surcharge
from app.models.tariff import Tariff
from app.schemas.tariff import TariffCreate, TariffUpdate


def get_tariffs(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    lane_id: int | None = None,
    carrier_id: int | None = None,
    effective_after: date | None = None,
    effective_before: date | None = None,
    is_active: bool | None = None,
) -> tuple[list[Tariff], int]:
    """获取费率列表（分页+筛选）"""
    query = select(Tariff).options(joinedload(Tariff.surcharges))

    if lane_id:
        query = query.where(Tariff.lane_id == lane_id)
    if carrier_id:
        query = query.where(Tariff.carrier_id == carrier_id)
    if effective_after:
        query = query.where(Tariff.effective_date >= effective_after)
    if effective_before:
        query = query.where(Tariff.effective_date <= effective_before)
    if is_active is not None:
        query = query.where(Tariff.is_active == is_active)

    # 总数（不含 joinedload）
    count_q = select(func.count()).select_from(select(Tariff.id).where(*query.whereclause) if query.whereclause is not None else select(Tariff.id))
    # 简化计数
    base_filters = []
    if lane_id:
        base_filters.append(Tariff.lane_id == lane_id)
    if carrier_id:
        base_filters.append(Tariff.carrier_id == carrier_id)
    if effective_after:
        base_filters.append(Tariff.effective_date >= effective_after)
    if effective_before:
        base_filters.append(Tariff.effective_date <= effective_before)
    if is_active is not None:
        base_filters.append(Tariff.is_active == is_active)

    count_query = select(func.count()).select_from(Tariff)
    for f in base_filters:
        count_query = count_query.where(f)
    total = db.execute(count_query).scalar() or 0

    query = query.order_by(Tariff.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(query).unique().scalars().all())

    return items, total


def get_tariff(db: Session, tariff_id: int) -> Tariff | None:
    query = (
        select(Tariff)
        .options(joinedload(Tariff.surcharges), joinedload(Tariff.lane), joinedload(Tariff.carrier))
        .where(Tariff.id == tariff_id)
    )
    return db.execute(query).unique().scalar_one_or_none()


def create_tariff(db: Session, data: TariffCreate) -> Tariff:
    surcharges_data = data.surcharges
    tariff_dict = data.model_dump(exclude={"surcharges"})
    tariff = Tariff(**tariff_dict)

    for sc in surcharges_data:
        tariff.surcharges.append(Surcharge(**sc.model_dump()))

    db.add(tariff)
    db.commit()
    db.refresh(tariff)
    return tariff


def update_tariff(db: Session, tariff_id: int, data: TariffUpdate) -> Tariff | None:
    tariff = db.get(Tariff, tariff_id)
    if not tariff:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tariff, key, value)
    db.commit()
    db.refresh(tariff)
    return tariff


def delete_tariff(db: Session, tariff_id: int) -> bool:
    tariff = db.get(Tariff, tariff_id)
    if not tariff:
        return False
    db.delete(tariff)
    db.commit()
    return True
