"""回归：做表→海运入库时，KMTC 等文件的港口名是双语合并形态 "English/中文"
（如 "Shanghai/上海"、"Busan/釜山"），_resolve_port 整串匹配不到 → 全部 skipped_unresolved
→ 入库 0 条。修复后应能拆分双语名、命中字典里的港口。
"""
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Carrier, CarrierType, Port
from app.services.step1_rates.sheet_builder.db_writer import commit_ocean_rows


@pytest.fixture
def db_session() -> Iterator:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # 字典：KMTC 船司 + 上海/釜山港（与真实 seed 同形：英文名 + 中文名）
    db.add(Carrier(code="KMTC", name_en="KMTC", name_cn="高丽海运",
                   carrier_type=CarrierType.shipping_line, country="KR"))
    db.add(Port(un_locode="CNSHA", name_en="Shanghai", name_cn="上海", country="CN", region="East Asia"))
    db.add(Port(un_locode="KRPUS", name_en="Busan", name_cn="釜山", country="KR", region="East Asia"))
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_commit_ocean_resolves_bilingual_port_names(db_session):
    db = db_session
    rows = [
        # 双语名 + 字典里有 → 应入库
        {"origin": "Shanghai/上海", "destination": "Busan/釜山", "carrier": "KMTC",
         "container_20gp": 100, "container_40gp": 200, "container_40hq": 210},
        # 双语名但字典里没有该目的港 → 仍跳过（数据完整性问题，非本 bug）
        {"origin": "Shanghai/上海", "destination": "Nowhere/无此港", "carrier": "KMTC",
         "container_20gp": 50, "container_40gp": 80, "container_40hq": 90},
    ]

    result = commit_ocean_rows(rows, db)

    assert result.skipped_no_price == 0           # 两行都有箱型价
    assert result.fcl_rows == 1                    # 上海→釜山 应成功入库（当前 bug 下是 0）
    assert result.skipped_unresolved == 1          # 仅 Nowhere 那行因字典无该港跳过
