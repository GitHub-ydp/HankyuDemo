"""上传记录 Schema"""
from datetime import datetime

from pydantic import BaseModel

from app.models.upload_log import UploadStatus


class UploadLogResponse(BaseModel):
    id: int
    batch_id: str
    file_name: str
    file_type: str
    source_type: str
    records_parsed: int
    records_imported: int
    status: UploadStatus
    error_message: str | None = None
    uploaded_by: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ParsePreviewRow(BaseModel):
    """解析预览中的单条数据"""
    origin_port: str
    destination_port: str
    carrier: str
    container_20gp: str | None = None
    container_40gp: str | None = None
    container_40hq: str | None = None
    container_45: str | None = None
    baf_20: str | None = None
    baf_40: str | None = None
    lss_20: str | None = None
    lss_40: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    transit_days: str | None = None
    remarks: str | None = None
    service_code: str | None = None


class ParsePreviewResponse(BaseModel):
    """文件解析预览响应"""
    batch_id: str
    file_name: str
    source_type: str
    total_rows: int
    preview_rows: list[ParsePreviewRow]
    columns_detected: list[str]
    warnings: list[str] = []


class ImportConfirmRequest(BaseModel):
    """确认导入请求"""
    batch_id: str
    confirmed_rows: list[int] | None = None  # None 表示全部导入


class ImportResultResponse(BaseModel):
    """导入结果响应"""
    batch_id: str
    records_parsed: int
    records_imported: int
    errors: list[str] = []
