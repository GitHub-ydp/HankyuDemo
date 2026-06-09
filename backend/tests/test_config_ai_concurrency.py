"""AI 后台执行器并发上限默认值（兼限流），可被 env 覆盖。"""


def test_ai_max_concurrency_default():
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.ai_max_concurrency == 3
