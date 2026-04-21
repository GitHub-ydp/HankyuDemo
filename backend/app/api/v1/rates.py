"""海运费率 API"""
import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models import RateStatus
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.freight_rate import FreightRateDetail
from app.schemas.upload_log import ImportResultResponse, ParsePreviewResponse, ParsePreviewRow
from app.services import freight_rate_service
from app.services.rate_parser import (
    detect_and_parse,
    import_parsed_rates,
    parse_kmtc_excel,
    parse_nvo_fak_excel,
)

router = APIRouter(prefix="/rates", tags=["rates"])

# 内存中缓存解析结果（Demo 用，生产应用 Redis）
_parse_cache: dict[str, dict] = {}


# ========== 费率查询 ==========

@router.get("", response_model=ApiResponse[PaginatedData[FreightRateDetail]])
def list_rates(
    origin_port_id: int | None = Query(None),
    destination_port_id: int | None = Query(None),
    carrier_id: int | None = Query(None),
    origin: str | None = Query(None, description="起运港关键词"),
    destination: str | None = Query(None, description="目的港关键词"),
    carrier: str | None = Query(None, description="船司关键词"),
    status: str | None = Query(None, description="状态: draft/active/expired"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = freight_rate_service.get_rates(
        db,
        origin_port_id=origin_port_id,
        destination_port_id=destination_port_id,
        carrier_id=carrier_id,
        origin_keyword=origin,
        destination_keyword=destination,
        carrier_keyword=carrier,
        status=status,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=PaginatedData(
        items=[FreightRateDetail.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    ))


@router.get("/stats")
def rate_stats(db: Session = Depends(get_db)):
    """费率统计"""
    return ApiResponse(data=freight_rate_service.get_rate_stats(db))


@router.get("/compare")
def compare_rates(
    origin_port_id: int = Query(..., description="起运港ID"),
    destination_port_id: int = Query(..., description="目的港ID"),
    db: Session = Depends(get_db),
):
    """同航线多供应商比价"""
    from app.services.port_service import get_port
    origin = get_port(db, origin_port_id)
    destination = get_port(db, destination_port_id)
    if not origin or not destination:
        return ApiResponse(code=400, message="无效的港口ID")

    rates = freight_rate_service.compare_rates(db, origin_port_id, destination_port_id)
    return ApiResponse(data={
        "origin": {"id": origin.id, "un_locode": origin.un_locode, "name_en": origin.name_en, "name_cn": origin.name_cn},
        "destination": {"id": destination.id, "un_locode": destination.un_locode, "name_en": destination.name_en, "name_cn": destination.name_cn},
        "rates": rates,
        "total": len(rates),
    })


@router.get("/{rate_id}", response_model=ApiResponse[FreightRateDetail])
def get_rate(rate_id: int, db: Session = Depends(get_db)):
    rate = freight_rate_service.get_rate(db, rate_id)
    if not rate:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(data=FreightRateDetail.model_validate(rate))


@router.put("/{rate_id}/status")
def update_status(rate_id: int, status: str = Query(...), db: Session = Depends(get_db)):
    """更新费率状态（draft → active / expired）"""
    try:
        rate_status = RateStatus(status)
    except ValueError:
        return ApiResponse(code=400, message=f"无效状态: {status}")
    rate = freight_rate_service.update_rate_status(db, rate_id, rate_status)
    if not rate:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(data={"id": rate_id, "status": status})


@router.put("/batch/{batch_id}/status")
def batch_update_status(batch_id: str, status: str = Query(...), db: Session = Depends(get_db)):
    """批量更新同批次费率状态"""
    try:
        rate_status = RateStatus(status)
    except ValueError:
        return ApiResponse(code=400, message=f"无效状态: {status}")
    count = freight_rate_service.batch_update_status(db, batch_id, rate_status)
    return ApiResponse(data={"batch_id": batch_id, "status": status, "updated_count": count})


@router.delete("/{rate_id}")
def delete_rate(rate_id: int, db: Session = Depends(get_db)):
    ok = freight_rate_service.delete_rate(db, rate_id)
    if not ok:
        return ApiResponse(code=404, message="费率不存在")
    return ApiResponse(message="删除成功")


# ========== 文件上传与解析 ==========

@router.post("/upload/parse")
async def upload_and_parse(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传费率文件并解析预览"""
    # 保存文件
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in (".xlsx", ".xls", ".csv"):
        return ApiResponse(code=400, message="仅支持 Excel (.xlsx/.xls) 和 CSV 文件")

    os.makedirs(settings.upload_dir, exist_ok=True)
    save_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, save_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # 自动检测并解析
    result = detect_and_parse(save_path, db)

    if "error" in result:
        return ApiResponse(code=400, message=result["error"])

    # 缓存解析结果（供后续确认导入用）
    _parse_cache[result["batch_id"]] = result

    # 构建预览响应
    all_rows = []
    if "parsed_rows" in result:
        all_rows = result["parsed_rows"]
    elif "sheets" in result:
        for sheet in result["sheets"]:
            all_rows.extend(sheet["parsed_rows"])

    preview_rows = []
    for r in all_rows[:50]:  # 最多预览50行
        preview_rows.append({
            "origin_port": r.get("origin_port_name", ""),
            "destination_port": r.get("destination_port_name", ""),
            "carrier": result.get("carrier_code", ""),
            "container_20gp": str(r["container_20gp"]) if r.get("container_20gp") else None,
            "container_40gp": str(r["container_40gp"]) if r.get("container_40gp") else None,
            "container_40hq": str(r["container_40hq"]) if r.get("container_40hq") else None,
            "container_45": str(r["container_45"]) if r.get("container_45") else None,
            "baf_20": str(r["baf_20"]) if r.get("baf_20") else None,
            "baf_40": str(r["baf_40"]) if r.get("baf_40") else None,
            "lss_20": str(r["lss_20"]) if r.get("lss_20") else None,
            "lss_40": str(r["lss_40"]) if r.get("lss_40") else None,
            "valid_from": str(r["valid_from"]) if r.get("valid_from") else None,
            "valid_to": str(r["valid_to"]) if r.get("valid_to") else None,
            "transit_days": str(r["transit_days"]) if r.get("transit_days") else None,
            "remarks": r.get("remarks"),
            "service_code": r.get("service_code"),
        })

    return ApiResponse(data={
        "batch_id": result["batch_id"],
        "file_name": result.get("file_name", file.filename),
        "source_type": result.get("source_type", "excel"),
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result.get("total_rows", len(all_rows)),
        "preview_rows": preview_rows,
        "warnings": result.get("warnings", []),
        "sheets": [{"name": s["sheet_name"], "rows": s["total_rows"]} for s in result.get("sheets", [])],
    })


@router.post("/upload/confirm")
def confirm_import(
    batch_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """确认导入解析结果到数据库"""
    parsed_data = _parse_cache.get(batch_id)
    if not parsed_data:
        return ApiResponse(code=404, message=f"批次 {batch_id} 不存在或已过期，请重新上传")

    result = import_parsed_rates(parsed_data, db)

    # 清理缓存
    _parse_cache.pop(batch_id, None)

    return ApiResponse(data=result)
