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
