"""统一 AI 客户端 — 默认走本地 vLLM (OpenAI-compatible)，保留 Anthropic 分支供后续设置页切换。

设计要点：
- Provider 由 get_ai_config().ai_provider 决定，单次调用可用 provider= 参数临时 override
- vLLM / Anthropic 两底层通过私有 helper 实现，public chat/chat_with_image 只拼 messages
- 超时统一走 get_ai_config().ai_timeout_seconds，Anthropic 分支显式传 timeout 修历史卡死 bug
- max_tokens 按 purpose 解析；vLLM 死守 2048-512 buffer，Anthropic 保留大窗口
- 图片自动 Pillow 压到 1280px / JPEG 85；HEIC 等不支持格式回退原字节
- vLLM user text 末尾自动追加 /no_think（双保险关思考）
"""
import base64
import io
import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.config import settings  # 保留给 DEFAULT_CORS_ORIGINS 等非 AI 配置（当前无用，但与原签名约定一致）
from app.services.config_service import get_ai_config

logger = logging.getLogger(__name__)


# ========== Exceptions ==========

class AIClientError(RuntimeError):
    """AI 客户端通用错误基类"""


class PromptTooLongError(AIClientError):
    """prompt 长度超过 provider 限制，无法留给输出足够 token"""


class ProviderUnavailableError(AIClientError):
    """目标 provider 未配置 / 连通失败"""


# ========== 私有 helpers ==========

def _resolve_provider(override: str | None) -> str:
    """解析最终 provider 名。override > get_ai_config().ai_provider。"""
    cfg = get_ai_config()
    name = (override or cfg.ai_provider or "vllm").strip().lower()
    if name not in ("vllm", "anthropic"):
        raise AIClientError(f"未知 provider: {name}（仅支持 vllm / anthropic）")
    return name


def _resolve_model(provider: str, override: str | None) -> str:
    """按 provider 解析 model。override 优先。"""
    if override:
        return override
    cfg = get_ai_config()
    if provider == "vllm":
        return cfg.vllm_model
    if provider == "anthropic":
        return cfg.anthropic_model
    raise AIClientError(f"未知 provider: {provider}")


def _resolve_max_tokens(override: int | None, purpose: str, provider: str) -> int:
    """按用途和 provider 选默认 max_tokens。

    - override 非空：以 override 为准，但 vllm 仍受 cap 约束；anthropic 放行
    - vllm：min(override or default_by_purpose, ai_max_tokens_cap)
    - anthropic：override or 4096（不走 vllm 的 1536 cap，R3 风险缓解）
    """
    cfg = get_ai_config()
    default_by_purpose = {
        "default": cfg.ai_max_tokens_default,
        "extract_json": cfg.ai_max_tokens_extract_json,
    }.get(purpose, cfg.ai_max_tokens_default)

    if provider == "anthropic":
        return override if override is not None else 4096

    # vllm 分支（包括回滚到百炼）
    val = override if override is not None else default_by_purpose
    if val > cfg.ai_max_tokens_cap:
        logger.warning(
            "max_tokens=%d 超过 ai_max_tokens_cap=%d，已降到 cap",
            val, cfg.ai_max_tokens_cap,
        )
        val = cfg.ai_max_tokens_cap
    return val


def _append_no_think(messages: list[dict]) -> list[dict]:
    """若 ai_auto_no_think 开启，在最后一条 user 的纯文本内容末尾追加 /no_think。

    幂等：已含 /no_think 就不再追加。
    对 content 是 list（多模态）的情况，追加到最后一条 text 段。
    """
    if not get_ai_config().ai_auto_no_think or not messages:
        return messages

    # 从后往前找第一条 role=user
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            if "/no_think" not in content:
                messages[i] = {**msg, "content": content.rstrip() + " /no_think"}
            return messages
        if isinstance(content, list):
            # 多模态：找最后一条 text
            new_content = list(content)
            for j in range(len(new_content) - 1, -1, -1):
                part = new_content[j]
                if part.get("type") == "text":
                    text = part.get("text", "")
                    if "/no_think" not in text:
                        new_content[j] = {**part, "text": text.rstrip() + " /no_think"}
                    break
            messages[i] = {**msg, "content": new_content}
            return messages
        break
    return messages


