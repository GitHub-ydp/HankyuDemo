"""新增 users 表和 login_events 表（真实登录认证）

Revision ID: 20260609_0001
Revises: 20260601_0001
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260609_0001"
down_revision: Union[str, None] = "20260601_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, comment="登录邮箱(小写归一)"),
        sa.Column("name", sa.String(100), nullable=False, comment="显示名"),
        sa.Column("password_hash", sa.String(255), nullable=False, comment="bcrypt 哈希"),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True, comment="启用(软停用释放席位)"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True, comment="最后登录时间(UTC aware)"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, comment="冗余邮箱(留痕)"),
        sa.Column("ip", sa.String(64), nullable=True, comment="登录IP"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="登录时刻(UTC aware)"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_login_events_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_events_user_id", "login_events", ["user_id"], unique=False)


def downgrade() -> None:
    # 先删 login_events（FK 依赖 users），再删 users
    op.drop_index("ix_login_events_user_id", table_name="login_events")
    op.drop_table("login_events")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
