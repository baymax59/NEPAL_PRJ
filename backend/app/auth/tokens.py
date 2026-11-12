"""Signed login tokens (JWT). A token only says *who* the user is; their role, clearance and
active status are read from the database on every request, so changes apply immediately."""

import datetime as dt
import uuid

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """(token, lifetime in seconds)."""
    settings = get_settings()
    lifetime = settings.access_token_minutes * 60
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + dt.timedelta(seconds=lifetime),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM), lifetime


def read_access_token(token: str) -> uuid.UUID | None:
    """The user ID in a valid, unexpired token; None for anything else."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],  # never accept "none" or another algorithm
            options={"require": ["exp", "iat", "sub"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
