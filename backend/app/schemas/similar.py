"""Uploading a new case, and finding historical cases similar to a whole document."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cases import CaseFilters, CaseSummary, ProvisionCitation

SIMILAR_RELEVANCE_NOTE = (
    "Relevance (0-100) orders results for this document: 100 means ranked first both by text similarity "
    "and by shared statutory provisions. Text similarity shows how much of the new case's text has a close "
    "match in the historical case. Neither is a probability, and similar text does not make two cases "
    "legally equivalent: review the matched passages and the differences."
)


class UploadOut(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    mime_type: str
    page_count: int | None
    passages: int
    provisions: list[ProvisionCitation]  # detected automatically
    warnings: list[str]
    created_at: dt.datetime


class SimilarParams(CaseFilters):
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=200)


class SimilarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: CaseFilters = Field(default_factory=CaseFilters)
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=200)


class PassageExcerpt(BaseModel):
    page_start: int | None
    page_end: int | None
    text: str  # the start of the passage, plain text
    source: str | None = None  # which document or note, when the query has several (an investigation)


class PassagePair(BaseModel):
    """A passage of the new case and the passage of the historical case closest to it."""

    similarity: float
    new_case: PassageExcerpt
    similar_case: PassageExcerpt
    similar_case_chunk_id: int
    similar_case_document_id: uuid.UUID


class SimilarCase(BaseModel):
    case: CaseSummary
    relevance: int = Field(ge=0, le=100)
    match_type: Literal["text+provisions", "text", "provisions"]
    # Average over the new case's passages of their closest match in this case (0 where none).
    text_similarity: float | None
    matched_passages: int  # passages of the new case with a close match here
    shared_provisions: list[str]
    provisions_only_in_new_case: list[str]
    provisions_only_in_this_case: list[str]  # the ones this case cites most
    reasons: list[str]
    differences: list[str]  # incl. outcome and decision year when comparing two cases
    passage_pairs: list[PassagePair]  # best few, most similar first


class QueryDocumentInfo(BaseModel):
    kind: Literal["upload", "case", "investigation"]
    id: str
    title: str
    page_count: int | None
    passages_total: int
    passages_used: int  # long documents are sampled evenly
    provisions: list[str]


class SimilarCasesResponse(BaseModel):
    query: QueryDocumentInfo
    total_cases: int
    results: list[SimilarCase]
    notices: list[str] = []
    relevance_note: str = SIMILAR_RELEVANCE_NOTE
