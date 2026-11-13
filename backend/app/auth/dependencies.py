"""FastAPI dependencies: who is calling, what they may see, and what they may do."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, get_audit_log
from app.auth.access import AccessContext, sensitivities_up_to
from app.auth.tokens import read_access_claims
from app.core.enums import AuditOutcome, Role
from app.db.models import CaseAccessGrant, User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


# While a temporary password is in use, only these answer: who am I, and set my own password.
PASSWORD_CHANGE_PATHS = ("/auth/me", "/auth/change-password")


def get_current_user(
    request: Request, token: Annotated[str | None, Depends(oauth2_scheme)], db: Annotated[Session, Depends(get_db)]
) -> User:
    claims = read_access_claims(token) if token else None
    user = db.get(User, uuid.UUID(claims["sub"])) if claims else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.must_change_password and not request.url.path.endswith(PASSWORD_CHANGE_PATHS):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must set your own password first (your password is temporary)")
    # Whether this login included a two-step verification code (privileged actions may require it: app/auth/mfa.py).
    user.mfa_verified = "otp" in (claims.get("amr") or [])
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_access_context(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> AccessContext:
    now = dt.datetime.now(dt.UTC)
    granted = db.scalars(
        select(CaseAccessGrant.case_id).where(
            CaseAccessGrant.user_id == user.id,
            or_(CaseAccessGrant.expires_at.is_(None), CaseAccessGrant.expires_at > now),
        )
    ).all()
    return AccessContext(user.id, sensitivities_up_to(user.clearance), frozenset(granted))


def require_role(*roles: Role):
    """Dependency that allows only the given roles (403 for others). Refusals are audited."""
    allowed = {role.value for role in roles}

    def check(user: CurrentUser, request: Request, audit: Annotated[AuditLog, Depends(get_audit_log)]) -> User:
        if user.role not in allowed:
            audit.record(
                "role.denied",
                AuditOutcome.DENIED,
                user=user,
                target_type="endpoint",
                target_id=f"{request.method} {request.url.path}"[:128],
                details={"role": user.role, "required": sorted(allowed)},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not allow this action")
        return user

    return check
