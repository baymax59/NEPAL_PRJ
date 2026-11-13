"""Chain of custody (docs/case-management/04 §4 and 07 §3).

Every exhibit's custody is a list of events that only grows: collected, ingested, transferred, acknowledged
or declined, accessed, verified, sealed, unsealed (and exported, with reports in CM-7).

- The officer who adds an exhibit is its first custodian.
- A transfer to a colleague is **pending** until the receiver acknowledges it; acknowledging re-checks the
  file's fingerprint, so the receiver confirms they received it intact. Until then the sender stays custodian.
- A transfer to a body outside the system (a forensic laboratory, a court) needs a receipt reference and is
  complete when recorded. Bringing it back is recorded by the supervisor, as a transfer to an officer.
- Corrections are new events; nothing is edited or removed.
"""

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import engine
from app.casemgmt.access import supervises
from app.casemgmt.enums import CustodyEventType as E
from app.casemgmt.enums import IntegrityTrigger
from app.casemgmt.errors import Conflict, Forbidden, Invalid, NotVisible
from app.casemgmt.evidence import Seen, check_object, custody_event, get_evidence, moment
from app.casemgmt.models import CustodyEvent, IntegrityCheck
from app.casemgmt.notifications import notify
from app.casemgmt.storage import EvidenceStore
from app.db.models import User


@dataclass
class CustodyState:
    custodian_id: uuid.UUID | None = None
    custodian_name: str | None = None  # a body outside the system
    pending: CustodyEvent | None = None  # a transfer waiting for its receiver
    events: list[CustodyEvent] = field(default_factory=list)


def fold(events: list[CustodyEvent]) -> CustodyState:
    """Who holds the exhibit now, and whether a transfer is waiting, from its events (oldest first)."""
    state = CustodyState(events=events)
    for event in events:
        if event.event_type == E.INGESTED:
            state.custodian_id, state.custodian_name = event.to_custodian_id, None
        elif event.event_type == E.TRANSFERRED:
            if event.to_custodian_id is None:  # to an outside body: complete with its receipt
                state.custodian_id, state.custodian_name = None, event.to_custodian_name
            else:
                state.pending = event
        elif event.event_type == E.ACKNOWLEDGED and state.pending and event.related_event_id == state.pending.id:
            state.custodian_id, state.custodian_name, state.pending = state.pending.to_custodian_id, None, None
        elif event.event_type == E.DECLINED and state.pending and event.related_event_id == state.pending.id:
            state.pending = None
    return state


def states(session: Session, item_ids) -> dict[uuid.UUID, CustodyState]:
    grouped: dict[uuid.UUID, list[CustodyEvent]] = defaultdict(list)
    for event in session.scalars(select(CustodyEvent).where(CustodyEvent.evidence_item_id.in_(list(item_ids))).order_by(CustodyEvent.id)):
        grouped[event.evidence_item_id].append(event)
    return {item_id: fold(grouped.get(item_id, [])) for item_id in item_ids}


def state(session: Session, seen: Seen) -> CustodyState:
    return states(session, [seen.item.id])[seen.item.id]


def _text(value: str | None, what: str, low: int, high: int) -> str:
    value = (value or "").strip()
    if not low <= len(value) <= high:
        raise Invalid(f"{what} must be {low} to {high:,} characters")
    return value


