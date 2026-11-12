"""Keyword search using PostgreSQL full-text search over document chunks.

- The query uses web-search syntax (websearch_to_tsquery): words are matched by their stem
  ("appeals" finds "appealed"), "quoted phrases" must appear together, -word excludes,
  and OR gives alternatives.
- Each chunk is ranked with ts_rank_cd; a case's rank is the sum of its best few chunks,
  so one strongly matching passage and several decent ones both count.
- Matching words are marked with control characters by ts_headline, then split into
  plain-text parts. No HTML is produced, so judgment text can't inject markup.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.cases.queries import filter_conditions
from app.db.models import Case, DocumentChunk
from app.schemas.cases import CaseFilters
from app.schemas.search import SnippetPart

PASSAGES_PER_CASE = 3
MARK_START, MARK_END = "\x02", "\x03"
HEADLINE_OPTIONS = (
    f"StartSel={MARK_START}, StopSel={MARK_END}, MaxWords=35, MinWords=15, "
    'MaxFragments=2, FragmentDelimiter=" … "'
)
_MARKED = re.compile(f"({MARK_START}.*?{MARK_END})", re.DOTALL)


@dataclass
class KeywordCandidate:
    case_id: uuid.UUID
    rank: float
    matching_passages: int
    chunk_ids: list[int]  # best first, at most PASSAGES_PER_CASE


# websearch_to_tsquery treats "or" in any letter case as the OR operator, so an everyday query
# such as "pension wrongly fixed or denied" silently became "(... fixed) OR denied" and matched
# almost every judgment (found in the Step 9 evaluation). Only an uppercase OR stays an
# operator, as documented in SearchRequest; "or"/"Or" outside quotes is just a common word.
_LOWERCASE_OR = re.compile(r"(?<![\w-])[oO]r(?![\w-])")


def normalize_query(query: str) -> str:
    parts = query.split('"')
    for i in range(0, len(parts), 2):  # even parts are outside quotes
        parts[i] = _LOWERCASE_OR.sub(" ", parts[i])
    return '"'.join(parts)


def to_tsquery(query: str) -> ColumnElement:
    return func.websearch_to_tsquery("english", normalize_query(query))


def has_search_terms(session: Session, tsquery: ColumnElement) -> bool:
    """False if the query contained only common words ("the", "of"), which are ignored."""
    return session.scalar(select(func.numnode(tsquery))) > 0


def keyword_candidates(
    session: Session, access: AccessContext, tsquery: ColumnElement, filters: CaseFilters, limit: int
) -> tuple[list[KeywordCandidate], int]:
    """Best-matching cases (up to `limit`) and the total number of matching cases."""
    rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
    # Every matching chunk the caller may see, numbered best-first within its case.
    matches = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.case_id,
            rank.label("rank"),
            func.row_number()
            .over(partition_by=DocumentChunk.case_id, order_by=(rank.desc(), DocumentChunk.id))
            .label("position"),
        )
        .join(Case, Case.id == DocumentChunk.case_id)
        .where(DocumentChunk.search_vector.op("@@")(tsquery), access.case_condition(), *filter_conditions(filters))
        .cte("matches")
    )
    is_top = matches.c.position <= PASSAGES_PER_CASE
    case_rank = func.sum(matches.c.rank).filter(is_top)
    rows = session.execute(
        select(
            matches.c.case_id,
            case_rank.label("rank"),
            func.count().label("matching_passages"),
            func.array_agg(aggregate_order_by(matches.c.chunk_id, matches.c.position)).filter(is_top).label("chunks"),
            func.count().over().label("total"),
        )
        .group_by(matches.c.case_id)
        .order_by(case_rank.desc(), matches.c.case_id)
        .limit(limit)
    ).all()
    candidates = [
        KeywordCandidate(row.case_id, float(row.rank), row.matching_passages, list(row.chunks)) for row in rows
    ]
    return candidates, (rows[0].total if rows else 0)


@dataclass
class ChunkSnippet:
    document_id: uuid.UUID
    page_start: int | None
    page_end: int | None
    parts: list[SnippetPart]
    contains_terms: bool  # the chunk itself matches the keyword query
    similarity: float | None  # to the query vector, if one was given


def chunk_snippets(
    session: Session, chunk_ids: list[int], tsquery: ColumnElement, query_vector: list[float] | None
) -> dict[int, ChunkSnippet]:
    """Highlighted snippets for specific chunks, plus how each relates to the query."""
    if not chunk_ids:
        return {}
    # Remove any stray marker characters from the source text before highlighting.
    clean_text = func.translate(DocumentChunk.text, MARK_START + MARK_END, "")
    similarity = (
        (1 - DocumentChunk.embedding.cosine_distance(query_vector)).label("similarity")
        if query_vector is not None
        else None
    )
    columns = [
        DocumentChunk.id,
        DocumentChunk.document_id,
        DocumentChunk.page_start,
        DocumentChunk.page_end,
        func.ts_headline("english", clean_text, tsquery, HEADLINE_OPTIONS).label("headline"),
        DocumentChunk.search_vector.op("@@")(tsquery).label("contains_terms"),
    ]
    if similarity is not None:
        columns.append(similarity)
    rows = session.execute(select(*columns).where(DocumentChunk.id.in_(chunk_ids))).all()
    return {
        row.id: ChunkSnippet(
            document_id=row.document_id,
            page_start=row.page_start,
            page_end=row.page_end,
            parts=split_highlights(row.headline),
            contains_terms=bool(row.contains_terms),
            similarity=round(float(row.similarity), 4) if similarity is not None and row.similarity is not None else None,
        )
        for row in rows
    }


def split_highlights(headline: str) -> list[SnippetPart]:
    parts = []
    for piece in _MARKED.split(headline):
        if piece.startswith(MARK_START):
            parts.append(SnippetPart(text=piece[1:-1], match=True))
        elif piece:
            parts.append(SnippetPart(text=piece, match=False))
    return parts
