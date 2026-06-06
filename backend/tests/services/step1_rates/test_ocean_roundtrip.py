import uuid
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Carrier, Port
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.ocean import OceanAdapter
from app.services.step1_rates.activator_mappers import to_freight_rate_from_ocean


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


def test_ocean_roundtrip_split_and_lossless(tmp_path, db):
    rows = [{
        "origin": "SHANGHAI", "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "currency": "USD", "valid_from": "2026-06-01", "valid_to": "2026-06-30",
        "rate_level": "NAC", "service_code": "EC1", "remark": "rt",
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_sea_filled.xlsx"
    path.write_bytes(content)

    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert len(fcl) == 1
    rate = to_freight_rate_from_ocean(fcl[0], uuid.uuid4(), db, source_file="rt.xlsx")
    assert rate.container_20gp == Decimal("1000")
    assert rate.container_40gp == Decimal("1800")
    assert rate.container_40hq == Decimal("1850")   # 关键：拆分不丢
    assert rate.currency == "USD"
    assert str(rate.valid_from) == "2026-06-01"
    assert rate.rate_level == "NAC"
    assert rate.service_code == "EC1"


def test_ocean_roundtrip_via_transit_fidelity(tmp_path, db):
    import uuid
    from app.services.step1_rates.adapters.ocean import OceanAdapter
    from app.services.step1_rates.activator_mappers import to_freight_rate_from_ocean
    from app.services.step1_rates.sheet_builder.template_filler import fill_template
    long_via = "VIA " + "X" * 200  # >100
    rows = [{
        "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "via": long_via, "transit": 18, "sailing": "S" * 80,
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_via_transit.xlsx"
    path.write_bytes(content)
    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert fcl
    # transit 不再被 h:mm 格式损坏成 1900 日期
    assert "1900" not in str(fcl[0].transit_time_text or "")
    assert "18" in str(fcl[0].transit_time_text or "")
    rate = to_freight_rate_from_ocean(fcl[0], uuid.uuid4(), db, source_file="x")
    assert len(rate.via) <= 100          # via 裁到列长
    assert len(rate.sailing_day) <= 50   # sailing_day 裁到列长
