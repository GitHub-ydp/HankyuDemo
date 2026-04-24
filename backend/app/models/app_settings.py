"""app_settings 单行表 — 存 AI 配置覆盖项（决策 α1 + β2 + ε1）。

单行约束由代码侧保证（id=1）。所有业务列 Nullable：NULL 表示未在 UI 改过，
config_service 会 fallback 到 env 默认值。

敏感字段（*_api_key）以 base64 编码存到 *_api_key_encoded 列（决策 A §4.3），
列名后缀 _encoded 强提醒不是明文；生产环境可平替 AES-GCM。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # AI 通用（9 项）
    ai_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_auto_no_think: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_max_tokens_default: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_max_tokens_extract_json: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_max_tokens_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_image_compress: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_image_max_edge_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_image_jpeg_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # vLLM（5 项）
    vllm_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vllm_api_key_encoded: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vllm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vllm_enable_thinking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vllm_enable_chat_template_kwargs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Anthropic（2 项）
    anthropic_api_key_encoded: Mapped[str | None] = mapped_column(String(500), nullable=True)
    anthropic_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 元数据
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
