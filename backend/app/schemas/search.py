"""Search request and response."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cases import CaseFilters, CaseSummary

SearchMode = Literal["hybrid", "keyword", "semantic"]

RELEVANCE_NOTE = (
    "Relevance (0-100) orders results within this search: 100 means ranked first by every search "
    "method that found matches (keyword and/or meaning-based); lower ranks score less. It shows how "
    "closely a case's text matches the query. It is not a probability, and it does not mean the "
    "cases are legally equivalent."
)


class SearchRequest(BaseModel):
    """`query` supports web-search syntax: "exact phrase", -excluded, word OR word.

    mode: `hybrid` (default) combines keyword and meaning-based search; `keyword` and
    `semantic` run one method only (useful for comparison and evaluation).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    filters: CaseFilters = Field(default_factory=CaseFilters)
    mode: SearchMode = "hybrid"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1000)


class SnippetPart(BaseModel):
    """A piece of a passage. `match` pieces are the search words: show them highlighted.

    Plain text only: render as text, never as HTML.
    """

    text: str
    match: bool


class Passage(BaseModel):
    chunk_id: int
    document_id: uuid.UUID
    page_start: int | None
    page_end: int | None
    snippet: list[SnippetPart]
    # "keyword": the passage contains the search terms; "semantic": among the passages
    # closest in meaning to the query.
    matched_by: list[Literal["keyword", "semantic"]]
    similarity: float | None  # closeness in meaning to the query (cosine), if computed


class SearchHit(BaseModel):
    case: CaseSummary
    relevance: int = Field(ge=0, le=100)  # see SearchResponse.relevance_note
    match_type: Literal["keyword+semantic", "keyword", "semantic"]
    keyword_rank: float | None  # full-text rank; None if the keywords weren't found
    semantic_similarity: float | None  # of the best passage; None if not among the closest
    matching_passages: int  # passages containing the search terms
    # Short, checkable reasons for the card ("Contains 2 of 3 search words: ...", "Does not contain: ...").
    # Full version: POST /api/cases/{display_id}/explain
    reasons: list[str]
    passages: list[Passage]  # a few of the best, from both methods


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode  # the mode actually used (hybrid falls back to keyword if needed)
    total_cases: int
    results: list[SearchHit]
    notices: list[str] = []
    relevance_note: str = RELEVANCE_NOTE
