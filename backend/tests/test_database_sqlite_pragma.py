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
        cur.close()
        conn.close()
