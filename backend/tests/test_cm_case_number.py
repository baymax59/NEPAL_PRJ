"""The case number (KH-2026-0001) can be changed by whoever oversees the case (docs/case-management/13, section 12, decision 20): the old number
is kept and still finds the case, is never given to another case, and the change is a numbered entry of the history. All names are fictional."""

from types import SimpleNamespace

import pytest
from cm_support import add_member, case, create_case, history, set_status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

NUMBER = "/api/v1/cases/{}/number"


def make(cm_client) -> SimpleNamespace:
    sup = cm_client("sup.num", "supervisor", "confidential")
    lead = cm_client("inv.num")
    created = create_case(sup, lead_investigator_id=str(lead.user.id), supervisor_id=str(sup.user.id))
    return SimpleNamespace(sup=sup, lead=lead, id=created["case_id"], number=created["display_id"])


def rename(client, case_id, number, reason="The station's own file number (fictional)", status=200) -> dict:
    response = client.post(NUMBER.format(case_id), json={"number": number, "reason": reason})
    assert response.status_code == status, response.text
    return response.json()


def listed(client, q) -> list[str]:
    response = client.get("/api/v1/cases", params={"q": q})
    assert response.status_code == 200, response.text
    return [c["display_id"] for c in response.json()["items"]]


def test_the_supervisor_changes_the_number_and_the_old_one_still_finds_the_case(cm_client):
    t = make(cm_client)
    before = len(history(t.lead, t.id))
    detail = rename(t.sup, t.id, "PS-CYB-2026/14")
    assert detail["display_id"] == "PS-CYB-2026/14"
    assert [(p["old_number"], p["new_number"], p["reason"]) for p in detail["previous_numbers"]] == [(t.number, "PS-CYB-2026/14", "The station's own file number (fictional)")]
    assert detail["previous_numbers"][0]["changed_by"]["id"] == str(t.sup.user.id)
    assert case(t.lead, t.id)["display_id"] == "PS-CYB-2026/14" and case(t.lead, t.id)["previous_numbers"][0]["old_number"] == t.number
    # the history keeps one more numbered entry, with who and why; the old entries still name the old number
    entries = history(t.lead, t.id)
    assert len(entries) == before + 1 and entries[-1]["kind"] == "case_renumbered"
    assert entries[-1]["details"] == {"old": t.number, "new": "PS-CYB-2026/14", "reason": "The station's own file number (fictional)"}
    assert t.number in entries[0]["summary"]
    # both numbers find the case
    assert listed(t.lead, "CYB-2026/14") == ["PS-CYB-2026/14"]
    assert listed(t.lead, t.number) == ["PS-CYB-2026/14"]
    # and the number can be changed again
    again = rename(t.sup, t.id, "PS-CYB-2026/14A")
    assert [p["new_number"] for p in again["previous_numbers"]] == ["PS-CYB-2026/14", "PS-CYB-2026/14A"]


def test_only_those_who_oversee_the_case_may_change_the_number(cm_client):
    t = make(cm_client)
    sub, analyst, viewer = (cm_client(name, role) for name, role in (("sub.num", "sub_investigator"), ("ana.num", "analyst"), ("view.num", "viewer")))
    for member, role in ((sub, "sub_investigator"), (analyst, "analyst"), (viewer, "viewer")):
        add_member(t.lead, t.id, member.user, role)
    for person in (t.lead, sub, analyst, viewer):
        rename(person, t.id, "MY-OWN-1", status=403)
        assert case(person, t.id)["can"]["rename_case"] is False
    assert case(t.sup, t.id)["can"]["rename_case"] is True
    admin = cm_client("admin.num", "super_admin", "confidential")
    assert rename(admin, t.id, "BY-ADMIN-1")["display_id"] == "BY-ADMIN-1"
    assert case(t.sup, t.id)["display_id"] == "BY-ADMIN-1"


def test_a_number_must_be_well_formed_unused_and_never_one_the_system_hands_out(cm_client):
    t = make(cm_client)
    other = create_case(t.sup, lead_investigator_id=str(t.lead.user.id), supervisor_id=str(t.sup.user.id))
    for bad in ("ab", "x" * 33, "<script>1", "-leading", "has;semicolon"):
        rename(t.sup, t.id, bad, status=422)
    rename(t.sup, t.id, "OK-1", reason="no", status=422)  # a reason is needed
    rename(t.sup, t.id, t.number.lower(), status=422)  # it already is this case's number
    rename(t.sup, t.id, other["display_id"], status=409)  # another case has it
    rename(t.sup, t.id, other["display_id"].lower(), status=409)  # whatever the letter case
    system_like = other["display_id"].rsplit("-", 1)[0] + "-9999"
    rename(t.sup, t.id, system_like, status=422)  # the system's own pattern is kept for new cases
    # a number this case gave up is not given to another case
    rename(t.sup, t.id, "FREED-1")
    rename(t.sup, other["case_id"], t.number, status=409)  # the number the first case gave up stays its own
    rename(t.sup, other["case_id"], "FREED-1", status=409)
    # but the case may return to its own first number
    assert rename(t.sup, t.id, t.number)["display_id"] == t.number
    # a new case still gets the next number of the system, with no clash
    third = create_case(t.sup, lead_investigator_id=str(t.lead.user.id), supervisor_id=str(t.sup.user.id))
    assert third["display_id"] not in (t.number, other["display_id"])


def test_a_number_given_up_by_one_case_is_never_taken_by_another(cm_client):
    t = make(cm_client)
    other = create_case(t.sup, lead_investigator_id=str(t.lead.user.id), supervisor_id=str(t.sup.user.id))
    rename(t.sup, t.id, "CUSTOM-1")
    rename(t.sup, other["case_id"], "CUSTOM-2")
    rename(t.sup, other["case_id"], "CUSTOM-1", status=409)  # in use
    rename(t.sup, t.id, "CUSTOM-3")
    rename(t.sup, other["case_id"], "CUSTOM-1", status=409)  # was this case's number before


def test_an_archived_case_keeps_its_number(cm_client):
    t = make(cm_client)
    for value in ("under_investigation", "investigation_completed"):
        set_status(t.lead, t.id, value)
    for value in ("closed", "archived"):
        set_status(t.sup, t.id, value)
    rename(t.sup, t.id, "TOO-LATE-1", status=403)
    assert case(t.sup, t.id)["can"]["rename_case"] is False


def test_the_database_keeps_the_record_of_number_changes_and_guards_everything_else(cm_client, db_session):
    t = make(cm_client)
    rename(t.sup, t.id, "DBTEST-1")
    with pytest.raises(DBAPIError):  # the record of a change can't be edited
        with db_session.begin_nested():
            db_session.execute(text("UPDATE case_number_changes SET old_number = 'X-FORGED'"))
    with pytest.raises(DBAPIError):  # or deleted
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM case_number_changes"))
    with pytest.raises(DBAPIError):  # the case's title is still protected: only the statuses, the supervisor and the number may change
        with db_session.begin_nested():
            db_session.execute(text("UPDATE case_families SET title = 'Rewritten'"))
    with db_session.begin_nested():
        db_session.execute(text("UPDATE case_families SET display_id = 'DIRECT-1' WHERE display_id = 'DBTEST-1'"))
