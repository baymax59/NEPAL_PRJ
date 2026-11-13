"""Dashboards by police station and by officer (phase R-5, docs/case-management/12-roles-and-stations.md §7).

Counts only, read only, always inside what the viewer may see: every figure is computed over the cases the viewer could open
(the same station, membership and clearance rules as the case lists), so a number never includes a case the viewer could not
open, and a station or officer outside the viewer's reach answers "not found" exactly like one that doesn't exist.
Nothing here changes anything.

The words used by the figures (the screens say the same):
    open      every case that is not closed or archived (it includes the two "pending" groups)
    pending   the case waits for evidence, or waits for a review
    closed    closed or archived
    late task a task that is still open or in progress after its due date
"""

import datetime as dt
import uuid
from collections import Counter, defaultdict

from sqlalchemy import ColumnElement, and_, extract, func, select
from sqlalchemy.orm import Session

from app.casemgmt import queries
from app.casemgmt.access import case_condition, my_stations
from app.casemgmt.accounts import RANK
from app.casemgmt.enums import HistoryKind, OrgRole, TaskStatus, WorkflowStatus
from app.casemgmt.errors import Forbidden, NotVisible
from app.casemgmt.models import (
    CaseEntry,
    CaseFamily,
    CaseMember,
    CaseStatusEvent,
    InvestigationTask,
    OfficerRegistry,
    PoliceStation,
    UserStation,
)
from app.db.models import User

CLOSED = [WorkflowStatus.CLOSED.value, WorkflowStatus.ARCHIVED.value]
OPEN_TASKS = [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]
STATION_VIEWERS = {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}
OFFICER_VIEWERS = STATION_VIEWERS | {OrgRole.INVESTIGATOR}  # an Investigator sees only their own page
MONTHS = 6
RECENT_DAYS = 30
OLDEST_SHOWN = 8


# ---------------------------------------------------------------- who may look


def require_station_view(viewer: User) -> None:
    if viewer.organization_id is None or viewer.org_role not in STATION_VIEWERS:
        raise Forbidden("Station dashboards are for a Super Admin, an Administrator and a Supervisor")


def require_officer_view(viewer: User) -> None:
    if viewer.organization_id is None or viewer.org_role not in OFFICER_VIEWERS:
        raise Forbidden("Officer dashboards are for a Super Admin, an Administrator, a Supervisor and an Investigator (their own)")


def can_open(viewer: User) -> ColumnElement[bool]:
    """The case may be opened by the viewer (station, team, clearance): the rule of every case query."""
    return case_condition(viewer)


def stations_in_scope(session: Session, viewer: User) -> list[PoliceStation]:
    """The stations whose dashboard the viewer may open: all for a Super Admin, the assigned ones for an Administrator or Supervisor."""
    require_station_view(viewer)
    query = select(PoliceStation).where(PoliceStation.organization_id == viewer.organization_id)
    if viewer.org_role != OrgRole.SUPER_ADMIN:
        query = query.where(PoliceStation.id.in_(my_stations(viewer)))
    return list(session.scalars(query.order_by(PoliceStation.created_at, PoliceStation.code)))


def get_station(session: Session, viewer: User, station_id: uuid.UUID) -> PoliceStation:
    require_station_view(viewer)
    found = next((s for s in stations_in_scope(session, viewer) if s.id == station_id), None)
    if found is None:
        raise NotVisible(exists=session.get(PoliceStation, station_id) is not None)
    return found


def may_open_officer(session: Session, viewer: User, target: User) -> bool:
    """Yourself; for a Super Admin anyone of the organisation; for an Administrator or Supervisor someone of a lower role who
    works at one of their stations. Nobody else (an Investigator sees only themselves)."""
    if viewer.organization_id is None or target.organization_id != viewer.organization_id:
        return False
    if target.id == viewer.id:
        return True
    if viewer.org_role == OrgRole.SUPER_ADMIN:
        return True
    if viewer.org_role in (OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR) and RANK[OrgRole(target.org_role)] < RANK[OrgRole(viewer.org_role)]:
        return session.scalar(select(UserStation.id).where(
            UserStation.user_id == target.id, UserStation.revoked_at.is_(None), UserStation.station_id.in_(my_stations(viewer)))) is not None
    return False


