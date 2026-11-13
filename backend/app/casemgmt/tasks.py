"""The task board of a case (spec §12 and §15, "Assigned tasks").

Tasks are created by people who work on the case (or the supervisor) and assigned to the active members of its team
who can work on it. A task's status and assignee are the only things that change, each change kept in
task_events. A task is never deleted: one that isn't needed any more is cancelled, with a reason.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.casemgmt import engine
from app.casemgmt.access import get_family, require, rights
from app.casemgmt.enums import MemberRole, TaskStatus
from app.casemgmt.errors import Conflict, Invalid, NotVisible
from app.casemgmt.members import active_member
from app.casemgmt.models import CaseFamily, InvestigationTask, TaskEvent
from app.casemgmt.notifications import notify
from app.db.models import User

T = TaskStatus
TRANSITIONS = {
    T.OPEN: {T.IN_PROGRESS, T.DONE, T.CANCELLED},
    T.IN_PROGRESS: {T.OPEN, T.DONE, T.CANCELLED},
    T.DONE: {T.OPEN},  # reopened, with a reason
    T.CANCELLED: {T.OPEN},
}


def _assignee(session: Session, family: CaseFamily, user_id) -> User:
    member = active_member(session, family, user_id)
    if member is None or member.role == MemberRole.VIEWER:
        raise Invalid("Tasks are assigned to active members of the case's team who work on it (not viewers)")
    return session.get(User, user_id)


def create_task(session: Session, actor: User, family: CaseFamily, *, title: str, description: str | None = None,
                assignee_id=None, due_at: dt.datetime | None = None) -> InvestigationTask:
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.create_tasks, "Tasks are created by the people working on the case, or by the supervisor", found)
    title = (title or "").strip()
    if not 3 <= len(title) <= 300:
        raise Invalid("A task needs a title of 3 to 300 characters")
    assignee = _assignee(session, family, assignee_id) if assignee_id else None
    if due_at is not None and (due_at.tzinfo is None or due_at.utcoffset() is None):
        raise Invalid("due_at needs a timezone, e.g. 2026-11-20T17:00:00+05:30")
    due = due_at.astimezone(dt.UTC) if due_at else None
    number = 1 + session.scalar(select(func.count()).select_from(InvestigationTask).where(InvestigationTask.case_family_id == family.id))
    task = InvestigationTask(case_family_id=family.id, display_id=f"TASK-{number:04d}", title=title,
                             description=(description or "").strip()[:10_000] or None, assignee_id=assignee.id if assignee else None,
                             due_at=due, status=T.OPEN.value, created_by=actor.id)
    session.add(task)
    session.flush()
    session.add(TaskEvent(task_id=task.id, field="created", new_value=T.OPEN.value, actor_id=actor.id))
    if assignee:
        session.add(TaskEvent(task_id=task.id, field="assignee", new_value=str(assignee.id), actor_id=actor.id))
        notify(session, [assignee.id], "task.assigned", family=family, actor=actor,
               task={"id": str(task.id), "display_id": task.display_id, "title": task.title})
    session.flush()
    return task


def get_task(session: Session, user: User, task_id) -> tuple[InvestigationTask, CaseFamily]:
    task = session.get(InvestigationTask, task_id)
    if task is None:
        raise NotVisible()
    return task, get_family(session, user, task.case_family_id)


def _check_version(task: InvestigationTask, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != task.version:
        raise Conflict("The task has changed since you last looked at it. Reload and try again: nothing was overwritten.",
                       current_version=task.version)


def change_status(session: Session, actor: User, task: InvestigationTask, family: CaseFamily, *,
                  status: str, reason: str | None = None, expected_version: int | None = None) -> None:
    engine._lock_family(session, family.id, task)
    found = rights(session, actor, family)
    require(found.open and (actor.id in (task.assignee_id, task.created_by) or found.revise_any),
            "A task's status is changed by its assignee, its creator, the Investigator who leads the case or the supervisor", found)
    if status not in set(TaskStatus):
        raise Invalid(f"Unknown task status '{status}'")
    engine._allowed(task.status, status, TRANSITIONS, f"task {task.display_id}")
    _check_version(task, expected_version)
    needs_reason = status == T.CANCELLED or task.status in (T.DONE, T.CANCELLED)
    reason = engine._reason(reason) if needs_reason else ((reason or "").strip()[:1000] or None)
    old, task.status, task.version = task.status, status, task.version + 1
    session.add(TaskEvent(task_id=task.id, field="status", old_value=old, new_value=status, actor_id=actor.id, reason=reason))
    session.flush()
    notify(session, [task.created_by, task.assignee_id], "task.status_changed", family=family, actor=actor,
           task={"id": str(task.id), "display_id": task.display_id, "title": task.title}, status=status)


def assign(session: Session, actor: User, task: InvestigationTask, family: CaseFamily, *, assignee_id,
           reason: str | None = None, expected_version: int | None = None) -> None:
    engine._lock_family(session, family.id, task)
    found = rights(session, actor, family)
    require(found.open and (actor.id == task.created_by or found.revise_any),
            "A task is assigned by its creator, the Investigator who leads the case or the supervisor", found)
    if task.status not in (T.OPEN, T.IN_PROGRESS):
        raise Invalid(f"Task {task.display_id} is {task.status}: reopen it first")
    _check_version(task, expected_version)
    assignee = _assignee(session, family, assignee_id) if assignee_id else None
    new = assignee.id if assignee else None
    if new == task.assignee_id:
        raise Invalid("The task is already assigned that way")
    old, task.assignee_id, task.version = task.assignee_id, new, task.version + 1
    session.add(TaskEvent(task_id=task.id, field="assignee", old_value=str(old) if old else None, new_value=str(new) if new else None,
                          actor_id=actor.id, reason=(reason or "").strip()[:1000] or None))
    session.flush()
    if assignee:
        notify(session, [assignee.id], "task.assigned", family=family, actor=actor,
               task={"id": str(task.id), "display_id": task.display_id, "title": task.title})
