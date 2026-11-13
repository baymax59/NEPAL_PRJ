"""The profile of a login (docs/case-management/13-plain-case-design.md, section 12): a person fills in and updates their own email, phone and job title,
at sign-up or afterwards; name, officer ID, rank, station, role and clearance stay what the register and their superiors say. All names are fictional."""

from sqlalchemy import select
from test_cm_people_api import OWN_PASSWORD, first_login, make_account, officer, people  # noqa: F401  (people is a fixture)
from test_cm_self_registration import PASSWORD, body, signup  # noqa: F401  (signup is a fixture)

from app.db.models import AuditEvent, User


def sign_up(w, signup, **more):
    officer(w.sa, "INV-9", w.a, "investigator", name="Ravi Kumar (fictional)")
    assert signup.post("/api/auth/register", json=body(**more)).status_code == 201
    return w.login("ravi.kumar", PASSWORD)


def test_the_profile_can_be_filled_in_when_the_login_is_created(people, signup):
    w = people
    mine = sign_up(w, signup, email="ravi@example.invalid", phone="+91 70000 00001")
    profile = mine.get("/api/auth/profile").json()
    assert (profile["email"], profile["phone"], profile["job_title"]) == ("ravi@example.invalid", "+91 70000 00001", None)
    assert profile["profile_updated_at"] is not None
    # the official details come from the register and are only shown
    assert (profile["officer_number"], profile["rank"], profile["stations"]) == ("INV-9", "Inspector", ["PS-A"])
    assert profile["display_name"] == "Ravi Kumar (fictional)" and profile["org_role"] == "viewer" and profile["clearance"] == "public"


def test_a_login_made_without_a_profile_starts_empty_and_the_person_updates_it_later(people, signup):
    w = people
    mine = sign_up(w, signup)
    me = mine.get("/api/auth/me").json()
    assert (me["email"], me["phone"], me["job_title"], me["profile_updated_at"]) == (None, None, None, None)  # the screens ask for it

    saved = mine.post("/api/auth/profile", json={"email": "ravi@example.invalid", "phone": "+91 (70000) 00-001", "job_title": "Investigating officer, cyber cell"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["job_title"] == "Investigating officer, cyber cell" and saved.json()["profile_updated_at"] is not None
    me = mine.get("/api/auth/me").json()
    assert (me["email"], me["phone"], me["profile_updated_at"] is not None) == ("ravi@example.invalid", "+91 (70000) 00-001", True)

    cleared = mine.post("/api/auth/profile", json={"email": "", "phone": "", "job_title": ""})  # an empty value clears it
    assert cleared.status_code == 200 and (cleared.json()["email"], cleared.json()["phone"], cleared.json()["job_title"]) == (None, None, None)


def test_only_these_three_things_can_be_changed_and_they_must_look_right(people, signup):
    w = people
    mine = sign_up(w, signup)
    for extra in ({"display_name": "Someone Else"}, {"org_role": "super_admin"}, {"clearance": "confidential"}, {"username": "root"}, {"officer_number": "ADM-1"}):
        assert mine.post("/api/auth/profile", json=extra).status_code == 422, extra
    assert mine.post("/api/auth/profile", json={"email": "not an email"}).status_code == 422
    assert mine.post("/api/auth/profile", json={"phone": "call me"}).status_code == 422
    assert mine.post("/api/auth/profile", json={"job_title": "x" * 101}).status_code == 422
    user = w.db.scalar(select(User).where(User.username == "ravi.kumar"))
    assert (user.display_name, user.org_role, user.clearance, user.email) == ("Ravi Kumar (fictional)", "viewer", "public", None)


def test_the_audit_trail_says_which_fields_changed_never_their_values(people, signup):
    w = people
    mine = sign_up(w, signup)
    mine.post("/api/auth/profile", json={"email": "ravi@example.invalid", "phone": "+91 70000 00001"})
    mine.post("/api/auth/profile", json={"email": "ravi@example.invalid", "phone": "+91 70000 00001", "job_title": "Inspector"})
    events = w.db.scalars(select(AuditEvent).where(AuditEvent.action == "user.profile_updated").order_by(AuditEvent.id)).all()
    assert [e.details["fields"] for e in events] == [["email", "phone"], ["job_title"]]
    assert "example.invalid" not in str([e.details for e in events]) and "70000" not in str([e.details for e in events])


def test_everybody_has_a_profile_of_their_own_and_nobody_can_change_another(people, signup):
    w = people
    mine = sign_up(w, signup)
    other = w.cm_client("sup.a", "supervisor")
    assert mine.post("/api/auth/profile", json={"phone": "+91 70000 00001"}).status_code == 200
    assert other.get("/api/auth/profile").json()["phone"] is None  # theirs is their own
    assert other.get("/api/auth/profile").json()["officer_number"] is None  # no register entry for this test account


def test_a_login_with_a_temporary_password_updates_the_profile_after_choosing_its_own_password(people):
    w = people
    officer(w.sa, "ADM-1", w.a, "administrator")
    made = make_account(w.sa, "ADM-1", "administrator", "admin.one")
    first = w.login("admin.one", made["temporary_password"])
    assert first.get("/api/auth/profile").status_code == 403  # nothing else works until the owner has chosen their own password
    own = first_login(w, "admin.one", made["temporary_password"])
    assert own.post("/api/auth/profile", json={"email": "admin@example.invalid", "job_title": "Administrator"}).status_code == 200
    assert own.get("/api/auth/profile").json()["stations"] == ["PS-A"]


def test_the_people_above_see_how_to_reach_a_person(people, signup):
    w = people
    mine = sign_up(w, signup)
    mine.post("/api/auth/profile", json={"email": "ravi@example.invalid", "phone": "+91 70000 00001", "job_title": "Inspector"})
    row = next(r for r in w.sa.get("/api/v1/people/accounts").json() if r["username"] == "ravi.kumar")
    assert (row["email"], row["phone"], row["job_title"]) == ("ravi@example.invalid", "+91 70000 00001", "Inspector")
