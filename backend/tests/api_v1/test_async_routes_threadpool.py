"""并发安全回归：长任务 async 路由必须把同步阻塞调用移出 event loop 线程。

背景：生产是单进程 uvicorn，只有一个 event loop。若 `async def` 路由在 loop
线程上**同步**执行重型阻塞调用（AI 推理 / Excel·PDF 解析 / xlwings 填表 /
.msg 解析），该长任务运行期间 loop 被独占，无法调度任何其它请求 → 全站卡死。
正确做法是用 fastapi.concurrency.run_in_threadpool 把同步调用甩到线程池。

探针原理：在被 mock 的业务函数里调 asyncio.get_running_loop()。
- 仍在 event loop 线程同步执行 → 不抛 → on_loop=True（= 会冻全站，bug）
- 被 run_in_threadpool 甩到 worker 线程 → RuntimeError → on_loop=False（已修复）
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app


def _on_event_loop_thread() -> bool:
    """在当前线程探测是否处于运行中的 event loop 线程。"""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


@pytest.fixture
def client():
    """get_db 置换为不连真实库的空 session（被测路由的 db 只透传给被 mock 的函数）。"""

    def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_rate_batch_upload_offloads_parse(client, monkeypatch):
    """POST /rate-batches/upload 的解析不得在 event loop 线程跑。"""
    from app.services import rate_batch_service

    seen: dict[str, bool] = {}

    def spy_create(file_name, content, db, parser_hint=None):
        seen["on_loop"] = _on_event_loop_thread()
        raise rate_batch_service.NoRatesFoundError("probe")

    monkeypatch.setattr(
        rate_batch_service, "create_draft_batch_from_upload", spy_create
    )

    resp = client.post(
        "/api/v1/rate-batches/upload",
        files={"file": ("r.xlsx", b"x", "application/octet-stream")},
    )

    # NoRatesFoundError → ApiResponse(code=422)，HTTP 仍 200
    assert resp.status_code == 200
    assert seen.get("on_loop") is False, (
        "create_draft_batch_from_upload 仍在 event loop 线程执行 → 解析期间冻全站"
    )


def test_upload_msg_file_offloads(client, monkeypatch):
    """POST /ai/upload-msg-file 的 .msg 解析不得在 event loop 线程跑。"""
    import extract_msg

    seen: dict[str, bool] = {}

    def spy_open(path):
        seen["on_loop"] = _on_event_loop_thread()
        # 抛普通异常，被路由 try/except 捕获成 400（HTTP 200），输出 pristine
        raise RuntimeError("probe")

    monkeypatch.setattr(extract_msg, "openMsg", spy_open)

    resp = client.post(
        "/api/v1/ai/upload-msg-file",
        files={"file": ("mail.msg", b"x", "application/octet-stream")},
    )

    assert resp.status_code == 200
    assert seen.get("on_loop") is False, (
        "extract_msg.openMsg 仍在 event loop 线程执行 → .msg 解析期间冻全站"
    )
