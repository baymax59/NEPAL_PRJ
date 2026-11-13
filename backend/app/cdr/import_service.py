"""CDR import pipeline: upload → parse → normalize → deduplicate → store.

Each import batch goes through these steps:
  1. The API receives the file and writes an import_batch row (status=pending).
  2. process_batch() is called (synchronously for now).
  3. The file is parsed row by row; MSISDNs are normalized, timestamps adjusted to UTC.
  4. Duplicate fingerprints within the same case are detected.
  5. All records are bulk-inserted; the batch status is updated.
  6. A custody event is written for each lifecycle step.

Design principle (from D1): every step is idempotent — re-processing a batch that failed
mid-way is safe (duplicates are detected and skipped).
"""

import datetime as dt
import hashlib
import uuid
import zoneinfo
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User
from app.cdr.enums import CustodyEventType, ImportStatus, RecordFormat
from app.cdr.models import CdrCustodyEvent, CdrImportBatch, CdrRecord
from app.cdr.msisdn import fingerprint_fields, normalize_msisdn
from app.cdr.parsers.base import ParsedRow
from app.cdr.parsers.csv_parser import parse_csv
from app.cdr.parsers.excel_parser import parse_excel


CDR_DATA_SUBDIR = "cdr_imports"


def _cdr_dir() -> Path:
    return get_settings().data_dir / CDR_DATA_SUBDIR


def _custody(db: Session, batch_id: uuid.UUID, event_type: str, actor: User | None = None, details: dict | None = None) -> None:
    db.add(CdrCustodyEvent(
        import_batch_id=batch_id,
        event_type=event_type,
        actor_id=actor.id if actor else None,
        actor_type="user" if actor else "system",
        occurred_at=dt.datetime.now(dt.UTC),
        details=details or {},
    ))


