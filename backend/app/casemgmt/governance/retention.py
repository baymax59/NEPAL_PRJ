"""Retention as a formal decision (phase CM-7, docs/case-management/07 §6). Knight Hawk never deletes a case.

- **Policies** (platform administrators) say after how many years a closed case is due for a retention review, for
  which case types, and under which rule or schedule. A policy is retired, never edited or removed.
- **Due for review**: closed (or archived) cases whose review date under their policy has passed, and that have no
  open decision and no "retain" decision still running. Nothing happens to them automatically.
- **Decisions** are proposed by the case's supervisor or a platform administrator, and approved or rejected by a
  **different** person (two-person rule, also a database constraint), with two-step verification when required.
  - retain: keep the case, and review it again on a given date;
  - archive: carried out on approval: the case becomes "archived" and read-only. Still kept;
  - transfer: records that the case was handed to another body; the records stay here;
  - dispose: records the decision only. The application never deletes anything: carrying out a disposal is a separate,
    formal process of the organisation (decision D15 in docs/DECISIONS.md), outside Knight Hawk.
- A **legal hold** blocks proposing or approving archive, transfer and disposal.
"""

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.mfa import require_strong_auth
from app.casemgmt import engine, queries
from app.casemgmt.access import family_condition, is_super_admin, supervises
from app.casemgmt.case_types import CASE_TYPES
from app.casemgmt.enums import PolicyStatus, RetentionAction, RetentionStatus, StatusField, WorkflowStatus
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.governance import holds
from app.casemgmt.models import CaseFamily, CaseStatusEvent, RetentionDecision, RetentionPolicy
from app.casemgmt.notifications import notify
from app.db.models import User

ACTIONS = {
    RetentionAction.RETAIN: "Retain, and review again later",
    RetentionAction.ARCHIVE: "Archive (read-only, kept in Knight Hawk)",
    RetentionAction.TRANSFER: "Transfer to another body (recorded; the records stay)",
    RetentionAction.DISPOSE: "Dispose (a recorded decision for the organisation's formal process; nothing is deleted here)",
}
HELD_ACTIONS = {RetentionAction.ARCHIVE, RetentionAction.TRANSFER, RetentionAction.DISPOSE}
CLOSED = {WorkflowStatus.CLOSED.value, WorkflowStatus.ARCHIVED.value}
CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def _text(value: str | None, what: str, low: int, high: int) -> str:
    value = (value or "").strip()
    if not low <= len(value) <= high:
        raise Invalid(f"{what}: {low} to {high:,} characters")
    return value


def _admin(user: User) -> None:
    if not is_super_admin(user):
        raise Forbidden("Only platform administrators manage retention policies")


# ---------------------------------------------------------------- policies


def create_policy(session: Session, admin: User, *, code: str, name: str, review_after_years: int, legal_basis: str,
                  case_types: list[str] | None = None, description: str | None = None) -> RetentionPolicy:
    _admin(admin)
    code = (code or "").strip().lower()
    if not CODE.fullmatch(code):
        raise Invalid("A policy's code is 2 to 63 lower-case letters, digits or '-', e.g. closed-cases-10y")
    if session.scalar(select(RetentionPolicy.id).where(RetentionPolicy.organization_id == admin.organization_id, RetentionPolicy.code == code)):
        raise Invalid(f"A policy with the code {code} exists already: policies can't be edited, retire it and add a new one")
    if not 1 <= int(review_after_years) <= 100:
        raise Invalid("Review after 1 to 100 years")
    types = sorted(set(case_types or []))
    unknown = [t for t in types if t not in CASE_TYPES]
    if unknown:
        raise Invalid(f"Unknown case types: {', '.join(unknown)}")
    policy = RetentionPolicy(organization_id=admin.organization_id, code=code, name=_text(name, "The name", 3, 200),
                             description=(description or "").strip()[:2000] or None, review_after_years=int(review_after_years),
                             case_types=types, legal_basis=_text(legal_basis, "The legal basis (the rule or schedule it follows)", 10, 2000),
                             status=PolicyStatus.ACTIVE.value, created_by=admin.id)
    session.add(policy)
    session.flush()
    return policy


def retire_policy(session: Session, admin: User, policy_id) -> RetentionPolicy:
    _admin(admin)
    policy = session.get(RetentionPolicy, policy_id)
    if policy is None or policy.organization_id != admin.organization_id:
        raise NotVisible(exists=policy is not None)
    if policy.status == PolicyStatus.RETIRED:
        raise Invalid("This policy is already retired")
    policy.status = PolicyStatus.RETIRED.value
    session.flush()
    return policy


def _policies(session: Session, organization_id) -> list[RetentionPolicy]:
    return list(session.scalars(select(RetentionPolicy).where(RetentionPolicy.organization_id == organization_id)
                                .order_by(RetentionPolicy.created_at)))


def matching(policies: list[RetentionPolicy], family: CaseFamily) -> RetentionPolicy | None:
    """The active policy for the case: one naming its type first, else one for every type."""
    active = [p for p in policies if p.status == PolicyStatus.ACTIVE]
    return next((p for p in active if family.case_type in p.case_types), None) or next((p for p in active if not p.case_types), None)


