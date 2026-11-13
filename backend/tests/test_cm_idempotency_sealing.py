"""Case Management: repeated create requests (Idempotency-Key), sealing notes, and a note's version history (fictional data)."""

import datetime as dt

import pytest
from cm_support import CASE, PNG, add_note, create_case, files, history, revise, stored_files, waiting_files
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.casemgmt import idempotency
from app.casemgmt.models import Artifact, CaseEntry, CaseFamily, CaseStatusEvent, EvidenceItem
from app.db.models import AuditEvent


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def test_a_repeated_create_returns_the_first_answer(cm_client, db_session, evidence_store):
    lead = cm_client("inv.arun")
    key = {"Idempotency-Key": "case-create-0001"}
    first = lead.post("/api/v1/cases", json=CASE, headers=key)
    again = lead.post("/api/v1/cases", json=CASE, headers=key)
    assert first.status_code == again.status_code == 201 and first.json() == again.json()
    assert again.headers["idempotent-replay"] == "true" and count(db_session, CaseFamily) == 1
    assert lead.post("/api/v1/cases", json={**CASE, "title": "Another case (fictional)"}, headers=key).status_code == 422
    assert lead.post("/api/v1/cases", json=CASE, headers={"Idempotency-Key": "short"}).status_code == 422
    assert cm_client("inv.other").post("/api/v1/cases", json=CASE, headers=key).status_code == 201  # keys are per user
    assert count(db_session, CaseFamily) == 2
    replayed = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.case.created")).all()
    assert [e.details.get("replayed") for e in replayed].count(True) == 1

    # A note sent twice (a lost answer): with a key, the repeat is the same note, not a second one.
    case_id = first.json()["case_id"]
    body = {"folder": "investigation-notes", "title": "Note (fictional)", "content": {"text": "First note (fictional)"}}
    entries = count(db_session, CaseEntry)
    one = lead.post(f"/api/v1/cases/{case_id}/notes", json=body, headers={"Idempotency-Key": "note-0001"})
    two = lead.post(f"/api/v1/cases/{case_id}/notes", json=body, headers={"Idempotency-Key": "note-0001"})
    assert one.status_code == two.status_code == 201 and one.json() == two.json()
    assert count(db_session, CaseEntry) == entries + 1 and count(db_session, Artifact) == 3  # two case summaries and the note

    # A new version sent twice: one new version.
    note_id = one.json()["file"]["id"]
    revision = {"content": {"text": "Second wording (fictional)"}, "expected_version": 1}
    first_rev = lead.post(f"/api/v1/artifacts/{note_id}/versions", json=revision, headers={"Idempotency-Key": "revise-0001"})
    second_rev = lead.post(f"/api/v1/artifacts/{note_id}/versions", json=revision, headers={"Idempotency-Key": "revise-0001"})
    assert first_rev.status_code == second_rev.status_code == 201 and first_rev.json() == second_rev.json()
    assert first_rev.json()["version"]["version_number"] == 2

    # An evidence upload sent twice: one exhibit, one stored file, nothing left waiting.
    form = {"folder": "digital-evidence", "title": "Screenshot (fictional)"}
    upload = lambda: lead.post(f"/api/v1/cases/{case_id}/evidence", data=form, files={"file": ("shot.png", PNG)},  # noqa: E731
                               headers={"Idempotency-Key": "evidence-0001"})
    first_upload, second_upload = upload(), upload()
    assert first_upload.status_code == second_upload.status_code == 201
    assert first_upload.json()["evidence"]["id"] == second_upload.json()["evidence"]["id"]
    assert count(db_session, EvidenceItem) == 1 and len(stored_files(evidence_store)) == 1 and waiting_files(evidence_store) == []


def test_keys_are_honoured_for_24_hours(cm_client, monkeypatch):
    lead = cm_client("inv.arun")
    key = {"Idempotency-Key": "case-create-0002"}
    assert lead.post("/api/v1/cases", json=CASE, headers=key).status_code == 201
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=25)
    monkeypatch.setattr(idempotency, "_now", lambda: later)
    assert "24 hours" in lead.post("/api/v1/cases", json=CASE, headers=key).json()["detail"]


def test_sealed_notes_disappear_for_investigators_but_stay_on_record(cm_client, db_session):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    added = add_note(lead, case_id, folder="investigation-notes", title="Transcript of the recorded call (fictional)",
                     artifact_type="transcription")["file"]
    url = f"/api/v1/artifacts/{added['id']}"

    assert lead.post(f"{url}/seal", json={"reason": "Linked to a sealed recording (fictional)"}).status_code == 403
    sealed = supervisor.post(f"{url}/seal", json={"reason": "Linked to a sealed recording (fictional)"}).json()
    assert sealed["sealed"] is True and sealed["sealed_by"]["username"] == "sup.kh"
    assert supervisor.post(f"{url}/seal", json={"reason": "Sealing twice"}).status_code == 422

    # For the lead it is as if it weren't there.
    assert lead.get(f"{url}/versions").status_code == 404
    assert added["display_id"] not in [f["display_id"] for f in files(lead, case_id)]
    revise(lead, added["id"], "Edited", 1, status=404)
    comment = {"target_type": "artifact", "target_id": added["id"], "body": "A remark (fictional)"}
    assert lead.post(f"/api/v1/cases/{case_id}/comments", json=comment).status_code == 404
    # The supervisor still sees it; unsealing brings it back. Both changes are recorded with their reasons.
    assert supervisor.get(f"{url}/versions").json()["sealed"] is True
    assert added["display_id"] in [f["display_id"] for f in files(supervisor, case_id)]
    supervisor.post(f"{url}/unseal", json={"reason": "Recording unsealed by the court (fictional)"})
    assert lead.get(f"{url}/versions").status_code == 200
    events = db_session.scalars(select(CaseStatusEvent).where(CaseStatusEvent.field == "seal").order_by(CaseStatusEvent.id)).all()
    assert [(e.new_value, e.reason.split(":")[0]) for e in events] == [("sealed", "TRN-0001"), ("unsealed", "TRN-0001")]
    assert [e["kind"] for e in history(lead, case_id)][-2:] == ["file_sealed", "file_unsealed"]
    with pytest.raises(IntegrityError, match="only"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE artifacts SET title = 'Renamed'"))


def test_a_notes_version_history_lists_every_version(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    note = add_note(lead, case_id, title="The suspect (fictional)", text="Unknown (fictional)")["file"]
    revise(lead, note["id"], "A relative (fictional, wrong)", 1)
    revise(lead, note["id"], "A relative, confirmed (fictional, wrong)", 2)
    for who in (lead, supervisor):
        versions = who.get(f"/api/v1/artifacts/{note['id']}/versions").json()["versions"]
        assert [(v["version_number"], v["content"]["text"]) for v in versions] == [
            (1, "Unknown (fictional)"), (2, "A relative (fictional, wrong)"), (3, "A relative, confirmed (fictional, wrong)")]
    # A mistake is corrected by one more version: the wrong ones stay in the history, attributed to who wrote them.
    revise(lead, note["id"], "Not a relative: an unknown person (fictional)", 3, note="The relative assumption was wrong (fictional)")
    versions = lead.get(f"/api/v1/artifacts/{note['id']}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [1, 2, 3, 4] and versions[3]["change_note"] == "The relative assumption was wrong (fictional)"
    assert [f["version_number"] for f in files(lead, case_id, folder="investigation-notes")] == [4]  # the current view shows the latest
