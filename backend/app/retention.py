"""Deleting data after its retention period (Step 14.3).

- Uploaded "new case" documents, with everything derived from them, after UPLOAD_RETENTION_DAYS (default 30).
- Audit entries after AUDIT_RETENTION_DAYS, but only if that is set. How long an audit trail must be kept
  is for your organisation to decide (docs/steps/14-5-*); until then nothing is deleted from it.

Each run is itself recorded in the audit log, with what it deleted.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.audit.log import AuditLog
from app.core.enums import AuditOutcome
from app.db.models import AuditEvent, Upload
from app.uploads.service import delete_upload


@dataclass
class RetentionResult:
    uploads: int
    audit_events: int
    upload_cutoff: dt.datetime
    audit_cutoff: dt.datetime | None  # None: audit entries are kept
    dry_run: bool


def apply_retention(
    session: Session,
    audit: AuditLog,
    data_dir: Path,
    upload_days: int,
    audit_days: int | None,
    *,
    dry_run: bool = False,
    now: dt.datetime | None = None,
) -> RetentionResult:
    now = now or dt.datetime.now(dt.UTC)
    upload_cutoff = now - dt.timedelta(days=upload_days)
    audit_cutoff = now - dt.timedelta(days=audit_days) if audit_days else None

    old_uploads = list(session.scalars(select(Upload).where(Upload.created_at < upload_cutoff)))
    old_audit = 0
    if audit_cutoff:
        old_audit = session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.occurred_at < audit_cutoff))

    if not dry_run:
        for upload in old_uploads:
            delete_upload(session, data_dir, upload)  # the file and every derived row
        if audit_cutoff:
            session.execute(delete(AuditEvent).where(AuditEvent.occurred_at < audit_cutoff))
            session.commit()

    result = RetentionResult(len(old_uploads), old_audit, upload_cutoff, audit_cutoff, dry_run)
    audit.record(
        "retention.run",
        AuditOutcome.SUCCESS,
        username="system:retention",
        details={
            "dry_run": dry_run,
            "uploads_deleted": 0 if dry_run else result.uploads,
            "uploads_due": result.uploads,
            "audit_events_deleted": 0 if dry_run else result.audit_events,
            "audit_events_due": result.audit_events,
            "upload_cutoff": upload_cutoff.isoformat(),
            "audit_cutoff": audit_cutoff.isoformat() if audit_cutoff else None,
        },
    )
    return result
