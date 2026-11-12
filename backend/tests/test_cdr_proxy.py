"""Security tests for the CDR proxy layer.

These tests verify the security invariants in cdr_proxy.py without reaching
any CDR backend: the proxy function is patched to record what it was called with.
They also do not require the test database — proxy endpoints only validate the
cdr_session cookie JWT, with no DB queries.
"""
import datetime as dt
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi.responses import JSONResponse

TEST_JWT_SECRET = "test-only-jwt-secret-0123456789abcdefghijklmnop"
COOKIE_NAME = "cdr_session"


def _make_cookie(
    case_id: str = "CASE-001",
    subject: str = "analyst1",
    analyst_id: str = "server-side-analyst-id",
    role: str = "analyst",
    expired: bool = False,
) -> str:
    now = dt.datetime.now(dt.UTC)
    exp = now - dt.timedelta(hours=1) if expired else now + dt.timedelta(hours=1)
    payload = {
        "purpose": "cdr_session",
        "sub": subject,
        "analyst_id": analyst_id,
        "role": role,
        "case_id": case_id,
        "iat": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def _ok():
    return JSONResponse({"ok": True})


@pytest.fixture(scope="module")
def proxy_app():
    """FastAPI app with the DB dependency mocked — proxy routes don't use the DB."""
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield app
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def pc(proxy_app):
    """Lightweight TestClient for CDR proxy endpoint tests."""
    from fastapi.testclient import TestClient

    with TestClient(proxy_app, raise_server_exceptions=False) as client:
        yield client


class TestD1ProxySecurity:
    """CDR D1 proxy rejects unauthenticated and expired requests."""

    def test_no_cookie_returns_401(self, pc):
        response = pc.get("/api/cdr/proxy/d1/health")
        assert response.status_code == 401

    def test_expired_cookie_returns_401(self, pc):
        cookie = _make_cookie(expired=True)
        response = pc.get("/api/cdr/proxy/d1/health", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 401

    def test_valid_cookie_reaches_proxy(self, pc):
        cookie = _make_cookie(case_id="CASE-001")
        with patch("app.api.cdr_proxy._proxy", return_value=_ok()):
            response = pc.get("/api/cdr/proxy/d1/upload", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 200


class TestD2ProxySecurity:
    """CDR D2 proxy enforces auth and injects analyst identity from the session."""

    def test_no_cookie_returns_401(self, pc):
        response = pc.get("/api/cdr/proxy/d2/search")
        assert response.status_code == 401

    def test_expired_cookie_returns_401(self, pc):
        cookie = _make_cookie(expired=True)
        response = pc.get("/api/cdr/proxy/d2/search", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 401

    def test_case_mismatch_returns_403(self, pc):
        # Cookie is for CASE-001; query param says CASE-002.
        cookie = _make_cookie(case_id="CASE-001")
        response = pc.get(
            "/api/cdr/proxy/d2/search?case_id=CASE-002",
            cookies={COOKIE_NAME: cookie},
        )
        assert response.status_code == 403

    def test_x_analyst_id_comes_from_session_not_browser(self, pc):
        """X-Analyst-Id forwarded to D2 must be from the session, not the browser header."""
        captured: dict = {}

        async def fake_proxy(request, target_url, extra_headers=None):
            captured["extra"] = extra_headers or {}
            return _ok()

        cookie = _make_cookie(case_id="CASE-001", analyst_id="server-side-analyst-id")
        with patch("app.api.cdr_proxy._proxy", new=fake_proxy):
            pc.get(
                "/api/cdr/proxy/d2/search?case_id=CASE-001",
                cookies={COOKIE_NAME: cookie},
                headers={"X-Analyst-Id": "attacker-forged-id"},
            )
        # The proxy sees the session analyst_id, never the browser-supplied one.
        assert captured["extra"].get("x-analyst-id") == "server-side-analyst-id"


class TestD3ProxySecurity:
    """CDR D3 proxy enforces that the URL case_id matches the session case_id."""

    def test_no_cookie_returns_401(self, pc):
        response = pc.get("/api/cdr/cases/CASE-001/tower-data")
        assert response.status_code == 401

    def test_expired_cookie_returns_401(self, pc):
        cookie = _make_cookie(expired=True)
        response = pc.get("/api/cdr/cases/CASE-001/tower-data", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 401

    def test_case_id_mismatch_returns_403(self, pc):
        # Cookie is for CASE-001; URL path says CASE-002.
        cookie = _make_cookie(case_id="CASE-001")
        response = pc.get("/api/cdr/cases/CASE-002/tower-data", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 403

    def test_matching_case_id_passes_and_routes_to_d3(self, pc):
        """When URL case_id matches the cookie, the request is forwarded with the correct target."""
        captured: dict = {}

        async def fake_proxy(request, target_url, extra_headers=None):
            captured["url"] = target_url
            return _ok()

        cookie = _make_cookie(case_id="CASE-001")
        with patch("app.api.cdr_proxy._proxy", new=fake_proxy):
            response = pc.get("/api/cdr/cases/CASE-001/tower-data", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 200
        assert "CASE-001" in captured.get("url", "")
        assert "tower-data" in captured.get("url", "")

    def test_different_case_in_cookie_cannot_access_another_case(self, pc):
        """A cookie minted for CASE-XYZ cannot be reused to access CASE-ABC."""
        cookie = _make_cookie(case_id="CASE-XYZ")
        response = pc.get("/api/cdr/cases/CASE-ABC/data", cookies={COOKIE_NAME: cookie})
        assert response.status_code == 403
