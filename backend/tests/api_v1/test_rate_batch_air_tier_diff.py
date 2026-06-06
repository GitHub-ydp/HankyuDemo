import uuid
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.models import Base
from app.services import rate_batch_service
from app.services.rate_batch_service import DraftRateBatch


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()


def test_air_tier_diff_is_neutral(db):
    bid = uuid.uuid4().hex
    now = datetime(2026, 6, 5)
    draft = DraftRateBatch(
        batch_id=bid, file_name="air_tier_rate_sheet_filled.xlsx", source_type="excel",
        batch_status="draft", activation_status="pending", adapter_key="air_tier",
        parser_hint=None, carrier_code=None, total_rows=3, warnings=[], sheets=[],
        created_at=now, updated_at=now,
        legacy_payload={"file_type": "air_tier"}, parse_records=[],
    )
    rate_batch_service._draft_batches[bid] = draft
    try:
        out = rate_batch_service.get_rate_batch_diff(bid, db)
    finally:
        rate_batch_service._draft_batches.pop(bid, None)
    assert out is not None
    assert out["summary"]["total_rows"] == 3
    assert out["summary"]["changed_rows"] == 0
    assert out["items"] == []
    assert "air_tier" in out["message"]


def test_normalize_row_air_tier_carries_tier_fields():
    """air_tier 预览行必须带上档位价/航司/货类等字段，否则导入页预览空白。"""
    row = {
        "record_kind": "air_tier",
        "origin_port_name": "PVG",
        "destination_port_name": "KIX",
        "service_desc": "托盘1:200",
        "currency": "CNY",
        "carrier": "CK/MU",  # air_tier 的航司来自 extras，并入 legacy dict
        "cargo_class": "普货",
        "packing": "托盘",
        "density": "1:200",
        "tier_prices": {45: 17.0, 100: 14.0},  # adapter 产出 int 键
        "valid_from": "2026-05-21",
    }
    pv = rate_batch_service._normalize_row(row, 1)["preview"]
    assert pv["record_kind"] == "air_tier"
    assert pv["carrier"] == "CK/MU"          # 航司不再为空
    # 键须归一为 str（否则响应 schema dict[str,...] 校验 int 键 400）
    assert pv["tier_prices"] == {"45": 17.0, "100": 14.0}
    assert pv["cargo_class"] == "普货"
    assert pv["packing"] == "托盘"
    assert pv["density"] == "1:200"
