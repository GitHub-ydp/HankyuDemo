"""admin/reset-rates 重灌 seed 测试。

验证：
1. reset 前的 carriers / ports 被清空
2. 重灌后 carriers ≥ seed 列表数量
3. 返回体含 carriers_reseeded / ports_reseeded > 0
4. carriers_deleted 反映「净清掉的临时船司」（清前总数 - 重灌字典数），
   carriers_purged_total 反映清前总数，carriers_kept_dict 反映保留的字典数
"""
from typing import Iterator

import pytest
from sqlalchemy import create_engine, event
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models import Base, Carrier, CarrierType, Port
from app.models.air_tier_rate import AirTierRate
from app.models.import_batch import ImportBatch, ImportBatchFileType
from tests.api_v1._auth_helpers import login_headers, register

ADMIN_EMAIL = "admin@x.com"


def _admin_headers(client, monkeypatch):
    """注册并登录一个管理员（邮箱∈ADMIN_EMAILS），返回 Bearer 头。

    reset-rates 现在要求管理员鉴权，测试需带 token 调用。
    """
    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    register(client, ADMIN_EMAIL)
    return login_headers(client, ADMIN_EMAIL)


@pytest.fixture
def client_with_isolated_db(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "admin_reset_reseed.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
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


def _seed_fake_dict(client: TestClient):
    """通过 dependency override 拿一个 db session 灌假数据。"""
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        db.add(Port(un_locode="ZZTST", name_en="Test Port", name_cn="测试港", country="X", region="Y"))
        db.add(
            Carrier(
                code="ZZTC",
                name_en="Test Carrier",
                name_cn="测试船司",
                carrier_type=CarrierType.shipping_line,
                country="X",
            )
        )
        db.commit()
        port_count_before = db.query(Port).count()
        carrier_count_before = db.query(Carrier).count()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
    return port_count_before, carrier_count_before


def test_reset_requires_admin(client_with_isolated_db, monkeypatch):
    """reset-rates 仅管理员可调用：无 token→401，非管理员→403。"""
    client = client_with_isolated_db
    assert client.post("/api/v1/admin/reset-rates").status_code == 401

    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    register(client, "user@x.com")
    headers = login_headers(client, "user@x.com")
    assert client.post("/api/v1/admin/reset-rates", headers=headers).status_code == 403


def test_reset_clears_dict_and_reseeds(client_with_isolated_db, monkeypatch):
    client = client_with_isolated_db
    port_before, carrier_before = _seed_fake_dict(client)
    assert port_before >= 1
    assert carrier_before >= 1

    headers = _admin_headers(client, monkeypatch)
    r = client.post("/api/v1/admin/reset-rates", headers=headers)
    assert r.status_code == 200
    body = r.json()
    data = body["data"]

    # 返回体含重灌字段
    assert "carriers_reseeded" in data
    assert "ports_reseeded" in data
    assert data["carriers_reseeded"] > 0
    assert data["ports_reseeded"] > 0

    # purged_total = 清前总数；kept_dict = 重灌字典数；deleted = 净清掉（临时部分）
    assert data["carriers_purged_total"] == carrier_before
    assert data["ports_purged_total"] == port_before
    assert data["carriers_kept_dict"] == data["carriers_reseeded"]
    assert data["ports_kept_dict"] == data["ports_reseeded"]
    assert data["carriers_deleted"] == max(0, carrier_before - data["carriers_reseeded"])
    assert data["ports_deleted"] == max(0, port_before - data["ports_reseeded"])

    # 重灌后 db 里 carriers / ports ≥ seed 列表数量
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        carriers_now = db.query(Carrier).count()
        ports_now = db.query(Port).count()

        # 假数据 ZZTST/ZZTC 已被清掉，留下的全是 seed 数据
        assert db.query(Carrier).filter(Carrier.code == "ZZTC").count() == 0
        assert db.query(Port).filter(Port.un_locode == "ZZTST").count() == 0

        assert carriers_now == data["carriers_reseeded"]
        assert ports_now == data["ports_reseeded"]
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_reset_on_empty_db_still_reseeds(client_with_isolated_db, monkeypatch):
    """空库直接 reset 也能正常重灌（无破坏性）。"""
    client = client_with_isolated_db
    headers = _admin_headers(client, monkeypatch)
    r = client.post("/api/v1/admin/reset-rates", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["carriers_deleted"] == 0
    assert data["ports_deleted"] == 0
    assert data["carriers_reseeded"] > 0
    assert data["ports_reseeded"] > 0


@pytest.fixture
def client_with_fk_db(tmp_path) -> Iterator[TestClient]:
    """与生产一致：SQLite 开启 FK 强制（PRAGMA foreign_keys=ON）。

    生产 engine 在 app/core/database.py 通过 connect 事件开 FK；测试 engine 是另建的，
    默认 FK 关闭——不开就复现不了「删父表 import_batches 时子表仍引用」的 FK 报错。
    """
    db_path = tmp_path / "admin_reset_fk.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

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


def test_reset_clears_air_tier_rates_with_fk_on(client_with_fk_db, monkeypatch):
    """回归：库里有 air_tier_rates(FK->import_batches) 时 reset 不能因 FK 报 500。

    air_tier_rates 是 Air EES 多档表，reset_rates 早期删除清单漏了它；
    开启 FK 后删 import_batches 会触发 FOREIGN KEY constraint failed → 500 → 前端 Network Error。
    """
    client = client_with_fk_db

    # 灌一个批次 + 一条挂在它下面的 air_tier 运价
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        batch = ImportBatch(file_type=ImportBatchFileType.air_tier, row_count=1)
        db.add(batch)
        db.flush()
        db.add(
            AirTierRate(
                origin="PVG",
                destination="LAX",
                tier_prices={"45": 17, "100": 14},
                batch_id=batch.batch_id,
            )
        )
        db.commit()
        assert db.query(AirTierRate).count() == 1
        assert db.query(ImportBatch).count() == 1
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    headers = _admin_headers(client, monkeypatch)
    r = client.post("/api/v1/admin/reset-rates", headers=headers)
    assert r.status_code == 200, r.text  # 当前 bug 下这里会是 500

    # air_tier_rates 与 import_batches 都被清掉
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        assert db.query(AirTierRate).count() == 0
        assert db.query(ImportBatch).count() == 0
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
