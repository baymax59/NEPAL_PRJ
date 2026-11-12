"""CaseRecord: the shared shape every data-source connector must produce.

Connectors (Supreme Court judgments now, authorised police records later) convert their
own records into CaseRecord. Everything after that (storage, search, details, chat) only
ever deals with CaseRecord data, so adding a source never requires changing those parts.

Rules:
- Leave a field empty (None / []) when the source does not contain it. Never guess.
- Blank strings are converted to None, so "" can never be mistaken for real data.
- `sensitivity` has no default: each connector must decide it explicitly.
"""

import datetime as dt
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.enums import Sensitivity

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Short, URL-safe case ID shown to users and used in API paths, e.g. "SC-ESCR010007902023".
DISPLAY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class _Strict(BaseModel):
    # Unknown fields are an error, so a typo in a connector fails loudly instead of being dropped.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PersonRef(_Strict):
    role: NonBlankStr  # e.g. "petitioner", "respondent", "judge", "complainant"
    name: NonBlankStr


class CaseDate(_Strict):
    kind: NonBlankStr  # e.g. "decision", "filing", "registration"
    value: dt.date
    source_field: NonBlankStr  # which source field this came from


class Outcome(_Strict):
    text: NonBlankStr  # exactly as recorded, e.g. "Appeal(s) allowed"
    source_field: NonBlankStr
    date: dt.date | None = None


class Provenance(_Strict):
    connector: NonBlankStr
    connector_version: NonBlankStr
    retrieved_at: dt.datetime
    source_uri: str | None = None
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class DocumentRef(_Strict):
    doc_type: NonBlankStr  # e.g. "judgment"
    source_uri: NonBlankStr
    title: str | None = None
    language: str | None = None
    doc_date: dt.date | None = None
    local_path: str | None = None  # relative to the data folder, once downloaded
    mime_type: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CaseRecord(_Strict):
    source_system: NonBlankStr = Field(max_length=64)
    source_record_id: NonBlankStr = Field(max_length=256)
    display_id: str = Field(pattern=DISPLAY_ID_PATTERN)
    sensitivity: Sensitivity
    provenance: Provenance

    title: str | None = None
    category: str | None = None
    court_or_agency: str | None = None
    status: str | None = None
    summary: str | None = None  # only a summary that exists in the source
    outcome: Outcome | None = None

    # Put the most important date first: it is used for sorting and filtering.
    dates: list[CaseDate] = []
    parties: list[PersonRef] = []
    officials: list[PersonRef] = []
    reference_numbers: dict[str, NonBlankStr] = {}
    source_extra: dict[str, Any] = {}
    documents: list[DocumentRef] = []
    warnings: list[str] = []

    @field_validator("title", "category", "court_or_agency", "status", "summary")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def missing_fields(self) -> list[str]:
        """Core fields the source did not provide, shown in the data-quality section."""
        checks = {
            "title": self.title,
            "category": self.category,
            "court_or_agency": self.court_or_agency,
            "status": self.status,
            "summary": self.summary,
            "outcome": self.outcome,
            "dates": self.dates,
            "parties": self.parties,
            "documents": self.documents,
        }
        return [name for name, value in checks.items() if not value]
