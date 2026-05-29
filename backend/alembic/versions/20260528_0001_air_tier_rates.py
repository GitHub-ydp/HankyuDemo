"""air_tier_rates 表（做表→入库的重量档运价）

Revision ID: 20260528_0001
Revises: 20260425_0001
Create Date: 2026-05-28

新增 air_tier_rates 表存重量档运价(tier_prices JSON)。import_batches.file_type 的
新枚举值 air_tier 无需迁移：该列为 native_enum=False 且未建 CHECK 约束(纯 VARCHAR)。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0001"
down_revision: Union[str, None] = "20260425_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "air_tier_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False, comment="起运港/机场代码"),
        sa.Column("destination", sa.String(length=100), nullable=False, comment="目的地"),
        sa.Column("service_desc", sa.String(length=100), nullable=True, comment="服务/航班/装载方式"),
        sa.Column("tier_prices", sa.JSON(), nullable=False, comment="重量档稀疏价 {KG: 单价}"),
        sa.Column("effective_from", sa.Date(), nullable=True, comment="报价生效开始"),
        sa.Column("effective_to", sa.Date(), nullable=True, comment="报价生效结束"),
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
        "ix_air_tier_rate_origin_dest",
        "air_tier_rates",
        ["origin", "destination"],
        unique=False,
    )
    op.create_index("ix_air_tier_rate_batch", "air_tier_rates", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_air_tier_rate_batch", table_name="air_tier_rates")
    op.drop_index("ix_air_tier_rate_origin_dest", table_name="air_tier_rates")
    op.drop_table("air_tier_rates")
