"""ai_client 单元测试骨架（T-AI-07）。

集成测试用 @pytest.mark.integration 标记，默认 pytest 会跑（不 skip）；
若 vLLM 不在线，集成测试会失败，手动 `pytest -m "not integration"` 跳过。
"""
import io
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from app.core.config import settings
from app.services import ai_client


# ---------- 单元：纯函数 helpers ----------

def test_resolve_provider_default_vllm():
    assert ai_client._resolve_provider(None) == settings.ai_provider


def test_resolve_provider_explicit_anthropic():
    assert ai_client._resolve_provider("anthropic") == "anthropic"
    assert ai_client._resolve_provider("VLLM") == "vllm"  # 大小写不敏感


def test_resolve_provider_invalid_raises():
    with pytest.raises(ai_client.AIClientError):
        ai_client._resolve_provider("foo")


def test_resolve_model_vllm_default():
    assert ai_client._resolve_model("vllm", None) == settings.vllm_model


def test_resolve_model_override():
    assert ai_client._resolve_model("vllm", "custom-m") == "custom-m"


def test_resolve_max_tokens_vllm_default():
    assert ai_client._resolve_max_tokens(None, "default", "vllm") == settings.ai_max_tokens_default


def test_resolve_max_tokens_vllm_extract_json():
    assert ai_client._resolve_max_tokens(None, "extract_json", "vllm") == settings.ai_max_tokens_extract_json


def test_resolve_max_tokens_vllm_cap():
    # override 超 cap 被压到 cap
    assert ai_client._resolve_max_tokens(8192, "default", "vllm") == settings.ai_max_tokens_cap


def test_resolve_max_tokens_anthropic_bypasses_cap():
    # R3 缓解：Anthropic 不走 vllm 的 1536 cap
    assert ai_client._resolve_max_tokens(8192, "default", "anthropic") == 8192
    assert ai_client._resolve_max_tokens(None, "default", "anthropic") == 4096


def test_append_no_think_plain():
    msgs = [{"role": "user", "content": "hello"}]
    out = ai_client._append_no_think([dict(m) for m in msgs])
    assert out[0]["content"].endswith("/no_think")


def test_append_no_think_idempotent():
    msgs = [{"role": "user", "content": "hello /no_think"}]
    out = ai_client._append_no_think([dict(m) for m in msgs])
    assert out[0]["content"].count("/no_think") == 1


def test_append_no_think_multimodal():
    import copy
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ],
    }]
    out = ai_client._append_no_think(copy.deepcopy(msgs))
    # 追加到最后一条 text 段
    texts = [p["text"] for p in out[0]["content"] if p["type"] == "text"]
    assert texts[-1].endswith("/no_think")


def test_append_no_think_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_auto_no_think", False)
    msgs = [{"role": "user", "content": "hello"}]
    out = ai_client._append_no_think([dict(m) for m in msgs])
    assert out[0]["content"] == "hello"


def test_compress_image_shrinks_large_jpeg(tmp_path):
    from PIL import Image
    path = tmp_path / "big.jpg"
    Image.new("RGB", (2000, 3000), color="red").save(path, "JPEG", quality=95)

    data, mime = ai_client._compress_image(str(path))
    assert mime == "image/jpeg"

    from PIL import Image as _I
    out = _I.open(io.BytesIO(data))
    assert max(out.size) <= settings.ai_image_max_edge_px


def test_compress_image_fallback_on_unreadable(tmp_path):
    # 假的 HEIC 文件（Pillow 打不开）→ fallback 原字节
    path = tmp_path / "fake.heic"
    path.write_bytes(b"not a real image")
    data, mime = ai_client._compress_image(str(path))
    assert data == b"not a real image"
    assert mime == "image/heic"


# ---------- 单元：vllm / anthropic 分支守卫 ----------

def test_vllm_raw_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "vllm_api_key", "")
    with pytest.raises(ai_client.ProviderUnavailableError):
        ai_client._vllm_raw([{"role": "user", "content": "x"}],
                            model="m", temperature=0, max_tokens=16, timeout=5)


def test_chat_anthropic_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(ai_client.ProviderUnavailableError):
        ai_client.chat("sys", "hello", provider="anthropic", max_tokens=16)


# ---------- 单元：Anthropic timeout mock ----------

def test_anthropic_timeout_propagates(monkeypatch):
    """stub 抛 APITimeoutError，ai_client 应转成 ProviderUnavailableError 且不卡死。"""
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")

    import anthropic

    class StubClient:
        def __init__(self, *a, **kw):
            self.messages = self
            # 验证传了 timeout + max_retries=1
            assert kw.get("timeout") is not None
            assert kw.get("max_retries") == 1

        def create(self, **kw):
            # 模拟 httpx 超时 → SDK 的 APITimeoutError 需要一个 httpx 请求对象
            import httpx as _httpx
            req = _httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.APITimeoutError(request=req)

    monkeypatch.setattr(anthropic, "Anthropic", StubClient)
    with pytest.raises(ai_client.ProviderUnavailableError):
        ai_client.chat("sys", "hi", provider="anthropic", max_tokens=16, timeout=1)


def test_get_current_provider_returns_settings():
    assert ai_client.get_current_provider() == settings.ai_provider


# ---------- 集成：vLLM 真实服务器（需在线） ----------


@pytest.mark.integration
def test_vllm_health_check_ok():
    if not settings.vllm_api_key:
        pytest.skip("VLLM_API_KEY 未配置")
    hc = ai_client.health_check()
    assert hc["provider"] == "vllm"
    assert hc["ok"] is True
    assert hc["latency_ms"] < 5000


@pytest.mark.integration
def test_vllm_chat_returns_ok():
    if not settings.vllm_api_key:
        pytest.skip("VLLM_API_KEY 未配置")
    out = ai_client.chat("你是测试助手", "只回 OK", max_tokens=16)
    assert "OK" in out.upper()


@pytest.mark.integration
def test_vllm_chat_with_image(tmp_path):
    if not settings.vllm_api_key:
        pytest.skip("VLLM_API_KEY 未配置")
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (320, 200), color="white")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 190], outline="black", width=3)
    d.text((100, 90), "HELLO", fill="black")
    path = tmp_path / "hello.png"
    img.save(path, "PNG")

    out = ai_client.chat_with_image(
        "你是图片识别助手，只用中文简短回答",
        "图里写的什么英文单词？只回一个单词",
        str(path),
        max_tokens=32,
    )
    assert out.strip()  # 非空
