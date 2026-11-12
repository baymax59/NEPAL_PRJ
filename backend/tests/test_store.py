"""Saving CaseRecords to the database (upsert_case_record)."""

from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import Case
from app.ingestion.store import upsert_case_record

JUDGMENT_PDF = {"doc_type": "judgment", "source_uri": "https://example.org/test-judgment.pdf", "language": "en"}


def test_missing_fields_are_stored_as_null_not_guessed(db_session, make_record):
    case, created = upsert_case_record(db_session, make_record())

    row = db_session.execute(
        text(
            "SELECT title, category, status, summary, outcome, primary_date, missing_fields "
            "FROM cases WHERE id = :id"
        ),
        {"id": case.id},
    ).one()

    assert created
    assert row.title is None
    assert row.category is None
    assert row.status is None
    assert row.summary is None
    assert row.outcome is None
    assert row.primary_date is None
    assert "outcome" in row.missing_fields
    assert "category" in row.missing_fields


def test_full_record_is_stored_with_its_sources(db_session, make_record):
    record = make_record(
        title="Test Petitioner versus Test Respondent",
        court_or_agency="Test Court",
        outcome={"text": "Appeal(s) allowed", "source_field": "disposal_nature"},
        dates=[{"kind": "decision", "value": "2023-12-04", "source_field": "decision_date"}],
        parties=[
            {"role": "petitioner", "name": "Test Petitioner"},
            {"role": "respondent", "name": "Test Respondent"},
        ],
        officials=[{"role": "judge", "name": "Test Judge"}],
        reference_numbers={"cnr": "TESTCNR0001"},
        source_extra={"available_languages": "ENG,HIN"},
        documents=[JUDGMENT_PDF],
    )

    case, _ = upsert_case_record(db_session, record)
    db_session.expire_all()  # force a fresh read from the database
    stored = db_session.get(Case, case.id)

    assert stored.title == "Test Petitioner versus Test Respondent"
    assert stored.outcome == "Appeal(s) allowed"
    assert stored.outcome_source_field == "disposal_nature"
    assert stored.primary_date == date(2023, 12, 4)
    assert stored.primary_date_kind == "decision"
    assert stored.parties[0] == {"role": "petitioner", "name": "Test Petitioner"}
    assert stored.reference_numbers == {"cnr": "TESTCNR0001"}
    assert stored.provenance["connector"] == "test_connector"
    assert stored.sensitivity == "public"
    assert stored.processing_status == "metadata_imported"
    assert [d.source_uri for d in stored.documents] == [JUDGMENT_PDF["source_uri"]]
    assert stored.documents[0].extraction_status == "pending"
    assert "outcome" not in stored.missing_fields
    assert "category" in stored.missing_fields


def test_reimport_updates_the_case_instead_of_duplicating_it(db_session, make_record):
    upsert_case_record(db_session, make_record(title="Old title", documents=[JUDGMENT_PDF]))
    case, created = upsert_case_record(db_session, make_record(title="New title", documents=[JUDGMENT_PDF]))

    count = db_session.scalar(
        select(func.count()).select_from(Case).where(Case.source_record_id == "TEST-001")
    )
    assert not created
    assert count == 1
    assert case.title == "New title"
    assert len(case.documents) == 1


def test_changed_document_file_is_marked_for_re_extraction(db_session, make_record):
    case, _ = upsert_case_record(db_session, make_record(documents=[{**JUDGMENT_PDF, "sha256": "a" * 64}]))
    case.documents[0].extraction_status = "extracted"
    db_session.flush()

    case, _ = upsert_case_record(db_session, make_record(documents=[{**JUDGMENT_PDF, "sha256": "b" * 64}]))

    assert case.documents[0].extraction_status == "pending"


def test_database_itself_rejects_unknown_sensitivity(db_session):
    # Even code that bypasses CaseRecord cannot store an invalid sensitivity level.
    db_session.add(
        Case(display_id="BAD-1", source_system="test_source", source_record_id="BAD-1", sensitivity="top-secret")
    )
    with pytest.raises(IntegrityError, match="ck_cases_sensitivity_allowed"):
        db_session.flush()
