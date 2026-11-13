"""People and stations through the API (phase R-4, docs/case-management/12-roles-and-stations.md): the chain of who creates whom, first
login with a temporary password, role changes, station assignment, password resets, ending accounts, the register of officers
(one by one and by CSV file) and police stations. All names, numbers and officers are fictional."""

import io
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_cm_stations_roles import make_station, place

from app.casemgmt.models import AuthorizationEvent, PoliceStation
from app.db.models import AuditEvent, User

TEMPORARY = re.compile(r"^[A-Za-z0-9]{4}(-[A-Za-z0-9]{4}){3}$")
OWN_PASSWORD = "My-own-fictional-pass-1"


@pytest.fixture
def people(app_overrides, cm_client, db_session):
    """A Super Admin, two stations, and a helper to log people in with real passwords."""
    clients = []

    def login(username: str, password: str, status: int = 200):
        client = TestClient(app_overrides)
        client.__enter__()
        clients.append(client)
        response = client.post("/api/auth/token", data={"username": username, "password": password})
        assert response.status_code == status, response.text
        if status == 200:
            client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        return client

    w = SimpleNamespace(db=db_session, login=login, cm_client=cm_client)
    w.a, w.b = make_station(db_session, "PS-A"), make_station(db_session, "PS-B")
    w.sa = cm_client("super.admin", "super_admin", "confidential")
    yield w
    for client in clients:
        client.__exit__(None, None, None)


def officer(client, number, station, highest="investigator", name=None, status=201):
    response = client.post("/api/v1/people/officers", json={"officer_number": number, "full_name": name or f"Officer {number} (fictional)",
                                                            "rank": "Inspector", "station_id": str(station.id), "highest_role": highest})
    assert response.status_code == status, response.text
    return response.json()


def make_account(client, number, role, username, status=201, **more):
    response = client.post("/api/v1/people/accounts", json={"officer_number": number, "username": username, "display_name": f"{username.title()} (fictional)",
                                                            "role": role, "clearance": "restricted", **more})
    assert response.status_code == status, response.text
    return response.json()


def first_login(w, username, temporary, own=OWN_PASSWORD):
    """Log in with the temporary password: nothing works until the owner sets their own."""
    client = w.login(username, temporary)
    me = client.get("/api/auth/me").json()
    assert me["must_change_password"] is True
    assert client.get("/api/v1/cases").status_code == 403  # everything else is refused first
    assert client.post("/api/auth/change-password", json={"current_password": temporary, "new_password": own}).status_code == 204
    return w.login(username, own)


# ---------------------------------------------------------------- the chain


def test_the_chain_from_super_admin_to_investigator_with_first_logins(people):
    w = people
    officer(w.sa, "ADM-1", w.a, "administrator")
    officer(w.sa, "SUP-1", w.a, "supervisor")
    officer(w.sa, "INV-1", w.a, "investigator")
    made = make_account(w.sa, "ADM-1", "administrator", "admin.one", extra_station_ids=[str(w.b.id)])
    assert TEMPORARY.match(made["temporary_password"]) and "temporary" in made["handover"]
    assert made["person"]["org_role"] == "administrator" and {s["code"] for s in made["person"]["stations"]} == {"PS-A", "PS-B"}
    assert made["person"]["must_change_password"] is True

    admin = first_login(w, "admin.one", made["temporary_password"])
    w.login("admin.one", made["temporary_password"], status=401)  # the temporary password is gone for good
    sup_made = make_account(admin, "SUP-1", "supervisor", "sup.one")
    sup = first_login(w, "sup.one", sup_made["temporary_password"])
    inv_made = make_account(sup, "INV-1", "investigator", "inv.one")
    inv = first_login(w, "inv.one", inv_made["temporary_password"])
    assert inv.get("/api/v1/people/capabilities").json()["create_roles"] == ["analyst", "sub_investigator", "investigator"]
    assert inv.get("/api/auth/me").json()["must_change_password"] is False

    # Each person made the next one, on the record: who made the account, with which role.
    events = {e.user_id: e for e in w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.change == "account_created"))}
    names = {u.username: u for u in w.db.scalars(select(User).where(User.username.in_(["admin.one", "sup.one", "inv.one"])))}
    assert events[names["admin.one"].id].actor_id == w.sa.user.id
    assert events[names["sup.one"].id].actor_id == names["admin.one"].id
    assert events[names["inv.one"].id].actor_id == names["sup.one"].id