def receive_file(
    db: Session,
    actor: User,
    case_family_id: uuid.UUID,
    filename: str,
    content: bytes,
    record_format: str,
    msisdn_rule: str,
    source_timezone: str,
) -> CdrImportBatch:
    """Create the import_batch row and persist the raw file. Returns the batch before processing."""
    settings = get_settings()
    file_hash = hashlib.sha256(content).hexdigest()
    now = dt.datetime.now(dt.UTC)

    batch = CdrImportBatch(
        id=uuid.uuid4(),
        case_family_id=case_family_id,
        uploaded_by=actor.id,
        file_name=filename,
        file_size_bytes=len(content),
        file_hash_sha256=file_hash,
        record_format=record_format,
        msisdn_rule=msisdn_rule,
        source_timezone=source_timezone,
        status=ImportStatus.PENDING,
        created_at=now,
    )
    db.add(batch)
    db.flush()

    dest_dir = _cdr_dir() / str(case_family_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{batch.id}.{record_format}"
    dest.write_bytes(content)
    batch.file_path = str(dest.relative_to(settings.data_dir))

    _custody(db, batch.id, CustodyEventType.RECEIVED, actor, details={"file_name": filename, "file_hash": file_hash})
    _custody(db, batch.id, CustodyEventType.HASHED, details={"sha256": file_hash})
    _custody(db, batch.id, CustodyEventType.STORED, details={"path": batch.file_path})
    db.commit()
    return batch


def _parse_timestamp(value: str, tz_name: str) -> tuple[dt.datetime | None, dt.datetime | None, str | None]:
    if not value:
        return None, None, None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%d/%m/%Y %H:%M:%S%z"):
        try:
            aware = dt.datetime.strptime(value.strip(), fmt)
            return aware.replace(tzinfo=None), aware.astimezone(dt.UTC), "source_offset"
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S",
                "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            naive = dt.datetime.strptime(value.strip(), fmt)
            try:
                zone = zoneinfo.ZoneInfo(tz_name)
            except (zoneinfo.ZoneInfoNotFoundError, KeyError):
                zone = dt.UTC
            aware = naive.replace(tzinfo=zone).astimezone(dt.UTC)
            return naive, aware, "import_timezone"
        except ValueError:
            pass
    return None, None, None


def _normalize_direction(raw: str | None) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    if lower in ("mo", "moc", "originating", "out", "outgoing", "o", "mt_sms_out", "sms_out"):
        return "outgoing"
    if lower in ("mt", "mtc", "terminating", "in", "incoming", "i", "mo_sms_in", "sms_in"):
        return "incoming"
    return None


def _normalize_service(raw: str | None) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    if lower in ("voice", "call", "moc", "mtc", "voice_call", "v"):
        return "voice"
    if lower in ("sms", "short_message", "text", "s"):
        return "sms"
    if lower in ("data", "gprs", "lte", "nr", "d"):
        return "data"
    return None


def _normalize_generation(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.upper().strip().replace(" ", "")
    for g in ("2G", "3G", "4G", "5G"):
        if g in upper:
            return g
    return None


def _map_row(parsed: ParsedRow, rule: str, tz_name: str) -> dict[str, Any]:
    m = parsed.mapped
    local_ts, utc_ts, tz_src = _parse_timestamp(m.get("timestamp", ""), tz_name)
    duration = None
    raw_dur = m.get("duration_seconds", "").replace("s", "").strip()
    if raw_dur.isdigit():
        duration = int(raw_dur)
    call_type = m.get("call_type") or None
    return {
        "a_party": m.get("a_party") or None,
        "b_party": m.get("b_party") or None,
        "a_party_canonical": normalize_msisdn(m.get("a_party"), rule),
        "b_party_canonical": normalize_msisdn(m.get("b_party"), rule),
        "msisdn_rule": rule if (m.get("a_party") or m.get("b_party")) else None,
        "timestamp_local": local_ts,
        "timestamp_utc": utc_ts,
        "timestamp_tz_source": tz_src,
        "duration_seconds": duration,
        "call_type": call_type,
        "call_direction": _normalize_direction(call_type or m.get("call_direction")),
        "service_type": _normalize_service(call_type or m.get("service_type")),
        "imei": m.get("imei") or None,
        "imsi": m.get("imsi") or None,
        "cell_id": m.get("cell_id") or None,
        "area_code": m.get("area_code") or None,
        "operator": m.get("operator") or None,
        "network_type": m.get("network_type") or None,
        "network_generation": _normalize_generation(m.get("network_type")),
        "date_range_status": "not_evaluated",
        "source_values": parsed.raw,
    }


def process_batch(db: Session, batch: CdrImportBatch) -> CdrImportBatch:
    """Parse the file, normalize, deduplicate, and bulk-insert all CDR records."""
    now = dt.datetime.now(dt.UTC)

    batch.status = ImportStatus.PROCESSING
    db.add(batch)
    _custody(db, batch.id, CustodyEventType.PROCESSING_STARTED, details={"started_at": now.isoformat()})
    db.commit()

    try:
        file_path = get_settings().data_dir / batch.file_path
        content = file_path.read_bytes()

        if batch.record_format == RecordFormat.CSV:
            rows = list(parse_csv(content))
        else:
            rows = list(parse_excel(content))

        existing_fps: set[str] = set(
            db.scalars(
                select(CdrRecord.record_fingerprint)
                .where(CdrRecord.case_family_id == batch.case_family_id)
                .where(CdrRecord.import_batch_id != batch.id)
            ).all()
        )

        total = len(rows)
        accepted = rejected = duplicate = 0
        seen_fps: set[str] = set()
        records_to_insert: list[dict] = []

        for parsed in rows:
            mapped = _map_row(parsed, batch.msisdn_rule, batch.source_timezone)
            fp = fingerprint_fields(mapped)
            is_dup = fp in existing_fps or fp in seen_fps
            if is_dup:
                duplicate += 1
            else:
                seen_fps.add(fp)
                accepted += 1

            records_to_insert.append({
                "id": uuid.uuid4(),
                "import_batch_id": batch.id,
                "case_family_id": batch.case_family_id,
                "source_row_number": parsed.row_number,
                "record_fingerprint": fp,
                "is_duplicate": is_dup,
                **mapped,
                "created_at": now,
            })

        if records_to_insert:
            db.execute(CdrRecord.__table__.insert(), records_to_insert)

        batch.total_rows = total
        batch.accepted_rows = accepted
        batch.rejected_rows = rejected
        batch.duplicate_rows = duplicate
        batch.status = ImportStatus.COMPLETED if rejected == 0 else ImportStatus.COMPLETED_WITH_ERRORS
        batch.completed_at = dt.datetime.now(dt.UTC)
        db.add(batch)
        _custody(db, batch.id, CustodyEventType.PROCESSING_COMPLETED, details={
            "total": total, "accepted": accepted, "rejected": rejected, "duplicate": duplicate,
        })
        db.commit()

    except Exception as exc:
        db.rollback()
        batch.status = ImportStatus.FAILED
        batch.import_notes = str(exc)[:500]
        batch.completed_at = dt.datetime.now(dt.UTC)
        db.add(batch)
        _custody(db, batch.id, CustodyEventType.PROCESSING_FAILED, details={"error": str(exc)[:200]})
        db.commit()

    return batch
