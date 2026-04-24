"""v1 API 总路由"""
from fastapi import APIRouter

from app.api.v1.carriers import router as carriers_router
from app.api.v1.ports import router as ports_router
from app.api.v1.rates import router as rates_router
from app.api.v1.rate_batches import router as rate_batches_router
from app.api.v1.rate_downloads import router as rate_downloads_router
from app.api.v1.email_search import router as email_search_router
from app.api.v1.ai_parse import router as ai_parse_router
from app.api.v1.bidding import router as bidding_router
from app.api.v1.admin import router as admin_router

router = APIRouter(prefix="/api/v1")
router.include_router(carriers_router)
router.include_router(ports_router)
router.include_router(rates_router)
router.include_router(rate_batches_router)
router.include_router(rate_downloads_router)
router.include_router(email_search_router)
router.include_router(ai_parse_router)
router.include_router(bidding_router)
router.include_router(admin_router)
