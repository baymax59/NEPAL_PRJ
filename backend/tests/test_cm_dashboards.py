"""Station and officer dashboards (phase R-5, docs/case-management/12-roles-and-stations.md §7).

The test of this phase: every figure on a dashboard equals what the database itself holds (counted here with separate queries),
and a dashboard never counts a case, station or officer its viewer could not open. All names and numbers are fictional."""

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest
from cm_support import add_note, create_case, make_station, place, upload
from sqlalchemy import func, select

from app.casemgmt.models import CaseEntry, CaseFamily, CaseStatusEvent, InvestigationTask
from app.db.models import AuditEvent

CLOSED = ("closed", "archived")


@pytest.fixture
def world(cm_client, db_session):
    """Station A (four officers, a Supervisor, an Administrator), station B (an Investigator and a Supervisor), a Super Admin."""
    a, b = make_station(db_session, "PS-A"), make_station(db_session, "PS-B")
    w = SimpleNamespace(a=a, b=b, db=db_session)
    w.sa = cm_client("super.admin", "super_admin", "confidential")
    w.admin_a = cm_client("admin.a", "administrator", "confidential")
    w.admin_ab = cm_client("admin.ab", "administrator", "confidential")
    w.sup_a = cm_client("sup.a", "supervisor", "confidential")
    w.sup_a2 = cm_client("sup.a2", "supervisor", "confidential")
    w.sup_b = cm_client("sup.b", "supervisor", "confidential")
    w.inv_a1, w.inv_a2, w.inv_b = cm_client("inv.a1"), cm_client("inv.a2"), cm_client("inv.b")
    w.sub_a = cm_client("sub.a", "sub_investigator")
    w.viewer_a = cm_client("viewer.a", "viewer")
    place(db_session, w.admin_a.user, a)
    place(db_session, w.admin_ab.user, a, b)
    for client, station in ((w.sup_a, a), (w.sup_a2, a), (w.inv_a1, a), (w.inv_a2, a), (w.sub_a, a), (w.viewer_a, a),
                            (w.sup_b, b), (w.inv_b, b)):
        place(db_session, client.user, station)
    return w


def register(w, station, lead, supervisor, **fields) -> dict:
    return create_case(w.sa, station_id=str(station.id), lead_investigator_id=str(lead.user.id),
                       supervisor_id=str(supervisor.user.id), **fields)


def set_status(client, case, *statuses) -> None:
    for value in statuses:
        response = client.post(f"/api/v1/cases/{case['case_id']}/status",
                               json={"field": "workflow", "value": value, "reason": "Fictional test transition"})
        assert response.status_code == 200, response.text


def close_after(w, case, days: float, by, archived: bool = False) -> None:
    """Close a case with a closing event dated `days` after it was registered (the real route stamps 'now', which a test
    transaction can't move), so the average time to close has known values. `archived`: and archive it a week later."""
    family = w.db.get(CaseFamily, uuid.UUID(case["case_id"]))
    family.workflow_status = "archived" if archived else "closed"
    w.db.add(CaseStatusEvent(case_family_id=family.id, field="workflow", old_value="investigation_completed", new_value="closed",
                             actor_id=by.user.id, reason="Fictional test", at=family.created_at + dt.timedelta(days=days)))
    if archived:
        w.db.add(CaseStatusEvent(case_family_id=family.id, field="workflow", old_value="closed", new_value="archived",
                                 actor_id=by.user.id, reason="Fictional test", at=family.created_at + dt.timedelta(days=days + 7)))
    w.db.commit()


@pytest.fixture
def cases(world):
    """Station A: five cases (pending evidence, still registered, two closed, pending review). Station B: two (one closed)."""
    w = world
    c = SimpleNamespace()
    c.a1 = register(w, w.a, w.inv_a1, w.sup_a, title="A1 (fictional)")
    c.a2 = register(w, w.a, w.inv_a1, w.sup_a, title="A2 (fictional)")
    c.a3 = register(w, w.a, w.inv_a2, w.sup_a, title="A3 (fictional)")
    c.a4 = register(w, w.a, w.inv_a2, w.sup_a, title="A4 (fictional)")
    c.a5 = register(w, w.a, w.inv_a2, w.sup_a, title="A5 (fictional)")
    c.b1 = register(w, w.b, w.inv_b, w.sup_b, title="B1 (fictional)")
    c.b2 = register(w, w.b, w.inv_b, w.sup_b, title="B2 (fictional)")
    set_status(w.inv_a1, c.a1, "under_investigation", "pending_evidence")
    set_status(w.inv_a2, c.a4, "under_investigation", "pending_review")
    close_after(w, c.a3, 3.5, w.sup_a)
    close_after(w, c.a5, 1.5, w.sup_a, archived=True)  # closed, then archived: still counts as closed
    set_status(w.inv_b, c.b1, "under_investigation", "investigation_completed")
    set_status(w.sup_b, c.b1, "closed")  # the real route: a Supervisor's decision
    return c


