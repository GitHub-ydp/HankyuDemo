"""AI 配置读写层 — DB 优先 > env fallback + 30s TTL 缓存（决策 β2 + ε1）。

ai_client 通过 get_ai_config() 读当前生效配置；UI 通过 admin_settings API 写。

敏感字段 base64 混淆落盘（决策 A §4.3，列名 *_api_key_encoded 明示非 AES）。
升级到 AES-GCM 只需替换 _encode_secret / _decode_secret 两函数。

缓存语义：module-level 单例，30s TTL；update_ai_config 成功 commit 后主动 invalidate。
"""
import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.app_settings import AppSettings
from app.schemas.app_settings import (
    AIConfig,
    AIConfigPatch,
    AIConfigResponse,
    FieldWithSource,
    MaskedSecret,
)

logger = logging.getLogger(__name__)

# 16 业务字段的有序元组（对齐 AIConfig / AppSettings 列）
AI_CONFIG_FIELDS: tuple[str, ...] = (
    "ai_provider",
    "ai_timeout_seconds",
    "ai_auto_no_think",
    "ai_max_tokens_default",
    "ai_max_tokens_extract_json",
    "ai_max_tokens_cap",
    "ai_image_compress",
    "ai_image_max_edge_px",
    "ai_image_jpeg_quality",
    "vllm_base_url",
    "vllm_api_key",
    "vllm_model",
    "vllm_enable_thinking",
    "vllm_enable_chat_template_kwargs",
    "anthropic_api_key",
    "anthropic_model",
)

_SENSITIVE_FIELDS: frozenset[str] = frozenset({"vllm_api_key", "anthropic_api_key"})

# DB 列名 → AIConfig 字段名 的映射（敏感字段有 _encoded 后缀）
_DB_COL_OF: dict[str, str] = {
    **{f: f for f in AI_CONFIG_FIELDS if f not in _SENSITIVE_FIELDS},
    "vllm_api_key": "vllm_api_key_encoded",
    "anthropic_api_key": "anthropic_api_key_encoded",
}

_CACHE_TTL_SECONDS = 30.0


@dataclass
class _CacheEntry:
    cfg: AIConfig
    loaded_at: float


_cache: _CacheEntry | None = None


# ===== 敏感字段编解码 =====

def _encode_secret(plaintext: str) -> str:
    """base64 混淆。空串仍返回空串。"""
    if not plaintext:
        return ""
    return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def _decode_secret(encoded: str | None) -> str:
    """解码失败返回空串，log warning。空或 None 返回空串。"""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.warning("app_settings 敏感字段 base64 解码失败，回落空串: %s", e)
        return ""


def mask_secret(plaintext: str) -> MaskedSecret:
    """脱敏：后 4 位前面拼 ••••，短串原样返。空串 is_set=False。"""
    if not plaintext:
        return MaskedSecret(masked="", is_set=False)
    tail = plaintext[-4:] if len(plaintext) > 4 else plaintext
    return MaskedSecret(masked=f"••••{tail}", is_set=True)


# ===== env 默认值 =====

def _env_defaults() -> dict[str, Any]:
    """从 pydantic settings 读 16 字段，作为 fallback 基线。"""
    return {f: getattr(settings, f) for f in AI_CONFIG_FIELDS}


# ===== 合并 DB + env =====

def _row_to_values(row: AppSettings | None) -> dict[str, Any]:
    """把 AppSettings 行转成业务字段名 → 值 的 dict（敏感字段已解码）。
    NULL 字段返回 None；敏感字段空串 / NULL 返回空串。
    """
    if row is None:
        return {f: None for f in AI_CONFIG_FIELDS}
    out: dict[str, Any] = {}
    for f in AI_CONFIG_FIELDS:
        col = _DB_COL_OF[f]
        val = getattr(row, col, None)
        if f in _SENSITIVE_FIELDS:
            # 空串和 NULL 都视为"未在 DB 里设置"；有值则解码
            out[f] = _decode_secret(val) if val else None
        else:
            out[f] = val
    return out


def _merge_db_over_env(row: AppSettings | None, env: dict[str, Any]) -> tuple[AIConfig, dict[str, str]]:
    """DB 非空字段覆盖 env。返回 (AIConfig 明文快照, 每字段 source: db|env)。

    敏感字段判断"DB 有值"用非空串；其他字段用 `is not None`。
    """
    db_values = _row_to_values(row)
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for f in AI_CONFIG_FIELDS:
        db_val = db_values[f]
        if f in _SENSITIVE_FIELDS:
            has_db = bool(db_val)
        else:
            has_db = db_val is not None
        if has_db:
            merged[f] = db_val
            sources[f] = "db"
        else:
            merged[f] = env[f]
            sources[f] = "env"
    return AIConfig(**merged), sources


