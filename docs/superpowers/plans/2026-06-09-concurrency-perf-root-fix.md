# 并发超时/变慢 根治 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除「多用户并发时前端连后端超时/变慢」的三个结构性根因——SQLite 全库写锁、AI 长任务占满共享线程池/GPU、超时三层倒挂——让单 worker 稳定支撑 2 客户多人并发。

**Architecture:** 三个 Phase 渐进上线，每个 Phase 末尾都是可独立部署的 milestone。Phase 1 纯配置过渡缓解（SQLite WAL + nginx 超时消倒挂）；Phase 2 迁 PostgreSQL（根治写锁，不迁历史数据）；Phase 3 AI 长任务异步化（提交即返回 + 前端轮询）+ 独立线程池限流 + 超时最终调小。核心设计是**最小侵入**：异步任务用 DB 表 `async_tasks` 做信令、`result_json` 存原 HTTP 响应体，AI 全量解析结果仍写现有内存 `_parse_cache`，下游 `/ai/confirm` 链路一行不改；前端把 `api.ts` 导出函数内部改成「提交→轮询→重新包成 ApiResponse」，页面组件零改动。

**Tech Stack:** FastAPI 0.115 + SQLAlchemy 2.0 + Alembic + pydantic-settings；PostgreSQL 16（docker-compose 已就绪，`psycopg2-binary` 已在依赖）；React 19 + TypeScript + axios；pytest（后端）/ ESLint + vite build（前端）。

**关键依赖关系：** 超时「调小」依赖 AI 异步化（同步 AI 仍需长超时，否则被前端/nginx 掐断）。故 Phase 1 只做「消倒挂」的过渡（把 nginx 提到 ≥ 后端），真正的「超时调小」在 Phase 3 末尾。

**执行约定：** 后端命令一律 `cd backend` 后用 `../.venv/bin/python -m pytest ...`（见 CLAUDE.md）。每个 Task 末尾 commit。前端无 `npm test`，只有 `npm run lint` 和 `npm run build`。

---

## Phase 1 — 过渡缓解（消倒挂 + 缓解写锁，零/低风险，可先上线）

### Task 1.1: SQLite 启用 WAL + busy_timeout（过渡缓解写锁）

**Files:**
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_database_sqlite_pragma.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_database_sqlite_pragma.py`：

```python
"""SQLite 连接必须启用 WAL + busy_timeout，缓解「写者阻塞读者」全站卡顿。"""
import sqlite3


def test_apply_sqlite_pragmas_enables_wal_busy_timeout_and_fk(tmp_path):
    from app.core.database import _apply_sqlite_pragmas

    conn = sqlite3.connect(str(tmp_path / "probe.db"))
    try:
        _apply_sqlite_pragmas(conn)
        cur = conn.cursor()
        assert cur.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert cur.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert cur.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_database_sqlite_pragma.py -v`
Expected: FAIL —— `ImportError: cannot import name '_apply_sqlite_pragmas'`

- [ ] **Step 3: 实现**

修改 `backend/app/core/database.py`，把 pragma 逻辑抽成可测函数并补 WAL/busy_timeout。把现有的：

```python
# SQLite 启用外键约束
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

替换为：

```python
def _apply_sqlite_pragmas(dbapi_conn) -> None:
    """SQLite 每条连接的 PRAGMA：外键约束 + WAL（读不被写阻塞）+ 5s 锁等待。

    WAL 让并发读不被写者阻塞，缓解「一人大批导入→全站查询卡住」。
    busy_timeout 让写冲突时等待而非立刻 'database is locked'。
    仅对文件型 SQLite 生效，PG 上线后此分支不走。
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# SQLite PRAGMA：外键 + WAL + busy_timeout
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        _apply_sqlite_pragmas(dbapi_conn)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_database_sqlite_pragma.py -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全绿（既有 452 + 新增 1）

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/database.py backend/tests/test_database_sqlite_pragma.py
git commit -m "perf(db): SQLite 启用 WAL + busy_timeout，缓解写者阻塞读者"
```

### Task 1.2: nginx 超时消倒挂（文档 + 运维命令）

**Files:**
- Modify: `DEPLOYMENT.md`（§2.7 nginx 配置块 + §0 复测表）

> nginx 实际配置在生产服务器、不在仓库；这里改文档建议值 + 给运维一条命令。无测试。

- [ ] **Step 1: 更新 DEPLOYMENT.md nginx 块**

把 `DEPLOYMENT.md` 中 §2.7 的：

```nginx
    proxy_read_timeout 120s;        # AI 兜底解析可能跑 30~90s
```

改为：

```nginx
    # ⚠️ 过渡期(Phase1)：提到 300s 与后端 AI_TIMEOUT_SECONDS 对齐，消除
    #    「nginx 先掐断 504、后端线程仍空转到 300s 不释放」的倒挂。
    #    AI 异步化(Phase3)上线后改回 60s（届时请求都变短）。
    proxy_read_timeout 300s;
```

并在 §0「部署前先看一眼最近的修复」表格追加一行：

```markdown
| 本次 perf 根治 | nginx proxy_read_timeout 120→300（过渡消倒挂） | 改 nginx site config 后 `sudo nginx -t && sudo systemctl reload nginx` |
```

- [ ] **Step 2: Commit**

```bash
git add DEPLOYMENT.md
git commit -m "docs(deploy): nginx proxy_read_timeout 过渡提到 300s 消除超时倒挂"
```

> **Phase 1 milestone：** 此处可上线。运维改 nginx + reload，后端重启加载 WAL。立刻缓解「一人导入全站卡」与「长任务 504 但后端不释放」。

---

## Phase 2 — PostgreSQL 迁移（根治写锁，不迁历史数据）

### Task 2.1: database.py PG 连接池配置

**Files:**
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_database_engine_pool.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_database_engine_pool.py`：

```python
"""引擎构造：PG 必须带连接池保活(pre_ping/recycle)，SQLite 保持 check_same_thread。"""


def test_pg_engine_enables_pre_ping_and_recycle():
    from app.core.database import _build_engine

    eng = _build_engine("postgresql+psycopg2://u:p@localhost:5432/db", debug=False)
    assert eng.pool._pre_ping is True
    assert eng.pool._recycle == 1800


