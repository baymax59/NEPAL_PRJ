"""Save CaseRecords into the database.

Saving is an "upsert": if the source record was imported before, it is updated in place,
so running an import twice never creates duplicates.

These functions only flush; the caller decides when to commit.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ExtractionStatus
from app.db.models import Case, CaseDocument
from app.schemas.case_record import CaseRecord, DocumentRef


def upsert_case_record(
    session: Session, record: CaseRecord, run_id: uuid.UUID | None = None
) -> tuple[Case, bool]:
    """Insert or update one case. Returns (case, created)."""
    case = session.scalars(
        select(Case).where(
            Case.source_system == record.source_system,
            Case.source_record_id == record.source_record_id,
        )
    ).one_or_none()
    created = case is None
    if case is None:
        case = Case(source_system=record.source_system, source_record_id=record.source_record_id)
        session.add(case)

    primary_date = record.dates[0] if record.dates else None

    case.display_id = record.display_id
    case.title = record.title
    case.category = record.category
    case.court_or_agency = record.court_or_agency
    case.status = record.status
    case.summary = record.summary
    case.outcome = record.outcome.text if record.outcome else None
    case.outcome_source_field = record.outcome.source_field if record.outcome else None
    case.outcome_date = record.outcome.date if record.outcome else None
    case.primary_date = primary_date.value if primary_date else None
    case.primary_date_kind = primary_date.kind if primary_date else None
    case.dates = [d.model_dump(mode="json") for d in record.dates]
    case.parties = [p.model_dump(mode="json") for p in record.parties]
    case.officials = [p.model_dump(mode="json") for p in record.officials]
    case.reference_numbers = dict(record.reference_numbers)
    case.source_extra = record.source_extra
    case.provenance = record.provenance.model_dump(mode="json")
    case.sensitivity = record.sensitivity.value
    case.missing_fields = record.missing_fields
    case.warnings = list(record.warnings)
    case.last_ingestion_run_id = run_id

    _sync_documents(case, record.documents)
    session.flush()
    return case, created


def _sync_documents(case: Case, refs: list[DocumentRef]) -> None:
    """Add new documents and update known ones (matched by source_uri).

    Documents missing from a re-import are kept: removing evidence is a deliberate
    decision, not something an import should do silently.
    """
    existing = {doc.source_uri: doc for doc in case.documents}
    for ref in refs:
        doc = existing.get(ref.source_uri)
        if doc is None:
            doc = CaseDocument(source_uri=ref.source_uri)
            case.documents.append(doc)
        elif ref.sha256 and doc.sha256 and ref.sha256 != doc.sha256:
            # The file itself changed, so its extracted text is out of date.
            doc.extraction_status = ExtractionStatus.PENDING.value
        doc.doc_type = ref.doc_type
        doc.title = ref.title
        doc.language = ref.language
        doc.doc_date = ref.doc_date
        doc.local_path = ref.local_path
        doc.mime_type = ref.mime_type
        doc.sha256 = ref.sha256
