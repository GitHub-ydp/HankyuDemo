"""数据导入服务 — 支持 Excel (.xlsx) 和 CSV"""
import io
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models.carrier import Carrier
from app.models.lane import Lane
from app.models.tariff import Tariff


def read_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """根据文件扩展名读取为 DataFrame"""
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(io.BytesIO(file_content))
    elif suffix == ".csv":
        return pd.read_csv(io.BytesIO(file_content))
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 .xlsx / .xls / .csv")


def preview_import(file_content: bytes, filename: str) -> dict:
    """预览导入文件内容（返回前 10 行和列信息）"""
    df = read_file(file_content, filename)
    return {
        "columns": list(df.columns),
        "row_count": len(df),
        "preview": df.head(10).fillna("").to_dict(orient="records"),
    }


def import_tariffs(
    db: Session,
    file_content: bytes,
    filename: str,
    column_mapping: dict[str, str] | None = None,
) -> dict:
    """
    批量导入费率数据

    column_mapping: 文件列名 → 系统字段名的映射，例如：
    {"起运地代码": "origin_code", "目的地代码": "destination_code", ...}
    """
    df = read_file(file_content, filename)

    # 如果有列映射，重命名列
    if column_mapping:
        df = df.rename(columns=column_mapping)

    created = 0
    skipped = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            row_dict = row.to_dict()

            # 查找或创建航线
            lane = _find_or_create_lane(db, row_dict)
            if not lane:
                errors.append({"row": idx + 2, "error": "无法匹配航线信息"})
                skipped += 1
                continue

            # 查找承运人
            carrier = _find_carrier(db, row_dict)
            if not carrier:
                errors.append({"row": idx + 2, "error": "无法匹配承运人信息"})
                skipped += 1
                continue

            # 创建费率
            tariff = Tariff(
                lane_id=lane.id,
                carrier_id=carrier.id,
                service_level=row_dict.get("service_level"),
                currency=row_dict.get("currency", "CNY"),
                base_rate=row_dict.get("base_rate", 0),
                unit=row_dict.get("unit", "per_kg"),
                min_charge=row_dict.get("min_charge"),
                transit_days=row_dict.get("transit_days"),
                effective_date=pd.to_datetime(row_dict.get("effective_date")).date()
                if row_dict.get("effective_date")
                else None,
                expiry_date=pd.to_datetime(row_dict.get("expiry_date")).date()
                if row_dict.get("expiry_date")
                else None,
                remarks=row_dict.get("remarks"),
                source=filename,
            )
            db.add(tariff)
            created += 1

        except Exception as e:
            errors.append({"row": idx + 2, "error": str(e)})
            skipped += 1

    db.commit()

    return {
        "total_rows": len(df),
        "created": created,
        "skipped": skipped,
        "errors": errors[:20],  # 最多返回 20 条错误
    }


def _find_or_create_lane(db: Session, row: dict) -> Lane | None:
    """根据行数据查找航线"""
    origin_code = row.get("origin_code")
    destination_code = row.get("destination_code")
    if not origin_code or not destination_code:
        return None

    lane = db.query(Lane).filter(
        Lane.origin_code == str(origin_code).strip(),
        Lane.destination_code == str(destination_code).strip(),
    ).first()

    return lane


def _find_carrier(db: Session, row: dict) -> Carrier | None:
    """根据行数据查找承运人"""
    carrier_name = row.get("carrier_name") or row.get("carrier")
    carrier_code = row.get("carrier_code")

    if carrier_code:
        carrier = db.query(Carrier).filter(Carrier.code == str(carrier_code).strip()).first()
        if carrier:
            return carrier

    if carrier_name:
        carrier = db.query(Carrier).filter(Carrier.name.ilike(f"%{str(carrier_name).strip()}%")).first()
        if carrier:
            return carrier

    return None
