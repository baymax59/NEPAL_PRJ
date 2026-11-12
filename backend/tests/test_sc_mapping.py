"""Supreme Court metadata row -> CaseRecord. Uses rows copied from the real 2023 metadata."""

import datetime as dt

from app.connectors.base import RecordFailure
from app.connectors.sc_judgments.manifest import FileEntry
from app.connectors.sc_judgments.mapping import map_row
from app.schemas.case_record import CaseRecord

RETRIEVED = dt.datetime(2026, 11, 3, 10, 0, tzinfo=dt.UTC)
META = FileEntry(
    key="metadata/parquet/year=2023/metadata.parquet",
    source_uri="https://example.org/metadata/parquet/year=2023/metadata.parquet",
    sha256="a" * 64,
    size_bytes=1000,
    retrieved_at=RETRIEVED,
)
PDF = FileEntry(
    key="data/pdf/year=2023/english/2023_15_808_820_EN.pdf",
    source_uri="https://example.org/data/pdf/year=2023/english/2023_15_808_820_EN.pdf",
    sha256="b" * 64,
    size_bytes=2000,
    retrieved_at=RETRIEVED,
)


def real_row(**overrides):
    row = {
        "title": "RAM LAL versus STATE OF RAJASTHAN & ORS.",
        "petitioner": "RAM LAL",
        "respondent": "STATE OF RAJASTHAN & ORS.",
        "description": "",
        "judge": "J.K. MAHESHWARI",
        "author_judge": None,
        "citation": "[2023] 15 S.C.R. 808",
        "case_id": "2023 INSC 1047",
        "cnr": "ESCR010007902023",
        "decision_date": "04-12-2023",
        "disposal_nature": "Appeal(s) allowed",
        "court": "Supreme Court of India",
        "available_languages": "ENG,HIN,PUN",
        "raw_html": "<select class='form-select' onchange=\"get_pdf_lang('1')\">...</select>",
        "path": "2023_15_808_820",
        "nc_display": "2023INSC1047",
        "scraped_at": "2025-06-12T21:53:00.935992",
        "year": "2023",
    }
    row.update(overrides)
    return row


def map_(row, pdf=PDF, pdf_failure=None):
    return map_row(row, metadata_file=META, pdf=pdf, pdf_failure=pdf_failure, source_ref="test row 0")


def test_real_row_maps_to_expected_record():
    record = map_(real_row())

    assert isinstance(record, CaseRecord)
    assert record.source_system == "sc_judgments"
    assert record.source_record_id == "ESCR010007902023"
    assert record.display_id == "SC-ESCR010007902023"
    assert record.sensitivity == "public"
    assert record.title == "RAM LAL versus STATE OF RAJASTHAN & ORS."
    assert record.court_or_agency == "Supreme Court of India"
    assert record.outcome.text == "Appeal(s) allowed"
    assert record.outcome.source_field == "disposal_nature"
    assert record.outcome.date == dt.date(2023, 12, 4)
    assert [(d.kind, d.value) for d in record.dates] == [("decision", dt.date(2023, 12, 4))]
    assert [(p.role, p.name) for p in record.parties] == [
        ("petitioner", "RAM LAL"),
        ("respondent", "STATE OF RAJASTHAN & ORS."),
    ]
    assert [(p.role, p.name) for p in record.officials] == [("judge", "J.K. MAHESHWARI")]
    assert record.reference_numbers == {
        "cnr": "ESCR010007902023",
        "neutral_citation": "2023 INSC 1047",
        "citation": "[2023] 15 S.C.R. 808",
    }
    assert record.provenance.source_uri == META.source_uri
    assert record.provenance.checksum_sha256 == META.sha256
    assert record.documents[0].local_path == "raw/sc_judgments/data/pdf/year=2023/english/2023_15_808_820_EN.pdf"
    assert record.documents[0].sha256 == PDF.sha256
    assert record.warnings == []
    # Only what the dataset genuinely lacks is reported missing.
    assert record.missing_fields == ["category", "status", "summary"]


def test_scraper_html_and_blank_fields_are_never_imported():
    record = map_(real_row())

    assert "raw_html" not in record.source_extra
    assert "<select" not in record.model_dump_json()
    assert "description" not in record.source_extra  # blank in the source
    assert record.source_extra["available_languages"] == "ENG,HIN,PUN"


def test_missing_disposal_means_no_outcome_not_a_guess():
    record = map_(real_row(disposal_nature=""))

    assert record.outcome is None
    assert "outcome" in record.missing_fields


def test_multi_judge_bench_is_split_into_separate_judges():
    record = map_(real_row(judge="A.M. KHANWILKAR, ABHAY S. OKA, C.T. RAVIKUMAR"))

    assert [p.name for p in record.officials] == ["A.M. KHANWILKAR", "ABHAY S. OKA", "C.T. RAVIKUMAR"]


def test_extra_whitespace_in_title_is_tidied():
    record = map_(real_row(title="ELDECO HOUSING AND INDUSTRIES LIMITED  versus ASHOK VIDYARTHI AND OTHERS"))

    assert record.title == "ELDECO HOUSING AND INDUSTRIES LIMITED versus ASHOK VIDYARTHI AND OTHERS"


def test_invalid_date_is_left_empty_with_a_warning():
    record = map_(real_row(decision_date="31-02-2023"))

    assert record.dates == []
    assert record.outcome.date is None
    assert any("decision_date" in w for w in record.warnings)


def test_missing_pdf_is_a_warning_not_a_failure():
    record = map_(real_row(), pdf=None, pdf_failure="HTTP 404")

    assert isinstance(record, CaseRecord)
    assert record.documents == []
    assert record.warnings == ["Judgment PDF not available (HTTP 404)"]


def test_row_without_cnr_is_reported_as_failure():
    result = map_(real_row(cnr="  "))

    assert isinstance(result, RecordFailure)
    assert "CNR" in result.reason


def test_two_judgments_sharing_a_neutral_citation_stay_separate():
    # Real situation in 2022: two different judgments both carry "2022 INSC 740".
    first = map_(real_row(case_id="2022 INSC 740", cnr="ESCR010006082022"))
    second = map_(real_row(case_id="2022 INSC 740", cnr="ESCR010004692022"))

    assert first.source_record_id != second.source_record_id
    assert first.display_id != second.display_id
