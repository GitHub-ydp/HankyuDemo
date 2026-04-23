"""T-B10 v0.1 bidding API：自动填入 + 一次性 token 下载。

见架构任务单 §3。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.bidding import BiddingAutoFillResponse
from app.services.step2_bidding import temp_files
from app.services.step2_bidding.bidding_orchestrator import run_auto_fill
from app.services.step2_bidding.token_store import TOKEN_STORE


router = APIRouter(prefix="/bidding", tags=["Bidding"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_EXT = ".xlsx"
_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.post("/auto-fill", response_model=BiddingAutoFillResponse)
async def auto_fill(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BiddingAutoFillResponse:
    """一次性自动填入：identify → parse → match → fill×2。

    响应恒为 200 + BiddingAutoFillResponse（降级由 body.ok/error 区分）。
    仅 F6（> 10MB）走 413、F7（扩展名错）走 400。
    """
    filename = file.filename or ""
    if not filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(
            status_code=400,
            detail=f"F7_WRONG_EXTENSION: only .xlsx allowed (got {filename!r})",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"F6_FILE_TOO_LARGE: {len(content)} bytes > "
                f"{_MAX_UPLOAD_BYTES} bytes limit"
            ),
        )

    bid_id = _new_bid_id()
    bid_dir = temp_files.alloc_bid_dir(bid_id)
    input_path = bid_dir / "input.xlsx"
    with open(input_path, "wb") as fh:
        fh.write(content)

    return run_auto_fill(
        input_path=input_path,
        bid_id=bid_id,
        bid_dir=bid_dir,
        db=db,
    )


@router.get("/download/{token}")
async def download(token: str) -> FileResponse:
    """一次性 token 下载。过期 / 不存在 / 已用 → 400 F7 风格（见下）。

    用户任务单明确要求"同 token 再请求期望 400 F7"。按用户需求用 400；架构任务单 §3.2
    写的 410 记为已知偏离（接口语义不变，均指向 F5 文案）。
    """
    entry = TOKEN_STORE.consume(token)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail="F5_TOKEN_EXPIRED: token not found / expired / already used",
        )
    if not entry.path.exists():
        raise HTTPException(
            status_code=400,
            detail="F5_TOKEN_EXPIRED: backing file was cleaned up",
        )
    return FileResponse(
        path=str(entry.path),
        media_type=_XLSX_MEDIA_TYPE,
        filename=entry.filename,
    )


def _new_bid_id() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid4().hex[:8]}"
