import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Carrier, Port
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.ocean import OceanAdapter


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    s.add(Port(un_locode="CNSHA", name_en="Shanghai", name_cn="上海"))
    s.add(Port(un_locode="USLAX", name_en="Los Angeles", name_cn="洛杉矶"))
    s.add(Carrier(code="ONE", name_en="Ocean Network Express"))
    s.commit()
    yield s
    s.close()


def test_ocean_reads_new_columns(tmp_path, db):
    rows = [{
        "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "currency": "EUR", "valid_from": "2026-06-01", "valid_to": "2026-06-30",
        "rate_level": "NAC", "service_code": "EC1", "remark": "rt",
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_sea_filled.xlsx"
    path.write_bytes(content)

    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert len(fcl) == 1
    r = fcl[0]
    assert r.container_40gp != r.container_40hq      # 拆分保留
    assert str(r.container_40gp) == "1800"
    assert str(r.container_40hq) == "1850"
    assert r.currency == "EUR"                        # 读到币种(非默认 USD)
    assert str(r.valid_from) == "2026-06-01"
    assert r.rate_level == "NAC"
    assert r.service_code == "EC1"


def test_ocean_overlong_fields_clipped(tmp_path, db):
    import uuid
    from app.services.step1_rates.activator_mappers import to_freight_rate_from_ocean
    rows = [{
        "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "currency": "USD/CNY/EUR", "rate_level": "Named Account Premium",
        "service_code": "TRANSPACIFIC-EXPRESS-WEEKLY-AE7",
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_overlong.xlsx"
    path.write_bytes(content)
    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert fcl
    fr = to_freight_rate_from_ocean(fcl[0], uuid.uuid4(), db, source_file="x")
    assert len(fr.currency) <= 5
    assert len(fr.rate_level) <= 10
    assert len(fr.service_code) <= 20
