"""Convert one row of a police-records export into a CaseRecord (Step 14.4, TEMPLATE).

The field list is a placeholder (fields.py) until the real export is known. The rules, though, are meant
to stay:
- Only what the row says is mapped. Nothing is derived or guessed: there is no title, because an FIR
  has none (the case ID is shown instead).
- Police records are never public: "restricted" unless the export marks them "confidential".
- Identities protected by law (victims of sexual offences, children) are never imported: the record
  becomes "confidential" and party names are left out. This default must be confirmed with the data owner.
- Messages about a row never contain personal data: they name the column, not its value.
"""

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.connectors.base import RecordFailure
from app.connectors.police_records.export_format import ExportFormat
from app.connectors.police_records.fields import CONNECTOR_VERSION, FIELDS, ID_FIELDS, SOURCE_SYSTEM
from app.core.enums import Sensitivity
from app.schemas.case_record import CaseRecord

# A document named in the export must be a plain file name inside the export folder (no "../").
SAFE_DOCUMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(pdf|docx|txt)$", re.IGNORECASE)
MIME_TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "txt": "text/plain"}
ID_PART = re.compile(r"[^A-Za-z0-9]+")


@dataclass(frozen=True)
class ExportInfo:
    folder: str  # relative to the data folder, e.g. "police_raw/2026-11-export"
    file_name: str
    sha256: str
    retrieved_at: dt.datetime


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def parse_date(value: str | None, column: str, warnings: list[str], formats: tuple[str, ...]) -> dt.date | None:
    if not value:
        return None
    for fmt in formats:
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    warnings.append(f"{column} is not a recognised date; left empty")  # the value itself isn't repeated
    return None


def map_row(
    row: dict[str, Any], *, export: ExportInfo, source_ref: str, fmt: ExportFormat | None = None
) -> CaseRecord | RecordFailure:
    """`row` uses the template's column names (the connector renames them, see export_format.py)."""
    fmt = fmt or ExportFormat()
    values = {key: clean(value) for key, value in row.items() if key}
    missing_ids = [field for field in ID_FIELDS if not values.get(field)]
    if missing_ids:
        return RecordFailure(source_ref, f"Missing {', '.join(missing_ids)}: the FIR can't be identified")

    station, year, number = (values[field] for field in ID_FIELDS)
    warnings: list[str] = []

    protected = (values.get("protected_identity") or "").lower() in fmt.yes_values
    requested = (values.get("sensitivity") or "").lower()
    if protected or requested == Sensitivity.CONFIDENTIAL:
        sensitivity = Sensitivity.CONFIDENTIAL
    else:
        sensitivity = Sensitivity.RESTRICTED
        if requested and requested != Sensitivity.RESTRICTED:
            warnings.append("sensitivity in the export is lower than 'restricted'; stored as 'restricted'")

    parties = []
    if protected:
        warnings.append("Identities protected by law: party names were not imported")
    else:
        if complainant := values.get("complainant_name"):
            parties.append({"role": "complainant", "name": complainant})
        parties += [
            {"role": "accused", "name": name}
            for part in (row.get("accused_names") or "").split(";")
            if (name := clean(part))
        ]

    registration = parse_date(values.get("registration_date"), "registration_date", warnings, fmt.date_formats)
    occurrence = parse_date(values.get("occurrence_date"), "occurrence_date", warnings, fmt.date_formats)
    report_date = parse_date(values.get("final_report_date"), "final_report_date", warnings, fmt.date_formats)
    dates = [
        {"kind": kind, "value": value, "source_field": field}
        for kind, value, field in (
            ("registration", registration, "registration_date"),  # first: the main date
            ("occurrence", occurrence, "occurrence_date"),
            ("final_report", report_date, "final_report_date"),
        )
        if value
    ]

    report = values.get("final_report_type")
    outcome = {"text": report, "source_field": "final_report_type", "date": report_date} if report else None

    documents = []
    if document := values.get("fir_document"):
        if SAFE_DOCUMENT.fullmatch(document):
            suffix = document.rsplit(".", 1)[1].lower()
            documents.append(
                {
                    "doc_type": "fir",
                    "source_uri": f"{export.folder}/{document}",
                    "local_path": f"{export.folder}/{document}",
                    "mime_type": MIME_TYPES[suffix],
                    "doc_date": registration,
                }
            )
        else:
            warnings.append("fir_document is not a plain PDF, .docx or .txt file name; not imported")

    officer = values.get("investigating_officer")
    unknown = {key: value for key, value in values.items() if key not in FIELDS and value}
    try:
        return CaseRecord.model_validate(
            {
                "source_system": SOURCE_SYSTEM,
                "source_record_id": f"{station}/{year}/{number}",
                "display_id": "FIR-" + "-".join(ID_PART.sub("", part) for part in (station, year, number)),
                "sensitivity": sensitivity,
                "provenance": {
                    "connector": SOURCE_SYSTEM,
                    "connector_version": CONNECTOR_VERSION,
                    "retrieved_at": export.retrieved_at,
                    "source_uri": f"{export.folder}/{export.file_name}",
                    "checksum_sha256": export.sha256,
                },
                "category": values.get("acts_sections"),
                "court_or_agency": values.get("police_station_name"),
                "status": values.get("investigation_status"),
                "summary": values.get("brief_facts"),
                "outcome": outcome,
                "dates": dates,
                "parties": parties,
                "officials": [{"role": "investigating_officer", "name": officer}] if officer else [],
                "reference_numbers": {"fir_number": number, "police_station_code": station},
                "source_extra": {key: value for key in ("district",) if (value := values.get(key))} | unknown,
                "documents": documents,
                "warnings": warnings,
            }
        )
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return RecordFailure(source_ref, f"Invalid record ({', '.join(fields)})")
