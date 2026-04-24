"""一次性脚本：从 air_freight_rates.service_desc 回填 airline_code。

仅用于 2026-04-24 Step1 四闭环前入库的历史 Air 行（airline_code IS NULL）。
新导入批次走 adapter + mapper 的前向修复路径（T-AC-01），无需此脚本。

用法（Windows 开发机）：
    D:\\Anaconda3\\envs\\py310\\python.exe backend/scripts/backfill_airline_code_20260424.py          # dry-run
    D:\\Anaconda3\\envs\\py310\\python.exe backend/scripts/backfill_airline_code_20260424.py --apply  # 真写库

macOS 开发机：
    backend/.venv/bin/python backend/scripts/backfill_airline_code_20260424.py [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在 backend 根目录之外也能 import app.*
_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models import AirFreightRate  # noqa: E402
from app.services.step1_rates.adapters.air import AirAdapter  # noqa: E402


AIRLINE_CODE_RE = AirAdapter._AIRLINE_CODE_RE
AIRLINE_CODE_MAX_LEN = 20


def _extract_code(service_desc: str | None) -> str | None:
    if not service_desc:
        return None
    codes = AIRLINE_CODE_RE.findall(service_desc)
    if not codes:
        return None
    unique_ordered = list(dict.fromkeys(codes))
    joined = "/".join(unique_ordered)
    return joined[:AIRLINE_CODE_MAX_LEN]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真写库。默认 dry-run，只打印将要更新的行。",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    session = SessionLocal()
    try:
        rows = (
            session.query(AirFreightRate)
            .filter(AirFreightRate.airline_code.is_(None))
            .all()
        )
        total = len(rows)
        would_update = 0
        no_code = 0
        samples: list[tuple[int, str, str]] = []

        for row in rows:
            new_code = _extract_code(row.service_desc)
            if new_code is None:
                no_code += 1
                continue
            would_update += 1
            if len(samples) < 20:
                samples.append((row.id, row.service_desc or "", new_code))
            if not dry_run:
                row.airline_code = new_code

        if dry_run:
            print("[dry-run] 未写库。示例（前 20）：")
            for rid, desc, code in samples:
                print(f"  id={rid} service_desc={desc!r} -> airline_code={code!r}")
            print(
                f"汇总: total_null={total} would_update={would_update} "
                f"no_code={no_code}"
            )
            print("如需正式写库，追加 --apply 再跑一次。")
        else:
            session.commit()
            print(f"[apply] updated={would_update} no_code={no_code} total_null={total}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
