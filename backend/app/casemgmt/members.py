"""The team of a case: who is on it, in which part (docs/case-management/13-plain-case-design.md §3).

- The Investigator who leads the case, its Supervisor, an Administrator of its station or the Super Admin adds a person **directly**:
  there is no invitation to accept and no approval step. The person must be an active user of the same organisation who works at the
  case's police station, with enough clearance, and whose account role allows the part: a Viewer account only Viewer; an Analyst
  account Analyst or Viewer; a Sub Investigator account Sub Investigator or Viewer; an Investigator account (or above) Sub
  Investigator, Analyst or Viewer. Nobody adds themselves, and the lead part is never given this way (see `change_lead`).
- Removing someone needs a reason. Everything they did stays attributed to them, and the change is a permanent access-history record.
- Handing the case to another Investigator is the Supervisor's (or an Administrator's) decision, with a reason; the old lead stays on
  the team as a Sub Investigator.
Each change is also an entry of the case's history and a notice to the person.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.auth.mfa import require_strong_auth
from app.casemgmt import engine, history
from app.casemgmt.access import LEAD_CAPABLE, require, rights, supervises, works_at
from app.casemgmt.enums import AuthorizationChange, HistoryKind, MemberRole, OrgRole, WorkflowStatus
from app.casemgmt.errors import Conflict, Forbidden, Invalid
from app.casemgmt.models import CaseFamily, CaseMember
from app.casemgmt.notifications import notify
from app.db.models import User

ADDABLE = {MemberRole.SUB_INVESTIGATOR, MemberRole.ANALYST, MemberRole.VIEWER}
# Which parts each account role may hold on a case.
ROLES_FOR = {
    OrgRole.VIEWER: {MemberRole.VIEWER},
    OrgRole.ANALYST: {MemberRole.ANALYST, MemberRole.VIEWER},
    OrgRole.SUB_INVESTIGATOR: {MemberRole.SUB_INVESTIGATOR, MemberRole.VIEWER},
    OrgRole.INVESTIGATOR: ADDABLE,
    OrgRole.SUPERVISOR: ADDABLE,
    OrgRole.ADMINISTRATOR: ADDABLE,
    OrgRole.SUPER_ADMIN: ADDABLE,
}
LABEL = {MemberRole.LEAD: "Investigator (case lead)", MemberRole.SUB_INVESTIGATOR: "Sub Investigator", MemberRole.ANALYST: "Analyst",
         MemberRole.VIEWER: "Viewer"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def active_member(session: Session, family: CaseFamily, user_id) -> CaseMember | None:
    return session.scalar(select(CaseMember).where(CaseMember.case_family_id == family.id, CaseMember.user_id == user_id,
                                                   CaseMember.revoked_at.is_(None)))


def add_member(session: Session, actor: User, family: CaseFamily, *, user_id, role: str) -> CaseMember:
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.manage_team, "Only the Investigator who leads the case, its supervisor or an administrator can add people", found)
    try:
        part = MemberRole(role)
    except ValueError:
        raise Invalid(f"Unknown part '{str(role)[:40]}'") from None
    if part not in ADDABLE:
        raise Invalid("People are added as Sub Investigator, Analyst or Viewer; the lead is changed by handing the case over")
    person = session.get(User, user_id)
    if person is None or not person.is_active or person.organization_id != family.organization_id:
        raise Invalid("Only active users of your organisation can be added")
    if person.id == actor.id:
        raise Invalid("Nobody can add themselves")
    allowed = ROLES_FOR.get(OrgRole(person.org_role), set())
    if part not in allowed:
        names = ", ".join(sorted(LABEL[r] for r in allowed)) or "none"
        raise Invalid(f"A {person.org_role.replace('_', ' ')} account can be added as: {names}")
    if family.classification not in sensitivities_up_to(person.clearance):
        raise Invalid(f"{person.display_name}'s clearance is below this case's classification ({family.classification})")
    if not works_at(person, family.station_id):
        raise Invalid(f"{person.display_name} doesn't work at this case's police station")
    if active_member(session, family, person.id) is not None:
        raise Conflict(f"{person.display_name} is already on the team of {family.display_id}")
    member = CaseMember(case_family_id=family.id, user_id=person.id, role=part.value, granted_by=actor.id)
    session.add(member)
    session.flush()
    engine.record_access(session, family=family, user_id=person.id, change=AuthorizationChange.MEMBERSHIP_GRANTED, old=None,
                         new=part.value, actor=actor, reason=f"Added to {family.display_id} as {LABEL[part]}")
    history.append(session, family, actor, HistoryKind.MEMBER_ADDED, f"{person.display_name} added as {LABEL[part]}",
                   subject_type="user", subject_id=person.id, details={"user": person.username, "role": part.value})
    notify(session, [person.id], "team.added", family=family, actor=actor, role=part.value, label=LABEL[part], title=family.title)
    return member


def remove_member(session: Session, actor: User, family: CaseFamily, user_id, reason: str) -> CaseMember:
    """End someone's place on the team. Their contributions stay attributed; the record of the change is permanent."""
    family = engine._lock_family(session, family.id)
    if user_id == actor.id:
        raise Forbidden("Nobody can change their own place on a team")
    require_strong_auth(actor, "ending someone's access to a case")
    found = rights(session, actor, family)
    require(found.manage_team, "Only the Investigator who leads the case, its supervisor or an administrator can remove people", found)
    member = active_member(session, family, user_id)
    if member is None:
        raise Invalid("That person isn't on this case's team")
    if member.role == MemberRole.LEAD:
        raise Invalid("The Investigator who leads the case changes only when the supervisor hands the case to another Investigator")
    reason = engine._reason(reason)
    person = session.get(User, user_id)
    member.revoked_by, member.revoked_at = actor.id, _now()
    engine.record_access(session, family=family, user_id=user_id, change=AuthorizationChange.MEMBERSHIP_REVOKED, old=member.role,
                         new=None, actor=actor, reason=reason)
    session.flush()
    history.append(session, family, actor, HistoryKind.MEMBER_REMOVED, f"{person.display_name} removed from the team: {reason}",
                   subject_type="user", subject_id=user_id, details={"user": person.username, "role": member.role, "reason": reason})
    notify(session, [user_id], "team.removed", family=family, actor=actor, role=member.role, title=family.title)
    return member


