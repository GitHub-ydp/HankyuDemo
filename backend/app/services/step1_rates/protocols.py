from __future__ import annotations

from pathlib import Path
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.step1_rates.entities import ParsedRateBatch, Step1FileType


class RateAdapter(Protocol):
    """Step1 费率来源适配器协议。"""

    key: str
    file_type: "Step1FileType"
    priority: int

    def detect(self, path: Path, *, file_type_hint: "Step1FileType | None" = None) -> bool:
        """按文件名和提示识别是否由当前适配器处理。"""

    def parse(self, path: Path, db: Session | None = None) -> "ParsedRateBatch":
        """执行解析并返回 Step1 文档定义的统一批次结构。"""
