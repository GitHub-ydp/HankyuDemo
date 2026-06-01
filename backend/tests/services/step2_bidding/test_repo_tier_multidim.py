"""query_air_tier：同港多泡比多行不崩 + extras 带结构化多维字段(SP4 用)。"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.air_tier_rate import AirTierRate
from app.models.base import Base
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed(db):
    bid = uuid.uuid4()
    db.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.air_tier,
                       status=ImportBatchStatus.active, row_count=2))
    db.add(AirTierRate(origin="PVG", destination="LAX", tier_prices={"45": 60, "100": 60},
                       currency="CNY", cargo_class="普货", packing="托", density="1:167",
                       carrier="CK/CA", batch_id=bid))
    db.add(AirTierRate(origin="PVG", destination="LAX", tier_prices={"100": 36},
                       currency="CNY", cargo_class="普货", packing="托", density="1:1000",
                       carrier="CK/CA", batch_id=bid))
    db.commit()


def test_query_air_tier_returns_multidim_rows(db_session):
    _seed(db_session)
    rows = Step1RateRepository(db_session).query_air_tier(origin="PVG", destination="LAX")

    assert len(rows) == 2, "同港多泡比应都返回，不崩"
    densities = {r.extras.get("density") for r in rows}
    assert densities == {"1:167", "1:1000"}
    r0 = next(r for r in rows if r.extras["density"] == "1:167")
    assert r0.extras["cargo_class"] == "普货"
    assert r0.extras["packing"] == "托"
    assert r0.extras["carrier"] == "CK/CA"
    assert r0.extras["tier_prices"] == {45: 60, 100: 60}
