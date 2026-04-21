"""数据导入 API"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.services import import_service

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview", response_model=ApiResponse)
async def preview_file(file: UploadFile = File(...)):
    """预览上传文件内容（前 10 行）"""
    content = await file.read()
    result = import_service.preview_import(content, file.filename)
    return ApiResponse(data=result)


@router.post("/tariffs", response_model=ApiResponse)
async def import_tariffs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """批量导入费率数据"""
    content = await file.read()
    result = import_service.import_tariffs(db, content, file.filename)
    return ApiResponse(data=result)
