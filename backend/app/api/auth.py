"""Log in (get a token), see who you are logged in as, and manage two-step verification (CM-7)."""

import datetime as dt
from typing import Annotated

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, get_audit_log
from app.auth import mfa
from app.auth.photos import CONTENT_TYPE, MAX_UPLOAD_BYTES, BadPhoto, prepare_photo
from app.auth.dependencies import CurrentUser
from app.auth.ratelimit import FailedLoginLimiter, get_login_limiter, get_signup_limiter
from app.auth.tokens import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.auth.users import authenticate
from app.core.config import get_settings
from app.core.enums import AuditOutcome
from app.db.models import User
from app.db.session import get_db
from app.casemgmt.accounts import profile_view, register_yourself, update_profile
from app.casemgmt.errors import Invalid
from app.schemas.auth import (
    ChangePassword,
    MfaCode,
    MfaLogin,
    MfaSetup,
    MfaStatus,
    ProfileIn,
    ProfileOut,
    RegisteredOut,
    RegisterIn,
    RegistrationStatus,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
Limiter = Annotated[FailedLoginLimiter, Depends(get_login_limiter)]
SignupLimiter = Annotated[FailedLoginLimiter, Depends(get_signup_limiter)]
WRONG_LOGIN = "Incorrect username or password, or the account is locked. Try again later."


def _address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _refuse_if_blocked(limiter: FailedLoginLimiter, address: str, audit: AuditLog, action: str, username: str | None) -> None:
    if limiter.blocked(address):
        # Too many failures from this computer: refuse without even checking the password or code.
        audit.record(action, AuditOutcome.REJECTED, username=(username or "")[:64] or None, details={"reason": "too_many_failures_from_address"})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed logins from this computer. Try again in a few minutes.",
            headers={"Retry-After": str(limiter.retry_after(address))},
        )


@router.post("/token", response_model=TokenOut)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: DbSession, audit: Audit, limiter: Limiter) -> TokenOut:
    address = _address(request)
    _refuse_if_blocked(limiter, address, audit, "auth.login", form.username)
    user, reason = authenticate(db, form.username, form.password)
    if user is None:
        limiter.record_failure(address)
        # The username typed is recorded (it may not exist); the password never is.
        audit.record("auth.login", AuditOutcome.REJECTED, username=form.username[:64], details={"reason": reason})
        # One message for every failure, so it can't reveal which accounts exist or are locked.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=WRONG_LOGIN, headers={"WWW-Authenticate": "Bearer"})
    if mfa.enabled(db, user):
        # The password was right; a code is still needed (POST /api/auth/mfa/login).
        audit.record("auth.login", AuditOutcome.SUCCESS, user=user, details={"second_step": "pending"})
        # No token yet (an empty string, not a password): the second step issues it.
        return TokenOut(access_token="", expires_in=0, mfa_required=True, mfa_ticket=mfa.issue_ticket(user))  # nosec B106
    audit.record("auth.login", AuditOutcome.SUCCESS, user=user)
    token, lifetime = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=lifetime)


@router.get("/registration", response_model=RegistrationStatus)
def registration_status() -> RegistrationStatus:
    """Whether the sign-in page offers "Create your account" (public)."""
    return RegistrationStatus(enabled=get_settings().self_registration)


@router.post("/register", response_model=RegisteredOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, db: DbSession, audit: Audit, limiter: SignupLimiter) -> RegisteredOut:
    """An officer in the register creates their own login (public). It starts with view-only access; the people above raise it."""
    if not get_settings().self_registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    address = _address(request)
    if limiter.blocked(address):
        audit.record("user.self_registered", AuditOutcome.REJECTED, username=body.username[:64], details={"reason": "too_many_attempts_from_address"})
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many sign-up attempts from this computer. Try again later.",
                            headers={"Retry-After": str(limiter.retry_after(address))})
    limiter.record_failure(address)  # every attempt counts, successful or not
    try:
        user, station = register_yourself(db, officer_number=body.officer_number, full_name=body.full_name, username=body.username, password=body.password,
                                         email=body.email, phone=body.phone)
    except Invalid as exc:
        db.rollback()
        audit.record("user.self_registered", AuditOutcome.REJECTED, username=body.username[:64], details={"reason": "refused"})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    db.commit()
    audit.record("user.self_registered", AuditOutcome.SUCCESS, user=user, details={"officer_number": body.officer_number.upper()})
    return RegisteredOut(username=user.username, display_name=user.display_name, org_role=user.org_role, station=station,
                         message="Your login is ready. It starts with view-only access: your Supervisor or Administrator can give you more.")


