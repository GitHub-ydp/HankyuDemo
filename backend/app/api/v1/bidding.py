"""T-B10 v0.1 bidding API：自动填入 + 一次性 token 下载。

见架构任务单 §3。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4
import zipfile

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
# .xlsx/.xlsm：单文件投标包（customer_a；.xlsm 是宏启用模板，identify 按内容识别、不看扩展名）；
# .zip：整包（Nitori 等多文件投标包，含报价表+成本邮件，单文件喂不了，须打包）
_ALLOWED_EXTS = (".xlsx", ".xlsm", ".zip")
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
    lower = filename.lower()
    if not lower.endswith(_ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail=f"F7_WRONG_EXTENSION: only .xlsx / .xlsm / .zip allowed (got {filename!r})",
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
    if lower.endswith(".zip"):
        # 整包：解压到 bid_dir，input_path 指向包内 TO GLOBAL 报价表，
        # bid_dir 用其所在目录（resolve_bundle 在该目录找报价表+成本邮件）。
        input_path = _prepare_zip_bundle(content, bid_dir)
        effective_dir = input_path.parent
    else:
        input_path = bid_dir / "input.xlsx"
        with open(input_path, "wb") as fh:
            fh.write(content)
        effective_dir = bid_dir

    return run_auto_fill(
        input_path=input_path,
        bid_id=bid_id,
        bid_dir=effective_dir,
        db=db,
    )


def _prepare_zip_bundle(content: bytes, bid_dir: Path) -> Path:
    """落盘并解压投标包 zip，返回包内 TO GLOBAL 报价表(*GLOBAL*.xlsm)路径。

    过滤 macOS 打包产生的 __MACOSX / `._` 资源叉文件，避免误选。
    """
    zip_path = bid_dir / "bundle.zip"
    zip_path.write_bytes(content)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(bid_dir)
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400, detail="F1_INVALID_XLSX: 上传的 zip 无法解压"
        )
    quotes = sorted(
        p
        for p in bid_dir.rglob("*GLOBAL*.xlsm")
        if "__MACOSX" not in p.parts and not p.name.startswith("._")
    )
    if not quotes:
        raise HTTPException(
            status_code=400,
            detail="F7_WRONG_EXTENSION: zip 内未找到 TO GLOBAL 报价表(*GLOBAL*.xlsm)",
        )
    return quotes[0]


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
