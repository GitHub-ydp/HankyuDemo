# 统一运价入库口 — Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做表页停止入库、只产表；三类运价（海运 FCL / 空运周报 / 空运档位）均可从「运价导入页」无损回流落库。

**Architecture:** 复用既有 `draft → activate` 管道。净新增空运档位（air_tier）导入适配器塞进同一管道；给生成的运价表补齐 DB 字段列（含海运 40GP/40HQ 拆 3 行）；扩展 OceanAdapter 按表头读新海运列；最后才拆除做表页第二入库口（保证拆除时回流路径已就位、无空档）。

**Tech Stack:** Python 3.10 + SQLAlchemy 2.0 + openpyxl + pytest（后端）；React 19 + TS + AntD v6（前端）。

**关键已验证事实（实现时可直接依赖）：**
- `OceanAdapter._normalize_container_type` **已**把 `40GP→"40ft"`、`40HQ→"40hq"` 区分映射；`_merge_40_payload` 已按类型分别写 `container_40gp`/`container_40hq`；`_append_pending_record` 的交叉填充仅在某一侧为 None 时触发。→ **海运 40GP/40HQ 拆分只需模板改成发 3 行，解析器无需改逻辑**，由 round-trip 测试把关。
- OceanAdapter 按**表头文本**自动发现列（`_build_fcl_column_map`），不依赖 `template_registry`。→ 新增海运列只要在生成表的表头行写出对应中/英文标签，并在 `_build_fcl_column_map` 加识别分支即可。
- `AirTierRate` 用字符串存 origin/destination/carrier，**无需港口/船司字典解析**，air_tier mapper 不会抛 PORT/CARRIER_NOT_FOUND。
- `ImportBatchFileType.air_tier` 枚举**已存在**，无需 alembic 迁移。
- 适配器注册表 `RateAdapterRegistry` 按 `priority` **升序**取第一个 `detect()` 命中者；现有优先级 air=10 / ocean=20 / ocean_ngb=30。air_tier 必须设 `priority < 10` 且 detect 走表头内容判定。

**通用约定：**
- 后端测试命令：`cd backend && ../.venv/bin/python -m pytest <路径> -v`
- 后端运行根目录始终在 `backend/`（否则 `.env` 不加载）。
- 注释 / commit message 用中文。

**生成档位表「表头契约」（Task 5 生产者与 Task 3 消费者共用，不可走样）：**
第 1 行表头依次为：
`["Origin (POL)", "Destination", "Service", <每个档位一列 "{kg}KG"（按 KG 升序）>, "Currency", "Effective From", "Effective To", "Carrier", "Cargo Class", "Packing", "Density", "Remark"]`

**生成海运表「列契约」（Task 7 生产者与 Task 8 消费者共用）：**
在原 `sea_blank.xlsx` 列基础上新增（1-based 列号，供 openpyxl 填充器用）：
`currency=18, valid_from=19, valid_to=20, rate_level=21, service_code=22`；表头行（第 8 行）对应写英文标签 `Currency / Valid From / Valid To / Rate Level / Service Code`。每条运价发 3 行：`("20FT","container_20gp"), ("40GP","container_40gp"), ("40HQ","container_40hq")`，3 行都重复写 目的港/船司/上述元数据列。

---

## Task 1: 给 Step1FileType 增加 air_tier

**Files:**
- Modify: `backend/app/services/step1_rates/entities.py:18-21`

- [ ] **Step 1: 写失败测试**

Create: `backend/tests/services/step1_rates/test_air_tier_enum.py`
```python
from app.services.step1_rates.entities import Step1FileType


def test_air_tier_file_type_exists():
    assert Step1FileType("air_tier") is Step1FileType.air_tier
    assert Step1FileType.air_tier.value == "air_tier"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_enum.py -v`
Expected: FAIL（`ValueError: 'air_tier' is not a valid Step1FileType`）

- [ ] **Step 3: 实现**

`entities.py` 的 `Step1FileType` 增加一行：
```python
class Step1FileType(str, Enum):
    air = "air"
    air_tier = "air_tier"
    ocean = "ocean"
    ocean_ngb = "ocean_ngb"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_enum.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/entities.py backend/tests/services/step1_rates/test_air_tier_enum.py
git commit -m "feat(step1): Step1FileType 增加 air_tier 类型"
```

---

## Task 2: 空运档位入库映射器 to_air_tier_rate

**Files:**
- Modify: `backend/app/services/step1_rates/activator_mappers.py`（顶部 import + 新增函数）
- Test: `backend/tests/services/step1_rates/test_air_tier_mapper.py`

参照实现（即将删除的 `sheet_builder/db_writer.commit_tier_rows` 的字段映射）：origin 缺省 `PVG`、currency 缺省 `CNY`、tier_prices 键归一 int、值 float。

- [ ] **Step 1: 写失败测试**

```python
import uuid
from app.models import AirTierRate
from app.services.step1_rates.activator_mappers import to_air_tier_rate
from app.services.step1_rates.entities import ParsedRateRecord


def _rec() -> ParsedRateRecord:
    return ParsedRateRecord(
        record_kind="air_tier",
        origin_port_name="PVG",
        destination_port_name="NRT",
        service_desc="CA",
        currency="JPY",
        extras={
            "tier_prices": {"45": 17.0, "100": "14"},
            "cargo_class": "普货",
            "packing": "托",
            "density": "1:167",
            "carrier": "CA",
            "row_index": 2,
        },
    )


def test_to_air_tier_rate_maps_fields():
    rate = to_air_tier_rate(_rec(), uuid.uuid4())
    assert isinstance(rate, AirTierRate)
    assert rate.origin == "PVG"
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"
    assert rate.cargo_class == "普货"
    assert rate.carrier == "CA"
    # 键归 int、值归 float
    assert rate.tier_prices == {45: 17.0, 100: 14.0}


def test_to_air_tier_rate_defaults():
    # 注意：ParsedRateRecord 继承 Step1RateRow.currency 默认值 "USD"(非 None)，省略 currency
    # 得到的是 "USD" 而非空。真实回流中由 AirTierAdapter 对空币种格填 "CNY"；mapper 的
    # `or "CNY"` 是兜底层，故这里显式传 currency=None 来验证兜底。
    rec = ParsedRateRecord(
        record_kind="air_tier", currency=None, extras={"tier_prices": {"45": 10.0}}
    )
    rate = to_air_tier_rate(rec, uuid.uuid4())
    assert rate.origin == "PVG"        # 缺省起运港
    assert rate.destination == ""      # 缺省目的地
    assert rate.currency == "CNY"      # currency=None → 兜底 CNY
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_mapper.py -v`
Expected: FAIL（`ImportError: cannot import name 'to_air_tier_rate'`）

- [ ] **Step 3: 实现**

`activator_mappers.py` 顶部 import 增加 `AirTierRate`：
```python
from app.models import (
    AirFreightRate,
    AirSurcharge,
    AirTierRate,
    Carrier,
    FreightRate,
    LclRate,
    Port,
    RateStatus,
    SourceType,
)
```
新增函数（放在 `to_air_surcharge` 之后）：
```python
def to_air_tier_rate(record: ParsedRateRecord, batch_id: uuid.UUID) -> AirTierRate:
    """air_tier record → AirTierRate（无港口/船司字典依赖，origin/dest 存字符串）。"""
    extras = record.extras or {}
    raw_tiers = extras.get("tier_prices") or {}
    tier_prices = {
        int(kg): float(price)
        for kg, price in raw_tiers.items()
        if price is not None and str(price) != ""
    }
    return AirTierRate(
        origin=record.origin_port_name or "PVG",
        destination=record.destination_port_name or "",
        service_desc=record.service_desc,
        tier_prices=tier_prices,
        effective_from=record.valid_from,
        effective_to=record.valid_to,
        currency=record.currency or "CNY",
        remark=record.remarks,
        cargo_class=extras.get("cargo_class"),
        packing=extras.get("packing"),
        density=extras.get("density"),
        carrier=extras.get("carrier"),
        batch_id=batch_id,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_mapper.py -v`