@router.post("/mfa/login", response_model=TokenOut)
def login_second_step(body: MfaLogin, request: Request, db: DbSession, audit: Audit, limiter: Limiter) -> TokenOut:
    """The second step of a login: the ticket from POST /api/auth/token and a current code from the authenticator app."""
    address = _address(request)
    _refuse_if_blocked(limiter, address, audit, "auth.mfa_login", None)
    user_id = mfa.read_ticket(body.ticket)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active or not mfa.check(db, user, body.code):
        limiter.record_failure(address)
        audit.record("auth.mfa_login", AuditOutcome.REJECTED, user=user, details={"reason": "invalid_ticket_or_code"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The code isn't valid, or the login took too long: log in again.",
                            headers={"WWW-Authenticate": "Bearer"})
    db.commit()  # the code's step is remembered: it can't be used again
    audit.record("auth.mfa_login", AuditOutcome.SUCCESS, user=user)
    token, lifetime = create_access_token(user.id, second_step=True)
    return TokenOut(access_token=token, expires_in=lifetime)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> dict:
    """Your own profile: the official details from the register, and your email, phone and job title."""
    return profile_view(db, user)


@router.post("/profile", response_model=ProfileOut)
def save_profile(body: ProfileIn, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Update your own profile (only yourself, only these three things). Which fields changed is recorded, never their values."""
    changed = update_profile(db, user, email=body.email, phone=body.phone, job_title=body.job_title)
    db.commit()
    audit.record("user.profile_updated", AuditOutcome.SUCCESS, user=user, details={"fields": changed})
    return profile_view(db, user)


@router.post("/profile/photo", response_model=ProfileOut)
def set_photo(file: Annotated[UploadFile, File()], user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Your own profile photo (only yours). JPEG, PNG or WebP up to 2 MB; the server draws it again as a small square JPEG."""
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        data = prepare_photo(raw)
    except BadPhoto as exc:
        audit.record("user.photo_changed", AuditOutcome.REJECTED, user=user, details={"reason": "refused"})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    user.photo_data, user.photo_updated_at = data, dt.datetime.now(dt.UTC)
    db.commit()
    audit.record("user.photo_changed", AuditOutcome.SUCCESS, user=user, details={"action": "set", "bytes": len(data)})
    return profile_view(db, user)


@router.post("/profile/photo/remove", response_model=ProfileOut)
def remove_photo(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Take your own photo off your profile."""
    user.photo_data, user.photo_updated_at = None, None
    db.commit()
    audit.record("user.photo_changed", AuditOutcome.SUCCESS, user=user, details={"action": "removed"})
    return profile_view(db, user)


@router.get("/photo/{user_id}")
def get_photo(user_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """A person's photo: only for people who are logged in, and only within the same organisation."""
    person = db.get(User, user_id)
    if person is None or person.organization_id != user.organization_id or person.photo_updated_at is None or not person.photo_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No photo")
    # (the application's own header rules already forbid caching by shared caches: Cache-Control: no-store)
    return Response(content=person.photo_data, media_type=CONTENT_TYPE, headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePassword, user: CurrentUser, db: DbSession, audit: Audit) -> None:
    """Choose your own password (needed with the temporary one you were given). The current password must be right."""
    settings = get_settings()
    if not verify_password(body.current_password, user.password_hash):
        user.failed_logins += 1  # a stolen token can't be used to guess the password for ever
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=settings.lockout_minutes)
        db.commit()
        audit.record("auth.password_changed", AuditOutcome.REJECTED, user=user, details={"reason": "wrong current password"})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The current password is not right")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a password different from the current one")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    audit.record("auth.password_changed", AuditOutcome.SUCCESS, user=user)  # the password itself is never recorded


@router.get("/mfa", response_model=MfaStatus)
def mfa_status(user: CurrentUser, db: DbSession) -> dict:
    return mfa.status(db, user)


def _mfa_change(action: str, user: User, db: Session, audit: AuditLog, change) -> None:
    try:
        change()
    except mfa.MfaError as error:
        db.rollback()
        audit.record(action, AuditOutcome.REJECTED, user=user, details={"reason": str(error)[:120]})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from None
    db.commit()
    audit.record(action, AuditOutcome.SUCCESS, user=user)


@router.post("/mfa/setup", response_model=MfaSetup)
def mfa_setup(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Start setting up two-step verification: scan the QR code, then confirm one code."""
    result: dict = {}
    _mfa_change("auth.mfa_setup", user, db, audit, lambda: result.update(mfa.start(db, user)))
    return result


@router.post("/mfa/confirm", response_model=MfaStatus)
def mfa_confirm(body: MfaCode, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Turn two-step verification on with the first code. The next logins ask for a code."""
    _mfa_change("auth.mfa_enabled", user, db, audit, lambda: mfa.confirm(db, user, body.code))
    return mfa.status(db, user)


@router.post("/mfa/disable", response_model=MfaStatus)
def mfa_disable(body: MfaCode, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Turn two-step verification off, with a current code."""
    _mfa_change("auth.mfa_disabled", user, db, audit, lambda: mfa.disable(db, user, body.code))
    return mfa.status(db, user)
