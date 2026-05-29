# Nitori 海运按 DB 运价匹配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Nitori(海运)投标包按 **DB 里的运价(FreightRate)** 匹配取价，而不是读投标包 zip 内的成本文件；并打通"海运做表→入库 FreightRate→Nitori 取价"后端闭环(MVP)。

**Architecture:** 复用 `FreightRate` 表(FCL)。Sea 做表已有，增强 `_normalize_sea` 保留结构化箱型/船司/transit；新增 `commit_ocean_rows` 写 FreightRate(解析港口/船司，supersede 旧 active ocean 批)；实现 `query_ocean_fcl` 只读查 active FreightRate；`NitoriProfile.match` 改为优先查 DB、查不到回退 cost-book。范围由 Nitori 倒逼(只覆盖其用到的 lane/箱型)。

**Tech Stack:** Python 3.10 / FastAPI / SQLAlchemy 2.0 / pytest。本地测试用 `../.venv/bin/python -m pytest`。

**Spec:** `docs/superpowers/specs/2026-05-29-nitori-ocean-db-match-design.md`
**MVP defer**(面向客户须说明)：Arbitrary/内陆附加费、LAX PDF、全附加费矩阵(ebs/yas/caf/isps/equipment/booking/thc/doc)、CNY 杂费、LCL、前端审核台 ocean 列。

---

## File Structure

- **Modify** `backend/app/services/step1_rates/sheet_builder/orchestrator.py` — `_normalize_sea` 保留结构化字段(Task 1)
- **Modify** `backend/app/services/step1_rates/sheet_builder/db_writer.py` — 新增 `commit_ocean_rows` + `OceanCommitResult` + helpers(Task 2)
- **Modify** `backend/app/services/step2_bidding/rate_repository.py` — 实现 `query_ocean_fcl` + `_ocean_to_step1_row`(Task 3)
- **Modify** `backend/app/services/step2_bidding/protocols.py` — `query_ocean_fcl` 协议签名(Task 3)
- **Modify** `backend/app/services/step2_bidding/customer_profiles/nitori.py` — `match` 优先 DB、回退 cost-book(Task 4)
- **Modify** `backend/app/services/step2_bidding/bidding_orchestrator.py` — `_run_nitori` 注入 repo(Task 5)
- **Modify** `backend/app/api/v1/rate_sheet.py` — `/commit` 端点按行形状分流 ocean(Task 5)
- **Create** `backend/tests/sheet_builder/test_ocean_writer.py`(Task 2)
- **Create** `backend/tests/services/step2_bidding/test_rate_repository_ocean.py`(Task 3)
- **Create** `backend/tests/services/step2_bidding/test_nitori_ocean_db.py`(Task 4)
- **Modify** `backend/tests/sheet_builder/test_orchestrator.py`(Task 1 追加用例)
- **Modify** `backend/tests/api_v1/test_rate_sheet_commit.py`(Task 5 追加用例)
- **Create** `backend/tests/services/step2_bidding/test_ocean_chain_e2e.py`(Task 6)

> 所有 pytest 命令在 `backend/` 目录下执行。提交信息中文 + 结尾附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`（下文 commit 步骤已省略该行，提交时补上）。

---

### Task 1: `_normalize_sea` 保留结构化箱型/船司/transit/origin

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/orchestrator.py:170-181`
- Test: `backend/tests/sheet_builder/test_orchestrator.py`（追加）

- [ ] **Step 1: 写失败测试**（追加到 `test_orchestrator.py` 末尾）

```python
from decimal import Decimal
from app.services.step1_rates.sheet_builder.orchestrator import _normalize_sea


def test_normalize_sea_preserves_container_breakdown_and_origin():
    row = {
        "destination_port_name": "HONG KONG",
        "carrier_name": "KMTC",
        "container_20gp": Decimal("250"),
        "container_40gp": Decimal("500"),
        "container_40hq": Decimal("520"),
        "transit_days": 3,
        "remarks": "直达",
    }
    out = _normalize_sea(row, "FALLBACK")
    assert out["origin"] == "SHANGHAI"            # 起运港按文件，默认上海
    assert out["destination"] == "HONG KONG"
    assert out["carrier"] == "KMTC"
    assert out["container_20gp"] == Decimal("250")
    assert out["container_40gp"] == Decimal("500")
    assert out["container_40hq"] == Decimal("520")
    assert out["transit_days"] == 3
    # 兼容旧前端 sea 预览列仍在
    assert out["freight_20"] == Decimal("250")
    assert out["freight_40"] == Decimal("500")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py::test_normalize_sea_preserves_container_breakdown_and_origin -v`
