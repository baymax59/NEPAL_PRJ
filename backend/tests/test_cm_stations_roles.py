"""Police stations and the seven roles (phase R-3, docs/case-management/12-roles-and-stations.md): what each role sees by station,
where cases can be registered, who may create whom, the officer-ID rule, station assignment and the promotion rule.
All names, numbers and officers are fictional."""

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest
from cm_support import add_member, create_case, make_station, place
from sqlalchemy import func, select

from app.casemgmt import accounts
from app.casemgmt.access import supervises
from app.casemgmt.errors import Conflict, Forbidden, Invalid
from app.casemgmt.models import AuthorizationEvent, CaseFamily, Organization, PoliceStation, UserStation
from app.db.models import User

PASSWORD = "Fictional-station-pass-1"


@pytest.fixture
def world(cm_client, cm_user, db_session):
    """Two stations, A and B, and people at each; one Administrator over both, one over A only, and a Super Admin."""
    a, b = make_station(db_session, "PS-A"), make_station(db_session, "PS-B")
    w = SimpleNamespace(a=a, b=b, db=db_session)
    w.sa = cm_client("super.admin", "super_admin", "confidential")
    w.admin_ab = cm_client("admin.ab", "administrator", "confidential")
    w.admin_a = cm_client("admin.a", "administrator", "confidential")
    w.sup_a, w.sup_b = cm_client("sup.a", "supervisor", "confidential"), cm_client("sup.b", "supervisor", "confidential")
    w.sup_a2 = cm_client("sup.a2", "supervisor", "confidential")
    w.inv_a, w.inv_b = cm_client("inv.a"), cm_client("inv.b")
    w.inv_a2 = cm_client("inv.a2")
    w.sub_a, w.sub_b = cm_client("sub.a", "sub_investigator"), cm_client("sub.b", "sub_investigator")
    w.viewer_a = cm_client("viewer.a", "viewer")
    place(db_session, w.admin_ab.user, a, b)
    place(db_session, w.admin_a.user, a)
    for client, station in ((w.sup_a, a), (w.sup_a2, a), (w.inv_a, a), (w.inv_a2, a), (w.sub_a, a), (w.viewer_a, a),
                            (w.sup_b, b), (w.inv_b, b), (w.sub_b, b)):
        place(db_session, client.user, station)
    return w


def register(w, creator, lead, supervisor, station=None) -> dict:
    fields = {"lead_investigator_id": str(lead.user.id), "supervisor_id": str(supervisor.user.id)}
    if station is not None:
        fields["station_id"] = str(station.id)
    return create_case(creator, **fields)


def visible_cases(client) -> set[str]:
    response = client.get("/api/v1/cases", params={"limit": 100})
    assert response.status_code == 200, response.text
    return {c["display_id"] for c in response.json()["items"]}


# ---------------------------------------------------------------- what each role sees


def test_each_role_sees_its_stations_and_nothing_across(world):
    w = world
    case_a = register(w, w.sup_a, w.inv_a, w.sup_a)
    case_b = register(w, w.sup_b, w.inv_b, w.sup_b)
    a, b = case_a["display_id"], case_b["display_id"]
    assert a != b

    assert visible_cases(w.sa) >= {a, b}  # the Super Admin: every station
    assert visible_cases(w.admin_ab) >= {a, b}  # an Administrator: the stations they were given
    assert visible_cases(w.admin_a) == {a}
    assert visible_cases(w.sup_a) == {a} and visible_cases(w.sup_b) == {b}  # a Supervisor: their one station, all of it
    assert visible_cases(w.inv_a) == {a} and visible_cases(w.inv_b) == {b}  # an Investigator: their own cases
    assert visible_cases(w.inv_a2) == set()  # same station, but not on the case
    assert visible_cases(w.sub_a) == set() and visible_cases(w.viewer_a) == set()  # added to a case first

    # Across stations the answer is "not found", exactly as for a case that doesn't exist.
    for outsider, case in ((w.inv_a, case_b), (w.sup_a, case_b), (w.admin_a, case_b), (w.inv_b, case_a), (w.sup_b, case_a)):
        assert outsider.get(f"/api/v1/cases/{case['case_id']}").status_code == 404
        assert outsider.get(f"/api/v1/cases/{case['case_id']}/files").status_code == 404
        assert outsider.get(f"/api/v1/cases/{case['case_id']}/history").status_code == 404
    assert w.admin_a.get(f"/api/v1/cases/{case_a['case_id']}").status_code == 200


