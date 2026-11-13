"""Comments on a case, its exhibits, notes and tasks (docs/case-management/04 §5, 13).

Comments are permanent. Editing one adds a new comment that replaces it; the earlier wording stays in the
history. Viewers read comments but don't write them. A comment is about something the author can see, and only
people who can still see that thing can read its comments (a sealed exhibit's comments disappear with it).
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import engine
from app.casemgmt.access import require, rights
from app.casemgmt.artifacts import get_artifact
from app.casemgmt.enums import CommentTarget
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.evidence import get_evidence
from app.casemgmt.models import CaseFamily, Comment, InvestigationTask
from app.casemgmt.notifications import notify
from app.db.models import User

MAX_BODY = 10_000


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise NotVisible() from None


def target(session: Session, user: User, family: CaseFamily, target_type: str, target_id: str) -> tuple[str, object]:
    """The normalised ID of a comment's subject and the subject itself, if the user can see it here; NotVisible otherwise."""
    kind = CommentTarget(target_type)
    if kind == CommentTarget.CASE:
        if str(target_id) != str(family.id):
            raise NotVisible(exists=True)
        return str(family.id), family
    if kind == CommentTarget.EVIDENCE:
        seen = get_evidence(session, user, _uuid(target_id))
        if seen.family.id != family.id:
            raise NotVisible(exists=True)
        return str(seen.item.id), seen.item
    if kind == CommentTarget.ARTIFACT:
        artifact, artifact_family, _ = get_artifact(session, user, _uuid(target_id))
        if artifact_family.id != family.id:
            raise NotVisible(exists=True)
        return str(artifact.id), artifact
    found = session.get(InvestigationTask, _uuid(target_id))
    if found is None or found.case_family_id != family.id:
        raise NotVisible(exists=found is not None)
    return str(found.id), found


def add_comment(session: Session, actor: User, family: CaseFamily, *, target_type: str, target_id: str, body: str,
                replaces_comment_id=None) -> Comment:
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.comment, "Comments are written by the people working on the case and the supervisor; viewers read them", found)
    subject_id, subject = target(session, actor, family, target_type, target_id)
    body = (body or "").strip()
    if not 1 <= len(body) <= MAX_BODY:
        raise Invalid(f"A comment is 1 to {MAX_BODY:,} characters")
    if replaces_comment_id is not None:
        earlier = session.get(Comment, replaces_comment_id)
        if earlier is None or earlier.case_family_id != family.id or (earlier.target_type, earlier.target_id) != (target_type, subject_id):
            raise Invalid("The comment being replaced isn't on the same subject")
        if earlier.author_id != actor.id:
            raise Forbidden("You can replace only your own comments")
        if session.scalar(select(Comment.id).where(Comment.replaces_comment_id == earlier.id)):
            raise Invalid("That comment was already replaced: replace the newest version")
    # The moment it is written (not the transaction's start), so comments, edits included, list in the order they were made.
    comment = Comment(case_family_id=family.id, target_type=target_type, target_id=subject_id,
                      author_id=actor.id, body=body, replaces_comment_id=replaces_comment_id, created_at=dt.datetime.now(dt.UTC))
    session.add(comment)
    session.flush()
    if isinstance(subject, InvestigationTask):
        notify(session, [subject.assignee_id, subject.created_by], "comment.added", family=family, actor=actor,
               on={"type": "task", "id": str(subject.id), "display_id": subject.display_id})
    return comment


def list_comments(session: Session, user: User, family: CaseFamily, target_type: str, target_id: str) -> list[Comment]:
    """Every comment on a subject (replaced versions included), oldest first."""
    subject_id, _ = target(session, user, family, target_type, target_id)
    return list(session.scalars(select(Comment).where(Comment.case_family_id == family.id, Comment.target_type == target_type,
                                                      Comment.target_id == subject_id).order_by(Comment.created_at, Comment.id)))
