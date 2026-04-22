from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import rate_batch_service
from app.services.rate_batch_service import DraftRateBatch


REAL_RATE_DIR = (
    Path(__file__).resolve().parents[5]
    / "资料"
    / "2026.04.21"
    / "RE_ 今後の進め方に関するご提案"
)

REAL_AIR_FILE = REAL_RATE_DIR / "【Air】 Market Price updated on  Apr 20.xlsx"
REAL_OCEAN_FILE = REAL_RATE_DIR / "【Ocean】 Sea Net Rate_2026_Apr.21 - Apr.30.xlsx"
REAL_OCEAN_NGB_FILE = (
    REAL_RATE_DIR / "【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx"
)


def _register_draft(batch, file_path: Path, adapter_key: str) -> str:
    legacy = batch.to_legacy_dict()
    now = datetime.now(timezone.utc)
    draft = DraftRateBatch(
        batch_id=legacy["batch_id"],
        file_name=file_path.name,
        source_type="excel",
        batch_status="draft",
        activation_status="not_activated",
        adapter_key=legacy.get("adapter_key") or adapter_key,
        parser_hint=None,
        carrier_code=legacy.get("carrier_code"),
        total_rows=legacy.get("total_rows", 0),
        warnings=list(legacy.get("warnings", [])),
        sheets=[],
        created_at=now,
        updated_at=now,
        row_payloads=[],
        file_path=str(file_path),
        legacy_payload=legacy,
    )
    rate_batch_service._draft_batches[draft.batch_id] = draft
    return draft.batch_id


@pytest.fixture(scope="module")
def air_batch_id() -> str:
    from app.services.step1_rates.adapters.air import AirAdapter

    if not REAL_AIR_FILE.exists():
        pytest.skip(f"Air 真实样本不可用：{REAL_AIR_FILE}")
    batch = AirAdapter().parse(REAL_AIR_FILE)
    return _register_draft(batch, REAL_AIR_FILE, "air")


@pytest.fixture(scope="module")
def ocean_batch_id() -> str:
    from app.services.step1_rates.adapters.ocean import OceanAdapter

    if not REAL_OCEAN_FILE.exists():
        pytest.skip(f"Ocean 真实样本不可用：{REAL_OCEAN_FILE}")
    batch = OceanAdapter().parse(REAL_OCEAN_FILE)
    return _register_draft(batch, REAL_OCEAN_FILE, "ocean")


@pytest.fixture(scope="module")
def ocean_ngb_batch_id() -> str:
    from app.services.step1_rates.adapters.ocean_ngb import OceanNgbAdapter

    if not REAL_OCEAN_NGB_FILE.exists():
        pytest.skip(f"Ocean-NGB 真实样本不可用：{REAL_OCEAN_NGB_FILE}")
    batch = OceanNgbAdapter().parse(REAL_OCEAN_NGB_FILE)
    return _register_draft(batch, REAL_OCEAN_NGB_FILE, "ocean_ngb")