def get(client, url, status: int = 200) -> dict:
    response = client.get(url)
    assert response.status_code == status, response.text
    return response.json()


def counted(db, station, *statuses) -> int:
    """What the database itself holds: cases of the station in these statuses (all of them when none are named)."""
    query = select(func.count()).select_from(CaseFamily).where(CaseFamily.station_id == station.id)
    if statuses:
        query = query.where(CaseFamily.workflow_status.in_(statuses))
    return db.scalar(query)


# ---------------------------------------------------------------- the figures equal the database


def test_station_figures_equal_the_database_counts(world, cases):
    w = world
    overview = get(w.sa, "/api/v1/dashboards/stations")
    by_code = {row["station"]["code"]: row for row in overview["stations"]}
    assert {"PS-A", "PS-B"} <= set(by_code)  # the Super Admin: every station
    for code, station in (("PS-A", w.a), ("PS-B", w.b)):
        f = by_code[code]["figures"]
        assert f["total"] == counted(w.db, station)
        assert f["closed"] == counted(w.db, station, *CLOSED)
        assert f["open"] == counted(w.db, station) - counted(w.db, station, *CLOSED)
        assert f["pending_evidence"] == counted(w.db, station, "pending_evidence")
        assert f["pending_review"] == counted(w.db, station, "pending_review")
        assert f["by_status"] == dict(w.db.execute(
            select(CaseFamily.workflow_status, func.count()).where(CaseFamily.station_id == station.id).group_by(CaseFamily.workflow_status)).all())

    a, b = by_code["PS-A"]["figures"], by_code["PS-B"]["figures"]
    assert (a["total"], a["open"], a["closed"], a["pending_evidence"], a["pending_review"]) == (5, 3, 2, 1, 1)
    assert (b["total"], b["open"], b["closed"], b["pending_evidence"], b["pending_review"]) == (2, 1, 1, 0, 0)
    assert a["new_this_month"] == 5 and b["new_this_month"] == 2  # all registered just now
    # People the Super Admin may open: A has sup.a, sup.a2, inv.a1, inv.a2, sub.a, viewer.a and two Administrators; B has two officers and one.
    assert by_code["PS-A"]["officers"] == 8 and by_code["PS-B"]["officers"] == 3
    # An Administrator sees the people below them, and themselves (not the other Administrator).
    assert get(w.admin_a, "/api/v1/dashboards/stations")["stations"][0]["officers"] == 7


def test_station_dashboard_details(world, cases):
    w = world
    d = get(w.sa, f"/api/v1/dashboards/stations/{w.a.id}")
    assert (d["station"]["code"], d["station"]["name"]) == ("PS-A", "PS-A police station (fictional)")
    f = d["figures"]
    assert f["average_days_to_close"] == 2.5  # (3.5 + 1.5) / 2 days, from the closing events in the database
    # The cases open the longest, oldest first: A1, then A2 (A3 and A5 are closed), then A4.
    assert [o["case"]["display_id"] for o in f["oldest_open"]] == [cases.a1["display_id"], cases.a2["display_id"], cases.a4["display_id"]]
    assert all(o["days_open"] == 0 for o in f["oldest_open"])
    assert {o["case"]["workflow_status"] for o in f["oldest_open"]} == {"pending_evidence", "registered", "pending_review"}

    # Month by month: six months, oldest first, ending with this month.
    now = dt.datetime.now(dt.UTC)
    months = [row["month"] for row in d["monthly"]]
    assert len(months) == 6 and months == sorted(months) and months[-1] == now.strftime("%Y-%m")
    assert d["monthly"][-1]["opened"] == 5 and sum(row["opened"] for row in d["monthly"]) == 5
    closing = w.db.scalars(select(CaseStatusEvent.at).where(CaseStatusEvent.new_value == "closed",
                                                            CaseStatusEvent.case_family_id.in_([uuid.UUID(cases.a3["case_id"]), uuid.UUID(cases.a5["case_id"])]))).all()
    this_month = now.strftime("%Y-%m")
    assert sum(row["closed"] for row in d["monthly"]) == sum(1 for at in closing if at.strftime("%Y-%m") <= this_month)

    # No cases have been closed in station B except through the real route: its average is a real (tiny) number, not None.
    b = get(w.sa, f"/api/v1/dashboards/stations/{w.b.id}")["figures"]
    assert b["average_days_to_close"] is not None and b["average_days_to_close"] >= 0


