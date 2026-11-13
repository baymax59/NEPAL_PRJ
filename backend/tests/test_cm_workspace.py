"""Case Management: what the screens need. Choosing colleagues, dashboards, the live notification stream, case links and the report
preview, on the plain case design. All names, numbers and facts are fictional."""

import asyncio
import hashlib
import json
import uuid
from types import SimpleNamespace

import pytest
from cm_support import PNG, add_member, add_note, create_case, files, folders, history, remove_member, revise, set_status, upload, withdraw
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.casemgmt import stream
from app.casemgmt.models import CaseLink, Organization
from app.db.models import AuditEvent


def team(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, case_id=created["case_id"])


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [c["username"] for c in response.json()]


# ---------------------------------------------------------------- choosing colleagues


def test_colleagues_for_a_new_case_are_only_people_who_could_lead_or_supervise_it(cm_client, db_session):
    registrar = cm_client("inv.registrar")
    cm_client("inv.bala"), cm_client("sup.chitra", "supervisor"), cm_client("analyst.dev", "analyst"), cm_client("viewer.esha", "viewer")
    cm_client("inv.low", clearance="internal")
    other = Organization(code="XY", name="Another force (fictional)")
    db_session.add(other)
    db_session.commit()
    cm_client("inv.outsider", organization=other)

    leads = names(registrar.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted"}))
    assert leads == ["inv.bala", "inv.registrar", "sup.chitra"]  # no analyst, viewer, low clearance or other force
    assert names(registrar.get("/api/v1/colleagues", params={"purpose": "supervisor", "classification": "restricted"})) == ["sup.chitra"]
    assert names(registrar.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "internal"})) == [
        "inv.bala", "inv.low", "inv.registrar", "sup.chitra"]
    assert names(registrar.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted", "q": "BAL"})) == ["inv.bala"]
    first = registrar.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted"}).json()[0]
    assert set(first) == {"id", "username", "display_name", "org_role", "roles"}  # never the clearance

    viewer = cm_client("viewer.only", "viewer")
    assert viewer.get("/api/v1/colleagues", params={"purpose": "lead", "classification": "restricted"}).status_code == 403
    assert registrar.get("/api/v1/colleagues", params={"purpose": "lead"}).status_code == 422


def test_colleagues_to_add_exclude_the_team_and_show_the_parts_each_can_have(cm_client):
    case = team(cm_client)
    meena, analyst = cm_client("inv.meena"), cm_client("analyst.dev", "analyst")
    cm_client("inv.low", clearance="internal")
    add_member(case.lead, case.case_id, meena.user)
    find = {"purpose": "team", "case_id": case.case_id}
    found = {c["username"]: c for c in case.lead.get("/api/v1/colleagues", params=find).json()}
    assert set(found) == {"analyst.dev", "sup.kh"}  # not the lead, the team member or the low clearance
    assert found["analyst.dev"]["roles"] == ["analyst", "viewer"]

    add_member(case.lead, case.case_id, analyst.user, "analyst")
    assert "analyst.dev" not in {c["username"] for c in case.lead.get("/api/v1/colleagues", params=find).json()}  # now on the team
    assert meena.get("/api/v1/colleagues", params=find).status_code == 403  # a Sub Investigator doesn't add people
    stranger = cm_client("inv.stranger")
    assert stranger.get("/api/v1/colleagues", params=find).status_code == 404  # can't see the case at all
    assert case.lead.get("/api/v1/colleagues", params={"purpose": "team"}).status_code == 422  # which case?


# ---------------------------------------------------------------- dashboards


def test_my_contributions_and_the_admin_overview(cm_client, evidence_store):
    admin = cm_client("admin.kh", "super_admin")
    case = team(cm_client)
    add_note(case.lead, case.case_id, folder="investigation-notes", title="Complaint of INR 250000 lost (fictional)")
    exhibit = upload(case.lead, case.case_id, PNG)
    add_note(case.lead, case.case_id, folder="osint", title="Profile (fictional)", artifact_type="analysis")
    meena = cm_client("inv.meena")
    add_member(case.lead, case.case_id, meena.user)
    add_note(meena, case.case_id, title="Meena's note (fictional)")
    remove_member(case.lead, case.case_id, meena.user)

    mine = case.lead.get("/api/v1/contributions/mine").json()
    assert mine["totals"] == {"entries": 5, "notes": 2, "revisions": 0, "evidence": 1}  # 2 notes, 1 exhibit, adding and removing Meena
    assert mine["no_longer_open"] == {"entries": 0, "notes": 0, "revisions": 0, "evidence": 0}
    assert mine["entries"][0]["kind"] == "member_removed" and mine["entries"][0]["case"]["id"] == case.case_id  # newest first
    gone = meena.get("/api/v1/contributions/mine").json()  # she can no longer open the case: her work is credited, as numbers only
    assert gone["entries"] == [] and gone["totals"]["entries"] == 0
    assert gone["no_longer_open"] == {"entries": 1, "notes": 1, "revisions": 0, "evidence": 0}  # her one note

    overview = admin.get("/api/v1/admin/overview")
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["cases"]["total"] == 1 and data["cases"]["by_type"][0]["label"] == "Cyber / online fraud"
    assert data["files"] == {"notes": 4, "exhibits": 1, "withdrawn": 0}  # summary, two notes, Meena's note; one exhibit
    assert len(data["activity"]["per_day"]) == 30 and sum(d["entries"] for d in data["activity"]["per_day"]) == data["activity"]["total"]
    assert data["evidence"]["items"] == 1 and data["evidence"]["integrity"] == {"never_checked": 1}
    assert data["tasks"] == {"open": 0, "overdue": 0} and data["recent_entries"][0]["case"]["display_id"]
    assert case.lead.get("/api/v1/admin/overview").status_code == 403
    assert case.lead.post(f"/api/v1/evidence/{exhibit['evidence']['id']}/verify").json()["result"] == "match"
    assert admin.get("/api/v1/admin/overview").json()["evidence"] == {"items": 1, "bytes": len(PNG), "integrity": {"match": 1}, "alerts": []}


# ---------------------------------------------------------------- live notices


def read_stream(client) -> list[str]:
    with client.stream("GET", "/api/v1/notifications/stream") as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        return [line for line in response.iter_lines() if line]


def test_the_notification_stream_tells_the_browser_when_notices_change(cm_client, anonymous_api, monkeypatch, db_session):
    monkeypatch.setattr(stream, "POLL_SECONDS", 0)
    monkeypatch.setattr(stream, "STREAM_SECONDS", 0)  # one check, then "reconnect"
    case = team(cm_client)
    meena = cm_client("inv.meena")
    assert read_stream(meena) == ["retry: 5000", "event: notices", 'data: {"unread": 0, "latest": null}', "event: reconnect", "data: {}"]

    add_member(case.lead, case.case_id, meena.user)  # added at once: she is told
    lines = read_stream(meena)
    assert lines[1] == "event: notices" and lines[2].startswith('data: {"unread": 1, "latest": ')  # counts only, no content

    assert anonymous_api.get("/api/v1/notifications/stream").status_code == 401
    assert anonymous_api.get("/api/v1/notifications/stream", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    audited = db_session.scalars(select(AuditEvent.action).where(AuditEvent.action == "cm.notifications.stream")).all()
    assert len(audited) == 2


def test_the_stream_ends_when_the_login_is_no_longer_valid(monkeypatch):
    monkeypatch.setattr(stream, "POLL_SECONDS", 0)
    answers = iter([{"unread": 2, "latest": 7}, {"unread": 2, "latest": 7}, None])

    async def connected() -> bool:
        return False

    async def collect() -> list[str]:
        return [chunk async for chunk in stream.events(lambda: next(answers), connected)]

    chunks = asyncio.run(collect())
    assert chunks == ["retry: 5000\n\n", 'event: notices\ndata: {"unread": 2, "latest": 7}\n\n', "event: expired\ndata: {}\n\n"]


# ---------------------------------------------------------------- live pages


def watch_stream(client, watch: str) -> list[str]:
    with client.stream("GET", "/api/v1/notifications/stream", params={"watch": watch}) as response:
        assert response.status_code == 200, response.read()
        return [line for line in response.iter_lines() if line]


def activity_of(lines: list[str]) -> str | None:
    """The fingerprint carried by a stream's `activity` event, if it sent one."""
    for i, line in enumerate(lines):
        if line == "event: activity":
            return json.loads(lines[i + 1].removeprefix("data: "))["marker"]
    return None


def test_an_open_page_is_told_when_what_it_shows_changes_and_only_then(cm_client, monkeypatch, db_session, evidence_store):
    monkeypatch.setattr(stream, "POLL_SECONDS", 0)
    monkeypatch.setattr(stream, "STREAM_SECONDS", 0)  # one check, then "reconnect"
    case = team(cm_client)
    page = f"case:{case.case_id}"
    lines = watch_stream(case.lead, page)
    assert lines[1] == "event: notices" and lines[3] == "event: activity"
    first = activity_of(lines)
    assert json.loads(lines[4].removeprefix("data: ")) == {"scope": page, "marker": first} and len(first) == 16

    def marker(client=case.lead, watch=page):
        return stream.activity_marker(db_session, client.user, stream.parse_watch(watch))

    # Reading changes nothing (every read is audited, so a refresh must never cause another one) ...
    exhibit = upload(case.lead, case.case_id, PNG)["evidence"]
    baseline = marker()
    assert baseline != first  # the upload was a history entry
    case.lead.get(f"/api/v1/cases/{case.case_id}")
    case.lead.get(f"/api/v1/cases/{case.case_id}/history")
    case.lead.get(f"/api/v1/cases/{case.case_id}/files")
    assert case.lead.get(f"/api/v1/evidence/{exhibit['id']}/preview").status_code == 200  # an 'accessed' custody event
    assert marker() == baseline
    # ... and every kind of change does: a note, a task, a comment, an integrity check, a folder, a team change, a status.
    seen = {baseline}
    helper = cm_client("sub.helper", "sub_investigator")
    changes = [
        lambda: add_note(case.lead, case.case_id, title="Fictional note."),
        lambda: case.lead.post(f"/api/v1/cases/{case.case_id}/tasks", json={"title": "Fictional task"}),
        lambda: case.lead.post(f"/api/v1/cases/{case.case_id}/comments", json={
            "target_type": "case", "target_id": case.case_id, "body": "Fictional comment."}),
        lambda: case.lead.post(f"/api/v1/evidence/{exhibit['id']}/verify", json={}),
        lambda: case.lead.post(f"/api/v1/cases/{case.case_id}/folders", json={"name": "Extra folder"}),
        lambda: add_member(case.lead, case.case_id, helper.user),
        lambda: set_status(case.lead, case.case_id, "under_investigation"),
    ]
    for change in changes:
        answer = change()
        assert getattr(answer, "status_code", 201) < 300, getattr(answer, "text", answer)
        assert marker() not in seen
        seen.add(marker())
    # Another case's change is not this page's.
    other = create_case(case.supervisor, lead_investigator_id=str(case.lead.user.id), supervisor_id=str(case.supervisor.user.id))
    before = marker()
    add_note(case.lead, other["case_id"], title="Another case (fictional)")
    assert marker() == before
    # The evidence page follows the same case; the stream sends a new fingerprint.
    assert marker(watch=f"evidence:{exhibit['id']}") is not None
    assert activity_of(watch_stream(case.lead, page)) == marker() != first


def test_a_page_the_user_may_not_open_gives_no_activity_at_all(cm_client, monkeypatch, db_session, evidence_store):
    monkeypatch.setattr(stream, "POLL_SECONDS", 0)
    monkeypatch.setattr(stream, "STREAM_SECONDS", 0)
    case = team(cm_client)
    exhibit = upload(case.lead, case.case_id, PNG)["evidence"]
    outsider = cm_client("inv.outsider")
    for watch in (f"case:{case.case_id}", f"evidence:{exhibit['id']}", "admin", f"case:{uuid.uuid4()}"):  # an outsider, or a page that doesn't exist
        lines = watch_stream(outsider, watch)
        assert "event: notices" in lines and "event: activity" not in lines, watch
    # A sealed exhibit's page is for the supervisor only: for the lead on the team it is as if it didn't exist (the case page is still theirs).
    sealed = case.supervisor.post(f"/api/v1/evidence/{exhibit['id']}/seal", json={"reason": "Protected witness (fictional)"})
    assert sealed.status_code == 200, sealed.text
    assert "event: activity" not in watch_stream(case.lead, f"evidence:{exhibit['id']}")
    assert activity_of(watch_stream(case.supervisor, f"evidence:{exhibit['id']}")) is not None
    assert activity_of(watch_stream(case.lead, f"case:{case.case_id}")) is not None
    assert case.lead.get("/api/v1/notifications/stream", params={"watch": "case:not-an-id"}).status_code == 422
    assert case.lead.get("/api/v1/notifications/stream", params={"watch": "everything"}).status_code == 422
    assert case.lead.get("/api/v1/notifications/stream", params={"watch": f"repository:{uuid.uuid4()}"}).status_code == 422  # no such page any more
    # The administration pages: platform administrators only; the watched page is in the stream's audit event.
    admin = cm_client("kh.admin", "super_admin", "confidential")
    assert stream.activity_marker(db_session, case.supervisor.user, stream.Watch("admin")) is None
    before = stream.activity_marker(db_session, admin.user, stream.Watch("admin"))
    add_note(case.lead, case.case_id, title="Fictional note.")
    assert stream.activity_marker(db_session, admin.user, stream.Watch("admin")) not in (None, before)
    assert activity_of(watch_stream(admin, "admin")) is not None
    watched = db_session.scalars(select(AuditEvent.details).where(AuditEvent.action == "cm.notifications.stream")).all()
    assert {"watch": "admin"} in watched and {"watch": f"case:{case.case_id}"} in watched


def test_activity_events_follow_the_fingerprint_at_most_as_often_as_allowed(monkeypatch):
    monkeypatch.setattr(stream, "POLL_SECONDS", 0)

    async def connected() -> bool:
        return False

    def run(markers: list[str], every: float) -> list[str]:
        answers = iter([*({"unread": 0, "latest": None, "activity": m} for m in markers), None])

        async def collect() -> list[str]:
            return [chunk async for chunk in stream.events(lambda: next(answers), connected, scope="admin", activity_every=every)]

        return [c for c in asyncio.run(collect()) if c.startswith("event: activity")]

    def sent(marker: str) -> str:
        return f'event: activity\ndata: {{"scope": "admin", "marker": "{marker}"}}\n\n'

    assert run(["a", "a", "b", "b", "c"], every=0) == [sent("a"), sent("b"), sent("c")]  # each change, once
    assert run(["a", "b", "c"], every=3600) == [sent("a")]  # admin pages: at most every ADMIN_ACTIVITY_SECONDS


# ---------------------------------------------------------------- case links


def link(client, case_id, target_case_id, link_type="same_person", reason="Fictional: the same mule account in both cases.", status=201) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/links", json={"target_case_id": target_case_id, "link_type": link_type, "reason": reason})
    assert response.status_code == status, response.text
    return response.json()


def test_cases_are_linked_with_a_reason_and_the_link_stays_in_history(cm_client, db_session):
    case = team(cm_client)
    other = create_case(case.supervisor, title="Second online fraud (FICTIONAL)", lead_investigator_id=str(case.lead.user.id),
                        supervisor_id=str(case.supervisor.user.id))
    added = link(case.lead, case.case_id, other["case_id"])
    assert added["display_id"] == "LNK-0001" and history(case.lead, case.case_id)[-1]["kind"] == "link_added"
    assert {f["name"]: f["system"] for f in folders(case.lead, case.case_id)}["links"] is True  # the links folder is made when needed

    links = case.lead.get(f"/api/v1/cases/{case.case_id}/links").json()
    [outgoing] = links["outgoing"]
    assert (outgoing["label"], outgoing["status"], outgoing["target"]["display_id"]) == ("Same person of interest", "active", other["display_id"])
    assert outgoing["target_now"]["title"] == "Second online fraud (FICTIONAL)"
    [incoming] = case.lead.get(f"/api/v1/cases/{other['case_id']}/links").json()["incoming"]
    assert incoming["case"]["id"] == case.case_id

    link(case.lead, case.case_id, other["case_id"], status=409)  # already linked
    link(case.lead, case.case_id, case.case_id, status=422)  # not to itself
    link(case.lead, case.case_id, other["case_id"], link_type="best_friends", status=422)
    revise(case.lead, added["artifact_id"], "changed", 1, status=422)  # a link can't be edited

    withdraw(case.lead, "artifacts", added["artifact_id"], reason="Linked by mistake (fictional)")
    now = case.lead.get(f"/api/v1/cases/{case.case_id}/links").json()
    assert [(o["status"], o["withdrawn_reason"]) for o in now["outgoing"]] == [("withdrawn", "Linked by mistake (fictional)")]
    assert case.lead.get(f"/api/v1/cases/{other['case_id']}/links").json()["incoming"] == []  # recorded, but no longer in force
    link(case.lead, case.case_id, other["case_id"])  # and the cases can be linked again, as a new link
    assert len(db_session.scalars(select(CaseLink)).all()) == 2

    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE case_links SET reason = 'changed'"))
    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM case_links"))


def test_links_need_access_to_both_cases_and_show_only_what_the_viewer_can_open(cm_client):
    case = team(cm_client)
    other_lead, meena = cm_client("inv.other"), cm_client("inv.meena")
    hidden = create_case(other_lead, title="Someone else's case (FICTIONAL)")
    link(case.lead, case.case_id, hidden["case_id"], status=404)  # can't link to a case you can't open

    target = create_case(case.supervisor, title="Linked case (FICTIONAL)", lead_investigator_id=str(case.lead.user.id),
                         supervisor_id=str(case.supervisor.user.id))
    link(case.lead, case.case_id, target["case_id"])  # the lead can open both
    add_member(case.lead, target["case_id"], other_lead.user, "viewer")  # can open the linked case only
    add_member(case.lead, case.case_id, meena.user)  # can open the linking case only
    assert other_lead.get(f"/api/v1/cases/{target['case_id']}/links").json()["incoming"] == []
    assert len(case.supervisor.get(f"/api/v1/cases/{target['case_id']}/links").json()["incoming"]) == 1
    [outgoing] = meena.get(f"/api/v1/cases/{case.case_id}/links").json()["outgoing"]
    assert outgoing["target"]["display_id"] == target["display_id"] and outgoing["target_now"] is None  # as recorded only
    viewer = cm_client("view.only", "viewer")
    add_member(case.lead, case.case_id, viewer.user, "viewer")
    add_member(case.lead, target["case_id"], viewer.user, "viewer")
    link(viewer, case.case_id, target["case_id"], link_type="related", status=403)  # a Viewer can open both, but only reads


# ---------------------------------------------------------------- report preview


def test_the_report_preview_describes_the_case_with_provenance_and_integrity(cm_client, evidence_store):
    case = team(cm_client)
    exhibit = upload(case.lead, case.case_id, PNG, collected_at="2026-11-02T14:30:00+05:30")
    assert case.lead.post(f"/api/v1/evidence/{exhibit['evidence']['id']}/verify").json()["result"] == "match"
    add_note(case.lead, case.case_id, folder="investigation-notes", title="Complaint of INR 250000 lost (fictional)")
    add_note(case.lead, case.case_id, folder="osint", title="Profile (fictional)", artifact_type="analysis")

    preview = case.lead.get(f"/api/v1/cases/{case.case_id}/report-preview")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    [evidence] = data["evidence"]
    assert (evidence["sha256"], evidence["original_filename"], evidence["folder"]) == (hashlib.sha256(PNG).hexdigest(), "whatsapp-message.png", "digital-evidence")
    assert evidence["custodian"]["user"]["username"] == "inv.arun" and evidence["last_check"]["result"] == "match"
    assert {a["display_id"] for a in data["artifacts"]} == {"SUM-0001", "NOTE-0001", "ANL-0001"}
    assert data["integrity"] == {"match": 1, "mismatch": 0, "missing": 0, "never_checked": 0}
    assert data["history"] == {"entries": 4, "intact": True} and data["withheld_entries"] == 0
    assert [(m["user"]["username"], m["role"]) for m in data["team"]] == [("inv.arun", "lead")]
    assert "case-information" in data["folders"] and "not automatically admissible" in data["disclaimer"]

    # Sealed: left out for the lead (and counted), included for the supervisor.
    sealed = case.supervisor.post(f"/api/v1/evidence/{exhibit['evidence']['id']}/seal", json={"reason": "Protected witness (fictional)"})
    assert sealed.status_code == 200, sealed.text
    hidden = case.lead.get(f"/api/v1/cases/{case.case_id}/report-preview").json()
    assert hidden["evidence"] == [] and hidden["withheld_entries"] == 1
    assert len(case.supervisor.get(f"/api/v1/cases/{case.case_id}/report-preview").json()["evidence"]) == 1
    # A withdrawn file is listed as withdrawn, with its reason.
    note = files(case.lead, case.case_id, folder="osint")[0]
    withdraw(case.lead, "artifacts", note["id"], reason="Not about this case (fictional)")
    assert "ANL-0001" not in [a["display_id"] for a in case.lead.get(f"/api/v1/cases/{case.case_id}/report-preview").json()["artifacts"]]  # gone for the team
    listed = {a["display_id"]: a for a in case.supervisor.get(f"/api/v1/cases/{case.case_id}/report-preview").json()["artifacts"]}
    assert (listed["ANL-0001"]["status"], listed["ANL-0001"]["withdrawn_reason"]) == ("withdrawn", "Not about this case (fictional)")