def test_nobody_creates_a_role_above_their_own_and_refusals_are_audited(people):
    w = people
    officer(w.sa, "SUP-2", w.a, "supervisor")
    officer(w.sa, "SUB-2", w.a, "sub_investigator")
    officer(w.sa, "INV-2", w.a, "investigator")
    inv = w.cm_client("inv.two", "investigator")
    place(w.db, inv.user, w.a)
    sub = w.cm_client("sub.two", "sub_investigator")
    place(w.db, sub.user, w.a)
    assert "supervisor" not in inv.get("/api/v1/people/capabilities").json()["create_roles"]

    refused = make_account(inv, "SUP-2", "supervisor", "sup.two", status=403)
    assert "can create only" in refused["detail"]
    make_account(sub, "SUB-2", "sub_investigator", "sub.three", status=403)  # a Sub Investigator creates nobody
    assert sub.get("/api/v1/people/accounts").status_code == 403
    make_account(inv, "NOT-THERE", "investigator", "ghost", status=422)  # not in the register
    first = make_account(inv, "INV-2", "investigator", "inv.three")
    assert first["person"]["org_role"] == "investigator"
    make_account(inv, "INV-2", "investigator", "inv.four", status=409)  # each officer once
    make_account(inv, "SUB-2", "investigator", "sub.four", status=403)  # above what the register allows for that officer

    denied = list(w.db.scalars(select(AuditEvent).where(AuditEvent.action == "cm.people.account_created", AuditEvent.outcome.in_(["denied", "rejected"]))))
    assert len(denied) >= 4  # every refusal is in the audit log
    everything = " ".join(str(e.details) for e in w.db.scalars(select(AuditEvent).where(AuditEvent.action.like("cm.people.%"))))
    assert first["temporary_password"] not in everything  # passwords are never recorded


def test_the_new_password_rules(people):
    w = people
    officer(w.sa, "ADM-3", w.a, "administrator")
    made = make_account(w.sa, "ADM-3", "administrator", "admin.three")
    client = w.login("admin.three", made["temporary_password"])
    wrong = client.post("/api/auth/change-password", json={"current_password": "not-the-password-xx", "new_password": OWN_PASSWORD})
    assert wrong.status_code == 400
    assert client.post("/api/auth/change-password", json={"current_password": made["temporary_password"], "new_password": "short"}).status_code == 422
    assert client.post("/api/auth/change-password", json={"current_password": made["temporary_password"],
                                                          "new_password": made["temporary_password"]}).status_code == 400
    assert client.post("/api/auth/change-password", json={"current_password": made["temporary_password"], "new_password": OWN_PASSWORD}).status_code == 204
    assert client.get("/api/v1/cases").status_code == 200  # free to work now


# ---------------------------------------------------------------- looking after people


def test_listings_show_each_person_what_they_may_do(people):
    w = people
    officer(w.sa, "SUP-4", w.a, "supervisor")
    officer(w.sa, "INV-4", w.a, "investigator")
    officer(w.sa, "INV-B", w.b, "investigator")
    admin = w.cm_client("admin.four", "administrator", "confidential")
    place(w.db, admin.user, w.a)
    officer(w.sa, "INV-5", w.a, "investigator")  # in the register, no account yet
    sup = make_account(admin, "SUP-4", "supervisor", "sup.four")  # Supervisors are made by Administrators
    supc = first_login(w, "sup.four", sup["temporary_password"])
    inv_a = make_account(supc, "INV-4", "investigator", "inv.four")
    # an investigator at the other station
    other = w.cm_client("inv.b", "investigator")
    place(w.db, other.user, w.b)

    everyone = {p["username"]: p for p in w.sa.get("/api/v1/people/accounts").json()}
    assert {"sup.four", "inv.four", "inv.b", "admin.four"} <= set(everyone)  # the Super Admin sees everyone
    mine = {p["username"]: p for p in supc.get("/api/v1/people/accounts").json()}
    assert "inv.four" in mine and "inv.b" not in mine  # a Supervisor sees their own station
    can = mine["inv.four"]["can"]
    assert can["change_role"] and set(can["allowed_roles"]) == {"viewer", "analyst", "sub_investigator"}  # below Supervisor, within the register
    assert can["reset_password"] and can["deactivate"] and not can["set_stations"]
    assert can["change_clearance"] and "confidential" not in can["allowed_clearances"] and can["allowed_clearances"]  # never above the Supervisor's own
    assert mine["sup.four"]["can"] == {"change_role": False, "allowed_roles": [], "change_clearance": False, "allowed_clearances": [],
                                        "set_stations": False, "reset_password": False, "deactivate": False, "reactivate": False}  # nobody changes themselves
    assert everyone["admin.four"]["can"]["set_stations"] is True  # the Super Admin places Administrators

    # Officers: only those the viewer can reach, and `free` = no account yet.
    free = {o["officer_number"] for o in supc.get("/api/v1/people/officers", params={"free": "true"}).json()}
    assert "INV-5" in free and "INV-B" not in free and "INV-4" not in free and "SUP-4" not in free
    five = next(o for o in supc.get("/api/v1/people/officers", params={"free": "true"}).json() if o["officer_number"] == "INV-5")
    assert five["creatable_roles"] == ["viewer", "analyst", "sub_investigator", "investigator"]  # what a Supervisor could make of this officer
    registry = {o["officer_number"]: o for o in w.sa.get("/api/v1/people/officers").json()}
    assert registry["INV-4"]["account"]["username"] == "inv.four" and registry["INV-B"]["account"] is None
    assert registry["INV-B"]["creatable_roles"] == []  # a Super Admin makes only Administrators
    assert inv_a["person"]["officer"]["officer_number"] == "INV-4"
    # Someone at another station is "not found", not "forbidden".
    assert supc.post(f"/api/v1/people/accounts/{other.user.id}/role", json={"role": "analyst", "reason": "Not mine (fictional)"}).status_code == 404