def get_officer(session: Session, viewer: User, user_id: uuid.UUID) -> User:
    require_officer_view(viewer)
    target = session.get(User, user_id)
    if target is None or not may_open_officer(session, viewer, target):
        raise NotVisible(exists=target is not None)
    return target


def station_officers(session: Session, viewer: User, station: PoliceStation) -> list[User]:
    """The active accounts working at the station whom the viewer may open, by name."""
    candidates = session.scalars(
        select(User).join(UserStation, UserStation.user_id == User.id)
        .where(UserStation.station_id == station.id, UserStation.revoked_at.is_(None), User.is_active.is_(True),
               User.organization_id == viewer.organization_id)
        .order_by(User.display_name, User.username))
    return [u for u in candidates if may_open_officer(session, viewer, u)]


# ---------------------------------------------------------------- figures of a set of cases


def month_start(now: dt.datetime, back: int = 0) -> dt.datetime:
    """The first moment (UTC) of the month `back` months before the one `now` is in."""
    year, month = now.year, now.month - back
    while month < 1:
        year, month = year - 1, month + 12
    return dt.datetime(year, month, 1, tzinfo=dt.UTC)


def _first_closed():
    """The first moment each case reached closed (or archived)."""
    return (select(CaseStatusEvent.case_family_id.label("family_id"), func.min(CaseStatusEvent.at).label("closed_at"))
            .where(CaseStatusEvent.field == "workflow", CaseStatusEvent.new_value.in_(CLOSED))
            .group_by(CaseStatusEvent.case_family_id).subquery())


def case_figures(session: Session, conditions: list, now: dt.datetime, *, oldest: int = 1) -> dict:
    """Open, closed and pending cases of the cases that match `conditions` (which always include the viewer's reach)."""
    by_status = {status: n for status, n in session.execute(
        select(CaseFamily.workflow_status, func.count()).where(*conditions).group_by(CaseFamily.workflow_status)).all()}
    total = sum(by_status.values())
    closed = sum(by_status.get(s, 0) for s in CLOSED)

    new_this_month = session.scalar(select(func.count()).select_from(CaseFamily).where(*conditions, CaseFamily.created_at >= month_start(now)))

    first_closed = _first_closed()
    seconds = extract("epoch", first_closed.c.closed_at - CaseFamily.created_at)
    average = session.scalar(
        select(func.avg(func.greatest(seconds, 0) / 86400)).select_from(CaseFamily)
        .join(first_closed, first_closed.c.family_id == CaseFamily.id)
        .where(*conditions, CaseFamily.workflow_status.in_(CLOSED)))

    still_open = session.scalars(select(CaseFamily).where(*conditions, CaseFamily.workflow_status.not_in(CLOSED))
                                 .order_by(CaseFamily.created_at, CaseFamily.id).limit(oldest))
    return {
        "total": total, "open": total - closed, "closed": closed,
        "pending_evidence": by_status.get(WorkflowStatus.PENDING_EVIDENCE.value, 0),
        "pending_review": by_status.get(WorkflowStatus.PENDING_REVIEW.value, 0),
        "by_status": by_status, "new_this_month": new_this_month or 0,
        "average_days_to_close": round(float(average), 1) if average is not None else None,
        "oldest_open": [{"case": queries.case_ref(f), "opened_at": f.created_at, "days_open": max(0, (now - f.created_at).days)}
                        for f in still_open],
    }


def monthly(session: Session, conditions: list, now: dt.datetime) -> list[dict]:
    """Cases opened and cases closed in each of the last MONTHS months (closed: the month a case first reached closed)."""
    first = month_start(now, MONTHS - 1)
    opened_month = func.date_trunc("month", func.timezone("UTC", CaseFamily.created_at))
    opened = {m.date(): n for m, n in session.execute(
        select(opened_month, func.count()).where(*conditions, CaseFamily.created_at >= first).group_by(opened_month)).all()}
    first_closed = _first_closed()
    closed_month = func.date_trunc("month", func.timezone("UTC", first_closed.c.closed_at))
    closed = {m.date(): n for m, n in session.execute(
        select(closed_month, func.count()).select_from(CaseFamily).join(first_closed, first_closed.c.family_id == CaseFamily.id)
        .where(*conditions, CaseFamily.workflow_status.in_(CLOSED), first_closed.c.closed_at >= first).group_by(closed_month)).all()}
    rows = []
    for back in range(MONTHS - 1, -1, -1):
        month = month_start(now, back).date()
        rows.append({"month": month.strftime("%Y-%m"), "opened": opened.get(month, 0), "closed": closed.get(month, 0)})
    return rows


