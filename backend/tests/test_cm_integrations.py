"""Case Management: integrations. Findings from outside systems (log events, alerts, CDR and IPDR results, OSINT,
indicators, external reports) added to cases with their provenance, under each source's access policy; identifiers
matched across the cases a reader can open; the fictional test source. All names, numbers and facts are fictional:
documentation IP ranges, .example domains and the test mobile network 001-01."""

import hashlib
import json
import uuid
from types import SimpleNamespace

import pytest
from cm_support import add_member, create_case, files, history, revise, withdraw
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.casemgmt.models import IntegrationImport, IntegrationIndicator, IntegrationSource, Organization
from app.core.config import get_settings
from app.db.models import AuditEvent

ADD = "/api/v1/integrations/add-to-case"
SOURCES = "/api/v1/integrations/sources"
RECORD_HASH = "sha256:" + hashlib.sha256(b"FICTIONAL CDR analysis record 01").hexdigest()
CDR_RESULT = {
    "item_type": "cdr_result",
    "source_record_id": "CDR-RES-2026-017-01",
    "source_hash": RECORD_HASH,
    "title": "Calls from the suspect number to the complainant (fictional)",
    "summary": "FICTIONAL. The suspect number called the complainant four times on 3 March 2026, 21 minutes in total.",
    "payload_ref": "fict-cdr://datasets/FICT-CYB-2026-017/analyses/01",
    "authority_ref": "Requisition FICT/CYB/2026/017 (fictional)",
    "observed_at": "2026-03-03T09:58:00+05:30",
    "observed_until": "2026-03-03T11:20:00+05:30",
    "identifiers": [{"type": "phone", "value": "070000 00042"}, {"type": "phone", "value": "+91 98450 12345"},
                    {"type": "imsi", "value": "001010000004242"}],
    "details": {"calls": 4, "total_duration_seconds": 1260},
}
CDR_SOURCE = {
    "code": "fict-cdr", "name": "CDR analysis (fictional)", "kind": "telecom",
    "legal_basis": "FICTIONAL: records obtained under requisitions to service providers.",
    "allowed_item_types": ["cdr_result", "ipdr_result", "indicator"],
}


def team(cm_client, supervisor=None, lead_name: str = "inv.arun", **case):
    supervisor = supervisor or cm_client("sup.kh", "supervisor")
    lead = cm_client(lead_name)
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id), **case)
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, case_id=created["case_id"])


def register(admin, status: int = 201, **overrides) -> dict:
    response = admin.post(SOURCES, json={**CDR_SOURCE, **overrides})
    assert response.status_code == status, response.text
    return response.json()


def add(client, key: str | None, case_id, finding: dict | None = None, *, status: int = 201, headers: dict | None = None, **fields) -> dict:
    body = {"case_id": str(case_id), **(finding or CDR_RESULT), **fields}
    sent = {**({"X-Integration-Key": key} if key else {}), **(headers or {})}
    response = client.post(ADD, json=body, headers=sent)
    assert response.status_code == status, response.text
    return response.json()


def imports_of(client, case_id) -> list[dict]:
    response = client.get(f"/api/v1/cases/{case_id}/imports")
    assert response.status_code == 200, response.text
    return response.json()["imports"]


def audit_rows(db_session, action: str) -> list[AuditEvent]:
    return list(db_session.scalars(select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)))


# ---------------------------------------------------------------- the acceptance: an immutable reference, a history entry, an audit event