def closed_on(session: Session, family: CaseFamily) -> dt.datetime | None:
    """When the case was last closed (its latest workflow change to "closed")."""
    return session.scalar(select(CaseStatusEvent.at).where(
        CaseStatusEvent.case_family_id == family.id, CaseStatusEvent.field == StatusField.WORKFLOW.value,
        CaseStatusEvent.new_value == WorkflowStatus.CLOSED.value).order_by(CaseStatusEvent.at.desc()).limit(1))


def _add_years(moment: dt.datetime, years: int) -> dt.date:
    day = moment.date()
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def _review(session: Session, family: CaseFamily, policies: list[RetentionPolicy], decisions: list[RetentionDecision], today: dt.date) -> dict:
    policy = matching(policies, family)
    closed = closed_on(session, family) if family.workflow_status in CLOSED else None
    due = _add_years(closed, policy.review_after_years) if closed and policy else None
    retained = next((d for d in decisions if d.action == RetentionAction.RETAIN and d.status == RetentionStatus.APPROVED
                     and d.review_on and d.review_on > today), None)
    if retained is not None:
        due = retained.review_on
    open_decision = next((d for d in decisions if d.status == RetentionStatus.PROPOSED), None)
    return {"policy": policy, "closed_at": closed, "due_on": due, "open_decision": open_decision,
            "is_due": bool(due and due <= today and open_decision is None)}


# ---------------------------------------------------------------- decisions


def _decisions(session: Session, family_ids) -> dict:
    found: dict = {}
    for d in session.scalars(select(RetentionDecision).where(RetentionDecision.case_family_id.in_(list(family_ids)))
                             .order_by(RetentionDecision.proposed_at.desc())):
        found.setdefault(d.case_family_id, []).append(d)
    return found


def propose(session: Session, actor: User, family: CaseFamily, *, action: str, reason: str, policy_id=None,
            review_on: dt.date | None = None, transfer_to: str | None = None) -> RetentionDecision:
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can propose a retention decision")
    try:
        kind = RetentionAction(action)
    except ValueError:
        raise Invalid(f"Unknown retention action: use one of {', '.join(a.value for a in RetentionAction)}") from None
    reason = _text(reason, "The reason", 10, 2000)
    family = engine._lock_family(session, family.id, family)
    if kind in HELD_ACTIONS:
        holds.ensure_not_held(session, family, f"a decision to {kind.value} it")
    if session.scalar(select(RetentionDecision.id).where(RetentionDecision.case_family_id == family.id,
                                                         RetentionDecision.status == RetentionStatus.PROPOSED.value)):
        raise Invalid(f"{family.display_id} already has a retention decision waiting: decide or withdraw it first")
    if kind == RetentionAction.RETAIN:
        if review_on is None or review_on <= dt.date.today() or review_on > dt.date.today() + dt.timedelta(days=36600):
            raise Invalid("A decision to retain needs the date of the next review, in the future (within 100 years)")
    else:
        review_on = None
    if kind == RetentionAction.TRANSFER:
        transfer_to = _text(transfer_to, "To whom the case is transferred", 3, 300)
    else:
        transfer_to = None
    if kind == RetentionAction.ARCHIVE and family.workflow_status != WorkflowStatus.CLOSED:
        raise Invalid(f"Only a closed case can be archived; {family.display_id} is {family.workflow_status.replace('_', ' ')}")
    policy = None
    if policy_id is not None:
        policy = session.get(RetentionPolicy, policy_id)
        if policy is None or policy.organization_id != family.organization_id:
            raise Invalid("Unknown retention policy")
    decision = RetentionDecision(organization_id=family.organization_id, case_family_id=family.id, policy_id=policy.id if policy else None,
                                 action=kind.value, reason=reason, review_on=review_on, transfer_to=transfer_to, proposed_by=actor.id,
                                 status=RetentionStatus.PROPOSED.value)
    session.add(decision)
    session.flush()
    return decision


def get_decision(session: Session, actor: User, decision_id) -> tuple[RetentionDecision, CaseFamily]:
    decision = session.get(RetentionDecision, decision_id)
    family = session.get(CaseFamily, decision.case_family_id) if decision else None
    if decision is None or not supervises(actor, family):
        raise NotVisible(exists=decision is not None)
    return decision, family


