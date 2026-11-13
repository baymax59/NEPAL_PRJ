"""Chat inside a case (docs/case-management/13-plain-case-design.md, section 12): the team group and private messages between two members of the team.
Only people on the team; permanent messages; unread counts and notices; read-only once the case is archived. All names are fictional."""

from types import SimpleNamespace

import pytest
from cm_support import add_member, case, create_case, notices, remove_member, set_status
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.casemgmt.models import Notification
from app.db.models import AuditEvent


def chat_team(cm_client) -> SimpleNamespace:
    """A case with its lead, a Sub Investigator, an Analyst and a Viewer on the team, and a Supervisor who oversees it without being on the team."""
    sup = cm_client("chat.sup", "supervisor", "confidential")
    lead, sub, analyst, viewer = (cm_client(n) for n in ("chat.lead", "chat.sub", "chat.analyst", "chat.viewer"))
    outsider = cm_client("chat.outsider", "investigator")
    created = create_case(sup, lead_investigator_id=str(lead.user.id), supervisor_id=str(sup.user.id))
    case_id = created["case_id"]
    add_member(lead, case_id, sub.user, "sub_investigator")
    add_member(lead, case_id, analyst.user, "analyst")
    add_member(lead, case_id, viewer.user, "viewer")
    return SimpleNamespace(sup=sup, lead=lead, sub=sub, analyst=analyst, viewer=viewer, outsider=outsider, id=case_id)


def say(client, case_id, body, to=None, status=201) -> dict:
    payload = {"body": body} | ({"to": str(to.user.id) if hasattr(to, "user") else to} if to is not None else {})
    response = client.post(f"/api/v1/cases/{case_id}/chat/messages", json=payload)
    assert response.status_code == status, response.text
    return response.json()


def read(client, case_id, with_="group", status=200, **params) -> list[dict]:
    response = client.get(f"/api/v1/cases/{case_id}/chat/messages", params={"with": with_, **params})
    assert response.status_code == status, response.text
    return response.json()["messages"] if status == 200 else response.json()


def threads(client, case_id, status=200):
    response = client.get(f"/api/v1/cases/{case_id}/chat/threads")
    assert response.status_code == status, response.text
    return response.json()


def thread(client, case_id, key) -> dict:
    return next(t for t in threads(client, case_id) if t["key"] == key)


def test_the_people_on_the_team_write_to_the_whole_team(cm_client):
    t = chat_team(cm_client)
    first = say(t.lead, t.id, "  Meet at the station at nine to go over the CDR (fictional).  ")
    assert first["mine"] is True and first["to"] is None and first["body"] == "Meet at the station at nine to go over the CDR (fictional)."
    say(t.analyst, t.id, "I will bring the call chart (fictional).")
    for member in (t.lead, t.sub, t.analyst, t.viewer):  # the Viewer is on the team too
        seen = read(member, t.id)
        assert [m["body"][:12] for m in seen] == ["Meet at the ", "I will bring"]
        assert [m["sender"]["username"] for m in seen] == ["chat.lead", "chat.analyst"]
    assert [m["mine"] for m in read(t.analyst, t.id)] == [False, True]  # "mine" is for the person who is looking


def test_a_private_message_is_seen_only_by_the_two_people(cm_client):
    t = chat_team(cm_client)
    say(t.sub, t.id, "Can you check the IPDR dates before the supervisor reads them? (fictional)", to=t.analyst)
    key_sub, key_analyst = str(t.sub.user.id), str(t.analyst.user.id)
    assert [m["body"][:12] for m in read(t.analyst, t.id, key_sub)] == ["Can you chec"]
    assert [m["body"][:12] for m in read(t.sub, t.id, key_analyst)] == ["Can you chec"]
    # nobody else sees it: not in the group, not in their own conversations with either of the two, not the lead, not the Supervisor who oversees the case
    assert read(t.lead, t.id) == [] and read(t.lead, t.id, key_sub) == [] and read(t.lead, t.id, key_analyst) == []
    assert read(t.viewer, t.id, key_sub) == [] and read(t.viewer, t.id) == []
    assert all(x["last"] is None for x in threads(t.lead, t.id))
    # and it is not in the team group either, for the two people themselves
    assert read(t.sub, t.id) == [] and read(t.analyst, t.id) == []


