"""Log in (get a token) and see who you are logged in as."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, get_audit_log
from app.auth.dependencies import CurrentUser
from app.auth.ratelimit import FailedLoginLimiter, get_login_limiter
from app.auth.tokens import create_access_token
from app.auth.users import authenticate
from app.core.enums import AuditOutcome
from app.db.session import get_db
from app.schemas.auth import TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenOut)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    audit: Annotated[AuditLog, Depends(get_audit_log)],
    limiter: Annotated[FailedLoginLimiter, Depends(get_login_limiter)],
) -> TokenOut:
    address = request.client.host if request.client else "unknown"
    if limiter.blocked(address):
        # Too many failures from this computer: refuse without even checking the password.
        audit.record(
            "auth.login", AuditOutcome.REJECTED, username=form.username[:64], details={"reason": "too_many_failures_from_address"}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed logins from this computer. Try again in a few minutes.",
            headers={"Retry-After": str(limiter.retry_after(address))},
        )
    user, reason = authenticate(db, form.username, form.password)
    if user is None:
        limiter.record_failure(address)
        # The username typed is recorded (it may not exist); the password never is.
        audit.record(
            "auth.login", AuditOutcome.REJECTED, username=form.username[:64], details={"reason": reason}
        )
        # One message for every failure, so it can't reveal which accounts exist or are locked.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password, or the account is locked. Try again later.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit.record("auth.login", AuditOutcome.SUCCESS, user=user)
    token, lifetime = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=lifetime)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
