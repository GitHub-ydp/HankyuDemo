"""统一 AI 客户端 — 优先 Claude API，回退通义千问 Qwen（阿里云百炼，OpenAI 兼容）
支持文本对话和图片视觉识别两种模式
"""
import base64
import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_provider() -> str:
    """检测可用的 AI 提供商"""
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.qwen_api_key:
        return "qwen"
    raise RuntimeError("未配置任何 AI API Key（ANTHROPIC_API_KEY 或 QWEN_API_KEY）")


def chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """纯文本对话 — 返回 AI 原始文本响应"""
    provider = _get_provider()

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    else:  # qwen (DashScope OpenAI-compatible)
        import httpx
        resp = httpx.post(
            f"{settings.qwen_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.qwen_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.qwen_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "enable_thinking": settings.qwen_enable_thinking,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def chat_with_image(
    system_prompt: str,
    user_text: str,
    image_path: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """图片+文本对话（Vision）— 返回 AI 原始文本响应"""
    # 读取图片并转 base64
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # 根据扩展名判断 MIME
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    media_type = mime_map.get(ext, "image/png")

    provider = _get_provider()

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    }},
                    {"type": "text", "text": user_text},
                ],
            }],
        )
        return resp.content[0].text

    else:  # qwen-vl (DashScope OpenAI-compatible with vision)
        import httpx
        resp = httpx.post(
            f"{settings.qwen_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.qwen_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.qwen_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "enable_thinking": settings.qwen_enable_thinking,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{media_type};base64,{image_data}",
                        }},
                        {"type": "text", "text": user_text},
                    ]},
                ],
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def extract_json(text: str) -> Any:
    """从 AI 响应中提取 JSON（处理 markdown 代码块）"""
    # 去掉 ```json ... ``` 包裹
    text = text.strip()
    if text.startswith("```"):
        # 去掉第一行和最后一行
        lines = text.split("\n")
        lines = lines[1:]  # 去掉 ```json
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return json.loads(text)
