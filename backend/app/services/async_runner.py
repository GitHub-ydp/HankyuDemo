"""AI 长任务后台执行器：与 FastAPI 请求线程池物理隔离的独立线程池。

设计要点：
- max_workers = settings.ai_max_concurrency，即 AI 并发上限（兼限流+排队）。
- work(task_db) 在后台线程跑，自带独立 DB session（请求 session 已随响应关闭）。
- work 返回的 dict 即「原 HTTP 响应体」，落 async_tasks.result_json 供前端轮询。
"""
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.async_task import AsyncTask, AsyncTaskStatus

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(
    max_workers=settings.ai_max_concurrency,
    thread_name_prefix="ai-task",
)


def create_task(db: Session, task_type: str) -> str:
    """在请求 session 内建一条 pending 任务，返回 task_id。"""
    task_id = uuid.uuid4().hex
    db.add(AsyncTask(id=task_id, task_type=task_type, status=AsyncTaskStatus.pending))
    db.commit()
    return task_id


def submit(task_id: str, work: Callable[[Session], dict]) -> Future:
    """把 work 丢进后台执行器。work 接收后台 DB session、返回响应体 dict。"""
    return _executor.submit(_run, task_id, work)


def _run(task_id: str, work: Callable[[Session], dict]) -> None:
    db = SessionLocal()
    try:
        task = db.get(AsyncTask, task_id)
        if task is None:
            logger.error("async task %s 不存在，跳过", task_id)
            return
        task.status = AsyncTaskStatus.running
        db.commit()
        try:
            data = work(db)
            task = db.get(AsyncTask, task_id)
            task.status = AsyncTaskStatus.succeeded
            task.result_json = data
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("async task %s 执行失败", task_id)
            db.rollback()
            task = db.get(AsyncTask, task_id)
            if task is not None:
                task.status = AsyncTaskStatus.failed
                task.error = str(exc)[:1000]
                db.commit()
    finally:
        db.close()
