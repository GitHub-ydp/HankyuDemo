"""
费率数据批量导入脚本

用法:
    python scripts/import_tariff.py <文件路径> [--preview] [--dry-run]

支持格式: .xlsx, .xls, .csv
"""
import argparse
import sys
from pathlib import Path

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pandas as pd


def read_file(filepath: str) -> pd.DataFrame:
    """根据扩展名读取文件"""
    p = Path(filepath)
    if not p.exists():
        print(f"错误: 文件不存在 — {filepath}")
        sys.exit(1)

    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath)
    elif suffix == ".csv":
        df = pd.read_csv(filepath)
    else:
        print(f"错误: 不支持的格式 {suffix}，仅支持 .xlsx / .xls / .csv")
        sys.exit(1)

    print(f"读取成功: {len(df)} 行, {len(df.columns)} 列")
    print(f"列名: {list(df.columns)}")
    return df


def preview(df: pd.DataFrame, rows: int = 5):
    """预览数据"""
    print(f"\n=== 数据预览（前 {rows} 行）===")
    print(df.head(rows).to_string(index=False))
    print(f"\n总计: {len(df)} 行")

    # 数据质量报告
    print("\n=== 数据质量 ===")
    for col in df.columns:
        null_count = df[col].isna().sum()
        if null_count > 0:
            print(f"  {col}: {null_count} 个空值 ({null_count/len(df)*100:.1f}%)")

    unique_counts = {col: df[col].nunique() for col in df.columns if df[col].dtype == "object"}
    if unique_counts:
        print("\n=== 唯一值统计 ===")
        for col, count in sorted(unique_counts.items(), key=lambda x: x[1]):
            print(f"  {col}: {count} 种")


def import_to_db(df: pd.DataFrame, dry_run: bool = False):
    """导入到数据库"""
    try:
        from app.core.database import SessionLocal
        from app.models.carrier import Carrier
        from app.models.lane import Lane
        from app.models.tariff import Tariff
    except ImportError as e:
        print(f"错误: 无法导入后端模块 — {e}")
        print("请确保已安装依赖: pip install -r backend/requirements.txt")
        sys.exit(1)

    if dry_run:
        print("\n[试运行模式] 不会实际写入数据库")

    db = SessionLocal()
    created = 0
    skipped = 0
    errors = []

    try:
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            try:
                # 查找航线
                origin_code = str(row_dict.get("origin_code", "")).strip()
                dest_code = str(row_dict.get("destination_code", "")).strip()

                if not origin_code or not dest_code:
                    errors.append(f"第 {idx+2} 行: 缺少航线代码")
                    skipped += 1
                    continue

                if not dry_run:
                    lane = db.query(Lane).filter(
                        Lane.origin_code == origin_code,
                        Lane.destination_code == dest_code,
                    ).first()

                    if not lane:
                        errors.append(f"第 {idx+2} 行: 航线 {origin_code}→{dest_code} 不存在")
                        skipped += 1
                        continue

                    carrier_name = str(row_dict.get("carrier_name", "") or row_dict.get("carrier", "")).strip()
                    carrier = db.query(Carrier).filter(
                        Carrier.name.ilike(f"%{carrier_name}%")
                    ).first() if carrier_name else None

                    if not carrier:
                        errors.append(f"第 {idx+2} 行: 承运人 '{carrier_name}' 不存在")
                        skipped += 1
                        continue

                    tariff = Tariff(
                        lane_id=lane.id,
                        carrier_id=carrier.id,
                        base_rate=row_dict.get("base_rate", 0),
                        currency=row_dict.get("currency", "CNY"),
                        unit=row_dict.get("unit", "per_kg"),
                        effective_date=pd.to_datetime(row_dict.get("effective_date")).date()
                        if row_dict.get("effective_date") else None,
                        source="script_import",
                    )
                    db.add(tariff)

                created += 1

            except Exception as e:
                errors.append(f"第 {idx+2} 行: {str(e)}")
                skipped += 1

        if not dry_run:
            db.commit()
            print(f"\n导入完成!")
        else:
            print(f"\n试运行完成（未写入数据库）")

        print(f"  成功: {created}")
        print(f"  跳过: {skipped}")

        if errors:
            print(f"\n错误详情（共 {len(errors)} 条，显示前 10 条）:")
            for err in errors[:10]:
                print(f"  - {err}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="费率数据批量导入")
    parser.add_argument("file", help="要导入的文件路径 (.xlsx/.xls/.csv)")
    parser.add_argument("--preview", action="store_true", help="仅预览数据，不导入")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不实际写入数据库")
    args = parser.parse_args()

    df = read_file(args.file)
    preview(df)

    if args.preview:
        return

    confirm = input("\n是否继续导入? (y/N): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return

    import_to_db(df, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