def _compress_image(path: str) -> tuple[bytes, str]:
    """Pillow 压图到最长边 ai_image_max_edge_px / JPEG quality 85。

    失败回退原字节 + 按扩展名推 mime。
    返回 (bytes, mime)。
    """
    cfg = get_ai_config()
    if not cfg.ai_image_compress:
        return _read_raw_image(path)

    try:
        from PIL import Image
    except Exception as e:
        logger.warning("Pillow 未安装，回退原字节: %s", e)
        return _read_raw_image(path)

    try:
        with Image.open(path) as im:
            im.load()
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            max_edge = cfg.ai_image_max_edge_px
            w, h = im.size
            if max(w, h) > max_edge:
                ratio = max_edge / float(max(w, h))
                im = im.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=cfg.ai_image_jpeg_quality, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception as e:
        logger.warning("图片压缩失败，回退原字节 path=%s err=%s", path, e)
        return _read_raw_image(path)


def _read_raw_image(path: str) -> tuple[bytes, str]:
    """读原字节 + 按扩展名猜 mime。"""
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        "heic": "image/heic", "heif": "image/heif",
    }
    return data, mime_map.get(ext, "image/png")


def _vllm_raw(
    messages: list[dict],
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    """打 vLLM / OpenAI-compatible 端点。抛 ProviderUnavailableError 或 AIClientError。"""
    cfg = get_ai_config()
    if not cfg.vllm_api_key:
        raise ProviderUnavailableError("VLLM_API_KEY 未配置")

    body: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if cfg.vllm_enable_chat_template_kwargs:
        body["chat_template_kwargs"] = {"enable_thinking": cfg.vllm_enable_thinking}

    url = f"{cfg.vllm_base_url.rstrip('/')}/chat/completions"
    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {cfg.vllm_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
    except httpx.TimeoutException as e:
        raise ProviderUnavailableError(f"vllm timeout: {e}") from e
    except httpx.ConnectError as e:
        raise ProviderUnavailableError(f"vllm connect error: {e}") from e
    except httpx.HTTPError as e:
        raise AIClientError(f"vllm http error: {e}") from e

    if resp.status_code >= 400:
        raise AIClientError(f"vllm {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, ValueError, IndexError) as e:
        raise AIClientError(f"vllm 响应结构异常: {e}; body={resp.text[:500]}") from e


def _anthropic_raw(
    messages: list[dict],
    system: str,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    """打 Anthropic API。抛 ProviderUnavailableError 或 AIClientError。

    显式传 timeout / max_retries=1 修历史卡死 bug。
    """
    cfg = get_ai_config()
    if not cfg.anthropic_api_key:
        raise ProviderUnavailableError("ANTHROPIC_API_KEY 未配置")

    try:
        import anthropic
    except ImportError as e:
        raise ProviderUnavailableError(f"anthropic SDK 未安装: {e}") from e

    try:
        client = anthropic.Anthropic(
            api_key=cfg.anthropic_api_key,
            timeout=timeout,
            max_retries=1,
        )
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return resp.content[0].text
    except anthropic.APITimeoutError as e:
        raise ProviderUnavailableError(f"anthropic timeout: {e}") from e
    except anthropic.APIConnectionError as e:
        raise ProviderUnavailableError(f"anthropic connect error: {e}") from e
    except anthropic.APIStatusError as e:
        raise AIClientError(f"anthropic {e.status_code}: {e}") from e
    except Exception as e:
        raise AIClientError(f"anthropic 调用失败: {e}") from e


def _anthropic_image_content(user_text: str, image_bytes: bytes, mime: str) -> list[dict]:
    """构造 Anthropic 风格的多模态 content（base64 source）。"""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return [
        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
        {"type": "text", "text": user_text},
    ]


def _vllm_image_content(user_text: str, image_bytes: bytes, mime: str) -> list[dict]:
    """构造 OpenAI-compatible 风格的多模态 content（data URL）。"""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        {"type": "text", "text": user_text},
    ]


# ========== Public API ==========

def chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> str:
    """纯文本对话 — 返回 AI 原始文本响应。

    max_tokens=None 时按 ai_max_tokens_default（get_ai_config）。
    provider=None 时按 ai_provider（get_ai_config，默认 vllm）。
    """
    prov = _resolve_provider(provider)
    mdl = _resolve_model(prov, model)
    mt = _resolve_max_tokens(max_tokens, "default", prov)
    to = timeout if timeout is not None else get_ai_config().ai_timeout_seconds

    if prov == "anthropic":
        messages = [{"role": "user", "content": user_message}]
        return _anthropic_raw(messages, system_prompt, model=mdl,
                              temperature=temperature, max_tokens=mt, timeout=to)

    # vllm：system 合并进 messages 头
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    messages = _append_no_think(messages)
    return _vllm_raw(messages, model=mdl, temperature=temperature,
                     max_tokens=mt, timeout=to)


def chat_with_image(
    system_prompt: str,
    user_text: str,
    image_path: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> str:
    """图片+文本对话（Vision）— 返回 AI 原始文本响应。"""
    prov = _resolve_provider(provider)
    mdl = _resolve_model(prov, model)
    mt = _resolve_max_tokens(max_tokens, "extract_json", prov)
    to = timeout if timeout is not None else get_ai_config().ai_timeout_seconds

    image_bytes, mime = _compress_image(image_path)

    if prov == "anthropic":
        messages = [{
            "role": "user",
            "content": _anthropic_image_content(user_text, image_bytes, mime),
        }]
        return _anthropic_raw(messages, system_prompt, model=mdl,
                              temperature=temperature, max_tokens=mt, timeout=to)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _vllm_image_content(user_text, image_bytes, mime)},
    ]
    messages = _append_no_think(messages)
    return _vllm_raw(messages, model=mdl, temperature=temperature,
                     max_tokens=mt, timeout=to)


def extract_json(text: str) -> Any:
    """从 AI 响应中提取 JSON（处理 markdown 代码块）"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def health_check(provider: str | None = None, timeout: float = 5.0) -> dict:
    """轻量连通性检查。返回 {'provider': ..., 'ok': bool, 'latency_ms': int, 'detail': str}"""
    prov = _resolve_provider(provider)
    cfg = get_ai_config()
    t0 = time.time()

    if prov == "vllm":
        url = f"{cfg.vllm_base_url.rstrip('/').rsplit('/v1', 1)[0]}/health"
        try:
            resp = httpx.get(url, timeout=timeout)
            ok = resp.status_code == 200
            return {
                "provider": "vllm",
                "ok": ok,
                "latency_ms": int((time.time() - t0) * 1000),
                "detail": f"{resp.status_code} {resp.text[:80]}",
            }
        except Exception as e:
            return {
                "provider": "vllm",
                "ok": False,
                "latency_ms": int((time.time() - t0) * 1000),
                "detail": f"error: {e}",
            }

    # anthropic：没有公开 /health，用 models 列表也不划算。只验证 key 配置
    return {
        "provider": "anthropic",
        "ok": bool(cfg.anthropic_api_key),
        "latency_ms": int((time.time() - t0) * 1000),
        "detail": "key configured" if cfg.anthropic_api_key else "ANTHROPIC_API_KEY 未配置",
    }


def get_current_provider() -> str:
    """给前端 /admin/ai-status 用；返回 get_ai_config().ai_provider。"""
    return _resolve_provider(None)