# ---------------------------------------------------------------- figures of officers


def officer_cases(session: Session, conditions: list, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[uuid.UUID, dict]]:
    """For each officer, the cases they work on or supervise: {user_id: {case_id: {"family", "roles", "active"}}}.

    A case counts once per officer, whatever parts they had on it. Work that ended (taken off the team) stays credited to them:
    that is `active` False."""
    found: dict[uuid.UUID, dict[uuid.UUID, dict]] = defaultdict(dict)

    def add(user_id, family: CaseFamily, role: str, active: bool) -> None:
        entry = found[user_id].setdefault(family.id, {"family": family, "roles": set(), "active": False})
        entry["roles"].add(role)
        entry["active"] = entry["active"] or active

    for user_id, family, role, revoked_at in session.execute(
            select(CaseMember.user_id, CaseFamily, CaseMember.role, CaseMember.revoked_at)
            .join(CaseFamily, CaseFamily.id == CaseMember.case_family_id)
            .where(CaseMember.user_id.in_(user_ids), *conditions)).all():
        add(user_id, family, role, revoked_at is None)
    for family in session.scalars(select(CaseFamily).where(CaseFamily.supervisor_id.in_(user_ids), *conditions)):
        add(family.supervisor_id, family, "supervisor", True)
    return found


def officer_figures(session: Session, viewer: User, users: list[User], now: dt.datetime, *, station_id: uuid.UUID | None = None) -> dict:
    """Progress and performance of each officer, only over the cases the viewer may open (and, when asked, one station's)."""
    ids = [u.id for u in users]
    conditions = [can_open(viewer)] + ([CaseFamily.station_id == station_id] if station_id is not None else [])
    cases = officer_cases(session, conditions, ids)

    # tasks assigned to them
    unfinished = InvestigationTask.status.in_(OPEN_TASKS)
    late = and_(unfinished, InvestigationTask.due_at < now)
    tasks: dict[uuid.UUID, Counter] = defaultdict(Counter)
    for user_id, n_late, n_open, n_done in session.execute(
            select(InvestigationTask.assignee_id, func.count().filter(late), func.count().filter(unfinished, ~late),
                   func.count().filter(InvestigationTask.status == TaskStatus.DONE.value))
            .join(CaseFamily, CaseFamily.id == InvestigationTask.case_family_id)
            .where(InvestigationTask.assignee_id.in_(ids), *conditions).group_by(InvestigationTask.assignee_id)).all():
        tasks[user_id].update({"late": n_late, "open": n_open, "done": n_done})

    # their own work: entries of the case history they made (notes, exhibits...), and when they last did something
    recent_since = now - dt.timedelta(days=RECENT_DAYS)
    work: dict[uuid.UUID, dict] = {}
    latest: dict[uuid.UUID, dt.datetime] = {}
    for user_id, n, recent, notes, exhibits, last in session.execute(
            select(CaseEntry.actor_id, func.count(), func.count().filter(CaseEntry.at >= recent_since),
                   func.count().filter(CaseEntry.kind.in_([HistoryKind.NOTE_ADDED.value, HistoryKind.NOTE_REVISED.value])),
                   func.count().filter(CaseEntry.kind == HistoryKind.EVIDENCE_ADDED.value), func.max(CaseEntry.at))
            .join(CaseFamily, CaseFamily.id == CaseEntry.case_family_id)
            .where(CaseEntry.actor_id.in_(ids), *conditions).group_by(CaseEntry.actor_id)).all():
        work[user_id] = {"entries": n, "entries_last_30_days": recent, "notes": notes, "evidence": exhibits}
        latest[user_id] = last

    figures = {}
    for user in users:
        mine = [entry["family"].workflow_status for entry in cases.get(user.id, {}).values()]
        by_status = Counter(mine)
        closed = sum(by_status[s] for s in CLOSED)
        done = work.get(user.id, {"entries": 0, "entries_last_30_days": 0, "notes": 0, "evidence": 0})
        figures[user.id] = {
            "cases": {"total": len(mine), "open": len(mine) - closed, "closed": closed,
                      "pending_evidence": by_status[WorkflowStatus.PENDING_EVIDENCE.value],
                      "pending_review": by_status[WorkflowStatus.PENDING_REVIEW.value]},
            "tasks": {"done": tasks[user.id]["done"], "open": tasks[user.id]["open"], "late": tasks[user.id]["late"]},
            "work": done,
            "last_activity": latest.get(user.id),
        }
    return {"figures": figures, "cases": cases}