Expected: PASS（2 个）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/activator_mappers.py backend/tests/services/step1_rates/test_air_tier_mapper.py
git commit -m "feat(step1): 新增 to_air_tier_rate 映射器(ParsedRateRecord→AirTierRate)"
```

---

> **评审修正（commit 18c1c79，已落地）**：非数字档位价用 `_safe_float` 跳过不炸整批；`col()` 去掉前缀回退只精确匹配；`parse` 落空补 warning + `wb.close()`；`_to_date` 支持 `YYYY/MM/DD` 并简化。下方原始代码为初版，最终代码以该 fix 提交为准。

## Task 3: 空运档位导入适配器 AirTierAdapter

**Files:**
- Create: `backend/app/services/step1_rates/adapters/air_tier.py`
- Modify: `backend/app/services/step1_rates/adapters/__init__.py`
- Test: `backend/tests/services/step1_rates/test_air_tier_adapter.py`

按「表头契约」识别与解析。detect 优先级 5（先于 air=10），按 sheet 内容判定，非档位文件安全返回 False。

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path
from openpyxl import Workbook
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.entities import Step1FileType


def _make_tier_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Air Rates 2026-06-01"
    header = ["Origin (POL)", "Destination", "Service", "45KG", "100KG",
              "Currency", "Effective From", "Effective To",
              "Carrier", "Cargo Class", "Packing", "Density", "Remark"]
    for c, label in enumerate(header, start=1):
        ws.cell(1, c).value = label
    ws.append(["PVG", "NRT", "CA", 17, 14, "JPY",
               "2026-06-01", "2026-06-07", "CA", "普货", "托", "1:167", "周一报价"])
    path = tmp_path / "air_tier_rate_sheet_filled.xlsx"
    wb.save(path)
    return path


def _make_ocean_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "JP N RATE FCL & LCL"
    path = tmp_path / "ocean_xx.xlsx"
    wb.save(path)
    return path


def test_detect_by_content(tmp_path):
    a = AirTierAdapter()
    assert a.detect(_make_tier_xlsx(tmp_path)) is True
    assert a.detect(_make_ocean_xlsx(tmp_path)) is False


def test_detect_by_hint(tmp_path):
    a = AirTierAdapter()
    assert a.detect(_make_ocean_xlsx(tmp_path), file_type_hint=Step1FileType.air_tier) is True


def test_parse_tier_rows(tmp_path):
    batch = AirTierAdapter().parse(_make_tier_xlsx(tmp_path), db=None)
    assert batch.file_type is Step1FileType.air_tier
    assert len(batch.records) == 1
    r = batch.records[0]
    assert r.record_kind == "air_tier"
    assert r.origin_port_name == "PVG"
    assert r.destination_port_name == "NRT"
    assert r.service_desc == "CA"
    assert r.currency == "JPY"
    assert str(r.valid_from) == "2026-06-01"
    assert r.extras["tier_prices"] == {45: 17.0, 100: 14.0}
    assert r.extras["cargo_class"] == "普货"
    assert r.extras["carrier"] == "CA"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_adapter.py -v`
Expected: FAIL（`ModuleNotFoundError: ...adapters.air_tier`）

- [ ] **Step 3: 实现**

Create `backend/app/services/step1_rates/adapters/air_tier.py`：
```python
"""Step1 空运重量档(air_tier)导入适配器。

解析「做表」生成的档位表（程序生成的统一格式，见表头契约），回流入 AirTierRate。
按 sheet 表头内容识别（不靠文件名——档位文件名常含 'air' 会被 AirAdapter 抢）。
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.services.step1_rates.entities import (
    ParsedRateBatch,
    ParsedRateRecord,
    Step1FileType,
)

_TIER_HEADER_RE = re.compile(r"^(\d+)\s*KG$", re.IGNORECASE)
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}


class AirTierAdapter:
    """识别并解析做表生成的空运重量档表。"""

    key = "air_tier"
    file_type = Step1FileType.air_tier
    priority = 5  # 必须先于 AirAdapter(10)

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        if file_type_hint is not None:
            return file_type_hint == self.file_type
        if path.suffix.lower() not in _EXCEL_EXTS:
            return False
        try:
            wb = load_workbook(path, data_only=True, read_only=True)
        except Exception:
            return False
        try:
            for ws in wb.worksheets:
                if self._tier_sheet_headers(ws) is not None:
                    return True
        finally:
            wb.close()
        return False

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        wb = load_workbook(path, data_only=True)
        records: list[ParsedRateRecord] = []
        for ws in wb.worksheets:
            headers = self._tier_sheet_headers(ws)
            if headers is None:
                continue
            records.extend(self._parse_sheet(ws, headers))
        return ParsedRateBatch(
            file_type=Step1FileType.air_tier,
            source_file=path.name,
            records=records,
            adapter_key=self.key,
        )

    def _tier_sheet_headers(self, ws) -> dict[str, Any] | None:
        """读第 1 行表头；命中档位表契约时返回 {name→col_index, "tiers":[(kg,col)]}，否则 None。"""
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not first_row:
            return None
        named: dict[str, int] = {}
        tiers: list[tuple[int, int]] = []
        for idx, cell in enumerate(first_row):
            text = str(cell).strip() if cell is not None else ""
            if not text:
                continue
            m = _TIER_HEADER_RE.match(text)
            if m:
                tiers.append((int(m.group(1)), idx))
            else:
                named[text.lower()] = idx
        has_origin = any(k.startswith("origin") for k in named)
        if has_origin and "destination" in named and tiers:
            return {"named": named, "tiers": tiers}
        return None

    def _parse_sheet(self, ws, headers: dict[str, Any]) -> list[ParsedRateRecord]:
        named: dict[str, int] = headers["named"]
        tiers: list[tuple[int, int]] = headers["tiers"]

        def col(*names: str) -> int | None:
            for n in names:
                if n in named:
                    return named[n]
            for key, idx in named.items():
                if key.startswith(names[0]):
                    return idx
            return None

        c_origin = col("origin (pol)", "origin")
        c_dest = col("destination")
        c_service = col("service")
        c_currency = col("currency")
        c_from = col("effective from")
        c_to = col("effective to")
        c_carrier = col("carrier")
        c_cargo = col("cargo class")
        c_pack = col("packing")
        c_density = col("density")
        c_remark = col("remark")

        out: list[ParsedRateRecord] = []
        for row_index, row in enumerate(
            ws.iter_rows(min_row=2, values_only=True), start=2
        ):
            def v(i: int | None) -> Any:
                return row[i] if i is not None and i < len(row) else None

            origin = v(c_origin)
            dest = v(c_dest)
            tier_prices: dict[int, float] = {}
            for kg, ci in tiers:
                price = row[ci] if ci < len(row) else None
                if price is not None and str(price).strip() != "":
                    tier_prices[kg] = float(price)
            if not origin and not dest and not tier_prices:
                continue  # 跳过空行
            out.append(
                ParsedRateRecord(
                    record_kind="air_tier",
                    origin_port_name=str(origin).strip() if origin else None,
                    destination_port_name=str(dest).strip() if dest else None,
                    service_desc=(str(v(c_service)).strip() if v(c_service) else None),
                    currency=(str(v(c_currency)).strip() if v(c_currency) else "CNY"),
                    valid_from=self._to_date(v(c_from)),
                    valid_to=self._to_date(v(c_to)),
                    remarks=(str(v(c_remark)).strip() if v(c_remark) else None),
                    source_type="excel",
                    extras={
                        "tier_prices": tier_prices,
                        "cargo_class": (str(v(c_cargo)).strip() if v(c_cargo) else None),
                        "packing": (str(v(c_pack)).strip() if v(c_pack) else None),
                        "density": (str(v(c_density)).strip() if v(c_density) else None),
                        "carrier": (str(v(c_carrier)).strip() if v(c_carrier) else None),
                        "row_index": row_index,
                    },
                )
            )
        return out

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if not value:
            return None
        if hasattr(value, "isoformat") and not isinstance(value, str):
            try:
                return value.date() if hasattr(value, "date") else value
            except Exception:
                return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
```