def test_role_station_password_and_ending_an_account(people):
    w = people
    sup = w.cm_client("sup.five", "supervisor", "confidential")
    place(w.db, sup.user, w.a)
    inv = w.cm_client("inv.five", "investigator")
    place(w.db, inv.user, w.a)
    admin = w.cm_client("admin.five", "administrator", "confidential")
    place(w.db, admin.user, w.a)
    url = lambda who, what: f"/api/v1/people/accounts/{who.user.id}/{what}"  # noqa: E731

    # Role: a Supervisor moves an Investigator among the roles below Supervisor.
    moved = sup.post(url(inv, "role"), json={"role": "analyst", "reason": "Moved to analysis (fictional)"})
    assert moved.status_code == 200 and moved.json()["org_role"] == "analyst" and moved.json()["org_role_since"] is not None
    assert sup.post(url(inv, "role"), json={"role": "supervisor", "reason": "Too high (fictional)"}).status_code == 403
    # Password: a reset gives a temporary one, shown once; the person must choose their own again.
    reset = sup.post(url(inv, "reset-password"), json={"reason": "Forgot it (fictional)"})
    assert reset.status_code == 200 and TEMPORARY.match(reset.json()["temporary_password"])
    again = first_login(w, "inv.five", reset.json()["temporary_password"], own="Another-fictional-pass-2")
    assert again.get("/api/v1/cases").status_code == 200
    # Ending an account: no login, history stays; then restored.
    assert sup.post(url(inv, "active"), json={"active": False, "reason": "Left the force (fictional)"}).status_code == 200
    w.login("inv.five", "Another-fictional-pass-2", status=401)
    assert sup.post(url(inv, "active"), json={"active": False, "reason": "Again (fictional)"}).status_code == 422
    assert sup.post(url(inv, "active"), json={"active": True, "reason": "Came back (fictional)"}).status_code == 200
    w.login("inv.five", "Another-fictional-pass-2")
    # Stations: the Super Admin gives the Administrator a second station; an Administrator may not assign to a Super Admin or a peer.
    both = w.sa.post(url(admin, "stations"), json={"station_ids": [str(w.a.id), str(w.b.id)], "reason": "Covers both (fictional)"})
    assert both.status_code == 200 and {s["code"] for s in both.json()["stations"]} == {"PS-A", "PS-B"}
    assert admin.post(url(admin, "stations"), json={"station_ids": [str(w.a.id)], "reason": "Myself (fictional)"}).status_code == 403
    assert inv.post(url(sup, "stations"), json={"station_ids": [str(w.b.id)], "reason": "Sideways (fictional)"}).status_code == 403
    kinds = {e.change for e in w.db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.user_id == inv.user.id))}
    assert {"role_changed", "password_reset", "account_deactivated", "account_reactivated"} <= kinds  # all permanent records


def test_nobody_looks_after_a_peer_or_someone_above_them(people):
    w = people
    sup = w.cm_client("sup.eight", "supervisor", "confidential")
    peer = w.cm_client("sup.nine", "supervisor", "confidential")
    boss = w.cm_client("admin.eight", "administrator", "confidential")
    for client in (sup, peer, boss):
        place(w.db, client.user, w.a)
    listed = {p["username"]: p for p in sup.get("/api/v1/people/accounts").json()}
    for name in ("sup.nine", "admin.eight"):  # a peer and a person above: visible at the station, but nothing to do about them
        assert listed[name]["can"]["reset_password"] is False and listed[name]["can"]["deactivate"] is False and listed[name]["can"]["change_role"] is False
    for target in (peer, boss):
        base = f"/api/v1/people/accounts/{target.user.id}"
        assert sup.post(f"{base}/reset-password", json={"reason": "Not allowed (fictional)"}).status_code == 403
        assert sup.post(f"{base}/active", json={"active": False, "reason": "Not allowed (fictional)"}).status_code == 403
        assert sup.post(f"{base}/role", json={"role": "viewer", "reason": "Not allowed (fictional)"}).status_code == 403
    assert w.db.get(User, peer.user.id).is_active and w.db.get(User, boss.user.id).is_active
    # The Administrator, who is above the Supervisor, may.
    assert boss.post(f"/api/v1/people/accounts/{sup.user.id}/reset-password", json={"reason": "Forgot it (fictional)"}).status_code == 200