def test_the_threads_list_the_group_and_each_other_member_with_unread_counts(cm_client):
    t = chat_team(cm_client)
    mine = threads(t.sub, t.id)
    assert [x["kind"] for x in mine] == ["group", "direct", "direct", "direct"]  # the team, and each of the other three
    assert mine[0]["title"] == "The team" and {x["peer"]["username"] for x in mine[1:]} == {"chat.lead", "chat.analyst", "chat.viewer"}
    say(t.lead, t.id, "Group message one (fictional)")
    say(t.lead, t.id, "Group message two (fictional)")
    say(t.lead, t.id, "Just for you (fictional)", to=t.sub)
    assert thread(t.sub, t.id, "group")["unread"] == 2 and thread(t.sub, t.id, str(t.lead.user.id))["unread"] == 1
    assert thread(t.lead, t.id, "group")["unread"] == 0  # your own messages are never unread
    assert thread(t.analyst, t.id, "group")["unread"] == 2 and thread(t.analyst, t.id, str(t.lead.user.id))["unread"] == 0
    last = thread(t.sub, t.id, "group")["last"]
    assert last["preview"] == "Group message two (fictional)" and last["sender"]["username"] == "chat.lead"

    newest = read(t.sub, t.id)[-1]["id"]
    assert t.sub.post(f"/api/v1/cases/{t.id}/chat/read", json={"thread": "group", "up_to": newest}).status_code == 204
    assert thread(t.sub, t.id, "group")["unread"] == 0 and thread(t.sub, t.id, str(t.lead.user.id))["unread"] == 1  # only that conversation
    say(t.lead, t.id, "Group message three (fictional)")
    assert thread(t.sub, t.id, "group")["unread"] == 1


def test_a_page_can_ask_only_for_what_is_new(cm_client):
    t = chat_team(cm_client)
    ids = [say(t.lead, t.id, f"Message {n} (fictional)")["id"] for n in range(1, 6)]
    assert [m["id"] for m in read(t.sub, t.id, after=ids[2])] == ids[3:]
    assert [m["id"] for m in read(t.sub, t.id, limit=2)] == ids[3:]  # the latest two, oldest first
    assert read(t.sub, t.id, after=ids[-1]) == []


def test_only_people_on_the_team_can_take_part_and_leaving_the_team_ends_it(cm_client):
    t = chat_team(cm_client)
    say(t.lead, t.id, "Team only (fictional)")
    for outsider in (t.sup, t.outsider):  # a Supervisor who oversees the case, and somebody with no part in it: both get "not found"
        assert outsider.get(f"/api/v1/cases/{t.id}/chat/threads").status_code == 404
        assert outsider.get(f"/api/v1/cases/{t.id}/chat/messages").status_code == 404
        assert outsider.post(f"/api/v1/cases/{t.id}/chat/messages", json={"body": "Let me in (fictional)"}).status_code == 404
    assert read(t.lead, t.id)[-1]["body"] == "Team only (fictional)"

    remove_member(t.lead, t.id, t.viewer.user)  # taken off the team: the conversations are closed to them at once
    assert t.viewer.get(f"/api/v1/cases/{t.id}/chat/threads").status_code == 404
    assert t.viewer.get(f"/api/v1/cases/{t.id}/chat/messages").status_code == 404
    assert str(t.viewer.user.id) not in [x["key"] for x in threads(t.lead, t.id)]  # and they are no longer offered to the others
    say(t.lead, t.id, "Private to somebody who left (fictional)", to=str(t.viewer.user.id), status=422)
    assert "not on this case's team" in say(t.lead, t.id, "x y z", to=str(t.viewer.user.id), status=422)["detail"]


def test_what_may_be_written_and_to_whom(cm_client):
    t = chat_team(cm_client)
    for empty in ("", "   ", "\n\t "):
        say(t.lead, t.id, empty, status=422)
    say(t.lead, t.id, "x" * 4001, status=422)
    assert say(t.lead, t.id, "x" * 4000)["body"] == "x" * 4000
    say(t.lead, t.id, "To myself (fictional)", to=t.lead, status=422)
    say(t.lead, t.id, "To a stranger (fictional)", to=t.outsider, status=422)
    say(t.lead, t.id, "To nobody known (fictional)", to="not-an-id", status=422)
    assert t.lead.post(f"/api/v1/cases/{t.id}/chat/messages", json={"body": "Hello (fictional)", "sender_id": "x"}).status_code == 422  # nothing else is accepted
    read(t.lead, t.id, "not-an-id", status=422)