Expected: FAIL — KeyError `'origin'`（现 `_normalize_sea` 无该键）

- [ ] **Step 3: 改 `_normalize_sea`**（替换 orchestrator.py:170-181 整个函数体）

```python
def _normalize_sea(row: dict[str, Any], carrier_fallback: str) -> dict[str, Any]:
    c20 = row.get("container_20gp")
    c40gp = row.get("container_40gp")
    c40hq = row.get("container_40hq")
    return {
        # 起运港按文件，默认上海（Sea Net Rate 模板 From: Shanghai）
        "origin": row.get("origin_port_name") or "SHANGHAI",
        "destination": row.get("destination_port_name") or row.get("destination"),
        "carrier": row.get("carrier_name") or carrier_fallback,
        # 结构化箱型价：入库 FreightRate 用，不再合并丢失
        "container_20gp": c20,
        "container_40gp": c40gp,
        "container_40hq": c40hq,
        "transit_days": row.get("transit_days"),
        # 兼容前端现有 sea 预览列
        "freight_20": c20,
        "freight_40": c40gp or c40hq,
        "lss_cic": row.get("lss_20") or row.get("lss_40"),
        "baf": row.get("baf_20") or row.get("baf_40"),
        "transit": row.get("transit_days"),
        "remark": row.get("remarks"),
        "source_file": row.get("source_file"),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_orchestrator.py -v`
Expected: PASS（含原有用例不回归）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/orchestrator.py backend/tests/sheet_builder/test_orchestrator.py
git commit -m "feat(step1): 海运归一行保留结构化箱型/船司/transit/起运港"
```

---

### Task 2: `commit_ocean_rows` → 写 FreightRate

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/db_writer.py`
- Test: `backend/tests/sheet_builder/test_ocean_writer.py`（新建）

- [ ] **Step 1: 写失败测试**（新建 `test_ocean_writer.py`）

```python
"""做表海运行 → 入库 FreightRate(commit_ocean_rows)。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.models.port import Port
from app.services.step1_rates.sheet_builder import db_writer


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401 注册全部模型

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="CNSHA", name_en="SHANGHAI", name_cn="上海"),
        Port(un_locode="HKHKG", name_en="HONG KONG", name_cn="香港"),
        Carrier(code="KMTC", name_en="KOREA MARINE TRANSPORT", name_cn="高丽海运"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _row(dest, c20, c40hq, carrier="KMTC"):
    return {
        "origin": "SHANGHAI", "destination": dest, "carrier": carrier,
        "container_20gp": c20, "container_40gp": None, "container_40hq": c40hq,
        "transit_days": 3, "remark": "直达",
    }


def test_commit_ocean_writes_freightrate(db_session):
    res = db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("250"), Decimal("500"))], db_session)
    assert res.fcl_rows == 1
    fr = db_session.execute(select(FreightRate)).scalars().one()
    assert fr.container_20gp == Decimal("250")
    assert fr.container_40hq == Decimal("500")
    assert fr.status == RateStatus.active
    assert fr.currency == "USD"
    sha = db_session.execute(select(Port).where(Port.un_locode == "CNSHA")).scalars().one()
    hkg = db_session.execute(select(Port).where(Port.un_locode == "HKHKG")).scalars().one()
    km = db_session.execute(select(Carrier).where(Carrier.code == "KMTC")).scalars().one()
    assert fr.origin_port_id == sha.id
    assert fr.destination_port_id == hkg.id
    assert fr.carrier_id == km.id
    batch = db_session.execute(select(ImportBatch)).scalars().one()
    assert batch.file_type == ImportBatchFileType.ocean
    assert batch.status == ImportBatchStatus.active
    assert batch.row_count == 1


def test_commit_ocean_skips_unresolved_and_no_price(db_session):
    rows = [
        _row("HONG KONG", Decimal("250"), Decimal("500")),          # ok
        _row("NOWHERE PORT", Decimal("100"), Decimal("200")),       # 目的港解析不到
        {"origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC"},  # 无箱型价
    ]
    res = db_writer.commit_ocean_rows(rows, db_session)
    assert res.fcl_rows == 1
    assert res.skipped_unresolved == 1
    assert res.skipped_no_price == 1


def test_commit_ocean_supersedes_prior_active(db_session):
    db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("250"), Decimal("500"))], db_session)
    res2 = db_writer.commit_ocean_rows([_row("HONG KONG", Decimal("240"), Decimal("480"))], db_session)
    batches = db_session.execute(
        select(ImportBatch).where(ImportBatch.file_type == ImportBatchFileType.ocean)
    ).scalars().all()
    actives = [b for b in batches if b.status == ImportBatchStatus.active]
    superseded = [b for b in batches if b.status == ImportBatchStatus.superseded]
    assert len(actives) == 1 and str(actives[0].batch_id) == res2.batch_id
    assert len(superseded) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_writer.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'commit_ocean_rows'`

