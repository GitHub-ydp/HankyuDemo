"""pytest conftest：在每个测试前后 invalidate config_service 缓存。

T-ST-05 后 ai_client 走 get_ai_config() 读配置，模块级 30s TTL 缓存在测试间会串台。
autouse fixture 确保每个测试用最新 DB/env 值。
"""
import pytest

from app.services import config_service


@pytest.fixture(autouse=True)
def _clear_ai_config_cache():
    """每个测试前后 invalidate，避免跨测试串台。"""
    config_service.invalidate_cache()
    yield
    config_service.invalidate_cache()
