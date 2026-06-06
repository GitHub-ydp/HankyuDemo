import uuid
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, AirTierRate, ImportBatch, ImportBatchStatus
from app.services.step1_rates import activator
from app.services.step1_rates.entities import ParsedRateRecord
from app.services.rate_batch_service import DraftRateBatch


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()


def _draft(records: list[ParsedRateRecord]) -> DraftRateBatch:
    now = datetime(2026, 6, 5)
    return DraftRateBatch(
        batch_id=str(uuid.uuid4()),
        file_name="air_tier_rate_sheet_filled.xlsx",
        source_type="excel",
        batch_status="draft",
        activation_status="pending",
        adapter_key="air_tier",
        parser_hint=None,
        carrier_code=None,
        total_rows=len(records),
        warnings=[],
        sheets=[],
        created_at=now,
        updated_at=now,
        legacy_payload={"file_type": "air_tier", "source_file": "air_tier_rate_sheet_filled.xlsx"},
        parse_records=records,
    )


def test_activate_air_tier_writes_rows(db):
    rec = ParsedRateRecord(
        record_kind="air_tier",
        origin_port_name="PVG",
        destination_port_name="NRT",
        service_desc="CA",
        currency="JPY",
        valid_from=date(2026, 6, 1),
        extras={"tier_prices": {45: 17.0, 100: 14.0}, "row_index": 2},
    )
    result = activator.activate(_draft([rec]), db, dry_run=False)
    assert result.activation_status == "activated"
    assert result.imported_detail.get("air_tier_rates") == 1
    rows = db.query(AirTierRate).all()
    assert len(rows) == 1
    assert rows[0].destination == "NRT"
    assert rows[0].currency == "JPY"
    batch = db.query(ImportBatch).one()
    assert batch.file_type.value == "air_tier"
    assert batch.status == ImportBatchStatus.active