def test_sqlite_engine_has_no_pre_ping():
    from app.core.database import _build_engine

    eng = _build_engine("sqlite:///./probe.db", debug=False)
    assert eng.pool._pre_ping is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_database_engine_pool.py -v`
Expected: FAIL —— `ImportError: cannot import name '_build_engine'`

- [ ] **Step 3: 实现**

修改 `backend/app/core/database.py`，把现有的：

```python
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=connect_args,
)
```

替换为：

```python
def _build_engine(database_url: str, debug: bool):
    """按 DB 类型构造引擎。

    - SQLite：check_same_thread=False（FastAPI 多线程需要），不配 QueuePool
      参数（SQLite 用默认）。
    - PostgreSQL：连接池保活——pool_pre_ping 防 PG 空闲断连后拿到死连接；
      pool_recycle=1800 主动回收；pool_size/max_overflow 给并发留余量。
    """
    kwargs = {"echo": debug}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return create_engine(database_url, **kwargs)


engine = _build_engine(settings.database_url, settings.debug)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_database_engine_pool.py -v`
Expected: PASS（`postgresql+psycopg2://` 引擎为惰性，不会真连库；`psycopg2-binary` 已在依赖）

- [ ] **Step 5: 全量回归 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest -q`

```bash
git add backend/app/core/database.py backend/tests/test_database_engine_pool.py
git commit -m "perf(db): PG 引擎启用 pool_pre_ping/recycle，保留 SQLite 分支"
```

### Task 2.2: 干净 PG 上验证全套 alembic 迁移

**Files:**
- Create: `scripts/verify_pg_migrations.sh`

> SQLite 容忍但 PG 严格的写法（Enum/JSON/自增/Boolean）必须在干净 PG 预演通过。这是本 Phase 唯一真风险点。

- [ ] **Step 1: 写验证脚本**

创建 `scripts/verify_pg_migrations.sh`：

```bash
#!/usr/bin/env bash
# 在一次性 docker PG 上跑全套 alembic 迁移 + seed，验证 SQLite→PG 兼容性。
# 用法：bash scripts/verify_pg_migrations.sh
set -euo pipefail

CONTAINER=hankyu_pg_verify
PORT=55432
URL="postgresql+psycopg2://postgres:postgres@localhost:${PORT}/hankyu_hanshin"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

cleanup
docker run -d --name "$CONTAINER" \
  -e POSTGRES_DB=hankyu_hanshin -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -p ${PORT}:5432 postgres:16 >/dev/null
echo "等待 PG 就绪..."
for i in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done

cd "$(dirname "$0")/../backend"
echo "==> alembic upgrade head"
DATABASE_URL="$URL" ../.venv/bin/python -m alembic upgrade head
echo "==> seed_data.py"
cd ..
DATABASE_URL="$URL" .venv/bin/python scripts/seed_data.py
echo "✅ PG 迁移 + seed 验证通过"
```

- [ ] **Step 2: 运行验证**

Run: `bash scripts/verify_pg_migrations.sh`
Expected: 末尾打印 `✅ PG 迁移 + seed 验证通过`；seed 日志含 `carriers seed: 34 inserted / ports seed: 140 inserted`。
若某条迁移在 PG 报错 → 记录报错迁移文件，**STOP 并按 systematic-debugging 修该迁移**（通常是 SQLite 特有写法），修好再跑本脚本。

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_pg_migrations.sh
git commit -m "chore(db): 加 PG 迁移验证脚本（干净 PG 跑全套 alembic+seed）"
```

### Task 2.3: .env.example + DEPLOYMENT.md 切 PG 说明

**Files:**
- Modify: `backend/.env.example`
- Modify: `DEPLOYMENT.md`（§6.2）

- [ ] **Step 1: 更新 .env.example**

确认 `backend/.env.example` 的 `DATABASE_URL` 段落同时给出 SQLite 与 PG 两行、并把生产推荐标到 PG（保持 SQLite 行注释、PG 行为推荐）。示例：

```dotenv
# 本地快速开发可用 SQLite；生产强烈推荐 PostgreSQL（根治并发写锁）
# DATABASE_URL=sqlite:///./hankyu_hanshin.db
DATABASE_URL=postgresql+psycopg2://hankyu:CHANGE_ME@localhost:5432/hankyu_hanshin
```

- [ ] **Step 2: 更新 DEPLOYMENT.md §6.2**

在 §6.2 PostgreSQL 段，把 driver 明确成 `postgresql+psycopg2://`，并追加一句：「生产从 SQLite 切 PG 后必须按 §3.x 的迁移 runbook 执行（备份→切 URL→alembic+seed→客户重导运价）」。

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example DEPLOYMENT.md
git commit -m "docs(deploy): .env.example 默认推荐 PG + 切库说明"
```

### Task 2.4: PG 迁移上线 runbook

**Files:**
- Modify: `DEPLOYMENT.md`（新增 §3.7 「SQLite → PostgreSQL 迁移」）

- [ ] **Step 1: 写 runbook**

在 `DEPLOYMENT.md` §3 升级部署末尾新增 §3.7：

```markdown
### 3.7 SQLite → PostgreSQL 迁移（一次性，停机窗口）

> 决策：**不迁历史数据**。字典重 seed，客户把在用的运价重导一遍（已与业务确认）。

1. 备份现有 SQLite：`cp backend/hankyu_hanshin.db backend/hankyu_hanshin.db.bak.$(date +%Y%m%d-%H%M%S)`
2. 起 PG 并建库（见 §6.2），或复用 docker-compose 的 postgres。
3. 改 `backend/.env`：`DATABASE_URL=postgresql+psycopg2://hankyu:<pwd>@localhost:5432/hankyu_hanshin`
4. 迁移 + 灌字典：
   ```bash
   cd backend && ../.venv/bin/python -m alembic upgrade head && cd ..
   .venv/bin/python scripts/seed_data.py   # 期望 34 船司 / 140 港口
   ```
5. 重启后端：`sudo systemctl restart hankyu-backend`
6. 烟雾测试（§3.6）：health / carriers≥34 / 导一份运价端到端。
7. 通知客户：历史运价不保留，请重新导入在用运价。
8. 回滚：把 `.env` 的 `DATABASE_URL` 改回 SQLite 行并重启即可（SQLite 文件未动）。
```

- [ ] **Step 2: Commit**

```bash
git add DEPLOYMENT.md
git commit -m "docs(deploy): 新增 SQLite→PG 迁移 runbook（不迁历史，客户重导）"
```

> **Phase 2 milestone：** 跑通 `verify_pg_migrations.sh` 后，按 §3.7 runbook 在生产切 PG。根治 SQLite 全库写锁。

---

## Phase 3 — AI 异步化 + 限流 + 超时最终对齐

### Task 3.1: settings 新增 AI 并发上限

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_config_ai_concurrency.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_config_ai_concurrency.py`：

