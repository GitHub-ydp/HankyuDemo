"""异步任务轮询端点。前端提交 AI 任务拿 task_id 后轮询此处直到终态。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.async_task import AsyncTask
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/tasks", tags=["async-tasks"])


@router.get("/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(AsyncTask, task_id)
    if task is None:
        return ApiResponse(code=404, message="任务不存在或已过期")
    status = task.status.value if hasattr(task.status, "value") else task.status
    return ApiResponse(data={
        "task_id": task.id,
        "status": status,
        "result": task.result_json,
        "error": task.error,
    })
