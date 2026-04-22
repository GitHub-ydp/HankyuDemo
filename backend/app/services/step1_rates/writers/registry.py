from __future__ import annotations

from app.services.step1_rates.entities import Step1FileType
from app.services.step1_rates.writers.air import AirWriter
from app.services.step1_rates.writers.ocean import OceanWriter
from app.services.step1_rates.writers.ocean_ngb import OceanNgbWriter
from app.services.step1_rates.writers.protocols import RateWriter


_WRITERS: dict[Step1FileType, RateWriter] = {
    Step1FileType.air: AirWriter(),
    Step1FileType.ocean: OceanWriter(),
    Step1FileType.ocean_ngb: OceanNgbWriter(),
}


def get_writer(file_type: Step1FileType) -> RateWriter:
    """根据 file_type 取对应 writer。"""
    try:
        return _WRITERS[file_type]
    except KeyError as exc:
        raise ValueError(f"no writer registered for file_type={file_type}") from exc