Modify `adapters/__init__.py`：
```python
from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.adapters.kmtc import KmtcAdapter
from app.services.step1_rates.adapters.nvo_fak import NvoFakAdapter
from app.services.step1_rates.adapters.ocean import OceanAdapter
from app.services.step1_rates.adapters.ocean_ngb import OceanNgbAdapter

__all__ = [
    "AirAdapter",
    "AirTierAdapter",
    "KmtcAdapter",
    "NvoFakAdapter",
    "OceanAdapter",
    "OceanNgbAdapter",
]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_adapter.py -v`
Expected: PASS（3 个）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/adapters/air_tier.py backend/app/services/step1_rates/adapters/__init__.py backend/tests/services/step1_rates/test_air_tier_adapter.py
git commit -m "feat(step1): 新增 AirTierAdapter(按表头内容识别+解析档位表)"
```

---

## Task 4: 注册适配器 + activator 接线 air_tier

**Files:**
- Modify: `backend/app/services/step1_rates/service.py:19-28`（注册到默认 registry）
- Modify: `backend/app/services/step1_rates/activator.py`（`_FILE_TYPE_MAP`、dispatch、`_plan_imported_detail`）
- Test: `backend/tests/services/step1_rates/test_air_tier_activate.py`

- [ ] **Step 1: 写失败测试**

端到端：用 AirTierAdapter 解析出的批次构造 draft 后 activate，断言 AirTierRate 落库。
```python
import uuid
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, AirTierRate, ImportBatch, ImportBatchStatus
from app.services.step1_rates import activator
from app.services.step1_rates.entities import ParsedRateRecord
from app.services.rate_batch_service import DraftRateBatch
from datetime import datetime


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()


def _draft(records: list[ParsedRateRecord]) -> DraftRateBatch:
    now = datetime(2026, 6, 5)
    return DraftRateBatch(
        batch_id=str(uuid.uuid4()),
        file_name="air_tier_rate_sheet_filled.xlsx",
        source_type="excel",
        batch_status="draft",
        activation_status="pending",
        adapter_key="air_tier",
        parser_hint=None,
        carrier_code=None,
        total_rows=len(records),
        warnings=[],
        sheets=[],
        created_at=now,
        updated_at=now,
        legacy_payload={"file_type": "air_tier", "source_file": "air_tier_rate_sheet_filled.xlsx"},
        parse_records=records,
    )


def test_activate_air_tier_writes_rows(db):
    rec = ParsedRateRecord(
        record_kind="air_tier",
        origin_port_name="PVG",
        destination_port_name="NRT",
        service_desc="CA",
        currency="JPY",
        valid_from=date(2026, 6, 1),
        extras={"tier_prices": {45: 17.0, 100: 14.0}, "row_index": 2},
    )
    result = activator.activate(_draft([rec]), db, dry_run=False)
    assert result.activation_status == "activated"
    assert result.imported_detail.get("air_tier_rates") == 1
    rows = db.query(AirTierRate).all()
    assert len(rows) == 1
    assert rows[0].destination == "NRT"
    assert rows[0].currency == "JPY"
    # 批次类型 air_tier 且 active
    batch = db.query(ImportBatch).one()
    assert batch.file_type.value == "air_tier"
    assert batch.status == ImportBatchStatus.active
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_activate.py -v`
Expected: FAIL（`unknown file_type 'air_tier'` 或 `unknown record_kind 'air_tier'`）

- [ ] **Step 3: 实现**

(a) `service.py` 的 `build_default_registry` 注册 AirTierAdapter：
```python
from app.services.step1_rates.adapters import (
    AirAdapter,
    AirTierAdapter,
    KmtcAdapter,
    NvoFakAdapter,
    OceanAdapter,
    OceanNgbAdapter,
)


def build_default_registry() -> RateAdapterRegistry:
    return RateAdapterRegistry(
        adapters=[
            AirAdapter(),
            AirTierAdapter(),
            KmtcAdapter(),
            NvoFakAdapter(),
            OceanAdapter(),
            OceanNgbAdapter(),
        ]
    )
```

(b) `activator.py` import 增加 `AirTierRate`：
```python
from app.models import (
    AirFreightRate,
    AirSurcharge,
    AirTierRate,
    FreightRate,
    ImportBatch,
    ImportBatchFileType,
    ImportBatchStatus,
    LclRate,
)
from app.services.step1_rates.activator_mappers import (
    ActivationError,
    to_air_freight_rate,
    to_air_surcharge,
    to_air_tier_rate,
    to_freight_rate_from_ngb,
    to_freight_rate_from_ocean,
    to_lcl_rate,
)
```

(c) `_FILE_TYPE_MAP` 增加 air_tier：
```python
_FILE_TYPE_MAP = {
    "air": ImportBatchFileType.air,
    "air_tier": ImportBatchFileType.air_tier,
    "ocean": ImportBatchFileType.ocean,
    "ocean_ngb": ImportBatchFileType.ocean_ngb,
}
```

(d) dispatch 循环内，在 `air_surcharge` 分支后增加 air_tier 分支，并在循环前声明 `tier_objs`：
```python
            air_objs: list[AirFreightRate] = []
            sur_objs: list[AirSurcharge] = []
            tier_objs: list[AirTierRate] = []
            freight_objs: list[FreightRate] = []
            lcl_objs: list[LclRate] = []

            for record in dispatchable:
                kind = record.record_kind
                row_idx = record.extras.get("row_index") if record.extras else None
                try:
                    if kind == "air_weekly":
                        air_objs.append(to_air_freight_rate(record, batch_uuid))
                    elif kind == "air_surcharge":
                        sur_objs.append(to_air_surcharge(record, batch_uuid))
                    elif kind == "air_tier":
                        tier_objs.append(to_air_tier_rate(record, batch_uuid))
                    elif kind == "fcl":
                        ...
```

(e) add_all 区块增加 tier_objs：
```python
            if tier_objs:
                db.add_all(tier_objs)
                imported_detail["air_tier_rates"] = len(tier_objs)
```

(f) `imported_rows` 累加 tier_objs：
```python
            imported_rows = (
                len(air_objs) + len(sur_objs) + len(tier_objs)
                + len(freight_objs) + len(lcl_objs)
            )
