"""Air / Sea 空白模板的填充配置注册表。

列映射与数据起始行均由实地调研空白模板（资料/2026.05.27）确定：
- Air `May 25 to May 31`：表头 r1，数据起 r2；A 起运港 / B 目的港 / C 服务 / D-J 每日价 / K 备注
- Sea `JP N RATE FCL & LCL`：表头 r8，数据起 r9；A 目的港 / B 船司 / C 箱型 / D 运费 …
"""
from __future__ import annotations

from pathlib import Path

from app.services.step1_rates.sheet_builder.entities import (
    SheetFillConfig,
    TemplateConfig,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


_AIR = TemplateConfig(
    template_type="air",
    template_path=_TEMPLATES_DIR / "air_blank.xlsx",
    sheets=(
        SheetFillConfig(
            sheet_name="May 25 to May 31",
            header_row=1,
            data_start_row=2,
            columns={
                "origin": 1,
                "destination": 2,
                "service": 3,
                "day1": 4,
                "day2": 5,
                "day3": 6,
                "day4": 7,
                "day5": 8,
                "day6": 9,
                "day7": 10,
                "remark": 11,
            },
        ),
    ),
)


_SEA = TemplateConfig(
    template_type="sea",
    template_path=_TEMPLATES_DIR / "sea_blank.xlsx",
    sheets=(
        SheetFillConfig(
            sheet_name="JP N RATE FCL & LCL",
            header_row=8,
            data_start_row=9,
            columns={
                "destination": 1,
                "carrier": 2,
                "container": 3,
                "freight": 4,
                "lss_cic": 5,
                "baf": 6,
                "ebs": 7,
                "yas_caf": 8,
                "sailing": 9,
                "via": 10,
                "transit": 11,
                "booking": 12,
                "rmks": 17,
            },
        ),
    ),
)


_REGISTRY: dict[str, TemplateConfig] = {"air": _AIR, "sea": _SEA}


def get_template_config(template_type: str) -> TemplateConfig:
    """按模板类型取填充配置。未知类型抛 ValueError。"""
    try:
        return _REGISTRY[template_type]
    except KeyError as exc:
        raise ValueError(
            f"unknown template_type {template_type!r}（支持: air / sea）"
        ) from exc


def supported_template_types() -> list[str]:
    return list(_REGISTRY.keys())
