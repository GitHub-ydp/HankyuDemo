"""API 依赖注入"""
from app.core.database import get_db

# 重新导出，方便 API 路由引用
__all__ = ["get_db"]
