"""Step1 rate batch draft APIs."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.rate_batch import (
    RateBatchActivateRequest,
    RateBatchActivateResponse,
    RateBatchDetail,
    RateBatchDiffResponse,
    RateBatchSummary,
)
from app.services import rate_batch_service

router = APIRouter(prefix="/rate-batches", tags=["rate-batches"])


@router.post("/upload", response_model=ApiResponse[RateBatchDetail])
async def upload_rate_batch(
    file: UploadFile = File(..., description="Step1 source file"),
    parser_hint: str | None = Form(None, description="Optional parser adapter key"),
    db: Session = Depends(get_db),
):
    """Upload a Step1 draft batch and return preview rows."""
    try:
        content = await file.read()
        payload = rate_batch_service.create_draft_batch_from_upload(
            file_name=file.filename or "",
            content=content,
            db=db,
            parser_hint=parser_hint,
        )
        return ApiResponse(data=RateBatchDetail.model_validate(payload))
    except rate_batch_service.NoRatesFoundError:
        return ApiResponse(
            code=422,
            message="NO_RATES_IN_FILE",
        )
    except ValueError as exc:
        return ApiResponse(code=400, message=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(code=500, message=f"Failed to upload Step1 batch: {exc}")


@router.get("", response_model=ApiResponse[PaginatedData[RateBatchSummary]])
def list_rate_batches(
    batch_status: str | None = Query(None, description="Batch status filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """List Step1 draft batches."""
    items, total = rate_batch_service.list_rate_batches(
        page=page,
        page_size=page_size,
        batch_status=batch_status,
    )
    return ApiResponse(
        data=PaginatedData(
            items=[RateBatchSummary.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )
    )


@router.get("/{batch_id}", response_model=ApiResponse[RateBatchDetail])
def get_rate_batch_detail(batch_id: str):
    """Get one Step1 draft batch detail."""
    payload = rate_batch_service.get_rate_batch_detail(batch_id)
    if not payload:
        return ApiResponse(code=404, message=f"Rate batch {batch_id} not found")
    return ApiResponse(data=RateBatchDetail.model_validate(payload))


@router.get("/{batch_id}/diff", response_model=ApiResponse[RateBatchDiffResponse])
def get_rate_batch_diff(
    batch_id: str,
    db: Session = Depends(get_db),
):
    """Diff a Step1 draft batch against existing freight rates."""
    payload = rate_batch_service.get_rate_batch_diff(batch_id, db)
    if not payload:
        return ApiResponse(code=404, message=f"Rate batch {batch_id} not found")
    return ApiResponse(data=RateBatchDiffResponse.model_validate(payload))


@router.post("/{batch_id}/activate", response_model=ApiResponse[RateBatchActivateResponse])
def activate_rate_batch(
    batch_id: str,
    request: RateBatchActivateRequest,
    db: Session = Depends(get_db),
):
    """Activate a Step1 draft batch with a stable stub response."""
    payload = rate_batch_service.activate_rate_batch(
        batch_id,
        db,
        dry_run=request.dry_run,
        force=request.force,
        selected_row_indices=request.selected_row_indices,
    )
    if not payload:
        return ApiResponse(code=404, message=f"Rate batch {batch_id} not found")
    return ApiResponse(data=RateBatchActivateResponse.model_validate(payload))