def test_a_sub_investigator_sees_only_the_cases_they_are_added_to(world):
    w = world
    case_a = register(w, w.sup_a, w.inv_a, w.sup_a)
    case_b = register(w, w.sup_b, w.inv_b, w.sup_b)
    add_member(w.inv_a, case_a["case_id"], w.sub_a.user)  # added directly by the Investigator who leads the case
    assert visible_cases(w.sub_a) == {case_a["display_id"]}
    assert w.sub_a.get(f"/api/v1/cases/{case_b['case_id']}").status_code == 404
    # Someone from another station can't be added.
    refused = add_member(w.inv_a, case_a["case_id"], w.sub_b.user, status=422)
    assert "police station" in refused["detail"]


def test_a_revoked_station_assignment_ends_the_station_wide_view(world):
    w = world
    case_a = register(w, w.sup_a, w.inv_a, w.sup_a)
    assert visible_cases(w.admin_a) == {case_a["display_id"]}
    place(w.db, w.admin_a.user)  # no station any more
    assert visible_cases(w.admin_a) == set()


# ---------------------------------------------------------------- where a case can be registered


def test_cases_are_registered_only_at_the_creators_own_stations(world):
    w = world
    family = lambda created: w.db.get(CaseFamily, uuid.UUID(created["case_id"]))  # noqa: E731

    assert family(register(w, w.sup_a, w.inv_a, w.sup_a)).station_id == w.a.id  # their only station, by default
    assert family(register(w, w.inv_b, w.inv_b, w.sup_b)).station_id == w.b.id
    own = register(w, w.admin_ab, w.inv_b, w.sup_b, station=w.b)
    assert family(own).station_id == w.b.id
    default = w.sa.post("/api/v1/cases", json={"title": "Fictional case from the Super Admin", "case_type": "theft",
                                               "description": "Fictional: a stolen bicycle.", "station_id": str(w.a.id),
                                               "lead_investigator_id": str(w.inv_a.user.id)})
    assert default.status_code == 201 and family(default.json()).station_id == w.a.id  # a Super Admin: any station

    body = {"title": "Fictional case", "case_type": "theft", "description": "Fictional: a stolen bicycle (test)."}
    refused = w.inv_a.post("/api/v1/cases", json={**body, "station_id": str(w.b.id)})
    assert refused.status_code == 403 and "PS-B" in refused.json()["detail"]
    assert w.admin_a.post("/api/v1/cases", json={**body, "station_id": str(w.b.id)}).status_code == 403
    assert w.inv_a.post("/api/v1/cases", json={**body, "station_id": str(uuid.uuid4())}).status_code == 422
    # An Administrator with two stations must say which.
    asked = w.admin_ab.post("/api/v1/cases", json={**body, "lead_investigator_id": str(w.inv_a.user.id)})
    assert asked.status_code == 422 and "Choose the police station" in asked.json()["detail"]
    # Those who can't register cases at all.
    assert w.sub_a.post("/api/v1/cases", json=body).status_code == 403
    assert w.viewer_a.post("/api/v1/cases", json=body).status_code == 403


def test_the_lead_and_supervisor_must_work_at_the_cases_station(world):
    w = world
    wrong_lead = w.sup_a.post("/api/v1/cases", json={"title": "Fictional case", "case_type": "theft", "description": "Fictional: a theft (test).",
                                                     "lead_investigator_id": str(w.inv_b.user.id)})
    assert wrong_lead.status_code == 422 and "doesn't work at the case's police station" in wrong_lead.json()["detail"]
    wrong_sup = w.sup_a.post("/api/v1/cases", json={"title": "Fictional case", "case_type": "theft", "description": "Fictional: a theft (test).",
                                                    "supervisor_id": str(w.sup_b.user.id)})
    assert wrong_sup.status_code == 422


def test_colleagues_are_found_only_at_the_cases_station(world):
    w = world
    found = w.sup_a.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted"}).json()
    names = {c["username"] for c in found}
    assert "inv.a" in names and "inv.b" not in names
    at_b = w.sa.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted", "station_id": str(w.b.id)}).json()
    assert {"inv.b"} <= {c["username"] for c in at_b} and "inv.a" not in {c["username"] for c in at_b}