def test_an_imported_finding_is_an_immutable_reference_with_a_history_entry_and_an_audit_event(cm_client, db_session):
    t = team(cm_client)
    admin = cm_client("admin.kh", "super_admin", "confidential")
    registered = register(admin)
    key = registered["key"]
    before = len(history(t.lead, t.case_id))

    added = add(t.lead, key, t.case_id)
    finding, entry = added["finding"], added["entry"]
    assert finding["display_id"] == "IMP-0001" and finding["status"] == "active" and finding["version_number"] == 1
    assert added["updated"] is False and entry == before + 2  # the first finding makes the "imports" folder, then it is added
    *_, folder_made, made = history(t.lead, t.case_id)
    assert folder_made["kind"] == "folder_added" and folder_made["details"] == {"folder": "imports", "system": True}
    assert (made["seq"], made["kind"]) == (entry, "import_added")
    assert made["details"] == {"display_id": "IMP-0001", "source": "fict-cdr", "item_type": "cdr_result", "record": "CDR-RES-2026-017-01",
                               "source_hash": RECORD_HASH, "updated": False, "content_sha256": finding["content_sha256"]}
    assert t.lead.get(f"/api/v1/cases/{t.case_id}/history/check").json()["intact"] is True
    # It is a file of the case, in a folder the system makes when the first finding arrives.
    [kept] = [f for f in files(t.lead, t.case_id, folder="imports")]
    assert kept["display_id"] == "IMP-0001"

    # Provenance: which system, which record, its hash, where the full record stays, under what authority, which key, for whom.
    assert finding["source"]["code"] == "fict-cdr" and finding["source_record_id"] == "CDR-RES-2026-017-01"
    assert finding["source_hash"] == RECORD_HASH and finding["payload_ref"].startswith("fict-cdr://")
    assert finding["authority_ref"] == "Requisition FICT/CYB/2026/017 (fictional)"
    assert finding["received_with"] == key[:12] and finding["imported_by"]["username"] == "inv.arun"
    assert finding["observed_at"] == "2026-03-03T09:58:00+05:30"
    assert [i["value"] for i in finding["identifiers"]] == ["+917000000042", "+919845012345", "001010000004242"]
    row = db_session.scalar(select(IntegrationImport).where(IntegrationImport.artifact_id == uuid.UUID(finding["artifact_id"])))
    assert row.source_hash == RECORD_HASH and row.key_prefix == key[:12]
    assert db_session.scalar(select(func.count()).select_from(IntegrationIndicator).where(IntegrationIndicator.import_id == row.id)) == 3

    # The audit event names the source and its key prefix, never the key, nor the identifiers.
    [event] = [e for e in audit_rows(db_session, "cm.integration.import") if e.outcome == "success"]
    assert event.details["source"] == "fict-cdr" and event.details["key"] == key[:12] and event.details["identifiers"] == 3
    assert key not in json.dumps(event.details) and "9845012345" not in json.dumps(event.details)

    # Never edited: not through a new version, not in the database. No DELETE anywhere.
    refused = revise(t.lead, finding["artifact_id"], "changed", 1, status=422)
    assert "kept exactly as received" in refused["detail"]
    for statement in (f"UPDATE integration_imports SET source_hash = 'x' WHERE id = '{row.id}'",
                      f"DELETE FROM integration_indicators WHERE import_id = '{row.id}'",
                      "UPDATE integration_sources SET allowed_item_types = '[]'::jsonb WHERE code = 'fict-cdr'",
                      "DELETE FROM integration_sources WHERE code = 'fict-cdr'"):
        with pytest.raises(DBAPIError, match="Case Management"), db_session.begin_nested():
            db_session.execute(text(statement))
    for path in (f"/api/v1/cases/{t.case_id}/imports/{finding['artifact_id']}", f"{SOURCES}/{registered['source']['id']}"):
        assert t.lead.delete(path).status_code == 405