```python
"""AI 后台执行器并发上限默认值（兼限流），可被 env 覆盖。"""


def test_ai_max_concurrency_default():
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.ai_max_concurrency == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_config_ai_concurrency.py -v`
Expected: FAIL —— `AttributeError: 'Settings' object has no attribute 'ai_max_concurrency'`

- [ ] **Step 3: 实现**

在 `backend/app/core/config.py` 的 `ai_image_jpeg_quality` 行后新增：

```python
    # AI 后台执行器并发上限（兼限流）：同时打到单 GPU 的 AI 任务数，超出排队。
    # 默认 3，匹配单 GPU 并发能力；env 可覆盖 AI_MAX_CONCURRENCY。
    ai_max_concurrency: int = 3
```

- [ ] **Step 4: 跑测试确认通过 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_config_ai_concurrency.py -v`

```bash
git add backend/app/core/config.py backend/tests/test_config_ai_concurrency.py
git commit -m "feat(ai): 新增 ai_max_concurrency 配置（后台执行器并发上限/限流）"
```

### Task 3.2: AsyncTask 模型 + alembic 迁移

**Files:**
- Create: `backend/app/models/async_task.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260609_0001_async_tasks.py`
- Test: `backend/tests/test_async_task_model.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_async_task_model.py`：

```python
"""AsyncTask 模型：建表 + 默认状态 pending + JSON 结果列。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _mk_session(tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401  确保所有表注册

    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_async_task_defaults_pending_and_stores_json(tmp_path):
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    db = _mk_session(tmp_path)
    try:
        t = AsyncTask(id="abc123", task_type="parse_email_text")
        db.add(t)
        db.commit()
        got = db.get(AsyncTask, "abc123")
        assert got.status == AsyncTaskStatus.pending
        assert got.result_json is None
        got.status = AsyncTaskStatus.succeeded
        got.result_json = {"batch_id": "b1", "preview_rows": []}
        db.commit()
        assert db.get(AsyncTask, "abc123").result_json["batch_id"] == "b1"
    finally:
        db.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_async_task_model.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.models.async_task'`

- [ ] **Step 3: 实现 model**

创建 `backend/app/models/async_task.py`：

```python
"""AI 长任务的异步任务信令表。

只存「进度信令 + 完成后的 HTTP 响应体(result_json)」，不存大中间态。
AI 全量解析结果仍在内存 _parse_cache（单 worker 假设下安全）。
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AsyncTaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AsyncTask(Base):
    __tablename__ = "async_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="任务 UUID hex")
    task_type: Mapped[str] = mapped_column(String(50), comment="任务类型")
    status: Mapped[AsyncTaskStatus] = mapped_column(
        Enum(AsyncTaskStatus, native_enum=False),
        default=AsyncTaskStatus.pending,
        comment="任务状态",
    )
    result_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="成功时的响应体（=原 HTTP data）"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: 注册到 models/__init__.py**

在 `backend/app/models/__init__.py` 的 import 区加：

```python
from app.models.async_task import AsyncTask, AsyncTaskStatus
```

并在 `__all__` 列表加 `"AsyncTask", "AsyncTaskStatus",`。

- [ ] **Step 5: 写 alembic 迁移**

创建 `backend/alembic/versions/20260609_0001_async_tasks.py`：

```python
"""新增 async_tasks 表（AI 长任务异步化信令）

Revision ID: 20260609_0001
Revises: 20260601_0001
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260609_0001"
down_revision: Union[str, None] = "20260601_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "async_tasks",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("async_tasks")
```

- [ ] **Step 6: 跑测试确认通过 + alembic 自检**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_async_task_model.py -v`
Expected: PASS

Run: `cd backend && ../.venv/bin/python -m alembic upgrade head`
Expected: 无错（本地 SQLite 上也能跑该迁移）

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/async_task.py backend/app/models/__init__.py \
        backend/alembic/versions/20260609_0001_async_tasks.py \
        backend/tests/test_async_task_model.py
git commit -m "feat(ai): 新增 async_tasks 表（异步任务信令，result_json 存响应体）"
```

### Task 3.3: async_runner 后台执行器（独立线程池 + 状态机）

**Files:**
- Create: `backend/app/services/async_runner.py`
- Test: `backend/tests/test_async_runner.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_async_runner.py`：

```python
"""后台执行器：work 成功→succeeded+result_json；抛错→failed+error。

用 tmp-file SQLite + monkeypatch SessionLocal，保证后台线程与测试线程
看到同一个库（file 库跨线程可见）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _patch_sessionlocal(monkeypatch, tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401

    eng = create_engine(
        f"sqlite:///{tmp_path/'runner.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)

    import app.services.async_runner as ar
    monkeypatch.setattr(ar, "SessionLocal", TestSession)
    return TestSession


def test_submit_success_marks_succeeded(monkeypatch, tmp_path):
    import app.services.async_runner as ar
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    TestSession = _patch_sessionlocal(monkeypatch, tmp_path)
    db = TestSession()
    task_id = ar.create_task(db, "unit")
    db.close()

    fut = ar.submit(task_id, lambda task_db: {"ok": True})
    fut.result(timeout=5)

    check = TestSession()
    t = check.get(AsyncTask, task_id)
    assert t.status == AsyncTaskStatus.succeeded
    assert t.result_json == {"ok": True}
    check.close()


def test_submit_failure_marks_failed(monkeypatch, tmp_path):
    import app.services.async_runner as ar
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    TestSession = _patch_sessionlocal(monkeypatch, tmp_path)
    db = TestSession()
    task_id = ar.create_task(db, "unit")
    db.close()

    def boom(task_db):
        raise ValueError("explode")

    fut = ar.submit(task_id, boom)
    fut.result(timeout=5)

    check = TestSession()
    t = check.get(AsyncTask, task_id)
    assert t.status == AsyncTaskStatus.failed
    assert "explode" in (t.error or "")
    check.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_async_runner.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.services.async_runner'`

- [ ] **Step 3: 实现**

创建 `backend/app/services/async_runner.py`：