def test_a_message_is_permanent(cm_client, db_session):
    t = chat_team(cm_client)
    sent = say(t.lead, t.id, "What was written stays (fictional)")
    base = f"/api/v1/cases/{t.id}/chat/messages"
    for method in ("PUT", "PATCH", "DELETE"):  # the API has nothing to change or remove a message: refused
        assert t.lead.request(method, f"{base}/{sent['id']}").status_code == 405
        assert t.lead.request(method, base, json={"body": "rewritten"}).status_code == 405
    for sql in (f"UPDATE case_messages SET body = 'rewritten' WHERE id = {sent['id']}", f"DELETE FROM case_messages WHERE id = {sent['id']}"):
        with pytest.raises(DBAPIError):  # and the database refuses it too
            db_session.execute(text(sql))
        db_session.rollback()
    assert read(t.lead, t.id)[-1]["body"] == "What was written stays (fictional)"


def test_an_archived_case_keeps_its_conversations_read_only(cm_client):
    t = chat_team(cm_client)
    say(t.lead, t.id, "Before the case was closed (fictional)")
    assert case(t.lead, t.id)["can"]["chat"] is True and case(t.lead, t.id)["can"]["write_chat"] is True
    assert case(t.sup, t.id)["can"]["chat"] is False  # oversees, but is not on the team
    for step in ("open", "closed", "archived"):  # a case is archived after it is closed
        set_status(t.sup, t.id, step)
    detail = case(t.lead, t.id)
    assert detail["can"]["chat"] is True and detail["can"]["write_chat"] is False
    assert "archived" in say(t.lead, t.id, "After (fictional)", status=403)["detail"]
    assert read(t.analyst, t.id)[0]["body"] == "Before the case was closed (fictional)"  # still readable


def test_the_team_is_told_once_per_conversation_and_reading_clears_the_notice(cm_client, db_session):
    t = chat_team(cm_client)
    say(t.lead, t.id, "First (fictional)")
    say(t.lead, t.id, "Second (fictional)")  # a second message does not add a second unread notice
    say(t.lead, t.id, "Only for the analyst (fictional)", to=t.analyst)
    assert notices(t.sub).count("chat.message") == 1 and notices(t.viewer).count("chat.message") == 1
    assert notices(t.lead).count("chat.message") == 0  # never the writer
    assert notices(t.analyst).count("chat.message") == 2  # the group, and the private one: two conversations
    private = db_session.scalar(select(Notification).where(Notification.payload["thread"].astext == str(t.lead.user.id)))
    assert private.payload["preview"] == "Only for the analyst (fictional)" and private.payload["group"] is False

    t.sub.post(f"/api/v1/cases/{t.id}/chat/read", json={"thread": "group", "up_to": read(t.sub, t.id)[-1]["id"]})
    assert [n for n in t.sub.get("/api/v1/notifications").json()["items"] if n["kind"] == "chat.message"][0]["read_at"] is not None
    say(t.lead, t.id, "Third (fictional)")  # after reading, the next message tells them again
    assert [n["read_at"] for n in t.sub.get("/api/v1/notifications").json()["items"] if n["kind"] == "chat.message"].count(None) == 1


def test_the_audit_trail_says_that_a_message_was_sent_never_what_it_said(cm_client, db_session):
    t = chat_team(cm_client)
    secret = "The informant's name is a fictional secret"
    say(t.lead, t.id, secret)
    say(t.lead, t.id, secret + " (private)", to=t.sub)
    say(t.outsider, t.id, "Let me in (fictional)", status=404)
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.chat.sent").order_by(AuditEvent.id)).all()
    assert [(e.outcome, (e.details or {}).get("thread")) for e in events] == [("success", "team"), ("success", "private"), ("denied", None)]
    assert "secret" not in str([e.details for e in events])
