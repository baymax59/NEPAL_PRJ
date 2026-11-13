"""Case Management:  signed PDF reports (a changed report fails verification), the hash-chained audit trail
(an edited audit row breaks the chain) with signed checkpoints, and the worker's scheduled jobs. All data is fictional."""

import hashlib
import os
import re
from contextlib import nullcontext
from types import SimpleNamespace

import pypdfium2 as pdfium
import pytest
from cm_support import PNG, add_member, add_note, create_case, files, history, revise, upload
from sqlalchemy import func, select, text

from app.casemgmt.governance import audit_chain, jobs
from app.casemgmt.models import AuditCheckpoint, JobRun, Notification, ReportExport, ReportVerification
from app.core.config import get_settings
from app.db.models import AuditEvent

PURPOSE = "Fictional: progress report for the supervisor's review."


def team(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, case_id=created["case_id"], case=created["display_id"])


def generate(client, case_id, status: int = 201, **fields) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/reports", json={"purpose": PURPOSE, **fields})
    assert response.status_code == status, response.text
    return response.json()


def download(client, export_id) -> bytes:
    link = client.post(f"/api/v1/reports/{export_id}/download-link")
    assert link.status_code == 200, link.text
    response = client.get(link.json()["url"])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf" and "attachment" in response.headers["content-disposition"]
    return response.content


def pdf_text(data: bytes) -> str:
    document = pdfium.PdfDocument(data)
    return "\n".join(document[i].get_textpage().get_text_range() for i in range(len(document)))


def verify_file(client, data: bytes) -> dict:
    response = client.post("/api/v1/reports/verify-file", files={"file": ("copy.pdf", data, "application/pdf")})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- reports


