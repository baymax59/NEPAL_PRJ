"""Processing stored documents into pages and chunks in the database."""

from sqlalchemy import func, select, text

from app.db.models import Case, CaseDocument, DocumentChunk, DocumentPage, DocumentProvision
from app.documents.processing import process_documents
from app.ingestion.store import upsert_case_record

PAGES = [
    ["The appellant challenged the ex-parte decree.", "The trial court had ordered demolition."],
    ["The appeals are allowed and the matter is remanded."],
]


def quiet(_message: str) -> None:
    pass


def store_case(session, make_record, local_path: str) -> Case:
    record = make_record(
        documents=[{"doc_type": "judgment", "source_uri": "https://example.org/j.pdf", "local_path": local_path}]
    )
    case, _ = upsert_case_record(session, record)
    session.commit()
    return case


def only_document(session) -> CaseDocument:
    return session.scalars(select(CaseDocument)).one()


def test_pages_and_chunks_are_stored_and_the_case_is_marked(db_session, make_record, make_pdf, tmp_path):
    make_pdf("raw/test/judgment.pdf", PAGES)
    case = store_case(db_session, make_record, "raw/test/judgment.pdf")

    stats = process_documents(db_session, tmp_path, progress=quiet)

    document = only_document(db_session)
    assert stats["extracted"] == 1
    assert document.extraction_status == "extracted"
    assert document.page_count == 2
    assert document.extractor.startswith("pypdfium2")
    assert document.extracted_at is not None
    assert [p.page_number for p in document.pages] == [1, 2]
    assert "ex-parte decree" in document.pages[0].text
    assert len(document.chunks) >= 1
    assert document.chunks[0].page_start == 1
    assert document.chunks[-1].page_end == 2
    assert db_session.get(Case, case.id).processing_status == "text_extracted"


def test_cited_provisions_are_stored_with_their_pages(db_session, make_record, make_pdf, tmp_path):
    make_pdf(
        "raw/test/judgment.pdf",
        [["The accused was convicted under Section 302 IPC."], ["Section 302 IPC and Article 21 were argued."]],
    )
    store_case(db_session, make_record, "raw/test/judgment.pdf")

    process_documents(db_session, tmp_path, progress=quiet)

    rows = db_session.execute(
        select(DocumentProvision.label, DocumentProvision.mention_count, DocumentProvision.pages).order_by(
            DocumentProvision.label
        )
    ).all()
    assert [tuple(row) for row in rows] == [("Article 21 of the Constitution", 1, [2]), ("Section 302 IPC", 2, [1, 2])]


def test_keyword_search_index_is_filled_automatically(db_session, make_record, make_pdf, tmp_path):
    make_pdf("raw/test/judgment.pdf", PAGES)
    store_case(db_session, make_record, "raw/test/judgment.pdf")
    process_documents(db_session, tmp_path, progress=quiet)

    # "appeal" matches "appeals" because the index stores word stems.
    matches = db_session.scalar(
        text("SELECT count(*) FROM document_chunks WHERE search_vector @@ plainto_tsquery('english', 'appeal')")
    )
    assert matches >= 1


def test_reprocessing_replaces_previous_results(db_session, make_record, make_pdf, tmp_path):
    make_pdf("raw/test/judgment.pdf", PAGES)
    store_case(db_session, make_record, "raw/test/judgment.pdf")
    process_documents(db_session, tmp_path, progress=quiet)
    first = (
        db_session.scalar(select(func.count()).select_from(DocumentPage)),
        db_session.scalar(select(func.count()).select_from(DocumentChunk)),
    )

    process_documents(db_session, tmp_path, reprocess=True, progress=quiet)

    second = (
        db_session.scalar(select(func.count()).select_from(DocumentPage)),
        db_session.scalar(select(func.count()).select_from(DocumentChunk)),
    )
    assert second == first


def test_only_pending_documents_are_processed_by_default(db_session, make_record, make_pdf, tmp_path):
    make_pdf("raw/test/judgment.pdf", PAGES)
    store_case(db_session, make_record, "raw/test/judgment.pdf")
    process_documents(db_session, tmp_path, progress=quiet)

    assert sum(process_documents(db_session, tmp_path, progress=quiet).values()) == 0


def test_missing_file_is_marked_failed_with_the_reason(db_session, make_record, tmp_path):
    case = store_case(db_session, make_record, "raw/test/missing.pdf")

    process_documents(db_session, tmp_path, progress=quiet)

    document = only_document(db_session)
    assert document.extraction_status == "failed"
    assert document.extraction_warnings == ["Document file is missing from the data folder"]
    assert db_session.get(Case, case.id).processing_status == "metadata_imported"


def test_path_outside_the_data_folder_is_refused(db_session, make_record, make_pdf, tmp_path):
    make_pdf("outside.pdf", PAGES)
    store_case(db_session, make_record, "../outside.pdf")

    process_documents(db_session, tmp_path / "data", progress=quiet)

    assert "outside the data folder" in only_document(db_session).extraction_warnings[0]


def test_scanned_document_is_marked_as_needing_ocr(db_session, make_record, make_pdf, tmp_path):
    make_pdf("raw/test/scan.pdf", [None, None, ["Certified copy"]])
    store_case(db_session, make_record, "raw/test/scan.pdf")

    process_documents(db_session, tmp_path, progress=quiet)

    document = only_document(db_session)
    assert document.extraction_status == "needs_ocr"
    assert [p.needs_ocr for p in document.pages] == [True, True, False]
    assert "2 of 3 pages look scanned" in document.extraction_warnings[0]