def test_everybody_is_offered_only_the_stations_they_may_register_cases_at(world):
    w = world
    codes = lambda client: {st["code"] for st in client.get("/api/v1/stations").json()}  # noqa: E731
    assert {"PS-A", "PS-B", "HQ"} <= codes(w.sa)  # the Super Admin: every station
    assert codes(w.admin_ab) == {"PS-A", "PS-B"} and codes(w.admin_a) == {"PS-A"}
    assert codes(w.sup_a) == {"PS-A"} and codes(w.inv_b) == {"PS-B"}
    place(w.db, w.inv_a2.user)  # no station at all
    assert codes(w.inv_a2) == set()


# ---------------------------------------------------------------- the register of officers and who creates whom


def officer(w, number, station, highest="investigator", name=None):
    return accounts.add_officer(w.db, w.sa.user, officer_number=number, full_name=name or f"Officer {number} (fictional)", rank="Inspector",
                                station_id=station.id, highest_role=highest)


def new_account(w, actor, number, role, username=None, clearance="restricted", **more):
    return accounts.create_account(w.db, actor.user, officer_number=number, username=username or number.lower().replace("/", "-"),
                                   display_name=f"Account {number} (fictional)", password=PASSWORD, role=role, clearance=clearance, **more).user


def test_the_hierarchy_of_who_creates_whom(world):
    w = world
    officer(w, "ADM-1", w.a, "administrator")
    officer(w, "SUP-1", w.a, "supervisor")
    officer(w, "INV-1", w.a, "investigator")
    officer(w, "INV-2", w.a, "investigator")
    officer(w, "SUB-1", w.a, "sub_investigator")
    officer(w, "ANA-1", w.a, "analyst")
    officer(w, "VIE-1", w.a, "viewer")
    officer(w, "SUP-B", w.b, "supervisor")

    admin = new_account(w, w.sa, "ADM-1", "administrator", extra_station_ids=[w.b.id])  # the Super Admin makes Administrators
    assert admin.org_role == "administrator" and {r.station_id for r in w.db.scalars(
        select(UserStation).where(UserStation.user_id == admin.id))} == {w.a.id, w.b.id}
    actor = SimpleNamespace(user=admin)
    supervisor = new_account(w, actor, "SUP-1", "supervisor")  # an Administrator makes Supervisors, at their stations
    assert supervisor.org_role == "supervisor"
    sup = SimpleNamespace(user=supervisor)
    investigator = new_account(w, sup, "INV-1", "investigator")  # a Supervisor makes the rest, at their station
    assert investigator.org_role == "investigator"
    inv = SimpleNamespace(user=investigator)
    assert new_account(w, inv, "INV-2", "investigator").org_role == "investigator"  # an Investigator makes another Investigator
    assert new_account(w, inv, "SUB-1", "sub_investigator").org_role == "sub_investigator"
    assert new_account(w, inv, "ANA-1", "analyst").org_role == "analyst"
    assert new_account(w, sup, "VIE-1", "viewer").org_role == "viewer"

    # Never a role above or equal to your own (an Investigator may make Investigators), and never a Super Admin.
    for actor_client, number, role in ((inv, "SUP-1", "supervisor"), (sup, "ADM-1", "administrator"), (w.sa, "SUP-1", "supervisor"),
                                       (actor, "INV-1", "investigator"), (w.sa, "ADM-1", "super_admin"), (inv, "VIE-1", "viewer")):
        with pytest.raises((Forbidden, Invalid)):
            new_account(w, actor_client, number, role, username="x" + number.lower())
    # People who can't create accounts at all.
    officer(w, "SUB-9", w.a, "sub_investigator")
    for who in (w.sub_a, w.viewer_a):
        with pytest.raises(Forbidden):
            new_account(w, who, "SUB-9", "sub_investigator", username="nobody")


