"""Case Management: who sees a case (404 like a missing one), the administrators' view, no deletion or rewriting, and the rules the
database enforces itself (fictional data)."""

import uuid
from types import SimpleNamespace

import pytest
from cm_support import add_member, add_note, case, create_case, history, upload
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.casemgmt.models import APPEND_ONLY_TABLES, NO_DELETE_TABLES, Organization
from app.db.models import AuditEvent


def investigation(cm_client):
    """A case with a note, an exhibit and one more team member."""
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    note = add_note(lead, created["case_id"], title="Three transfers, INR 250000 in total (fictional)")["file"]
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, id=created["case_id"], note=note)


def test_people_outside_a_case_get_404_exactly_like_for_a_missing_one(cm_client, db_session):
    t = investigation(cm_client)
    stranger = cm_client("inv.other")
    hidden = stranger.get(f"/api/v1/cases/{t.id}")
    missing = stranger.get(f"/api/v1/cases/{uuid.uuid4()}")
    assert hidden.status_code == missing.status_code == 404 and hidden.json() == missing.json() == {"detail": "Not found"}
    for url in ("files", "history", "history/check", "team", "folders", "tasks", "access-history"):
        assert stranger.get(f"/api/v1/cases/{t.id}/{url}").status_code == 404, url
    assert stranger.get(f"/api/v1/artifacts/{t.note['id']}/versions").status_code == 404
    assert stranger.get("/api/v1/cases").json()["total"] == 0 and stranger.get("/api/v1/cases/mine").json() == []
    outcomes = db_session.scalars(select(AuditEvent.outcome).where(
        AuditEvent.action == "cm.case.view", AuditEvent.username == "inv.other").order_by(AuditEvent.id)).all()
    assert outcomes == ["denied", "not_found"]  # the log knows the difference; the user can't tell


def test_other_organisations_and_lower_clearances_see_nothing(cm_client, db_session):
    t = investigation(cm_client)
    other = Organization(code="XY", name="Another force (fictional)")
    db_session.add(other)
    db_session.commit()
    foreign_admin = cm_client("admin.xy", "super_admin", "confidential", organization=other)
    assert foreign_admin.get(f"/api/v1/cases/{t.id}").status_code == 404
    assert foreign_admin.get(f"/api/v1/admin/cases/{t.id}/audit").status_code == 404
    assert foreign_admin.get("/api/v1/admin/cases").json()["total"] == 0
    low_admin = cm_client("admin.low", "super_admin", "internal")  # the case is restricted
    assert low_admin.get(f"/api/v1/cases/{t.id}").status_code == 404
    assert cm_client("admin.kh", "super_admin", "restricted").get(f"/api/v1/cases/{t.id}").status_code == 200


def test_every_part_reads_the_case_but_only_some_change_it(cm_client):
    t = investigation(cm_client)
    sub, analyst, viewer = cm_client("sub.one", "sub_investigator"), cm_client("analyst.one", "analyst"), cm_client("viewer.one", "viewer")
    for client, role in ((sub, "sub_investigator"), (analyst, "analyst"), (viewer, "viewer")):
        add_member(t.lead, t.id, client.user, role)
    for client in (sub, analyst, viewer, t.lead, t.supervisor):  # everyone can read
        for url in ("", "/files", "/history", "/team", "/folders", "/tasks"):
            assert client.get(f"/api/v1/cases/{t.id}{url}").status_code == 200, url
    can = {name: case(client, t.id)["can"] for name, client in (("lead", t.lead), ("sub", sub), ("analyst", analyst), ("viewer", viewer))}
    assert [can[n]["add_files"] for n in ("lead", "sub", "analyst", "viewer")] == [True, True, True, False]
    assert [can[n]["manage_team"] for n in ("lead", "sub", "analyst", "viewer")] == [True, False, False, False]
    assert [can[n]["add_folders"] for n in ("lead", "sub", "analyst", "viewer")] == [True, False, False, False]
    assert [can[n]["change_workflow_status"] for n in ("lead", "sub", "analyst", "viewer")] == [True, False, False, False]
    assert can["lead"]["hand_over"] is False and case(t.supervisor, t.id)["can"]["hand_over"] is True