```

(g) `_plan_imported_detail`（dry_run 预览）增加 air_tier 计数：
```python
    if kind_counts.get("air_tier"):
        detail["air_tier_rates"] = kind_counts["air_tier"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_activate.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/service.py backend/app/services/step1_rates/activator.py backend/tests/services/step1_rates/test_air_tier_activate.py
git commit -m "feat(step1): activator 接线 air_tier(注册适配器+dispatch+批次类型)"
```

---

## Task 5: 档位生成表补列（_build_tier_sheet）

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/template_filler.py:71-101`
- Test: `backend/tests/sheet_builder/test_tier_sheet_columns.py`

按「表头契约」给档位表补 currency/effective_from/effective_to/carrier/cargo_class/packing/density 列。

- [ ] **Step 1: 写失败测试**

```python
from io import BytesIO
from openpyxl import load_workbook
from app.services.step1_rates.sheet_builder.template_filler import fill_template


def test_tier_sheet_has_metadata_columns():
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "carrier": "CA", "cargo_class": "普货",
        "packing": "托", "density": "1:167",
        "effective_week_start": "2026-06-01", "effective_to": "2026-06-07",
        "remark": "周一报价", "tier_prices": {45: 17.0, 100: 14.0},
    }]
    content, _ = fill_template("air", rows)
    ws = load_workbook(BytesIO(content)).active
    header = [c.value for c in ws[1]]
    for label in ["Origin (POL)", "Destination", "Service", "45KG", "100KG",
                  "Currency", "Effective From", "Effective To",
                  "Carrier", "Cargo Class", "Packing", "Density", "Remark"]:
        assert label in header, f"缺表头列 {label}"
    # 值落对位置
    data = {header[i]: ws.cell(2, i + 1).value for i in range(len(header))}
    assert data["Currency"] == "JPY"
    assert data["Effective From"] == "2026-06-01"
    assert data["Carrier"] == "CA"
    assert data["45KG"] == 17.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_tier_sheet_columns.py -v`
Expected: FAIL（缺 Currency 等表头）

- [ ] **Step 3: 实现**

替换 `template_filler.py` 的 `_build_tier_sheet`：
```python
_TIER_META_COLS = (
    ("Currency", "currency"),
    ("Effective From", "effective_week_start"),
    ("Effective To", "effective_to"),
    ("Carrier", "carrier"),
    ("Cargo Class", "cargo_class"),
    ("Packing", "packing"),
    ("Density", "density"),
)


def _build_tier_sheet(rows: list[dict[str, Any]]) -> tuple[bytes, str]:
    """程序生成档位表：起运港|目的港|服务|动态 KG 列|元数据列|备注。"""
    tiers = sorted({kg for row in rows for kg in _row_tiers(row)})
    wb = Workbook()
    ws = wb.active
    ws.title = _tier_sheet_name(rows)

    header = (
        ["Origin (POL)", "Destination", "Service"]
        + [f"{kg}KG" for kg in tiers]
        + [label for label, _ in _TIER_META_COLS]
        + ["Remark"]
    )
    for c, label in enumerate(header, start=1):
        ws.cell(1, c).value = label

    meta_start = 4 + len(tiers)  # KG 列之后第一列
    r = 2
    for row in rows:
        ws.cell(r, 1).value = row.get("origin")
        ws.cell(r, 2).value = row.get("destination")
        ws.cell(r, 3).value = row.get("service")
        row_tiers = _row_tiers(row)
        for i, kg in enumerate(tiers):
            price = row_tiers.get(kg)
            if price is not None:
                ws.cell(r, 4 + i).value = price
        for j, (_, field_name) in enumerate(_TIER_META_COLS):
            ws.cell(r, meta_start + j).value = row.get(field_name)
        ws.cell(r, meta_start + len(_TIER_META_COLS)).value = row.get("remark")
        r += 1

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), "air_tier_rate_sheet_filled.xlsx"
```

> 注意：文件名由 `air_rate_sheet_filled.xlsx` 改为 `air_tier_rate_sheet_filled.xlsx`，更贴近内容（识别走表头，不依赖文件名）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_tier_sheet_columns.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/template_filler.py backend/tests/sheet_builder/test_tier_sheet_columns.py
git commit -m "feat(step1): 档位生成表补 币种/生效日/航司/货类等列(往返无损)"
```

---

## Task 6: 空运档位 round-trip 测试（生成→重新导入→无损）

**Files:**
- Test: `backend/tests/services/step1_rates/test_air_tier_roundtrip.py`

锁住「生成→下载→重新解析→映射」全链字段不丢。纯回归测试，不改产线代码。

- [ ] **Step 1: 写测试**

```python
import uuid
from io import BytesIO
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.activator_mappers import to_air_tier_rate


def test_air_tier_roundtrip_lossless(tmp_path):
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "carrier": "CA", "cargo_class": "普货",
        "packing": "托", "density": "1:167",
        "effective_week_start": "2026-06-01", "effective_to": "2026-06-07",
        "remark": "周一报价", "tier_prices": {45: 17.0, 100: 14.0, 300: 12.0},
    }]
    content, _ = fill_template("air", rows)
    path = tmp_path / "air_tier_rate_sheet_filled.xlsx"
    path.write_bytes(content)

    batch = AirTierAdapter().parse(path, db=None)
    assert len(batch.records) == 1
    rate = to_air_tier_rate(batch.records[0], uuid.uuid4())

    assert rate.origin == "PVG"
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"          # 关键：日本段币种不丢
    assert str(rate.effective_from) == "2026-06-01"
    assert rate.carrier == "CA"
    assert rate.cargo_class == "普货"
    assert rate.tier_prices == {45: 17.0, 100: 14.0, 300: 12.0}
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_tier_roundtrip.py -v`
Expected: PASS（依赖 Task 3/5 已完成）

- [ ] **Step 3: 提交**

```bash
git add backend/tests/services/step1_rates/test_air_tier_roundtrip.py
git commit -m "test(step1): 空运档位 round-trip 无损回归(币种/生效日/档位)"
```

---

## Task 7: 海运生成表 40GP/40HQ 拆 3 行 + 补元数据列

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/template_registry.py:52-69`（sea columns 增列）
- Modify: `backend/app/services/step1_rates/sheet_builder/template_filler.py:31-32,157-177`（`_SEA_CONTAINER_ROWS` 改 3 行 + `_fill_sea` 写表头与元数据列）
- Test: `backend/tests/sheet_builder/test_sea_sheet_split.py`

- [ ] **Step 1: 写失败测试**

```python
from io import BytesIO
from openpyxl import load_workbook
from app.services.step1_rates.sheet_builder.template_filler import fill_template


def test_sea_sheet_splits_40gp_40hq_and_meta():
    rows = [{
        "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "freight_20": 1000, "freight_40": 1800,
        "currency": "USD", "valid_from": "2026-06-01", "valid_to": "2026-06-30",
        "rate_level": "NAC", "service_code": "EC1", "remark": "test",
    }]
    content, _ = fill_template("sea", rows)
    ws = load_workbook(BytesIO(content))["JP N RATE FCL & LCL"]
    # 第 8 行表头含新列
    header = [c.value for c in ws[8]]
    for label in ["Currency", "Valid From", "Valid To", "Rate Level", "Service Code"]:
        assert label in header, f"缺表头 {label}"
    # 数据从第 9 行起，3 行：20FT/40GP/40HQ，箱型价各异
    labels = [ws.cell(9 + i, 3).value for i in range(3)]
    assert labels == ["20FT", "40GP", "40HQ"]
    freights = [ws.cell(9 + i, 4).value for i in range(3)]
    assert freights == [1000, 1800, 1850]   # 40GP≠40HQ 不再合并
    # 元数据每行都带（取第 9 行）
    cur_col = header.index("Currency") + 1
    assert ws.cell(9, cur_col).value == "USD"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_sea_sheet_split.py -v`
Expected: FAIL（仅 2 行 / 无新表头）

- [ ] **Step 3: 实现**

(a) `template_registry.py` 的 `_SEA` columns 增加 5 列：
```python
            columns={
                "destination": 1,
                "carrier": 2,
                "container": 3,
                "freight": 4,
                "lss_cic": 5,
                "baf": 6,
                "ebs": 7,
                "yas_caf": 8,
                "sailing": 9,
                "via": 10,
                "transit": 11,
                "booking": 12,
                "rmks": 17,
                "currency": 18,
                "valid_from": 19,
                "valid_to": 20,
                "rate_level": 21,
                "service_code": 22,
            },
```

