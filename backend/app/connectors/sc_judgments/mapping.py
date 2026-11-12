"""Convert one row of Supreme Court metadata into a CaseRecord.

Field-by-field decisions are documented in docs/DATASET.md. In short:
- Identity is the CNR. The neutral citation (`case_id`, e.g. "2022 INSC 740") is NOT unique
  in this dataset (7 values are shared by different judgments in 2022-23), so it is kept only
  as a reference number.
- Only what the row actually says is mapped. The dataset has no category, status or summary,
  so those stay empty. `description` is always blank in the years checked; if a later year
  fills it, it goes to source_extra because its meaning is undocumented.
- `raw_html` is a scraper artefact and is never imported.
"""

import datetime as dt
from typing import Any

from pydantic import ValidationError

from app.connectors.base import RecordFailure
from app.connectors.sc_judgments.manifest import FileEntry
from app.connectors.sc_judgments.source import CONNECTOR_VERSION, RAW_DIR, SOURCE_SYSTEM
from app.core.enums import Sensitivity
from app.schemas.case_record import CaseRecord

# Kept for reference on the details page, without being part of the shared schema.
EXTRA_FIELDS = ("available_languages", "nc_display", "scraped_at", "year", "path", "description")


def clean(value: Any) -> str | None:
    """Collapse runs of whitespace; blank or missing becomes None."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def map_row(
    row: dict[str, Any],
    *,
    metadata_file: FileEntry,
    pdf: FileEntry | None,
    pdf_failure: str | None,
    source_ref: str,
) -> CaseRecord | RecordFailure:
    cnr = clean(row.get("cnr"))
    if cnr is None:
        return RecordFailure(source_ref, "Row has no CNR, so it cannot be identified reliably")

    warnings: list[str] = []

    decision_date = None
    raw_date = clean(row.get("decision_date"))
    if raw_date:
        try:
            decision_date = dt.datetime.strptime(raw_date, "%d-%m-%Y").date()
        except ValueError:
            warnings.append(f"decision_date {raw_date!r} is not a valid DD-MM-YYYY date; left empty")

    disposal = clean(row.get("disposal_nature"))
    outcome = (
        # The disposal is recorded in the judgment delivered on the decision date.
        {"text": disposal, "source_field": "disposal_nature", "date": decision_date} if disposal else None
    )

    parties = [
        {"role": role, "name": name}
        for role in ("petitioner", "respondent")
        if (name := clean(row.get(role)))
    ]

    # Multi-judge benches are comma-separated: "D.Y. CHANDRACHUD, A.S. BOPANNA".
    judges = [name for part in (row.get("judge") or "").split(",") if (name := clean(part))]
    officials = [{"role": "judge", "name": name} for name in judges]
    if author := clean(row.get("author_judge")):
        officials.append({"role": "author_judge", "name": author})

    reference_numbers = {
        key: value
        for key, value in {
            "cnr": cnr,
            "neutral_citation": clean(row.get("case_id")),
            "citation": clean(row.get("citation")),
        }.items()
        if value
    }

    documents = []
    if pdf is not None:
        documents.append(
            {
                "doc_type": "judgment",
                "source_uri": pdf.source_uri,
                "language": "en",
                "doc_date": decision_date,
                "local_path": str(RAW_DIR / pdf.key),
                "mime_type": "application/pdf",
                "sha256": pdf.sha256,
            }
        )
    else:
        warnings.append(f"Judgment PDF not available ({pdf_failure or 'not downloaded'})")

    try:
        return CaseRecord.model_validate(
            {
                "source_system": SOURCE_SYSTEM,
                "source_record_id": cnr,
                "display_id": f"SC-{cnr}",
                "sensitivity": Sensitivity.PUBLIC,
                "provenance": {
                    "connector": SOURCE_SYSTEM,
                    "connector_version": CONNECTOR_VERSION,
                    "retrieved_at": metadata_file.retrieved_at,
                    "source_uri": metadata_file.source_uri,
                    "checksum_sha256": metadata_file.sha256,
                },
                "title": clean(row.get("title")),
                "court_or_agency": clean(row.get("court")),
                "outcome": outcome,
                "dates": [{"kind": "decision", "value": decision_date, "source_field": "decision_date"}]
                if decision_date
                else [],
                "parties": parties,
                "officials": officials,
                "reference_numbers": reference_numbers,
                "source_extra": {key: value for key in EXTRA_FIELDS if (value := clean(row.get(key)))},
                "documents": documents,
                "warnings": warnings,
            }
        )
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        return RecordFailure(source_ref, f"Invalid record ({', '.join(fields)})")