def test_the_same_record_twice_is_refused_and_a_changed_record_becomes_a_new_version(cm_client):
    t = team(cm_client)
    key = register(cm_client("admin.kh", "super_admin", "confidential"))["key"]
    first = add(t.lead, key, t.case_id)["finding"]
    again = add(t.lead, key, t.case_id, status=409)
    assert "already holds this record" in again["detail"] and again["existing"]["display_id"] == "IMP-0001"

    changed = add(t.lead, key, t.case_id, source_hash="sha256:" + "ab" * 32, details={"calls": 5, "total_duration_seconds": 1300})
    assert changed["updated"] is True and changed["finding"]["display_id"] == "IMP-0001"
    assert changed["finding"]["version_number"] == 2 and changed["finding"]["versions"] == 2
    detail = t.lead.get(f"/api/v1/cases/{t.case_id}/imports/{first['artifact_id']}").json()
    assert [v["version_number"] for v in detail["history"]] == [1, 2] and detail["history"][1]["current"] is True
    assert "the record's hash changed" in detail["history"][1]["change_note"]
    assert detail["history"][0]["source_hash"] == RECORD_HASH
    assert detail["details"] == {"calls": 5, "total_duration_seconds": 1300}
    # Version 1 is still exactly as received: the file's versions keep both.
    versions = t.lead.get(f"/api/v1/artifacts/{first['artifact_id']}/versions").json()["versions"]
    by_number = {v["version_number"]: v for v in versions}
    assert by_number[1]["content"]["details"] == {"calls": 4, "total_duration_seconds": 1260}
    assert by_number[2]["content"]["details"] == {"calls": 5, "total_duration_seconds": 1300}

    # Withdrawn (it stays in the case), then the record is sent again: it becomes a new file, active.
    withdraw(t.lead, "artifacts", first["artifact_id"], reason="Sent to the wrong case (fictional)")
    assert imports_of(t.supervisor, t.case_id)[0]["status"] == "withdrawn"
    back = add(t.lead, key, t.case_id, source_hash="sha256:" + "ab" * 32, details={"calls": 5, "total_duration_seconds": 1300})
    assert back["finding"]["display_id"] == "IMP-0002" and back["finding"]["version_number"] == 1
    assert back["finding"]["status"] == "active" and back["updated"] is False
    assert sorted(i["display_id"] for i in imports_of(t.supervisor, t.case_id)) == ["IMP-0001", "IMP-0002"]


# ---------------------------------------------------------------- the source's access policy


def test_the_source_key_and_its_policy_are_enforced(cm_client, db_session):
    t = team(cm_client)
    admin = cm_client("admin.kh", "super_admin", "confidential")
    cdr = register(admin)
    entries = len(history(t.lead, t.case_id))

    assert "integration key" in add(t.lead, None, t.case_id, status=403)["detail"]
    assert "isn't valid" in add(t.lead, "khi_" + "x" * 48, t.case_id, status=403)["detail"]
    denied = [e for e in audit_rows(db_session, "cm.integration.import") if e.outcome == "denied"]
    assert len(denied) == 2 and all("khi_" not in json.dumps(e.details) for e in denied)

    assert "may add only" in add(t.lead, cdr["key"], t.case_id, {**CDR_RESULT, "item_type": "osint"}, status=403)["detail"]
    assert "needs authority_ref" in add(t.lead, cdr["key"], t.case_id, authority_ref=None, status=422)["detail"]
    assert "observed_at" in add(t.lead, cdr["key"], t.case_id, observed_at=None, observed_until=None, status=422)["detail"]
    assert "timezone" in add(t.lead, cdr["key"], t.case_id, observed_at="2026-03-03T09:58:00", status=422)["detail"]
    assert "source_hash" in add(t.lead, cdr["key"], t.case_id, source_hash="not-a-hash", status=422)["detail"]
    assert "check digit" in add(t.lead, cdr["key"], t.case_id, identifiers=[{"type": "imei", "value": "004400112233441"}],
                                status=422)["detail"]
    assert "64,000 bytes" in add(t.lead, cdr["key"], t.case_id, details={"rows": "x" * 70_000}, status=422)["detail"]

    secret = register(admin, code="fict-secret-cdr", min_case_classification="confidential")
    assert "classified confidential or higher" in add(t.lead, secret["key"], t.case_id, status=403)["detail"]

    source_id = cdr["source"]["id"]
    assert admin.post(f"{SOURCES}/{source_id}/status", json={"enabled": False, "reason": "Paused for a check (fictional)"}).status_code == 200
    assert "disabled" in add(t.lead, cdr["key"], t.case_id, status=403)["detail"]
    assert admin.post(f"{SOURCES}/{source_id}/status", json={"enabled": True, "reason": "Check done (fictional)"}).status_code == 200
    rotated = admin.post(f"{SOURCES}/{source_id}/key", json={"reason": "Key shared by mistake (fictional)"}).json()
    assert rotated["key"] != cdr["key"] and rotated["source"]["key_prefix"] == rotated["key"][:12]
    assert "isn't valid" in add(t.lead, cdr["key"], t.case_id, status=403)["detail"]
    assert len(history(t.lead, t.case_id)) == entries  # nothing refused left anything behind
    add(t.lead, rotated["key"], t.case_id)

    # A source of another organisation can't add to this one's cases, whatever its key.
    other_org = Organization(code="ZZ", name="Other police organisation (fictional)")
    db_session.add(other_org)
    db_session.commit()
    foreign = register(cm_client("admin.zz", "super_admin", "confidential", organization=other_org), code="zz-cdr")
    assert "another organisation" in add(t.lead, foreign["key"], t.case_id, source_record_id="CDR-RES-2", status=403)["detail"]


