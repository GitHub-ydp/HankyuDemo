"""Bidding /auto-fill 端点：Nitori 投标包 .zip 整包上传端到端。

验证部署态真实路径：上传 zip → 解压 → 识别 nitori → 填表 → 返回下载 token。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app
from app.models import Base


NITORI_ZIP = (
    Path(__file__).resolve().parents[3]
    / "资料"
    / "2026.05.26"
    / "ニトリ様海上入札.zip"
)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'bidding_zip.db'}",
        connect_args={"check_same_thread": False},
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_auto_fill_nitori_zip_end_to_end(client):
    if not NITORI_ZIP.exists():
        pytest.skip(f"Nitori zip 不可用：{NITORI_ZIP}")
    with open(NITORI_ZIP, "rb") as f:
        resp = client.post(
            "/api/v1/bidding/auto-fill",
            files={"file": ("ニトリ様海上入札.zip", f, "application/zip")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, body
    assert body["identify"]["matched_customer"] == "nitori"
    assert body["fill"]["filled_count"] > 0
    assert body["download"]["cost_token"]
    assert body["download"]["sr_token"]


def test_auto_fill_rejects_unknown_ext(client):
    resp = client.post(
        "/api/v1/bidding/auto-fill",
        files={"file": ("foo.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "F7" in resp.text


def test_auto_fill_accepts_xlsm_single_file(client):
    """单文件 .xlsm 投标包应被受理(走内容识别)，不再被 F7 扩展名挡掉。

    投标模板常是宏启用的 .xlsm；以前只放行 .xlsx/.zip，用户被迫把单文件打成 zip。
    """
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = "x"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = client.post(
        "/api/v1/bidding/auto-fill",
        files={
            "file": (
                "bid.xlsm",
                buf,
                "application/vnd.ms-excel.sheet.macroEnabled.12",
            )
        },
    )
    # 过了扩展名闸门：恒 200 + body(降级由 ok/error 区分)；不能是 400 F7。
    assert resp.status_code == 200, resp.text
    assert "F7_WRONG_EXTENSION" not in resp.text


def test_auto_fill_nitori_single_xlsm_db_only(client):
    """单个 Nitori 报价表 .xlsm（无成本邮件）应按「纯 DB 运价匹配」处理，绝不能裸 500。

    回归 bug：d297c85 放开 .xlsm 闸门后，单个「TO GLOBAL 見積り書.xlsm」被 identify
    判成 nitori → 走未加 try 的 _run_nitori → resolve_bundle 找不到整包而抛异常 →
    裸 500（无 CORS 头）→ 浏览器拦截 → 前端显示「网络异常 / Network Error」。

    新行为（福山口径：海运优先查 DB 运价，成本邮件仅兜底）：单 .xlsm 也能跑——
    报价表即上传文件本身，纯按 DB 匹配；缺成本邮件时给出 warning 而非报错。
    本测试 DB 为空 → filled=0，但仍 ok=True + 可下载 + warning，且绝不是 500/F8。
    """
    import io
    import zipfile

    if not NITORI_ZIP.exists():
        pytest.skip(f"Nitori zip 不可用：{NITORI_ZIP}")

    # 从整包里抠出单个 TO GLOBAL 报价表 .xlsm，模拟用户只传了这一个文件
    with zipfile.ZipFile(NITORI_ZIP) as zf:
        name = next(
            n
            for n in zf.namelist()
            if "GLOBAL" in n
            and n.lower().endswith(".xlsm")
            and "__MACOSX" not in n
            and not Path(n).name.startswith("._")
        )
        data = zf.read(name)

    resp = client.post(
        "/api/v1/bidding/auto-fill",
        files={
            "file": (
                "見積り書.xlsm",
                io.BytesIO(data),
                "application/vnd.ms-excel.sheet.macroEnabled.12",
            )
        },
    )

    # 关键断言：绝不能是 500（500 无 CORS → 浏览器里就是 Network Error）
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["identify"]["matched_customer"] == "nitori"
    assert body["ok"] is True, body            # 单文件也被处理，而不是报错
    assert body["download"]["cost_token"]      # 产出可下载
    assert body["download"]["sr_token"]
    # 缺成本邮件 → 必有「仅按 DB 匹配」的 warning
    assert any("成本邮件" in w for w in body["fill"]["global_warnings"]), body
    assert "F8_NETWORK_ERROR" not in resp.text