def test_an_account_is_made_only_for_a_registered_officer_with_the_right_station_and_role(world):
    w = world
    sup = SimpleNamespace(user=w.sup_a.user)
    officer(w, "INV-A1", w.a, "investigator")
    officer(w, "INV-B1", w.b, "investigator")
    officer(w, "SUB-A1", w.a, "sub_investigator")

    with pytest.raises(Invalid, match="not in the register"):  # an ID that doesn't exist
        new_account(w, sup, "NOT-THERE", "investigator")
    with pytest.raises(Forbidden, match="at most the role"):  # above what the register allows
        new_account(w, sup, "SUB-A1", "investigator")
    with pytest.raises(Forbidden, match="isn't one of yours"):  # the officer's station comes from the register: not this supervisor's
        new_account(w, sup, "INV-B1", "investigator")
    made = new_account(w, sup, "INV-A1", "investigator")
    assert made.officer_id is not None
    assert {r.station_id for r in w.db.scalars(select(UserStation).where(UserStation.user_id == made.id))} == {w.a.id}
    with pytest.raises(Conflict, match="already has an account"):  # each officer once
        new_account(w, sup, "INV-A1", "investigator", username="second.try")
    with pytest.raises(Conflict):
        officer(w, "INV-A1", w.a)  # and each ID is in the register once
    officer(w, "INV-A2", w.a)
    w.sup_a.user.clearance = "restricted"
    with pytest.raises(Forbidden, match="clearance"):  # not above the creator's own clearance
        new_account(w, sup, "INV-A2", "investigator", clearance="confidential")
    with pytest.raises(Forbidden):  # only the Super Admin enters officers
        accounts.add_officer(w.db, w.sup_a.user, officer_number="X-1", full_name="Officer X (fictional)", rank="SI",
                             station_id=w.a.id, highest_role="investigator")

    events = list(w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.user_id == made.id).order_by(AuthorizationEvent.id)))
    assert [e.change for e in events] == ["account_created", "station_granted"] and events[0].actor_id == w.sup_a.user.id


# ---------------------------------------------------------------- stations given to people


def test_the_super_admin_gives_an_administrator_stations_and_an_administrator_places_others(world):
    w = world
    case_b = register(w, w.sup_b, w.inv_b, w.sup_b)
    assert visible_cases(w.admin_a) == set()
    accounts.set_stations(w.db, w.sa.user, w.admin_a.user, [w.a.id, w.b.id], "Now also covers station B (fictional)")
    w.db.commit()
    assert case_b["display_id"] in visible_cases(w.admin_a)
    accounts.set_stations(w.db, w.sa.user, w.admin_a.user, [w.a.id], "Back to station A only (fictional)")
    w.db.commit()
    assert visible_cases(w.admin_a) == set()  # the assignment ended; nothing was deleted
    rows = list(w.db.scalars(select(UserStation).where(UserStation.user_id == w.admin_a.user.id)))
    assert sum(r.revoked_at is not None for r in rows) >= 1 and len(rows) >= 3
    kinds = [e.change for e in w.db.scalars(select(AuthorizationEvent).where(
        AuthorizationEvent.user_id == w.admin_a.user.id, AuthorizationEvent.change.like("station_%")).order_by(AuthorizationEvent.id))]
    assert "station_granted" in kinds and "station_revoked" in kinds

    # An Administrator places a Supervisor (exactly one station, inside the Administrator's own stations).
    accounts.set_stations(w.db, w.admin_ab.user, w.sup_a.user, [w.b.id], "Transferred to station B (fictional)")
    assert [r.station_id for r in w.db.scalars(select(UserStation).where(UserStation.user_id == w.sup_a.user.id, UserStation.revoked_at.is_(None)))] == [w.b.id]
    with pytest.raises(Invalid, match="exactly one station"):
        accounts.set_stations(w.db, w.admin_ab.user, w.sup_a.user, [w.a.id, w.b.id], "Two stations (fictional)")
    with pytest.raises(Forbidden, match="isn't one of yours"):
        accounts.set_stations(w.db, w.admin_a.user, w.sup_b.user, [w.b.id], "Outside my stations (fictional)")
    with pytest.raises(Forbidden):  # only people below an Administrator
        accounts.set_stations(w.db, w.admin_a.user, w.admin_ab.user, [w.a.id], "Peer (fictional)")
    with pytest.raises(Forbidden):
        accounts.set_stations(w.db, w.sup_b.user, w.inv_b.user, [w.b.id], "A Supervisor can't (fictional)")


# ---------------------------------------------------------------- promotions add no power over existing cases


