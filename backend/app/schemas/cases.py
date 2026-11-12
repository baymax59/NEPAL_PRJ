"""What the case API accepts and returns.

Empty values are returned as null / [] and never filled in. The frontend shows them as
"Not available in source". Internal details (local file paths) are never returned.
"""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CaseFilters(BaseModel):
    """Filters shared by the case list and search.

    A year filter only matches cases whose date is known: a case with no recorded date
    cannot be said to fall inside a year range.
    """

    model_config = ConfigDict(extra="forbid")

    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    outcome: list[str] = Field(default_factory=list, max_length=20)
    source_system: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def years_in_order(self) -> "CaseFilters":
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("year_from must not be after year_to")
        return self


class CaseListParams(CaseFilters):
    sort: Literal["date_desc", "date_asc", "title"] = "date_desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class PersonOut(BaseModel):
    role: str
    name: str


class CaseDateOut(BaseModel):
    kind: str
    value: dt.date
    source_field: str


class CaseSummary(BaseModel):
    """The fields a result card needs."""

    model_config = ConfigDict(from_attributes=True)

    display_id: str
    title: str | None
    category: str | None
    court_or_agency: str | None
    status: str | None
    outcome: str | None
    primary_date: dt.date | None
    primary_date_kind: str | None
    source_system: str
    reference_numbers: dict[str, str]
    sensitivity: str  # shown to users already cleared to see the case, so they handle it correctly
    processing_status: str
    missing_fields: list[str]


class CaseList(BaseModel):
    total: int
    items: list[CaseSummary]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_type: str
    title: str | None
    language: str | None
    doc_date: dt.date | None
    page_count: int | None
    mime_type: str | None
    source_uri: str
    extraction_status: str
    extraction_warnings: list[str]
    extractor: str | None


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # "judgment" (from the source record), "order_under_appeal" or "dated_mention" (found in the text)
    event_type: str
    event_date: dt.date | None
    date_text: str | None
    description: str
    document_id: uuid.UUID | None
    page_number: int | None
    source_excerpt: str | None
    extraction_method: str


class CourtMentionOut(BaseModel):
    """A court or tribunal named in the case's documents, detected automatically."""

    name: str
    mentions: int
    pages: list[int]


class ProvisionCitation(BaseModel):
    """A statutory provision a case cites, detected automatically from its text."""

    key: str  # stable identifier, e.g. "crpc|section|438"
    label: str  # e.g. "Section 438 CrPC"
    mentions: int
    pages: list[int]


class CaseDetail(CaseSummary):
    """Everything the details page shows, grouped like its sections."""

    # Identification
    source_record_id: str
    dates: list[CaseDateOut]
    # Overview (only what the source records; AI summaries come later and are labelled)
    summary: str | None
    parties: list[PersonOut]
    officials: list[PersonOut]
    # Provisions cited in the case's documents, most-mentioned first (automatically detected)
    provisions: list[ProvisionCitation]
    # Courts and tribunals named in the documents, most-mentioned first (automatically detected)
    courts: list[CourtMentionOut]
    # Outcome, with where it came from
    outcome_source_field: str | None
    outcome_date: dt.date | None
    # Timeline (filled in Step 12)
    timeline: list[TimelineEventOut]
    # Documents
    documents: list[DocumentOut]
    # Data quality and provenance
    warnings: list[str]
    provenance: dict[str, Any]
    source_extra: dict[str, Any]
    attribution: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class CountedValue(BaseModel):
    value: str
    count: int


class YearRange(BaseModel):
    min: int
    max: int


class FilterOptions(BaseModel):
    """Values available for the filter controls, counting only cases the user may see."""

    years: YearRange | None
    outcomes: list[CountedValue]
    source_systems: list[CountedValue]
