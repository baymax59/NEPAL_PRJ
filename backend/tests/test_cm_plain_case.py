"""The plain case design (phase G-2, docs/case-management/13-plain-case-design.md): the folders made when a case is registered, files
(notes with versions, exhibits, withdrawing), the history chain and its check, and the team added directly by the Investigator.
All names and facts are fictional."""

import uuid
from types import SimpleNamespace

import pytest
from cm_support import (
    PNG,
    add_member,
    add_note,
    case,
    create_case,
    files,
    folders,
    history,
    make_station,
    notices,
    place,
    remove_member,
    revise,
    set_status,
    team_of,
    upload,
    withdraw,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.casemgmt import history as case_history
from app.casemgmt.case_types import CASE_TYPES
from app.casemgmt.models import CaseEntry


def make_case(cm_client, **overrides) -> SimpleNamespace:
    sup = cm_client("sup.plain", "supervisor", "confidential")
    lead = cm_client("inv.plain")
    created = create_case(sup, lead_investigator_id=str(lead.user.id), supervisor_id=str(sup.user.id), **overrides)
    return SimpleNamespace(sup=sup, lead=lead, id=created["case_id"], created=created, display_id=created["display_id"])


# ---------------------------------------------------------------- registering a case


def test_registering_a_case_makes_its_folders_at_once(cm_client):
    t = make_case(cm_client)
    expected = CASE_TYPES["cyber_fraud"]["folders"]
    assert t.created["folders"] == expected  # made from the case's type, in the type's order
    listed = folders(t.lead, t.id)
    assert [f["name"] for f in listed] == expected and not any(f["system"] for f in listed)
    assert {f["name"]: f["files"] for f in listed}["case-information"] == 1  # the case summary is in it
    assert [f["files"] for f in listed if f["name"] != "case-information"] == [0] * (len(expected) - 1)
    summary = files(t.lead, t.id, folder="case-information")
    assert [(f["display_id"], f["type"], f["kind"]) for f in summary] == [("SUM-0001", "case_summary", "note")]

    detail = case(t.lead, t.id)
    assert detail["lead"]["username"] == "inv.plain" and detail["my_role"] == "lead"
    assert [(m["user"]["username"], m["role"]) for m in detail["team"]] == [("inv.plain", "lead")]
    assert [f["name"] for f in detail["folders"]] == expected
    first = history(t.lead, t.id)
    assert [(e["seq"], e["kind"]) for e in first] == [(1, "case_registered")]
    assert first[0]["details"]["folders"] == expected and first[0]["details"]["lead"] == "inv.plain"

    # Another kind of case gets its own folders.
    theft = create_case(t.sup, case_type="theft", lead_investigator_id=str(t.lead.user.id), supervisor_id=str(t.sup.user.id))
    assert theft["folders"] == CASE_TYPES["theft"]["folders"] and "recovered-property" in theft["folders"]


def test_an_official_reference_at_registration_is_a_file_and_a_record(cm_client):
    sup = cm_client("sup.ref2", "supervisor", "confidential")
    lead = cm_client("inv.ref2")
    created = create_case(sup, lead_investigator_id=str(lead.user.id), supervisor_id=str(sup.user.id),
                          official_reference={"ref_type": "FIR", "number": "0123/2026", "issuing_authority": "Example PS (fictional)"})
    assert [f["display_id"] for f in files(lead, created["case_id"], folder="case-information")] == ["SUM-0001", "REF-0001"]
    assert case(lead, created["case_id"])["official_references"] == ["FIR 0123/2026, Example PS (fictional)"]


def test_folders_are_added_never_removed(cm_client):
    t = make_case(cm_client)
    sub = cm_client("sub.f")
    add_member(t.lead, t.id, sub.user)
    response = t.lead.post(f"/api/v1/cases/{t.id}/folders", json={"name": "Witness statements 2"})
    assert response.status_code == 201 and response.json()["name"] == "Witness statements 2" and response.json()["files"] == 0
    assert t.lead.post(f"/api/v1/cases/{t.id}/folders", json={"name": "witness statements 2"}).status_code == 409  # the same name
    assert t.lead.post(f"/api/v1/cases/{t.id}/folders", json={"name": "bad/name"}).status_code == 422
    assert sub.post(f"/api/v1/cases/{t.id}/folders", json={"name": "Mine"}).status_code == 403
    assert t.sup.post(f"/api/v1/cases/{t.id}/folders", json={"name": "From the supervisor"}).status_code == 201
    assert [e["kind"] for e in history(t.lead, t.id) if e["kind"] == "folder_added"] == ["folder_added", "folder_added"]
    assert t.lead.delete(f"/api/v1/cases/{t.id}/folders/{uuid.uuid4()}").status_code == 405  # nothing is deleted


# ---------------------------------------------------------------- notes: add, revise, withdraw


def test_a_note_goes_straight_into_a_folder_and_into_the_history(cm_client):
    t = make_case(cm_client)
    added = add_note(t.lead, t.id, folder="complainant", title="Statement of the complainant (fictional)", text="She shared an OTP.")
    assert (added["file"]["display_id"], added["file"]["folder"], added["file"]["version_number"], added["entry"]) == ("NOTE-0001", "complainant", 1, 2)
    assert [f["display_id"] for f in files(t.lead, t.id, folder="complainant")] == ["NOTE-0001"]
    assert {f["name"]: f["files"] for f in folders(t.lead, t.id)}["complainant"] == 1
    entry = history(t.lead, t.id)[-1]
    assert (entry["seq"], entry["kind"], entry["actor"]["username"]) == (2, "note_added", "inv.plain")
    assert "content_sha256" in entry["details"]
    add_note(t.lead, t.id, folder="no-such-folder", status=422)  # a note goes into one of the case's folders
    add_note(t.lead, t.id, title="ab", status=422)
    add_note(t.lead, t.id, artifact_type="report", status=422)  # reports are generated, not written
    assert len(files(t.lead, t.id)) == 2  # the summary and the note


def test_notes_name_the_files_they_are_based_on(cm_client, evidence_store):
    t = make_case(cm_client)
    exhibit = upload(t.lead, t.id, PNG)["evidence"]
    note = add_note(t.lead, t.id, title="Analysis of the message (fictional)", artifact_type="analysis", derived_from=[exhibit["display_id"]])
    versions = t.lead.get(f"/api/v1/artifacts/{note['file']['id']}/versions").json()["versions"]
    assert len(versions[0]["derived_from"]) == 1
    derived = t.lead.get(f"/api/v1/evidence/{exhibit['id']}/versions").json()["derived"]
    assert [d["display_id"] for d in derived] == [note["file"]["display_id"]]
    add_note(t.lead, t.id, derived_from=["EV-0099"], status=422)  # not a file of this case
    add_note(t.lead, t.id, derived_from=[note["file"]["display_id"] + "x"], status=422)


def test_a_revised_note_keeps_its_old_version_and_refuses_a_stale_edit(cm_client):
    t = make_case(cm_client)
    note = add_note(t.lead, t.id, text="First wording.")["file"]
    second = revise(t.lead, note["id"], "Second wording.", expected_version=1)["version"]
    assert second["version_number"] == 2 and second["content"] == {"text": "Second wording."}
    revise(t.lead, note["id"], "Written from the old version.", expected_version=1, status=409)  # someone was quicker
    third = revise(t.sup, note["id"], "Third wording.", expected_version=2, note="Corrected the date (fictional)")["version"]
    assert third["version_number"] == 3 and third["change_note"] == "Corrected the date (fictional)"
    shown = t.lead.get(f"/api/v1/artifacts/{note['id']}/versions").json()
    assert [v["content"]["text"] for v in shown["versions"]] == ["First wording.", "Second wording.", "Third wording."]  # nothing lost
    assert shown["can"]["revise"] is True
    assert [e["kind"] for e in history(t.lead, t.id)][-3:] == ["note_added", "note_revised", "note_revised"]
    summary = files(t.lead, t.id, folder="case-information")[0]
    revise(t.lead, summary["id"], "Changing the summary.", expected_version=1, status=422)  # the registration record


def test_what_each_part_may_do_with_notes(cm_client):
    t = make_case(cm_client)
    sub, analyst, viewer = cm_client("sub.n", "sub_investigator"), cm_client("ana.n", "analyst"), cm_client("view.n", "viewer")
    add_member(t.lead, t.id, sub.user)
    add_member(t.lead, t.id, analyst.user, "analyst")
    add_member(t.lead, t.id, viewer.user, "viewer")
    mine = add_note(sub, t.id, folder="investigation-notes", title="By the Sub Investigator")["file"]
    theirs = add_note(analyst, t.id, folder="cdr-analysis", title="By the Analyst", artifact_type="analysis")["file"]
    by_lead = add_note(t.lead, t.id, title="By the Investigator")["file"]
    add_note(viewer, t.id, status=403)  # a Viewer only reads
    # Their own notes: new versions are fine. Someone else's: only the Investigator or the supervisor.
    revise(sub, mine["id"], "Better wording.", 1)
    revise(sub, by_lead["id"], "Changing the Investigator's note.", 1, status=403)
    revise(analyst, theirs["id"], "Better analysis.", 1)
    revise(analyst, mine["id"], "Changing the Sub Investigator's note.", 2, status=403)
    revise(t.lead, mine["id"], "The Investigator revises any note.", 2)
    revise(t.sup, theirs["id"], "The supervisor revises any note.", 2)
    revise(viewer, mine["id"], "A Viewer can't.", 3, status=403)
    # Withdrawing is for the Investigator and above.
    withdraw(sub, "artifacts", mine["id"], status=403)
    withdraw(analyst, "artifacts", theirs["id"], status=403)
    withdraw(viewer, "artifacts", mine["id"], status=403)
    assert [f["display_id"] for f in files(viewer, t.id, folder="investigation-notes")] == ["NOTE-0001", "NOTE-0002"]  # and they all see the files


def test_a_withdrawn_file_leaves_the_current_view_and_stays_in_the_history(cm_client):
    t = make_case(cm_client)
    wrong = add_note(t.lead, t.id, title="Wrongly entered (fictional)")["file"]
    keep = add_note(t.lead, t.id, title="A good note")["file"]
    withdraw(t.lead, "artifacts", wrong["id"], reason="x", status=422)  # a reason is needed
    done = withdraw(t.lead, "artifacts", wrong["id"], reason="Entered in the wrong case (fictional)")
    assert done["status"] == "withdrawn" and done["withdrawn_reason"] == "Entered in the wrong case (fictional)"
    assert [f["display_id"] for f in files(t.lead, t.id, folder="investigation-notes")] == [keep["display_id"]]
    assert [f["display_id"] for f in files(t.lead, t.id, folder="investigation-notes", include_withdrawn=True)] == [keep["display_id"]]  # gone for the team
    shown = files(t.sup, t.id, folder="investigation-notes")  # the supervisor keeps it in view, marked as withdrawn, with who and why
    assert [(f["display_id"], f["status"]) for f in shown] == [(wrong["display_id"], "withdrawn"), (keep["display_id"], "active")]
    assert shown[0]["withdrawn_by"]["id"] == str(t.lead.user.id) and shown[0]["withdrawn_at"] and shown[0]["withdrawn_reason"].startswith("Entered")
    assert t.lead.get(f"/api/v1/artifacts/{wrong['id']}/versions").status_code == 404
    assert t.sup.get(f"/api/v1/artifacts/{wrong['id']}/versions").status_code == 200
    assert {f["name"]: f["files"] for f in folders(t.lead, t.id)}["investigation-notes"] == 1  # withdrawn files are not counted
    withdraw(t.sup, "artifacts", keep["id"], reason="The supervisor tries to remove it (fictional)", status=403)  # a supervisor removes nothing
    withdraw(t.sup, "artifacts", wrong["id"], status=403)
    revise(t.sup, wrong["id"], "Trying to revise it.", 1, status=422)
    summary = files(t.lead, t.id, folder="case-information")[0]
    withdraw(t.lead, "artifacts", summary["id"], status=422)  # the registration record can't be withdrawn
    entry = [e for e in history(t.lead, t.id) if e["kind"] == "file_withdrawn"]
    assert len(entry) == 1 and entry[0]["details"]["reason"] == "Entered in the wrong case (fictional)"
    # The files and their versions are all still in the database: nothing was deleted.
    assert t.lead.post(f"/api/v1/artifacts/{wrong['id']}/delete", json={}).status_code == 405


# ---------------------------------------------------------------- exhibits


def test_an_exhibit_is_added_to_a_folder_and_can_be_withdrawn(cm_client, evidence_store):
    t = make_case(cm_client)
    analyst = cm_client("ana.e", "analyst")
    viewer = cm_client("view.e", "viewer")
    add_member(t.lead, t.id, analyst.user, "analyst")
    add_member(t.lead, t.id, viewer.user, "viewer")
    added = upload(t.lead, t.id, PNG, folder="digital-evidence", title="WhatsApp message (fictional)")
    assert added["evidence"]["display_id"] == "EV-0001" and added["evidence"]["folder"] == "digital-evidence"
    assert added["evidence"]["status"] == "active" and added["duplicates"] == []
    upload(t.lead, t.id, PNG, folder="no-such-folder", status=422)
    upload(viewer, t.id, PNG + b"x", status=403)  # a Viewer only reads
    again = upload(analyst, t.id, PNG, title="The same file again (fictional)")  # an Analyst adds files too
    assert [d["display_id"] for d in again["duplicates"]] == ["EV-0001"]
    entries = history(t.lead, t.id)
    assert [e["kind"] for e in entries][-2:] == ["evidence_added", "evidence_added"]
    assert entries[-2]["summary"] == "EV-0001 WhatsApp message (fictional) added to digital-evidence"

    withdraw(analyst, "evidence", again["evidence"]["id"], status=403)
    withdrawn = withdraw(t.lead, "evidence", again["evidence"]["id"], reason="Uploaded twice by mistake (fictional)")
    assert withdrawn["status"] == "withdrawn"
    assert [f["display_id"] for f in files(t.lead, t.id, folder="digital-evidence")] == ["EV-0001"]
    assert [f["display_id"] for f in files(t.lead, t.id, folder="digital-evidence", include_withdrawn=True)] == ["EV-0001"]  # gone for the team
    withdraw(t.sup, "evidence", added["evidence"]["id"], reason="The supervisor tries to remove it (fictional)", status=403)
    shown = files(t.sup, t.id, folder="digital-evidence")  # the supervisor still has it
    assert [(f["display_id"], f["status"]) for f in shown] == [("EV-0001", "active"), ("EV-0002", "withdrawn")]
    assert shown[0]["kind"] == "evidence" and shown[0]["evidence"]["sha256"]
    # The exhibit's bytes and custody stay: withdrawing hides, nothing is removed.
    assert t.sup.get(f"/api/v1/evidence/{again['evidence']['id']}/custody").status_code == 200
    assert t.lead.get(f"/api/v1/evidence/{again['evidence']['id']}/custody").status_code == 404


# ---------------------------------------------------------------- the history chain


def test_the_history_is_one_chain_that_can_be_checked(cm_client, db_session, evidence_store):
    t = make_case(cm_client)
    sub = cm_client("sub.h", "sub_investigator")
    add_member(t.lead, t.id, sub.user)
    note = add_note(t.lead, t.id)["file"]
    revise(t.lead, note["id"], "Revised.", 1)
    upload(t.lead, t.id, PNG)
    set_status(t.lead, t.id, "under_investigation")
    remove_member(t.lead, t.id, sub.user)
    entries = history(t.lead, t.id)
    assert [e["seq"] for e in entries] == list(range(1, len(entries) + 1))
    assert [e["kind"] for e in entries] == ["case_registered", "member_added", "note_added", "note_revised", "evidence_added",
                                            "status_changed", "member_removed"]
    checked = t.lead.get(f"/api/v1/cases/{t.id}/history/check").json()
    assert checked == {"entries": 7, "intact": True, "first_problem": None, "problem": None}
    # Paging through it gives the same entries.
    first = t.lead.get(f"/api/v1/cases/{t.id}/history", params={"limit": 3}).json()
    assert [e["seq"] for e in first["entries"]] == [1, 2, 3] and first["next_after"] == 3
    rest = t.lead.get(f"/api/v1/cases/{t.id}/history", params={"limit": 50, "after": 3}).json()
    assert [e["seq"] for e in rest["entries"]] == [4, 5, 6, 7] and rest["next_after"] is None
    # "Recent activity": only the newest few, still oldest of them first.
    newest = t.lead.get(f"/api/v1/cases/{t.id}/history", params={"latest": 3}).json()
    assert [e["seq"] for e in newest["entries"]] == [5, 6, 7] and newest["next_after"] is None
    assert [e["seq"] for e in t.lead.get(f"/api/v1/cases/{t.id}/history", params={"latest": 50}).json()["entries"]] == list(range(1, 8))
    assert t.lead.get(f"/api/v1/cases/{t.id}/history", params={"latest": 0}).status_code == 422

    case_id = uuid.UUID(t.id)
    # The database itself refuses to change, remove or add out of order.
    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE case_entries SET summary = 'edited' WHERE case_family_id = :c"), {"c": case_id})
    with pytest.raises(IntegrityError, match="permanent"):
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM case_entries WHERE case_family_id = :c"), {"c": case_id})
    last = db_session.query(CaseEntry).filter(CaseEntry.case_family_id == case_id).order_by(CaseEntry.seq.desc()).first()
    with pytest.raises(IntegrityError, match="next one"):
        with db_session.begin_nested():
            db_session.execute(text(
                "INSERT INTO case_entries (case_family_id, seq, kind, actor_id, at, summary, details, prev_hash, entry_hash) "
                "VALUES (:c, :seq, 'folder_added', :a, now(), 'skipped ahead', '{}', :p, 'x')"),
                {"c": case_id, "seq": last.seq + 2, "a": last.actor_id, "p": last.entry_hash})
    # If someone with the power to switch the rule off changed an entry anyway, the check would show it.
    db_session.execute(text("ALTER TABLE case_entries DISABLE TRIGGER cm_case_entries_permanent"))
    db_session.execute(text("UPDATE case_entries SET summary = 'edited later' WHERE case_family_id = :c AND seq = 3"), {"c": case_id})
    broken = t.lead.get(f"/api/v1/cases/{t.id}/history/check").json()
    assert (broken["intact"], broken["first_problem"]) == (False, 3) and "changed" in broken["problem"]
    # Recomputing the changed entry's own fingerprint doesn't hide it: the entry after it no longer follows it.
    changed = db_session.query(CaseEntry).filter(CaseEntry.case_family_id == case_id, CaseEntry.seq == 3).one()
    db_session.refresh(changed)
    db_session.execute(text("UPDATE case_entries SET entry_hash = :h WHERE case_family_id = :c AND seq = 3"),
                       {"h": case_history._fingerprint(changed), "c": case_id})
    db_session.expire_all()  # the test's own session holds the old row: look again
    hidden = t.lead.get(f"/api/v1/cases/{t.id}/history/check").json()
    assert (hidden["intact"], hidden["first_problem"]) == (False, 4) and "follow" in hidden["problem"]
    # Taking an entry out leaves a gap that is found too.
    db_session.execute(text("DELETE FROM case_entries WHERE case_family_id = :c AND seq = 5"), {"c": case_id})
    db_session.expire_all()
    assert t.lead.get(f"/api/v1/cases/{t.id}/history/check").json()["first_problem"] == 4  # the first problem is still the earlier one


# ---------------------------------------------------------------- the team: added directly by the Investigator


def test_the_investigator_adds_a_sub_investigator_and_an_analyst_directly(cm_client):
    t = make_case(cm_client)
    sub, analyst = cm_client("sub.t", "sub_investigator"), cm_client("ana.t", "analyst")
    other = cm_client("inv.other")
    add_member(analyst, t.id, other.user, status=404)  # they can't even see the case yet
    result = add_member(t.lead, t.id, sub.user, "sub_investigator")  # at once: no invitation, no acceptance, no approval
    assert [(m["user"]["username"], m["role"]) for m in result["team"] if m["revoked_at"] is None] == [("inv.plain", "lead"), ("sub.t", "sub_investigator")]
    add_member(t.lead, t.id, analyst.user, "analyst")
    assert case(sub, t.id)["my_role"] == "sub_investigator" and case(analyst, t.id)["my_role"] == "analyst"  # they see the case at once
    assert "team.added" in notices(sub) and "team.added" in notices(analyst)
    assert [e["kind"] for e in history(t.lead, t.id)][1:3] == ["member_added", "member_added"]
    access = t.lead.get(f"/api/v1/cases/{t.id}/access-history").json()
    assert [(a["user"]["username"], a["change"], a["new_value"]) for a in access][-2:] == [
        ("sub.t", "membership_granted", "sub_investigator"), ("ana.t", "membership_granted", "analyst")]
    # Another Investigator can help too, as a Sub Investigator or an Analyst.
    add_member(t.lead, t.id, other.user, "analyst")
    # The Supervisor adds people as well.
    viewer = cm_client("view.t", "viewer")
    add_member(t.sup, t.id, viewer.user, "viewer")
    # Sub Investigators, Analysts and Viewers don't add people.
    spare = cm_client("spare.t", "sub_investigator")
    for who in (sub, analyst, viewer):
        add_member(who, t.id, spare.user, status=403)


def test_who_can_be_added_and_in_which_part(cm_client, db_session):
    t = make_case(cm_client)
    viewer_acct, analyst_acct, sub_acct = cm_client("view.acct", "viewer"), cm_client("ana.acct", "analyst"), cm_client("sub.acct", "sub_investigator")
    # The account role limits the part.
    add_member(t.lead, t.id, viewer_acct.user, "analyst", status=422)
    add_member(t.lead, t.id, viewer_acct.user, "sub_investigator", status=422)
    add_member(t.lead, t.id, analyst_acct.user, "sub_investigator", status=422)
    add_member(t.lead, t.id, sub_acct.user, "analyst", status=422)
    add_member(t.lead, t.id, sub_acct.user, "lead", status=422)  # the lead is changed by handing the case over
    add_member(t.lead, t.id, t.lead.user, "viewer", status=422)  # nobody adds themselves
    add_member(t.lead, t.id, viewer_acct.user, "viewer")
    add_member(t.lead, t.id, viewer_acct.user, "viewer", status=409)  # already on the team
    # Clearance: the case is restricted.
    junior = cm_client("junior", "analyst", "internal")
    add_member(t.lead, t.id, junior.user, "analyst", status=422)
    # Station: someone at another police station can't be added.
    elsewhere = cm_client("elsewhere", "analyst")
    place(db_session, elsewhere.user, make_station(db_session, "PS-OTHER"))
    add_member(t.lead, t.id, elsewhere.user, "analyst", status=422)
    # Someone who has left the organisation's service (ended account) can't be added.
    ended = cm_client("ended", "analyst")
    ended.user.is_active = False
    db_session.commit()
    add_member(t.lead, t.id, ended.user, "analyst", status=422)


def test_removing_someone_keeps_what_they_did(cm_client):
    t = make_case(cm_client)
    sub = cm_client("sub.r", "sub_investigator")
    add_member(t.lead, t.id, sub.user)
    note = add_note(sub, t.id, title="Written by the Sub Investigator")["file"]
    remove_member(t.lead, t.id, sub.user, reason="x", status=422)  # a reason is needed
    remove_member(sub, t.id, sub.user, status=403)  # nobody changes their own place
    remove_member(t.lead, t.id, t.lead.user, status=403)
    after = remove_member(t.lead, t.id, sub.user)
    gone = next(m for m in after["team"] if m["user"]["username"] == "sub.r")
    assert gone["revoked_at"] is not None and gone["revoked_by"]["username"] == "inv.plain"
    case(sub, t.id, status=404)  # their access ends at once
    assert [f["display_id"] for f in files(t.lead, t.id, folder="investigation-notes")] == [note["display_id"]]  # their note stays
    assert files(t.lead, t.id, folder="investigation-notes")[0]["created_by"]["username"] == "sub.r"  # and stays theirs
    assert [m["role"] for m in team_of(t.lead, t.id) if m["revoked_at"] is None] == ["lead"]
    assert "member_removed" in [e["kind"] for e in history(t.lead, t.id)] and "team.removed" in notices(sub)
    add_member(t.lead, t.id, cm_client("again", "sub_investigator").user)  # someone else can take the place
    add_member(t.lead, t.id, sub.user, "sub_investigator")  # and the same person can be added again


def test_the_supervisor_hands_the_case_to_another_investigator(cm_client):
    t = make_case(cm_client)
    new = cm_client("inv.new")
    analyst = cm_client("ana.lead", "analyst")
    response = t.lead.post(f"/api/v1/cases/{t.id}/lead", json={"user_id": str(new.user.id), "reason": "Wants to keep the case (fictional)"})
    assert response.status_code == 403  # only the supervisor or an administrator decides
    assert t.sup.post(f"/api/v1/cases/{t.id}/lead", json={"user_id": str(analyst.user.id), "reason": "Wrong kind of account (fictional)"}).status_code == 422
    assert t.sup.post(f"/api/v1/cases/{t.id}/lead", json={"user_id": str(t.lead.user.id), "reason": "Already the lead (fictional)"}).status_code == 422
    done = t.sup.post(f"/api/v1/cases/{t.id}/lead", json={"user_id": str(new.user.id), "reason": "Reassigned to a new investigator (fictional)"})
    assert done.status_code == 200 and done.json()["lead"]["username"] == "inv.new"
    roles = {m["user"]["username"]: m["role"] for m in done.json()["team"]}
    assert roles == {"inv.new": "lead", "inv.plain": "sub_investigator"}  # the old lead keeps helping
    assert case(new, t.id)["my_role"] == "lead" and case(t.lead, t.id)["my_role"] == "sub_investigator"
    add_note(new, t.id, title="By the new lead")
    withdraw(t.lead, "artifacts", add_note(new, t.id, title="Another")["file"]["id"], status=403)  # the old lead no longer withdraws
    entry = [e for e in history(new, t.id) if e["kind"] == "lead_changed"]
    assert len(entry) == 1 and entry[0]["details"] == {"from": "inv.plain", "to": "inv.new", "reason": "Reassigned to a new investigator (fictional)"}
    assert "case.assigned" in notices(new)


def test_an_archived_case_is_read_only(cm_client):
    t = make_case(cm_client)
    for value in ("under_investigation", "investigation_completed"):
        set_status(t.lead, t.id, value)
    for value in ("closed", "archived"):
        set_status(t.sup, t.id, value)
    assert case(t.lead, t.id)["workflow_status"] == "archived"
    add_note(t.lead, t.id, status=403)
    sub = cm_client("sub.a", "sub_investigator")
    add_member(t.lead, t.id, sub.user, status=403)
    assert t.lead.post(f"/api/v1/cases/{t.id}/folders", json={"name": "Late folder"}).status_code == 403
    assert case(t.lead, t.id)["can"]["add_files"] is False
    assert set_status(t.sup, t.id, "reopened")["workflow_status"] == "reopened"  # the supervisor can still reopen it
    assert case(t.lead, t.id)["can"]["add_files"] is True  # and the case can be worked on again


def test_a_case_summary_in_the_plain_design_has_no_git_words(cm_client):
    t = make_case(cm_client)
    detail = case(t.lead, t.id)
    assert not {"repositories", "active_workspace", "branches", "commits"} & set(detail)
    for url in (f"/api/v1/cases/{t.id}/repositories", "/api/v1/workspaces/active", f"/api/v1/repositories/{uuid.uuid4()}"):
        assert t.lead.get(url).status_code in (404, 405)  # they no longer exist
