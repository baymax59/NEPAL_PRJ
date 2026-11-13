"""Login, current user and audit-log responses."""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TokenOut(BaseModel):
    access_token: str  # empty while a second step is needed
    token_type: str = "bearer"
    expires_in: int  # seconds
    # Two-step verification (CM-7): the password was right, and a code is needed. Send the ticket and a current code to
    # POST /api/auth/mfa/login within 5 minutes.
    mfa_required: bool = False
    mfa_ticket: str | None = None


class MfaLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: str = Field(max_length=2000)
    code: str = Field(min_length=6, max_length=10)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)  # the same minimum as everywhere (app/auth/passwords.py)


class MfaCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=10)


class MfaStatus(BaseModel):
    enabled: bool
    confirmed_at: dt.datetime | None
    required: bool  # the organisation requires it for this user's role (privileged actions)
    verified_now: bool  # this login included a code
    setup_pending: bool


class MfaSetup(BaseModel):
    secret: str  # the key to type into the authenticator app, if the QR code can't be scanned
    otpauth_uri: str
    qr_svg: str  # a data: URI of the QR code (SVG)


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_PATTERN = r"^[0-9+()\-. ]{6,40}$"


class ProfileIn(BaseModel):
    """What a person fills in about themselves. All optional; an empty value clears it. Name, officer ID, rank and station are not here: they come from the register."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str | None = Field(None, max_length=200, pattern=EMAIL_PATTERN)
    phone: str | None = Field(None, max_length=40, pattern=PHONE_PATTERN)
    job_title: str | None = Field(None, max_length=100)

    @field_validator("email", "phone", "job_title", mode="before")
    @classmethod
    def _blank_is_nothing(cls, value):
        """An empty box clears the field: it is not an email or phone number that looks wrong."""
        return None if isinstance(value, str) and not value.strip() else value


class ProfileOut(BaseModel):
    username: str
    display_name: str
    org_role: str
    clearance: str
    officer_number: str | None  # from the register: read-only
    rank: str | None
    stations: list[str]
    email: str | None
    phone: str | None
    job_title: str | None
    profile_updated_at: dt.datetime | None
    id: uuid.UUID | None = None
    photo_updated_at: dt.datetime | None = None


class RegisterIn(BaseModel):
    """An officer creating their own login. Nothing but these four things is accepted: the role, clearance and station never come from here."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    officer_number: str = Field(min_length=2, max_length=32, description="the officer ID in the register")
    full_name: str = Field(min_length=3, max_length=200, description="as written in the register")
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=200)
    email: str | None = Field(None, max_length=200, pattern=EMAIL_PATTERN, description="optional: part of the profile")
    phone: str | None = Field(None, max_length=40, pattern=PHONE_PATTERN, description="optional: part of the profile")

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _blank_is_nothing(cls, value):
        """An empty box clears the field: it is not an email or phone number that looks wrong."""
        return None if isinstance(value, str) and not value.strip() else value


class RegisteredOut(BaseModel):
    username: str
    display_name: str
    org_role: str
    station: str
    message: str


class RegistrationStatus(BaseModel):
    enabled: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: str
    clearance: str
    # Case Management (Step 15): the organisation role (investigator, supervisor, super_admin...), which decides the
    # screens offered. The backend checks every request again.
    org_role: str
    organization_id: uuid.UUID | None
    mfa_verified: bool = False  # this login included a two-step verification code
    must_change_password: bool = False  # a temporary password is in use: only /auth/me and /auth/change-password answer
    # The person's own profile (all optional): the screens ask for it until it is filled in.
    email: str | None = None
    phone: str | None = None
    job_title: str | None = None
    profile_updated_at: dt.datetime | None = None
    photo_updated_at: dt.datetime | None = None  # set when the person has a profile photo (GET /api/auth/photo/{id})


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: dt.datetime
    username: str | None
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    client_ip: str | None


class AuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=64)
    outcome: str | None = Field(default=None, max_length=16)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditPage(BaseModel):
    total: int
    events: list[AuditEventOut]
