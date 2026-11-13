"""Read-only views for the case's access history, tasks, comments, notes and notices (docs/case-management/13). Access is decided
before these run."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import queries
from app.casemgmt.access import rights, supervises
from app.casemgmt.enums import FileStatus, TaskStatus
from app.casemgmt.models import AuthorizationEvent, CaseFamily, CaseFolder, Comment, InvestigationTask, Notification, TaskEvent
from app.casemgmt.plain import plain
from app.db.models import User


def _lookup(session: Session, model, ids) -> dict:
    ids = {i for i in ids if i}
    return {row.id: row for row in session.scalars(select(model).where(model.id.in_(ids)))} if ids else {}


# ---------------------------------------------------------------- access history


def access_history(session: Session, rows: list[AuthorizationEvent]) -> list[dict]:
    who = queries.people(session, [u for r in rows for u in (r.user_id, r.actor_id)])
    return [{"id": r.id, "user": who.get(r.user_id), "change": r.change, "old_value": r.old_value, "new_value": r.new_value,
             "actor": who.get(r.actor_id), "reason": plain(r.reason), "at": r.at} for r in rows]


# ---------------------------------------------------------------- tasks


def task_ref(task: InvestigationTask) -> dict:
    return {"id": task.id, "display_id": task.display_id, "title": task.title, "status": task.status}


def tasks(session: Session, rows: list[InvestigationTask]) -> list[dict]:
    families = _lookup(session, CaseFamily, [t.case_family_id for t in rows])
    who = queries.people(session, [u for t in rows for u in (t.assignee_id, t.created_by)])
    return [{**task_ref(t), "case": queries.case_ref(families[t.case_family_id]), "description": t.description,
             "assignee": who.get(t.assignee_id), "due_at": t.due_at, "created_by": who.get(t.created_by), "created_at": t.created_at,
             "version": t.version} for t in rows]


def task_detail(session: Session, user: User, task: InvestigationTask, family: CaseFamily) -> dict:
    events = list(session.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.id)))
    who = queries.people(session, [e.actor_id for e in events])
    found = rights(session, user, family)
    return {**tasks(session, [task])[0],
            "events": [{"field": e.field, "old_value": e.old_value, "new_value": e.new_value, "actor": who.get(e.actor_id),
                        "reason": plain(e.reason), "at": e.at} for e in events],
            "can": {"change_status": found.open and (user.id in (task.assignee_id, task.created_by) or found.revise_any),
                    "assign": found.open and task.status in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
                    and (user.id == task.created_by or found.revise_any)}}


# ---------------------------------------------------------------- comments


def comments(session: Session, rows: list[Comment]) -> list[dict]:
    replaced_by = {r.replaces_comment_id: r.id for r in rows if r.replaces_comment_id}
    who = queries.people(session, [r.author_id for r in rows])
    return [{"id": r.id, "target_type": r.target_type, "target_id": r.target_id, "author": who.get(r.author_id), "body": r.body,
             "created_at": r.created_at, "replaces_comment_id": r.replaces_comment_id, "replaced_by": replaced_by.get(r.id),
             "current": r.id not in replaced_by} for r in rows]


# ---------------------------------------------------------------- notes and analyses, notifications


def artifact_history(session: Session, user: User, artifact, family: CaseFamily, versions) -> dict:
    who = queries.people(session, [v.author_id for v in versions] + [artifact.sealed_by])
    folder = session.get(CaseFolder, artifact.folder_id)
    found = rights(session, user, family)
    from app.casemgmt.enums import ArtifactType
    from app.casemgmt.engine import KEPT_AS_MADE

    editable = (artifact.status == FileStatus.ACTIVE.value and ArtifactType(artifact.artifact_type) not in KEPT_AS_MADE
                and (found.revise_any or (found.add_files and artifact.created_by == user.id)))
    return {"id": artifact.id, "display_id": artifact.display_id, "title": artifact.title, "artifact_type": artifact.artifact_type,
            "folder": folder.name, "status": artifact.status, "withdrawn_reason": artifact.withdrawn_reason,
            "case": queries.case_ref(family), "sealed": artifact.sealed, "sealed_reason": artifact.sealed_reason,
            "sealed_by": who.get(artifact.sealed_by), "sealed_at": artifact.sealed_at,
            "versions": [{"id": v.id, "version_number": v.version_number, "content": v.content, "content_sha256": v.content_sha256,
                          "derived_from": v.derived_from, "author": who.get(v.author_id), "created_at": v.created_at,
                          "change_note": plain(v.change_note)} for v in versions],
            "can": {"revise": editable, "withdraw": found.withdraw and artifact.status == FileStatus.ACTIVE.value,
                    "seal": supervises(user, family)}}


def notification(row: Notification) -> dict:
    return {"id": row.id, "kind": row.kind, "payload": row.payload, "created_at": row.created_at, "read_at": row.read_at}