def change_lead(session: Session, actor: User, family: CaseFamily, *, user_id, reason: str) -> CaseMember:
    """Hand the case to another Investigator (the supervisor, or an administrator, decides). The old lead stays as a Sub Investigator."""
    family = engine._lock_family(session, family.id)
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can hand the case to another Investigator")
    if family.workflow_status == WorkflowStatus.ARCHIVED.value:
        raise Forbidden("This case is archived: its record is preserved and can't change")
    reason = engine._reason(reason)
    new = engine._colleague(session, actor, user_id, LEAD_CAPABLE, family.classification, "new lead investigator")
    if not works_at(new, family.station_id):
        raise Invalid("The new lead investigator doesn't work at this case's police station")
    old = session.scalar(select(CaseMember).where(CaseMember.case_family_id == family.id, CaseMember.role == MemberRole.LEAD.value,
                                                  CaseMember.revoked_at.is_(None)))
    if old is not None and old.user_id == new.id:
        raise Invalid(f"{new.display_name} already leads this case")
    now = _now()
    previous = session.get(User, old.user_id) if old else None
    if old is not None:
        old.revoked_by, old.revoked_at = actor.id, now
        engine.record_access(session, family=family, user_id=old.user_id, change=AuthorizationChange.MEMBERSHIP_REVOKED,
                             old=MemberRole.LEAD.value, new=None, actor=actor, reason=f"Case handed to {new.display_name}: {reason}")
    existing = active_member(session, family, new.id)
    if existing is not None:
        existing.revoked_by, existing.revoked_at = actor.id, now
        engine.record_access(session, family=family, user_id=new.id, change=AuthorizationChange.MEMBERSHIP_REVOKED, old=existing.role,
                             new=None, actor=actor, reason="Becoming the lead")
    session.flush()
    lead = CaseMember(case_family_id=family.id, user_id=new.id, role=MemberRole.LEAD.value, granted_by=actor.id)
    session.add(lead)
    engine.record_access(session, family=family, user_id=new.id, change=AuthorizationChange.MEMBERSHIP_GRANTED, old=None,
                         new=MemberRole.LEAD.value, actor=actor, reason=f"Investigator leading {family.display_id}: {reason}")
    if old is not None:  # the old lead stays and keeps helping, as a Sub Investigator
        session.add(CaseMember(case_family_id=family.id, user_id=old.user_id, role=MemberRole.SUB_INVESTIGATOR.value, granted_by=actor.id))
        engine.record_access(session, family=family, user_id=old.user_id, change=AuthorizationChange.MEMBERSHIP_GRANTED, old=None,
                             new=MemberRole.SUB_INVESTIGATOR.value, actor=actor, reason=f"Stays on {family.display_id} as Sub Investigator")
    session.flush()
    history.append(session, family, actor, HistoryKind.LEAD_CHANGED,
                   f"Case handed from {previous.display_name if previous else 'nobody'} to {new.display_name}: {reason}",
                   subject_type="user", subject_id=new.id,
                   details={"from": previous.username if previous else None, "to": new.username, "reason": reason})
    notify(session, [new.id], "case.assigned", family=family, actor=actor, title=family.title)
    if previous is not None:
        notify(session, [previous.id], "team.role_changed", family=family, actor=actor, role=MemberRole.SUB_INVESTIGATOR.value,
               title=family.title)
    return lead


def team(session: Session, family: CaseFamily) -> list[tuple[CaseMember, User]]:
    """Everyone who is or was on the case's team, the active ones first (the Investigator who leads it at the top)."""
    rows = session.execute(select(CaseMember, User).join(User, User.id == CaseMember.user_id)
                           .where(CaseMember.case_family_id == family.id)).all()
    order = {MemberRole.LEAD.value: 0, MemberRole.SUB_INVESTIGATOR.value: 1, MemberRole.ANALYST.value: 2, MemberRole.VIEWER.value: 3}
    return sorted(rows, key=lambda r: (r[0].revoked_at is not None, order.get(r[0].role, 9), r[0].granted_at))