- [ ] **Step 3: 实现 `commit_ocean_rows`**（追加到 `db_writer.py`）

在文件顶部 import 区追加：
```python
from decimal import Decimal

from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus, SourceType
from app.services.step1_rates.activator_mappers import _resolve_port
```

在文件末尾追加：
```python
@dataclass
class OceanCommitResult:
    """海运入库结果。fcl_rows=0 时不建批次，batch_id 为空串。"""

    batch_id: str
    fcl_rows: int
    skipped_no_price: int
    skipped_unresolved: int


_OCEAN_PRICE_KEYS = ("container_20gp", "container_40gp", "container_40hq")


def commit_ocean_rows(
    rows: list[dict[str, Any]],
    db: Session,
    *,
    source_file: str | None = None,
    imported_by: str | None = None,
) -> OceanCommitResult:
    """审核后的海运行入库 FreightRate(FCL)；无箱型价/港口船司解析不到的行跳过计数。

    只写 active；新批次 supersede 上一个 active 的 ocean 批(与 air_tier 套路一致)。
    """
    priced = [r for r in rows if any(r.get(k) is not None for k in _OCEAN_PRICE_KEYS)]
    skipped_no_price = len(rows) - len(priced)
    if not priced:
        return OceanCommitResult(batch_id="", fcl_rows=0, skipped_no_price=skipped_no_price, skipped_unresolved=0)

    db.execute(
        update(ImportBatch)
        .where(
            ImportBatch.file_type == ImportBatchFileType.ocean,
            ImportBatch.status == ImportBatchStatus.active,
        )
        .values(status=ImportBatchStatus.superseded)
    )

    batch_uuid = uuid.uuid4()
    batch = ImportBatch(
        batch_id=batch_uuid,
        file_type=ImportBatchFileType.ocean,
        source_file=source_file,
        status=ImportBatchStatus.active,
        imported_by=imported_by,
    )
    db.add(batch)

    written = 0
    skipped_unresolved = 0
    for r in priced:
        origin_port = _resolve_port(db, r.get("origin") or "SHANGHAI")
        dest_port = _resolve_port(db, r.get("destination"))
        carrier_id = _resolve_carrier_id(db, r.get("carrier"))
        if origin_port is None or dest_port is None or carrier_id is None:
            skipped_unresolved += 1
            continue
        db.add(
            FreightRate(
                carrier_id=carrier_id,
                origin_port_id=origin_port.id,
                destination_port_id=dest_port.id,
                container_20gp=_to_decimal(r.get("container_20gp")),
                container_40gp=_to_decimal(r.get("container_40gp")),
                container_40hq=_to_decimal(r.get("container_40hq")),
                transit_days=_to_int(r.get("transit_days")),
                currency="USD",
                status=RateStatus.active,
                source_type=SourceType.excel,
                source_file=source_file or r.get("source_file"),
                remarks=r.get("remark"),
                batch_id=batch_uuid,
            )
        )
        written += 1

    batch.row_count = written
    db.commit()
    return OceanCommitResult(
        batch_id=str(batch_uuid),
        fcl_rows=written,
        skipped_no_price=skipped_no_price,
        skipped_unresolved=skipped_unresolved,
    )


def _resolve_carrier_id(db: Session, name: Any) -> int | None:
    """宽松解析船司 → id(查不到返回 None，不抛异常)。"""
    if not name:
        return None
    n = str(name).strip()
    c = db.query(Carrier).filter(Carrier.code == n).first()
    if c is None:
        c = db.query(Carrier).filter(Carrier.name_en.ilike(f"%{n}%")).first()
    if c is None:
        c = db.query(Carrier).filter(Carrier.code.ilike(f"%{n}%")).first()
    return c.id if c else None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/sheet_builder/test_ocean_writer.py -v`
