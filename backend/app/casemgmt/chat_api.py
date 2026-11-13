"""Chat inside a case under /api/v1/cases/{id}/chat (docs/case-management/13, section 12): the team group and private messages.

Only people on the case's team; anyone else gets 404. A message is permanent: there is no way to edit or delete one (the same rules as the rest of the
module: deletions are refused). Writing is audited (that a message was sent, never what it said); reading is not, because the screens ask every few
seconds. Included before the module's main router, whose catch-all answers 405 to deletions on these paths too.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.auth.dependencies import CurrentUser
from app.casemgmt import chat
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family
from app.casemgmt.api import Audit, Audited, DbSession
from app.casemgmt.models import CaseMessage
from app.casemgmt.queries import people
from app.db.models import User

router = APIRouter(prefix="/v1", tags=["case management: chat"])


def _out(db, user: User, rows: list[CaseMessage]) -> list[dict]:
    who = people(db, {i for m in rows for i in (m.sender_id, m.recipient_id)})
    return [{"id": m.id, "sender": who[m.sender_id], "to": who.get(m.recipient_id), "body": m.body, "at": m.created_at, "mine": m.sender_id == user.id}
            for m in rows]


@router.get("/cases/{case_id}/chat/threads", response_model=list[s.ChatThread])
def chat_threads(case_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict]:
    """The conversations of this case as you see them: the team group, and one with each other member (latest message, unread count)."""
    family = get_family(db, user, case_id)
    found = chat.threads(db, user, family)
    who = people(db, {i for f in found for i in ([f["thread"].peer.id] if f["thread"].peer else []) + ([f["last"].sender_id] if f["last"] else [])})
    result = []
    for f in found:
        thread, last = f["thread"], f["last"]
        result.append({
            "key": thread.key, "kind": "group" if thread.peer is None else "direct",
            "title": "The team" if thread.peer is None else thread.peer.display_name,
            "peer": who.get(thread.peer.id) if thread.peer else None,
            "last": {"id": last.id, "sender": who[last.sender_id], "preview": last.body if len(last.body) <= chat.PREVIEW else last.body[: chat.PREVIEW - 1] + "…",
                     "at": last.created_at} if last else None,
            "unread": f["unread"]})
    return result


@router.get("/cases/{case_id}/chat/messages", response_model=s.ChatMessages)
def chat_messages(case_id: uuid.UUID, user: CurrentUser, db: DbSession,
                  thread: Annotated[str, Query(alias="with", max_length=40)] = chat.GROUP,
                  after: Annotated[int | None, Query(ge=0)] = None, limit: Annotated[int, Query(ge=1, le=200)] = 60) -> dict:
    """The messages of one conversation, oldest first: the latest ones, or (with `after`) those written since message number `after`."""
    family = get_family(db, user, case_id)
    rows = chat.messages(db, user, family, thread, after=after, limit=limit)
    return {"thread": thread, "messages": _out(db, user, rows)}


@router.post("/cases/{case_id}/chat/messages", response_model=s.ChatMessageOut, status_code=status.HTTP_201_CREATED)
def chat_send(case_id: uuid.UUID, body: s.ChatMessageIn, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Write to the team, or privately to one member. Permanent."""
    with Audited(db, audit, user, "cm.chat.sent", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        message = chat.send(db, user, family, to=body.to, body=body.body)
        event.write(thread="team" if message.recipient_id is None else "private", length=len(message.body))
        result = _out(db, user, [message])[0]
    return result


@router.post("/cases/{case_id}/chat/read", status_code=status.HTTP_204_NO_CONTENT)
def chat_read(case_id: uuid.UUID, body: s.ChatReadIn, user: CurrentUser, db: DbSession) -> None:
    """Say how far you have read a conversation (for the unread counts; also clears its notice)."""
    family = get_family(db, user, case_id)
    chat.mark_read(db, user, family, body.thread, body.up_to)
    db.commit()
