"""air_tier_rates 增加多维字段(货类/包装/泡比/航司)

Revision ID: 20260601_0001
Revises: 20260528_0001
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0001"
down_revision: Union[str, None] = "20260528_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("air_tier_rates", sa.Column("cargo_class", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("packing", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("density", sa.String(length=20), nullable=True))
    op.add_column("air_tier_rates", sa.Column("carrier", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("air_tier_rates", "carrier")
    op.drop_column("air_tier_rates", "density")
    op.drop_column("air_tier_rates", "packing")
    op.drop_column("air_tier_rates", "cargo_class")