Expected: PASS（3 用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/db_writer.py backend/tests/sheet_builder/test_ocean_writer.py
git commit -m "feat(step1): 海运做表行入库 FreightRate(commit_ocean_rows，解析港口/船司+supersede)"
```

---

### Task 3: `query_ocean_fcl` 只读查 active FreightRate

**Files:**
- Modify: `backend/app/services/step2_bidding/rate_repository.py:181-183`（替换 stub）+ 顶部 import + 末尾加 converter
- Modify: `backend/app/services/step2_bidding/protocols.py:77`
- Test: `backend/tests/services/step2_bidding/test_rate_repository_ocean.py`（新建）

- [ ] **Step 1: 写失败测试**（新建 `test_rate_repository_ocean.py`）

```python
"""query_ocean_fcl：按 origin/dest 查 active FreightRate → Step1RateRow。"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.freight_rate import FreightRate, RateStatus
from app.models.import_batch import ImportBatch, ImportBatchFileType, ImportBatchStatus
from app.models.port import Port
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="CNSHA", name_en="SHANGHAI"),
        Port(un_locode="HKHKG", name_en="HONG KONG"),
        Carrier(code="KMTC", name_en="KOREA MARINE TRANSPORT"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_rate(s, status=ImportBatchStatus.active, c20=Decimal("250"), c40hq=Decimal("500")):
    sha = s.query(Port).filter_by(un_locode="CNSHA").one()
    hkg = s.query(Port).filter_by(un_locode="HKHKG").one()
    km = s.query(Carrier).filter_by(code="KMTC").one()
    bid = uuid.uuid4()
    s.add(ImportBatch(batch_id=bid, file_type=ImportBatchFileType.ocean, status=status))
    s.add(FreightRate(
        carrier_id=km.id, origin_port_id=sha.id, destination_port_id=hkg.id,
        container_20gp=c20, container_40hq=c40hq, transit_days=3,
        currency="USD", status=RateStatus.active, batch_id=bid,
    ))
    s.commit()


def test_query_ocean_fcl_returns_active_rate(db_session):
    _seed_rate(db_session)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="HONG KONG")
    assert len(rows) == 1
    r = rows[0]
    assert r.container_20gp == Decimal("250")
    assert r.container_40hq == Decimal("500")
    assert r.carrier_name == "KOREA MARINE TRANSPORT"
    assert r.transit_days == 3
    assert r.record_kind == "ocean_fcl"


def test_query_ocean_fcl_excludes_superseded(db_session):
    _seed_rate(db_session, status=ImportBatchStatus.superseded)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="HONG KONG")
    assert rows == []


def test_query_ocean_fcl_unresolved_port_returns_empty(db_session):
    _seed_rate(db_session)
    rows = Step1RateRepository(db_session).query_ocean_fcl(origin="SHANGHAI", destination="NOWHERE")
    assert rows == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step2_bidding/test_rate_repository_ocean.py -v`
Expected: FAIL — `NotImplementedError: query_ocean_fcl 将于 v2.0 实现`

- [ ] **Step 3: 实现 `query_ocean_fcl`**

3a. 顶部 import 区追加（rate_repository.py:23 附近）：
```python
from app.models.freight_rate import FreightRate
```

3b. 替换 `query_ocean_fcl` stub（rate_repository.py:181-183）：
```python
    def query_ocean_fcl(
        self,
        *,
        origin: str,
        destination: str,
        effective_on: date | None = None,
        currency: str | None = None,
    ) -> list[Step1RateRow]:
        """查 origin → destination 的 FCL 海运运价(做表入库的 active ocean 批)。

        - origin/destination 是文字(如 'SHANGHAI'/'HONG KONG')，先经 _resolve_port 解析为 port_id 再按 id 精确匹配
        - 仅 active 批次；解析不到任一港口 → 返回空
        """
        from app.services.step1_rates.activator_mappers import _resolve_port

        o = _resolve_port(self._db, origin)
        d = _resolve_port(self._db, destination)
        if o is None or d is None:
            return []
        stmt = (
            select(FreightRate, ImportBatch)
            .join(ImportBatch, FreightRate.batch_id == ImportBatch.batch_id)
            .where(
                and_(
                    ImportBatch.status == ImportBatchStatus.active,
                    FreightRate.origin_port_id == o.id,
                    FreightRate.destination_port_id == d.id,
                )
            )
        )
        if currency is not None:
            stmt = stmt.where(FreightRate.currency == currency)
        rows = self._db.execute(stmt).all()
        return [self._ocean_to_step1_row(rate, batch) for rate, batch in rows]
```

3c. 在 Converters 区（`_surcharge_to_step1_row` 之后）追加：
```python
    @staticmethod
    def _ocean_to_step1_row(rate: FreightRate, batch: ImportBatch) -> Step1RateRow:
        return Step1RateRow(
            carrier_id=rate.carrier_id,
            carrier_name=rate.carrier.name_en if rate.carrier else None,
            origin_port_id=rate.origin_port_id,
            destination_port_id=rate.destination_port_id,
            container_20gp=_as_decimal(rate.container_20gp),
            container_40gp=_as_decimal(rate.container_40gp),
            container_40hq=_as_decimal(rate.container_40hq),
            container_45=_as_decimal(rate.container_45),
            transit_days=rate.transit_days,
            transit_time_text=rate.transit_time_text,
            record_kind="ocean_fcl",
            currency=rate.currency or "USD",
            remarks=rate.remarks,
            source_type=RateSourceKind.excel.value,
            source_file=batch.source_file,
            upload_batch_id=str(batch.batch_id),
            extras={
                "step2_record_id": rate.id,
                "step2_batch_status": batch.status.value
                if hasattr(batch.status, "value")
                else str(batch.status),
            },
        )
```

3d. 更新协议 `protocols.py:77`：
```python
    def query_ocean_fcl(
        self,
        *,
        origin: str,
        destination: str,
        effective_on: date | None = None,
        currency: str | None = None,
    ) -> list["Step1RateRow"]: ...
```

- [ ] **Step 4: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step2_bidding/test_rate_repository_ocean.py -v`
Expected: PASS（3 用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step2_bidding/rate_repository.py backend/app/services/step2_bidding/protocols.py backend/tests/services/step2_bidding/test_rate_repository_ocean.py
git commit -m "feat(step2): 实现 query_ocean_fcl(按港口查 active FreightRate→Step1RateRow)"
```

---

### Task 4: `NitoriProfile.match` 优先查 DB、回退 cost-book

**Files:**
- Modify: `backend/app/services/step2_bidding/customer_profiles/nitori.py:19,28-31,74-100`
- Test: `backend/tests/services/step2_bidding/test_nitori_ocean_db.py`（新建）

- [ ] **Step 1: 写失败测试**（新建 `test_nitori_ocean_db.py`）

```python
"""NitoriProfile.match 优先查 DB(repo.query_ocean_fcl)，按箱型取价。"""
from __future__ import annotations

from decimal import Decimal

from app.services.step1_rates.entities import Step1RateRow
from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
from app.services.step2_bidding.entities import (
    CostType, ParsedPkg, PkgRow, PkgSection, RowStatus,
)


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows

    def query_ocean_fcl(self, *, origin, destination, effective_on=None, currency=None):
        return self._rows


def _pkg(size):
    row = PkgRow(
        row_idx=9, section_index=0, section_code="GLOBAL",
        origin_code="SHANGHAI", origin_text_raw="SHANGHAI",
        destination_text_raw="HONG KONG", destination_code="HONGKONG",
        cost_type=CostType.UNKNOWN, currency="USD",
        volume_desc=None, existing_price=None, existing_lead_time=None,
        existing_carrier=None, existing_remark=None, is_example=False,
        client_constraint_text=None,
        extras={"size": size, "pod_raw": "HONG KONG", "is_china": True},
    )
    section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
    return ParsedPkg(
        bid_id="b", customer_code="nitori", period="x", sheet_name="s",
        source_file="f", sections=[section], rows=[row], warnings=[],
    )


def _rate():
    return Step1RateRow(
        carrier_name="KMTC", container_20gp=Decimal("250"),
        container_40hq=Decimal("500"), transit_days=3, record_kind="ocean_fcl",
    )


def test_nitori_match_uses_db_40hc():
    rep = NitoriProfile(repo=_FakeRepo([_rate()])).match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.FILLED
    assert rep.cost_price == Decimal("500")        # 40HC→container_40hq
    assert rep.sell_price == Decimal("575")        # 500×1.15
    assert rep.carrier_text == "KMTC"


def test_nitori_match_uses_db_20f():
    rep = NitoriProfile(repo=_FakeRepo([_rate()])).match(_pkg("20F"))[0]
    assert rep.cost_price == Decimal("250")        # 20F→container_20gp


def test_nitori_match_no_rate_when_db_empty_and_no_costbook():
    rep = NitoriProfile(repo=_FakeRepo([])).match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.NO_RATE
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/services/step2_bidding/test_nitori_ocean_db.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'repo'`

- [ ] **Step 3: 改 `nitori.py`**

3a. 在常量区（nitori.py:19 后）追加：
```python
_SIZE_TO_CONTAINER = {"20F": "container_20gp", "40HC": "container_40hq", "40F": "container_40hq"}  # 40HC=40HQ
```

3b. 改 `__init__`（nitori.py:28-30）：
```python
    def __init__(self, cost_book: NitoriCostBook | None = None,
                 markup_ratio: Decimal = _MARKUP, repo=None):
        self._cost = cost_book
        self._markup = markup_ratio
        self._repo = repo
```

3c. 替换 `match`（nitori.py:74-100 整个方法）+ 加两个私有 helper：
```python
    def match(self, parsed: ParsedPkg) -> list[PerRowReport]:
        reports: list[PerRowReport] = []
        for row in parsed.rows:
            if not row.extras.get("is_china"):
                continue
            size = row.extras.get("size", "")
            cost_price, carrier_text, lead = self._match_from_db(row, size)
            if cost_price is None and self._cost is not None:
                cost_price, carrier_text, lead = self._match_from_cost_book(row, size)
            if cost_price is None:
                reports.append(PerRowReport(
                    row_idx=row.row_idx, section_code="GLOBAL",
                    destination_code=row.destination_code, status=RowStatus.NO_RATE,
                    cost_price=None, sell_price=None, markup_ratio=None,
                    lead_time_text=None, carrier_text=None, remark_text=None,
                    selected_candidate=None))
                continue
            sell = (cost_price * self._markup).quantize(Decimal("1"))
            reports.append(PerRowReport(
                row_idx=row.row_idx, section_code="GLOBAL",
                destination_code=row.destination_code, status=RowStatus.FILLED,
                cost_price=cost_price, sell_price=sell, markup_ratio=self._markup,
                lead_time_text=lead, carrier_text=carrier_text,
                remark_text=None, selected_candidate=None))
        return reports

    def _match_from_db(self, row, size):
        """优先：查 DB 运价(福山确认的口径)。返回 (cost_price, carrier, lead) 或 (None,None,None)。"""
        if self._repo is None:
            return None, None, None
        cands = self._repo.query_ocean_fcl(origin=row.origin_code, destination=row.destination_code)
        if not cands:
            return None, None, None
        cand = cands[0]  # MVP：取第一条；多候选筛选福山验收再加
        col = _SIZE_TO_CONTAINER.get(size)
        price = getattr(cand, col) if col else None
        if price is None:
            return None, None, None
        lead = cand.transit_time_text or (str(cand.transit_days) if cand.transit_days is not None else None)
        return price, cand.carrier_name, lead

    def _match_from_cost_book(self, row, size):
        """回退：zip 内成本文件(MVP 兜底；福山验收后或移除)。"""
        lane = self._cost.lookup(pol=row.origin_code, pod=row.destination_code)
        cost_field = _SIZE_TO_COST.get(size)
        if not lane or lane.no_service or not cost_field:
            return None, None, None
        price = getattr(lane, f"rate_{cost_field}")
        if price is None:
            return None, None, None
        return price, lane.carrier, lane.transit_time
```

- [ ] **Step 4: 跑测试确认通过 + 不回归旧 Nitori 测试**

Run: `../.venv/bin/python -m pytest tests/services/step2_bidding/test_nitori_ocean_db.py tests/services/step2_bidding/test_nitori_profile.py -v`
Expected: PASS（新 3 用例 + 旧 cost-book 用例：旧用例 `NitoriProfile(cost_book=...)` 无 repo → `_match_from_db` 返回 None → 回退 cost-book → 行为不变）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step2_bidding/customer_profiles/nitori.py backend/tests/services/step2_bidding/test_nitori_ocean_db.py
git commit -m "feat(step2): Nitori match 优先查 DB 运价、查不到回退 cost-book"
```

---

### Task 5: 接线 `_run_nitori` 注入 repo + `/commit` 端点分流 ocean

**Files:**
- Modify: `backend/app/services/step2_bidding/bidding_orchestrator.py:85,153,159`
- Modify: `backend/app/api/v1/rate_sheet.py`（`/commit` 端点 + import db_writer 已在）
- Test: `backend/tests/api_v1/test_rate_sheet_commit.py`（追加 ocean 分流用例）

- [ ] **Step 1: 写失败测试**（追加到 `test_rate_sheet_commit.py`）

```python
def _new_sea_session(client: TestClient) -> str:
    r = client.post("/api/v1/rate-sheet/session", data={"template_type": "sea"})
    assert r.status_code == 200
    return r.json()["data"]["session_id"]


def test_commit_dispatches_ocean_path(client):
    sid = _new_sea_session(client)
    rows = [{"origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC",
             "container_20gp": 250, "container_40hq": 500, "transit_days": 3}]
    r = client.post(f"/api/v1/rate-sheet/{sid}/commit", json={"rows": rows})
    assert r.status_code == 200
    data = r.json()["data"]
    assert "fcl_rows" in data                    # 走了 ocean 分流
    assert data["skipped_unresolved"] == 1       # 测试 DB 未 seed 港口/船司 → 解析不到
```

- [ ] **Step 2: 跑测试确认失败**

Run: `../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_commit.py::test_commit_dispatches_ocean_path -v`
Expected: FAIL — `KeyError: 'fcl_rows'`（现 `/commit` 只走 tier，返回 `tier_rows`）

- [ ] **Step 3a: 改 `/commit` 端点分流**（rate_sheet.py，替换 `commit_rate_sheet` 函数体）

```python
@router.post("/{session_id}/commit")
def commit_rate_sheet(
    session_id: str, body: DownloadRequest, db: Session = Depends(get_db)
):
    """审核后的「勾选+编辑」行直接入库(save-from-session)。

    按行形状分流：含箱型价(container_*)→海运 FreightRate；否则→air_tier。
    """
    try:
        orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    rows = body.rows
    if any(_has_ocean_price(r) for r in rows):
        ocean = db_writer.commit_ocean_rows(rows, db)
        return ApiResponse(data={
            "batch_id": ocean.batch_id,
            "fcl_rows": ocean.fcl_rows,
            "skipped_no_price": ocean.skipped_no_price,
            "skipped_unresolved": ocean.skipped_unresolved,
        })

    result = db_writer.commit_tier_rows(rows, db)
    return ApiResponse(data={
        "batch_id": result.batch_id,
        "tier_rows": result.tier_rows,
        "skipped_weekly": result.skipped_weekly,
    })


def _has_ocean_price(r: dict) -> bool:
    return any(r.get(k) is not None for k in ("container_20gp", "container_40gp", "container_40hq"))
```

- [ ] **Step 3b: 接线 `_run_nitori` 注入 repo**（bidding_orchestrator.py）

改 caller（line 85）：
```python
    if identify_result.matched_customer == "nitori":
        return _run_nitori(input_path, bid_id, bid_dir, identify_block, db)
```
改签名（line 153）：
```python
def _run_nitori(input_path, bid_id, bid_dir, identify_block, db):
```
改 NitoriProfile 构造（line 159，`Step1RateRepository` 已在 line 43 import）：
```python
    profile = NitoriProfile(
        cost_book=NitoriCostBook.from_xlsx(cost_path),
        repo=Step1RateRepository(db),
    )
```

- [ ] **Step 4: 跑测试确认通过 + 不回归**

Run: `../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_commit.py tests/services/step2_bidding/ -v`
Expected: PASS（新 ocean 分流用例 + 原 air commit 用例 + 原 Nitori 集成用例：`_run_nitori` 传入空 DB → `query_ocean_fcl` 返回 [] → Nitori 回退 cost-book → 原结果不变）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/rate_sheet.py backend/app/services/step2_bidding/bidding_orchestrator.py backend/tests/api_v1/test_rate_sheet_commit.py
git commit -m "feat(step2): /commit 端点分流海运入库 + _run_nitori 注入 repo"
```

---

### Task 6: 端到端链路测试（commit → query → Nitori 取价）

**Files:**
- Test: `backend/tests/services/step2_bidding/test_ocean_chain_e2e.py`（新建）

- [ ] **Step 1: 写端到端测试**

```python
"""海运闭环：commit_ocean_rows → query_ocean_fcl → NitoriProfile.match。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.carrier import Carrier
from app.models.port import Port
from app.services.step1_rates.sheet_builder import db_writer
from app.services.step2_bidding.customer_profiles.nitori import NitoriProfile
from app.services.step2_bidding.entities import (
    CostType, ParsedPkg, PkgRow, PkgSection, RowStatus,
)
from app.services.step2_bidding.rate_repository import Step1RateRepository


