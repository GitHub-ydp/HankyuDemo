from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.step1_rates.entities import ParsedRateBatch, Step1FileType


class OceanNgbAdapter:
    """Step1 Ocean-NGB adapter。"""

    key = "ocean_ngb"
    file_type = Step1FileType.ocean_ngb
    priority = 30

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        if file_type_hint == self.file_type:
            return True
        normalized_name = path.name.lower()
        return "ocean-ngb" in normalized_name or "ocean ngb" in normalized_name or "ngb" in normalized_name

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        return ParsedRateBatch(
            file_type=self.file_type,
            source_file=path.name,
            adapter_key=self.key,
            warnings=[
                "TODO: 接入 Step1 Ocean-NGB Rate sheet 真实解析逻辑。",
                "当前骨架预留 Lv.1 / Lv.2 / Lv.3 / Net 分级语义。",
            ],
            metadata={
                "status": "stub",
                "todo": [
                    "只解析 Rate sheet",
                    "保留 rate_level",
                    "跳过 sample sheet",
                    "按需读取 Shipping line name 作为 lookup",
                ],
            },
        )