```python
"""AI 长任务后台执行器：与 FastAPI 请求线程池物理隔离的独立线程池。

设计要点：
- max_workers = settings.ai_max_concurrency，即 AI 并发上限（兼限流+排队）。
- work(task_db) 在后台线程跑，自带独立 DB session（请求 session 已随响应关闭）。
- work 返回的 dict 即「原 HTTP 响应体」，落 async_tasks.result_json 供前端轮询。
"""
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.async_task import AsyncTask, AsyncTaskStatus

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(
    max_workers=settings.ai_max_concurrency,
    thread_name_prefix="ai-task",
)


def create_task(db: Session, task_type: str) -> str:
    """在请求 session 内建一条 pending 任务，返回 task_id。"""
    task_id = uuid.uuid4().hex
    db.add(AsyncTask(id=task_id, task_type=task_type, status=AsyncTaskStatus.pending))
    db.commit()
    return task_id


def submit(task_id: str, work: Callable[[Session], dict]) -> Future:
    """把 work 丢进后台执行器。work 接收后台 DB session、返回响应体 dict。"""
    return _executor.submit(_run, task_id, work)


def _run(task_id: str, work: Callable[[Session], dict]) -> None:
    db = SessionLocal()
    try:
        task = db.get(AsyncTask, task_id)
        if task is None:
            logger.error("async task %s 不存在，跳过", task_id)
            return
        task.status = AsyncTaskStatus.running
        db.commit()
        try:
            data = work(db)
            task = db.get(AsyncTask, task_id)
            task.status = AsyncTaskStatus.succeeded
            task.result_json = data
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("async task %s 执行失败", task_id)
            db.rollback()
            task = db.get(AsyncTask, task_id)
            if task is not None:
                task.status = AsyncTaskStatus.failed
                task.error = str(exc)[:1000]
                db.commit()
    finally:
        db.close()
```

- [ ] **Step 4: 跑测试确认通过 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_async_runner.py -v`
Expected: PASS（两条）

```bash
git add backend/app/services/async_runner.py backend/tests/test_async_runner.py
git commit -m "feat(ai): 后台执行器 async_runner（独立线程池兼限流+DB状态机）"
```

### Task 3.4: GET /tasks/{id} 轮询端点

**Files:**
- Create: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/api_v1/test_tasks_endpoint.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/api_v1/test_tasks_endpoint.py`：

```python
"""轮询端点：未知 id → 404；已存在 → 返回 status/result/error。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def _client(tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401

    eng = create_engine(
        f"sqlite:///{tmp_path/'tasks.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app), TestSession


def test_unknown_task_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    try:
        resp = client.get("/api/v1/tasks/doesnotexist")
        assert resp.status_code == 200
        assert resp.json()["code"] == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_known_task_returns_status_and_result(tmp_path):
    from app.models.async_task import AsyncTask, AsyncTaskStatus

    client, TestSession = _client(tmp_path)
    try:
        db = TestSession()
        db.add(AsyncTask(
            id="t1", task_type="unit",
            status=AsyncTaskStatus.succeeded, result_json={"batch_id": "b1"},
        ))
        db.commit()
        db.close()

        resp = client.get("/api/v1/tasks/t1")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "succeeded"
        assert body["data"]["result"]["batch_id"] == "b1"
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_tasks_endpoint.py -v`
Expected: FAIL —— 404 路由不存在（FastAPI 返回 HTTP 404，`body["code"]` 断言失败）

- [ ] **Step 3: 实现端点**

创建 `backend/app/api/v1/tasks.py`：

```python
"""异步任务轮询端点。前端提交 AI 任务拿 task_id 后轮询此处直到终态。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.async_task import AsyncTask
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/tasks", tags=["async-tasks"])


@router.get("/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(AsyncTask, task_id)
    if task is None:
        return ApiResponse(code=404, message="任务不存在或已过期")
    status = task.status.value if hasattr(task.status, "value") else task.status
    return ApiResponse(data={
        "task_id": task.id,
        "status": status,
        "result": task.result_json,
        "error": task.error,
    })
```

- [ ] **Step 4: 注册路由**

在 `backend/app/api/v1/router.py` import 区加 `from app.api.v1.tasks import router as tasks_router`，并在末尾加 `router.include_router(tasks_router)`。

- [ ] **Step 5: 跑测试确认通过 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_tasks_endpoint.py -v`

```bash
git add backend/app/api/v1/tasks.py backend/app/api/v1/router.py \
        backend/tests/api_v1/test_tasks_endpoint.py
