"""Demo 用：一键清空业务数据，方便重新导入演示。

清空内容：
- Step1 批次主表（import_batches）+ Air/LCL 明细（air_freight_rates / air_surcharges / lcl_rates）
- 老运价（freight_rates，含 Ocean/NGB/domestic 激活目的地）
- 上传记录（upload_logs）
- 内存草稿字典（rate_batch_service._draft_batches）
- 解析缓存（rates._parse_cache / ai_parse._parse_cache / _inbox_email_cache）
- Step2 下载 token 字典（TOKEN_STORE）

保留（主数据字典，reset 不清）：
- 港口（ports）：parser/activator 硬编码 un_locode / name 查询，清掉会导致 activation CARRIER/PORT_NOT_FOUND
- 船司（carriers）：activator._lookup_carrier 按 code / name_en 精确 + ilike 匹配，清掉会导致所有行 CARRIER_NOT_FOUND
  历史 bug：2026-04-24 reset 后 carriers 为空，NGB/Ocean 采用时 78 行全部 dict miss → 0 行入库

返回体向后兼容：rates_deleted / carriers_deleted / upload_logs_deleted / cache_cleared
仍然返回（前端已在用），carriers_deleted 固定为 0。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import FreightRate, UploadLog
from app.models.air_freight_rate import AirFreightRate
from app.models.air_surcharge import AirSurcharge
from app.models.import_batch import ImportBatch
from app.models.lcl_rate import LclRate
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset-rates")
def reset_rates(db: Session = Depends(get_db)):
    """一键清空 Step1/Step2 所有业务数据 + 内存（演示按钮）。"""
    # 统计清理前数量
    air_freight_count = db.query(AirFreightRate).count()
    air_surcharge_count = db.query(AirSurcharge).count()
    lcl_count = db.query(LclRate).count()
    freight_count = db.query(FreightRate).count()
    batch_count = db.query(ImportBatch).count()
    upload_count = db.query(UploadLog).count()

    # 删除顺序：先子表（带 batch_id / carrier_id 外键）→ import_batches → upload_logs
    # carriers / ports 作为主数据字典保留（见文件头注释）
    db.query(AirFreightRate).delete(synchronize_session=False)
    db.query(AirSurcharge).delete(synchronize_session=False)
    db.query(LclRate).delete(synchronize_session=False)
    db.query(FreightRate).delete(synchronize_session=False)
    db.query(ImportBatch).delete(synchronize_session=False)
    db.query(UploadLog).delete(synchronize_session=False)
    db.commit()

    # 清空内存字典
    from app.services.rate_batch_service import _draft_batches
    from app.api.v1.rates import _parse_cache as rates_parse_cache
    from app.api.v1.ai_parse import _parse_cache as ai_parse_cache
    from app.api.v1.ai_parse import _inbox_email_cache
    from app.services.step2_bidding.token_store import TOKEN_STORE

    drafts_cleared = len(_draft_batches)
    _draft_batches.clear()

    cache_cleared = (
        len(rates_parse_cache) + len(ai_parse_cache) + len(_inbox_email_cache)
    )
    rates_parse_cache.clear()
    ai_parse_cache.clear()
    _inbox_email_cache.clear()

    tokens_cleared = TOKEN_STORE.clear()

    # 向后兼容字段：rates_deleted 聚合所有 rate 类表，前端原有消息模板不破
    total_rates_deleted = air_freight_count + air_surcharge_count + lcl_count + freight_count

    return ApiResponse(data={
        "rates_deleted": total_rates_deleted,
        "carriers_deleted": 0,  # 主数据字典保留，见文件头注释
        "upload_logs_deleted": upload_count,
        "cache_cleared": cache_cleared,
        "batches_deleted": batch_count,
        "drafts_cleared": drafts_cleared,
        "tokens_cleared": tokens_cleared,
        "air_freight_rates_deleted": air_freight_count,
        "air_surcharges_deleted": air_surcharge_count,
        "lcl_rates_deleted": lcl_count,
        "freight_rates_deleted": freight_count,
    }, message=f"已清空 {total_rates_deleted} 条运价 / {batch_count} 个批次 / {drafts_cleared} 个草稿")
