"""Logging in, tokens, lockout, and endpoints refusing callers who aren't logged in."""

import datetime as dt
import uuid

import jwt
import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.auth.tokens import ALGORITHM
from app.core.config import get_settings
from app.db.models import AuditEvent
from conftest import TEST_PASSWORD, auth_header

GENERIC_FAILURE = "Incorrect username or password, or the account is locked. Try again later."


def login(client, username, password=TEST_PASSWORD):
    return client.post("/api/auth/token", data={"username": username, "password": password})


def login_reasons(db_session) -> list[str]:
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login").order_by(AuditEvent.id))
    return [e.details.get("reason", e.outcome) for e in events]


def test_login_returns_a_token_that_identifies_the_user(anonymous_api, make_user):
    make_user("alice", role="viewer", clearance="internal")

    response = login(anonymous_api, "Alice")  # usernames are not case-sensitive

    assert response.status_code == 200
    token = response.json()["access_token"]
    me = anonymous_api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert (me["username"], me["role"], me["clearance"]) == ("alice", "viewer", "internal")


def test_wrong_password_and_unknown_user_get_the_same_answer(anonymous_api, make_user, db_session):
    make_user("alice")

    wrong = login(anonymous_api, "alice", "not the password")
    unknown = login(anonymous_api, "mallory", "whatever-password")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": GENERIC_FAILURE}
    assert login_reasons(db_session) == ["wrong_password", "unknown_user"]  # only the audit log knows


def test_account_locks_after_repeated_wrong_passwords(anonymous_api, make_user, db_session):
    user = make_user("alice")
    for _ in range(get_settings().max_failed_logins):
        login(anonymous_api, "alice", "wrong password!!")

    locked = login(anonymous_api, "alice")  # even the right password is refused while locked

    assert locked.status_code == 401
    assert locked.json() == {"detail": GENERIC_FAILURE}
    assert login_reasons(db_session)[-2:] == ["wrong_password_now_locked", "locked"]
    user.locked_until = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)  # lock period over
    db_session.flush()
    assert login(anonymous_api, "alice").status_code == 200


def test_deactivated_users_cannot_log_in_or_use_old_tokens(anonymous_api, make_user, db_session):
    user = make_user("alice")
    headers = auth_header(user)
    user.is_active = False
    db_session.flush()

    assert login(anonymous_api, "alice").status_code == 401
    assert anonymous_api.get("/api/cases", headers=headers).status_code == 401


def test_passwords_are_stored_only_as_argon2_hashes(make_user):
    user = make_user("alice")

    assert TEST_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_short_passwords_are_refused():
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("short")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/cases"),
        ("get", "/api/cases/filters"),
        ("get", "/api/cases/SC-ANY"),
        ("post", "/api/cases/SC-ANY/explain"),
        ("get", "/api/cases/SC-ANY/similar"),
        ("post", "/api/search"),
        ("post", "/api/uploads"),
        ("get", f"/api/uploads/{uuid.uuid4()}"),
        ("get", "/api/audit"),
        ("get", "/api/auth/me"),
    ],
)
def test_every_data_endpoint_requires_login(anonymous_api, method, path):
    response = getattr(anonymous_api, method)(path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_health_check_needs_no_login(anonymous_api):
    assert anonymous_api.get("/api/health").status_code == 200


def _token(user_id, secret=None, minutes=5, **overrides):
    now = dt.datetime.now(dt.UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + dt.timedelta(minutes=minutes), **overrides}
    return jwt.encode(payload, secret or get_settings().jwt_secret.get_secret_value(), algorithm=ALGORITHM)


@pytest.mark.parametrize(
    "make_token",
    [
        lambda uid: _token(uid, secret="someone-elses-secret-0123456789abcdefghij"),  # forged
        lambda uid: _token(uid, minutes=-1),  # expired
        lambda uid: _token(uuid.uuid4()),  # valid signature, unknown user
        lambda uid: jwt.encode({"sub": str(uid)}, key=None, algorithm="none"),  # unsigned
        lambda uid: "not-a-token",
    ],
    ids=["forged", "expired", "unknown-user", "unsigned", "garbage"],
)
def test_bad_tokens_are_refused(anonymous_api, make_user, make_token):
    user = make_user("alice")

    response = anonymous_api.get("/api/cases", headers={"Authorization": f"Bearer {make_token(user.id)}"})

    assert response.status_code == 401
