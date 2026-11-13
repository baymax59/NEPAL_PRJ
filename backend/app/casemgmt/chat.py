"""Chat inside a case (docs/case-management/13, section 12): the team group and private messages between two members.

Who: the people on the case's team (any part, as long as they are on it now). Somebody who oversees the case without being on the team is not in
the conversation (add them to the team to include them). Taking a person off the team ends their access to the conversations at once.
What: a message is permanent and attributed, like everything else in a case: it is never edited or deleted. An archived case keeps its
conversations, read-only. Who wrote what, to whom, and when is a record; the audit trail says that a message was sent, never what it said.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.casemgmt.access import membership
from app.casemgmt.enums import WorkflowStatus
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.models import CaseChatRead, CaseFamily, CaseMember, CaseMessage, Notification
from app.casemgmt.notifications import notify
from app.db.models import User

GROUP = "group"
MAX_BODY = 4000
PREVIEW = 90


@dataclass
class Thread:
    """One conversation as one person sees it: the team group, or the private conversation with one other member."""

    key: str  # "group" or the other person's id
    peer: User | None


def require_member(session: Session, user: User, family: CaseFamily) -> CaseMember:
    """The user's place on the team. Anyone else gets 'not found': the conversations are the team's."""
    member = membership(session, user, family)
    if member is None:
        raise NotVisible(exists=True)
    return member


def require_open(family: CaseFamily) -> None:
    if family.workflow_status == WorkflowStatus.ARCHIVED.value:
        raise Forbidden("This case is archived: its record is preserved, so no new messages can be written")


def active_members(session: Session, family: CaseFamily) -> list[User]:
    rows = session.execute(select(User).join(CaseMember, CaseMember.user_id == User.id).where(
        CaseMember.case_family_id == family.id, CaseMember.revoked_at.is_(None)).order_by(User.display_name)).scalars().all()
    return list(rows)


def thread_for(session: Session, user: User, family: CaseFamily, key: str | None) -> Thread:
    """The conversation named by `key` ("group", or the id of another person on the team)."""
    if key in (None, "", GROUP):
        return Thread(GROUP, None)
    try:
        peer_id = uuid.UUID(key)
    except ValueError:
        raise Invalid("Unknown conversation") from None
    peer = session.get(User, peer_id)
    if peer is None or peer.id == user.id or membership(session, peer, family) is None:
        raise Invalid("That person is not on this case's team")
    return Thread(str(peer.id), peer)


def _in_thread(user: User, family: CaseFamily, thread: Thread):
    if thread.peer is None:
        return and_(CaseMessage.case_family_id == family.id, CaseMessage.recipient_id.is_(None))
    return and_(CaseMessage.case_family_id == family.id, or_(
        and_(CaseMessage.sender_id == user.id, CaseMessage.recipient_id == thread.peer.id),
        and_(CaseMessage.sender_id == thread.peer.id, CaseMessage.recipient_id == user.id)))


def _last_read(session: Session, user: User, family: CaseFamily, key: str) -> int:
    row = session.scalar(select(CaseChatRead.last_read_id).where(
        CaseChatRead.user_id == user.id, CaseChatRead.case_family_id == family.id, CaseChatRead.thread == key))
    return row or 0


def _set_read(session: Session, user: User, family: CaseFamily, key: str, up_to: int) -> None:
    row = session.scalar(select(CaseChatRead).where(
        CaseChatRead.user_id == user.id, CaseChatRead.case_family_id == family.id, CaseChatRead.thread == key))
    if row is None:
        session.add(CaseChatRead(user_id=user.id, case_family_id=family.id, thread=key, last_read_id=up_to))
    elif up_to > row.last_read_id:
        row.last_read_id = up_to
    # the notices about this conversation are read too
    session.execute(update(Notification).where(
        Notification.user_id == user.id, Notification.kind == "chat.message", Notification.case_family_id == family.id,
        Notification.read_at.is_(None), Notification.payload["thread"].astext == key).values(read_at=func.now()))


def send(session: Session, user: User, family: CaseFamily, *, to: str | None, body: str) -> CaseMessage:
    """Write a message to the team (`to` empty or "group") or privately to one member."""
    require_member(session, user, family)
    require_open(family)
    text = (body or "").strip()
    if not 1 <= len(text) <= MAX_BODY:
        raise Invalid(f"Write a message of 1 to {MAX_BODY} characters")
    thread = thread_for(session, user, family, to)
    message = CaseMessage(case_family_id=family.id, sender_id=user.id, recipient_id=thread.peer.id if thread.peer else None, body=text)
    session.add(message)
    session.flush()
    _set_read(session, user, family, thread.key if thread.peer is None else str(thread.peer.id), message.id)
    # Told: the other members (group) or the other person (private). One unread notice per conversation, not one per message.
    if thread.peer is None:
        people = [u for u in active_members(session, family) if u.id != user.id]
        key_for = lambda person: GROUP  # noqa: E731
    else:
        people = [thread.peer]
        key_for = lambda person: str(user.id)  # noqa: E731  (for the other person, the conversation is named by the sender)
    preview = text if len(text) <= PREVIEW else text[: PREVIEW - 1] + "…"
    for person in people:
        key = key_for(person)
        waiting = session.scalar(select(Notification.id).where(
            Notification.user_id == person.id, Notification.kind == "chat.message", Notification.case_family_id == family.id,
            Notification.read_at.is_(None), Notification.payload["thread"].astext == key).limit(1))
        if waiting is None:
            notify(session, [person.id], "chat.message", family=family, actor=user, thread=key, group=thread.peer is None, preview=preview)
    session.flush()
    return message


def messages(session: Session, user: User, family: CaseFamily, key: str | None, *, after: int | None = None, limit: int = 60) -> list[CaseMessage]:
    """The messages of one conversation, oldest first: the latest `limit`, or those after message number `after`."""
    require_member(session, user, family)
    thread = thread_for(session, user, family, key)
    query = select(CaseMessage).where(_in_thread(user, family, thread))
    if after is not None:
        return list(session.scalars(query.where(CaseMessage.id > after).order_by(CaseMessage.id).limit(limit)))
    return list(reversed(list(session.scalars(query.order_by(CaseMessage.id.desc()).limit(limit)))))


def mark_read(session: Session, user: User, family: CaseFamily, key: str | None, up_to: int) -> None:
    require_member(session, user, family)
    thread = thread_for(session, user, family, key)
    _set_read(session, user, family, thread.key, up_to)


def threads(session: Session, user: User, family: CaseFamily) -> list[dict]:
    """The team group first, then one conversation for each other member: the latest message and how many are unread."""
    require_member(session, user, family)
    result = []
    for thread in [Thread(GROUP, None)] + [Thread(str(m.id), m) for m in active_members(session, family) if m.id != user.id]:
        where = _in_thread(user, family, thread)
        last = session.scalar(select(CaseMessage).where(where).order_by(CaseMessage.id.desc()).limit(1))
        unread = session.scalar(select(func.count()).select_from(CaseMessage).where(
            where, CaseMessage.sender_id != user.id, CaseMessage.id > _last_read(session, user, family, thread.key))) or 0
        result.append({"thread": thread, "last": last, "unread": unread})
    return result