def test_only_people_who_may_add_to_the_case_can_add_findings(cm_client):
    t = team(cm_client)
    key = register(cm_client("admin.kh", "super_admin", "confidential"))["key"]
    outsider = cm_client("inv.outsider")
    assert add(outsider, key, t.case_id, status=404)["detail"] == "Not found"
    viewer = cm_client("viewer.kh", "viewer")
    add_member(t.lead, t.case_id, viewer.user, "viewer")
    assert "read this case but not add" in add(viewer, key, t.case_id, status=403)["detail"]
    # A Sub Investigator and an Analyst on the team add directly: there is no branch and no approval step.
    helper = cm_client("inv.meera")
    add_member(t.lead, t.case_id, helper.user)
    added = add(helper, key, t.case_id)
    assert added["finding"]["imported_by"]["username"] == "inv.meera"
    assert history(t.lead, t.case_id)[-1]["actor"]["username"] == "inv.meera"
    analyst = cm_client("analyst.kh", "analyst")
    add_member(t.lead, t.case_id, analyst.user, "analyst")
    add(analyst, key, t.case_id, source_record_id="CDR-RES-2026-017-02")
    # The lead is told, without any content of the finding.
    notices = t.lead.get("/api/v1/notifications").json()["items"]
    found = [n for n in notices if n["kind"] == "import.added"]
    assert sorted(n["payload"]["artifact"]["display_id"] for n in found) == ["IMP-0001", "IMP-0002"]
    assert all(n["payload"]["source"] == "CDR analysis (fictional)" and "summary" not in n["payload"] for n in found)


# ---------------------------------------------------------------- identifiers across cases


