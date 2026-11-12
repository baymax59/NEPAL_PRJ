"""Turn stored documents into page text and searchable chunks.

For each document: extract -> clean -> store pages -> chunk -> store chunks -> set status.
Re-processing a document replaces its previous pages and chunks.
"""

import datetime as dt
import logging
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import ExtractionStatus, ProcessingStatus
from app.db.models import Case, CaseDocument, DocumentChunk, DocumentPage
from app.documents.chunk import chunk_pages
from app.documents.clean import clean_pages
from app.documents.extract import ExtractionError, extract
from app.explain.indexing import store_provisions
from app.extraction.indexing import store_timeline_and_entities

logger = logging.getLogger(__name__)

# A page with fewer characters than this, but with images, is treated as scanned.
MIN_TEXT_CHARS = 30


def resolve_local_path(data_dir: Path, local_path: str | None) -> Path:
    """The document's file inside data_dir. Refuses paths that point outside it."""
    if not local_path:
        raise ExtractionError("No local copy of this document")
    root = data_dir.resolve()
    path = (root / local_path).resolve()
    if not path.is_relative_to(root):
        raise ExtractionError("Document path points outside the data folder; refused")
    if not path.is_file():
        raise ExtractionError("Document file is missing from the data folder")
    return path


def process_document(session: Session, document: CaseDocument, data_dir: Path) -> None:
    extracted = extract(resolve_local_path(data_dir, document.local_path))
    cleaned = clean_pages([page.text for page in extracted.pages])

    # Replace earlier results. Deleting first avoids clashes on (document_id, page/chunk number).
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    session.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
    session.expire(document, ["pages", "chunks"])

    scanned_pages = []
    page_texts = []
    for page, text in zip(extracted.pages, cleaned, strict=True):
        needs_ocr = len(text) < MIN_TEXT_CHARS and page.has_images
        if needs_ocr:
            scanned_pages.append(page.number)
        page_texts.append((page.number, text))
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=page.number,
                text=text,
                char_count=len(text),
                needs_ocr=needs_ocr,
            )
        )

    store_provisions(session, document, page_texts)
    store_timeline_and_entities(session, document, page_texts)
    chunks = chunk_pages([(number, text) for number, text in page_texts if text])
    session.add_all(
        DocumentChunk(
            document_id=document.id,
            case_id=document.case_id,
            chunk_index=chunk.index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
            word_count=chunk.word_count,
        )
        for chunk in chunks
    )

    warnings = []
    if not chunks:
        status = ExtractionStatus.NEEDS_OCR if scanned_pages else ExtractionStatus.FAILED
        warnings.append("No text could be extracted" + (" (pages look scanned)" if scanned_pages else ""))
    elif len(scanned_pages) > len(extracted.pages) / 2:
        status = ExtractionStatus.NEEDS_OCR
        warnings.append(f"{len(scanned_pages)} of {len(extracted.pages)} pages look scanned; their text is missing")
    else:
        status = ExtractionStatus.EXTRACTED
        if scanned_pages:
            warnings.append(f"Pages {', '.join(map(str, scanned_pages))} look scanned; their text is missing")

    document.extraction_status = status.value
    document.extraction_warnings = warnings
    document.page_count = len(extracted.pages) if extracted.has_page_numbers else None
    document.mime_type = document.mime_type or extracted.mime_type
    document.extractor = extracted.extractor
    document.extracted_at = dt.datetime.now(dt.UTC)
    session.flush()


def _update_case_status(session: Session, case_id) -> None:
    case = session.get(Case, case_id)
    statuses = {doc.extraction_status for doc in case.documents}
    if statuses == {ExtractionStatus.EXTRACTED.value} and case.processing_status == ProcessingStatus.METADATA_IMPORTED:
        case.processing_status = ProcessingStatus.TEXT_EXTRACTED.value


def process_documents(
    session: Session,
    data_dir: Path,
    *,
    reprocess: bool = False,
    limit: int | None = None,
    progress: Callable[[str], None] = print,
) -> dict[str, int]:
    """Process pending documents (or all, with reprocess=True). Commits after each document."""
    query = select(CaseDocument.id).order_by(CaseDocument.created_at)
    if not reprocess:
        query = query.where(CaseDocument.extraction_status == ExtractionStatus.PENDING.value)
    document_ids = session.scalars(query.limit(limit)).all()

    stats = {status.value: 0 for status in ExtractionStatus if status != ExtractionStatus.PENDING}
    for n, document_id in enumerate(document_ids, start=1):
        document = session.get(CaseDocument, document_id)
        try:
            with session.begin_nested():
                process_document(session, document, data_dir)
        except ExtractionError as exc:
            document.extraction_status = ExtractionStatus.FAILED.value
            document.extraction_warnings = [str(exc)]
        except Exception as exc:
            # Keep going: one unreadable file must not stop the batch.
            logger.exception("Unexpected error processing document %s", document_id)
            document.extraction_status = ExtractionStatus.FAILED.value
            document.extraction_warnings = [f"Unexpected error ({type(exc).__name__})"]
        _update_case_status(session, document.case_id)
        session.commit()
        stats[document.extraction_status] += 1
        if n % 10 == 0 or n == len(document_ids):
            progress(f"processed {n}/{len(document_ids)}")
    return stats