def test_a_station_with_no_cases_says_so(world):
    figures = get(world.sa, f"/api/v1/dashboards/stations/{world.a.id}")["figures"]
    assert (figures["total"], figures["open"], figures["closed"], figures["new_this_month"]) == (0, 0, 0, 0)
    assert figures["average_days_to_close"] is None and figures["oldest_open"] == [] and figures["by_status"] == {}


def test_officers_of_a_station_with_their_own_figures(world, cases):
    w = world
    d = get(w.sa, f"/api/v1/dashboards/stations/{w.a.id}")
    rows = {r["person"]["username"]: r for r in d["officers"]}
    assert set(rows) == {"sup.a", "sup.a2", "inv.a1", "inv.a2", "sub.a", "viewer.a", "admin.a", "admin.ab"}  # everyone at the station
    below = {r["person"]["username"] for r in get(w.admin_a, f"/api/v1/dashboards/stations/{w.a.id}")["officers"]}
    assert below == {"sup.a", "sup.a2", "inv.a1", "inv.a2", "sub.a", "viewer.a", "admin.a"}  # an Administrator: below them, and themselves
    below = {r["person"]["username"] for r in get(w.sup_a, f"/api/v1/dashboards/stations/{w.a.id}")["officers"]}
    assert below == {"sup.a", "inv.a1", "inv.a2", "sub.a", "viewer.a"}  # a Supervisor: below them, and themselves (not sup.a2)
    assert rows["inv.a1"]["person"]["org_role"] == "investigator" and rows["inv.a1"]["person"]["stations"][0]["code"] == "PS-A"
    # What each leads, counted again from the cases themselves.
    assert rows["inv.a1"]["cases"] == {"total": 2, "open": 2, "closed": 0, "pending_evidence": 1, "pending_review": 0}
    assert rows["inv.a2"]["cases"] == {"total": 3, "open": 1, "closed": 2, "pending_evidence": 0, "pending_review": 1}
    assert rows["sup.a"]["cases"]["total"] == 5 and rows["sup.a"]["cases"]["closed"] == 2  # the Supervisor of all five
    assert rows["sup.a2"]["cases"]["total"] == 0 and rows["sub.a"]["cases"]["total"] == 0
    assert rows["viewer.a"]["last_activity"] is None and rows["sub.a"]["last_activity"] is None  # nothing done
    assert rows["inv.a1"]["last_activity"] is not None  # they moved their cases along


def test_an_officers_progress_and_performance(world, cases, db_session, evidence_store):
    w = world
    case_id = cases.a1["case_id"]

    def task(**fields):
        response = w.inv_a1.post(f"/api/v1/cases/{case_id}/tasks", json={"title": "Request the call records (fictional)", "assignee_id": str(w.inv_a1.user.id), **fields})
        assert response.status_code == 201, response.text
        return response.json()

    finished = task()
    for value in ("in_progress", "done"):
        assert w.inv_a1.post(f"/api/v1/tasks/{finished['id']}/status", json={"status": value}).status_code == 200
    task(due_at="2099-01-01T10:00:00+00:00")  # not yet due
    task(due_at="2020-01-01T10:00:00+00:00")  # late
    task(due_at="2020-01-01T10:00:00+00:00")  # late
    cancelled = task(due_at="2020-01-01T10:00:00+00:00")  # cancelled work is neither done nor late
    assert w.inv_a1.post(f"/api/v1/tasks/{cancelled['id']}/status", json={"status": "cancelled", "reason": "Not needed (fictional)"}).status_code == 200

    add_note(w.inv_a1, case_id, folder="investigation-notes", title="First finding (fictional)")
    add_note(w.inv_a1, case_id, folder="cdr-analysis", title="Second finding (fictional)", artifact_type="analysis")
    upload(w.inv_a1, case_id, b"FICTIONAL exhibit", "exhibit.txt", title="An exhibit (fictional)")

    d = get(w.sa, f"/api/v1/dashboards/officers/{w.inv_a1.user.id}")
    assert (d["person"]["username"], d["person"]["org_role"], d["person"]["is_active"]) == ("inv.a1", "investigator", True)
    assert d["tasks"] == {"done": 1, "open": 1, "late": 2}
    assert d["cases"]["total"] == 2 and d["cases"]["pending_evidence"] == 1

    # Counted again from the database: the entries of the case history they made (moving their cases along counts too).
    mine = CaseEntry.actor_id == w.inv_a1.user.id
    in_database = db_session.scalar(select(func.count()).select_from(CaseEntry).where(mine))
    assert in_database >= 3 and d["work"]["entries"] == in_database
    assert d["work"]["entries_last_30_days"] == in_database  # all made just now
    assert (d["work"]["notes"], d["work"]["evidence"]) == (2, 1)
    newest = db_session.scalar(select(func.max(CaseEntry.at)).where(mine))
    assert dt.datetime.fromisoformat(d["last_activity"]) == newest
    assert db_session.scalar(select(func.count()).select_from(InvestigationTask).where(InvestigationTask.assignee_id == w.inv_a1.user.id)) == 5

    # Their cases, with how long each has been open.
    listed = {c["case"]["display_id"]: c for c in d["case_list"]}
    assert set(listed) == {cases.a1["display_id"], cases.a2["display_id"]}
    assert listed[cases.a1["display_id"]]["roles"] == ["lead"] and listed[cases.a1["display_id"]]["active"] is True
    assert listed[cases.a1["display_id"]]["station_code"] == "PS-A" and listed[cases.a1["display_id"]]["days_open"] == 0

    # The Supervisor of the case: their own entries (moving cases along belongs to the leads here), counted the same way.
    s = get(w.sa, f"/api/v1/dashboards/officers/{w.sup_a.user.id}")
    assert s["work"]["entries"] == db_session.scalar(select(func.count()).select_from(CaseEntry).where(CaseEntry.actor_id == w.sup_a.user.id))
    assert "reviews" not in s  # there are no review requests any more


