"""Collaboration endpoints under /api/v1 (docs/case-management/06, 13): the case's access history, the task board, comments, the version
history of notes (revising, withdrawing, sealing) and notifications. The same rules as the rest of the module: access inside the queries,
404 for anything not visible, every request audited, nothing deleted. Included before the module's main router, whose catch-all
answers 405 to deletions on these paths too.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select, update

from app.auth.dependencies import CurrentUser
from app.casemgmt import artifacts, collab_views, comments, engine, history, tasks
from app.casemgmt import schemas as s
from app.casemgmt.access import case_condition, get_family
from app.casemgmt.api import Audit, Audited, Cursor, DbSession, IdempotencyKeyHeader, Limit, _next, _offset, _require_admin
from app.casemgmt.enums import TaskStatus
from app.casemgmt.errors import NotVisible
from app.casemgmt.idempotency import Once
from app.casemgmt.models import AuthorizationEvent, CaseFamily, InvestigationTask, Notification
from app.db.models import User

router = APIRouter(prefix="/v1", tags=["case management: collaboration"])


def _replay(once: Once, event: Audited):
    if (previous := once.previous()) is not None:
        event.read(replayed=True)
        return previous
    return None


# ---------------------------------------------------------------- access history


@router.get("/cases/{case_id}/access-history", response_model=list[s.AccessEventOut])
def access_history(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """Everyone added to or removed from this case's team, oldest first (permanent)."""
    with Audited(db, audit, user, "cm.access_history.read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        rows = list(db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.case_family_id == family.id).order_by(AuthorizationEvent.id)))
        event.read(count=len(rows))
    return collab_views.access_history(db, rows)


@router.get("/admin/cases/{case_id}/access-history", response_model=list[s.AccessEventOut])
def admin_access_history(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """The access history of a case (the administrators' team history)."""
    with Audited(db, audit, user, "cm.admin.access_history", "cm_case", case_id) as event:
        _require_admin(user)
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        rows = list(db.scalars(select(AuthorizationEvent).where(AuthorizationEvent.case_family_id == family.id).order_by(AuthorizationEvent.id)))
        event.read(count=len(rows))
    return collab_views.access_history(db, rows)


# ---------------------------------------------------------------- tasks


@router.post("/cases/{case_id}/tasks", response_model=s.TaskDetail, status_code=status.HTTP_201_CREATED)
def create_task(case_id: uuid.UUID, body: s.TaskCreate, user: CurrentUser, db: DbSession, audit: Audit,
                idempotency_key: IdempotencyKeyHeader = None) -> dict:
    with Audited(db, audit, user, "cm.task.created", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/tasks", body.model_dump(mode="json"))
        if (previous := _replay(once, event)) is not None:
            return previous
        task = tasks.create_task(db, user, family, title=body.title, description=body.description, assignee_id=body.assignee_id,
                                 due_at=body.due_at)
        result = collab_views.task_detail(db, user, task, family)
        once.save(status.HTTP_201_CREATED, s.TaskDetail, result)
        event.write(task=task.display_id, assignee=body.assignee_id)
    return result


@router.get("/cases/{case_id}/tasks", response_model=list[s.TaskOut])
def case_tasks(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, status_filter: Annotated[
        str | None, Query(alias="status", max_length=16)] = None, assignee: uuid.UUID | None = None) -> list[dict]:
    with Audited(db, audit, user, "cm.tasks.list", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        conditions = [InvestigationTask.case_family_id == family.id]
        if status_filter:
            conditions.append(InvestigationTask.status == status_filter)
        if assignee:
            conditions.append(InvestigationTask.assignee_id == assignee)
        rows = list(db.scalars(select(InvestigationTask).where(*conditions).order_by(InvestigationTask.created_at)))
        event.read(count=len(rows))
    return collab_views.tasks(db, rows)


@router.get("/tasks/mine", response_model=list[s.TaskOut])
def my_tasks(user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """Open tasks assigned to me, in cases I can still open (the investigator's "Assigned tasks")."""
    with Audited(db, audit, user, "cm.tasks.mine", "cm_task") as event:
        rows = list(db.scalars(
            select(InvestigationTask).join(CaseFamily, CaseFamily.id == InvestigationTask.case_family_id)
            .where(InvestigationTask.assignee_id == user.id, case_condition(user),
                   InvestigationTask.status.in_([TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]))
            .order_by(InvestigationTask.due_at.asc().nulls_last(), InvestigationTask.created_at)))
        event.read(count=len(rows))
    return collab_views.tasks(db, rows)


@router.get("/tasks/{task_id}", response_model=s.TaskDetail)
def task_detail(task_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.task.view", "cm_task", task_id) as event:
        task, family = tasks.get_task(db, user, task_id)
        event.target_id = family.display_id
        result = collab_views.task_detail(db, user, task, family)
        event.read(task=task.display_id)
    return result


@router.post("/tasks/{task_id}/status", response_model=s.TaskDetail)
def change_task_status(task_id: uuid.UUID, body: s.TaskStatusChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.task.status_changed", "cm_task", task_id, status=body.status) as event:
        task, family = tasks.get_task(db, user, task_id)
        event.target_id = family.display_id
        tasks.change_status(db, user, task, family, status=body.status, reason=body.reason, expected_version=body.expected_version)
        result = collab_views.task_detail(db, user, task, family)
        event.write(task=task.display_id)
    return result


@router.post("/tasks/{task_id}/assign", response_model=s.TaskDetail)
def assign_task(task_id: uuid.UUID, body: s.TaskAssign, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.task.assigned", "cm_task", task_id, assignee=body.assignee_id) as event:
        task, family = tasks.get_task(db, user, task_id)
        event.target_id = family.display_id
        tasks.assign(db, user, task, family, assignee_id=body.assignee_id, reason=body.reason, expected_version=body.expected_version)
        result = collab_views.task_detail(db, user, task, family)
        event.write(task=task.display_id)
    return result


# ---------------------------------------------------------------- comments


@router.post("/cases/{case_id}/comments", response_model=s.CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(case_id: uuid.UUID, body: s.CommentCreate, user: CurrentUser, db: DbSession, audit: Audit,
                idempotency_key: IdempotencyKeyHeader = None) -> dict:
    with Audited(db, audit, user, "cm.comment.added", "cm_case", case_id, subject_type=body.target_type) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/comments", body.model_dump(mode="json"))
        if (previous := _replay(once, event)) is not None:
            return previous
        comment = comments.add_comment(db, user, family, target_type=body.target_type, target_id=body.target_id, body=body.body,
                                       replaces_comment_id=body.replaces_comment_id)
        result = collab_views.comments(db, [comment])[0]
        once.save(status.HTTP_201_CREATED, s.CommentOut, result)
        event.write(comment=comment.id, subject=comment.target_id, replaces=body.replaces_comment_id)
    return result


@router.get("/cases/{case_id}/comments", response_model=list[s.CommentOut])
def list_comments(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit,
                  target_type: Annotated[str, Query(pattern=r"^(case|evidence|artifact|task)$")],
                  target_id: Annotated[str, Query(min_length=1, max_length=64)]) -> list[dict]:
    with Audited(db, audit, user, "cm.comments.list", "cm_case", case_id, subject_type=target_type) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        rows = comments.list_comments(db, user, family, target_type, target_id)
        event.read(count=len(rows))
    return collab_views.comments(db, rows)


# ---------------------------------------------------------------- notes and analyses: versions, withdrawing, sealing


def _artifact_label(db, artifact) -> str:
    return f"{db.get(CaseFamily, artifact.case_family_id).display_id}/{artifact.display_id}"


@router.get("/artifacts/{artifact_id}/versions", response_model=s.ArtifactHistory)
def artifact_versions(artifact_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Every version of a note or analysis, oldest first."""
    with Audited(db, audit, user, "cm.artifact.versions", "cm_artifact", artifact_id) as event:
        artifact, family, versions = artifacts.get_artifact(db, user, artifact_id)
        event.target_id = _artifact_label(db, artifact)
        result = collab_views.artifact_history(db, user, artifact, family, versions)
        event.read(count=len(versions))
    return result


@router.post("/artifacts/{artifact_id}/versions", response_model=s.NoteRevised, status_code=status.HTTP_201_CREATED)
def revise_artifact(artifact_id: uuid.UUID, body: s.NoteRevise, user: CurrentUser, db: DbSession, audit: Audit,
                    idempotency_key: IdempotencyKeyHeader = None) -> dict:
    """A new version of a note. The old text stays; if someone revised it since you opened it, nothing is overwritten (409)."""
    with Audited(db, audit, user, "cm.note.revised", "cm_artifact", artifact_id) as event:
        artifact, family, _ = artifacts.get_artifact(db, user, artifact_id)
        event.target_id = _artifact_label(db, artifact)
        once = Once(db, user, idempotency_key, f"POST /api/v1/artifacts/{artifact_id}/versions", body.model_dump(mode="json"))
        if (previous := _replay(once, event)) is not None:
            return previous
        version = engine.revise_note(db, user, family, artifact, content=body.content, expected_version=body.expected_version,
                                     note=body.note, derived_from=body.derived_from)
        entry = history.last_entry(db, family.id)
        result = {"version": collab_views.artifact_history(db, user, artifact, family, [version])["versions"][0], "entry": entry.seq}
        once.save(status.HTTP_201_CREATED, s.NoteRevised, result)
        event.write(version=version.version_number, entry=entry.seq, sha256=version.content_sha256)
    return result


@router.post("/artifacts/{artifact_id}/withdraw", response_model=s.ArtifactHistory)
def withdraw_artifact(artifact_id: uuid.UUID, body: s.RequiredReason, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Withdraw a wrong note, with a reason. It leaves the case's current view and stays in the history."""
    with Audited(db, audit, user, "cm.artifact.withdrawn", "cm_artifact", artifact_id) as event:
        artifact, family, versions = artifacts.get_artifact(db, user, artifact_id)
        event.target_id = _artifact_label(db, artifact)
        engine.withdraw_file(db, user, family, artifact, reason=body.reason)
        result = collab_views.artifact_history(db, user, artifact, family, versions)
        event.write(reason_given=True)
    return result


def _seal_artifact(artifact_id: uuid.UUID, body: s.RequiredReason, user: User, db, audit, sealed: bool) -> dict:
    with Audited(db, audit, user, f"cm.artifact.{'sealed' if sealed else 'unsealed'}", "cm_artifact", artifact_id) as event:
        artifact, family, versions = artifacts.get_artifact(db, user, artifact_id)
        event.target_id = _artifact_label(db, artifact)
        artifacts.set_sealed(db, user, artifact, family, sealed=sealed, reason=body.reason)
        result = collab_views.artifact_history(db, user, artifact, family, versions)
        event.write()
    return result


@router.post("/artifacts/{artifact_id}/seal", response_model=s.ArtifactHistory)
def seal_artifact(artifact_id: uuid.UUID, body: s.RequiredReason, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Hide a note or analysis from everyone but the supervisor and administrators. Nothing is removed."""
    return _seal_artifact(artifact_id, body, user, db, audit, True)


@router.post("/artifacts/{artifact_id}/unseal", response_model=s.ArtifactHistory)
def unseal_artifact(artifact_id: uuid.UUID, body: s.RequiredReason, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    return _seal_artifact(artifact_id, body, user, db, audit, False)


# ---------------------------------------------------------------- notifications


@router.get("/notifications", response_model=s.NotificationList)
def list_notifications(user: CurrentUser, db: DbSession, audit: Audit, limit: Limit = 50, cursor: Cursor = None,
                       unread_only: bool = False) -> dict:
    with Audited(db, audit, user, "cm.notifications.list", "cm_notification") as event:
        offset = _offset(cursor)
        conditions = [Notification.user_id == user.id] + ([Notification.read_at.is_(None)] if unread_only else [])
        total = db.scalar(select(func.count()).select_from(Notification).where(*conditions))
        unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
        rows = db.scalars(select(Notification).where(*conditions).order_by(Notification.id.desc()).limit(limit).offset(offset))
        result = {"items": [collab_views.notification(n) for n in rows], "unread": unread, "total": total,
                  "next_cursor": _next(offset, limit, total)}
        event.read(count=len(result["items"]), unread=unread)
    return result


@router.post("/notifications/{notification_id}/read", response_model=s.NotificationOut)
def read_notification(notification_id: int, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.notification.read", "cm_notification", notification_id) as event:
        notice = db.get(Notification, notification_id)
        if notice is None or notice.user_id != user.id:
            raise NotVisible(exists=notice is not None)
        if notice.read_at is None:
            notice.read_at = func.now()
            db.flush()
            db.refresh(notice)
        result = collab_views.notification(notice)
        event.write()
    return result


@router.post("/notifications/read-all", response_model=s.Marked)
def read_all_notifications(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.notifications.read_all", "cm_notification") as event:
        marked = db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
                            .values(read_at=func.now()).execution_options(synchronize_session=False)).rowcount
        event.write(marked=marked)
    return {"marked": marked}