def test_a_promotion_adds_no_power_over_cases_that_already_exist(world):
    w = world
    own = register(w, w.sup_a, w.inv_a, w.sup_a)  # supervised by sup.a
    other = register(w, w.sup_a2, w.inv_a, w.sup_a2)  # supervised by sup.a2
    family_own, family_other = (w.db.get(CaseFamily, uuid.UUID(c["case_id"])) for c in (own, other))
    hand_over = lambda case, to: w.sup_a.post(f"/api/v1/cases/{case['case_id']}/lead", json={  # noqa: E731
        "user_id": str(to.user.id), "reason": "Handing the case to another Investigator (fictional)"})

    # The Super Admin promotes the Supervisor of station A to Administrator.
    promoted = accounts.change_role(w.db, w.sa.user, w.sup_a.user, "administrator", "Promoted to Administrator (fictional)")
    w.db.commit()
    assert promoted.org_role == "administrator" and promoted.org_role_since is not None
    event = w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.user_id == promoted.id,
                                                          AuthorizationEvent.change == "role_changed")).one()
    assert (event.old_value, event.new_value, event.actor_id) == ("supervisor", "administrator", w.sa.user.id)

    # Seeing is not affected: the whole station, old cases too.
    assert {own["display_id"], other["display_id"]} <= visible_cases(w.sup_a)
    assert w.sup_a.get(f"/api/v1/cases/{other['case_id']}").status_code == 200
    # Changing is: the case they were assigned to stays theirs; a case that existed before is out of reach of the new role.
    assert supervises(promoted, family_own) is True
    assert supervises(promoted, family_other) is False
    assert hand_over(other, w.inv_a2).status_code == 403  # an older case, supervised by someone else

    # A case registered after the promotion is within the Administrator's powers at their station.
    later = register(w, w.sup_a2, w.inv_a, w.sup_a2)
    family_later = w.db.get(CaseFamily, uuid.UUID(later["case_id"]))
    assert family_later.created_at > promoted.org_role_since and supervises(promoted, family_later) is True
    handed = hand_over(later, w.inv_a2)
    assert handed.status_code == 200, handed.text  # a case registered after the promotion is within their powers
    # Nothing was rewritten: the access history still says what they were.
    assert w.db.scalars(select(func.count()).select_from(AuthorizationEvent).where(AuthorizationEvent.user_id == promoted.id)).one() >= 1


def test_who_may_change_whose_role(world):
    w = world
    with pytest.raises(Forbidden, match="own role"):
        accounts.change_role(w.db, w.sup_a.user, w.sup_a.user, "investigator", "Myself (fictional)")
    with pytest.raises(Forbidden):  # an Investigator can't change roles at all
        accounts.change_role(w.db, w.inv_a.user, w.sub_a.user, "analyst", "Not allowed (fictional)")
    with pytest.raises(Forbidden):  # a Supervisor moves people only below Supervisor
        accounts.change_role(w.db, w.sup_a.user, w.inv_a.user, "supervisor", "Too high (fictional)")
    with pytest.raises(Forbidden):  # nobody makes a Super Admin
        accounts.change_role(w.db, w.sa.user, w.admin_a.user, "super_admin", "No (fictional)")
    with pytest.raises(Forbidden, match="one of your stations"):  # another station's people are out of reach
        accounts.change_role(w.db, w.sup_a.user, w.inv_b.user, "analyst", "Wrong station (fictional)")
    moved = accounts.change_role(w.db, w.sup_a.user, w.inv_a2.user, "analyst", "Moved to analysis (fictional)")
    assert moved.org_role == "analyst"
    with pytest.raises(Invalid, match="already"):
        accounts.change_role(w.db, w.sup_a.user, w.inv_a2.user, "analyst", "Again (fictional)")


def test_a_role_change_respects_the_registers_highest_role(world):
    w = world
    officer(w, "INV-Z", w.a, "investigator")
    officer(w, "SUP-Z", w.a, "supervisor")
    low = new_account(w, SimpleNamespace(user=w.sup_a.user), "INV-Z", "investigator")
    with pytest.raises(Forbidden, match="at most the role"):
        accounts.change_role(w.db, w.sa.user, low, "supervisor", "Above the register (fictional)")
    higher = new_account(w, SimpleNamespace(user=w.sup_a.user), "SUP-Z", "investigator")
    assert accounts.change_role(w.db, w.sa.user, higher, "supervisor", "Within the register (fictional)").org_role == "supervisor"