# ---------------------------------------------------------------- who sees what


def test_each_role_sees_only_its_stations_and_officers(world, cases):
    w = world
    def codes(client) -> list[str]:
        return [row["station"]["code"] for row in get(client, "/api/v1/dashboards/stations")["stations"]]

    assert {"PS-A", "PS-B"} <= set(codes(w.sa))
    assert codes(w.admin_ab) == ["PS-A", "PS-B"]
    assert codes(w.admin_a) == ["PS-A"] and codes(w.sup_a) == ["PS-A"] and codes(w.sup_b) == ["PS-B"]

    # Another station answers "not found", like one that doesn't exist.
    for outsider, station in ((w.admin_a, w.b), (w.sup_a, w.b), (w.sup_b, w.a)):
        assert outsider.get(f"/api/v1/dashboards/stations/{station.id}").status_code == 404
    assert w.admin_a.get(f"/api/v1/dashboards/stations/{uuid.uuid4()}").status_code == 404
    assert w.admin_a.get(f"/api/v1/dashboards/stations/{w.a.id}").status_code == 200
    # An Administrator sees their stations' officers (below them) and not someone else's.
    assert w.admin_a.get(f"/api/v1/dashboards/officers/{w.inv_a1.user.id}").status_code == 200
    assert w.admin_a.get(f"/api/v1/dashboards/officers/{w.sup_a.user.id}").status_code == 200
    assert w.admin_a.get(f"/api/v1/dashboards/officers/{w.inv_b.user.id}").status_code == 404
    assert w.admin_a.get(f"/api/v1/dashboards/officers/{w.admin_ab.user.id}").status_code == 404  # a peer: same rank
    assert w.admin_a.get(f"/api/v1/dashboards/officers/{w.sa.user.id}").status_code == 404  # above
    assert w.admin_ab.get(f"/api/v1/dashboards/officers/{w.inv_b.user.id}").status_code == 200
    # A Supervisor sees the people of their own station below them, and themselves.
    assert w.sup_a.get(f"/api/v1/dashboards/officers/{w.inv_a2.user.id}").status_code == 200
    assert w.sup_a.get(f"/api/v1/dashboards/officers/{w.sup_a.user.id}").status_code == 200
    assert w.sup_a.get(f"/api/v1/dashboards/officers/{w.sup_a2.user.id}").status_code == 404  # a peer
    assert w.sup_a.get(f"/api/v1/dashboards/officers/{w.admin_a.user.id}").status_code == 404  # above
    assert w.sup_a.get(f"/api/v1/dashboards/officers/{w.inv_b.user.id}").status_code == 404  # another station
    assert w.sa.get(f"/api/v1/dashboards/officers/{w.inv_b.user.id}").status_code == 200


def test_an_investigator_sees_only_their_own_page(world, cases):
    w = world
    assert w.inv_a1.get(f"/api/v1/dashboards/officers/{w.inv_a1.user.id}").status_code == 200
    assert w.inv_a1.get(f"/api/v1/dashboards/officers/{w.inv_a2.user.id}").status_code == 404
    assert w.inv_a1.get(f"/api/v1/dashboards/officers/{w.sup_a.user.id}").status_code == 404
    assert w.inv_a1.get("/api/v1/dashboards/stations").status_code == 403
    assert w.inv_a1.get(f"/api/v1/dashboards/stations/{w.a.id}").status_code == 403
    me = get(w.inv_a1, f"/api/v1/dashboards/officers/{w.inv_a1.user.id}")
    assert me["cases"]["total"] == 2


