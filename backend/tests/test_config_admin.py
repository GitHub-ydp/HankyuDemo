from app.core import config


def test_is_admin_email_reads_live_and_normalizes(monkeypatch):
    monkeypatch.setattr(config.settings, "admin_emails", "Boss@Hankyu.co.jp, ops@x.com")
    assert config.is_admin_email("boss@hankyu.co.jp") is True
    assert config.is_admin_email("  OPS@X.COM ") is True
    assert config.is_admin_email("nobody@x.com") is False


def test_is_admin_email_empty_list(monkeypatch):
    monkeypatch.setattr(config.settings, "admin_emails", "")
    assert config.is_admin_email("anyone@x.com") is False
