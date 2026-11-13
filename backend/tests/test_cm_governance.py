"""Case Management: legal holds, retention as a two-person decision (nothing is ever deleted), two-step
verification (TOTP) for privileged actions, and the runtime database role without DELETE. All data is fictional."""

import datetime as dt
import time
import uuid
from types import SimpleNamespace

import pyotp
import pytest
from cm_support import PNG, add_member, add_note, case, create_case, history, notices, upload, withdraw
from conftest import TEST_PASSWORD
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.casemgmt.models import APPEND_ONLY_TABLES, NO_DELETE_TABLES, CaseFamily, CaseStatusEvent, RetentionDecision
from app.core.config import get_settings


def team(cm_client, **case):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id), **case)
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, case_id=created["case_id"])


def set_status(client, case_id, value: str, status: int = 200) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/status", json={"field": "workflow", "value": value, "reason": f"Fictional: {value}"})
    assert response.status_code == status, response.text
    return response.json()


def close(t) -> None:
    set_status(t.supervisor, t.case_id, "open")
    set_status(t.supervisor, t.case_id, "closed")


def propose(client, case_id, status: int = 201, **body) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/retention-decisions", json={"reason": "Fictional: the case was closed long ago.", **body})
    assert response.status_code == status, response.text
    return response.json()


def decide(client, decision_id, approve: bool = True, status: int = 200) -> dict:
    response = client.post(f"/api/v1/retention-decisions/{decision_id}/decide", json={"approve": approve, "note": "Fictional: checked."})
    assert response.status_code == status, response.text
    return response.json()


# ---------------------------------------------------------------- legal holds and retention


def test_a_legal_hold_blocks_archiving_and_disposal_decisions_until_released(cm_client):
    t = team(cm_client)
    close(t)
    hold = t.supervisor.post(f"/api/v1/cases/{t.case_id}/legal-holds",
                             json={"reason": "Fictional: preservation order pending appeal.", "authority_ref": "Order FICT/2026/7"})
    assert hold.status_code == 201, hold.text
    assert t.lead.post(f"/api/v1/cases/{t.case_id}/legal-holds", json={"reason": "Fictional: the lead tries."}).status_code == 403
    assert cm_client("inv.outsider").get(f"/api/v1/cases/{t.case_id}/governance").status_code == 404

    assert "legal hold" in set_status(t.supervisor, t.case_id, "archived", status=403)["detail"]
    assert "legal hold" in propose(t.supervisor, t.case_id, action="archive", status=403)["detail"]
    retained = propose(t.supervisor, t.case_id, action="retain", review_on=str(dt.date.today() + dt.timedelta(days=365)))
    assert retained["status"] == "proposed"  # keeping a case is always possible
    governance = t.supervisor.get(f"/api/v1/cases/{t.case_id}/governance").json()
    assert governance["on_hold"] is True and governance["holds"][0]["authority_ref"] == "Order FICT/2026/7"

    released = t.supervisor.post(f"/api/v1/legal-holds/{hold.json()['id']}/release", json={"reason": "Fictional: the appeal was decided."})
    assert released.status_code == 200 and released.json()["active"] is False
    set_status(t.supervisor, t.case_id, "archived")  # allowed again
    assert t.supervisor.get(f"/api/v1/cases/{t.case_id}/governance").json()["holds"][0]["release_reason"] == "Fictional: the appeal was decided."


def test_a_legal_hold_is_told_to_the_investigator_leading_the_case_now_and_not_to_the_one_who_handed_it_over(cm_client):
    t = team(cm_client)
    new_lead = cm_client("inv.new")
    helper = cm_client("sub.helper", "sub_investigator")
    add_member(t.lead, t.case_id, helper.user)
    handed = t.supervisor.post(f"/api/v1/cases/{t.case_id}/lead", json={"user_id": str(new_lead.user.id), "reason": "Handed to another investigator (fictional)"})
    assert handed.status_code == 200, handed.text
    hold = t.supervisor.post(f"/api/v1/cases/{t.case_id}/legal-holds", json={"reason": "Fictional: preservation order pending appeal."})
    assert hold.status_code == 201, hold.text
    assert t.supervisor.post(f"/api/v1/legal-holds/{hold.json()['id']}/release", json={"reason": "Fictional: the appeal was decided."}).status_code == 200
    # The case's lead now is told, both times. The one who handed it over (now a Sub Investigator) and the rest of the team are not.
    assert [k for k in notices(new_lead) if k.startswith("legal_hold")] == ["legal_hold.released", "legal_hold.placed"]
    for not_told in (t.lead, helper):
        assert not [k for k in notices(not_told) if k.startswith("legal_hold")]


