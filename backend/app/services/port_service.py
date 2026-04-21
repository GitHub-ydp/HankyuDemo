"""港口服务"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Port


def get_ports(
    db: Session,
    keyword: str | None = None,
    region: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[Port], int]:
    """查询港口列表"""
    q = db.query(Port).filter(Port.is_active == True)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(
            Port.un_locode.ilike(like),
            Port.name_en.ilike(like),
            Port.name_cn.ilike(like),
        ))
    if region:
        q = q.filter(Port.region == region)

    total = q.count()
    items = q.order_by(Port.un_locode).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def get_port(db: Session, port_id: int) -> Port | None:
    return db.query(Port).filter(Port.id == port_id).first()


def get_port_by_locode(db: Session, locode: str) -> Port | None:
    return db.query(Port).filter(Port.un_locode == locode).first()
