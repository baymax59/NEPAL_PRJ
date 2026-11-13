"""Figures for the dashboards (spec §14 "Overview Dashboard", "Investigation Activity"; §15 "My Contributions"; docs/case-management/13).

Counts only, always within what the user may see: the administrator's organisation and clearance, or the cases an investigator
can open. Nothing here changes anything.
"""

import datetime as dt
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.casemgmt import evidence_views, queries
from app.casemgmt.access import case_condition, family_condition
from app.casemgmt.case_types import CASE_TYPES
from app.casemgmt.enums import FileStatus, HistoryKind, IntegrityResult, TaskStatus
from app.casemgmt.models import (
    Artifact,
    CaseEntry,
    CaseFamily,
    EvidenceItem,
    EvidenceObject,
    EvidenceVersion,
    InvestigationTask,
)
from app.db.models import User

ACTIVITY_DAYS = 30
OPEN_TASKS = [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]


def _counts(session: Session, column, *conditions) -> dict[str, int]:
    query = select(column, func.count()).select_from(CaseFamily)
    return {key: n for key, n in session.execute(query.where(*conditions).group_by(column)).all()}


def _entries(session: Session, rows: list[CaseEntry]) -> list[dict]:
    """History entries as the dashboards list them, each with its case."""
    if not rows:
        return []
    families = {f.id: f for f in session.scalars(select(CaseFamily).where(CaseFamily.id.in_({e.case_family_id for e in rows})))}
    who = queries.people(session, [e.actor_id for e in rows])
    return [{"seq": e.seq, "kind": e.kind, "at": e.at, "actor": who.get(e.actor_id), "summary": e.summary, "subject_type": e.subject_type,
             "subject_id": e.subject_id, "details": e.details, "case": queries.case_ref(families[e.case_family_id])} for e in rows]


def admin_overview(session: Session, admin: User) -> dict:
    """The organisation's case work at a glance, for its administrator."""
    in_scope = family_condition(admin)
    now = dt.datetime.now(dt.UTC)
    by_status = _counts(session, CaseFamily.workflow_status, in_scope)
    by_priority = _counts(session, CaseFamily.priority, in_scope)
    by_type = _counts(session, CaseFamily.case_type, in_scope)
    labels = {code: t["label"] for code, t in CASE_TYPES.items()}

    # History entries per day (UTC) for the last ACTIVITY_DAYS days, with the empty days filled in.
    since = (now - dt.timedelta(days=ACTIVITY_DAYS - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day = func.date_trunc("day", func.timezone("UTC", CaseEntry.at))
    per_day = {d.date(): n for d, n in session.execute(
        select(day, func.count()).join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id)
        .where(in_scope, CaseEntry.at >= since).group_by(day)).all()}
    activity = [{"day": (since + dt.timedelta(days=i)).date(), "entries": per_day.get((since + dt.timedelta(days=i)).date(), 0)}
                for i in range(ACTIVITY_DAYS)]
    total_entries = session.scalar(select(func.count()).select_from(CaseEntry)
                                   .join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id).where(in_scope)) or 0

    # Evidence within the administrator's clearance, and the result of each object's latest integrity check.
    allowed = list(sensitivities_up_to(admin.clearance))
    rows = session.execute(
        select(EvidenceItem.id, EvidenceItem.display_id, EvidenceItem.title, EvidenceItem.status, CaseFamily.id, CaseFamily.display_id,
               EvidenceObject.sha256, EvidenceObject.size_bytes)
        .join(CaseFamily, CaseFamily.id == EvidenceItem.case_family_id)
        .join(EvidenceVersion, EvidenceVersion.evidence_item_id == EvidenceItem.id)
        .join(EvidenceObject, EvidenceObject.sha256 == EvidenceVersion.object_sha256)
        .where(in_scope, EvidenceItem.classification.in_(allowed))).all()
    checks = evidence_views.last_checks(session, [r[6] for r in rows])
    integrity = Counter()
    alerts = []
    for item_id, display_id, title, _status, case_id, case_display_id, sha, _ in rows:
        check = checks.get(sha)
        result = check.result if check else "never_checked"
        integrity[result] += 1
        if check and check.result != IntegrityResult.MATCH:
            alerts.append({"evidence_id": item_id, "display_id": display_id, "title": title, "case_id": case_id,
                           "case_display_id": case_display_id, "result": check.result, "checked_at": check.checked_at})

    def family_count(model, *conditions) -> int:
        return session.scalar(select(func.count()).select_from(model).join(CaseFamily, CaseFamily.id == model.case_family_id)
                              .where(in_scope, *conditions)) or 0

    recent = list(session.scalars(
        select(CaseEntry).join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id).where(in_scope)
        .order_by(CaseEntry.at.desc(), CaseEntry.id.desc()).limit(12)))
    active, withdrawn = FileStatus.ACTIVE.value, FileStatus.WITHDRAWN.value
    return {
        "cases": {"total": sum(by_status.values()), "by_status": by_status, "by_priority": by_priority,
                  "by_type": [{"code": code, "label": labels.get(code, code), "count": n} for code, n in
                              sorted(by_type.items(), key=lambda kv: -kv[1])]},
        "files": {"notes": family_count(Artifact, Artifact.status == active),
                  "exhibits": sum(1 for r in rows if r[3] == active),
                  "withdrawn": family_count(Artifact, Artifact.status == withdrawn) + sum(1 for r in rows if r[3] == withdrawn)},
        "activity": {"total": total_entries, "per_day": activity},
        "evidence": {"items": len(rows), "bytes": sum(r[7] for r in rows), "integrity": dict(integrity), "alerts": alerts[:20]},
        "tasks": {"open": family_count(InvestigationTask, InvestigationTask.status.in_(OPEN_TASKS)),
                  "overdue": family_count(InvestigationTask, InvestigationTask.status.in_(OPEN_TASKS), InvestigationTask.due_at < now)},
        "recent_entries": _entries(session, recent),
        "generated_at": now,
    }


def _contribution_totals(session: Session, user: User, *, openable_only: bool) -> dict:
    """How many history entries, notes, revisions and exhibits the user made (only where they can still open, or anywhere)."""
    scope = [case_condition(user)] if openable_only else []

    def count(*kinds) -> int:
        query = select(func.count()).select_from(CaseEntry).join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id).where(
            CaseEntry.actor_id == user.id, *scope)
        if kinds:
            query = query.where(CaseEntry.kind.in_([k.value for k in kinds]))
        return session.scalar(query) or 0

    return {"entries": count(), "notes": count(HistoryKind.NOTE_ADDED), "revisions": count(HistoryKind.NOTE_REVISED),
            "evidence": count(HistoryKind.EVIDENCE_ADDED)}


def my_contributions(session: Session, user: User, *, limit: int = 20) -> dict:
    """The user's own history entries, in cases they can still open, newest first; and how much they did.

    Work in cases they can no longer open (an access that ended) stays credited to them: it is counted in `no_longer_open`, as
    numbers only. Nothing from those cases is shown."""
    base = (select(CaseEntry).join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id)
            .where(CaseEntry.actor_id == user.id, case_condition(user)))
    rows = list(session.scalars(base.order_by(CaseEntry.at.desc(), CaseEntry.id.desc()).limit(limit)))
    openable = _contribution_totals(session, user, openable_only=True)
    everywhere = _contribution_totals(session, user, openable_only=False)
    return {"entries": _entries(session, rows), "totals": openable,
            "no_longer_open": {key: everywhere[key] - openable[key] for key in openable}}
