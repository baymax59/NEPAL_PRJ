"""Login, current user and audit-log responses."""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: str
    clearance: str


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
