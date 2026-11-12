"""The audit log: who did what, when, and with what outcome.

- Written in its own transaction, so the record is kept even if the request then fails.
- Fails closed: if an event can't be written, the request fails instead of going unrecorded.
- Privacy: search text and uploaded file names are never stored. Search text is kept only as a
  keyed fingerprint (HMAC). With the AUDIT_SECRET an investigator can check whether a given
  search was made, but the log alone doesn't reveal what anyone searched for.
"""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AuditOutcome
from app.db.models import AuditEvent, User
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def fingerprint(text: str) -> str:
    key = get_settings().audit_secret.get_secret_value().encode()
    return hmac.new(key, text.strip().encode(), hashlib.sha256).hexdigest()


class AuditLog:
    def __init__(self, client_ip: str | None = None, session: Session | None = None):
        self.client_ip = client_ip
        # Tests pass their own session so audit rows are rolled back with the test.
        self._session = session

    def record(
        self,
        action: str,
        outcome: AuditOutcome,
        *,
        user: User | None = None,
        username: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = AuditEvent(
            user_id=user.id if user else None,
            username=user.username if user else username,
            action=action,
            outcome=outcome.value,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            client_ip=self.client_ip,
        )
        if self._session is not None:
            self._session.add(event)
            self._session.flush()
            return
        try:
            with SessionLocal() as session:
                session.add(event)
                session.commit()
        except Exception:
            logger.exception("Could not write audit event %s", action)
            raise


def get_audit_log(request: Request) -> AuditLog:
    return AuditLog(client_ip=request.client.host if request.client else None)
