"""Step 14.2: API response headers, the per-computer login limit, and refusing unsafe production settings."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.ratelimit import FailedLoginLimiter, get_login_limiter
from app.core.config import Settings
from app.db.models import AuditEvent
from conftest import TEST_PASSWORD

STRONG = "x" * 40  # long enough for every secret setting


def login(client, username, password=TEST_PASSWORD):
    return client.post("/api/auth/token", data={"username": username, "password": password})


@pytest.mark.parametrize("path", ["/api/health", "/api/cases", "/api/no-such-endpoint"])
def test_api_responses_must_not_be_cached_or_sniffed(anonymous_api, path):
    response = anonymous_api.get(path)  # a success, a "log in first" and a "not found"

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_one_computer_trying_many_accounts_is_slowed_down(anonymous_api, app_overrides, make_user, db_session):
    limiter = FailedLoginLimiter(limit=3, window_seconds=900)
    app_overrides.dependency_overrides[get_login_limiter] = lambda: limiter
    make_user("alice")
    for name in ("bob", "carol", "dave"):  # three different accounts, one wrong password each
        assert login(anonymous_api, name, "guess").status_code == 401

    blocked = login(anonymous_api, "alice")  # even the right password, for an account never tried

    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many failed logins from this computer. Try again in a few minutes."}
    assert 0 < int(blocked.headers["Retry-After"]) <= 900
    reasons = [e.details.get("reason") for e in db_session.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login"))]
    assert reasons[-1] == "too_many_failures_from_address"


def test_successful_logins_are_not_counted(anonymous_api, app_overrides, make_user):
    limiter = FailedLoginLimiter(limit=2, window_seconds=900)
    app_overrides.dependency_overrides[get_login_limiter] = lambda: limiter
    make_user("alice")

    assert all(login(anonymous_api, "alice").status_code == 200 for _ in range(5))


def test_the_limit_is_per_address_and_wears_off():
    now = [0.0]
    limiter = FailedLoginLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("10.0.0.1")
    limiter.record_failure("10.0.0.1")

    assert limiter.blocked("10.0.0.1")
    assert not limiter.blocked("10.0.0.2")  # another computer is not affected
    assert limiter.retry_after("10.0.0.1") == 60
    now[0] = 61
    assert not limiter.blocked("10.0.0.1")
    assert limiter._failures == {}  # nothing kept once the window has passed


def settings(**values) -> Settings:
    base = {"postgres_password": STRONG, "jwt_secret": STRONG + "jwt", "audit_secret": STRONG + "audit"}
    return Settings(_env_file=None, **{**base, **values})


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"jwt_secret": STRONG, "audit_secret": STRONG}, "JWT_SECRET and AUDIT_SECRET must be different"),
        ({"postgres_password": "change-me"}, "POSTGRES_PASSWORD must be at least 16 characters"),
        ({"postgres_password": "short-password"}, "POSTGRES_PASSWORD must be at least 16 characters"),
    ],
)
def test_a_real_installation_refuses_unsafe_settings(values, problem):
    with pytest.raises(ValidationError, match=problem):
        settings(environment="production", **values)


def test_development_settings_are_allowed_on_a_developers_computer():
    assert settings(environment="development", postgres_password="change-me").environment == "development"
    assert settings(environment="production").environment == "production"


def test_an_empty_audit_retention_setting_means_keep_audit_entries():
    # Docker Compose passes an unset variable as "" (docker-compose.yml: AUDIT_RETENTION_DAYS).
    assert settings(audit_retention_days="").audit_retention_days is None
    assert settings(audit_retention_days="365").audit_retention_days == 365
