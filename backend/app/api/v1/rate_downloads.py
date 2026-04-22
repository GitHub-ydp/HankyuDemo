"""Step1 rate batch 原格式回填下载路由。"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services import rate_batch_service
from app.services.step1_rates.entities import Step1FileType
from app.services.step1_rates.writers import get_writer

router = APIRouter(prefix="/rate-batches", tags=["rate-batches"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("/{batch_id}/download")
def download_rate_batch(batch_id: str) -> StreamingResponse:
    """导出当前 batch 的原格式回填 xlsx。"""
    draft = rate_batch_service._draft_batches.get(batch_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"rate batch {batch_id} not found")

    file_type_raw = (draft.legacy_payload or {}).get("file_type")
    if not file_type_raw:
        raise HTTPException(
            status_code=422,
            detail=f"rate batch {batch_id} has no file_type recorded",
        )
    try:
        file_type = Step1FileType(file_type_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        writer = get_writer(file_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        content, filename = writer.write(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"writer failed: {exc}") from exc

    encoded_name = quote(filename)
    headers = {
        "Content-Disposition": (
            f"attachment; filename*=UTF-8''{encoded_name}"
        )
    }
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers=headers,
    )
