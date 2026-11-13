"""Step 14.3: uploads (and, only if configured, audit entries) are deleted after their retention period."""

import datetime as dt
import io

from sqlalchemy import func, select

from app.audit.log import AuditLog
from app.db.models import AuditEvent, Upload, UploadChunk
from app.retention import apply_retention
from app.uploads.service import save_upload

NOW = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.UTC)


def make_upload(session, data_dir, embedder, days_old: int) -> Upload:
    text = io.BytesIO(b"Anticipatory bail was refused by the High Court and the appellant appealed.")
    upload = save_upload(session, data_dir, f"case-{days_old}.txt", text, max_bytes=1_000_000, embedder=embedder)
    upload.created_at = NOW - dt.timedelta(days=days_old)
    session.flush()
    return upload


def audit_entry(session, days_old: int, action: str = "case.view") -> int:
    event = AuditEvent(action=action, outcome="success", details={}, occurred_at=NOW - dt.timedelta(days=days_old))
    session.add(event)
    session.flush()
    return event.id


def exists(session, model, column, value) -> bool:
    return session.scalar(select(func.count()).select_from(model).where(column == value)) > 0


def run(session, data_dir, upload_days=30, audit_days=None, dry_run=False):
    return apply_retention(session, AuditLog(session=session), data_dir, upload_days, audit_days, dry_run=dry_run, now=NOW)


def test_old_uploads_are_deleted_with_their_files_and_passages(db_session, tmp_path, fake_embedder):
    old = make_upload(db_session, tmp_path, fake_embedder, days_old=31)
    recent = make_upload(db_session, tmp_path, fake_embedder, days_old=29)
    old_id, old_file = old.id, tmp_path / old.stored_path
    assert exists(db_session, UploadChunk, UploadChunk.upload_id, old_id)

    result = run(db_session, tmp_path)

    assert result.uploads == 1
    assert not exists(db_session, Upload, Upload.id, old_id)
    assert not exists(db_session, UploadChunk, UploadChunk.upload_id, old_id)  # passages and embeddings
    assert not old_file.exists()
    assert exists(db_session, Upload, Upload.id, recent.id) and (tmp_path / recent.stored_path).exists()


def test_a_dry_run_deletes_nothing(db_session, tmp_path, fake_embedder):
    old = make_upload(db_session, tmp_path, fake_embedder, days_old=400)

    result = run(db_session, tmp_path, dry_run=True)

    assert result.uploads == 1 and result.dry_run
    assert exists(db_session, Upload, Upload.id, old.id) and (tmp_path / old.stored_path).exists()


def test_audit_entries_are_kept_unless_a_period_is_set(db_session, tmp_path):
    ancient, recent = audit_entry(db_session, days_old=3000), audit_entry(db_session, days_old=10)

    run(db_session, tmp_path)  # AUDIT_RETENTION_DAYS not set: the organisation hasn't decided yet
    assert exists(db_session, AuditEvent, AuditEvent.id, ancient)

    result = run(db_session, tmp_path, audit_days=365)
    assert result.audit_events == 1
    assert not exists(db_session, AuditEvent, AuditEvent.id, ancient)
    assert exists(db_session, AuditEvent, AuditEvent.id, recent)


def test_case_management_audit_events_are_never_deleted(db_session, tmp_path):
    """Case history is permanent (docs/case-management/07 §6): its audit trail is outside retention."""
    case_event = audit_entry(db_session, days_old=3000, action="cm.evidence.added")
    other = audit_entry(db_session, days_old=3000)
    assert run(db_session, tmp_path, audit_days=365).audit_events == 1
    assert exists(db_session, AuditEvent, AuditEvent.id, case_event) and not exists(db_session, AuditEvent, AuditEvent.id, other)


def test_every_run_is_audited(db_session, tmp_path, fake_embedder):
    make_upload(db_session, tmp_path, fake_embedder, days_old=31)

    run(db_session, tmp_path)

    event = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "retention.run")).one()
    assert event.username == "system:retention"
    assert event.details["uploads_deleted"] == 1
    assert event.details["audit_cutoff"] is None
