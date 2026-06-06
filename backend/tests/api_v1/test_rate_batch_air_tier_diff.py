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
