"""数据库连接管理"""
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=connect_args,
)


def _apply_sqlite_pragmas(dbapi_conn: Any) -> None:
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

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """获取数据库 Session（用于 FastAPI 依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表（开发环境用）"""
    from app.models import Base
    Base.metadata.create_all(bind=engine)
