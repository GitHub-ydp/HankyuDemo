"""add step1 rate model skeleton

Revision ID: 20260421_0001
Revises: None
Create Date: 2026-04-21 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260421_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import_batch_file_type = sa.Enum(
    "air",
    "ocean",
    "ocean_ngb",
    name="importbatchfiletype",
    native_enum=False,
)
import_batch_status = sa.Enum(
    "draft",
    "active",
    "superseded",
    name="importbatchstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False, comment="批次 UUID"),
        sa.Column("file_type", import_batch_file_type, nullable=False, comment="文件类型"),
        sa.Column("source_file", sa.String(length=255), nullable=True, comment="来源文件名"),
        sa.Column("sheet_name", sa.String(length=100), nullable=True, comment="来源 Sheet"),
        sa.Column("effective_from", sa.Date(), nullable=True, comment="生效开始日期"),
        sa.Column("effective_to", sa.Date(), nullable=True, comment="生效结束日期"),
        sa.Column(
            "imported_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="导入时间",
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="记录数",
        ),
        sa.Column("status", import_batch_status, nullable=False, comment="批次状态"),
        sa.Column("imported_by", sa.String(length=100), nullable=True, comment="导入人"),
        sa.Column("diff_summary", sa.JSON(), nullable=True, comment="差异摘要"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", name="uq_import_batches_batch_id"),
    )
    op.create_index(
        "ix_import_batch_file_effective",
        "import_batches",
        ["file_type", "effective_from", "effective_to"],
        unique=False,
    )
    op.create_index("ix_import_batch_status", "import_batches", ["status"], unique=False)

    op.create_table(
        "air_freight_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False, comment="起运港/机场代码"),
        sa.Column("destination", sa.String(length=100), nullable=False, comment="目的地"),
        sa.Column("airline_code", sa.String(length=20), nullable=True, comment="航司代码"),
        sa.Column("service_desc", sa.String(length=100), nullable=True, comment="服务描述"),
        sa.Column("effective_week_start", sa.Date(), nullable=True, comment="周报价生效开始"),
        sa.Column("effective_week_end", sa.Date(), nullable=True, comment="周报价生效结束"),
        sa.Column("price_day1", sa.Numeric(10, 2), nullable=True, comment="第 1 天报价"),
        sa.Column("price_day2", sa.Numeric(10, 2), nullable=True, comment="第 2 天报价"),
        sa.Column("price_day3", sa.Numeric(10, 2), nullable=True, comment="第 3 天报价"),
        sa.Column("price_day4", sa.Numeric(10, 2), nullable=True, comment="第 4 天报价"),
        sa.Column("price_day5", sa.Numeric(10, 2), nullable=True, comment="第 5 天报价"),
        sa.Column("price_day6", sa.Numeric(10, 2), nullable=True, comment="第 6 天报价"),
        sa.Column("price_day7", sa.Numeric(10, 2), nullable=True, comment="第 7 天报价"),
        sa.Column("currency", sa.String(length=5), nullable=False, comment="币种"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("batch_id", sa.Uuid(), nullable=False, comment="所属导入批次"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.batch_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_air_freight_rate_origin_dest_week",
        "air_freight_rates",
        ["origin", "destination", "effective_week_start"],
        unique=False,
    )
    op.create_index("ix_air_freight_rate_batch", "air_freight_rates", ["batch_id"], unique=False)

    op.create_table(
        "air_surcharges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("area", sa.String(length=50), nullable=True, comment="区域"),
        sa.Column("from_region", sa.String(length=50), nullable=True, comment="起运区域"),
        sa.Column("airline_code", sa.String(length=20), nullable=True, comment="航司代码"),
        sa.Column("effective_date", sa.Date(), nullable=True, comment="生效日期"),
        sa.Column("myc_min", sa.Numeric(10, 2), nullable=True, comment="MYC 最低收费"),
        sa.Column("myc_fee_per_kg", sa.Numeric(10, 4), nullable=True, comment="MYC 每公斤收费"),
        sa.Column("msc_min", sa.Numeric(10, 2), nullable=True, comment="MSC 最低收费"),
        sa.Column("msc_fee_per_kg", sa.Numeric(10, 4), nullable=True, comment="MSC 每公斤收费"),
        sa.Column("destination_scope", sa.String(length=200), nullable=True, comment="目的地范围"),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
        sa.Column("currency", sa.String(length=5), nullable=False, comment="币种"),
        sa.Column("batch_id", sa.Uuid(), nullable=False, comment="所属导入批次"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.batch_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_air_surcharge_effective",
        "air_surcharges",
        ["effective_date", "airline_code"],
        unique=False,
    )
    op.create_index("ix_air_surcharge_batch", "air_surcharges", ["batch_id"], unique=False)

    op.create_table(
        "lcl_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("origin_port_id", sa.Integer(), nullable=False, comment="起运港"),
        sa.Column("destination_port_id", sa.Integer(), nullable=False, comment="目的港"),
        sa.Column("freight_per_cbm", sa.Numeric(10, 2), nullable=True, comment="每 CBM 运费"),
        sa.Column("freight_per_ton", sa.Numeric(10, 2), nullable=True, comment="每 TON 运费"),
        sa.Column("currency", sa.String(length=5), nullable=False, comment="币种"),
        sa.Column("lss", sa.String(length=50), nullable=True, comment="LSS"),
        sa.Column("ebs", sa.String(length=50), nullable=True, comment="EBS"),
        sa.Column("cic", sa.String(length=50), nullable=True, comment="CIC"),
        sa.Column("ams_aci_ens", sa.String(length=50), nullable=True, comment="AMS/ACI/ENS"),
        sa.Column("sailing_day", sa.String(length=50), nullable=True, comment="开船日"),
        sa.Column("via", sa.String(length=100), nullable=True, comment="中转港"),
        sa.Column("transit_time_text", sa.String(length=100), nullable=True, comment="航程文本"),
        sa.Column("remarks", sa.Text(), nullable=True, comment="备注"),
        sa.Column("valid_from", sa.Date(), nullable=True, comment="生效日期"),
        sa.Column("valid_to", sa.Date(), nullable=True, comment="失效日期"),
        sa.Column("batch_id", sa.Uuid(), nullable=False, comment="所属导入批次"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.batch_id"]),
        sa.ForeignKeyConstraint(["destination_port_id"], ["ports.id"]),
        sa.ForeignKeyConstraint(["origin_port_id"], ["ports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lcl_rate_origin_dest_valid",
        "lcl_rates",
        ["origin_port_id", "destination_port_id", "valid_from"],
        unique=False,
    )
    op.create_index("ix_lcl_rate_batch", "lcl_rates", ["batch_id"], unique=False)

    with op.batch_alter_table("freight_rates") as batch_op:
        batch_op.add_column(sa.Column("lss_cic", sa.Numeric(10, 2), nullable=True, comment="LSS+CIC"))
        batch_op.add_column(sa.Column("baf", sa.Numeric(10, 2), nullable=True, comment="BAF"))
        batch_op.add_column(sa.Column("ebs", sa.Numeric(10, 2), nullable=True, comment="EBS"))
        batch_op.add_column(sa.Column("yas_caf", sa.Numeric(10, 2), nullable=True, comment="YAS/CAF"))
        batch_op.add_column(
            sa.Column("booking_charge", sa.Numeric(10, 2), nullable=True, comment="订舱费")
        )
        batch_op.add_column(sa.Column("thc", sa.Numeric(10, 2), nullable=True, comment="THC"))
        batch_op.add_column(sa.Column("doc", sa.Numeric(10, 2), nullable=True, comment="DOC"))
        batch_op.add_column(sa.Column("isps", sa.Numeric(10, 2), nullable=True, comment="ISPS"))
        batch_op.add_column(
            sa.Column("equipment_mgmt", sa.Numeric(10, 2), nullable=True, comment="用箱管理费")
        )
        batch_op.add_column(sa.Column("rate_level", sa.String(length=10), nullable=True, comment="费率等级"))
        batch_op.add_column(sa.Column("sailing_day", sa.String(length=50), nullable=True, comment="开船日"))
        batch_op.add_column(sa.Column("via", sa.String(length=100), nullable=True, comment="中转港"))
        batch_op.add_column(
            sa.Column("transit_time_text", sa.String(length=100), nullable=True, comment="航程文本")
        )
        batch_op.add_column(sa.Column("rmks", sa.Text(), nullable=True, comment="原表备注"))
        batch_op.add_column(sa.Column("batch_id", sa.Uuid(), nullable=True, comment="Step1 导入批次 UUID"))
        batch_op.create_index("ix_rate_batch_uuid", ["batch_id"], unique=False)
        batch_op.create_index("ix_rate_level", ["rate_level"], unique=False)
        batch_op.create_foreign_key(
            "fk_freight_rates_batch_id_import_batches",
            "import_batches",
            ["batch_id"],
            ["batch_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("freight_rates") as batch_op:
        batch_op.drop_constraint("fk_freight_rates_batch_id_import_batches", type_="foreignkey")
        batch_op.drop_index("ix_rate_level")
        batch_op.drop_index("ix_rate_batch_uuid")
        batch_op.drop_column("batch_id")
        batch_op.drop_column("rmks")
        batch_op.drop_column("transit_time_text")
        batch_op.drop_column("via")
        batch_op.drop_column("sailing_day")
        batch_op.drop_column("rate_level")
        batch_op.drop_column("equipment_mgmt")
        batch_op.drop_column("isps")
        batch_op.drop_column("doc")
        batch_op.drop_column("thc")
        batch_op.drop_column("booking_charge")
        batch_op.drop_column("yas_caf")
        batch_op.drop_column("ebs")
        batch_op.drop_column("baf")
        batch_op.drop_column("lss_cic")

    op.drop_index("ix_lcl_rate_batch", table_name="lcl_rates")
    op.drop_index("ix_lcl_rate_origin_dest_valid", table_name="lcl_rates")
    op.drop_table("lcl_rates")

    op.drop_index("ix_air_surcharge_batch", table_name="air_surcharges")
    op.drop_index("ix_air_surcharge_effective", table_name="air_surcharges")
    op.drop_table("air_surcharges")

    op.drop_index("ix_air_freight_rate_batch", table_name="air_freight_rates")
    op.drop_index("ix_air_freight_rate_origin_dest_week", table_name="air_freight_rates")
    op.drop_table("air_freight_rates")

    op.drop_index("ix_import_batch_status", table_name="import_batches")
    op.drop_index("ix_import_batch_file_effective", table_name="import_batches")
    op.drop_table("import_batches")