git commit -m "feat(ai): GET /tasks/{id} 异步任务轮询端点"
```

### Task 3.5: ai_parse 4 个 AI 端点异步化（提交即返回 task_id）

**Files:**
- Modify: `backend/app/api/v1/ai_parse.py`
- Test: `backend/tests/api_v1/test_ai_parse_async.py`

> 改造原则：① 提交端点内**先完成 UploadFile 落盘**（请求结束后 UploadFile 失效），再建任务、提交后台、返回 `{task_id}`；② 把原本的「解析 + 写 _parse_cache + 构造响应 data」搬进 `work(task_db)`，原响应 data 原样返回（落 result_json）；③ `no_rows` 等业务非异常情况也作为 **succeeded**，把 message/warnings 放进 result data，前端据此提示。

- [ ] **Step 1: 写守卫测试**

创建 `backend/tests/api_v1/test_ai_parse_async.py`：

```python
"""AI 端点异步化守卫：提交立即返回 task_id，真正解析在后台执行器跑。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def _client(tmp_path):
    from app.models.base import Base
    import app.models  # noqa: F401

    eng = create_engine(
        f"sqlite:///{tmp_path/'aip.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    # 后台 runner 也指向同一个库，保证轮询看得到结果
    import app.services.async_runner as ar
    ar_session = sessionmaker(bind=eng)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app), TestSession, ar, ar_session


def test_parse_email_text_returns_task_id_then_polls(tmp_path, monkeypatch):
    import app.api.v1.ai_parse as ai_parse
    from app.models.async_task import AsyncTaskStatus, AsyncTask

    client, TestSession, ar, ar_session = _client(tmp_path)
    monkeypatch.setattr(ar, "SessionLocal", ar_session)

    def fake_parse(text, db):
        return {
            "batch_id": "b1", "total_rows": 1, "parsed_rows": [{"x": 1}],
            "carrier_code": "C", "warnings": [],
        }

    monkeypatch.setattr(ai_parse, "parse_email_text", fake_parse)

    try:
        submit = client.post("/api/v1/ai/parse-email-text", data={"text": "hi"})
        assert submit.status_code == 200
        task_id = submit.json()["data"]["task_id"]
        assert task_id

        # 轮询直到终态
        import time
        for _ in range(50):
            poll = client.get(f"/api/v1/tasks/{task_id}").json()["data"]
            if poll["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert poll["status"] == "succeeded"
        assert poll["result"]["batch_id"] == "b1"
        assert poll["result"]["total_rows"] == 1
        assert len(poll["result"]["preview_rows"]) == 1  # parsed_rows 1 行 → preview 1 行
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_ai_parse_async.py -v`
Expected: FAIL —— 提交响应里没有 `data.task_id`（当前端点直接返回解析结果）

- [ ] **Step 3: 实现 — 加共享响应构造 + 改 4 端点**

在 `backend/app/api/v1/ai_parse.py` 顶部 import 区加：

```python
from app.services import async_runner
```

把 `_build_preview` 之外，新增三个「响应体构造」helper（放文件末尾 `_build_preview` 旁）：

```python
def _email_text_response(result: dict) -> dict:
    """parse-email-text 成功响应体（= 原 ApiResponse.data）。"""
    if not result["parsed_rows"]:
        return {"batch_id": None, "no_rows": True,
                "message": f"未能提取到费率数据。{'; '.join(result.get('warnings', []))}"}
    _parse_cache[result["batch_id"]] = result
    return {
        "batch_id": result["batch_id"],
        "file_name": "email_text_input",
        "source_type": "email_text",
        "carrier_code": result.get("carrier_code", ""),
        "total_rows": result["total_rows"],
        "preview_rows": _build_preview(result),
        "warnings": result.get("warnings", []),
        "sheets": [],
    }
```

然后把 `api_parse_email_text` 整体替换为：

```python
@router.post("/parse-email-text")
def api_parse_email_text(
    text: str = Form(..., description="邮件文本内容"),
    db: Session = Depends(get_db),
):
    """提交 AI 文本解析任务，立即返回 task_id（前端轮询 /tasks/{id}）。"""
    if not text.strip():
        return ApiResponse(code=400, message="文本内容不能为空")

    task_id = async_runner.create_task(db, "parse_email_text")

    def work(task_db: Session) -> dict:
        result = parse_email_text(text, task_db)
        return _email_text_response(result)

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

`api_parse_wechat_image`（保留 async + 落盘在请求内）替换为：

```python
@router.post("/parse-wechat-image")
async def api_parse_wechat_image(
    file: UploadFile = File(...),
    context: str = Form("", description="补充上下文（可选）"),
    db: Session = Depends(get_db),
):
    """落盘截图后提交 AI 视觉任务，立即返回 task_id。"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return ApiResponse(code=400, message="仅支持图片文件 (PNG/JPG/GIF/WebP)")

    os.makedirs(settings.upload_dir, exist_ok=True)
    save_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, save_name)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    fallback_name = file.filename
    task_id = async_runner.create_task(db, "parse_wechat_image")

    def work(task_db: Session) -> dict:
        result = parse_wechat_image(save_path, task_db, extra_context=context)
        if not result["parsed_rows"]:
            return {"batch_id": None, "no_rows": True,
                    "message": f"未能从截图中提取费率。{'; '.join(result.get('warnings', []))}"}
        _parse_cache[result["batch_id"]] = result
        return {
            "batch_id": result["batch_id"],
            "file_name": result.get("file_name", fallback_name),
            "source_type": "wechat_image",
            "carrier_code": result.get("carrier_code", ""),
            "total_rows": result["total_rows"],
            "preview_rows": _build_preview(result),
            "warnings": result.get("warnings", []),
            "sheets": [],
        }

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

`api_parse_inbox_email` 替换为（cache 校验在提交时做，解析进 work）：

```python
@router.post("/parse-inbox-email")
def api_parse_inbox_email(
    cache_key: str = Form(..., description="邮件缓存 key（来自 /inbox-emails 列表）"),
    db: Session = Depends(get_db),
):
    """提交邮件正文 AI 解析任务，立即返回 task_id。"""
    cached = _inbox_email_cache.get(cache_key)
    if not cached:
        return ApiResponse(code=404, message="邮件缓存已过期，请先重新拉取邮件列表")
    body = cached.get("body") or ""
    if not body.strip():
        return ApiResponse(code=400, message="该邮件正文为空，无法识别")

    subject = cached.get("subject", "")
    from_name = cached.get("from_name") or cached.get("from", "")
    date_str = (cached.get("date") or "")[:10]
    enriched_text = (
        f"【邮件主题】{subject}\n【发件人】{from_name}\n【日期】{date_str}\n\n{body}"
    )

    task_id = async_runner.create_task(db, "parse_inbox_email")

    def work(task_db: Session) -> dict:
        result = parse_email_text(enriched_text, task_db)
        if not result["parsed_rows"]:
            return {"batch_id": None, "no_rows": True,
                    "message": f"未能从邮件中提取到费率。{'; '.join(result.get('warnings', []))}"}
        safe_subject = (subject[:40] or "inbox_email").replace("/", "_").replace("\\", "_")
        result["file_name"] = f"📧 {safe_subject}"
        for row in result["parsed_rows"]:
            row["source_file"] = result["file_name"]
        _parse_cache[result["batch_id"]] = result
        return {
            "batch_id": result["batch_id"],
            "file_name": result["file_name"],
            "source_type": "inbox_email",
            "carrier_code": result.get("carrier_code", ""),
            "total_rows": result["total_rows"],
            "preview_rows": _build_preview(result),
            "warnings": result.get("warnings", []),
            "sheets": [],
            "email_meta": {"subject": subject, "from": from_name, "date": date_str},
        }

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

`api_parse_inbox_attachment` 替换为（附件二进制在提交时落盘，解析进 work）：

```python
@router.post("/parse-inbox-attachment")
def api_parse_inbox_attachment(
    cache_key: str = Form(..., description="邮件缓存 key"),
    attachment_index: int = Form(..., description="image_attachments 数组下标"),
    db: Session = Depends(get_db),
):
    """落盘邮件图片附件后提交 AI 视觉任务，立即返回 task_id。"""
    cached = _inbox_email_cache.get(cache_key)
    if not cached:
        return ApiResponse(code=404, message="邮件缓存已过期，请先重新拉取邮件列表")
    image_list = cached.get("image_attachments") or []
    if attachment_index < 0 or attachment_index >= len(image_list):
        return ApiResponse(code=400, message="附件下标越界")
    image = image_list[attachment_index]
    data: bytes = image.get("data") or b""
    if not data:
        return ApiResponse(code=400, message="附件内容为空")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = image.get("filename", f"attachment_{attachment_index}.png")
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    save_name = f"inbox_{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(settings.upload_dir, save_name)
    with open(save_path, "wb") as f:
        f.write(data)

    subject = cached.get("subject", "")
    from_name = cached.get("from_name") or cached.get("from", "")
    extra_context = f"该图片来自邮件「{subject}」，发件人 {from_name}。"
    img_filename = image.get("filename", "")

    task_id = async_runner.create_task(db, "parse_inbox_attachment")

    def work(task_db: Session) -> dict:
        result = parse_wechat_image(save_path, task_db, extra_context=extra_context)
        if not result["parsed_rows"]:
            return {"batch_id": None, "no_rows": True,
                    "message": f"未能从邮件附件图片中提取费率。{'; '.join(result.get('warnings', []))}"}
        safe_subject = (subject[:30] or "inbox_image").replace("/", "_").replace("\\", "_")
        result["file_name"] = f"📎 {safe_subject} - {img_filename}"
        for row in result["parsed_rows"]:
            row["source_file"] = result["file_name"]
        _parse_cache[result["batch_id"]] = result
        return {
            "batch_id": result["batch_id"],
            "file_name": result["file_name"],
            "source_type": "inbox_attachment",
            "carrier_code": result.get("carrier_code", ""),
            "total_rows": result["total_rows"],
            "preview_rows": _build_preview(result),
            "warnings": result.get("warnings", []),
            "sheets": [],
            "email_meta": {"subject": subject, "from": from_name, "attachment": img_filename},
        }

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

