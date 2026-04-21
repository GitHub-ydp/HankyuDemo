from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.step1_rates.entities import ParsedRateBatch, Step1FileType


class AirAdapter:
    """Step1 Air adapter。"""

    key = "air"
    file_type = Step1FileType.air
    priority = 10

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        if file_type_hint == self.file_type:
            return True
        normalized_name = path.name.lower()
        return "air" in normalized_name or "market price" in normalized_name

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        return ParsedRateBatch(
            file_type=self.file_type,
            source_file=path.name,
            adapter_key=self.key,
            warnings=[
                "TODO: 接入 Step1 Air 周表与 Surcharges 真实解析逻辑。",
                "当前仅提供文档对齐后的骨架接口，不再暴露旧的 KMTC/NVO/AI 语义。",
            ],
            metadata={
                "status": "stub",
                "todo": [
                    "解析周表 sheet",
                    "解析 Surcharges sheet",
                    "抽取 effective_week_start/effective_week_end",
                ],
            },
        )
