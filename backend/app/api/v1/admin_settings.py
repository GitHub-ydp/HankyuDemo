"""AI 设置页 API — GET / PATCH / test-connection / reset。

敏感字段脱敏由 config_service._build_response 负责；外层日志不打明文。
test-connection 基于已保存的配置调 health_check（决策 C + 业务需求 §1.3）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.app_settings import (
    AIConfigPatch,
    AIConfigResponse,
    TestConnectionResponse,
)
from app.schemas.common import ApiResponse
from app.services import ai_client, config_service

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


@router.get("/ai", response_model=ApiResponse[AIConfigResponse])
def get_ai_settings(db: Session = Depends(get_db)):
    """返回当前生效 AI 配置（敏感字段脱敏）+ 每字段 source（db | env）。"""
    resp = config_service.get_ai_config_response(db)
    return ApiResponse(data=resp)


@router.patch("/ai", response_model=ApiResponse[AIConfigResponse])
def patch_ai_settings(
    patch: AIConfigPatch,
    db: Session = Depends(get_db),
):
    """部分更新 AI 配置。字段三态（决策 D）：
    - 不出现在 body → 保持 DB / env 现值
    - body 里 = null → 敏感字段清空；普通字段回 NULL 从 env fallback
    - body 里 = 非空值 → 覆盖
    """
    try:
        resp = config_service.update_ai_config(patch, db=db, updated_by=None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败：{e}") from e
    return ApiResponse(data=resp, message="已保存")


@router.post("/ai/test-connection", response_model=ApiResponse[TestConnectionResponse])
def test_connection():
    """测当前生效（已保存）的 provider 连通性。未保存的编辑不参与。"""
    try:
        hc = ai_client.health_check(provider=None, timeout=5.0)
    except Exception as e:
        return ApiResponse(
            data=TestConnectionResponse(
                ok=False,
                provider=ai_client.get_current_provider(),
                latency_ms=0,
                detail=f"internal error: {e}",
            )
        )
    return ApiResponse(data=TestConnectionResponse(**hc))


@router.post("/ai/reset", response_model=ApiResponse[AIConfigResponse])
def reset_ai_settings(db: Session = Depends(get_db)):
    """重置为 env 默认值（删 DB 行），敏感字段一同清空。"""
    resp = config_service.reset_to_defaults(db=db, updated_by=None)
    return ApiResponse(data=resp, message="已重置")
