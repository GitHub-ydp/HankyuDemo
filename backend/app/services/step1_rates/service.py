from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.step1_rates.adapters import AirAdapter, OceanAdapter, OceanNgbAdapter
from app.services.step1_rates.entities import ParsedRateBatch, Step1FileType
from app.services.step1_rates.normalizers import legacy_payload_to_parsed_batch
from app.services.step1_rates.registry import RateAdapterRegistry


def build_default_registry() -> RateAdapterRegistry:
    return RateAdapterRegistry(
        adapters=[
            AirAdapter(),
            OceanAdapter(),
            OceanNgbAdapter(),
        ]
    )


DEFAULT_RATE_ADAPTER_REGISTRY = build_default_registry()


def _coerce_parser_hint(parser_hint: str | None) -> Step1FileType | None:
    if not parser_hint:
        return None
    try:
        return Step1FileType(parser_hint)
    except ValueError:
        return None


def parse_rate_file(
    file_path: str | Path,
    db: Session,
    *,
    file_type_hint: Step1FileType | None = None,
    registry: RateAdapterRegistry | None = None,
) -> ParsedRateBatch:
    active_registry = registry or DEFAULT_RATE_ADAPTER_REGISTRY
    return active_registry.parse(Path(file_path), db=db, file_type_hint=file_type_hint)


def parse_rate_file_to_legacy(
    file_path: str | Path,
    db: Session | None,
    *,
    file_type_hint: Step1FileType | None = None,
    registry: RateAdapterRegistry | None = None,
) -> dict:
    return parse_rate_file(
        file_path,
        db,
        file_type_hint=file_type_hint,
        registry=registry,
    ).to_legacy_dict()


def parse_excel_file(
    file_path: str | Path,
    db: Session,
    *,
    file_name: str | None = None,
    parser_hint: str | None = None,
    registry: RateAdapterRegistry | None = None,
) -> ParsedRateBatch:
    del file_name
    return parse_rate_file(
        file_path,
        db,
        file_type_hint=_coerce_parser_hint(parser_hint),
        registry=registry,
    )


def parse_air_file(
    file_path: str,
    db: Session,
    *,
    registry: RateAdapterRegistry | None = None,
) -> ParsedRateBatch:
    return parse_rate_file(
        file_path,
        db,
        file_type_hint=Step1FileType.air,
        registry=registry,
    )


def parse_ocean_file(
    file_path: str,
    db: Session,
    *,
    registry: RateAdapterRegistry | None = None,
) -> ParsedRateBatch:
    return parse_rate_file(
        file_path,
        db,
        file_type_hint=Step1FileType.ocean,
        registry=registry,
    )


def parse_ocean_ngb_file(
    file_path: str,
    db: Session,
    *,
    registry: RateAdapterRegistry | None = None,
) -> ParsedRateBatch:
    return parse_rate_file(
        file_path,
        db,
        file_type_hint=Step1FileType.ocean_ngb,
        registry=registry,
    )


def build_batch_from_legacy_payload(
    payload: dict,
    *,
    file_type: Step1FileType,
    adapter_key: str | None = None,
    source_file: str | None = None,
    effective_from=None,
    effective_to=None,
) -> ParsedRateBatch:
    return legacy_payload_to_parsed_batch(
        payload,
        file_type=file_type,
        adapter_key=adapter_key,
        source_file=source_file,
        effective_from=effective_from,
        effective_to=effective_to,
    )
