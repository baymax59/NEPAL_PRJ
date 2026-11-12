"""Run an import: take records from any connector and store them, keeping a record of the run.

- Each case is saved inside its own savepoint, so one bad record never stops the import.
- A source record seen twice in one run is reported, not silently merged.
- Results are committed in batches; the IngestionRun row is committed first, so even a
  crashed import leaves a trace of what was attempted.
"""

import datetime as dt
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.connectors.base import RecordFailure, SourceConnector
from app.core.enums import RunStatus
from app.db.models import IngestionRun
from app.ingestion.store import upsert_case_record

MAX_FAILURES_KEPT = 100  # stored on the run for review; the count is always exact


def run_import(
    session: Session,
    connector: SourceConnector,
    parameters: dict[str, Any] | None = None,
    batch_size: int = 50,
) -> IngestionRun:
    run = IngestionRun(
        source_system=connector.source_system,
        connector_version=connector.version,
        parameters=parameters or {},
    )
    session.add(run)
    session.commit()

    stats = {"seen": 0, "created": 0, "updated": 0, "failed": 0, "with_warnings": 0}
    failures: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    def fail(source_ref: str, reason: str) -> None:
        stats["failed"] += 1
        if len(failures) < MAX_FAILURES_KEPT:
            failures.append({"source_ref": source_ref, "reason": reason})

    try:
        for item in connector.iter_records():
            stats["seen"] += 1
            if isinstance(item, RecordFailure):
                fail(item.source_ref, item.reason)
                continue
            if item.source_record_id in seen_ids:
                fail(item.display_id, "Same source record appeared twice in this import; kept the first")
                continue
            seen_ids.add(item.source_record_id)

            try:
                with session.begin_nested():
                    _, created = upsert_case_record(session, item, run_id=run.id)
            except SQLAlchemyError as exc:
                # Only the error type is kept: messages can contain record contents.
                fail(item.display_id, f"Database rejected the record ({type(getattr(exc, 'orig', exc)).__name__})")
                continue

            stats["created" if created else "updated"] += 1
            if item.warnings:
                stats["with_warnings"] += 1
            if (stats["created"] + stats["updated"]) % batch_size == 0:
                session.commit()
    except Exception as exc:
        session.rollback()
        _finish(session, run, RunStatus.FAILED, stats, failures, error=f"{type(exc).__name__}: {exc}")
        raise

    _finish(session, run, RunStatus.PARTIAL if stats["failed"] else RunStatus.SUCCEEDED, stats, failures)
    return run


def _finish(
    session: Session,
    run: IngestionRun,
    status: RunStatus,
    stats: dict[str, int],
    failures: list[dict[str, str]],
    error: str | None = None,
) -> None:
    run.status = status.value
    run.stats = {**stats, "failures": failures}
    run.error_summary = error[:2000] if error else None
    run.finished_at = dt.datetime.now(dt.UTC)
    session.commit()
