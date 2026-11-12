"""Step 14.4: the police-records connector TEMPLATE, with the FICTIONAL sample export (samples/)."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

from app.connectors.base import RecordFailure
from app.connectors.police_records.connector import PoliceRecordsConnector
from app.connectors.police_records.fields import RAW_DIR
from app.connectors.police_records.mapping import ExportInfo, map_row
from app.core.config import get_settings
from app.documents.processing import process_documents
from app.ingestion.pipeline import run_import

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "police-records-FICTIONAL"
EXPORT = ExportInfo(folder="police_raw/test", file_name="records.csv", sha256="0" * 64,
                    retrieved_at=dt.datetime(2026, 11, 1, tzinfo=dt.UTC))
ROW = {
    "fir_number": "0001", "fir_year": "2026", "police_station_code": "PS9999",
    "police_station_name": "Example Nagar Police Station (fictional)", "district": "Example District (fictional)",
    "registration_date": "14-07-2026", "occurrence_date": "02/07/2026", "acts_sections": "BNS 318(4), 316(2)",
    "complainant_name": "Fictional Complainant One", "accused_names": "Fictional Accused A; Fictional Accused B",
    "investigating_officer": "Inspector Fictional Officer", "investigation_status": "Under investigation",
    "final_report_type": "", "final_report_date": "", "brief_facts": "FICTIONAL. An advance was paid.",
    "sensitivity": "restricted", "protected_identity": "no", "fir_document": "FICT-0001.txt", "note": "FICTIONAL SAMPLE",
}


def mapped(**changes):
    return map_row({**ROW, **changes}, export=EXPORT, source_ref="records.csv record 1")


def test_a_row_becomes_a_restricted_case_record_with_only_what_the_row_says():
    record = mapped()

    assert record.display_id == "FIR-PS9999-2026-0001"
    assert record.source_record_id == "PS9999/2026/0001"
    assert record.sensitivity == "restricted"
    assert record.title is None  # an FIR has no title; nothing is made up
    assert record.court_or_agency == "Example Nagar Police Station (fictional)"
    assert record.category == "BNS 318(4), 316(2)"
    assert [(d.kind, d.value) for d in record.dates] == [("registration", dt.date(2026, 7, 14)), ("occurrence", dt.date(2026, 7, 2))]
    assert [(p.role, p.name) for p in record.parties] == [
        ("complainant", "Fictional Complainant One"), ("accused", "Fictional Accused A"), ("accused", "Fictional Accused B")]
    assert [(o.role, o.name) for o in record.officials] == [("investigating_officer", "Inspector Fictional Officer")]
    assert record.outcome is None  # no final report yet
    assert record.reference_numbers == {"fir_number": "0001", "police_station_code": "PS9999"}
    assert record.source_extra == {"district": "Example District (fictional)", "note": "FICTIONAL SAMPLE"}
    assert record.documents[0].local_path == "police_raw/test/FICT-0001.txt"
    assert record.warnings == []


def test_a_final_report_is_the_recorded_outcome():
    record = mapped(final_report_type="Chargesheet filed", final_report_date="30-09-2026")

    assert (record.outcome.text, record.outcome.source_field, record.outcome.date) == (
        "Chargesheet filed", "final_report_type", dt.date(2026, 9, 30))
    assert record.dates[-1].kind == "final_report"


def test_identities_protected_by_law_are_never_imported():
    record = mapped(protected_identity="Yes", sensitivity="restricted")

    assert record.sensitivity == "confidential"
    assert record.parties == []
    assert "Fictional Complainant One" not in record.model_dump_json()
    assert record.warnings == ["Identities protected by law: party names were not imported"]


@pytest.mark.parametrize(
    ("given", "stored", "warned"),
    [("restricted", "restricted", False), ("", "restricted", False), ("confidential", "confidential", False),
     ("public", "restricted", True), ("internal", "restricted", True)],
)
def test_police_records_are_never_less_than_restricted(given, stored, warned):
    record = mapped(sensitivity=given)

    assert record.sensitivity == stored
    assert bool(record.warnings) == warned


def test_rows_that_cant_be_identified_are_reported_without_personal_data():
    failure = mapped(fir_number="", complainant_name="Fictional Person Named Here")

    assert isinstance(failure, RecordFailure)
    assert failure.reason == "Missing fir_number: the FIR can't be identified"
    assert "Fictional Person" not in failure.reason


def test_bad_dates_and_unsafe_document_names_are_flagged_not_guessed():
    record = mapped(registration_date="31-02-2026", fir_document="../../secrets.txt")

    assert [d.kind for d in record.dates] == ["occurrence"]
    assert record.documents == []
    assert record.warnings == [
        "registration_date is not a recognised date; left empty",  # the value itself isn't repeated
        "fir_document is not a plain PDF, .docx or .txt file name; not imported",
    ]


def test_the_connector_reads_an_export_folder_including_line_breaks_inside_fields(tmp_path):
    folder = tmp_path / RAW_DIR / "export1"
    shutil.copytree(SAMPLE, folder)
    text = (folder / "records.csv").read_text(encoding="utf-8")
    # This field is quoted in the CSV, so a line break inside it is legal (exports from Excel do this).
    (folder / "records.csv").write_text(text.replace("FICTIONAL. A motorcycle", "FICTIONAL.\nA motorcycle"), encoding="utf-8")

    records = list(PoliceRecordsConnector(tmp_path, "export1").iter_records())

    assert [r.display_id for r in records] == ["FIR-PS9999-2026-0001", "FIR-PS9999-2026-0002", "FIR-PS9999-2026-0003"]
    assert records[1].summary.startswith("FICTIONAL. A motorcycle")  # the line break inside quotes is kept as one field
    assert [r.sensitivity.value for r in records] == ["restricted", "restricted", "confidential"]
    assert records[0].provenance.checksum_sha256 is not None


@pytest.fixture
def imported(db_session, tmp_path, monkeypatch, app_overrides):
    """The fictional export imported into the test database, its FIR texts processed into passages."""
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    shutil.copytree(SAMPLE, tmp_path / RAW_DIR / "fictional")
    run = run_import(db_session, PoliceRecordsConnector(tmp_path, "fictional"), parameters={"authorisation": "test"})
    process_documents(db_session, tmp_path, progress=lambda _: None)
    return run


def visible(client) -> list[str]:
    return sorted(item["display_id"] for item in client.get("/api/cases", params={"source_system": "police_records"}).json()["items"])


def found(client, query="advance for cotton yarn") -> list[str]:
    response = client.post("/api/search", json={"query": query, "mode": "keyword"})
    return [hit["case"]["display_id"] for hit in response.json()["results"]]


def test_imported_police_records_are_seen_only_by_users_cleared_for_them(imported, client_as):
    assert imported.stats["created"] == 3
    viewer = client_as("pat", role="viewer", clearance="public")
    analyst = client_as("rita", role="analyst", clearance="restricted")
    admin = client_as("ada", role="admin", clearance="confidential")

    assert visible(viewer) == [] and found(viewer) == []
    assert viewer.get("/api/cases/FIR-PS9999-2026-0001").status_code == 404  # same answer as a missing case
    assert visible(analyst) == ["FIR-PS9999-2026-0001", "FIR-PS9999-2026-0002"]
    assert found(analyst) == ["FIR-PS9999-2026-0001"]  # its FIR text was processed and is searchable
    assert analyst.get("/api/cases/FIR-PS9999-2026-0003").status_code == 404  # confidential
    assert visible(admin) == ["FIR-PS9999-2026-0001", "FIR-PS9999-2026-0002", "FIR-PS9999-2026-0003"]
