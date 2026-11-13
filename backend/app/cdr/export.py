"""CDR export: CSV download and saving a summary report to the case (Feature 12 / 13)."""
from __future__ import annotations

import csv
import datetime as dt
import io

from sqlalchemy.orm import Session

from app.cdr import analytics
from app.cdr.models import CdrImportBatch, CdrRecord


# ───────────────────────────── CSV export ───────────────────────────────────

_CSV_COLUMNS = [
    "row", "import_batch_id", "source_row_number", "is_duplicate",
    "a_party", "b_party", "a_party_canonical", "b_party_canonical",
    "timestamp_utc", "duration_seconds",
    "call_type", "call_direction", "service_type",
    "imei", "imsi", "cell_id", "area_code",
    "operator", "network_type", "network_generation",
    "record_fingerprint",
]


def generate_csv(records: list[CdrRecord]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for i, r in enumerate(records, 1):
        writer.writerow({
            "row": i,
            "import_batch_id": str(r.import_batch_id),
            "source_row_number": r.source_row_number,
            "is_duplicate": r.is_duplicate,
            "a_party": r.a_party or "",
            "b_party": r.b_party or "",
            "a_party_canonical": r.a_party_canonical or "",
            "b_party_canonical": r.b_party_canonical or "",
            "timestamp_utc": r.timestamp_utc.isoformat() if r.timestamp_utc else "",
            "duration_seconds": r.duration_seconds if r.duration_seconds is not None else "",
            "call_type": r.call_type or "",
            "call_direction": r.call_direction or "",
            "service_type": r.service_type or "",
            "imei": r.imei or "",
            "imsi": r.imsi or "",
            "cell_id": r.cell_id or "",
            "area_code": r.area_code or "",
            "operator": r.operator or "",
            "network_type": r.network_type or "",
            "network_generation": r.network_generation or "",
            "record_fingerprint": r.record_fingerprint,
        })
    return buf.getvalue()


def all_records_csv(db: Session, case_family_id) -> str:
    """Generate a CSV of all non-duplicate CDR records for a case."""
    _, records = analytics.search_records(
        db, case_family_id, include_duplicates=False, limit=50_000, offset=0
    )
    return generate_csv(records)


# ───────────────────────────── Export to case ────────────────────────────────

def build_summary_content(db: Session, case_family_id) -> dict:
    """Build a compact summary dict suitable for storage as a case artifact."""
    stats = analytics.summary_stats(db, case_family_id)
    top = analytics.top_contacts(db, case_family_id, limit=10)
    anomalies = analytics.anomaly_detect(db, case_family_id)
    freq = analytics.frequency_by_hour(db, case_family_id)

    from sqlalchemy import select, func
    batch_count = db.scalar(
        select(func.count()).select_from(CdrImportBatch).where(CdrImportBatch.case_family_id == case_family_id)
    ) or 0

    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "batch_count": batch_count,
        "summary": stats,
        "top_contacts": top[:10],
        "anomaly_count": len(anomalies),
        "high_severity_anomalies": [a for a in anomalies if a.get("severity") == "high"][:5],
        "peak_hours": sorted(freq, key=lambda x: -x["count"])[:3],
        "note": "Full dataset available as CSV export from the CDR Analysis tab.",
    }


def add_to_case(db: Session, actor, family) -> dict:
    """Save a CDR analysis summary as an 'analysis' artifact in the case."""
    from app.casemgmt import engine as ce

    content = build_summary_content(db, family.id)
    title = f"CDR Analysis — {dt.date.today().isoformat()}"

    # Ensure the CDR folder exists before add_note looks it up by name.
    ce.ensure_folder(db, family, actor, "cdr-analysis", system=True)

    # add_note acquires the case lock and writes the history entry.
    artifact, _version = ce.add_note(
        db, actor, family,
        folder="cdr-analysis",
        artifact_type="analysis",
        title=title,
        content=content,
    )
    return {
        "artifact_id": str(artifact.id),
        "display_id": artifact.display_id,
        "title": artifact.title,
        "message": f"CDR analysis saved to case as {artifact.display_id} in the 'cdr-analysis' folder.",
    }
