"""CaseRecord validation. Plain unit tests: no database needed."""

import pytest
from pydantic import ValidationError

from app.schemas.case_record import CaseRecord


def test_minimal_record_lists_every_missing_core_field(make_record):
    record = make_record()

    assert record.missing_fields == [
        "title",
        "category",
        "court_or_agency",
        "status",
        "summary",
        "outcome",
        "dates",
        "parties",
        "documents",
    ]


def test_blank_strings_become_none_so_they_count_as_missing(make_record):
    record = make_record(title="   ", category="", status=" Pending ")

    assert record.title is None
    assert record.category is None
    assert record.status == "Pending"
    assert "title" in record.missing_fields
    assert "status" not in record.missing_fields


def test_sensitivity_has_no_default(make_record):
    data = make_record().model_dump()
    del data["sensitivity"]

    with pytest.raises(ValidationError, match="sensitivity"):
        CaseRecord.model_validate(data)


def test_unknown_sensitivity_is_rejected(make_record):
    with pytest.raises(ValidationError):
        make_record(sensitivity="top-secret")


def test_unknown_fields_are_rejected_so_connector_typos_fail_loudly(make_record):
    with pytest.raises(ValidationError, match="titel"):
        make_record(titel="Typo in field name")


def test_blank_outcome_text_is_rejected(make_record):
    # A connector must pass outcome=None when the source has no outcome, not an empty one.
    with pytest.raises(ValidationError):
        make_record(outcome={"text": "  ", "source_field": "disposal_nature"})


@pytest.mark.parametrize("bad_id", ["", "has space", "../etc/passwd", "-starts-with-dash", "x" * 65])
def test_display_id_must_be_short_and_url_safe(make_record, bad_id):
    with pytest.raises(ValidationError):
        make_record(display_id=bad_id)


def test_dates_are_parsed_and_validated(make_record):
    record = make_record(dates=[{"kind": "decision", "value": "2023-12-04", "source_field": "decision_date"}])
    assert record.dates[0].value.isoformat() == "2023-12-04"

    with pytest.raises(ValidationError):
        make_record(dates=[{"kind": "decision", "value": "31-02-2023", "source_field": "decision_date"}])
