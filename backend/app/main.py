"""FastAPI 应用入口"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭事件"""
    # 启动时自动建表
    init_db()
    # 确保上传目录存在
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI 驱动的海运运价自动解析与管理系统",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件（上传文件）
if os.path.isdir(settings.upload_dir):
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# 注册路由
from app.api.v1.router import router as v1_router  # noqa: E402
app.include_router(v1_router)


@app.get("/")
def root():
    return {"name": settings.app_name, "version": "0.2.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}
