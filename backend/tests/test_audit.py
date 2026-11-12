"""The audit log: what is recorded, what is never recorded, and who may read it."""

import json

import pytest
from sqlalchemy import select

from app.audit.log import fingerprint
from app.db.models import AuditEvent

SECRET_QUERY = "Ramesh Kumar of 12 Gandhi Road accused of theft"


def events(db_session, action: str) -> list[AuditEvent]:
    return list(db_session.scalars(select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)))


@pytest.fixture
def cases(add_case):
    add_case(1, title="Public case", year=2023, passages=["Anticipatory bail refused."])
    add_case(2, title="Restricted case", year=2023, sensitivity="restricted", passages=["Anticipatory bail refused."])


def test_searches_are_recorded_without_the_search_text(api, cases, db_session):
    api.post("/api/search", json={"query": SECRET_QUERY, "filters": {"year_from": 2020}})

    [event] = events(db_session, "search")
    assert event.username == "test.analyst"
    assert event.outcome == "success"
    assert event.details["query_fingerprint"] == fingerprint(SECRET_QUERY)
    assert event.details["query_length"] == len(SECRET_QUERY)
    assert event.details["filters"] == {"year_from": 2020}
    recorded = json.dumps(event.details)
    assert "Ramesh" not in recorded and "Gandhi" not in recorded


def test_case_views_record_success_denied_and_not_found(api, cases, db_session):
    api.get("/api/cases/TEST-API-1")
    api.get("/api/cases/TEST-API-2")  # restricted: the user sees "not found"...
    api.get("/api/cases/TEST-API-999")

    outcomes = [(e.target_id, e.outcome) for e in events(db_session, "case.view")]
    # ...but the audit log shows it was a denied attempt on a case that exists.
    assert outcomes == [("TEST-API-1", "success"), ("TEST-API-2", "denied"), ("TEST-API-999", "not_found")]


def test_uploads_are_recorded_without_the_file_name(api, db_session, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    api.post("/api/uploads", files={"file": ("FIR-Ramesh-Kumar.txt", b"Anticipatory bail refused.", "text/plain")})

    [event] = events(db_session, "upload.create")
    assert event.outcome == "success"
    assert len(event.details["sha256"]) == 64
    assert "Ramesh" not in json.dumps(event.details)


def test_failed_logins_record_the_username_but_never_the_password(anonymous_api, db_session):
    anonymous_api.post("/api/auth/token", data={"username": "mallory", "password": "Secret-Password-123"})

    [event] = events(db_session, "auth.login")
    assert (event.username, event.outcome, event.details) == ("mallory", "rejected", {"reason": "unknown_user"})
    assert "Secret-Password" not in json.dumps(event.details)


def test_attempts_beyond_a_users_role_are_recorded(client_as, db_session):
    viewer = client_as("vera", role="viewer")

    viewer.post("/api/uploads", files={"file": ("x.txt", b"text", "text/plain")})
    viewer.get("/api/audit")

    denied = [(e.username, e.outcome, e.target_id) for e in events(db_session, "role.denied")]
    assert denied == [("vera", "denied", "POST /api/uploads"), ("vera", "denied", "GET /api/audit")]


def test_only_admins_can_read_the_audit_log_and_reading_is_recorded(client_as, db_session):
    analyst = client_as("anna", role="analyst")
    admin = client_as("adam", role="admin")
    analyst.get("/api/cases")

    assert analyst.get("/api/audit").status_code == 403
    page = admin.get("/api/audit", params={"username": "anna"}).json()
    assert [e["action"] for e in page["events"]] == ["role.denied", "case.list"]  # newest first
    assert events(db_session, "audit.read")[0].username == "adam"