(b) `template_filler.py` 顶部 `_SEA_CONTAINER_ROWS` 改 3 行：
```python
_SEA_CONTAINER_ROWS = (
    ("20FT", "container_20gp"),
    ("40GP", "container_40gp"),
    ("40HQ", "container_40hq"),
)

# (表头标签, 列键, 行字段) —— 新增海运元数据列(模板无表头，填充时一并写第8行表头)
_SEA_META_COLS = (
    ("Currency", "currency", "currency"),
    ("Valid From", "valid_from", "valid_from"),
    ("Valid To", "valid_to", "valid_to"),
    ("Rate Level", "rate_level", "rate_level"),
    ("Service Code", "service_code", "service_code"),
)
```

(c) 重写 `_fill_sea`：
```python
def _fill_sea(workbook, sheet_cfg: SheetFillConfig, rows: list[dict[str, Any]]) -> None:
    ws = workbook[sheet_cfg.sheet_name]
    _unmerge_data_area(ws, sheet_cfg.data_start_row)
    col = sheet_cfg.columns
    # 模板无这些新列表头 → 填充时在表头行写英文标签，供重新导入时 OceanAdapter 按表头识别
    for label, col_key, _ in _SEA_META_COLS:
        ws.cell(sheet_cfg.header_row, col[col_key]).value = label
    r = sheet_cfg.data_start_row
    for row in rows:
        for container_label, freight_key in _SEA_CONTAINER_ROWS:
            safe_set(ws.cell(r, col["destination"]), row.get("destination"))
            safe_set(ws.cell(r, col["carrier"]), row.get("carrier"))
            safe_set(ws.cell(r, col["container"]), container_label)
            safe_set(ws.cell(r, col["freight"]), row.get(freight_key))
            safe_set(ws.cell(r, col["lss_cic"]), row.get("lss_cic"))
            safe_set(ws.cell(r, col["baf"]), row.get("baf"))
            safe_set(ws.cell(r, col["ebs"]), row.get("ebs"))
            safe_set(ws.cell(r, col["yas_caf"]), row.get("yas_caf"))
            safe_set(ws.cell(r, col["sailing"]), row.get("sailing"))
            safe_set(ws.cell(r, col["via"]), row.get("via"))
            safe_set(ws.cell(r, col["transit"]), row.get("transit"))
            safe_set(ws.cell(r, col["booking"]), row.get("booking"))
            safe_set(ws.cell(r, col["rmks"]), row.get("remark"))
            for _, col_key, field_name in _SEA_META_COLS:
                safe_set(ws.cell(r, col[col_key]), row.get(field_name))
            r += 1
```

> `safe_set` 对 None 不写，故缺字段不会污染单元格。`sheet_cfg.header_row` 即第 8 行。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_sea_sheet_split.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/template_registry.py backend/app/services/step1_rates/sheet_builder/template_filler.py backend/tests/sheet_builder/test_sea_sheet_split.py
git commit -m "feat(step1): 海运生成表拆 40GP/40HQ 三行 + 补币种/生效日等列"
```

---

## Task 8: OceanAdapter 读新海运列 + mapper 透传 service_code/rate_level

**Files:**
- Modify: `backend/app/services/step1_rates/adapters/ocean.py`（`_parse_fcl_sheet` 读列范围、`_build_fcl_column_map` 识别新表头、`_build_fcl_row_payload` 读值）
- Modify: `backend/app/services/step1_rates/activator_mappers.py`（`to_freight_rate_from_ocean` 透传 service_code/rate_level）
- Test: `backend/tests/services/step1_rates/test_ocean_new_columns.py`

> 40GP/40HQ 拆分**无需**改 OceanAdapter 逻辑（`_normalize_container_type` 已区分 40GP→"40ft"/40HQ→"40hq"，`_merge_40_payload` 已分别落字段，3 行同 pair_key 自然合成）；本任务只加「新元数据列」的读取。Task 9 的 round-trip 测试验证拆分。

- [ ] **Step 1: 写失败测试**

直接喂一张 Task 7 生成的海运表，断言 OceanAdapter 读到 currency/valid_from/valid_to/rate_level/service_code，且 40gp≠40hq。用 in-memory db fixture 注港口（OceanAdapter parse 会对起运/目的港走 `_resolve_port_ref`，给真实 db 最稳）。
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Carrier, Port
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.ocean import OceanAdapter


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    s.add(Port(un_locode="CNSHA", name_en="Shanghai", name_cn="上海"))
    s.add(Port(un_locode="USLAX", name_en="Los Angeles", name_cn="洛杉矶"))
    s.add(Carrier(code="ONE", name_en="Ocean Network Express"))
    s.commit()
    yield s
    s.close()


def test_ocean_reads_new_columns(tmp_path, db):
    rows = [{
        "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "currency": "EUR", "valid_from": "2026-06-01", "valid_to": "2026-06-30",
        "rate_level": "NAC", "service_code": "EC1", "remark": "rt",
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_sea_filled.xlsx"
    path.write_bytes(content)

    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert len(fcl) == 1
    r = fcl[0]
    assert r.container_40gp != r.container_40hq      # 拆分保留
    assert str(r.container_40gp) == "1800"
    assert str(r.container_40hq) == "1850"
    assert r.currency == "EUR"                        # 读到币种(非默认 USD)
    assert str(r.valid_from) == "2026-06-01"
    assert r.rate_level == "NAC"
    assert r.service_code == "EC1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_ocean_new_columns.py -v`
Expected: FAIL（currency=="USD" 默认值，或 rate_level/service_code 为 None）

- [ ] **Step 3: 实现**

(a) `_parse_fcl_sheet` 把读列范围 `range(1, 18)` 改为 `range(1, 23)`（读到第 22 列）：
```python
            row = [worksheet.cell(row=row_index, column=column).value for column in range(1, 23)]
```

(b) `_build_fcl_column_map` 的 `layout` 字典增加 5 个键，并在 for 循环里加识别分支（`_normalize_header_text` 已小写+折空格，匹配小写标签）：
```python
        layout: dict[str, int | None] = {
            ...
            "remarks": None,
            "currency": None,
            "valid_from": None,
            "valid_to": None,
            "rate_level": None,
            "service_code": None,
        }
```
循环内新增分支（放在 remarks 分支附近）：
```python
            elif cell == "currency":
                layout["currency"] = index
            elif cell == "valid from":
                layout["valid_from"] = index
            elif cell == "valid to":
                layout["valid_to"] = index
            elif cell == "rate level":
                layout["rate_level"] = index
            elif cell == "service code":
                layout["service_code"] = index
```

(c) `_build_fcl_row_payload` 读新列并覆盖默认值。在 return 字典前计算：
```python
        col_currency = self._normalize_text(self._get_layout_value(row, layout, "currency"))
        col_valid_from = self._to_date(self._get_layout_value(row, layout, "valid_from"))
        col_valid_to = self._to_date(self._get_layout_value(row, layout, "valid_to"))
        col_rate_level = self._normalize_text(self._get_layout_value(row, layout, "rate_level"))
        col_service_code = self._normalize_text(self._get_layout_value(row, layout, "service_code"))
```
并把 return 字典里这几项改为读列优先、回落原值：
```python
            "currency": col_currency or "USD",
            "valid_from": col_valid_from or effective_from,
            "valid_to": col_valid_to or effective_to,
            "rate_level": col_rate_level,
            "service_code": col_service_code,
```
> `rate_level`/`service_code` 是 `Step1RateRow` 既有字段，原 payload 未设（默认 None），现按列写入。

(d) `activator_mappers.to_freight_rate_from_ocean`：把硬编码的 `service_code=None`、`rate_level=None` 改为透传：
```python
        service_code=record.service_code,
        ...
        rate_level=record.rate_level,
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_ocean_new_columns.py -v`
Expected: PASS
Run（回归，确保未破坏真实海运解析）: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/ -v`
Expected: 全 PASS（重点关注既有 ocean / commit_ocean 相关测试不退化）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/adapters/ocean.py backend/app/services/step1_rates/activator_mappers.py backend/tests/services/step1_rates/test_ocean_new_columns.py
git commit -m "feat(step1): OceanAdapter 按表头读币种/生效日/费率档/服务码 + mapper 透传"
```

