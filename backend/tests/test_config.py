def test_admin_emails_parses_csv(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "alice@test.com,bob@test.com")
    from app.config import settings
    assert settings.ADMIN_EMAILS == ["alice@test.com", "bob@test.com"]


def test_admin_emails_strips_whitespace(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " alice@test.com , bob@test.com ")
    from app.config import settings
    assert settings.ADMIN_EMAILS == ["alice@test.com", "bob@test.com"]


def test_admin_emails_empty_string_returns_empty_list(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "")
    from app.config import settings
    assert settings.ADMIN_EMAILS == []


def test_admin_emails_unset_returns_empty_list(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    from app.config import settings
    assert settings.ADMIN_EMAILS == []