def test_retention_is_decided_by_a_second_person_and_never_deletes_anything(cm_client, db_session):
    t = team(cm_client)
    admin = cm_client("admin.kh", "super_admin", "confidential")
    close(t)
    assert "future" in propose(t.supervisor, t.case_id, action="retain", status=422)["detail"]
    assert "transferred" in propose(t.supervisor, t.case_id, action="transfer", status=422)["detail"]
    proposed = propose(t.supervisor, t.case_id, action="archive")
    assert "already has a retention decision" in propose(t.supervisor, t.case_id, action="dispose", status=422)["detail"]
    assert "second person" in decide(t.supervisor, proposed["id"], status=403)["detail"]
    assert db_session.get(RetentionDecision, uuid.UUID(proposed["id"])).decided_by is None
    approved = decide(admin, proposed["id"])
    assert approved["status"] == "approved" and approved["decided_by"]["username"] == "admin.kh"
    family = db_session.get(CaseFamily, uuid.UUID(t.case_id))
    db_session.refresh(family)
    assert family.workflow_status == "archived"
    assert case(t.lead, t.case_id)["workflow_status"] == "archived"
    add_note(t.lead, t.case_id, status=403)  # read-only, still there

    # Disposal: a recorded decision only. The case and its history stay.
    dispose = propose(admin, t.case_id, action="dispose")
    done = decide(t.supervisor, dispose["id"])
    assert done["status"] == "approved" and done["outside_action"] is True
    assert [e["kind"] for e in history(t.lead, t.case_id)][-1] == "status_changed"  # the whole history is still there
    assert t.lead.get(f"/api/v1/cases/{t.case_id}/history/check").json()["intact"] is True
    with pytest.raises(DBAPIError, match="two_people"), db_session.begin_nested():
        db_session.execute(text(f"UPDATE retention_decisions SET decided_by = proposed_by WHERE id = '{dispose['id']}'"))


def test_retention_policies_show_the_cases_due_for_review(cm_client, db_session):
    admin = cm_client("admin.kh", "super_admin", "confidential")
    t = team(cm_client)
    policy = admin.post("/api/v1/admin/retention/policies", json={
        "code": "closed-cyber-1y", "name": "Closed cyber cases: review after a year (fictional)", "review_after_years": 1,
        "legal_basis": "Fictional schedule FICT-RS-12, item 4", "case_types": ["cyber_fraud"]})
    assert policy.status_code == 201, policy.text
    assert cm_client("inv.someone").post("/api/v1/admin/retention/policies", json={
        "code": "x-1", "name": "x", "review_after_years": 1, "legal_basis": "Fictional schedule"}).status_code == 403
    # The case was closed two years ago (set directly: a test can't wait two years).
    db_session.execute(text(f"UPDATE case_families SET workflow_status = 'closed' WHERE id = '{t.case_id}'"))
    db_session.add(CaseStatusEvent(case_family_id=uuid.UUID(t.case_id), field="workflow", old_value="open", new_value="closed",
                                   actor_id=t.supervisor.user.id, reason="Fictional: closed",
                                   at=dt.datetime.now(dt.UTC) - dt.timedelta(days=730)))
    db_session.commit()
    overview = admin.get("/api/v1/admin/retention").json()
    assert [d["case"]["id"] for d in overview["due"]] == [t.case_id] and overview["due"][0]["policy"]["name"].startswith("Closed cyber")
    decision = propose(t.supervisor, t.case_id, action="retain", review_on=str(dt.date.today() + dt.timedelta(days=400)))
    assert admin.get("/api/v1/admin/retention").json()["due"] == []  # a decision is waiting
    assert [w["id"] for w in admin.get("/api/v1/admin/retention").json()["waiting"]] == [decision["id"]]
    decide(admin, decision["id"])
    assert admin.get("/api/v1/admin/retention").json()["due"] == []  # retained until the next review
    retired = admin.post(f"/api/v1/admin/retention/policies/{policy.json()['id']}/retire")
    assert retired.status_code == 200 and retired.json()["status"] == "retired"


# ---------------------------------------------------------------- two-step verification