# ===== 对外：读配置 =====

def get_ai_config(db: Session | None = None) -> AIConfig:
    """读当前生效配置（DB 优先 > env fallback，30s TTL 缓存）。

    db=None 时内部自管 SessionLocal；ai_client 调用路径不需要传 db。
    DB 读异常时回落 env，不 raise（风险 R5 缓解）。
    """
    global _cache
    now = time.time()
    if _cache is not None and now - _cache.loaded_at < _CACHE_TTL_SECONDS:
        return _cache.cfg

    cfg = _load_from_db(db)
    _cache = _CacheEntry(cfg=cfg, loaded_at=now)
    return cfg


def _load_from_db(db: Session | None) -> AIConfig:
    """不走缓存的裸读。异常回落 env。"""
    env = _env_defaults()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.query(AppSettings).filter_by(id=1).first()
    except Exception as e:
        logger.warning("app_settings 读失败，回落 env: %s", e)
        row = None
    finally:
        if owns_session:
            session.close()

    cfg, _sources = _merge_db_over_env(row, env)
    return cfg


def invalidate_cache() -> None:
    """清零缓存时间戳，强制下次 get_ai_config() 重读 DB。"""
    global _cache
    _cache = None


# ===== 对外：写配置 =====

def update_ai_config(
    patch: AIConfigPatch,
    *,
    db: Session,
    updated_by: str | None = None,
) -> AIConfigResponse:
    """部分更新。只改 patch.model_fields_set 里的字段。

    - 敏感字段 None → DB 列写空串（清空）
    - 敏感字段非空 → DB 列写 base64 编码
    - 普通字段 None → DB 列写 NULL（回落 env）
    - 普通字段非 None → DB 列写该值
    - commit 成功后才 invalidate 缓存（R9 缓解）
    """
    row = db.query(AppSettings).filter_by(id=1).first()
    if row is None:
        row = AppSettings(id=1)
        db.add(row)

    # 只对 fields_set 里的字段做写入
    changed = patch.model_fields_set
    for field in changed:
        new_val = getattr(patch, field)
        col = _DB_COL_OF[field]
        if field in _SENSITIVE_FIELDS:
            if new_val is None or new_val == "":
                setattr(row, col, "")
            else:
                setattr(row, col, _encode_secret(new_val))
        else:
            setattr(row, col, new_val)

    if updated_by is not None:
        row.updated_by = updated_by

    db.commit()
    invalidate_cache()

    # 审计日志：仅列出字段名，敏感字段不打 value
    sensitive_changed = [f for f in changed if f in _SENSITIVE_FIELDS]
    non_sensitive_changed = [f for f in changed if f not in _SENSITIVE_FIELDS]
    logger.info(
        "app_settings updated: non_sensitive=%s sensitive=%s by=%s",
        non_sensitive_changed, sensitive_changed, updated_by or "-",
    )

    return _build_response(db)


def reset_to_defaults(*, db: Session, updated_by: str | None = None) -> AIConfigResponse:
    """删掉 DB 行，让所有字段回落 env 默认值。"""
    db.query(AppSettings).filter_by(id=1).delete()
    db.commit()
    invalidate_cache()
    logger.info("app_settings reset to env defaults by=%s", updated_by or "-")
    return _build_response(db)


# ===== 对外：build 响应 =====

def _build_response(db: Session) -> AIConfigResponse:
    """读最新 DB 行，拼 AIConfigResponse（敏感字段脱敏 + 每字段 source）。"""
    env = _env_defaults()
    row = db.query(AppSettings).filter_by(id=1).first()
    cfg, sources = _merge_db_over_env(row, env)

    out: dict[str, Any] = {}
    for f in AI_CONFIG_FIELDS:
        value = getattr(cfg, f)
        if f in _SENSITIVE_FIELDS:
            out[f] = FieldWithSource(value=mask_secret(value), source=sources[f])
        else:
            out[f] = FieldWithSource(value=value, source=sources[f])
    return AIConfigResponse(**out)


def get_ai_config_response(db: Session) -> AIConfigResponse:
    """给 GET /admin/settings/ai 用。"""
    return _build_response(db)
