"""Two-step verification (TOTP, RFC 6238) for Knight Hawk users (phase CM-7, docs/case-management/07 §5).

- A user turns it on by scanning a QR code (or typing the key) into an authenticator app and confirming one code.
- The secret is stored encrypted (Fernet) with MFA_KEY, a key kept outside the database (derived from JWT_SECRET until
  one is set; the readiness check says so).
- At login, a user with two-step verification gets, after the password, a short-lived "second step" ticket. With a
  current code it becomes a normal login token that records the second step ("amr": ["pwd", "otp"]).
- A code works once (its 30-second step is remembered), and one step of clock drift either way is accepted.
- With CM_MFA_REQUIRED=true, platform administrators and supervisors must have logged in with a code before any
  privileged action (require_strong_auth): approvals, merges, sealing, access changes, legal holds, retention decisions,
  integration sources, audit checkpoints, supervisors' status decisions.
"""

import base64
import datetime as dt
import hashlib
import hmac
import uuid

import jwt
import pyotp
import segno
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.casemgmt.enums import OrgRole
from app.casemgmt.errors import Forbidden
from app.core.config import get_settings
from app.db.models import User, UserMfa

ISSUER = "Knight Hawk"
TICKET_PURPOSE = "mfa-second-step"
TICKET_MINUTES = 5
STEP_SECONDS = 30
PRIVILEGED = {OrgRole.SUPER_ADMIN.value, OrgRole.SUPERVISOR.value}


class MfaError(ValueError):
    """A two-step verification request that can't be carried out; the message says why."""


def _fernet() -> Fernet:
    settings = get_settings()
    material = (settings.mfa_key.get_secret_value().encode() if settings.mfa_key is not None
                else hmac.new(settings.jwt_secret.get_secret_value().encode(), b"two-step verification secrets v1", hashlib.sha256).digest())
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def _secret(row: UserMfa) -> str:
    return _fernet().decrypt(row.secret_encrypted.encode()).decode()


def required_for(user: User) -> bool:
    return get_settings().cm_mfa_required and user.org_role in PRIVILEGED


def enabled(session: Session, user: User) -> bool:
    row = session.get(UserMfa, user.id)
    return row is not None and row.confirmed_at is not None


def status(session: Session, user: User) -> dict:
    row = session.get(UserMfa, user.id)
    return {"enabled": row is not None and row.confirmed_at is not None, "confirmed_at": row.confirmed_at if row else None,
            "required": required_for(user), "verified_now": bool(getattr(user, "mfa_verified", False)),
            "setup_pending": row is not None and row.confirmed_at is None}


def start(session: Session, user: User) -> dict:
    """A new secret, not yet active: the QR code and the key to type. Replaces an unfinished set-up."""
    row = session.get(UserMfa, user.id)
    if row is not None and row.confirmed_at is not None:
        raise MfaError("Two-step verification is already on. Turn it off first (with a code) to set it up again.")
    secret = pyotp.random_base32()
    encrypted = _fernet().encrypt(secret.encode()).decode()
    if row is None:
        session.add(UserMfa(user_id=user.id, secret_encrypted=encrypted))
    else:
        row.secret_encrypted, row.last_step = encrypted, None
    session.flush()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=ISSUER)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": segno.make(uri, error="m").svg_data_uri(scale=5, border=2)}


def _step(secret: str, code: str, last_step: int | None) -> int | None:
    """The 30-second step a code belongs to, if it is current (±1 step) and wasn't used before."""
    code = (code or "").replace(" ", "").strip()
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    now = int(dt.datetime.now(dt.UTC).timestamp()) // STEP_SECONDS
    for step in (now, now - 1, now + 1):
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return None if last_step is not None and step <= last_step else step
    return None


def confirm(session: Session, user: User, code: str) -> None:
    row = session.get(UserMfa, user.id)
    if row is None:
        raise MfaError("Start the set-up first")
    if row.confirmed_at is not None:
        raise MfaError("Two-step verification is already on")
    step = _step(_secret(row), code, row.last_step)
    if step is None:
        raise MfaError("That code isn't valid. Check that the phone's clock is right, and enter the code shown now.")
    row.last_step, row.confirmed_at = step, dt.datetime.now(dt.UTC)
    session.flush()


def check(session: Session, user: User, code: str) -> bool:
    """A login's second step: a current, unused code of the user's confirmed secret."""
    row = session.get(UserMfa, user.id)
    if row is None or row.confirmed_at is None:
        return False
    step = _step(_secret(row), code, row.last_step)
    if step is None:
        return False
    row.last_step = step
    session.flush()
    return True


def disable(session: Session, user: User, code: str) -> None:
    if not check(session, user, code):
        raise MfaError("That code isn't valid: two-step verification stays on")
    session.delete(session.get(UserMfa, user.id))
    session.flush()


# ---------------------------------------------------------------- the second step of a login


def _ticket_key() -> bytes:
    return hmac.new(get_settings().jwt_secret.get_secret_value().encode(), b"two-step login ticket v1", hashlib.sha256).digest()


def issue_ticket(user: User) -> str:
    now = dt.datetime.now(dt.UTC)
    claims = {"sub": str(user.id), "iat": now, "exp": now + dt.timedelta(minutes=TICKET_MINUTES), "jti": uuid.uuid4().hex,
              "purpose": TICKET_PURPOSE}
    return jwt.encode(claims, _ticket_key(), algorithm="HS256")


def read_ticket(ticket: str) -> uuid.UUID | None:
    try:
        claims = jwt.decode(ticket, _ticket_key(), algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
        return uuid.UUID(claims["sub"]) if claims.get("purpose") == TICKET_PURPOSE else None
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def require_strong_auth(actor: User, action: str) -> None:
    """Privileged actions: refused (403) for platform administrators and supervisors who didn't log in with a code,
    when the organisation requires it (CM_MFA_REQUIRED)."""
    if required_for(actor) and not getattr(actor, "mfa_verified", False):
        raise Forbidden(f"Two-step verification is required for {action}. Turn it on under Account, then log in again with a code.")
