"""Task 8 — 操作记录盖章测试。

验证 import_parsed_rates 支持 operator_email 并写入 upload_logs.uploaded_by。
"""

from app.services.rate_parser import import_parsed_rates


def test_import_parsed_rates_accepts_operator_email(tmp_path):
    """import_parsed_rates 支持 operator_email，并写入 upload_logs.uploaded_by。"""
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base
    from app.models.upload_log import UploadLog

    engine = create_engine(
        f"sqlite:///{tmp_path / 'st.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    parsed = {
        "batch_id": str(uuid.uuid4()),
        "file_name": "x.xlsx",
        "file_type": "xlsx",
        "source_type": "excel",
        "rates": [],
        "parsed_rows": [],
    }
    import_parsed_rates(parsed, db, operator_email="ops@x.com")

    log = db.query(UploadLog).first()
    assert log is not None
    assert log.uploaded_by == "ops@x.com"


def test_import_parsed_rates_operator_email_defaults_none(tmp_path):
    """不传 operator_email 时，uploaded_by 为 None（向后兼容）。"""
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base
    from app.models.upload_log import UploadLog

    engine = create_engine(
        f"sqlite:///{tmp_path / 'st2.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    parsed = {
        "batch_id": str(uuid.uuid4()),
        "file_name": "y.xlsx",
        "file_type": "xlsx",
        "source_type": "excel",
        "rates": [],
        "parsed_rows": [],
    }
    import_parsed_rates(parsed, db)

    log = db.query(UploadLog).first()
    assert log is not None
    assert log.uploaded_by is None