def test_a_report_is_a_signed_pdf_kept_with_its_hash_and_a_changed_report_fails_verification(cm_client, db_session, evidence_store):
    t = team(cm_client)
    exhibit = upload(t.lead, t.case_id, PNG)["evidence"]
    note_id = add_note(t.lead, t.case_id, title="First steps (fictional)",
                       text="Fictional: the complainant was interviewed on 4 March 2026.")["file"]["display_id"]
    assert t.lead.post(f"/api/v1/evidence/{exhibit['id']}/verify").json()["result"] == "match"
    before = len(history(t.lead, t.case_id))
    made = generate(t.lead, t.case_id)
    report, entry = made["report"], made["entry"]
    assert (report["display_id"], report["version_number"], report["report_type"]) == ("RPT-0001", 1, "case_report")
    assert entry == before + 1 and report["as_of_entry"] == before and report["page_count"] >= 1
    made_in = history(t.lead, t.case_id)[-1]  # the history says which entry the report describes, and vouches for the file
    assert made_in["kind"] == "report_generated" and made_in["seq"] == entry
    assert made_in["details"]["sha256"] == report["sha256"] and made_in["details"]["as_of_entry"] == before
    assert t.lead.get(f"/api/v1/cases/{t.case_id}/history/check").json()["intact"] is True

    data = download(t.lead, report["id"])
    assert hashlib.sha256(data).hexdigest() == report["sha256"]  # exactly the file generated
    words = pdf_text(data)
    for expected in (t.case, "RPT-0001 version 1", "Fictional: progress report", "not automatically admissible",
                     note_id, f"as of entry {before}", "Original"):
        assert expected in words, expected
    # No fingerprints or codes anywhere in the report: people read "Original" and "entry 12", never a hash.
    assert exhibit["sha256"][:32] not in words and "SHA-256" not in words
    assert re.search(r"[0-9a-f]{16,}", words.lower()) is None, "a long code was printed in the report"

    # A copy someone holds is checked byte for byte; one changed byte and it is no longer recognised.
    genuine = verify_file(t.supervisor, data)
    assert genuine["result"] == "match" and genuine["report"]["display_id"] == "RPT-0001" and genuine["recorded_sha256"] == report["sha256"]
    changed = bytearray(data)
    changed[len(changed) // 2] ^= 0x01
    assert verify_file(t.lead, bytes(changed))["result"] == "unknown"

    # The stored copy is checked too: intact, then changed behind the application's back (a changed report fails verification).
    assert t.lead.post(f"/api/v1/reports/{report['id']}/verify").json()["result"] == "match"
    stored = evidence_store.local_path(db_session.get(ReportExport, report["id"]).storage_key)
    os.chmod(stored, 0o644)
    stored.write_bytes(bytes(changed))
    failed = t.lead.post(f"/api/v1/reports/{report['id']}/verify").json()
    assert failed["result"] == "mismatch" and "was changed" in failed["message"]
    link = t.lead.post(f"/api/v1/reports/{report['id']}/download-link").json()
    refused = t.lead.get(link["url"])
    assert refused.status_code == 409 and "no longer matches" in refused.json()["detail"]
    results = list(db_session.scalars(select(ReportVerification.result).where(ReportVerification.report_export_id == report["id"])
                                      .order_by(ReportVerification.id)))
    # Every check is kept: the download's own check, the submitted copy, the stored copy (intact, then changed), the refused download.
    assert results == ["match", "match", "match", "mismatch", "mismatch"]


def test_a_report_says_which_entry_of_the_history_it_describes_and_later_work_is_not_in_it(cm_client):
    t = team(cm_client)
    add_note(t.lead, t.case_id, title="First steps (fictional)", text="Fictional: the complainant was interviewed.")
    first = generate(t.lead, t.case_id)["report"]
    add_note(t.lead, t.case_id, title="Second steps (fictional)", text="Fictional: the bank was written to.")
    second = generate(t.lead, t.case_id)["report"]
    assert second["as_of_entry"] == first["as_of_entry"] + 2  # the first report's entry, then the second note
    words = pdf_text(download(t.lead, first["id"]))
    assert "First steps (fictional)" in words and "Second steps (fictional)" not in words  # written after that entry
    assert "Second steps (fictional)" in pdf_text(download(t.lead, second["id"]))
    entries = history(t.lead, t.case_id)
    assert [e["seq"] for e in entries if e["kind"] == "report_generated"] == [first["as_of_entry"] + 1, second["as_of_entry"] + 1]
    # Someone outside the case can't read the list (the same answer as for a case that doesn't exist).
    stranger = cm_client("stranger.kh")
    assert stranger.get(f"/api/v1/cases/{t.case_id}/reports").status_code == 404
    assert stranger.post(f"/api/v1/cases/{t.case_id}/reports", json={"purpose": PURPOSE}).status_code == 404


def test_reports_have_versions_follow_the_shared_view_and_are_never_edited(cm_client):
    t = team(cm_client)
    exhibit = upload(t.lead, t.case_id, PNG)["evidence"]
    assert t.lead.post(f"/api/v1/evidence/{exhibit['id']}/verify").json()["result"] == "match"  # a custody event with the check's method
    sealed = upload(t.lead, t.case_id, PNG + b" second", "second.png", title="Second message (fictional)")["evidence"]
    assert t.supervisor.post(f"/api/v1/evidence/{sealed['id']}/seal", json={"reason": "Protected witness (fictional)"}).status_code == 200
    first = generate(t.lead, t.case_id, report_type="evidence_register")["report"]
    assert first["display_id"] == "RPT-0001" and first["withheld_entries"] == 1  # the sealed exhibit is never in a report
    # Even the supervisor's report leaves it out: every member can open a report.
    words = pdf_text(download(t.lead, first["id"]))
    assert "EV-0001" in words and "EV-0002" not in words and "Chain of custody of EV-0001" in words
    # The register shows the check in words: no fingerprint, no code, not even the name of the method.
    assert "automatic file check" in words
    assert re.search(r"[0-9a-f]{16,}", words.lower()) is None and "sha-256" not in words.lower() and "sha256" not in words.lower()
    second = generate(t.lead, t.case_id, report_type="evidence_register")["report"]
    assert (second["display_id"], second["version_number"]) == ("RPT-0001", 2)
    listed = t.lead.get(f"/api/v1/cases/{t.case_id}/reports").json()["reports"]
    assert [(r["display_id"], r["version_number"]) for r in listed] == [("RPT-0001", 2), ("RPT-0001", 1)]
    # Version 2 describes the case as it stood after version 1 was added.
    assert second["as_of_entry"] == first["as_of_entry"] + 1

    # A report is kept exactly as it was signed: it can't be revised (a new version is generated instead) or deleted.
    report_file = next(f for f in files(t.lead, t.case_id, folder="reports") if f["display_id"] == "RPT-0001")
    refused = revise(t.lead, report_file["id"], "edited", report_file["version_number"], status=422)
    assert "generated report" in refused["detail"]
    assert t.lead.delete(f"/api/v1/reports/{first['id']}").status_code == 405
    # Reading needs access to the case; generating needs the right to add to it.
    outsider = cm_client("inv.outsider")
    assert outsider.get(f"/api/v1/reports/{first['id']}").status_code == 404
    checked = verify_file(outsider, download(t.lead, first["id"]))  # genuine, but no details for someone outside the case
    assert checked["result"] == "match" and checked["report"] is None and "don't have access" in checked["message"]
    # A Viewer only reads; the supervisor oversees the case and may add to it (a new version of the register).
    viewer = cm_client("inv.viewer")
    add_member(t.lead, t.case_id, viewer.user, "viewer")
    generate(viewer, t.case_id, status=403, report_type="evidence_register")
    third = generate(t.supervisor, t.case_id, report_type="evidence_register")["report"]
    assert third["version_number"] == 3 and third["withheld_entries"] == 1
    # The supervisor may see the sealed exhibit, but a report is read by every member: it is left out of theirs too.
    supervisor_words = pdf_text(download(t.supervisor, third["id"]))
    assert "EV-0001" in supervisor_words and "EV-0002" not in supervisor_words
    assert generate(t.lead, t.case_id, purpose="short", status=422)["detail"].startswith("Say what the report is for")


# ---------------------------------------------------------------- the audit chain


def chained(db_session) -> list[AuditEvent]:
    return list(db_session.scalars(select(AuditEvent).where(AuditEvent.chain_seq.is_not(None)).order_by(AuditEvent.chain_seq)))


def test_case_management_events_form_a_chain_and_an_edited_audit_row_breaks_it(cm_client, db_session, evidence_store):
    admin = cm_client("admin.kh", "super_admin", "confidential")
    t = team(cm_client)
    add_note(t.lead, t.case_id, title="Fictional note A.")
    add_note(t.lead, t.case_id, title="Fictional note B.")
    events = chained(db_session)
    assert len(events) >= 3 and [e.chain_seq for e in events] == list(range(events[0].chain_seq, events[0].chain_seq + len(events)))
    assert all(later.prev_hash == earlier.hash for earlier, later in zip(events, events[1:]))
    assert db_session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "auth.login",
                                                                               AuditEvent.chain_seq.is_not(None))) == 0  # outside the chain

    verified = admin.post("/api/v1/admin/audit/verify").json()
    assert verified["status"] == "ok" and verified["summary"]["intact"] is True
    signed = admin.post("/api/v1/admin/audit/checkpoints").json()
    assert signed["status"] == "ok" and signed["summary"]["signed"] is True
    checkpoint = db_session.scalar(select(AuditCheckpoint))
    assert evidence_store.hash(checkpoint.storage_key) == checkpoint.stored_sha256  # also kept in the write-once store

    # The database refuses to change or delete a chained event...
    target = events[1]
    with pytest.raises(Exception, match="Case Management"), db_session.begin_nested():
        db_session.execute(text(f"UPDATE audit_events SET details = '{{}}' WHERE id = {target.id}"))
    # ...so someone with full control of the database switches the rule off: the edit is detected.
    db_session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER cm_audit_events_permanent"))
    db_session.execute(text(f"UPDATE audit_events SET details = '{{\"edited\": true}}' WHERE id = {target.id}"))
    report = audit_chain.verify(db_session, evidence_store)
    assert not report.intact and (report.breaks[0].problem, report.breaks[0].chain_seq) == ("edited", target.chain_seq)

    # Recomputing every hash after the edit makes the chain look whole, but it no longer matches the signed checkpoint.
    db_session.execute(text("""
        DO $$ DECLARE e audit_events; previous text := repeat('0', 64);
        BEGIN FOR e IN SELECT * FROM audit_events WHERE chain_seq IS NOT NULL ORDER BY chain_seq LOOP
            UPDATE audit_events SET prev_hash = previous, hash = cm_audit_hash(previous, e) WHERE id = e.id RETURNING hash INTO previous;
        END LOOP; END $$"""))
    problems = {b.problem for b in audit_chain.verify(db_session, evidence_store).breaks}
    assert problems == {"checkpoint_mismatch"}

    # A deleted event leaves a gap; the administrators' check fails, and they are told.
    db_session.execute(text(f"DELETE FROM audit_events WHERE id = {events[2].id}"))
    other_admin = cm_client("admin2.kh", "super_admin", "confidential")
    failed = admin.post("/api/v1/admin/audit/verify").json()
    assert failed["status"] == "failed" and "missing" in {b["problem"] for b in failed["summary"]["breaks"]}
    # The other administrators are told (whoever ran the check sees the result directly).
    assert db_session.scalar(select(Notification).where(Notification.user_id == other_admin.user.id,
                                                        Notification.kind == "governance.audit_chain_broken")) is not None


def test_a_checkpoint_needs_the_right_key_and_its_stored_file(cm_client, db_session, evidence_store, monkeypatch):
    admin = cm_client("admin.kh", "super_admin", "confidential")
    team(cm_client)
    admin.post("/api/v1/admin/audit/checkpoints")
    assert audit_chain.verify(db_session, evidence_store).intact
    monkeypatch.setattr(get_settings(), "cm_checkpoint_key", type(get_settings().jwt_secret)("another-key-kept-elsewhere-0123456789"))
    assert {b.problem for b in audit_chain.verify(db_session, evidence_store).breaks} == {"other_key"}
    monkeypatch.undo()
    checkpoint = db_session.scalar(select(AuditCheckpoint))
    stored = evidence_store.local_path(checkpoint.storage_key)
    os.chmod(stored, 0o644)
    stored.write_bytes(b'{"forged": true}')
    assert {b.problem for b in audit_chain.verify(db_session, evidence_store).breaks} == {"checkpoint_file"}
    # Only administrators verify or sign.
    assert cm_client("inv.someone").post("/api/v1/admin/audit/verify").status_code == 403


# ---------------------------------------------------------------- the worker


def test_the_worker_runs_due_jobs_once_records_them_and_warns_about_changed_evidence(cm_client, db_session, evidence_store):
    admin = cm_client("admin.kh", "super_admin", "confidential")
    t = team(cm_client)
    exhibit = upload(t.lead, t.case_id, PNG)["evidence"]
    sessions = lambda: nullcontext(db_session)  # noqa: E731 - the test's session, rolled back at the end
    runs = jobs.run_due(sessions, evidence_store)
    assert {r.job: r.status for r in runs} == {"audit_checkpoint": "ok", "audit_verify": "ok", "evidence_sweep": "ok"}
    assert jobs.due(db_session) == []  # each runs once a day
    assert db_session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "cm.governance.job")) == 3

    stored = next(p for p in (evidence_store.root / "objects").rglob("*") if p.is_file() and p.name == exhibit["sha256"])
    os.chmod(stored, 0o644)
    stored.write_bytes(b"changed behind the application's back")
    sweep = jobs.run(db_session, evidence_store, "evidence_sweep")
    assert sweep.status == "warning" and sweep.summary["mismatch"] == 1
    assert db_session.scalar(select(Notification).where(Notification.user_id == admin.user.id,
                                                        Notification.kind == "governance.evidence_integrity")) is not None
    overview = admin.get("/api/v1/admin/governance").json()
    assert {j["job"]: j["last_run"]["status"] for j in overview["jobs"]}["evidence_sweep"] == "warning"
    assert overview["chain"]["events"] > 0 and set(overview["settings"]) >= {"mfa_required", "checkpoint_key_set", "runtime_login"}
    assert db_session.scalar(select(func.count()).select_from(JobRun)) == 4
