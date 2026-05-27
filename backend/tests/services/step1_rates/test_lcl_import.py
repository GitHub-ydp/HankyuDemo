"""Step1 LCL 入库回归测试。

锁住两个新能力：
1. LCL record（kind=lcl / ocean_ngb_lcl）经 to_lcl_rate → LclRate（v0.1 曾设计为不入库）。
2. 港口名空格变体（"HONGKONG"↔"Hong Kong"）/ 英中斜杠（"Hong Kong/香港"）能解析
   （rate_parser._resolve_port 归一兜底）。
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, LclRate, Port
from app.services.step1_rates.activator_mappers import ActivationError, to_lcl_rate
from app.services.step1_rates.entities import ParsedRateRecord
import uuid


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    for code, en, cn in [
        ("CNSHA", "Shanghai", "上海"),
        ("HKHKG", "Hong Kong", "香港"),
        ("JPTYO", "Tokyo", "东京"),
    ]:
        session.add(Port(un_locode=code, name_en=en, name_cn=cn))
    session.commit()
    yield session
    session.close()


def _lcl(dest: str, kind: str = "lcl") -> ParsedRateRecord:
    return ParsedRateRecord(
        record_kind=kind,
        carrier_name="LCL",
        origin_port_name="Shanghai",
        destination_port_name=dest,
        freight_per_cbm=Decimal("5"),
        freight_per_ton=Decimal("10"),
        currency="USD",
        extras={"row_index": 1},
    )


def test_lcl_maps_to_lcl_rate(db: Session) -> None:
    """kind=lcl → LclRate，运费/港口/币种正确。"""
    rate = to_lcl_rate(_lcl("Tokyo"), uuid.uuid4(), db)
    assert isinstance(rate, LclRate)
    assert rate.freight_per_cbm == Decimal("5")
    assert rate.freight_per_ton == Decimal("10")
    assert rate.currency == "USD"
    tokyo = db.query(Port).filter(Port.un_locode == "JPTYO").one()
    assert rate.destination_port_id == tokyo.id


def test_lcl_space_variant_resolves(db: Session) -> None:
    """'HONGKONG'(无空格) 能解析到 'Hong Kong'（归一兜底）。"""
    rate = to_lcl_rate(_lcl("HONGKONG"), uuid.uuid4(), db)
    hk = db.query(Port).filter(Port.un_locode == "HKHKG").one()
    assert rate.destination_port_id == hk.id


def test_lcl_en_cn_slash_resolves(db: Session) -> None:
    """'Hong Kong/香港'(英中斜杠) 能解析（rate_parser 拆 '/')。"""
    rate = to_lcl_rate(_lcl("Hong Kong/香港"), uuid.uuid4(), db)
    hk = db.query(Port).filter(Port.un_locode == "HKHKG").one()
    assert rate.destination_port_id == hk.id


def test_ocean_ngb_lcl_kind_maps(db: Session) -> None:
    """kind=ocean_ngb_lcl 同样入 LclRate。"""
    rate = to_lcl_rate(_lcl("Tokyo", kind="ocean_ngb_lcl"), uuid.uuid4(), db)
    assert isinstance(rate, LclRate)


def test_lcl_missing_port_raises(db: Session) -> None:
    """目的港字典缺失 → PORT_NOT_FOUND（软失败，可被 activator 跳过）。"""
    with pytest.raises(ActivationError) as exc:
        to_lcl_rate(_lcl("NOWHERE PORT XYZ"), uuid.uuid4(), db)
    assert exc.value.code == "PORT_NOT_FOUND"