def person(session: Session, user: User) -> dict:
    """Who the officer is, as the screens show them."""
    stations = list(session.execute(
        select(PoliceStation.id, PoliceStation.code, PoliceStation.name).join(UserStation, UserStation.station_id == PoliceStation.id)
        .where(UserStation.user_id == user.id, UserStation.revoked_at.is_(None)).order_by(PoliceStation.code)))
    register = session.get(OfficerRegistry, user.officer_id) if user.officer_id else None
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "org_role": user.org_role,
            "is_active": user.is_active,
            "officer": {"officer_number": register.officer_number, "full_name": register.full_name, "rank": register.rank}
            if register else None,
            "stations": [{"id": i, "code": c, "name": n} for i, c, n in stations]}


# ---------------------------------------------------------------- the three dashboards


def _station_brief(station: PoliceStation) -> dict:
    return {"id": station.id, "code": station.code, "name": station.name, "district": station.district, "status": station.status}


def stations_overview(session: Session, viewer: User) -> dict:
    """Every station the viewer may open, each with its open, closed and pending cases."""
    now = dt.datetime.now(dt.UTC)
    rows = []
    for station in stations_in_scope(session, viewer):
        conditions = [can_open(viewer), CaseFamily.station_id == station.id]
        rows.append({"station": _station_brief(station), "figures": case_figures(session, conditions, now),
                     "officers": len(station_officers(session, viewer, station))})
    return {"stations": rows, "generated_at": now}


def station_dashboard(session: Session, viewer: User, station_id: uuid.UUID) -> dict:
    """One station: its figures, the cases open the longest, a month-by-month picture, and each officer's progress."""
    station = get_station(session, viewer, station_id)
    now = dt.datetime.now(dt.UTC)
    conditions = [can_open(viewer), CaseFamily.station_id == station.id]
    people = station_officers(session, viewer, station)
    detail = officer_figures(session, viewer, people, now, station_id=station.id)
    return {
        "station": _station_brief(station),
        "figures": case_figures(session, conditions, now, oldest=OLDEST_SHOWN),
        "monthly": monthly(session, conditions, now),
        "officers": [{"person": person(session, u), **detail["figures"][u.id]} for u in people],
        "generated_at": now,
    }


def officer_dashboard(session: Session, viewer: User, user_id: uuid.UUID) -> dict:
    """One officer: progress, reviews, tasks, last activity, and their cases (only those the viewer may open)."""
    target = get_officer(session, viewer, user_id)
    now = dt.datetime.now(dt.UTC)
    detail = officer_figures(session, viewer, [target], now)
    stations = {s.id: s.code for s in session.scalars(select(PoliceStation).where(PoliceStation.organization_id == viewer.organization_id))}
    mine = sorted(detail["cases"].get(target.id, {}).values(), key=lambda e: (e["family"].created_at, e["family"].id))
    return {
        "person": person(session, target),
        **detail["figures"][target.id],
        "case_list": [{"case": queries.case_ref(e["family"]), "station_code": stations.get(e["family"].station_id, ""),
                   "roles": sorted(e["roles"]), "active": e["active"], "opened_at": e["family"].created_at,
                   "days_open": max(0, (now - e["family"].created_at).days) if e["family"].workflow_status not in CLOSED else None}
                  for e in mine],
        "generated_at": now,
    }
