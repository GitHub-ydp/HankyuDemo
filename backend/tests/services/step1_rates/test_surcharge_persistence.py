"""P1-1 附加费入库回归：ngb/kmtc 附加费不得在激活映射层丢弃。

背景（2026-06-06 链路A 准确性测试）：源表有 BAF/THC/LSS/DOC 等附加费，
但 freight_rates 对应列全 null（ngb 0/78、kmtc 0/90）。根因两段：
1. to_freight_rate_from_ngb 不映射任何附加费字段（kmtc 已解析进 entity 仍被丢）；
2. OceanNgbAdapter 只把附加费收进 extras，entity 数值字段从未赋值。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.port import Port
from app.services.step1_rates.activator_mappers import to_freight_rate_from_ngb
from app.services.step1_rates.adapters.ocean_ngb import OceanNgbAdapter
from app.services.step1_rates.entities import ParsedRateRecord


@pytest.fixture()
def db():
    import app.models  # noqa: F401 注册全部模型

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all(
        [
            Carrier(code="KMTC", name_en="Korea Marine Transport"),
            Port(un_locode="CNSHA", name_en="Shanghai", name_cn="上海"),
            Port(un_locode="KRPUS", name_en="Busan", name_cn="釜山"),
        ]
    )
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_mapper_passes_surcharges_through(db):
    """kmtc 风格 record（附加费已在 entity 字段上）→ FreightRate 不得丢列。"""
    record = ParsedRateRecord(
        record_kind="ocean_ngb_fcl",
        carrier_name="KMTC",
        origin_port_name="CNSHA",
        destination_port_name="KRPUS",
        container_20gp=Decimal("130"),
        container_40gp=Decimal("260"),
        container_40hq=Decimal("260"),
        baf_20=Decimal("220"),
        baf_40=Decimal("440"),
        lss_20=Decimal("14"),
        lss_40=Decimal("28"),
        baf=Decimal("220"),
        yas_caf=Decimal("30"),
        thc=Decimal("960"),
        doc=Decimal("400"),
        isps=Decimal("30"),
        currency="USD",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 6, 30),
        source_type="excel",
        source_file="kmtc.xlsx",
        extras={"row_index": 6},
    )
    rate = to_freight_rate_from_ngb(record, uuid.uuid4(), db)
    assert rate.baf_20 == Decimal("220")
    assert rate.baf_40 == Decimal("440")
    assert rate.lss_20 == Decimal("14")
    assert rate.lss_40 == Decimal("28")
    assert rate.baf == Decimal("220")
    assert rate.yas_caf == Decimal("30")
    assert rate.thc == Decimal("960")
    assert rate.doc == Decimal("400")
    assert rate.isps == Decimal("30")


def _ngb_row(level: str = "Lv.1", mode: str = "FCL") -> list:
    """构造一行 55 列的 NGB Rate 行（按真实 4 月文件 row2 取值）。"""
    row: list = [None] * 55
    row[0] = "HHE/NGB"          # A agent
    row[1] = level               # B P/S rate
    row[2] = date(2026, 4, 1)    # C valid from
    row[3] = date(2026, 4, 30)   # D valid to
    row[4] = mode                # E FCL/LCL
    row[5] = "SINO"              # F shipping line
    row[8] = "NINGBO"            # I origin port
    row[9] = "TYO"               # J POD code
    row[12] = "JPTYO"            # M place of delivery code
    row[13] = "TOKYO"            # N place of delivery full
    row[16] = "USD"              # Q currency
    row[17] = 90                 # R 20GP
    row[18] = 150                # S 40GP
    row[19] = 150                # T 40HC
    row[20] = "USD"              # U FAF ccy
    row[21] = "240/TEU"          # V FAF value
    row[22] = "30/TEU"           # W YAS ccy or %
    row[23] = "PLUS"             # X YAS value
    row[24] = "CNY"              # Y THC ccy
    row[25] = 630                # Z THC 20
    row[26] = 960                # AA THC 40
    row[27] = "CNY"              # AB DOC ccy
    row[28] = 400                # AC DOC per BL
    row[29] = "CNY"              # AD seal ccy
    row[30] = 90                 # AE seal
    row[31] = "USD30/BL"         # AF ENS
    row[32] = "USD145/TEU"       # AG LSF/LSS
    row[34] = "CNY20/20'\nCNY30/40'"  # AI ISPS
    return row


def test_ngb_adapter_extracts_fcl_surcharges_into_entity_fields():
    """NGB FCL 行的附加费必须解析进 entity 数值字段（不只是 extras）。

    口径：/TEU 值按 20'=v、40'=2v；thc/isps 单值列取 40' 口径（与 ocean adapter
    _merge_40_payload 覆盖后的存量行为一致）。
    """
    adapter = OceanNgbAdapter()
    record, warnings, _, _ = adapter._build_ngb_record(
        _ngb_row(),
        2,
        source_file="ngb.xlsx",
        sheet_name="Rate",
        last_lv1_rates=None,
    )
    assert record is not None
    assert record.baf == Decimal("240")
    assert record.baf_20 == Decimal("240")
    assert record.baf_40 == Decimal("480")
    assert record.yas_caf == Decimal("30")
    assert record.thc == Decimal("960")
    assert record.doc == Decimal("400")
    assert record.lss_20 == Decimal("145")
    assert record.lss_40 == Decimal("290")
    assert record.isps == Decimal("30")
    # extras 原文保留不动
    assert record.extras["faf_value_raw"] == "240/TEU"
    assert record.extras["thc_20"] == 630


def test_ngb_mapper_roundtrip_persists_surcharges(db):
    """NGB record → to_freight_rate_from_ngb 全链路附加费非 null。"""
    db.add(Carrier(code="SINO", name_en="Sinokor Merchant Marine"))
    db.add(Port(un_locode="CNNGB", name_en="Ningbo", name_cn="宁波"))
    db.add(Port(un_locode="JPTYO", name_en="Tokyo", name_cn="东京"))
    db.commit()

    adapter = OceanNgbAdapter()
    record, _, _, _ = adapter._build_ngb_record(
        _ngb_row(),
        2,
        source_file="ngb.xlsx",
        sheet_name="Rate",
        last_lv1_rates=None,
    )
    rate = to_freight_rate_from_ngb(record, uuid.uuid4(), db)
    assert rate.baf == Decimal("240")
    assert rate.baf_20 == Decimal("240")
    assert rate.baf_40 == Decimal("480")
    assert rate.yas_caf == Decimal("30")
    assert rate.thc == Decimal("960")
    assert rate.doc == Decimal("400")
    assert rate.lss_20 == Decimal("145")
    assert rate.lss_40 == Decimal("290")


REAL_NGB_FILE = (
    Path(__file__).resolve().parents[4]
    / "资料"
    / "2026.04.21"
    / "RE_ 今後の進め方に関するご提案"
    / "【Ocean-NGB】 Ocean FCL rate sheet  HHENGB 2026 APR.xlsx"
)


def test_real_ngb_file_all_fcl_rows_have_baf():
    if not REAL_NGB_FILE.exists():
        pytest.skip(f"NGB 真实样本不可用：{REAL_NGB_FILE}")
    batch = OceanNgbAdapter().parse(REAL_NGB_FILE)
    fcl = [r for r in batch.records if r.record_kind == "ocean_ngb_fcl"]
    assert len(fcl) == 78
    missing = [r for r in fcl if r.baf is None or r.thc is None or r.doc is None]
    assert not missing, f"{len(missing)}/78 行附加费缺失"
    # 真实文件分布：75 行 FAF=240/TEU，3 行 FAF=0
    assert sum(1 for r in fcl if r.baf == Decimal("240")) == 75
    assert sum(1 for r in fcl if r.lss_20 == Decimal("145")) == 75
