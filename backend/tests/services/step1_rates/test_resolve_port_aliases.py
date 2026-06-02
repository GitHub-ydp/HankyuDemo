import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.port import Port
from app.services.step1_rates.activator_mappers import _resolve_port


@pytest.fixture()
def db():
    import app.models  # noqa: F401 注册全部模型
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="KRPUS", name_en="Busan", name_cn="釜山"),
        Port(un_locode="TWKHH", name_en="Kaohsiung", name_cn="高雄"),
        Port(un_locode="INKTP", name_en="Kattupalli", name_cn="卡图帕利"),
        Port(un_locode="BDCGP", name_en="Chattogram", name_cn="吉大港"),
        Port(un_locode="MYPKG", name_en="Port Kelang", name_cn="巴生港"),
        Port(un_locode="TWTXG", name_en="Taichung", name_cn="台中"),
        Port(un_locode="USSTL", name_en="St. Louis", name_cn="圣路易斯"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_resolve_variant_ports(db):
    cases = {
        "PUSAN": "KRPUS",
        "KAOHSIUNG CITY": "TWKHH",
        "KATTUPALLI PORT": "INKTP",
        "CHITTAGONG": "BDCGP",
        "PORT KLANG": "MYPKG",
        "TAICHUNG CITY": "TWTXG",
        "SAINT LOUIS": "USSTL",
    }
    for raw, expected in cases.items():
        port = _resolve_port(db, raw)
        assert port is not None, f"{raw} 应解析到港"
        assert port.un_locode == expected, f"{raw} → {port.un_locode}, 期望 {expected}"
