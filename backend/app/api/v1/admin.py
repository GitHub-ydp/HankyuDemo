"""Demo 用：一键清空业务数据，方便重新导入演示。

清空内容：
- 运价（freight_rates）
- 船司与供应商（carriers）
- 上传记录（upload_logs）
- 内存解析缓存

保留：港口（ports）。
原因：港口是 parser 内硬编码 un_locode 查询的基础字典，没有 UI 创建入口，
清掉后会导致 rate import 失败，演示流程跑不通。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Carrier, FreightRate, UploadLog
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset-rates")
def reset_rates(db: Session = Depends(get_db)):
    """一键清空运价 + 船司 + 上传记录 + 内存缓存（演示按钮）。"""
    rate_count = db.query(FreightRate).count()
    upload_count = db.query(UploadLog).count()
    carrier_count = db.query(Carrier).count()

    # 顺序：先 freight_rates（含 carrier_id 外键），再 carriers
    db.query(FreightRate).delete(synchronize_session=False)
    db.query(UploadLog).delete(synchronize_session=False)
    db.query(Carrier).delete(synchronize_session=False)
    db.commit()

    # 清空内存解析缓存（rates.py + ai_parse.py）
    from app.api.v1.rates import _parse_cache as rates_parse_cache
    from app.api.v1.ai_parse import _parse_cache as ai_parse_cache
    from app.api.v1.ai_parse import _inbox_email_cache

    cache_cleared = (
        len(rates_parse_cache) + len(ai_parse_cache) + len(_inbox_email_cache)
    )
    rates_parse_cache.clear()
    ai_parse_cache.clear()
    _inbox_email_cache.clear()

    return ApiResponse(data={
        "rates_deleted": rate_count,
        "carriers_deleted": carrier_count,
        "upload_logs_deleted": upload_count,
        "cache_cleared": cache_cleared,
    }, message=f"已清空 {rate_count} 条运价 / {carrier_count} 条船司")