def test_the_admin_sees_every_case_with_its_team_and_history(cm_client, evidence_store):
    t = investigation(cm_client)
    upload(t.lead, t.id, b"FICTIONAL exhibit", "exhibit.txt", title="An exhibit (fictional)")
    sub = cm_client("sub.admin", "sub_investigator")
    add_member(t.lead, t.id, sub.user)
    admin = cm_client("admin.kh", "super_admin", "restricted")
    [item] = admin.get("/api/v1/admin/cases").json()["items"]
    assert item["display_id"] == t.created["display_id"] and [p["username"] for p in item["leads"]] == ["inv.arun"]
    assert item["supervisor"]["username"] == "sup.kh" and item["station_code"] == "HQ"
    assert (item["files"], item["evidence_count"], item["entries"]) == (3, 1, 4)  # files: summary, note, exhibit; entries: registered, note, exhibit, member added
    access = admin.get(f"/api/v1/admin/cases/{t.id}/access-history").json()
    assert [(a["user"]["username"], a["change"]) for a in access] == [("inv.arun", "membership_granted"), ("sub.admin", "membership_granted")]
    assert t.lead.get(f"/api/v1/admin/cases/{t.id}/access-history").status_code == 403  # administrators only
    audit = admin.get(f"/api/v1/admin/cases/{t.id}/audit").json()
    assert {"cm.case.created", "cm.note.added", "cm.evidence.added", "cm.team.added"} <= {e["action"] for e in audit["items"]}
    assert [e["seq"] for e in history(admin, t.id)] == [1, 2, 3, 4]
    assert admin.get(f"/api/v1/cases/{t.id}/history/check").json()["intact"] is True


def test_team_members_cannot_grant_themselves_privileges(cm_client):
    t = investigation(cm_client)
    sub, friend = cm_client("sub.one", "sub_investigator"), cm_client("sub.friend", "sub_investigator")
    add_member(t.lead, t.id, sub.user)
    add_member(sub, t.id, friend.user, status=403)  # a Sub Investigator doesn't add people
    add_member(sub, t.id, sub.user, status=403)
    assert sub.post(f"/api/v1/cases/{t.id}/team/{sub.user.id}/remove", json={"reason": "Leaving myself (fictional)"}).status_code == 403
    assert sub.post(f"/api/v1/cases/{t.id}/team/{t.lead.user.id}/remove", json={"reason": "Removing the lead (fictional)"}).status_code == 403
    assert sub.post(f"/api/v1/cases/{t.id}/lead", json={"user_id": str(sub.user.id), "reason": "Making myself the lead"}).status_code == 403
    for method in ("PUT", "PATCH", "DELETE"):  # there is no way to change a part by request
        assert sub.request(method, f"/api/v1/cases/{t.id}/team/{sub.user.id}", json={"role": "lead"}).status_code == 405
    assert case(sub, t.id)["my_role"] == "sub_investigator"


def test_deleting_or_rewriting_history_is_refused_and_audited(cm_client, db_session):
    t = investigation(cm_client)
    attempts = [("DELETE", f"/api/v1/cases/{t.id}"), ("PUT", f"/api/v1/cases/{t.id}/history"), ("PATCH", f"/api/v1/cases/{t.id}"),
                ("DELETE", f"/api/v1/artifacts/{t.note['id']}"), ("POST", f"/api/v1/cases/{t.id}/history/reset"),
                ("POST", f"/api/v1/cases/{t.id}/history/rewrite")]
    for method, url in attempts:
        response = t.lead.request(method, url, json={})
        assert response.status_code == 405, (method, url)
        assert "permanent" in response.json()["detail"]
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.destructive_operation.rejected")).all()
    assert len(events) == len(attempts) and {e.outcome for e in events} == {"rejected"}
    assert t.created["display_id"] in {e.target_id for e in events}
    assert t.lead.get(f"/api/v1/artifacts/{t.note['id']}/versions").status_code == 200  # all still there
    assert t.lead.post(f"/api/v1/cases/{t.id}/unknown-action").status_code == 404