---

## Task 9: 海运 round-trip 测试（拆分 + 无损）

**Files:**
- Test: `backend/tests/services/step1_rates/test_ocean_roundtrip.py`

- [ ] **Step 1: 写测试**

用 in-memory db（注入港口/船司）走「生成→重新解析→映射 FreightRate」全链。
```python
import uuid
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Carrier, Port
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.ocean import OceanAdapter
from app.services.step1_rates.activator_mappers import to_freight_rate_from_ocean


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    s.add(Port(un_locode="CNSHA", name_en="Shanghai", name_cn="上海"))
    s.add(Port(un_locode="USLAX", name_en="Los Angeles", name_cn="洛杉矶"))
    s.add(Carrier(code="ONE", name_en="Ocean Network Express"))
    s.commit()
    yield s
    s.close()


def test_ocean_roundtrip_split_and_lossless(tmp_path, db):
    rows = [{
        "origin": "SHANGHAI", "destination": "USLAX", "carrier": "ONE",
        "container_20gp": 1000, "container_40gp": 1800, "container_40hq": 1850,
        "currency": "USD", "valid_from": "2026-06-01", "valid_to": "2026-06-30",
        "rate_level": "NAC", "service_code": "EC1", "remark": "rt",
    }]
    content, _ = fill_template("sea", rows)
    path = tmp_path / "ocean_sea_filled.xlsx"
    path.write_bytes(content)

    batch = OceanAdapter().parse(path, db=db)
    fcl = [r for r in batch.records if r.record_kind == "fcl"]
    assert len(fcl) == 1
    rate = to_freight_rate_from_ocean(fcl[0], uuid.uuid4(), db, source_file="rt.xlsx")
    assert rate.container_20gp == Decimal("1000")
    assert rate.container_40gp == Decimal("1800")
    assert rate.container_40hq == Decimal("1850")   # 关键：拆分不丢
    assert rate.currency == "USD"
    assert str(rate.valid_from) == "2026-06-01"
    assert rate.rate_level == "NAC"
    assert rate.service_code == "EC1"
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_ocean_roundtrip.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add backend/tests/services/step1_rates/test_ocean_roundtrip.py
git commit -m "test(step1): 海运 round-trip(40GP≠40HQ 拆分 + 元数据无损)"
```

---

## Task 10: 空运周报生成表补币种列（_fill_air）

> 为 Task 13 的周报回流做准备（Option B）。给 `air_blank` 生成表加 Currency 列，让人工可调、回流不丢币种。
> 周起始日已由 `_apply_week_headers` 写进 7 个日期表头（Task 13 据此解析周）。

**Files:**
- Modify: `backend/app/services/step1_rates/sheet_builder/template_registry.py:36-39`（air columns 增 currency）
- Modify: `backend/app/services/step1_rates/sheet_builder/template_filler.py:141-154`（`_fill_air` 写表头+值）
- Test: `backend/tests/sheet_builder/test_air_weekly_currency.py`

- [ ] **Step 1: 写失败测试**

```python
from io import BytesIO
from openpyxl import load_workbook
from app.services.step1_rates.sheet_builder.template_filler import fill_template


def test_air_weekly_sheet_has_currency_column():
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "day1": 10, "day2": 11,
        "effective_week_start": "2026-05-25",
    }]
    content, _ = fill_template("air", rows)  # 无 tier_prices → 走周表分支
    ws = load_workbook(BytesIO(content)).active
    header = [c.value for c in ws[1]]
    assert "Currency" in header
    cur_col = header.index("Currency") + 1
    assert ws.cell(2, cur_col).value == "JPY"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_air_weekly_currency.py -v`
Expected: FAIL（无 Currency 列）

- [ ] **Step 3: 实现**

(a) `template_registry.py` `_AIR` columns 增 `"currency": 12`（K=11 是 remark，L=12 空）：
```python
                "remark": 11,
                "currency": 12,
```
(b) `_fill_air` 写表头与值：
```python
def _fill_air(workbook, sheet_cfg: SheetFillConfig, rows: list[dict[str, Any]]) -> None:
    ws = workbook[sheet_cfg.sheet_name]
    _unmerge_data_area(ws, sheet_cfg.data_start_row)
    _apply_week_headers(ws, sheet_cfg, rows)
    col = sheet_cfg.columns
    ws.cell(sheet_cfg.header_row, col["currency"]).value = "Currency"
    r = sheet_cfg.data_start_row
    for row in rows:
        safe_set(ws.cell(r, col["origin"]), row.get("origin"))
        safe_set(ws.cell(r, col["destination"]), row.get("destination"))
        safe_set(ws.cell(r, col["service"]), row.get("service"))
        for day in range(1, 8):
            safe_set(ws.cell(r, col[f"day{day}"]), row.get(f"day{day}"))
        safe_set(ws.cell(r, col["remark"]), row.get("remark"))
        safe_set(ws.cell(r, col["currency"]), row.get("currency"))
        r += 1
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/sheet_builder/test_air_weekly_currency.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/sheet_builder/template_registry.py backend/app/services/step1_rates/sheet_builder/template_filler.py backend/tests/sheet_builder/test_air_weekly_currency.py
git commit -m "feat(step1): 空运周报生成表补币种列(为回流做准备)"
```

---

## Task 11: 拆除做表页第二入库口（前端按钮 + 后端端点 + db_writer）

> ⚠️ 必须在 Task 1–10 完成、回流路径全部就位后再做，避免出现「做表不能入库、导入又认不出」的空档。

**Files:**
- Modify: `frontend/src/pages/RateSheetBuilder.tsx`（删 `入库` 按钮、`handleCommit`、`showCommit`；下载后引导文案）
- Modify: `frontend/src/services/api.ts:257-258`（删 `rateSheetApi.commitToDb`）
- Modify: `backend/app/api/v1/rate_sheet.py`（删 `/{session_id}/commit` 端点与 `_has_ocean_price`）
- Delete: `backend/app/services/step1_rates/sheet_builder/db_writer.py`
- Delete: `backend/tests/api_v1/test_rate_sheet_commit.py`（端点已删）+ `backend/tests/services/step1_rates/test_commit_ocean_bilingual.py`（commit_ocean 已删）
- Modify: `frontend/src/i18n/{zh,ja,en}.json`（删 `rateSheet.commit*`；加 `rateSheet.downloadThenImportHint`）

- [ ] **Step 1: 后端删端点与 db_writer**

删除 `rate_sheet.py` 中 `@router.post("/{session_id}/commit")` 整个函数、`_has_ocean_price`，以及顶部 `from ...sheet_builder import db_writer, orchestrator` 改为 `from ...sheet_builder import orchestrator`。
删除文件 `db_writer.py` 及其两个测试文件。

- [ ] **Step 2: 跑后端全量，确认无引用残留**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全 PASS（若报 `ImportError: db_writer`，搜索并清理残留引用：`grep -rn "db_writer\|commit_tier_rows\|commit_ocean_rows\|/commit" app/ tests/`）

- [ ] **Step 3: 前端删入库 UI**

`RateSheetBuilder.tsx`：
- 删 `handleCommit` 函数（214-246 行附近）。
- 删 `showCommit` 常量（446 行）及其引用的「入库」按钮 `<button ...{t('rateSheet.commit')}...>`（605-616 行）。
- 「下载」按钮的 `marginLeft` 简化为不再依赖 `showCommit`。
- 下载成功后追加引导：在 `handleDownload` 成功分支 `message.success(t('rateSheet.downloadThenImportHint'))`。

`api.ts`：删除 `commitToDb` 那一项。

- [ ] **Step 4: i18n 三份同步**