def test_the_other_roles_have_no_dashboards(world, cases):
    w = world
    for client in (w.sub_a, w.viewer_a):
        assert client.get("/api/v1/dashboards/stations").status_code == 403
        assert client.get(f"/api/v1/dashboards/stations/{w.a.id}").status_code == 403
        assert client.get(f"/api/v1/dashboards/officers/{client.user.id}").status_code == 403


def test_a_figure_never_counts_a_case_the_viewer_cannot_open(world, cases, db_session):
    w = world
    # An officer who now works at both stations, with a case at each: the Administrator of A sees only the one at A.
    both = w.inv_a1
    place(db_session, both.user, w.a, w.b)
    at_b = register(w, w.b, w.inv_a1, w.sup_b, title="Led from A, at B (fictional)")
    assert at_b["display_id"]

    full = get(w.sa, f"/api/v1/dashboards/officers/{both.user.id}")
    assert full["cases"]["total"] == 3
    narrow = get(w.admin_a, f"/api/v1/dashboards/officers/{both.user.id}")
    assert narrow["cases"]["total"] == 2
    assert {c["case"]["display_id"] for c in narrow["case_list"]} == {cases.a1["display_id"], cases.a2["display_id"]}
    assert {c["case"]["display_id"] for c in full["case_list"]} == {cases.a1["display_id"], cases.a2["display_id"], at_b["display_id"]}
    # The station page of A, shown to A's Administrator, counts the officer's cases at A only.
    rows = {r["person"]["username"]: r for r in get(w.admin_a, f"/api/v1/dashboards/stations/{w.a.id}")["officers"]}
    assert rows["inv.a1"]["cases"]["total"] == 2


def test_a_clearance_hides_cases_from_the_figures(world, cases, cm_client, db_session):
    w = world
    secret_lead = cm_client("inv.conf", "investigator", "confidential")
    secret_sup = cm_client("sup.conf", "supervisor", "confidential")
    place(db_session, secret_lead.user, w.a)
    place(db_session, secret_sup.user, w.a)
    register(w, w.a, secret_lead, secret_sup, title="Confidential matter (fictional)", classification="confidential")
    restricted = cm_client("sup.restricted", "supervisor", "restricted")
    place(db_session, restricted.user, w.a)

    assert get(w.sa, f"/api/v1/dashboards/stations/{w.a.id}")["figures"]["total"] == 6
    assert get(w.sup_a, f"/api/v1/dashboards/stations/{w.a.id}")["figures"]["total"] == 6  # confidential clearance
    assert get(restricted, f"/api/v1/dashboards/stations/{w.a.id}")["figures"]["total"] == 5  # not the confidential one
    assert get(restricted, "/api/v1/dashboards/stations")["stations"][0]["figures"]["total"] == 5


# ---------------------------------------------------------------- they change nothing, and are recorded


def test_dashboards_change_nothing_and_are_audited(world, cases, db_session):
    w = world
    before = (db_session.scalar(select(func.count()).select_from(CaseFamily)), db_session.scalar(select(func.count()).select_from(CaseEntry)),
              db_session.scalar(select(func.count()).select_from(CaseStatusEvent)))
    get(w.admin_a, "/api/v1/dashboards/stations")
    get(w.admin_a, f"/api/v1/dashboards/stations/{w.a.id}")
    get(w.admin_a, f"/api/v1/dashboards/officers/{w.inv_a1.user.id}")
    assert w.admin_a.get(f"/api/v1/dashboards/stations/{w.b.id}").status_code == 404
    after = (db_session.scalar(select(func.count()).select_from(CaseFamily)), db_session.scalar(select(func.count()).select_from(CaseEntry)),
             db_session.scalar(select(func.count()).select_from(CaseStatusEvent)))
    assert before == after

    events = list(db_session.scalars(select(AuditEvent).where(AuditEvent.action.like("cm.dashboard.%")).order_by(AuditEvent.id)))
    assert [(e.action, e.outcome) for e in events] == [
        ("cm.dashboard.stations", "success"), ("cm.dashboard.station", "success"), ("cm.dashboard.officer", "success"),
        ("cm.dashboard.station", "denied")]  # it exists but is outside their stations: refused and recorded
    assert events[1].target_id == "PS-A" and events[2].target_id == "inv.a1"
