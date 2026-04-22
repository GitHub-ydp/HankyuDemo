from __future__ import annotations

from typing import Protocol

from app.services.step1_rates.entities import Step1FileType


class RateWriter(Protocol):
    """Step1 原格式回填 writer 契约。"""

    key: str
    file_type: Step1FileType

    def write(self, batch_id: str) -> tuple[bytes, str]:
        """根据 batch_id 回填原件模板并返回 (xlsx bytes, 建议文件名)。"""
        ...
