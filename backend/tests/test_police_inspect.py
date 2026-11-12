"""Adapting to a real police export by settings (format.json), and inspecting an export safely."""

import csv
import io
import json
import shutil
from pathlib import Path

import pytest

from app.connectors.police_records.connector import PoliceRecordsConnector
from app.connectors.police_records.export_format import ExportFormat, FormatError
from app.connectors.police_records.fields import RAW_DIR
from app.connectors.police_records.inspect import inspect_export

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "police-records-FICTIONAL"
# How a real export might differ from the template: other column names, file name and date style.
RENAMED = {
    "fir_number": "FIR No", "fir_year": "Year", "police_station_code": "PS Code", "police_station_name": "Police Station",
    "registration_date": "Reg Date", "occurrence_date": "Date of Occurrence", "complainant_name": "Complainant",
    "accused_names": "Accused", "brief_facts": "Brief Facts", "investigation_status": "Status",
}


def renamed_export(folder: Path) -> Path:
    """The fictional sample, rewritten as such a real export would look."""
    shutil.copytree(SAMPLE, folder)
    rows = list(csv.DictReader(io.StringIO((folder / "records.csv").read_text(encoding="utf-8"), newline="")))
    (folder / "records.csv").unlink()
    with (folder / "fir_register.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=[RENAMED.get(k, k) for k in rows[0]])
        writer.writeheader()
        for row in rows:
            for date_field in ("registration_date", "occurrence_date", "final_report_date"):
                if row[date_field]:
                    day, month, year = row[date_field].split("-")
                    row[date_field] = f"{year}-{month}-{day} 10:30:00"  # a timestamp, not a plain date
            writer.writerow({RENAMED.get(k, k): v for k, v in row.items()})
    return folder


def test_the_fictional_sample_matches_the_template_and_no_personal_data_is_shown():
    lines, suggestion = inspect_export(SAMPLE, ExportFormat())
    report = "\n".join(lines)

    assert "NOT FOUND" not in report
    assert "3 row(s)" in report
    assert "0 row(s) incomplete, 0 duplicate(s)" in report
    assert "2 of 2 document file(s) present" in report
    assert "'Under investigation' x2" in report  # code values are shown...
    for personal in ("Fictional Complainant One", "Fictional Accused A", "Inspector Fictional Officer", "cotton yarn"):
        assert personal not in report  # ...personal data and narratives never are
    assert "'note': 0% empty, 1 different values" in report  # unrecognised column: counts only
    assert "FICTIONAL SAMPLE" not in report
    assert set(suggestion) == {"_comment"}  # nothing to change


def test_a_differently_laid_out_export_is_handled_by_a_format_file_not_code(tmp_path):
    folder = renamed_export(tmp_path / RAW_DIR / "real-like")

    lines, suggestion = inspect_export(folder, ExportFormat(records_file="fir_register.csv"))

    assert suggestion["records_file"] == "fir_register.csv"
    assert suggestion["columns"] == RENAMED  # every renamed column recognised
    assert suggestion["date_formats"] == ["%Y-%m-%d %H:%M:%S"]
    assert "dates readable 100%" in "\n".join(lines)

    (folder / "format.json").write_text(json.dumps(suggestion), encoding="utf-8")
    records = list(PoliceRecordsConnector(tmp_path, "real-like").iter_records())

    assert [r.display_id for r in records] == ["FIR-PS9999-2026-0001", "FIR-PS9999-2026-0002", "FIR-PS9999-2026-0003"]
    assert records[0].dates[0].value.isoformat() == "2026-07-14"
    assert [p.name for p in records[0].parties][:1] == ["Fictional Complainant One"]
    assert records[0].warnings == []
    assert records[2].sensitivity == "confidential" and records[2].parties == []  # protection rules unchanged


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('{"columns": {"fir_no": "FIR No"}}', "fir_no is not a template field"),
        ('{"records_file": "../secret.csv"}', "records_file must be a plain file name"),
        ('{"colums": {}}', "unknown setting"),
        ("not json", "can't be read as JSON"),
    ],
)
def test_mistakes_in_a_format_file_are_reported(tmp_path, content, message):
    (tmp_path / "format.json").write_text(content, encoding="utf-8")

    with pytest.raises(FormatError, match=message):
        ExportFormat.for_folder(tmp_path)