def decide(session: Session, actor: User, decision: RetentionDecision, family: CaseFamily, *, approve: bool, note: str) -> RetentionDecision:
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can decide a retention decision")
    require_strong_auth(actor, "deciding a retention decision")
    family = engine._lock_family(session, family.id, family, decision)
    if decision.status != RetentionStatus.PROPOSED:
        raise Invalid(f"This decision is already {decision.status}")
    if decision.proposed_by == actor.id:
        raise Forbidden("A second person decides: whoever proposed a retention decision can't approve or reject it")
    note = _text(note, "The note on your decision", 5, 2000)
    kind = RetentionAction(decision.action)
    if approve and kind in HELD_ACTIONS:
        holds.ensure_not_held(session, family, f"approving a decision to {kind.value} it")
    if approve and kind == RetentionAction.ARCHIVE:
        reason = f"Retention decision approved: {note}"[:1000]
        engine.change_case_status(session, actor, family, field=StatusField.WORKFLOW.value, value=WorkflowStatus.ARCHIVED.value, reason=reason)
    decision.status = (RetentionStatus.APPROVED if approve else RetentionStatus.REJECTED).value
    decision.decided_by, decision.decided_at, decision.decision_note = actor.id, dt.datetime.now(dt.UTC), note
    session.flush()
    notify(session, [decision.proposed_by, family.supervisor_id], "retention.decided", family=family, actor=actor,
           action=kind.value, decision=decision.status)
    return decision


def withdraw(session: Session, actor: User, decision: RetentionDecision, family: CaseFamily, *, reason: str) -> RetentionDecision:
    if decision.proposed_by != actor.id and not is_super_admin(actor):
        raise Forbidden("Only whoever proposed it, or an administrator, can withdraw a retention decision")
    if decision.status != RetentionStatus.PROPOSED:
        raise Invalid(f"This decision is already {decision.status}")
    decision.status = RetentionStatus.WITHDRAWN.value
    decision.decided_at, decision.decision_note = dt.datetime.now(dt.UTC), _text(reason, "The reason", 5, 2000)
    session.flush()
    return decision


# ---------------------------------------------------------------- views


def decision_view(d: RetentionDecision, who: dict, policies: dict) -> dict:
    policy = policies.get(d.policy_id)
    return {"id": d.id, "action": d.action, "action_label": ACTIONS[RetentionAction(d.action)], "reason": d.reason,
            "review_on": d.review_on, "transfer_to": d.transfer_to, "policy": {"id": policy.id, "name": policy.name} if policy else None,
            "proposed_by": who.get(d.proposed_by), "proposed_at": d.proposed_at, "status": d.status, "decided_by": who.get(d.decided_by),
            "decided_at": d.decided_at, "decision_note": d.decision_note,
            "outside_action": d.action == RetentionAction.DISPOSE and d.status == RetentionStatus.APPROVED}


def policy_view(p: RetentionPolicy, who: dict) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "description": p.description, "review_after_years": p.review_after_years,
            "case_types": p.case_types, "legal_basis": p.legal_basis, "status": p.status, "created_by": who.get(p.created_by),
            "created_at": p.created_at}


def for_case(session: Session, viewer: User, family: CaseFamily) -> dict:
    """The case's legal holds, retention decisions and review date (who may act is decided by the backend on each request)."""
    policies = _policies(session, family.organization_id)
    decisions = _decisions(session, [family.id]).get(family.id, [])
    review = _review(session, family, policies, decisions, dt.date.today())
    who = queries.people(session, [d.proposed_by for d in decisions] + [d.decided_by for d in decisions])
    by_id = {p.id: p for p in policies}
    return {"holds": holds.for_case(session, family), "on_hold": holds.on_hold(session, family.id),
            "decisions": [decision_view(d, who, by_id) for d in decisions],
            "policy": policy_view(review["policy"], queries.people(session, [review["policy"].created_by])) if review["policy"] else None,
            "closed_at": review["closed_at"], "review_due_on": review["due_on"], "review_due": review["is_due"],
            "can_decide": supervises(viewer, family), "actions": [{"code": a.value, "label": label} for a, label in ACTIONS.items()]}


def overview(session: Session, admin: User) -> dict:
    """Policies, cases due for review, and decisions waiting for a second person (platform administrators)."""
    _admin(admin)
    today = dt.date.today()
    policies = _policies(session, admin.organization_id)
    families = list(session.scalars(select(CaseFamily).where(family_condition(admin))))
    decisions = _decisions(session, [f.id for f in families])
    flat = [d for ds in decisions.values() for d in ds]
    who = queries.people(session, [p.created_by for p in policies] + [d.proposed_by for d in flat] + [d.decided_by for d in flat])
    by_id = {p.id: p for p in policies}
    by_family = {f.id: f for f in families}
    due = []
    for family in families:
        if family.workflow_status not in CLOSED:
            continue
        review = _review(session, family, policies, decisions.get(family.id, []), today)
        if review["is_due"]:
            due.append({"case": queries.case_ref(family), "policy": {"id": review["policy"].id, "name": review["policy"].name},
                        "closed_at": review["closed_at"], "due_on": review["due_on"], "on_hold": holds.on_hold(session, family.id)})
    waiting = [{**decision_view(d, who, by_id), "case": queries.case_ref(by_family[d.case_family_id])}
               for d in flat if d.status == RetentionStatus.PROPOSED]
    return {"policies": [policy_view(p, who) for p in policies], "due": sorted(due, key=lambda r: r["due_on"]), "waiting": waiting,
            "actions": [{"code": a.value, "label": label} for a, label in ACTIONS.items()]}
