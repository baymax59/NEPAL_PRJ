"""Reading the audit log (administrators only). Reading it is itself recorded."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, get_audit_log
from app.auth.dependencies import require_role
from app.core.enums import AuditOutcome, Role
from app.db.models import AuditEvent, User
from app.db.session import get_db
from app.schemas.auth import AuditEventOut, AuditPage, AuditQuery

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
def read_audit_log(
    params: Annotated[AuditQuery, Query()],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
    audit: Annotated[AuditLog, Depends(get_audit_log)],
) -> AuditPage:
    conditions = []
    if params.action:
        conditions.append(AuditEvent.action == params.action)
    if params.username:
        conditions.append(AuditEvent.username == params.username.lower())
    if params.outcome:
        conditions.append(AuditEvent.outcome == params.outcome)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions))
    events = db.scalars(
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    audit.record("audit.read", AuditOutcome.SUCCESS, user=admin, details=params.model_dump(exclude_defaults=True))
    return AuditPage(total=total, events=[AuditEventOut.model_validate(e) for e in events])