def transfer(session: Session, actor: User, seen: Seen, *, to_user_id=None, to_external: str | None = None,
             reason: str | None, method: str | None = None, authorization_ref: str | None = None,
             receipt_reference: str | None = None, occurred_at: dt.datetime | None = None) -> CustodyEvent:
    engine._lock_family(session, seen.family.id)
    current = state(session, seen)
    if current.pending is not None:
        raise Conflict("A transfer of this exhibit is waiting for its receiver to acknowledge it",
                       pending_transfer=current.pending.id)
    if not (current.custodian_id == actor.id or supervises(actor, seen.family)):
        raise Forbidden("Only the exhibit's current custodian, the supervisor or an administrator can transfer it")
    if (to_user_id is None) == (to_external is None):
        raise Invalid("Give either the officer receiving the exhibit (to_user_id) or the outside body (to_external)")
    reason = _text(reason, "The reason", 5, 1000)
    when, tz = moment(occurred_at, "occurred_at")
    details = {}
    if to_user_id is not None:
        receiver = session.get(User, to_user_id)
        if receiver is None or not receiver.is_active or receiver.organization_id != seen.family.organization_id:
            raise Invalid("The receiver must be an active user of your organisation")
        if receiver.id == current.custodian_id:
            raise Invalid("The receiver already holds this exhibit")
        try:
            get_evidence(session, receiver, seen.item.id)
        except NotVisible:
            raise Invalid("The receiver can't see this exhibit: add them to the case first") from None
        to = {"to_custodian_id": receiver.id}
    else:
        to = {"to_custodian_name": _text(to_external, "The outside body's name", 3, 200)}
        details["receipt_reference"] = _text(receipt_reference, "A receipt reference (for an outside body)", 3, 200)
    event = custody_event(session, seen, E.TRANSFERRED, actor, occurred_at=when, occurred_tz=tz,
                          from_custodian_id=current.custodian_id, from_custodian_name=current.custodian_name,
                          reason=reason, method=(method or "").strip()[:100] or None,
                          authorization_ref=(authorization_ref or "").strip()[:200] or None, details=details, **to)
    if event.to_custodian_id:  # the receiver is told a transfer is waiting for their acknowledgement
        notify(session, [event.to_custodian_id], "custody.transfer_pending", family=seen.family, actor=actor,
               evidence={"id": str(seen.item.id), "display_id": seen.item.display_id}, transfer=event.id)
    return event


def _pending(session: Session, seen: Seen, transfer_event_id: int | None) -> CustodyEvent:
    pending = state(session, seen).pending
    if pending is None or pending.id != transfer_event_id:
        raise Invalid("There is no pending transfer with that number for this exhibit")
    return pending


def acknowledge(session: Session, actor: User, seen: Seen, store: EvidenceStore, *, transfer_event_id: int | None,
                reason: str | None = None) -> tuple[CustodyEvent, IntegrityCheck]:
    """The receiver confirms the exhibit arrived. The file's fingerprint is checked and recorded at that moment."""
    engine._lock_family(session, seen.family.id)
    pending = _pending(session, seen, transfer_event_id)
    if pending.to_custodian_id != actor.id:
        raise Forbidden("Only the officer receiving the exhibit can acknowledge the transfer")
    check = check_object(session, store, seen.obj, actor=actor, trigger=IntegrityTrigger.ACKNOWLEDGEMENT, item_id=seen.item.id)
    event = custody_event(session, seen, E.ACKNOWLEDGED, actor, from_custodian_id=pending.from_custodian_id,
                          from_custodian_name=pending.from_custodian_name, to_custodian_id=actor.id,
                          related_event_id=pending.id, verification_sha256=check.computed_sha256,
                          reason=(reason or "").strip()[:1000] or "Received", details={"integrity": check.result})
    return event, check


def decline(session: Session, actor: User, seen: Seen, *, transfer_event_id: int | None, reason: str | None) -> CustodyEvent:
    """A pending transfer that won't happen: refused by the receiver, or withdrawn by the sender or supervisor."""
    engine._lock_family(session, seen.family.id)
    pending = _pending(session, seen, transfer_event_id)
    if actor.id == pending.to_custodian_id:
        by = "receiver"
    elif actor.id == pending.actor_id or supervises(actor, seen.family):
        by = "sender"
    else:
        raise Forbidden("Only the receiver, the sender or the supervisor can decline this transfer")
    return custody_event(session, seen, E.DECLINED, actor, related_event_id=pending.id,
                         from_custodian_id=pending.from_custodian_id, from_custodian_name=pending.from_custodian_name,
                         to_custodian_id=pending.to_custodian_id, reason=_text(reason, "The reason", 5, 1000),
                         details={"declined_by": by})


def record_access(session: Session, actor: User, seen: Seen, *, method: str, verification_sha256: str | None = None,
                  token_id: str | None = None) -> CustodyEvent:
    """Someone opened the exhibit's content (a download or a preview)."""
    return custody_event(session, seen, E.ACCESSED, actor, method=method, verification_sha256=verification_sha256,
                         token_id=token_id)