DATABASE_REFUSES = [
    ("UPDATE artifact_versions SET content = '{}'::jsonb", "permanent"),
    ("DELETE FROM artifact_versions", "permanent"),
    ("DELETE FROM case_families", "permanent"),
    ("UPDATE case_families SET title = 'Renamed'", "only"),
    ("UPDATE case_families SET station_id = gen_random_uuid()", "only"),
    ("DELETE FROM artifacts", "permanent"),
    ("UPDATE artifacts SET folder_id = gen_random_uuid()", "only"),
    ("UPDATE artifacts SET title = 'Renamed'", "only"),
    ("DELETE FROM case_members", "permanent"),
    ("UPDATE case_members SET role = 'viewer'", "only"),
    ("UPDATE case_members SET user_id = gen_random_uuid()", "only"),
    ("DELETE FROM case_status_events", "permanent"),
    ("UPDATE case_status_events SET new_value = 'closed'", "permanent"),
    ("UPDATE authorization_events SET reason = 'edited afterwards'", "permanent"),
    ("DELETE FROM authorization_events", "permanent"),
    ("UPDATE notifications SET kind = 'something else'", "only"),
    ("DELETE FROM notifications", "permanent"),
    ("UPDATE case_entries SET kind = 'note_added'", "permanent"),
    ("DELETE FROM case_entries", "permanent"),
]


@pytest.mark.parametrize(("statement", "message"), DATABASE_REFUSES)
def test_the_database_itself_refuses_to_change_or_delete_the_record(cm_client, db_session, statement, message):
    t = investigation(cm_client)
    add_member(t.lead, t.id, cm_client("sub.db", "sub_investigator").user)
    with pytest.raises(IntegrityError, match=message):
        with db_session.begin_nested():
            db_session.execute(text(statement))


def test_the_database_allows_only_the_changes_a_record_is_meant_to_have(cm_client, db_session):
    t = investigation(cm_client)
    sub = cm_client("sub.ok", "sub_investigator")
    add_member(t.lead, t.id, sub.user)
    with db_session.begin_nested():  # who is on a team may end; nothing else about the row changes
        db_session.execute(text("UPDATE case_members SET revoked_at = now(), revoked_by = user_id WHERE role = 'sub_investigator'"))
        db_session.execute(text("UPDATE artifacts SET status = 'withdrawn', withdrawn_reason = 'direct test'"))
        db_session.execute(text("UPDATE artifacts SET sealed = true, sealed_reason = 'direct test'"))
        db_session.execute(text("UPDATE case_families SET workflow_status = 'open'"))


def test_the_migration_installed_the_database_rules(db_session):
    triggers = set(db_session.scalars(text("SELECT tgname FROM pg_trigger WHERE tgname LIKE 'cm\\_%' AND NOT tgisinternal")))
    assert {"cm_case_entries_permanent", "cm_case_entries_in_order", "cm_case_folders_permanent", "cm_case_members_status_only",
            "cm_case_families_status_only", "cm_artifacts_status_only", "cm_evidence_items_status_only"} <= triggers
    # The git-style rules are gone with their tables.
    assert not {t for t in triggers if "commit" in t or "branch" in t or "repositor" in t or "snapshot" in t}
    for table in APPEND_ONLY_TABLES:
        assert f"cm_{table}_permanent" in triggers, table
    assert {"cm_audit_events_chain", "cm_audit_events_permanent"} <= triggers
    status_only = {t for t in NO_DELETE_TABLES if f"cm_{t}_status_only" in triggers}
    assert {"case_families", "case_members", "evidence_items", "artifacts", "investigation_tasks", "notifications"} <= status_only
