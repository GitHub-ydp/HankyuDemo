"""运价管理 / 航线比价 air_tier tab：列表查询 + 比价 + 响应序列化回归。"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, AirTierRate, ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.schemas.freight_rate import AirTierRateResponse, RateType
from app.services import freight_rate_service as svc


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    bid = uuid.uuid4()
    s.add(ImportBatch(
        batch_id=bid, file_type=ImportBatchFileType.air_tier, source_file="x.xlsx",
        row_count=2, status=ImportBatchStatus.active, imported_by="t",
    ))
    s.add(AirTierRate(
        origin="PVG", destination="KIX", carrier="CK/MU", service_desc="CK/MU",
        tier_prices={45: 17.0, 100: 14.0}, currency="CNY", batch_id=bid,
    ))
    s.add(AirTierRate(
        origin="PVG", destination="NRT", carrier="NH", service_desc="托盘1:200",
        tier_prices={500: 13.5, 1000: 13.0}, currency="CNY", batch_id=bid,
    ))
    s.commit()
    yield s
    s.close()


def test_list_air_tier_returns_rows(db):
    items, total = svc.list_rates_by_type(db, RateType.air_tier, page=1, page_size=20)
    assert total == 2
    assert {i.destination for i in items} == {"KIX", "NRT"}


def test_list_air_tier_filter_by_dest_and_carrier(db):
    items, total = svc.list_rates_by_type(db, RateType.air_tier, destination_text="KIX")
    assert total == 1 and items[0].carrier == "CK/MU"
    items, total = svc.list_rates_by_type(db, RateType.air_tier, airline_code="NH")
    assert total == 1 and items[0].destination == "NRT"


def test_air_tier_response_serializes_tier_prices_with_str_keys(db):
    items, _ = svc.list_rates_by_type(db, RateType.air_tier, destination_text="KIX")
    resp = AirTierRateResponse.model_validate(items[0])
    # int 档位键须归一为 str（否则前端取值 / JSON 序列化错位）
    assert resp.tier_prices == {"45": 17.0, "100": 14.0}
    assert resp.carrier == "CK/MU"
    assert isinstance(resp.batch_id, str)


def test_compare_air_tier_groups_by_lane(db):
    out = svc.compare_rates_by_type(db, RateType.air_tier, origin_text="PVG", destination_text="KIX")
    assert out["total"] == 1
    assert out["rates"][0]["tier_prices"] == {"45": 17.0, "100": 14.0}
    assert out["rates"][0]["carrier"] == "CK/MU"
