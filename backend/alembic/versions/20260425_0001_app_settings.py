"""add app_settings single-row table

Revision ID: 20260425_0001
Revises: 20260421_0001
Create Date: 2026-04-25 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260425_0001"
down_revision: Union[str, None] = "20260421_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        # AI 通用（9 项，全部 Nullable 以支持 env fallback）
        sa.Column("ai_provider", sa.String(length=20), nullable=True),
        sa.Column("ai_timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("ai_auto_no_think", sa.Boolean(), nullable=True),
        sa.Column("ai_max_tokens_default", sa.Integer(), nullable=True),
        sa.Column("ai_max_tokens_extract_json", sa.Integer(), nullable=True),
        sa.Column("ai_max_tokens_cap", sa.Integer(), nullable=True),
        sa.Column("ai_image_compress", sa.Boolean(), nullable=True),
        sa.Column("ai_image_max_edge_px", sa.Integer(), nullable=True),
        sa.Column("ai_image_jpeg_quality", sa.Integer(), nullable=True),
        # vLLM（5 项）
        sa.Column("vllm_base_url", sa.String(length=500), nullable=True),
        sa.Column("vllm_api_key_encoded", sa.String(length=500), nullable=True),
        sa.Column("vllm_model", sa.String(length=100), nullable=True),
        sa.Column("vllm_enable_thinking", sa.Boolean(), nullable=True),
        sa.Column("vllm_enable_chat_template_kwargs", sa.Boolean(), nullable=True),
        # Anthropic（2 项）
        sa.Column("anthropic_api_key_encoded", sa.String(length=500), nullable=True),
        sa.Column("anthropic_model", sa.String(length=100), nullable=True),
        # 元数据
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