`zh.json` 增 `"downloadThenImportHint": "运价表已下载，请到「运价导入」页上传此表以形成数据"`，删 `commit`/`commitSuccess`/`commitSuccessOcean`/`commitFailed` 键。`ja.json`/`en.json` 同步对应译文：
- ja: `"downloadThenImportHint": "レート表をダウンロードしました。「レート取込」画面でこの表をアップロードしてデータ化してください"`
- en: `"downloadThenImportHint": "Rate sheet downloaded. Upload it on the Rate Import page to persist the data."`

- [ ] **Step 5: 前端构建校验**

Run: `cd frontend && npm run build`
Expected: 构建通过（无 `commitToDb`/`showCommit`/缺失 i18n 键的类型或引用报错）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/RateSheetBuilder.tsx frontend/src/services/api.ts frontend/src/i18n/zh.json frontend/src/i18n/ja.json frontend/src/i18n/en.json backend/app/api/v1/rate_sheet.py
git rm backend/app/services/step1_rates/sheet_builder/db_writer.py backend/tests/api_v1/test_rate_sheet_commit.py backend/tests/services/step1_rates/test_commit_ocean_bilingual.py
git commit -m "refactor(step1): 拆除做表页入库口(删 commit 端点/db_writer/按钮),入库统一走导入页"
```

---

## Task 12: 导入页 parser_hint 选择 + air_tier 跳过 diff

**Files:**
- Modify: `frontend/src/pages/RateUpload.tsx`（excel tab 加 parser 下拉，传给 `rateBatchApi.upload`）
- Modify: `frontend/src/i18n/{zh,ja,en}.json`（parser 选项文案）
- Modify: `backend/app/api/v1/rate_batches.py:81-92`（air_tier 批次跳过/空 diff）
- Test: `backend/tests/api_v1/test_rate_batch_air_tier_diff.py`

- [ ] **Step 1: 写后端失败测试（air_tier diff 不报错、返回空对比）**

```python
# 复用既有 api_v1 测试风格(TestClient + 内存 db)。断言对 air_tier 草稿请求 diff 返回 code=0
# 且 diff 项为空(air_tier 无 FreightRate 可比)。具体 fixture 参照 tests/api_v1/ 现有用例。
def test_air_tier_batch_diff_is_empty(client_and_air_tier_draft):
    client, batch_id = client_and_air_tier_draft
    res = client.get(f"/api/v1/rate-batches/{batch_id}/diff").json()
    assert res["code"] == 0
    assert res["data"]["added"] == [] or res["data"].get("added_count", 0) >= 0
```
> 注：若现有 diff 响应结构不同，按实际 `RateBatchDiffResponse` schema 调整断言字段名。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_batch_air_tier_diff.py -v`
Expected: FAIL（diff 对 air_tier 走 FreightRate 比较，可能抛错或返回错配）

- [ ] **Step 3: 后端实现**

`rate_batches.py` 的 `get_rate_batch_diff`：取出 draft 后，若 `legacy_payload.file_type == "air_tier"`（或 draft.adapter_key=="air_tier"），直接返回空 diff（不进入 FreightRate 比较），附 message「档位运价无 FreightRate 对比」。

- [ ] **Step 4: 前端 parser 下拉**

`RateUpload.tsx` excel tab：在 DropZone 上方加一个 `<select>`（或 AntD `Select`），值 `auto/ocean/air/air_tier`，state `parserHint`；`handleExcelUpload` 调用改为 `rateBatchApi.upload(file, parserHint === 'auto' ? undefined : parserHint)`。默认 `auto`（靠内容自动识别，下拉仅作兜底）。i18n 加 `upload.parserHint*` 文案三份。

- [ ] **Step 5: 跑测试 + 前端构建**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_batch_air_tier_diff.py -v` → PASS
Run: `cd frontend && npm run build` → PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/RateUpload.tsx frontend/src/i18n/*.json backend/app/api/v1/rate_batches.py backend/tests/api_v1/test_rate_batch_air_tier_diff.py
git commit -m "feat(step1): 导入页 parser 兜底选择 + air_tier 批次跳过 FreightRate diff"
```

---

## 收尾：全量回归

- [ ] **后端全量**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全 PASS（含新增 air_tier / round-trip / ocean 回归）

- [ ] **前端构建 + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: 通过

- [ ] **人工冒烟（按 DEPLOYMENT.md 起服务）**

1. 做表页：上传一份空运档位杂料 → 审核台只剩「下载」无「入库」→ 下载档位表。
2. 导入页：上传刚下载的档位表 → 自动识别 air_tier → 预览 → activate → `AirTierRate` 落库。
3. 同上验证海运 sea 表：导入后在运价列表能看到 40GP 与 40HQ 不同价。
4. step2 投标空运档位仍能取到价（链路未断）。

---

## 验收对照（spec → 任务）

| spec 验收项 | 对应任务 |
|---|---|
| 做表页无任何入库入口 | Task 11 |
| 下载的运价表能从导入页落库 | Task 4/6/8/9/12 |
| 海运 40GP 与 40HQ 可区分 | Task 7（生成）+ Task 9（验证） |
| 币种/生效日 round-trip 保留 | Task 5/6（空运档位）、7/8/9（海运）、10/13（空运周报） |
| step2 仍能取 AirTierRate | Task 2/3/4（air_tier 入库链路）+ 收尾冒烟 |
| 全量 pytest 通过 + 海运不退化 | Task 8 回归 + 收尾全量 |

> **空运周报已定 Option B**：做表生成的周报表本身可回流（Task 10 补币种列 + Task 13 新增 air_weekly 适配器）。

---

## Task 13: air_weekly 适配器（读 air_blank 布局回流）+ round-trip

**Files:**
- Create: `backend/app/services/step1_rates/adapters/air_weekly.py`
- Modify: `backend/app/services/step1_rates/adapters/__init__.py`（导出 AirWeeklyAdapter）
- Modify: `backend/app/services/step1_rates/service.py`（注册到默认 registry）
- Test: `backend/tests/services/step1_rates/test_air_weekly_adapter.py`

读做表生成的周报表布局：`Origin (POL) | Destinations | Service/+100KG | <7 个日期列> | Remark (Selling) | Currency`。
产 `record_kind="air_weekly"` 记录（activator 已接线 air→AirFreightRate，无需改 activator）。priority=6（air_tier=5 之后、air=10 之前），按表头内容识别。周起始日从首个日期列表头解析。

- [ ] **Step 1: 写失败测试（detect + parse + round-trip）**

```python
import uuid
from app.services.step1_rates.sheet_builder.template_filler import fill_template
from app.services.step1_rates.adapters.air_weekly import AirWeeklyAdapter
from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.activator_mappers import to_air_freight_rate
from app.services.step1_rates.entities import Step1FileType


def _make(tmp_path):
    rows = [{
        "origin": "PVG", "destination": "NRT", "service": "CA",
        "currency": "JPY", "effective_week_start": "2026-05-25",
        "day1": 10, "day2": 11, "day3": 12, "day4": 13,
        "day5": 14, "day6": 15, "day7": 16, "remark": "wk",
    }]
    content, _ = fill_template("air", rows)  # 无 tier_prices → 周表分支
    path = tmp_path / "air_weekly_rate_sheet_filled.xlsx"
    path.write_bytes(content)
    return path


def test_detect_weekly_layout(tmp_path):
    path = _make(tmp_path)
    assert AirWeeklyAdapter().detect(path) is True


def test_air_adapter_skips_generated_weekly(tmp_path):
    # 既有 AirAdapter(读真实承运商布局)不应误吞做表生成表(无 A1=Destinations)
    path = _make(tmp_path)
    assert AirWeeklyAdapter().priority < AirAdapter().priority


def test_parse_and_roundtrip(tmp_path):
    path = _make(tmp_path)
    batch = AirWeeklyAdapter().parse(path, db=None)
    assert batch.file_type is Step1FileType.air
    recs = [r for r in batch.records if r.record_kind == "air_weekly"]
    assert len(recs) == 1
    r = recs[0]
    assert r.origin_port_name == "PVG"
    assert r.destination_port_name == "NRT"
    assert r.service_desc == "CA"
    assert r.currency == "JPY"
    assert str(r.effective_week_start) == "2026-05-25"
    rate = to_air_freight_rate(r, uuid.uuid4())
    assert rate.destination == "NRT"
    assert rate.currency == "JPY"
    assert str(rate.price_day1) == "10"
    assert str(rate.price_day7) == "16"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_weekly_adapter.py -v`
