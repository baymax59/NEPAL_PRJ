"""Case Management: the task board, comments and notifications on the plain case design (fictional data)."""

import uuid
from types import SimpleNamespace

import pytest
from cm_support import PNG, add_member, add_note, create_case, notices, set_status, upload
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def team(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    meena, viewer = cm_client("inv.meena"), cm_client("viewer.one", "viewer")
    add_member(lead, case_id, meena.user)
    add_member(lead, case_id, viewer.user, "viewer")
    return SimpleNamespace(supervisor=supervisor, lead=lead, meena=meena, viewer=viewer, created=created, id=case_id)


def new_task(client, case_id, status: int = 201, **fields) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/tasks", json={"title": "Request the call records (fictional)", **fields})
    assert response.status_code == status, response.text
    return response.json()


def test_the_task_board(cm_client, db_session):
    case = team(cm_client)
    task = new_task(case.lead, case.id, assignee_id=str(case.meena.user.id), due_at="2026-11-20T17:00:00+05:30",
                    description="From the operator, for 1-3 November (fictional)")
    assert (task["display_id"], task["status"], task["assignee"]["username"]) == ("TASK-0001", "open", "inv.meena")
    assert [t["display_id"] for t in case.meena.get("/api/v1/tasks/mine").json()] == ["TASK-0001"]
    assert notices(case.meena)[0] == "task.assigned"

    new_task(case.viewer, case.id, status=403)  # viewers read only
    new_task(case.lead, case.id, assignee_id=str(case.viewer.user.id), status=422)  # tasks go to people who work on it
    new_task(case.lead, case.id, assignee_id=str(cm_client("inv.stranger").user.id), status=422)  # not on the team

    url = f"/api/v1/tasks/{task['id']}"
    started = case.meena.post(f"{url}/status", json={"status": "in_progress"}).json()
    assert (started["status"], started["version"]) == ("in_progress", 1)
    assert case.meena.post(f"{url}/status", json={"status": "done", "expected_version": 0}).status_code == 409  # someone was quicker
    assert case.viewer.post(f"{url}/status", json={"status": "done"}).status_code == 403
    assert case.meena.post(f"{url}/status", json={"status": "done", "expected_version": 1}).json()["status"] == "done"
    assert case.meena.post(f"{url}/status", json={"status": "open"}).status_code == 422  # reopening needs a reason
    reopened = case.lead.post(f"{url}/status", json={"status": "open", "reason": "Wrong period received (fictional)"}).json()
    assert [(e["field"], e["new_value"]) for e in reopened["events"]] == [
        ("created", "open"), ("assignee", str(case.meena.user.id)), ("status", "in_progress"), ("status", "done"), ("status", "open")]
    assert case.lead.post(f"{url}/assign", json={"assignee_id": str(case.lead.user.id)}).json()["assignee"]["username"] == "inv.arun"
    assert case.meena.post(f"{url}/assign", json={"assignee_id": str(case.meena.user.id)}).status_code == 403
    assert [t["display_id"] for t in case.lead.get(f"/api/v1/cases/{case.id}/tasks", params={"status": "open"}).json()] == ["TASK-0001"]
    assert case.meena.get("/api/v1/tasks/mine").json() == []
    assert case.viewer.get(f"/api/v1/cases/{case.id}/tasks").status_code == 200  # a Viewer sees the board

    # An archived case's board is kept exactly as it was.
    for value in ("under_investigation", "investigation_completed"):
        set_status(case.lead, case.id, value)
    for value in ("closed", "archived"):
        set_status(case.supervisor, case.id, value)
    new_task(case.lead, case.id, status=403)
    assert case.lead.post(f"{url}/status", json={"status": "done"}).status_code == 403
    with pytest.raises(IntegrityError, match="permanent"):  # the history of a task never changes
        with db_session.begin_nested():
            db_session.execute(text("UPDATE task_events SET new_value = 'done'"))
    with pytest.raises(IntegrityError, match="only"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE investigation_tasks SET title = 'Renamed'"))


def test_comments_are_permanent_and_follow_what_they_are_about(cm_client, db_session, evidence_store):
    case = team(cm_client)
    note = add_note(case.lead, case.id, title="Initial assessment (fictional)")["file"]
    exhibit = upload(case.lead, case.id, PNG, "message.png")["evidence"]
    url = f"/api/v1/cases/{case.id}/comments"
    on_case = {"target_type": "case", "target_id": case.id}

    first = case.lead.post(url, json={**on_case, "body": "Check the timing (fictional)"})
    assert first.status_code == 201 and first.json()["target_id"] == case.id
    edited = case.lead.post(url, json={**on_case, "body": "Check the timing of the second transfer (fictional)",
                                       "replaces_comment_id": first.json()["id"]}).json()
    listed = case.lead.get(url, params=on_case).json()
    assert [(c["body"], c["current"]) for c in listed] == [("Check the timing (fictional)", False), (edited["body"], True)]
    assert case.lead.post(url, json={**on_case, "body": "again", "replaces_comment_id": first.json()["id"]}).status_code == 422
    assert case.meena.post(url, json={**on_case, "body": "mine now", "replaces_comment_id": edited["id"]}).status_code == 403

    assert case.viewer.post(url, json={**on_case, "body": "A viewer's remark"}).status_code == 403  # viewers read only
    assert len(case.viewer.get(url, params=on_case).json()) == 2
    assert case.lead.post(url, json={"target_type": "case", "target_id": str(uuid.uuid4()), "body": "x"}).status_code == 404
    on_note = {"target_type": "artifact", "target_id": note["id"]}
    assert case.meena.post(url, json={**on_note, "body": "Looks complete (fictional)"}).status_code == 201

    on_exhibit = {"target_type": "evidence", "target_id": exhibit["id"]}
    assert case.meena.post(url, json={**on_exhibit, "body": "The message was forwarded (fictional)"}).status_code == 201
    case.supervisor.post(f"/api/v1/evidence/{exhibit['id']}/seal", json={"reason": "Court order (fictional)"})
    assert case.meena.get(url, params=on_exhibit).status_code == 404  # a sealed exhibit's comments go with it
    assert len(case.supervisor.get(url, params=on_exhibit).json()) == 1

    task = new_task(case.lead, case.id, assignee_id=str(case.meena.user.id))
    case.lead.post(url, json={"target_type": "task", "target_id": task["id"], "body": "Priority: high (fictional)"})
    assert notices(case.meena)[0] == "comment.added"
    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE comments SET body = 'rewritten'"))


def test_notifications_are_private_and_can_be_marked_read(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    assert lead.get("/api/v1/notifications").json()["items"][0]["kind"] == "case.assigned"  # the lead is told about the case
    meena = cm_client("inv.meena")
    add_member(lead, created["case_id"], meena.user, "analyst")
    listing = meena.get("/api/v1/notifications").json()
    assert listing["unread"] == 1 and listing["items"][0]["kind"] == "team.added"
    payload = listing["items"][0]["payload"]
    assert payload["case"] == created["display_id"] and payload["role"] == "analyst" and payload["by"]
    notice = listing["items"][0]["id"]
    assert lead.post(f"/api/v1/notifications/{notice}/read").status_code == 404  # someone else's notice
    assert meena.post(f"/api/v1/notifications/{notice}/read").json()["read_at"]
    assert meena.get("/api/v1/notifications", params={"unread_only": True}).json()["items"] == []
    assert meena.post("/api/v1/notifications/read-all").json() == {"marked": 0}
    add_member(supervisor, created["case_id"], cm_client("view.kh", "viewer").user, "viewer")
    assert lead.get("/api/v1/notifications").json()["unread"] == 1  # still the first one: nothing was read
    assert lead.post("/api/v1/notifications/read-all").json() == {"marked": 1}
    assert lead.get("/api/v1/notifications").json()["unread"] == 0
