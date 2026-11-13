"""No fingerprints or codes in what people read: the text the system writes, and old text shown through `plain`.
All data is fictional."""

import re

from cm_support import PNG, add_member, add_note, create_case, history, set_status, upload, withdraw

from app.casemgmt.plain import plain

LONG_CODE = re.compile(r"\b(?=[0-9]*[a-f])[0-9a-f]{10,}\b", re.IGNORECASE)


def test_plain_replaces_codes_but_keeps_numbers_and_words():
    assert plain("created from c582360566ab") == "created from an earlier update"
    assert plain("merged as " + "ab" * 32) == "merged as an earlier update"
    assert plain("CDR of 7000000042 added") == "CDR of 7000000042 added"  # a 10-digit phone number is not a code
    assert plain("Reviewed the defaced deadline note") == "Reviewed the defaced deadline note"
    assert plain(None) is None and plain("") == ""


def test_the_text_the_system_writes_has_no_codes(cm_client):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    helper = cm_client("inv.meera")
    case_id = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))["case_id"]

    # Everything that writes a line of the case history: notes, files, folders, the team, status changes, reports.
    note = add_note(lead, case_id, title="First steps (fictional)", text="Fictional: the complainant was interviewed.")["file"]
    exhibit = upload(lead, case_id, PNG)["evidence"]
    add_member(lead, case_id, helper.user)
    assert lead.post(f"/api/v1/cases/{case_id}/folders", json={"name": "bank-letters"}).status_code == 201
    withdraw(lead, "artifacts", note["id"], reason="Entered by mistake (fictional)")
    withdraw(lead, "evidence", exhibit["id"], reason="Uploaded by mistake (fictional)")
    set_status(lead, case_id, "under_investigation")
    report = lead.post(f"/api/v1/cases/{case_id}/reports", json={"purpose": "Fictional: progress report for the supervisor."})
    assert report.status_code == 201, report.text

    entries = history(lead, case_id)
    assert {"case_registered", "note_added", "evidence_added", "member_added", "folder_added", "file_withdrawn",
            "status_changed", "report_generated"} <= {e["kind"] for e in entries}
    for entry in entries:
        assert not LONG_CODE.search(entry["summary"]), entry["summary"]
