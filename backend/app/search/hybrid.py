"""Hybrid search: combine keyword and meaning-based (semantic) rankings.

Keyword ranks and embedding similarities are on different scales, so they are merged by
*position* with Reciprocal Rank Fusion (RRF): each method contributes 1 / (K + position).
A case ranked well by both methods rises to the top; a case found by only one still appears.

Relevance (0-100) = the case's RRF score divided by the best possible score (first place in
every method that found anything). It orders results within one search; it is not a probability.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.db.models import Case
from app.embeddings.model import Embedder
from app.explain.citations import case_citations
from app.explain.service import build_query_profile, page_label, reasons_for, term_counts
from app.schemas.cases import CaseSummary
from app.schemas.search import SearchHit, SearchRequest, SearchResponse
from app.search.keyword import (
    PASSAGES_PER_CASE,
    KeywordCandidate,
    chunk_snippets,
    has_search_terms,
    keyword_candidates,
    to_tsquery,
)
from app.search.passages import interleave, to_passage
from app.search.semantic import SemanticCandidate, semantic_candidates

logger = logging.getLogger(__name__)

# Dampens the difference between neighbouring positions. 60 is common for long result lists,
# but with lists of tens of cases it made the 40th result score ~61/100. With 10, relevance
# falls off sensibly (5th ≈ 73, 20th ≈ 37, 40th ≈ 22). To be tuned with the Step 9 evaluation.
RRF_K = 10
CANDIDATES_PER_METHOD = 200

STOPWORDS_ONLY_NOTICE = (
    "The search only contains very common words (such as 'the' or 'of'), which are ignored. "
    "Add more specific terms."
)
SEMANTIC_UNAVAILABLE_NOTICE = (
    "Meaning-based search is unavailable (embedding model not loaded), so only keyword matches are shown."
)


@dataclass
class FusedResult:
    case_id: uuid.UUID
    score: float
    keyword: KeywordCandidate | None = None
    semantic: SemanticCandidate | None = None


def fuse(keyword: list[KeywordCandidate], semantic: list[SemanticCandidate]) -> list[FusedResult]:
    """Reciprocal Rank Fusion of two best-first candidate lists."""
    results: dict[uuid.UUID, FusedResult] = {}
    for position, candidate in enumerate(keyword, start=1):
        result = results.setdefault(candidate.case_id, FusedResult(candidate.case_id, 0.0))
        result.keyword = candidate
        result.score += 1 / (RRF_K + position)
    for position, candidate in enumerate(semantic, start=1):
        result = results.setdefault(candidate.case_id, FusedResult(candidate.case_id, 0.0))
        result.semantic = candidate
        result.score += 1 / (RRF_K + position)
    return sorted(results.values(), key=lambda r: (-r.score, str(r.case_id)))


def search(session: Session, access: AccessContext, embedder: Embedder | None, request: SearchRequest) -> SearchResponse:
    mode = request.mode
    notices: list[str] = []

    tsquery = to_tsquery(request.query)
    if not has_search_terms(session, tsquery):
        return SearchResponse(query=request.query, mode=mode, total_cases=0, results=[], notices=[STOPWORDS_ONLY_NOTICE])

    query_vector = None
    if mode != "keyword":
        if embedder is None:
            notices.append(SEMANTIC_UNAVAILABLE_NOTICE)
            if mode == "semantic":
                return SearchResponse(query=request.query, mode=mode, total_cases=0, results=[], notices=notices)
            mode = "keyword"
        else:
            query_vector = embedder.embed_query(request.query)

    keyword, keyword_total = [], 0
    if mode != "semantic":
        keyword, keyword_total = keyword_candidates(session, access, tsquery, request.filters, CANDIDATES_PER_METHOD)

    semantic = []
    if query_vector is not None:
        semantic = semantic_candidates(
            session,
            access,
            query_vector,
            model_name=embedder.model_name,
            min_similarity=embedder.min_similarity,
            filters=request.filters,
            limit=CANDIDATES_PER_METHOD,
        )

    fused = fuse(keyword, semantic)
    # Only methods that found something count towards the maximum: if keyword search found
    # nothing, the best meaning-based match is the best result there is.
    methods_with_results = bool(keyword) + bool(semantic)
    best_possible = max(methods_with_results, 1) / (RRF_K + 1)
    page = fused[request.offset : request.offset + request.limit]

    hits = _build_hits(session, request.query, page, tsquery, query_vector, best_possible)
    # Keyword-only totals are exact; with semantic search the candidate lists are capped.
    total = keyword_total if mode == "keyword" else len(fused)
    return SearchResponse(query=request.query, mode=mode, total_cases=total, results=hits, notices=notices)


def _passage_chunk_ids(result: FusedResult) -> list[int]:
    semantic_ids = [chunk_id for chunk_id, _ in result.semantic.chunks] if result.semantic else []
    keyword_ids = result.keyword.chunk_ids if result.keyword else []
    return interleave(semantic_ids, keyword_ids, PASSAGES_PER_CASE)


def _build_hits(
    session, query: str, page: list[FusedResult], tsquery, query_vector, best_possible: float
) -> list[SearchHit]:
    if not page:
        return []
    case_ids = [r.case_id for r in page]
    cases = {case.id: case for case in session.scalars(select(Case).where(Case.id.in_(case_ids)))}
    chunk_ids = {result.case_id: _passage_chunk_ids(result) for result in page}
    snippets = chunk_snippets(session, [c for ids in chunk_ids.values() for c in ids], tsquery, query_vector)
    # For the card reasons: which query words and provisions each case contains.
    profile = build_query_profile(session, query)
    counts = term_counts(session, case_ids, profile)
    citations = case_citations(session, case_ids)

    hits = []
    for result in page:
        semantic_ids = {chunk_id for chunk_id, _ in result.semantic.chunks} if result.semantic else set()
        passages = [to_passage(chunk_id, snippets[chunk_id], semantic_ids) for chunk_id in chunk_ids[result.case_id]]
        closest = None
        if result.semantic:
            best_chunk, best_similarity = result.semantic.chunks[0]
            best = snippets[best_chunk]
            closest = (page_label(best.page_start, best.page_end), best_similarity)
        reasons = reasons_for(profile, counts.get(result.case_id, {}), citations.get(result.case_id, []), closest)
        hits.append(
            SearchHit(
                case=CaseSummary.model_validate(cases[result.case_id]),
                relevance=round(100 * result.score / best_possible),
                match_type="keyword+semantic"
                if result.keyword and result.semantic
                else ("keyword" if result.keyword else "semantic"),
                keyword_rank=round(result.keyword.rank, 4) if result.keyword else None,
                semantic_similarity=round(result.semantic.similarity, 4) if result.semantic else None,
                matching_passages=result.keyword.matching_passages if result.keyword else 0,
                reasons=reasons,
                passages=passages,
            )
        )
    return hits
