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
