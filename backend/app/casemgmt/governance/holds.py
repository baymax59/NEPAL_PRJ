"""Legal holds (phase CM-7, docs/case-management/07 §6).

A legal hold records an order or instruction to preserve a case. While a hold is active:
- the case can't be set to "archived";
- no retention decision to archive, transfer or dispose of it can be proposed or approved.
Nothing in Knight Hawk is ever deleted anyway; a hold makes the obligation explicit and blocks the formal decisions.

Holds are placed and released by the case's supervisor or a platform administrator, with a reason (and two-step
verification when required). A hold is never removed: it is released, and both stay in its history.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.mfa import require_strong_auth
from app.casemgmt import queries
from app.casemgmt.access import family_condition, supervises
from app.casemgmt.enums import MemberRole
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.models import CaseFamily, CaseMember, LegalHold
from app.casemgmt.notifications import notify
from app.db.models import User


def _text(value: str | None, what: str, low: int, high: int) -> str:
    value = (value or "").strip()
    if not low <= len(value) <= high:
        raise Invalid(f"{what}: {low} to {high:,} characters")
    return value


def active(session: Session, family_id) -> list[LegalHold]:
    return list(session.scalars(select(LegalHold).where(LegalHold.case_family_id == family_id, LegalHold.released_at.is_(None))
                                .order_by(LegalHold.placed_at)))


def on_hold(session: Session, family_id) -> bool:
    return session.scalar(select(LegalHold.id).where(LegalHold.case_family_id == family_id, LegalHold.released_at.is_(None)).limit(1)) is not None


def ensure_not_held(session: Session, family: CaseFamily, what: str) -> None:
    if on_hold(session, family.id):
        raise Forbidden(f"{family.display_id} is under a legal hold: {what} is not allowed until the hold is released")


def _people_to_tell(session: Session, family: CaseFamily) -> list:
    leads = list(session.scalars(select(CaseMember.user_id).where(
        CaseMember.case_family_id == family.id, CaseMember.revoked_at.is_(None), CaseMember.role == MemberRole.LEAD.value)))
    return [*leads, family.supervisor_id]


def place(session: Session, actor: User, family: CaseFamily, *, reason: str, authority_ref: str | None = None) -> LegalHold:
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can place a legal hold")
    require_strong_auth(actor, "placing a legal hold")
    hold = LegalHold(organization_id=family.organization_id, case_family_id=family.id, reason=_text(reason, "The reason", 10, 2000),
                     authority_ref=(authority_ref or "").strip()[:300] or None, placed_by=actor.id)
    session.add(hold)
    session.flush()
    notify(session, _people_to_tell(session, family), "legal_hold.placed", family=family, actor=actor)
    return hold


def get_hold(session: Session, actor: User, hold_id) -> tuple[LegalHold, CaseFamily]:
    hold = session.get(LegalHold, hold_id)
    family = session.get(CaseFamily, hold.case_family_id) if hold else None
    if hold is None or not supervises(actor, family):
        raise NotVisible(exists=hold is not None)
    return hold, family


def release(session: Session, actor: User, hold: LegalHold, family: CaseFamily, *, reason: str) -> LegalHold:
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can release a legal hold")
    require_strong_auth(actor, "releasing a legal hold")
    if hold.released_at is not None:
        raise Invalid("This legal hold was already released")
    hold.released_by, hold.released_at = actor.id, dt.datetime.now(dt.UTC)
    hold.release_reason = _text(reason, "The reason", 10, 2000)
    session.flush()
    notify(session, _people_to_tell(session, family), "legal_hold.released", family=family, actor=actor)
    return hold


def view(hold: LegalHold, who: dict) -> dict:
    return {"id": hold.id, "reason": hold.reason, "authority_ref": hold.authority_ref, "placed_by": who.get(hold.placed_by),
            "placed_at": hold.placed_at, "released_by": who.get(hold.released_by), "released_at": hold.released_at,
            "release_reason": hold.release_reason, "active": hold.released_at is None}


def for_case(session: Session, family: CaseFamily) -> list[dict]:
    holds = list(session.scalars(select(LegalHold).where(LegalHold.case_family_id == family.id).order_by(LegalHold.placed_at.desc())))
    who = queries.people(session, [h.placed_by for h in holds] + [h.released_by for h in holds])
    return [view(h, who) for h in holds]


def all_active(session: Session, admin: User) -> list[dict]:
    """Every active hold in the organisation, with its case (platform administrators)."""
    rows = list(session.execute(select(LegalHold, CaseFamily).join(CaseFamily, CaseFamily.id == LegalHold.case_family_id)
                                .where(LegalHold.released_at.is_(None), family_condition(admin)).order_by(LegalHold.placed_at.desc())))
    who = queries.people(session, [h.placed_by for h, _ in rows])
    return [{**view(h, who), "case": queries.case_ref(f)} for h, f in rows]
