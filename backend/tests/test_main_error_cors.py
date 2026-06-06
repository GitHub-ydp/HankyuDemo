"""全局兜底中间件：未处理异常产生的 500 也必须带 CORS 头。

根因回顾：Starlette 自带 ServerErrorMiddleware 在 CORS 之外层，未处理异常的 500
不经 CORS → 无 Access-Control-Allow-Origin → 浏览器跨域拦截 → 前端误报 Network Error。
ServerErrorCorsMiddleware 注册在 CORS 内层，把异常就地转 500，让 CORS 外层补上跨域头。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import ServerErrorCorsMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    # 顺序同 app.main：先加兜底(内层)，再加 CORS(外层)
    app.add_middleware(ServerErrorCorsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return app


def test_unhandled_500_keeps_cors_header():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/boom", headers={"Origin": "http://localhost:5173"})

    assert resp.status_code == 500
    # 关键：500 也带 CORS 头 → 浏览器不会把它吞成 Network Error
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    # 不向客户端泄漏内部堆栈/异常细节
    assert "kaboom" not in resp.text


def test_normal_200_still_has_cors_header():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/ok", headers={"Origin": "http://localhost:5173"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
