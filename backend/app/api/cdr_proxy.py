"""CDR backend reverse proxy.

All CDR API traffic flows through here. The host validates the cdr_session
cookie, enforces case-scoped access, and injects the correct credentials
server-side before forwarding to D1 / D2 / D3.

Security invariants enforced here:
- D2 X-Analyst-Id is ALWAYS taken from the validated session, never from the browser.
- D3 URL case_id MUST match the session case_id; mismatches return 403.
- The cdr_session cookie is httpOnly; JavaScript cannot read it.
- CDR backend CSP headers are stripped; the host sets its own.
- Requests without a valid cookie are rejected with 401 before forwarding.
"""
import datetime as dt
import uuid
from typing import Annotated

import httpx
import jwt
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.core.config import get_settings

router = APIRouter(prefix="/cdr", tags=["cdr-proxy"])

COOKIE_NAME = "cdr_session"

# Only these headers are forwarded to CDR backends; all others are dropped.
_FORWARD_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "content-length",
    "range",
}

# Strip these from upstream responses before returning to the browser.
_STRIP_RESPONSE_HEADERS = {"content-security-policy", "transfer-encoding", "server"}


def _validate_session(cookie: str, required_case_id: str | None = None) -> dict:
    """Decode and validate the cdr_session cookie JWT.

    Raises 401 for missing/invalid/expired cookie; 403 for case_id mismatch.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            cookie,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "purpose", "case_id"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="CDR session expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CDR session")

    if payload.get("purpose") != "cdr_session":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CDR session purpose")

    if required_case_id is not None and payload["case_id"] != required_case_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CDR session case mismatch")

    return payload


def _session_case(cookie: str) -> str:
    """Extract case_id from a cookie without enforcing a specific value."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            cookie,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["case_id"]},
        )
        return payload["case_id"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CDR session")


def _safe_request_headers(request: Request) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in request.headers.items()
        if k.lower() in _FORWARD_REQUEST_HEADERS
    }


def _clean_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _STRIP_RESPONSE_HEADERS}


async def _proxy(
    request: Request,
    target_url: str,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    headers = _safe_request_headers(request)
    if extra_headers:
        headers.update(extra_headers)
    body = await request.body()
    async with httpx.AsyncClient(timeout=60.0) as client:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
            follow_redirects=True,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_clean_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


def _issue_d1_jwt(key: str, subject: str, role: str, case_id: str) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": subject,
        "case_ids": [case_id],
        "roles": [role],
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, key, algorithm="HS256")


@router.api_route("/proxy/d1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_d1(
    path: str,
    request: Request,
    cdr_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Forward to CDR D1 backend with server-side JWT Bearer auth."""
    if cdr_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No CDR session")

    # D1 has non-case-scoped routes; extract case_id from cookie, then validate.
    cookie_case_id = _session_case(cdr_session)
    case_id_param = request.query_params.get("case_id") or cookie_case_id
    session = _validate_session(cdr_session, required_case_id=case_id_param)

    settings = get_settings()
    extra: dict[str, str] = {}
    if settings.cdr_d1_jwt_key is not None:
        token = _issue_d1_jwt(
            settings.cdr_d1_jwt_key.get_secret_value(),
            subject=session["sub"],
            role=session["role"],
            case_id=session["case_id"],
        )
        extra["authorization"] = f"Bearer {token}"

    target = f"{settings.cdr_d1_api_url.rstrip('/')}/{path}"
    return await _proxy(request, target, extra_headers=extra)


@router.api_route("/proxy/d2/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_d2(
    path: str,
    request: Request,
    cdr_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Forward to CDR D2. X-Analyst-Id is taken from the session; any browser-supplied value is dropped."""
    if cdr_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No CDR session")

    case_id_param = request.query_params.get("case_id")
    if case_id_param:
        session = _validate_session(cdr_session, required_case_id=case_id_param)
    else:
        session = _validate_session(cdr_session)

    # analyst_id comes from the validated session — never from the browser.
    extra = {"x-analyst-id": session["analyst_id"]}
    settings = get_settings()
    target = f"{settings.cdr_d2_api_url.rstrip('/')}/{path}"
    return await _proxy(request, target, extra_headers=extra)


@router.api_route("/cases/{case_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_d3(
    case_id: str,
    path: str,
    request: Request,
    cdr_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Forward to CDR D3. URL case_id must match the session case_id; mismatch returns 403."""
    if cdr_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No CDR session")

    _validate_session(cdr_session, required_case_id=case_id)

    settings = get_settings()
    target = f"{settings.cdr_d3_api_url.rstrip('/')}/api/cdr/cases/{case_id}/{path}"
    return await _proxy(request, target)