@pytest.fixture()
def db_session():
    import app.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = Session(bind=engine)
    s.add_all([
        Port(un_locode="CNSHA", name_en="SHANGHAI"),
        Port(un_locode="HKHKG", name_en="HONG KONG"),
        Carrier(code="KMTC", name_en="KOREA MARINE TRANSPORT"),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _pkg(size):
    row = PkgRow(
        row_idx=9, section_index=0, section_code="GLOBAL",
        origin_code="SHANGHAI", origin_text_raw="SHANGHAI",
        destination_text_raw="HONG KONG", destination_code="HONG KONG",
        cost_type=CostType.UNKNOWN, currency="USD",
        volume_desc=None, existing_price=None, existing_lead_time=None,
        existing_carrier=None, existing_remark=None, is_example=False,
        client_constraint_text=None,
        extras={"size": size, "pod_raw": "HONG KONG", "is_china": True},
    )
    section = PkgSection(0, "GLOBAL", 6, "CHINA", "CN", "USD", "", False, [])
    return ParsedPkg(bid_id="b", customer_code="nitori", period="x", sheet_name="s",
                     source_file="f", sections=[section], rows=[row], warnings=[])


def test_ocean_chain_commit_query_nitori(db_session):
    # 1. 入库（模拟做表归一行）
    res = db_writer.commit_ocean_rows([{
        "origin": "SHANGHAI", "destination": "HONG KONG", "carrier": "KMTC",
        "container_20gp": Decimal("250"), "container_40hq": Decimal("500"), "transit_days": 3,
    }], db_session)
    assert res.fcl_rows == 1

    # 2. 查 + Nitori 取价
    profile = NitoriProfile(repo=Step1RateRepository(db_session))
    rep = profile.match(_pkg("40HC"))[0]
    assert rep.status == RowStatus.FILLED
    assert rep.cost_price == Decimal("500")
    assert rep.sell_price == Decimal("575")
    assert rep.carrier_text == "KOREA MARINE TRANSPORT"
```

- [ ] **Step 2: 跑测试确认通过**

Run: `../.venv/bin/python -m pytest tests/services/step2_bidding/test_ocean_chain_e2e.py -v`
Expected: PASS

- [ ] **Step 3: 全量回归**

Run: `../.venv/bin/python -m pytest -q`
Expected: 全绿（仅既有 3 个 `test_ai_client` vLLM 环境失败无关）

- [ ] **Step 4: 提交**

```bash
git add backend/tests/services/step2_bidding/test_ocean_chain_e2e.py
git commit -m "test(step2): 海运闭环端到端(commit→query→Nitori 取价)"
```

- [ ] **Step 5: 手动真实验证（非自动化，可选）**

启动后端后，对真实 Nitori 投标包 zip 跑 `/auto-fill`，确认海运段命中 DB 运价（需先用真实 Sea 元料金做表→/commit 入库 FreightRate）。命令参考：
```bash
curl -s --noproxy '*' -F "file=@资料/2026.04.02/.../Nitori.zip" http://127.0.0.1:8000/api/v1/bidding/auto-fill
```

---

## Self-Review

**Spec coverage:** ①复用 FreightRate ✓(Task 2/3)；②Nitori 倒逼范围 ✓(只 Shanghai/Nitori lane)；③USD ✓(commit/query 固定 USD)；④多起运港只取上海 ✓(_normalize_sea 默认 SHANGHAI)；⑤40HC→40hq ✓(_SIZE_TO_CONTAINER)。defer 项(Arbitrary/PDF/全附加费/CNY/LCL/前端 ocean 列)均未触碰 ✓。

**Placeholder scan:** 无 TBD/TODO；每步含完整代码与命令 ✓。

**Type consistency:** `commit_ocean_rows`→`OceanCommitResult(batch_id,fcl_rows,skipped_no_price,skipped_unresolved)` 全程一致；`query_ocean_fcl` 返回 `Step1RateRow`(container_20gp/40hq/carrier_name/transit_days/record_kind="ocean_fcl")，Nitori `_match_from_db` 用 `getattr(cand, "container_40hq")` 与之对齐；`_SIZE_TO_CONTAINER` 值即 Step1RateRow/FreightRate 列名 ✓。

**回归保护:** Nitori `match` 保留 cost-book 回退 → 旧 Nitori 测试(无 repo / 空 DB)行为不变；`/commit` 按行形状分流 → 旧 air tier commit 用例(tier_prices 行无 container)不受影响。