# ---------------------------------------------------------------- the register and the stations


def test_officers_by_csv_all_or_nothing(people):
    w = people
    good = "officer_number,full_name,rank,station_code,highest_role\nCSV-1,Officer One (fictional),SI,PS-A,investigator\nCSV-2,Officer Two (fictional),ASI,PS-B,sub_investigator\n"
    sent = w.sa.post("/api/v1/people/officers/import", files={"file": ("officers.csv", io.BytesIO(good.encode()), "text/csv")})
    assert sent.status_code == 200 and sent.json() == {"imported": 2, "errors": []}
    assert {o["officer_number"] for o in w.sa.get("/api/v1/people/officers").json()} >= {"CSV-1", "CSV-2"}

    bad = ("officer_number,full_name,rank,station_code,highest_role\nCSV-3,Officer Three (fictional),SI,PS-A,investigator\n"
           "CSV-1,Duplicate (fictional),SI,PS-A,investigator\nCSV-4,Officer Four (fictional),SI,NOPE,investigator\nCSV-5,Officer Five (fictional),SI,PS-A,emperor\n"
           "CSV-6,Officer Six (fictional),SI,PS-A,super_admin\n")
    result = w.sa.post("/api/v1/people/officers/import", files={"file": ("bad.csv", io.BytesIO(bad.encode()), "text/csv")}).json()
    assert result["imported"] == 0 and [e["row"] for e in result["errors"]] == [3, 4, 5, 6]
    assert "CSV-3" not in {o["officer_number"] for o in w.sa.get("/api/v1/people/officers").json()}  # nothing was entered, not even the good row
    wrong_header = w.sa.post("/api/v1/people/officers/import", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert wrong_header.status_code == 422 and "officer_number" in wrong_header.json()["detail"]
    sup = w.cm_client("sup.six", "supervisor")
    place(w.db, sup.user, w.a)
    assert sup.post("/api/v1/people/officers/import", files={"file": ("officers.csv", io.BytesIO(good.encode()), "text/csv")}).status_code == 403
    assert sup.post("/api/v1/people/officers", json={"officer_number": "X-1", "full_name": "Officer X (fictional)", "rank": "SI",
                                                      "station_id": str(w.a.id), "highest_role": "investigator"}).status_code == 403


def test_stations_are_opened_corrected_and_never_deleted(people):
    w = people
    made = w.sa.post("/api/v1/people/stations", json={"code": "ps-009", "name": "Example Nagar PS (fictional)", "district": "Example district"})
    assert made.status_code == 201 and made.json()["code"] == "PS-009" and made.json()["cases"] == 0
    assert w.sa.post("/api/v1/people/stations", json={"code": "PS-009", "name": "Duplicate (fictional)"}).status_code == 409
    assert w.sa.post("/api/v1/people/stations", json={"code": "bad code!", "name": "Bad (fictional)"}).status_code == 422
    station_id = made.json()["id"]
    renamed = w.sa.post(f"/api/v1/people/stations/{station_id}", json={"name": "Example Nagar Police Station (fictional)", "district": None, "status": "inactive"})
    assert renamed.status_code == 200 and renamed.json()["status"] == "inactive"
    assert w.sa.delete(f"/api/v1/people/stations/{station_id}").status_code == 405  # never deleted
    inactive = w.db.get(PoliceStation, station_id)
    assert inactive.status == "inactive" and inactive.code == "PS-009"  # the code is permanent
    case = w.sa.post("/api/v1/cases", json={"title": "Fictional case", "case_type": "theft", "description": "Fictional: a stolen bicycle (test).", "station_id": station_id})
    assert case.status_code == 422 and "inactive" in case.json()["detail"]  # nothing new at an inactive station

    sup = w.cm_client("sup.seven", "supervisor")
    place(w.db, sup.user, w.a)
    assert sup.post("/api/v1/people/stations", json={"code": "PS-010", "name": "Not allowed (fictional)"}).status_code == 403
    mine = sup.get("/api/v1/people/stations").json()
    assert [s["code"] for s in mine] == ["PS-A"]  # a Supervisor sees only their own station
    assert {s["code"] for s in w.sa.get("/api/v1/people/stations").json()} >= {"PS-A", "PS-B", "PS-009", "HQ"}
