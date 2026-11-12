"""CDR Analysis session bridge.

Validates the host user's login and case access, then sets an httpOnly
cdr_session cookie that the CDR proxy layer validates on every request.
No CDR credentials are ever returned to the browser in the response body.
"""
import datetime as dt
import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.auth.dependencies import CurrentUser, get_access_context
from app.cases.queries import get_visible_case
from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/cdr", tags=["cdr"])

Access = Annotated[AccessContext, Depends(get_access_context)]
DbSession = Annotated[Session, Depends(get_db)]

COOKIE_NAME = "cdr_session"
COOKIE_MAX_AGE = 3600  # 1 hour


class CdrSession(BaseModel):
    """Public fields returned to the browser — no credentials."""

    case_id: str
    display_name: str
    role: str
    msisdn_rule: str
    timezone: str


def _make_session_cookie(
    key: str, subject: str, analyst_id: str, role: str, case_id: str
) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "purpose": "cdr_session",
        "sub": subject,
        "analyst_id": analyst_id,
        "role": role,
        "case_id": case_id,
        "iat": now,
        "exp": now + dt.timedelta(seconds=COOKIE_MAX_AGE),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, key, algorithm="HS256")


@router.get("/session", response_model=CdrSession)
def get_cdr_session(
    case_id: Annotated[str, Query(description="The host display_id of the case to open in CDR")],
    response: Response,
    user: CurrentUser,
    access: Access,
    db: DbSession,
) -> CdrSession:
    """Verify case access and set a short-lived httpOnly cdr_session cookie."""
    case = get_visible_case(db, access, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case not accessible")

    settings = get_settings()
    cookie_value = _make_session_cookie(
        key=settings.jwt_secret.get_secret_value(),
        subject=user.username,
        analyst_id=str(user.id),
        role=user.role,
        case_id=case_id,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="strict",
        secure=settings.environment != "development",
        max_age=COOKIE_MAX_AGE,
        path="/api/cdr",
    )
    return CdrSession(
        case_id=case_id,
        display_name=user.display_name,
        role=user.role,
        msisdn_rule=settings.cdr_msisdn_rule,
        timezone=settings.cdr_timezone,
    )