> `/ai/parse-wechat-image` 旧守卫测试 `test_parse_wechat_image_offloads_ai`（`tests/api_v1/test_async_routes_threadpool.py`）会失效——它断言 `parse_wechat_image` 不在 event loop 线程；异步化后该函数已不在请求内调用。**Step 4 处理它。**

- [ ] **Step 4: 修旧守卫测试**

`parse-wechat-image` 不再于请求内调用 `parse_wechat_image`，旧探针 `test_parse_wechat_image_offloads_ai` 不再适用。从 `tests/api_v1/test_async_routes_threadpool.py` 删除 `test_parse_wechat_image_offloads_ai` 函数（新行为由 `test_ai_parse_async.py` 覆盖）。其余探针（rate_sheet/rate_batch/bidding/upload_msg）保留。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_ai_parse_async.py tests/api_v1/test_async_routes_threadpool.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/ai_parse.py backend/tests/api_v1/test_ai_parse_async.py \
        backend/tests/api_v1/test_async_routes_threadpool.py
git commit -m "feat(ai): ai_parse 4 个 AI 端点异步化（提交即返回 task_id+后台执行）"
```

### Task 3.6: rate-sheet /files 异步化

**Files:**
- Modify: `backend/app/api/v1/rate_sheet.py:48-90`（`upload_rate_sheet_files`）
- Test: `backend/tests/api_v1/test_rate_sheet_async.py`

- [ ] **Step 1: 读现状**

Run: `sed -n '40,110p' backend/app/api/v1/rate_sheet.py`
确认 `upload_rate_sheet_files` 现在用 `run_in_threadpool(orchestrator.add_file, ...)` 逐个文件抽取、最后返回汇总。记录它返回的响应 data 结构（供 work 原样返回）。

- [ ] **Step 2: 写守卫测试**

创建 `backend/tests/api_v1/test_rate_sheet_async.py`：

```python
"""rate-sheet /files 异步化守卫：提交立即返回 task_id。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def test_rate_sheet_files_returns_task_id(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models  # noqa: F401
    from app.services.step1_rates.sheet_builder import orchestrator
    import app.services.async_runner as ar

    eng = create_engine(
        f"sqlite:///{tmp_path/'rs.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    monkeypatch.setattr(ar, "SessionLocal", TestSession)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db

    session = orchestrator.create_session("air")
    monkeypatch.setattr(orchestrator, "add_file", lambda *a, **k: orchestrator.FileResult(
        name="a.xlsx", source_type="excel", status="parsed"))

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/rate-sheet/{session.session_id}/files",
            files={"files": ("a.xlsx", b"x", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_async.py -v`
Expected: FAIL —— 响应无 `data.task_id`

- [ ] **Step 4: 实现**

在 `backend/app/api/v1/rate_sheet.py` import 区加 `from app.services import async_runner`（`run_in_threadpool` 仍被 `download_into_template` 使用，保留）。把 `upload_rate_sheet_files` 整体替换为：

```python
@router.post("/{session_id}/files")
async def upload_rate_sheet_files(
    session_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """落盘一批杂料后提交抽取任务，立即返回 task_id（前端轮询 /tasks/{id}）。"""
    try:
        orchestrator.get_session(session_id)
    except KeyError:
        return ApiResponse(code=404, message="会话不存在或已过期，请重新创建")

    os.makedirs(settings.upload_dir, exist_ok=True)
    # UploadFile 请求结束即失效：先把所有文件落盘，记录 (原名, 落盘路径)
    saved: list[tuple[str, str]] = []
    for upload in files:
        original_name = upload.filename or "file"
        safe_name = original_name.replace("/", "_").replace("\\", "_")
        save_name = f"ratesheet_{uuid.uuid4().hex[:8]}_{safe_name}"
        save_path = os.path.join(settings.upload_dir, save_name)
        content = await upload.read()
        with open(save_path, "wb") as fh:
            fh.write(content)
        saved.append((original_name, save_path))

    task_id = async_runner.create_task(db, "rate_sheet_files")

    def work(task_db: Session) -> dict:
        session = orchestrator.get_session(session_id)
        results = []
        for original_name, save_path in saved:
            file_result = orchestrator.add_file(
                session_id, original_name, save_path, task_db
            )
            results.append({
                "name": file_result.name,
                "source_type": file_result.source_type,
                "status": file_result.status,
                "row_count": file_result.row_count,
                "warnings": file_result.warnings,
                "message": file_result.message,
            })
        needs_review = sum(1 for r in session.rows if r.get("needs_review"))
        return {
            "files": results,
            "summary": {
                "total_rows": len(session.rows),
                "needs_review": needs_review,
            },
        }

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

- [ ] **Step 5: 跑测试确认通过 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_rate_sheet_async.py -v`

```bash
git add backend/app/api/v1/rate_sheet.py backend/tests/api_v1/test_rate_sheet_async.py
git commit -m "feat(ai): rate-sheet /files 抽取异步化（提交即返回 task_id）"
```

### Task 3.7: bidding /auto-fill 异步化

**Files:**
- Modify: `backend/app/api/v1/bidding.py:36-66`（`auto_fill`）
- Test: `backend/tests/api_v1/test_bidding_async.py`

- [ ] **Step 1: 读现状**

Run: `sed -n '30,120p' backend/app/api/v1/bidding.py`
确认 `auto_fill` 现在 `await file.read()` → `run_in_threadpool(_process_auto_fill, content, lower, db)` → 返回 `BiddingAutoFillResponse`。记录 `_process_auto_fill` 返回结构（即 result_json）。

- [ ] **Step 2: 写守卫测试**

创建 `backend/tests/api_v1/test_bidding_async.py`：

```python
"""bidding /auto-fill 异步化守卫：提交立即返回 task_id。"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def test_auto_fill_returns_task_id(tmp_path, monkeypatch):
    from app.models.base import Base
    import app.models  # noqa: F401
    import app.api.v1.bidding as bidding
    import app.services.async_runner as ar

    eng = create_engine(
        f"sqlite:///{tmp_path/'bid.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng)
    monkeypatch.setattr(ar, "SessionLocal", TestSession)

    def _db():
        d = TestSession()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(bidding, "_process_auto_fill",
                        lambda content, lower, db: {"ok": True})

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/bidding/auto-fill",
            files={"file": ("bid.xlsx", b"x", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
```

> 注意：现状 `auto_fill` 直接返回 `BiddingAutoFillResponse`（非 ApiResponse 包装）。异步化后提交端点改为返回 `ApiResponse(data={"task_id": ...})`；前端 `biddingApi.autoFill` 在 Task 3.9 改为「提交+轮询」后，pollTask 返回的 result_json 即原 `BiddingAutoFillResponse` 结构，前端签名不变。

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_bidding_async.py -v`
Expected: FAIL —— 响应无 `data.task_id`

- [ ] **Step 4: 实现**

在 `backend/app/api/v1/bidding.py` import 区加 `from app.services import async_runner` 和 `from app.schemas.common import ApiResponse`。把 `auto_fill` 整体替换为（注意去掉 `response_model=`，因为现在返回 ApiResponse）：

```python
@router.post("/auto-fill")
async def auto_fill(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """提交投标包自动填入任务，立即返回 task_id（前端轮询 /tasks/{id}）。

    扩展名/大小校验仍同步即时返回：F7→400、F6→413；
    identify→parse→match→fill 的降级由轮询结果的 ok/error 区分。
    """
    filename = file.filename or ""
    lower = filename.lower()
    if not lower.endswith(_ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail=f"F7_WRONG_EXTENSION: only .xlsx / .xlsm / .zip allowed (got {filename!r})",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"F6_FILE_TOO_LARGE: {len(content)} bytes > "
                f"{_MAX_UPLOAD_BYTES} bytes limit"
            ),
        )

    task_id = async_runner.create_task(db, "bidding_auto_fill")

    def work(task_db: Session) -> dict:
        resp = _process_auto_fill(content, lower, task_db)
        # BiddingAutoFillResponse(pydantic) → dict 落 result_json（JSON 可序列化）
        return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)

    async_runner.submit(task_id, work)
    return ApiResponse(data={"task_id": task_id})
```

`_process_auto_fill` 函数本身不变（仍同步执行落盘/解压/填表），只是改由后台执行器调用、不再 `run_in_threadpool`。

> 旧守卫 `test_bidding_auto_fill_offloads`（test_async_routes_threadpool.py）断言 `run_auto_fill` 不在 loop 线程——异步化后 `_process_auto_fill` 已不在请求内调用。从该测试文件删除 `test_bidding_auto_fill_offloads`（新行为由 test_bidding_async.py 覆盖）。

- [ ] **Step 5: 跑测试确认通过 + Commit**

Run: `cd backend && ../.venv/bin/python -m pytest tests/api_v1/test_bidding_async.py tests/api_v1/test_async_routes_threadpool.py -v`

```bash
git add backend/app/api/v1/bidding.py backend/tests/api_v1/test_bidding_async.py \
        backend/tests/api_v1/test_async_routes_threadpool.py
git commit -m "feat(ai): bidding /auto-fill 异步化（提交即返回 task_id）"
```

### Task 3.8: 前端 pollTask 轮询工具

**Files:**
- Create: `frontend/src/services/asyncTask.ts`

- [ ] **Step 1: 实现**

创建 `frontend/src/services/asyncTask.ts`：

```typescript
import api from './api';
import type { ApiResponse } from '../types';

interface TaskState {
  task_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  result: unknown;
  error: string | null;
}

/**
 * 轮询异步任务直到终态。
 * @returns 成功时返回后台任务的 result（= 原 HTTP 响应 data）。
 */
export async function pollTask(
  taskId: string,
  opts?: { interval?: number; timeout?: number }
): Promise<unknown> {
  const interval = opts?.interval ?? 1500;
  const timeout = opts?.timeout ?? 300000;
  const start = Date.now();

  for (;;) {
    const resp = (await api.get<unknown, ApiResponse>(`/tasks/${taskId}`)) as ApiResponse;
    const state = resp.data as TaskState;
    if (state.status === 'succeeded') return state.result;
    if (state.status === 'failed') throw new Error(state.error || 'AI 处理失败');
    if (Date.now() - start > timeout) throw new Error('AI 处理超时，请稍后重试');
    await new Promise((r) => setTimeout(r, interval));
  }
}
```

- [ ] **Step 2: lint + Commit**

Run: `cd frontend && npm run lint`

```bash
git add frontend/src/services/asyncTask.ts
git commit -m "feat(fe): pollTask 异步任务轮询工具"
```

### Task 3.9: api.ts 6 处调用改「提交+轮询」（保持签名零页面改动）

**Files:**
- Modify: `frontend/src/services/api.ts`（`aiParseApi` 4 处 + `rateSheetApi.uploadFiles` + `biddingApi.autoFill`）

> 策略：每个函数内部「提交拿 task_id → pollTask → 重新包成 `{code:0, data: result, message:'ok'}`」，对外返回类型不变，**页面组件零改动**。

- [ ] **Step 1: 引入 pollTask**

在 `frontend/src/services/api.ts` 顶部加 `import { pollTask } from './asyncTask';`。

- [ ] **Step 2: 改 aiParseApi.parseEmailText**

```typescript
  parseEmailText: async (text: string): Promise<ApiResponse> => {
    const formData = new FormData();
    formData.append('text', text);
    const submit = (await api.post<unknown, ApiResponse>('/ai/parse-email-text', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return { code: 0, data: result, message: 'ok' } as ApiResponse;
  },
```

- [ ] **Step 3: 改 aiParseApi.parseWechatImage**

```typescript
  parseWechatImage: async (file: File, context?: string): Promise<ApiResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (context) formData.append('context', context);
    const submit = (await api.post<unknown, ApiResponse>('/ai/parse-wechat-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return { code: 0, data: result, message: 'ok' } as ApiResponse;
  },
```

- [ ] **Step 4: 改 aiParseApi.parseInboxEmail**

```typescript
  parseInboxEmail: async (cacheKey: string): Promise<ApiResponse> => {
    const formData = new FormData();
    formData.append('cache_key', cacheKey);
    const submit = (await api.post<unknown, ApiResponse>('/ai/parse-inbox-email', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return { code: 0, data: result, message: 'ok' } as ApiResponse;
  },
```

- [ ] **Step 5: 改 aiParseApi.parseInboxAttachment**

```typescript
  parseInboxAttachment: async (cacheKey: string, attachmentIndex: number): Promise<ApiResponse> => {
    const formData = new FormData();
    formData.append('cache_key', cacheKey);
    formData.append('attachment_index', String(attachmentIndex));
    const submit = (await api.post<unknown, ApiResponse>('/ai/parse-inbox-attachment', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return { code: 0, data: result, message: 'ok' } as ApiResponse;
  },
```

- [ ] **Step 6: 改 rateSheetApi.uploadFiles**

```typescript
  uploadFiles: async (sessionId: string, files: File[]): Promise<ApiResponse> => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    const submit = (await api.post<unknown, ApiResponse>(`/rate-sheet/${sessionId}/files`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return { code: 0, data: result, message: 'ok' } as ApiResponse;
  },
```

- [ ] **Step 7: 改 biddingApi.autoFill**

```typescript
  autoFill: async (
    file: File,
    onUploadProgress?: (percent: number) => void
  ): Promise<BiddingAutoFillResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const submit = (await api.post<unknown, ApiResponse>('/bidding/auto-fill', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (!onUploadProgress) return;
        const total = evt.total || file.size || 1;
        const pct = Math.min(100, Math.round(((evt.loaded || 0) / total) * 100));
        onUploadProgress(pct);
      },
    })) as ApiResponse;
    const taskId = (submit.data as { task_id: string }).task_id;
    const result = await pollTask(taskId);
    return result as BiddingAutoFillResponse;
  },
```

- [ ] **Step 8: 验证页面消费未破坏**

读 `frontend/src/pages/RateUpload.tsx` 中 `parseEmailText/parseWechatImage/parseInboxEmail/parseInboxAttachment` 的调用点（行 327/365/380/413 附近），确认它们用 `res.data.xxx`（包装后仍成立）。重点确认 `no_rows` 分支：原同步返回 `code=200 + data=result + message`；现在成功 data 里带 `no_rows: true` 与 `message`。若页面靠 `res.message` 或 `res.data.preview_rows.length` 判空，逻辑仍成立（`no_rows` data 无 `preview_rows`→读取为 undefined）。**如发现页面依赖 `res.message` 文案，在此微调页面读 `res.data.message`。**

- [ ] **Step 9: lint + build + Commit**

Run: `cd frontend && npm run lint && npm run build`
Expected: 通过

```bash
git add frontend/src/services/api.ts frontend/src/pages/RateUpload.tsx
git commit -m "feat(fe): 6个AI调用改提交+轮询(保持ApiResponse签名,页面零改动)"
```

### Task 3.10: 超时最终对齐（异步化红利）

**Files:**
- Modify: `frontend/src/services/api.ts`（去掉 AI 端点的 120/180s 长 timeout）
- Modify: `DEPLOYMENT.md`（nginx 300s → 60s）

- [ ] **Step 1: 前端去长超时**

`frontend/src/services/api.ts` 中，已异步化的 6 个调用现在都是「短提交 + 短轮询」，移除它们残留的 `timeout: 120000/180000`（若上面重写时已无则跳过）。轮询端点走 axios 默认 60s 足够。`rateSheetApi.preview/downloadFilled/downloadIntoTemplate`（大 JSON，非 AI）**保留** 180s。

- [ ] **Step 2: nginx 回 60s**

`DEPLOYMENT.md` §2.7 把过渡的 `proxy_read_timeout 300s` 改回：

```nginx
    # 异步化(Phase3)后所有请求都短（提交+轮询），回到常规 60s。
    # 例外：rate-sheet 大 JSON preview/download 仍可能久，如需可单独 location 放宽。
    proxy_read_timeout 60s;
```

- [ ] **Step 3: lint + build + Commit**

Run: `cd frontend && npm run lint && npm run build`

```bash
git add frontend/src/services/api.ts DEPLOYMENT.md
git commit -m "perf: 异步化后超时三层对齐（前端去长超时 + nginx 回 60s）"
```

### Task 3.11: 全量回归 + 并发烟雾验证

**Files:** 无（验证）

- [ ] **Step 1: 后端全量**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: 全绿（既有 452 - 删除的 2 个旧探针 + 新增约 8 个）

- [ ] **Step 2: 前端**

Run: `cd frontend && npm run lint && npm run build`
Expected: 通过

- [ ] **Step 3: 并发烟雾（本地，可选但推荐）**

本地起后端（SQLite 即可），用浏览器或脚本同时发：1 个 AI 解析（慢）+ 连续多个 `GET /api/v1/carriers`（轻）。预期：AI 解析期间轻查询**不被阻塞**（毫秒级返回），AI 任务在 `/tasks/{id}` 轮询到 succeeded。

- [ ] **Step 4: Commit（若有验证脚本/文档微调）**

```bash
git add -A && git commit -m "test: 并发根治全量回归 + 烟雾验证通过" || echo "无改动可提交"
```

> **Phase 3 milestone：** AI 长任务不再占 HTTP 连接/线程槽，轻请求全程畅通；超时倒挂消除。三个根因全部根治。

---

## 上线总顺序回顾
1. **Phase 1**（WAL + nginx 300s 过渡）→ 立刻缓解，零风险。
2. **Phase 2**（按 §3.7 runbook 切 PG）→ 根治写锁，停机窗口 + 客户重导。
3. **Phase 3**（异步化 + 限流 + 超时回调）→ 前后端一起部署（前端必 `npm run build` + 拷 dist + reload nginx，见 DEPLOYMENT §3.4）。

## 部署注意（来自 DEPLOYMENT.md 最常踩坑）
- 后端改动必 `systemctl restart hankyu-backend`；前端改动必 `npm run build` + 拷 `dist/` + `nginx reload`，少一步等于没改。
- Phase 2 切 PG 后必跑 `seed_data.py`，否则字典空→导入全 `CARRIER_NOT_FOUND`。
- `async_tasks` 表随 alembic 迁移自动建；生产走 alembic（非 init_db）。
