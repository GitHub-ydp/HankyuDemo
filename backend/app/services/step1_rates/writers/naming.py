from __future__ import annotations

from datetime import date, datetime

from app.services.step1_rates.entities import Step1FileType


_MONTH_ABBR = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def _month_abbr(month: int) -> str:
    return _MONTH_ABBR[month - 1]


def _fmt_mmm_space_dd(value: date) -> str:
    return f"{_month_abbr(value.month)} {value.day:02d}"


def _fmt_mmm_dot_dd(value: date) -> str:
    return f"{_month_abbr(value.month)}.{value.day:02d}"


def build_filename(
    file_type: Step1FileType,
    effective_from: date | None,
    effective_to: date | None,
    *,
    now: datetime | None = None,
) -> str:
    """业务需求 §5.1 文件命名模板（Q-W6 默认值）。

    - Air:       `【Air】 Market Price updated on <MMM dd>.xlsx`
    - Ocean:     `【Ocean】 Sea Net Rate_<YYYY>_<MMM.dd> - <MMM.dd>.xlsx`
    - Ocean-NGB: `【Ocean-NGB】 Ocean FCL rate sheet  HHENGB <YYYY> <MMM_UPPER>.xlsx`
    - 若 `now` 非 None，在 `.xlsx` 之前追加 `_HHmmss`（同日重复导出）。
    """
    fallback = effective_from or (now.date() if now else date.today())

    if file_type == Step1FileType.air:
        base = f"【Air】 Market Price updated on {_fmt_mmm_space_dd(fallback)}"
    elif file_type == Step1FileType.ocean:
        start = effective_from or fallback
        end = effective_to or start
        base = (
            f"【Ocean】 Sea Net Rate_{start.year}_"
            f"{_fmt_mmm_dot_dd(start)} - {_fmt_mmm_dot_dd(end)}"
        )
    elif file_type == Step1FileType.ocean_ngb:
        base = (
            f"【Ocean-NGB】 Ocean FCL rate sheet  HHENGB "
            f"{fallback.year} {_month_abbr(fallback.month).upper()}"
        )
    else:
        raise ValueError(f"unsupported file_type: {file_type}")

    if now is not None:
        base = f"{base}_{now.strftime('%H%M%S')}"
    return f"{base}.xlsx"