def test_identifiers_are_matched_across_cases_only_where_the_reader_may_look(cm_client, db_session):
    supervisor = cm_client("sup.kh", "supervisor")
    a = team(cm_client, supervisor, "inv.arun")
    b = team(cm_client, supervisor, "inv.bina", title="Second online fraud investigation (FICTIONAL TEST CASE)")
    key = register(cm_client("admin.kh", "super_admin", "confidential"))["key"]
    add(a.lead, key, a.case_id)
    in_b = add(b.lead, key, b.case_id, {**CDR_RESULT, "source_record_id": "CDR-RES-2026-099-01",
                                       "identifiers": [{"type": "phone", "value": "+917000000042"}]})["finding"]

    def matches(client, case_id):
        view = client.get(f"/api/v1/cases/{case_id}/indicators").json()
        return {(i["type"], i["value"]): i["other_cases"] for i in view["indicators"]}

    # The lead of A can't open B: the match isn't shown, not even as a count.
    assert matches(a.lead, a.case_id)[("phone", "+917000000042")] == []
    # The supervisor of both cases sees it.
    seen = matches(supervisor, a.case_id)[("phone", "+917000000042")]
    assert [c["case"]["display_id"] for c in seen] == [b.created["display_id"]] and seen[0]["linked"] is False
    assert seen[0]["imports"][0]["display_id"] == "IMP-0001"
    # Once on case B too, the lead of A sees it, and links the cases.
    add_member(b.lead, b.case_id, a.lead.user, "viewer")
    assert len(matches(a.lead, a.case_id)[("phone", "+917000000042")]) == 1
    linked = a.lead.post(f"/api/v1/cases/{a.case_id}/links", json={
        "target_case_id": b.case_id, "link_type": "shared_evidence",
        "reason": "The same suspect phone number in both cases (fictional)."})
    assert linked.status_code == 201, linked.text
    assert matches(supervisor, a.case_id)[("phone", "+917000000042")][0]["linked"] is True
    # Sealed in case B: only its supervisor still sees the match.
    assert supervisor.post(f"/api/v1/artifacts/{in_b['artifact_id']}/seal", json={"reason": "Sensitive source (fictional)"}).status_code == 200
    assert matches(a.lead, a.case_id)[("phone", "+917000000042")] == []
    assert len(matches(supervisor, a.case_id)[("phone", "+917000000042")]) == 1

    detail = supervisor.get(f"/api/v1/cases/{a.case_id}/imports/{imports_of(a.lead, a.case_id)[0]['artifact_id']}").json()
    phone = next(i for i in detail["identifiers"] if i["value"] == "+917000000042")
    assert phone["as_received"] == "070000 00042" and phone["other_cases"][0]["linked"] is True


# ---------------------------------------------------------------- part of the case record


def test_imported_findings_join_the_case_record(cm_client):
    t = team(cm_client)
    key = register(cm_client("admin.kh", "super_admin", "confidential"))["key"]
    add(t.lead, key, t.case_id)
    # Case Intelligence reads it like a note: found by search, dated in the timeline.
    found = t.lead.post(f"/api/v1/cases/{t.case_id}/intelligence/search", json={"query": "suspect number called", "mode": "keyword"}).json()
    assert [r["source"]["display_id"] for r in found["results"]] == ["IMP-0001"]
    rebuilt = t.lead.post(f"/api/v1/cases/{t.case_id}/intelligence/timeline", json={})
    assert rebuilt.status_code == 201, rebuilt.text
    events = t.lead.get(f"/api/v1/cases/{t.case_id}/intelligence/timeline").json()["timeline"]["events"]
    assert any(e["kind"] == "imported_finding" and e["date"] == "2026-03-03" for e in events)
    # The report lists it with its provenance.
    report = t.lead.get(f"/api/v1/cases/{t.case_id}/report-preview").json()
    [listed] = report["imports"]
    assert listed["display_id"] == "IMP-0001" and listed["source"] == "CDR analysis (fictional)"
    assert listed["source_hash"] == RECORD_HASH and listed["version_number"] == 1 and listed["status"] == "active"


# ---------------------------------------------------------------- sources, the contract, the test source


