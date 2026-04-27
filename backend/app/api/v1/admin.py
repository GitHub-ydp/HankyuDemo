"""Demo 用：一键清空业务数据，方便重新导入演示。

清空内容：
- Step1 批次主表（import_batches）+ Air/LCL 明细（air_freight_rates / air_surcharges / lcl_rates）
- 老运价（freight_rates，含 Ocean/NGB/domestic 激活目的地）
- 上传记录（upload_logs）
- 主数据字典（ports / carriers）—— 清空后立即调 scripts/seed_data.py 的 reseed_dictionaries()
  自动重灌，保证字典完整（避免 04-24 NGB 78 行全 CARRIER_NOT_FOUND 0 行入库的历史坑）
- 内存草稿字典（rate_batch_service._draft_batches）
- 解析缓存（rates._parse_cache / ai_parse._parse_cache / _inbox_email_cache）
- Step2 下载 token 字典（TOKEN_STORE）

返回体新增字段：carriers_reseeded / ports_reseeded（重灌数量）；
carriers_deleted 改为实际清掉的条数（不再固定 0）。
"""
import importlib.util
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Carrier, FreightRate, Port, UploadLog
from app.models.air_freight_rate import AirFreightRate
from app.models.air_surcharge import AirSurcharge
from app.models.import_batch import ImportBatch
from app.models.lcl_rate import LclRate
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def _load_seed_module():
    """动态加载 scripts/seed_data.py（不是 python 包，不能直接 import）。"""
    seed_path = Path(__file__).resolve().parents[4] / "scripts" / "seed_data.py"
    spec = importlib.util.spec_from_file_location("seed_data", seed_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法定位 seed_data 模块: {seed_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    carrier_count = db.query(Carrier).count()
    port_count = db.query(Port).count()

    # 删除顺序：先子表（带 batch_id / carrier_id 外键）→ import_batches → upload_logs
    # → 字典（carriers / ports），最后由 reseed_dictionaries 重灌
    db.query(AirFreightRate).delete(synchronize_session=False)
    db.query(AirSurcharge).delete(synchronize_session=False)
    db.query(LclRate).delete(synchronize_session=False)
    db.query(FreightRate).delete(synchronize_session=False)
    db.query(ImportBatch).delete(synchronize_session=False)
    db.query(UploadLog).delete(synchronize_session=False)
    db.query(Carrier).delete(synchronize_session=False)
    db.query(Port).delete(synchronize_session=False)
    db.commit()

    # 立即重灌字典（同 session）
    seed_module = _load_seed_module()
    reseed_result = seed_module.reseed_dictionaries(db)

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
        "carriers_deleted": carrier_count,
        "ports_deleted": port_count,
        "carriers_reseeded": reseed_result["carriers_reseeded"],
        "ports_reseeded": reseed_result["ports_reseeded"],
        "upload_logs_deleted": upload_count,
        "cache_cleared": cache_cleared,
        "batches_deleted": batch_count,
        "drafts_cleared": drafts_cleared,
        "tokens_cleared": tokens_cleared,
        "air_freight_rates_deleted": air_freight_count,
        "air_surcharges_deleted": air_surcharge_count,
        "lcl_rates_deleted": lcl_count,
        "freight_rates_deleted": freight_count,
    }, message=f"已清空 {total_rates_deleted} 条运价 / {batch_count} 个批次 / {drafts_cleared} 个草稿；重灌 {reseed_result['carriers_reseeded']} 船司 / {reseed_result['ports_reseeded']} 港口")
