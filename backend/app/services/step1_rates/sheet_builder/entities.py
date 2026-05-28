"""Rate Sheet Builder 内部 DTO。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SheetFillConfig:
    """单个 sheet 的填充配置：列语义 → 1-based 列号，以及表头/数据起始行。"""

    sheet_name: str
    header_row: int
    data_start_row: int
    columns: dict[str, int]


@dataclass(frozen=True)
class TemplateConfig:
    """一个空白模板（Air / Sea）的完整填充配置。"""

    template_type: str  # "air" | "sea"
    template_path: Path
    sheets: tuple[SheetFillConfig, ...]
