"""Tests for the CDR session bridge endpoint.

All tests use a lightweight fixture that bypasses the test database — the session
endpoint's security logic (auth required, case access check, cookie issuance)
can be verified with mocked dependencies and get_visible_case patches.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def session_app():
    """App with DB and auth dependencies mocked — session tests need no real DB."""
    from app.auth.dependencies import get_access_context, get_current_user
    from app.db.session import get_db
    from app.main import app

    fake_user = MagicMock()
    fake_user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    fake_user.username = "analyst1"
    fake_user.display_name = "Test Analyst"
    fake_user.role = "analyst"
    fake_user.clearance = "public"
    fake_user.is_active = True

    fake_access = MagicMock()

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_access_context] = lambda: fake_access
    yield app
    for dep in (get_db, get_current_user, get_access_context):
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def anon(session_app):
    """Unauthenticated test client."""
    from fastapi.testclient import TestClient

    # Temporarily remove the CurrentUser override so the endpoint returns 401.
    from app.auth.dependencies import get_current_user

    overrides_backup = session_app.dependency_overrides.pop(get_current_user, None)
    with TestClient(session_app, raise_server_exceptions=False) as client:
        yield client
    if overrides_backup is not None:
        session_app.dependency_overrides[get_current_user] = overrides_backup


@pytest.fixture
def authed(session_app):
    """Authenticated test client (analyst with public clearance)."""
    from fastapi.testclient import TestClient

    with TestClient(session_app, raise_server_exceptions=False) as client:
        yield client


VISIBLE_CASE_ID = "SC-2023-VISIBLE"
HIDDEN_CASE_ID = "SC-2023-HIDDEN"


class TestCdrSessionEndpoint:
    """Test /api/cdr/session case access enforcement."""

    def test_session_requires_auth(self, anon):
        """Unauthenticated request returns 401."""
        response = anon.get("/api/cdr/session?case_id=CASE-001")
        assert response.status_code == 401

    def test_session_inaccessible_case_returns_403(self, authed):
        """Case that the user cannot see returns 403."""
        with patch("app.api.cdr_session.get_visible_case", return_value=None):
            response = authed.get(f"/api/cdr/session?case_id={HIDDEN_CASE_ID}")
        assert response.status_code == 403

    def test_session_returns_case_id_matching_request(self, authed):
        """Session case_id echoes the requested case_id."""
        fake_case = MagicMock()
        fake_case.display_id = VISIBLE_CASE_ID
        with patch("app.api.cdr_session.get_visible_case", return_value=fake_case):
            response = authed.get(f"/api/cdr/session?case_id={VISIBLE_CASE_ID}")
        assert response.status_code == 200
        assert response.json()["case_id"] == VISIBLE_CASE_ID

    def test_no_cross_case_leakage(self, authed):
        """A user cannot get a CDR session for a case they cannot see."""
        with patch("app.api.cdr_session.get_visible_case", return_value=None):
            response = authed.get(f"/api/cdr/session?case_id={HIDDEN_CASE_ID}")
        assert response.status_code == 403

    def test_session_sets_httponly_cookie(self, authed):
        """A successful session call must set the cdr_session httpOnly cookie."""
        fake_case = MagicMock()
        fake_case.display_id = VISIBLE_CASE_ID
        with patch("app.api.cdr_session.get_visible_case", return_value=fake_case):
            response = authed.get(f"/api/cdr/session?case_id={VISIBLE_CASE_ID}")
        assert response.status_code == 200
        cookie_header = response.headers.get("set-cookie", "")
        assert "cdr_session" in cookie_header
        assert "HttpOnly" in cookie_header

    def test_response_body_contains_no_credentials(self, authed):
        """The response body must not contain any CDR credentials."""
        fake_case = MagicMock()
        fake_case.display_id = VISIBLE_CASE_ID
        with patch("app.api.cdr_session.get_visible_case", return_value=fake_case):
            response = authed.get(f"/api/cdr/session?case_id={VISIBLE_CASE_ID}")
        assert response.status_code == 200
        body = response.json()
        assert "d1_token" not in body
        assert "d2_analyst_id" not in body
        assert "subject" not in body
