"""Case Management CM-1: creating cases, case types, statuses and official references (fictional data)."""

import re

from cm_support import CASE, case, create_case, files, history
from sqlalchemy import func, select

from app.casemgmt.models import CaseFamily
from app.db.models import AuditEvent


def test_a_new_case_gets_its_folders_a_lead_a_summary_and_a_first_history_entry(cm_client, db_session):
    supervisor = cm_client("sup.one", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(
        supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id),
        official_reference={"ref_type": "FIR", "number": "0123/2026", "issuing_authority": "Example Nagar PS (fictional)"},
    )
    assert re.fullmatch(r"KH-\d{4}-0001", created["display_id"])
    assert created["lead"]["username"] == "inv.arun" and "case-information" in created["folders"]

    # The lead investigator is on the team at once, and sees the case in "my cases".
    mine = lead.get("/api/v1/cases/mine").json()
    assert [(c["case"]["display_id"], c["role"]) for c in mine] == [(created["display_id"], "lead")]
    summary = [f for f in files(lead, created["case_id"], folder="case-information") if f["type"] == "case_summary"][0]
    shown = lead.get(f"/api/v1/artifacts/{summary['id']}/versions").json()
    assert shown["versions"][0]["content"]["title"] == CASE["title"] and shown["display_id"] == "SUM-0001"

    detail = supervisor.get(f"/api/v1/cases/{created['case_id']}").json()
    assert detail["official_references"] == ["FIR 0123/2026, Example Nagar PS (fictional)"]
    assert detail["my_role"] is None and detail["can"]["hand_over"] is True  # the supervisor oversees without being on the team
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "cm.case.created"))
    assert event.target_id == created["display_id"] and event.outcome == "success"


def test_case_numbers_follow_on_and_an_investigator_leads_their_own_case(cm_client):
    investigator = cm_client("inv.one")
    first, second = create_case(investigator), create_case(investigator)
    assert int(second["display_id"][-4:]) == int(first["display_id"][-4:]) + 1
    assert case(investigator, first["case_id"])["my_role"] == "lead"
    assert investigator.get("/api/v1/cases").json()["total"] == 2


def test_viewers_and_analysts_cannot_create_cases(cm_client, db_session):
    for role in ("viewer", "analyst"):
        response = cm_client(f"{role}.one", role).post("/api/v1/cases", json=CASE)
        assert response.status_code == 403, role
    assert db_session.scalar(select(func.count()).select_from(CaseFamily)) == 0
    outcomes = db_session.scalars(select(AuditEvent.outcome).where(AuditEvent.action == "cm.case.created")).all()
    assert outcomes == ["denied", "denied"]


def test_every_case_type_is_accepted(cm_client):
    client = cm_client("inv.types")
    types = client.get("/api/v1/case-types").json()
    assert {"cyber_fraud", "murder", "missing_person", "narcotics", "civil_dispute", "other"} <= {t["code"] for t in types}
    # A type that isn't in the list is accepted too, with the general folder template.
    created = create_case(client, case_type="wildlife_trafficking")
    detail = case(client, created["case_id"])
    assert detail["case_type"] == "wildlife_trafficking"
    assert "case-information" in created["folders"] and len(created["folders"]) > 3  # the general folders


def test_the_lead_and_supervisor_must_be_suitable(cm_client):
    supervisor = cm_client("sup.two", "supervisor")
    viewer = cm_client("viewer.two", "viewer")
    low = cm_client("inv.low", "investigator", clearance="internal")
    assert supervisor.post("/api/v1/cases", json={**CASE, "lead_investigator_id": str(viewer.user.id)}).status_code == 422
    response = supervisor.post("/api/v1/cases", json={**CASE, "lead_investigator_id": str(low.user.id)})
    assert response.status_code == 422 and "clearance" in response.json()["detail"]
    assert supervisor.post("/api/v1/cases", json={**CASE, "supervisor_id": str(viewer.user.id)}).status_code == 422
    assert supervisor.post("/api/v1/cases", json={**CASE, "priority": "urgent"}).status_code == 422
    assert supervisor.post("/api/v1/cases", json={**CASE, "unexpected": 1}).status_code == 422


def test_the_workflow_status_follows_allowed_transitions(cm_client):
    supervisor = cm_client("sup.flow", "supervisor")
    lead = cm_client("inv.flow")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    url = f"/api/v1/cases/{created['case_id']}/status"

    def change(client, value, field="workflow"):
        return client.post(url, json={"field": field, "value": value, "reason": "Fictional test transition"})

    assert change(lead, "under_investigation").status_code == 200
    assert change(lead, "registered").status_code == 422  # not an allowed transition
    assert change(lead, "investigation_completed").status_code == 200
    assert change(lead, "closed").status_code == 403  # the supervisor's decision
    closed = change(supervisor, "closed")
    assert closed.status_code == 200 and closed.json()["workflow_status"] == "closed"
    assert change(lead, "Chargesheet filed", field="official").status_code == 403
    assert change(supervisor, "Chargesheet filed", field="official").json()["official_status"] == "Chargesheet filed"

    statuses = [(e["field"], e["old_value"], e["new_value"]) for e in closed.json()["status_history"]]
    assert statuses == [("workflow", None, "registered"), ("workflow", "registered", "under_investigation"),
                       ("workflow", "under_investigation", "investigation_completed"),
                       ("workflow", "investigation_completed", "closed")]
    # Closing the case closes or changes nothing in it: the files and the history are as they were, and the history is recorded.
    assert [f["display_id"] for f in files(supervisor, created["case_id"], folder="case-information")] == ["SUM-0001"]
    kinds = [e["kind"] for e in history(supervisor, created["case_id"])]
    assert kinds == ["case_registered", "status_changed", "status_changed", "status_changed", "status_changed"]  # three workflow steps, one official


def test_official_references_are_added_never_edited(cm_client):
    supervisor = cm_client("sup.ref", "supervisor")
    lead = cm_client("inv.ref")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    url = f"/api/v1/cases/{created['case_id']}/official-references"
    reference = {"ref_type": "FIR", "number": "0456/2026", "issuing_authority": "Example PS (fictional)", "ref_date": "2026-11-01"}
    assert supervisor.post(url, json=reference).status_code == 201
    assert supervisor.post(url, json=reference).status_code == 409  # already recorded
    assert lead.post(url, json={**reference, "number": "0457/2026"}).status_code == 403
    detail = lead.get(f"/api/v1/cases/{created['case_id']}").json()
    assert [r["number"] for r in detail["references"]] == ["0456/2026"]
    assert (detail["can"]["change_workflow_status"], detail["can"]["change_official_status"], detail["can"]["add_official_reference"]) == (True, False, False)
