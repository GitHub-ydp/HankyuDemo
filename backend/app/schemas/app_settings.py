"""AI 设置页 pydantic schema（见架构任务单 §3.1）。

三种形态：
- AIConfig：service 层内部明文快照，ai_client 消费
- AIConfigResponse：GET/PATCH 返回体，敏感字段脱敏 + 每字段带 source
- AIConfigPatch：PATCH 请求体，全部 Optional；敏感字段语义见决策 D
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ===== 内部明文快照 =====

class AIConfig(BaseModel):
    """service 层返回的完整 AI 配置快照（明文，仅后端内部使用）。"""
    model_config = ConfigDict(protected_namespaces=())

    # AI 通用
    ai_provider: Literal["vllm", "anthropic"]
    ai_timeout_seconds: int
    ai_auto_no_think: bool
    ai_max_tokens_default: int
    ai_max_tokens_extract_json: int
    ai_max_tokens_cap: int
    ai_image_compress: bool
    ai_image_max_edge_px: int
    ai_image_jpeg_quality: int
    # vLLM
    vllm_base_url: str
    vllm_api_key: str
    vllm_model: str
    vllm_enable_thinking: bool
    vllm_enable_chat_template_kwargs: bool
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str


# ===== 响应脱敏结构 =====

class MaskedSecret(BaseModel):
    """API Key 脱敏形态：masked='••••VwH'（后 4 位）或 ''；is_set=True 表示有值。"""
    masked: str
    is_set: bool


class FieldWithSource(BaseModel):
    """每字段带 source 标签，告诉 UI 当前值来自 DB 还是 env fallback。"""
    value: Any
    source: Literal["db", "env"]


class AIConfigResponse(BaseModel):
    """GET/PATCH /admin/settings/ai 的返回体。"""
    model_config = ConfigDict(protected_namespaces=())

    ai_provider: FieldWithSource
    ai_timeout_seconds: FieldWithSource
    ai_auto_no_think: FieldWithSource
    ai_max_tokens_default: FieldWithSource
    ai_max_tokens_extract_json: FieldWithSource
    ai_max_tokens_cap: FieldWithSource
    ai_image_compress: FieldWithSource
    ai_image_max_edge_px: FieldWithSource
    ai_image_jpeg_quality: FieldWithSource
    vllm_base_url: FieldWithSource
    vllm_api_key: FieldWithSource  # value 是 MaskedSecret
    vllm_model: FieldWithSource
    vllm_enable_thinking: FieldWithSource
    vllm_enable_chat_template_kwargs: FieldWithSource
    anthropic_api_key: FieldWithSource  # value 是 MaskedSecret
    anthropic_model: FieldWithSource


# ===== PATCH 请求体 =====

class AIConfigPatch(BaseModel):
    """PATCH /admin/settings/ai 请求体，所有字段 Optional。

    决策 D 三态语义：
    - 字段不出现在 model_fields_set → 保持原值
    - 字段 = None → 清空（敏感字段写空字符串，普通字段写 NULL 回落 env）
    - 字段 = 非空值 → 覆盖
    """
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    ai_provider: Optional[Literal["vllm", "anthropic"]] = None
    ai_timeout_seconds: Optional[int] = Field(None, ge=10, le=600)
    ai_auto_no_think: Optional[bool] = None
    ai_max_tokens_default: Optional[int] = Field(None, ge=64, le=8192)
    ai_max_tokens_extract_json: Optional[int] = Field(None, ge=64, le=8192)
    ai_max_tokens_cap: Optional[int] = Field(None, ge=256, le=4096)
    ai_image_compress: Optional[bool] = None
    ai_image_max_edge_px: Optional[int] = Field(None, ge=640, le=2048)
    ai_image_jpeg_quality: Optional[int] = Field(None, ge=60, le=95)
    vllm_base_url: Optional[str] = Field(None, pattern=r"^https?://.+")
    vllm_api_key: Optional[str] = None
    vllm_model: Optional[str] = Field(None, min_length=1, max_length=100)
    vllm_enable_thinking: Optional[bool] = None
    vllm_enable_chat_template_kwargs: Optional[bool] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = Field(None, min_length=1, max_length=100)


# ===== 测试连通性 =====

class TestConnectionResponse(BaseModel):
    ok: bool
    provider: Literal["vllm", "anthropic"]
    latency_ms: int
    detail: str