def test_administrators_manage_sources_and_a_key_is_shown_only_once(cm_client, db_session):
    investigator = cm_client("inv.arun")
    assert investigator.get(SOURCES).status_code == 403
    assert investigator.post(SOURCES, json=CDR_SOURCE).status_code == 403
    admin = cm_client("admin.kh", "super_admin", "confidential")
    registered = register(admin)
    key = registered["key"]
    assert key.startswith("khi_") and registered["source"]["key_prefix"] == key[:12]
    stored = db_session.scalar(select(IntegrationSource).where(IntegrationSource.code == "fict-cdr"))
    assert stored.key_hash == hashlib.sha256(key.encode()).hexdigest()  # only the hash is kept
    assert stored.authority_required_for == ["cdr_result", "ipdr_result"]  # the default for telecom data
    listed = admin.get(SOURCES).json()
    assert key not in json.dumps(listed) and listed[0]["policy"]["min_case_classification"] == "internal"

    assert "already registered" in register(admin, status=422)["detail"]
    assert "Unknown kind" in register(admin, code="fict-x", kind="satellite", status=422)["detail"]
    assert "can only be required" in register(admin, code="fict-y", authority_required_for=["osint"], status=422)["detail"]
    assert "legal basis" in register(admin, code="fict-z", legal_basis="none", status=422)["detail"]

    source_id = registered["source"]["id"]
    admin.post(f"{SOURCES}/{source_id}/status", json={"enabled": False, "reason": "Paused (fictional)"})
    admin.post(f"{SOURCES}/{source_id}/key", json={"reason": "Routine rotation (fictional)"})
    [source] = [s for s in admin.get(SOURCES).json() if s["id"] == source_id]
    assert [h["event_type"] for h in source["history"]] == ["registered", "disabled", "key_rotated"]
    assert source["history"][1]["reason"] == "Paused (fictional)" and source["status"] == "disabled"


def test_the_contract_describes_itself(cm_client):
    described = cm_client("inv.arun").get("/api/v1/integrations/contract").json()
    assert described["version"] == "2.0"
    assert [t["code"] for t in described["item_types"]] == ["log_event", "alert", "cdr_result", "ipdr_result", "osint", "indicator", "report"]
    assert {t["code"] for t in described["identifier_types"]} == {"ip", "domain", "url", "email", "phone", "imei", "imsi", "account",
                                                                 "file_hash"}


def test_the_fictional_test_source(cm_client, monkeypatch):
    t = team(cm_client)
    view = t.lead.get("/api/v1/integrations/test-source").json()
    assert view["registered"] is False and len(view["findings"]) == 8
    assert all(f["summary"].startswith("FICTIONAL") for f in view["findings"])
    send = {"case_id": t.case_id, "finding_id": "cdr-calls-to-complainant"}
    assert "isn't registered" in t.lead.post("/api/v1/integrations/test-source/send", json=send).json()["detail"]

    admin = cm_client("admin.kh", "super_admin", "confidential")
    assert admin.post(f"{SOURCES}/test-source").status_code == 201
    sent = t.lead.post("/api/v1/integrations/test-source/send", json=send)
    assert sent.status_code == 201, sent.text
    finding = sent.json()["finding"]
    assert finding["fictional"] is True and finding["received_with"] is None and finding["source"]["code"] == "fict-test-source"
    assert {i["type"] for i in finding["identifiers"]} == {"phone", "imei", "imsi"}

    # The source changes its record (an alert raised to critical): a new version, the first kept.
    for finding_id, version in (("alert-rapid-transfers", 1), ("alert-rapid-transfers-update", 2)):
        result = t.lead.post("/api/v1/integrations/test-source/send", json={**send, "finding_id": finding_id}).json()
        assert result["finding"]["version_number"] == version

    monkeypatch.setattr(get_settings(), "cm_test_source", False)
    assert t.lead.get("/api/v1/integrations/test-source").status_code == 404


def test_add_to_case_can_be_repeated_safely_with_an_idempotency_key(cm_client):
    t = team(cm_client)
    key = register(cm_client("admin.kh", "super_admin", "confidential"))["key"]
    body = {"case_id": t.case_id, **CDR_RESULT}
    headers = {"X-Integration-Key": key, "Idempotency-Key": "fict-cdr-01-attempt"}
    first = t.lead.post(ADD, json=body, headers=headers)
    repeat = t.lead.post(ADD, json=body, headers=headers)
    assert first.status_code == repeat.status_code == 201 and repeat.headers["Idempotent-Replay"] == "true"
    assert repeat.json()["entry"] == first.json()["entry"] and len(imports_of(t.lead, t.case_id)) == 1