Expected: FAIL（`ModuleNotFoundError: ...adapters.air_weekly`）

- [ ] **Step 3: 实现**

Create `backend/app/services/step1_rates/adapters/air_weekly.py`：
```python
"""Step1 空运周报(air_weekly)回流适配器。

读「做表」生成的周报表布局(air_blank)：
  Origin (POL) | Destinations | Service/+100KG | <7 个日期列> | Remark (Selling) | Currency
产 record_kind="air_weekly" → activator 已接线 air→AirFreightRate。
按表头内容识别(不靠文件名)；周起始日从首个日期列表头(形如 '2026/5/25 (Mon)')解析。
注意与既有 AirAdapter(读真实承运商布局 A1='Destinations'、无 origin 列)区分：本适配器要求有 'origin' 表头。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.services.step1_rates.entities import (
    ParsedRateBatch,
    ParsedRateRecord,
    Step1FileType,
)

_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}


class AirWeeklyAdapter:
    """识别并解析做表生成的空运周报表(air_blank 布局)。"""

    key = "air_weekly"
    file_type = Step1FileType.air
    priority = 6  # air_tier(5) 之后、air(10) 之前

    def detect(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> bool:
        if file_type_hint is not None:
            return False  # air hint 仍交给真实承运商 AirAdapter
        if path.suffix.lower() not in _EXCEL_EXTS:
            return False
        try:
            wb = load_workbook(path, data_only=True, read_only=True)
        except Exception:
            return False
        try:
            for ws in wb.worksheets:
                if self._weekly_headers(ws) is not None:
                    return True
        finally:
            wb.close()
        return False

    def parse(self, path: Path, db: Session | None = None) -> ParsedRateBatch:
        wb = load_workbook(path, data_only=True)
        records: list[ParsedRateRecord] = []
        for ws in wb.worksheets:
            headers = self._weekly_headers(ws)
            if headers is None:
                continue
            records.extend(self._parse_sheet(ws, headers))
        return ParsedRateBatch(
            file_type=Step1FileType.air,
            source_file=path.name,
            records=records,
            adapter_key=self.key,
        )

    def _weekly_headers(self, ws) -> dict[str, Any] | None:
        """命中周报布局返回 {origin,destination,service,remark,currency,date_cols:[idx],week_start}，否则 None。"""
        first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not first:
            return None
        named: dict[str, int] = {}
        date_cols: list[int] = []
        week_start: date | None = None
        for idx, cell in enumerate(first):
            text = str(cell).strip() if cell is not None else ""
            if not text:
                continue
            m = _DATE_RE.search(text)
            if m:
                date_cols.append(idx)
                if week_start is None:
                    week_start = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                named[text.lower()] = idx
        has_origin = any(k.startswith("origin") for k in named)
        has_dest = any(k.startswith("destination") for k in named)
        has_service = any(k.startswith("service") for k in named)
        if has_origin and has_dest and has_service and len(date_cols) >= 7:
            return {
                "origin": next(named[k] for k in named if k.startswith("origin")),
                "destination": next(named[k] for k in named if k.startswith("destination")),
                "service": next(named[k] for k in named if k.startswith("service")),
                "remark": next((named[k] for k in named if k.startswith("remark")), None),
                "currency": named.get("currency"),
                "date_cols": date_cols[:7],
                "week_start": week_start,
            }
        return None

    def _parse_sheet(self, ws, h: dict[str, Any]) -> list[ParsedRateRecord]:
        week_start: date | None = h["week_start"]
        week_end = week_start + timedelta(days=6) if week_start else None
        out: list[ParsedRateRecord] = []
        for row_index, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            def v(i: int | None) -> Any:
                return row[i] if i is not None and i < len(row) else None

            origin = v(h["origin"])
            dest = v(h["destination"])
            prices = [self._dec(row[ci] if ci < len(row) else None) for ci in h["date_cols"]]
            if not origin and not dest and not any(p is not None for p in prices):
                continue
            kw: dict[str, Any] = {f"price_day{i + 1}": prices[i] for i in range(7)}
            out.append(
                ParsedRateRecord(
                    record_kind="air_weekly",
                    origin_port_name=str(origin).strip() if origin else None,
                    destination_port_name=str(dest).strip() if dest else None,
                    service_desc=(str(v(h["service"])).strip() if v(h["service"]) else None),
                    currency=(str(v(h["currency"])).strip() if v(h["currency"]) else "CNY"),
                    effective_week_start=week_start,
                    effective_week_end=week_end,
                    remarks=(str(v(h["remark"])).strip() if v(h["remark"]) else None),
                    source_type="excel",
                    extras={"row_index": row_index},
                    **kw,
                )
            )
        return out

    @staticmethod
    def _dec(value: Any) -> Decimal | None:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        try:
            return value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
```

Modify `adapters/__init__.py`（加入 AirWeeklyAdapter 的 import 与 `__all__`）：
```python
from app.services.step1_rates.adapters.air import AirAdapter
from app.services.step1_rates.adapters.air_tier import AirTierAdapter
from app.services.step1_rates.adapters.air_weekly import AirWeeklyAdapter
from app.services.step1_rates.adapters.kmtc import KmtcAdapter
from app.services.step1_rates.adapters.nvo_fak import NvoFakAdapter
from app.services.step1_rates.adapters.ocean import OceanAdapter
from app.services.step1_rates.adapters.ocean_ngb import OceanNgbAdapter

__all__ = [
    "AirAdapter",
    "AirTierAdapter",
    "AirWeeklyAdapter",
    "KmtcAdapter",
    "NvoFakAdapter",
    "OceanAdapter",
    "OceanNgbAdapter",
]
```

Modify `service.py` 的 `build_default_registry`，加入 `AirWeeklyAdapter()`（顺序不影响，registry 按 priority 排）：
```python
from app.services.step1_rates.adapters import (
    AirAdapter,
    AirTierAdapter,
    AirWeeklyAdapter,
    KmtcAdapter,
    NvoFakAdapter,
    OceanAdapter,
    OceanNgbAdapter,
)


def build_default_registry() -> RateAdapterRegistry:
    return RateAdapterRegistry(
        adapters=[
            AirAdapter(),
            AirTierAdapter(),
            AirWeeklyAdapter(),
            KmtcAdapter(),
            NvoFakAdapter(),
            OceanAdapter(),
            OceanNgbAdapter(),
        ]
    )
```

- [ ] **Step 4: 跑测试确认通过 + air 回归**

Run: `cd backend && ../.venv/bin/python -m pytest tests/services/step1_rates/test_air_weekly_adapter.py tests/services/step1_rates/test_air_adapter.py -v`
Expected: 全 PASS（既有 AirAdapter 真实承运商解析不退化——做表生成表无 A1='Destinations' 且本适配器优先级更高，两者互不干扰）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/step1_rates/adapters/air_weekly.py backend/app/services/step1_rates/adapters/__init__.py backend/app/services/step1_rates/service.py backend/tests/services/step1_rates/test_air_weekly_adapter.py
git commit -m "feat(step1): 新增 AirWeeklyAdapter(做表周报表回流→AirFreightRate)"
```
