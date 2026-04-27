"""admin/reset-rates 重灌 seed 测试。

验证：
1. reset 前的 carriers / ports 被清空
2. 重灌后 carriers ≥ seed 列表数量
3. 返回体含 carriers_reseeded / ports_reseeded > 0
4. carriers_deleted 不再固定 0，反映实际清掉的条数
"""
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app
from app.models import Base, Carrier, CarrierType, Port


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


def test_reset_clears_dict_and_reseeds(client_with_isolated_db):
    client = client_with_isolated_db
    port_before, carrier_before = _seed_fake_dict(client)
    assert port_before >= 1
    assert carrier_before >= 1

    r = client.post("/api/v1/admin/reset-rates")
    assert r.status_code == 200
    body = r.json()
    data = body["data"]

    # 返回体含重灌字段
    assert "carriers_reseeded" in data
    assert "ports_reseeded" in data
    assert data["carriers_reseeded"] > 0
    assert data["ports_reseeded"] > 0

    # carriers_deleted 反映实际清掉的条数（不再固定 0）
    assert data["carriers_deleted"] == carrier_before
    assert data["ports_deleted"] == port_before

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


def test_reset_on_empty_db_still_reseeds(client_with_isolated_db):
    """空库直接 reset 也能正常重灌（无破坏性）。"""
    client = client_with_isolated_db
    r = client.post("/api/v1/admin/reset-rates")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["carriers_deleted"] == 0
    assert data["ports_deleted"] == 0
    assert data["carriers_reseeded"] > 0
    assert data["ports_reseeded"] > 0
