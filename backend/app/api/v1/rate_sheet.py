"""运价表生成 API — 选模板 → 多源上传抽取 → 汇总预览(审核) → 下载填好的模板。

编排逻辑在 services/step1_rates/sheet_builder/orchestrator.py，本层只做 HTTP 适配。
"""
import json
import os
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.schemas.common import ApiResponse
from app.services.step1_rates.sheet_builder import orchestrator
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.sheet_builder.template_refill import (
    RefillError,
    refill_into_template,
)
from app.services.step1_rates.sheet_builder.template_registry import (
    supported_template_types,
)

router = APIRouter(prefix="/rate-sheet", tags=["rate-sheet"])


@router.post("/session")
def create_rate_sheet_session(template_type: str = Form(...)):
    """创建运价表生成会话（指定要做哪张表：air / sea）。"""
    if template_type not in supported_template_types():
        return ApiResponse(
            code=400,
            message=f"不支持的模板类型 '{template_type}'（支持: {'/'.join(supported_template_types())}）",
        )
    session = orchestrator.create_session(template_type)
    return ApiResponse(
        data={"session_id": session.session_id, "template_type": session.template_type}
    )


@router.post("/{session_id}/files")
async def upload_rate_sheet_files(
    session_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """上传该模板对应的一批杂料（各家 Excel / 微信图 / 邮件文本），逐个抽取并汇总。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    os.makedirs(settings.upload_dir, exist_ok=True)
    results = []
    for upload in files:
        original_name = upload.filename or "file"
        safe_name = original_name.replace("/", "_").replace("\\", "_")
        save_name = f"ratesheet_{uuid.uuid4().hex[:8]}_{safe_name}"
        save_path = os.path.join(settings.upload_dir, save_name)
        content = await upload.read()
        with open(save_path, "wb") as fh:
            fh.write(content)

        # 抽取(AI/Excel/PDF)是同步阻塞重活，甩到线程池，避免冻住 event loop 拖垮全站
        file_result = await run_in_threadpool(
            orchestrator.add_file, session_id, original_name, save_path, db
        )
        results.append(
            {
                "name": file_result.name,
                "source_type": file_result.source_type,
                "status": file_result.status,
                "row_count": file_result.row_count,
                "warnings": file_result.warnings,
                "message": file_result.message,
            }
        )

    needs_review = sum(1 for r in session.rows if r.get("needs_review"))
    return ApiResponse(
        data={
            "files": results,
            "summary": {
                "total_rows": len(session.rows),
                "needs_review": needs_review,
            },
        }
    )


@router.get("/{session_id}/preview")
def preview_rate_sheet(session_id: str):
    """返回汇总后的运价行（含 needs_review 标记），供审核台展示。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    return ApiResponse(
        data={
            "template_type": session.template_type,
            "total_rows": len(session.rows),
            "needs_review": sum(1 for r in session.rows if r.get("needs_review")),
            "rows": session.rows,
            "files": [
                {
                    "name": f.name,
                    "source_type": f.source_type,
                    "status": f.status,
                    "row_count": f.row_count,
                    "message": f.message,
                }
                for f in session.files
            ],
        }
    )


@router.get("/{session_id}/download")
def download_rate_sheet(session_id: str):
    """把汇总运价填进空白模板并返回 xlsx 下载流。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    content, filename = fill_template(session.template_type, session.rows)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class DownloadRequest(BaseModel):
    rows: list[dict[str, Any]]


@router.post("/{session_id}/download")
def download_rate_sheet_post(session_id: str, body: DownloadRequest):
    """按前端传来的「勾选+编辑后」最终行填模板并返回 xlsx（不读 session.rows）。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    content, filename = fill_template(session.template_type, body.rows)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{session_id}/download-into-template")
async def download_into_template(
    session_id: str,
    template: UploadFile = File(...),
    rows: str = Form(...),
):
    """指定数据下载：把当前会话 rows 按目的港回填进用户上传的模板（仅 OTHER PORTS 页）。"""
    try:
        session = orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")
    if session.template_type != "sea":
        return ApiResponse(code=400, message="指定数据下载仅支持海运模板")

    try:
        parsed_rows = json.loads(rows)
        if not isinstance(parsed_rows, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return ApiResponse(code=400, message="提交的运价数据格式有误")

    template_bytes = await template.read()
    try:
        content = await run_in_threadpool(
            refill_into_template, template_bytes, parsed_rows
        )
    except RefillError as exc:
        return ApiResponse(code=400, message=str(exc))
    except Exception:
        return ApiResponse(code=400, message="模板文件无法解析，请上传 .xlsx 模板")

    stem = (template.filename or "rate").rsplit(".", 1)[0] or "rate"
    download_name = f"{stem}_filled.xlsx"
    disposition = (
        "attachment; filename=rate_filled.xlsx; "
        f"filename*=UTF-8''{quote(download_name)}"
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )
