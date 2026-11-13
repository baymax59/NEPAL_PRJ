"""Case Management: adding evidence to a folder of the case, file checks, who sees it, sealing and no deletion (fictional data)."""

import datetime as dt
import hashlib
import io
import os
import uuid
from types import SimpleNamespace

import pytest
from cm_support import PNG, add_member, add_note, create_case, files, history, revise, stored_files, upload, waiting_files, withdraw
from conftest import build_pdf
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.casemgmt.errors import Conflict, Invalid, TooLarge
from app.casemgmt.models import EvidenceItem, EvidenceObject, EvidenceVersion, Organization
from app.core.config import get_settings
from app.db.models import AuditEvent

CSV = b"caller,callee,start\nFICTIONAL-NUMBER-A,FICTIONAL-NUMBER-B,2026-11-01T10:00:00+05:30\n"


def team(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, id=created["case_id"])


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def test_adding_evidence_hashes_stores_and_records_it(cm_client, db_session, evidence_store):
    case = team(cm_client)
    result = upload(case.lead, case.id, PNG, "WhatsApp Message.PNG", collected_at="2026-11-02T14:30:00+05:30",
                    collected_by="SI Meena (fictional)", source="Complainant's phone (fictional)",
                    collection_authority="Seizure memo 12/2026 (fictional)", evidence_type="screenshot")
    item = result["evidence"]
    assert (item["display_id"], item["folder"], item["status"]) == ("EV-0001", "digital-evidence", "active")
    assert (item["sha256"], item["size_bytes"]) == (hashlib.sha256(PNG).hexdigest(), len(PNG))
    assert (item["mime_type"], item["category"], item["evidence_type"], item["active_content"]) == ("image/png", "image", "screenshot", False)
    assert item["custodian"]["user"]["username"] == "inv.arun" and item["classification"] == "restricted"

    entry = history(case.lead, case.id)[-1]
    assert (entry["seq"], entry["kind"], result["entry"]) == (2, "evidence_added", 2)
    assert entry["summary"] == "EV-0001 WhatsApp message (fictional) added to digital-evidence" and entry["details"]["sha256"] == item["sha256"]

    # The bytes are stored once, under their hash, read-only.
    [stored] = stored_files(evidence_store)
    assert stored.name == item["sha256"] and stored.read_bytes() == PNG and not os.access(stored, os.W_OK)
    assert waiting_files(evidence_store) == []
    assert [f["display_id"] for f in files(case.lead, case.id, folder="digital-evidence")] == ["EV-0001"]

    custody = case.lead.get(f"/api/v1/evidence/{item['id']}/custody").json()
    collected, ingested = custody["events"]
    assert (collected["event_type"], ingested["event_type"]) == ("collected", "ingested")
    assert dt.datetime.fromisoformat(collected["occurred_at"]) == dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC)
    assert collected["occurred_tz"] == "+05:30" and collected["authorization_ref"] == "Seizure memo 12/2026 (fictional)"
    assert ingested["verification_sha256"] == item["sha256"] and ingested["to_custodian"]["user"]["username"] == "inv.arun"

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "cm.evidence.added"))
    assert event.outcome == "success" and event.target_id == case.created["display_id"]
    assert event.details["sha256"] == item["sha256"] and "whatsapp" not in str(event.details).lower()  # no file names in the log


def test_the_same_bytes_are_stored_once(cm_client, db_session, evidence_store):
    case = team(cm_client)
    first = upload(case.lead, case.id, PNG, "message.png")
    second = upload(case.lead, case.id, PNG, "message-copy-from-second-phone.png", title="Same message, second phone (fictional)")
    assert second["evidence"]["display_id"] == "EV-0002" and second["duplicates"] == [
        {"id": first["evidence"]["id"], "display_id": "EV-0001", "title": "WhatsApp message (fictional)"}]
    assert count(db_session, EvidenceObject) == 1 and len(stored_files(evidence_store)) == 1


def test_the_store_never_overwrites_or_keeps_refused_uploads(evidence_store):
    incoming = evidence_store.receive(io.BytesIO(b"fictional exhibit"), 1000)
    key, created = evidence_store.keep(incoming)
    assert created and evidence_store.hash(key) == hashlib.sha256(b"fictional exhibit").hexdigest()
    again, created_again = evidence_store.keep(evidence_store.receive(io.BytesIO(b"fictional exhibit"), 1000))
    assert (again, created_again) == (key, False) and waiting_files(evidence_store) == []

    path = evidence_store.local_path(key)  # someone with server access changes the stored file...
    os.chmod(path, 0o644)
    path.write_bytes(b"changed")
    with pytest.raises(Conflict, match="no longer matches"):  # ...and the same exhibit uploaded again is refused
        evidence_store.keep(evidence_store.receive(io.BytesIO(b"fictional exhibit"), 1000))
    assert path.read_bytes() == b"changed"  # never "repaired" by overwriting

    with pytest.raises(TooLarge):
        evidence_store.receive(io.BytesIO(b"x" * 11), 10)
    with pytest.raises(Invalid, match="empty"):
        evidence_store.receive(io.BytesIO(b""), 10)
    assert waiting_files(evidence_store) == []
    with pytest.raises(ValueError):
        evidence_store.local_path("../../etc/passwd")


def test_a_file_must_be_what_its_name_says(cm_client, db_session, evidence_store, monkeypatch):
    case = team(cm_client)
    program = b"MZ\x90\x00" + b"\x00" * 200
    assert "disguised" in upload(case.lead, case.id, program, "statement.pdf", status=415)["detail"].lower()
    assert "doesn't match" in upload(case.lead, case.id, b"just some text", "photo.jpg", status=415)["detail"]
    assert "empty" in upload(case.lead, case.id, b"", "empty.txt", status=422)["detail"]
    monkeypatch.setattr(get_settings(), "max_evidence_mb", 1)
    upload(case.lead, case.id, b"a" * (1024 * 1024 + 1), "big.txt", status=413)
    assert count(db_session, EvidenceItem) == 0 and stored_files(evidence_store) == [] and waiting_files(evidence_store) == []

    # Honestly named programs and pages are accepted as evidence, marked, and never opened by the application.
    sample = upload(case.lead, case.id, program, "malware-sample.exe", folder="digital-evidence", title="Sample (fictional)")
    assert (sample["evidence"]["category"], sample["evidence"]["active_content"]) == ("executable", True)
    page = upload(case.lead, case.id, b"<!DOCTYPE html><html><script>alert(1)</script></html>", "phishing-page.html",
                  folder="osint", title="Phishing page (fictional)")
    assert (page["evidence"]["mime_type"], page["evidence"]["active_content"]) == ("text/html", True)
    monkeypatch.setattr(get_settings(), "evidence_accept_programs", False)
    upload(case.lead, case.id, program, "another-sample.exe", folder="digital-evidence", status=415)


def test_who_may_add_evidence(cm_client, db_session, evidence_store):
    case = team(cm_client)
    sub, analyst, viewer = cm_client("sub.one", "sub_investigator"), cm_client("analyst.one", "analyst"), cm_client("viewer.one", "viewer")
    outsider = cm_client("inv.outsider")
    for client, role in ((sub, "sub_investigator"), (analyst, "analyst"), (viewer, "viewer")):
        add_member(case.lead, case.id, client.user, role)

    upload(viewer, case.id, b"viewer", "a.txt", status=403)  # a Viewer only reads
    upload(outsider, case.id, b"outsider", "o.txt", status=404)  # not on the team: the case is not even visible
    upload(sub, case.id, b"sub investigator", "b.txt")  # Sub Investigators and Analysts add files straight into the case
    upload(analyst, case.id, b"analyst", "c.txt")
    upload(case.supervisor, case.id, b"supervisor", "d.txt")  # the supervisor oversees the case and may add too
    upload(case.lead, case.id, b"lead", "e.txt")
    assert count(db_session, EvidenceItem) == 4 and len(stored_files(evidence_store)) == 4 and waiting_files(evidence_store) == []
    assert {f["created_by"]["username"] for f in files(case.lead, case.id, folder="digital-evidence")} == {
        "sub.one", "analyst.one", "sup.kh", "inv.arun"}


def test_folders_and_details_are_checked(cm_client):
    case = team(cm_client)
    upload(case.lead, case.id, PNG, "message.png")
    upload(case.lead, case.id, PNG, "message.png", title="Uploading the same file again (fictional)")  # allowed: the copy is noted
    for fields in ({"folder": "Bad Folder"}, {"folder": "../etc"}, {"collected_at": "2026-11-02T14:30:00"},
                   {"collected_at": "2099-01-01T00:00:00+00:00"}, {"classification": "public"}, {"classification": "confidential"},
                   {"evidence_type": "Bad Type!"}):
        upload(case.lead, case.id, b"text", "other.txt", status=422, **fields)


def test_evidence_never_changes_corrections_are_derived_notes(cm_client):
    case = team(cm_client)
    exhibit = upload(case.lead, case.id, CSV, "call-records.csv", folder="cdr-analysis", title="Call records (fictional)")
    evidence_id, number = exhibit["evidence"]["id"], exhibit["evidence"]["display_id"]
    assert case.lead.post(f"/api/v1/artifacts/{evidence_id}/versions", json={"content": {"text": "edited"}, "expected_version": 1}).status_code == 404

    analysis = add_note(case.lead, case.id, folder="cdr-analysis", title="Call network (fictional)", artifact_type="analysis",
                        text="Two numbers in regular contact (fictional)", derived_from=[number])["file"]
    revise(case.lead, analysis["id"], "Three numbers (fictional)", 1, derived_from=[number])
    add_note(case.lead, case.id, title="Based on nothing", derived_from=["EV-0099"], status=422)
    versions = case.lead.get(f"/api/v1/evidence/{evidence_id}/versions").json()
    assert versions["original"]["version_number"] == 1 and versions["original"]["sha256"] == hashlib.sha256(CSV).hexdigest()
    assert [(d["display_id"], d["version_number"], d["artifact_type"]) for d in versions["derived"]] == [
        ("ANL-0001", 1, "analysis"), ("ANL-0001", 2, "analysis")]

    withdraw(case.lead, "evidence", evidence_id, reason="Duplicate of the operator's export (fictional)")
    # It has left the team's view (the lead's included); the supervisor still has it, marked as withdrawn.
    assert [f["display_id"] for f in files(case.lead, case.id, folder="cdr-analysis", include_withdrawn=True)] == ["ANL-0001"]
    assert case.lead.get(f"/api/v1/evidence/{evidence_id}").status_code == 404
    assert files(case.supervisor, case.id, folder="cdr-analysis")[0]["status"] == "withdrawn"
    assert case.supervisor.get(f"/api/v1/evidence/{evidence_id}").status_code == 200  # still on record
    assert case.supervisor.get(f"/api/v1/evidence/{evidence_id}").json()["withdrawn_reason"] == "Duplicate of the operator's export (fictional)"
    assert [d["display_id"] for d in case.supervisor.get(f"/api/v1/evidence/{evidence_id}/versions").json()["derived"]] == ["ANL-0001", "ANL-0001"]


def test_only_the_cases_team_and_overseers_see_its_evidence(cm_client, db_session, evidence_store):
    case = team(cm_client)
    exhibit = upload(case.lead, case.id, PNG, "message.png")["evidence"]
    stranger = cm_client("inv.other")  # same station, not on the team
    assert stranger.get(f"/api/v1/evidence/{exhibit['id']}").status_code == 404
    assert stranger.get(f"/api/v1/evidence/{exhibit['id']}").json() == stranger.get(f"/api/v1/evidence/{uuid.uuid4()}").json()
    assert case.supervisor.get(f"/api/v1/evidence/{exhibit['id']}").status_code == 200  # the case's supervisor sees it
    add_member(case.lead, case.id, stranger.user, "viewer")
    assert stranger.get(f"/api/v1/evidence/{exhibit['id']}").status_code == 200  # a Viewer reads
    other = Organization(code="XY", name="Another force (fictional)")
    db_session.add(other)
    db_session.commit()
    foreign = cm_client("admin.xy", "super_admin", "confidential", organization=other)
    assert foreign.get(f"/api/v1/evidence/{exhibit['id']}").status_code == 404


def test_sealed_evidence_disappears_for_investigators_but_stays_on_record(cm_client):
    case = team(cm_client)
    sealed = upload(case.lead, case.id, b"Statement of a protected witness (FICTIONAL)", "witness.txt", folder="complainant",
                    title="Protected witness statement (fictional)")
    upload(case.lead, case.id, PNG, "message.png")
    evidence_id = sealed["evidence"]["id"]
    url = f"/api/v1/evidence/{evidence_id}"

    assert case.lead.post(f"{url}/seal", json={"reason": "Protected witness (fictional)"}).status_code == 403
    detail = case.supervisor.post(f"{url}/seal", json={"reason": "Protected witness (fictional)"}).json()
    assert detail["sealed"] is True and detail["sealed_reason"] == "Protected witness (fictional)"
    assert case.supervisor.post(f"{url}/seal", json={"reason": "Sealing twice"}).status_code == 422

    # For the lead it is as if it weren't there.
    assert case.lead.get(url).status_code == 404 and case.lead.post(f"{url}/download-token").status_code == 404
    assert [f["display_id"] for f in files(case.lead, case.id, folder="digital-evidence")] == ["EV-0002"]
    assert files(case.lead, case.id, folder="complainant") == []
    withdraw(case.lead, "evidence", evidence_id, status=404)
    assert [f["display_id"] for f in files(case.supervisor, case.id, folder="complainant")] == ["EV-0001"]  # the supervisor sees it

    # The supervisor still sees it; unsealing brings it back. Both are custody events and history entries.
    assert case.supervisor.get(url).json()["sealed"] is True
    assert case.supervisor.post(f"{url}/unseal", json={"reason": "Trial concluded (fictional)"}).json()["sealed"] is False
    assert case.lead.get(url).status_code == 200
    events = [e["event_type"] for e in case.lead.get(f"{url}/custody").json()["events"]]
    assert events == ["ingested", "sealed", "unsealed"]
    assert [e["kind"] for e in history(case.lead, case.id)][-2:] == ["file_sealed", "file_unsealed"]


def test_evidence_above_a_users_clearance_is_hidden(cm_client):
    supervisor = cm_client("sup.kh", "supervisor", "confidential")
    lead = cm_client("inv.arun", clearance="confidential")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    secret = upload(lead, case_id, b"Informant details (FICTIONAL)", "informant.txt", folder="investigation-notes",
                    title="Informant details (fictional)", classification="confidential")
    colleague = cm_client("inv.colleague")  # restricted clearance: enough for the case, not for this exhibit
    add_member(lead, case_id, colleague.user)
    assert colleague.get(f"/api/v1/evidence/{secret['evidence']['id']}").status_code == 404
    assert files(colleague, case_id, folder="investigation-notes") == []
    assert lead.get(f"/api/v1/evidence/{secret['evidence']['id']}").json()["classification"] == "confidential"


def test_the_files_list_groups_exhibits_and_notes_by_folder(cm_client):
    case = team(cm_client)
    upload(case.lead, case.id, PNG, "message.png")
    upload(case.lead, case.id, b"Complaint text (FICTIONAL)", "complaint.txt", folder="complainant", title="Complaint (fictional)")
    add_note(case.lead, case.id, folder="complainant", title="Note on the complaint (fictional)")
    everything = case.lead.get(f"/api/v1/cases/{case.id}/files").json()
    assert {f["name"]: f["files"] for f in everything["folders"]}["complainant"] == 2
    assert [(f["folder"], f["display_id"], f["kind"]) for f in everything["files"]] == [
        ("case-information", "SUM-0001", "note"), ("complainant", "EV-0002", "evidence"), ("complainant", "NOTE-0001", "note"),
        ("digital-evidence", "EV-0001", "evidence")]  # folder by folder, in the order the folders were made; oldest first within a folder
    exhibit = [f for f in everything["files"] if f["kind"] == "evidence"][0]["evidence"]
    assert (exhibit["mime_type"], exhibit["category"]) in {("text/plain", "text"), ("image/png", "image")}
    assert case.lead.get(f"/api/v1/cases/{case.id}/files", params={"folder": "Bad Path"}).status_code == 422


def test_deleting_or_overwriting_evidence_is_refused_and_audited(cm_client, db_session):
    case = team(cm_client)
    exhibit = upload(case.lead, case.id, PNG, "message.png")
    evidence_id = exhibit["evidence"]["id"]
    attempts = [("DELETE", f"/api/v1/evidence/{evidence_id}"), ("PUT", f"/api/v1/evidence/{evidence_id}"),
                ("PATCH", f"/api/v1/evidence/{evidence_id}/custody"), ("POST", f"/api/v1/evidence/{evidence_id}/delete"),
                ("POST", f"/api/v1/evidence/{evidence_id}/overwrite")]
    for method, url in attempts:
        assert case.supervisor.request(method, url, json={}).status_code == 405, (method, url)
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.destructive_operation.rejected")).all()
    assert len(events) == len(attempts) and {e.target_id for e in events} == {case.created["display_id"] + "/EV-0001"}
    assert case.lead.post(f"/api/v1/evidence/{evidence_id}/verify").json()["result"] == "match"  # untouched


DATABASE_REFUSES = [
    ("UPDATE evidence_objects SET size_bytes = 1", "permanent"),
    ("DELETE FROM evidence_objects", "permanent"),
    ("UPDATE evidence_versions SET original_filename = 'renamed.png'", "permanent"),
    ("DELETE FROM evidence_versions", "permanent"),
    ("DELETE FROM evidence_source_references", "permanent"),
    ("UPDATE chain_of_custody_events SET reason = 'edited afterwards'", "permanent"),
    ("DELETE FROM chain_of_custody_events", "permanent"),
    ("UPDATE evidence_integrity_checks SET result = 'mismatch'", "permanent"),
    ("DELETE FROM evidence_integrity_checks", "permanent"),
    ("DELETE FROM evidence_items", "permanent"),
    ("UPDATE evidence_items SET title = 'Renamed'", "only"),
    ("UPDATE evidence_items SET folder_id = gen_random_uuid()", "only"),  # a file never moves to another folder
    ("DELETE FROM case_folders", "permanent"),
    ("UPDATE case_folders SET name = 'renamed'", "permanent"),
]


@pytest.mark.parametrize(("statement", "message"), DATABASE_REFUSES)
def test_the_database_itself_refuses_to_change_evidence(cm_client, db_session, statement, message):
    case = team(cm_client)
    exhibit = upload(case.lead, case.id, CSV, "call-records.csv", folder="cdr-analysis", title="Call records (fictional)",
                     source_system="Operator CDR export (fictional)", source_record_id="REQ-0001")
    case.lead.post(f"/api/v1/evidence/{exhibit['evidence']['id']}/verify")
    with pytest.raises(IntegrityError, match=message):
        with db_session.begin_nested():
            db_session.execute(text(statement))


def test_an_exhibit_has_exactly_one_version(cm_client, db_session):
    case = team(cm_client)
    exhibit = upload(case.lead, case.id, PNG, "message.png")
    original = db_session.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_item_id == uuid.UUID(exhibit["evidence"]["id"])))
    fields = {c: getattr(original, c) for c in ("evidence_item_id", "object_sha256", "original_filename", "display_filename",
                                                 "mime_type", "size_bytes", "active_content", "uploaded_by")}
    for version_number in (1, 2):  # a second original, or a "v2" of an original: both refused
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.add(EvidenceVersion(**fields, version_number=version_number))
    with db_session.begin_nested():  # sealing and withdrawing are the changes an exhibit's record allows
        db_session.execute(text("UPDATE evidence_items SET sealed = true, sealed_reason = 'direct test'"))
        db_session.execute(text("UPDATE evidence_items SET status = 'withdrawn', withdrawn_reason = 'direct test'"))


def test_acceptance_evidence_is_uploaded_recorded_and_checked(cm_client):
    """Specification §27 step 4 (evidence uploaded and recorded in the case) and step 15 (integrity checks succeed)."""
    admin = cm_client("admin.kh", "super_admin", "restricted")
    arun = cm_client("inspector.arun")
    created = create_case(admin, title="Online Banking Fraud Investigation (FICTIONAL)", lead_investigator_id=str(arun.user.id))
    case_id = created["case_id"]
    exhibits = [
        upload(arun, case_id, PNG, "whatsapp-message.png", title="WhatsApp fraud message (fictional)"),
        upload(arun, case_id, build_pdf([["Bank statement (FICTIONAL)", "Debit INR 250000"]]), "bank-statement.pdf",
               folder="financial-transactions", title="Bank transaction statement (fictional)"),
        upload(arun, case_id, b"hxxp://fictional-bank-login.example/verify\n", "suspicious-url.txt", folder="osint",
               title="Suspicious URL (fictional)"),
        upload(arun, case_id, b"2026-11-01T10:02:11Z 203.0.113.7 POST /login 200\n", "network.log", folder="digital-evidence",
               title="Network log (fictional)"),
    ]
    add_note(arun, case_id, title="Initial assessment (fictional)", text="Phishing link led to three transfers (fictional)",
             derived_from=[e["evidence"]["display_id"] for e in exhibits])
    assert [e["kind"] for e in history(arun, case_id)] == ["case_registered"] + ["evidence_added"] * 4 + ["note_added"]
    for exhibit in exhibits:
        assert arun.post(f"/api/v1/evidence/{exhibit['evidence']['id']}/verify").json()["result"] == "match"
    report = admin.get("/api/v1/admin/evidence-integrity").json()
    assert report["counts"] == {"match": 4, "mismatch": 0, "missing": 0, "never_checked": 0} and report["total"] == 4
    assert admin.get("/api/v1/admin/cases").json()["items"][0]["evidence_count"] == 4