def login(anonymous_api, username: str) -> dict:
    response = anonymous_api.post("/api/auth/token", data={"username": username, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def next_code(secret: str) -> str:
    """The code of the next 30-second step: accepted (one step of drift), and not used yet."""
    return pyotp.TOTP(secret).at(int(time.time()) + 30)


def test_two_step_verification_and_privileged_actions(cm_client, anonymous_api, monkeypatch):
    t = team(cm_client)
    sup = t.supervisor
    setup = sup.post("/api/auth/mfa/setup")
    assert setup.status_code == 200 and setup.json()["qr_svg"].startswith("data:image/svg+xml")
    secret = setup.json()["secret"]
    assert sup.post("/api/auth/mfa/confirm", json={"code": "000000"}).status_code == 422
    assert sup.post("/api/auth/mfa/confirm", json={"code": pyotp.TOTP(secret).now()}).json()["enabled"] is True

    first = login(anonymous_api, "sup.kh")
    assert first["mfa_required"] is True and first["access_token"] == "" and first["mfa_ticket"]
    assert anonymous_api.post("/api/auth/mfa/login", json={"ticket": first["mfa_ticket"], "code": "123456"}).status_code == 401
    code = next_code(secret)
    strong = anonymous_api.post("/api/auth/mfa/login", json={"ticket": first["mfa_ticket"], "code": code})
    assert strong.status_code == 200, strong.text
    assert anonymous_api.post("/api/auth/mfa/login", json={"ticket": first["mfa_ticket"], "code": code}).status_code == 401  # once
    headers = {"Authorization": f"Bearer {strong.json()['access_token']}"}
    assert anonymous_api.get("/api/auth/me", headers=headers).json()["mfa_verified"] is True

    # When the organisation requires it, privileged actions need a login with a code.
    monkeypatch.setattr(get_settings(), "cm_mfa_required", True)
    refused = sup.post(f"/api/v1/cases/{t.case_id}/legal-holds", json={"reason": "Fictional: preservation order."})
    assert refused.status_code == 403 and "Two-step verification is required" in refused.json()["detail"]
    allowed = anonymous_api.post(f"/api/v1/cases/{t.case_id}/legal-holds", json={"reason": "Fictional: preservation order."}, headers=headers)
    assert allowed.status_code == 201, allowed.text
    # Ordinary work isn't affected: the lead adds a note without a code.
    add_note(t.lead, t.case_id, title="Fictional note after the hold.")
    assert sup.get("/api/auth/mfa").json()["required"] is True


# ---------------------------------------------------------------- the runtime database role


DELETABLE = {"document_pages", "document_chunks", "document_provisions", "case_events", "case_entities", "uploads", "upload_chunks",
             "case_access_grants", "audit_events", "user_mfa"}


def test_the_runtime_role_can_not_delete_case_records_nor_edit_permanent_ones(db_session):
    def can(table: str, privilege: str) -> bool:
        return db_session.scalar(text("SELECT has_table_privilege('cm_runtime', :t, :p)"), {"t": table, "p": privilege})

    for table in APPEND_ONLY_TABLES:
        assert can(table, "INSERT") and not can(table, "UPDATE") and not can(table, "DELETE"), table
    for table in NO_DELETE_TABLES:
        assert can(table, "UPDATE") and not can(table, "DELETE"), table
    for table in DELETABLE:
        assert can(table, "DELETE"), table


def test_the_whole_module_works_under_the_runtime_role(cm_client, db_session, evidence_store):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    helper = cm_client("inv.meera")
    db_session.execute(text("SET LOCAL ROLE cm_runtime"))  # from here on, the application's rights only
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    exhibit = upload(lead, case_id, PNG)
    note = add_note(lead, case_id, title="Fictional note one.")["file"]
    add_member(lead, case_id, helper.user)
    add_note(helper, case_id, title="Fictional note two.")
    withdraw(lead, "artifacts", note["id"], reason="Entered by mistake (fictional)")
    withdraw(lead, "evidence", exhibit["evidence"]["id"], reason="Uploaded by mistake (fictional)")
    report = lead.post(f"/api/v1/cases/{case_id}/reports", json={"purpose": "Fictional: checking the runtime role."})
    assert report.status_code == 201, report.text
    assert lead.get(f"/api/v1/cases/{case_id}/history/check").json()["intact"] is True
    with pytest.raises(DBAPIError, match="permission denied"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM case_families"))
    with pytest.raises(DBAPIError, match="permission denied"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM case_members"))
    with pytest.raises(DBAPIError, match="permission denied"), db_session.begin_nested():
        db_session.execute(text("UPDATE case_entries SET summary = 'edited'"))
    with pytest.raises(DBAPIError, match="permission denied"), db_session.begin_nested():
        db_session.execute(text("UPDATE artifact_versions SET change_note = 'edited'"))
