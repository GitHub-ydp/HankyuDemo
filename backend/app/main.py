"""FastAPI 应用入口"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db

logger = logging.getLogger("app.error")


class ServerErrorCorsMiddleware:
    """兜底：任何未处理异常 → 500 JSON 响应（而非裸 raise）。

    为什么需要它：Starlette 自带的 ServerErrorMiddleware 处于 CORSMiddleware 之外层，
    未处理异常产生的 500 不会经过 CORS 的 send 包装 → 响应缺 Access-Control-Allow-Origin
    → 浏览器跨域拦截 → 前端 axios 拿不到 response → 误报「Network Error / 网络异常」。

    本中间件注册在 CORSMiddleware 之“内层”（在其之前 add_middleware），把异常就地转成
    正常 500 响应，于是 CORS 外层能给它正常加上 CORS 头，前端就能看到真实的 500 而非
    假的网络错误。注意只在尚未开始发送响应时兜底（流式中途异常无法补救，按原样抛出）。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            logger.exception("未处理异常，返回 500 JSON（保留 CORS 头）")
            if response_started:
                # 响应头已发出，无法再替换，只能继续抛给外层 ServerErrorMiddleware
                raise
            response = JSONResponse(
                status_code=500, content={"detail": "Internal Server Error"}
            )
            await response(scope, receive, send)


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

# ⚠️ 中间件顺序：后 add 的处于外层。先加“异常兜底”(内层)，再加 CORS(外层)，
# 这样未处理异常被兜底成 500 响应后，仍会经过 CORS 外层补上跨域头（避免前端误报 Network Error）。
app.add_middleware(ServerErrorCorsMiddleware)

# CORS 中间件（外层）
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
