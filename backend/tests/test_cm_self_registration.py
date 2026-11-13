"""Officers create their own login (docs/case-management/13-plain-case-design.md, section 12): only an officer who is in the register, with a
matching name and no account yet; the account starts with the least access (Viewer, public clearance) at the officer's own station; the people above
are told and raise it (role and clearance) within what the register and their own clearance allow. All names and numbers are fictional."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from cm_support import place
from test_cm_people_api import officer, people  # noqa: F401  (people is a fixture)

from app.auth.ratelimit import FailedLoginLimiter, get_signup_limiter
from app.casemgmt.accounts import SELF_REGISTRATION_REFUSED
from app.casemgmt.models import AuthorizationEvent, Notification
from app.core.config import get_settings
from app.db.models import AuditEvent, User

PASSWORD = "My-own-fictional-pass-1"


@pytest.fixture
def signup(people, app_overrides):  # noqa: F811
    """An anonymous visitor of the sign-in page, with a fresh limit of sign-up attempts."""
    limiter = FailedLoginLimiter(10, 3600)  # one for the whole test, like the real one
    app_overrides.dependency_overrides[get_signup_limiter] = lambda: limiter
    with TestClient(app_overrides) as visitor:
        yield visitor
    app_overrides.dependency_overrides.pop(get_signup_limiter, None)


def body(**over):
    return {"officer_number": "INV-9", "full_name": "Ravi Kumar (fictional)", "username": "ravi.kumar", "password": PASSWORD, **over}


def test_an_officer_in_the_register_creates_their_own_login_with_view_only_access(people, signup):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    made = signup.post("/api/auth/register", json=body(officer_number="inv-9", full_name="  ravi  KUMAR (fictional) "))
    assert made.status_code == 201, made.text
    assert made.json()["org_role"] == "viewer" and made.json()["station"] == "PS-A" and made.json()["username"] == "ravi.kumar"

    user = w.db.scalar(select(User).where(User.username == "ravi.kumar"))
    assert (user.org_role, user.clearance, user.role) == ("viewer", "public", "viewer")  # the least access there is
    assert user.officer_id is not None and user.must_change_password is False and user.display_name == "Ravi Kumar (fictional)"

    mine = w.login("ravi.kumar", PASSWORD)  # the password they chose works at once
    me = mine.get("/api/auth/me").json()
    assert me["org_role"] == "viewer" and me["clearance"] == "public" and me["must_change_password"] is False
    assert mine.get("/api/v1/cases").json()["items"] == []  # no case is open to them

    kinds = [e.change for e in w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.user_id == user.id).order_by(AuthorizationEvent.id))]
    assert kinds == ["account_created", "station_granted"]
    assert w.db.scalar(select(AuditEvent).where(AuditEvent.action == "user.self_registered", AuditEvent.outcome == "success")) is not None


def test_every_refusal_gives_the_same_answer_so_the_form_cannot_be_used_to_explore_the_register(people, signup):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    refusals = [
        signup.post("/api/auth/register", json=body(officer_number="NOPE-1")),  # not in the register
        signup.post("/api/auth/register", json=body(full_name="Someone Else (fictional)")),  # the name doesn't match
    ]
    assert signup.post("/api/auth/register", json=body()).status_code == 201
    refusals.append(signup.post("/api/auth/register", json=body(username="ravi.second")))  # the officer already has an account
    for refusal in refusals:
        assert refusal.status_code == 422 and refusal.json()["detail"] == SELF_REGISTRATION_REFUSED
    assert w.db.scalar(select(User).where(User.username == "ravi.second")) is None
    assert w.db.scalars(select(AuditEvent).where(AuditEvent.action == "user.self_registered", AuditEvent.outcome == "rejected")).all()


def test_only_the_four_things_are_accepted_and_the_username_and_password_must_fit(people, signup):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    # a role, clearance or station can never be asked for here
    for extra in ({"org_role": "super_admin"}, {"clearance": "confidential"}, {"station_id": str(w.b.id)}, {"role": "admin"}):
        assert signup.post("/api/auth/register", json={**body(), **extra}).status_code == 422
    assert signup.post("/api/auth/register", json=body(password="short")).status_code == 422
    assert signup.post("/api/auth/register", json=body(username="a b")).status_code == 422
    assert w.db.scalar(select(User).where(User.username.in_(["ravi.kumar", "a b"]))) is None
    taken = signup.post("/api/auth/register", json=body(username="super.admin"))  # a username that exists
    assert taken.status_code == 422 and "already exists" in taken.json()["detail"]


def test_the_people_who_can_raise_the_access_are_told(people, signup):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    sup_a, sup_b = w.cm_client("sup.a", "supervisor"), w.cm_client("sup.b", "supervisor")
    place(w.db, sup_a.user, w.a)
    place(w.db, sup_b.user, w.b)
    w.db.commit()
    assert signup.post("/api/auth/register", json=body()).status_code == 201
    told = {w.db.get(User, n.user_id).username for n in w.db.scalars(select(Notification).where(Notification.kind == "account.self_registered"))}
    assert told == {"super.admin", "sup.a"}  # the Super Admin and this station's Supervisor; not the other station's
    notice = w.db.scalar(select(Notification).where(Notification.kind == "account.self_registered"))
    assert notice.payload["officer"] == "INV-9" and notice.payload["username"] == "ravi.kumar" and notice.payload["station"] == "PS-A"


def test_a_supervisor_raises_the_role_within_the_register_and_the_clearance_within_their_own(people, signup):
    w = people
    officer(w.sa, "INV-9", w.a, "analyst", name="Ravi Kumar (fictional)")  # the register allows this officer at most an analyst
    sup = w.cm_client("sup.a", "supervisor", "restricted")
    other = w.cm_client("sup.b", "supervisor", "confidential")
    place(w.db, sup.user, w.a)
    place(w.db, other.user, w.b)
    assert signup.post("/api/auth/register", json=body()).status_code == 201
    person = w.db.scalar(select(User).where(User.username == "ravi.kumar"))
    base = f"/api/v1/people/accounts/{person.id}"

    row = next(r for r in sup.get("/api/v1/people/accounts").json() if r["username"] == "ravi.kumar")
    assert row["clearance"] == "public" and row["can"]["allowed_roles"] == ["analyst"]  # no higher: the register's ceiling
    assert row["can"]["change_clearance"] is True and row["can"]["allowed_clearances"] == ["internal", "restricted"]  # never above the Supervisor's own

    assert sup.post(f"{base}/role", json={"role": "investigator", "reason": "Above the register (fictional)"}).status_code == 403
    assert sup.post(f"{base}/role", json={"role": "analyst", "reason": "Joined the unit (fictional)"}).status_code == 200
    assert sup.post(f"{base}/clearance", json={"clearance": "confidential", "reason": "Above my own (fictional)"}).status_code == 403
    assert sup.post(f"{base}/clearance", json={"clearance": "restricted", "reason": "Works on restricted cases (fictional)"}).status_code == 200
    assert sup.post(f"{base}/clearance", json={"clearance": "restricted", "reason": "Nothing changes (fictional)"}).status_code == 422
    assert sup.post(f"{base}/clearance", json={"clearance": "internal", "reason": "x"}).status_code == 422  # a reason is needed

    w.db.expire_all()
    person = w.db.get(User, person.id)
    assert (person.org_role, person.clearance) == ("analyst", "restricted")
    kinds = [(e.change, e.old_value, e.new_value) for e in w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.user_id == person.id).order_by(AuthorizationEvent.id))]
    assert ("role_changed", "viewer", "analyst") in kinds and ("clearance_changed", "public", "restricted") in kinds

    assert other.post(f"{base}/clearance", json={"clearance": "internal", "reason": "Not my station (fictional)"}).status_code == 404  # another station's Supervisor
    mine = w.login("ravi.kumar", PASSWORD)
    assert mine.post(f"/api/v1/people/accounts/{person.id}/clearance", json={"clearance": "confidential", "reason": "Giving myself more"}).status_code in (403, 404)


def test_sign_up_can_be_switched_off(people, signup, monkeypatch):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    assert signup.get("/api/auth/registration").json() == {"enabled": True}
    monkeypatch.setattr(get_settings(), "self_registration", False)
    assert signup.get("/api/auth/registration").json() == {"enabled": False}
    assert signup.post("/api/auth/register", json=body()).status_code == 404
    assert w.db.scalar(select(User).where(User.username == "ravi.kumar")) is None


def test_too_many_attempts_from_one_computer_are_stopped(people, app_overrides):
    w = people
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    limiter = FailedLoginLimiter(3, 3600)
    app_overrides.dependency_overrides[get_signup_limiter] = lambda: limiter
    try:
        with TestClient(app_overrides) as visitor:
            for _ in range(3):  # every attempt counts, wrong ones too
                assert visitor.post("/api/auth/register", json=body(full_name="Wrong Name (fictional)")).status_code == 422
            blocked = visitor.post("/api/auth/register", json=body())  # even a correct one is refused now
            assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    finally:
        app_overrides.dependency_overrides.pop(get_signup_limiter, None)
    assert w.db.scalar(select(User).where(User.username == "ravi.kumar")) is None
