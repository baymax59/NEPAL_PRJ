"""Find historical cases similar to a whole document: an uploaded new case, or an existing case.

Two signals, merged by rank (Reciprocal Rank Fusion, as in hybrid search):

1. Text. Each passage of the new case is compared with the stored passages (pgvector). For each
   historical case, every new-case passage keeps its closest match there (if close enough).
   Text similarity = the average of those best matches over *all* new-case passages, counting 0
   where there is none. So a case scores high only when much of the new case is echoed in it,
   not because one sentence happens to match.
2. Shared provisions. Provisions cited by both, weighted by rarity: sharing "Section 27 of the
   Evidence Act" says more than sharing Article 14, which many judgments cite.
"""

import datetime as dt
import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.cases.queries import filter_conditions
from app.db.models import Case, DocumentChunk, DocumentProvision, Upload
from app.embeddings.model import Embedder
from app.explain.citations import case_citations
from app.explain.service import page_label
from app.schemas.cases import CaseFilters, CaseSummary, ProvisionCitation
from app.schemas.similar import (
    PassageExcerpt,
    PassagePair,
    QueryDocumentInfo,
    SimilarCase,
    SimilarCasesResponse,
)

MAX_QUERY_PASSAGES = 60  # long documents are sampled evenly, to keep the search fast
NEIGHBOURS_PER_PASSAGE = 25
RRF_K = 10
PAIRS_SHOWN = 3
EXCERPT_WORDS = 60
SEMANTIC_UNAVAILABLE = "Text comparison unavailable (embedding model not loaded); only shared provisions were used."


@dataclass
class QueryPassage:
    page_start: int | None
    page_end: int | None
    text: str
    vector: list[float] | None
    # Where it comes from, when the query has several documents (an investigation: "EV-0002 v1, p.3").
    source: str | None = None


@dataclass
class QueryDocument:
    kind: str  # "upload", "case", or "investigation" (a Case Management case at a commit, phase CM-5)
    id: str
    title: str
    page_count: int | None
    passages: list[QueryPassage]
    vectors_model: str | None
    provisions: list[ProvisionCitation]
    exclude_case_id: uuid.UUID | None = None
    # Known only when the query is an existing case: used to compare outcome and year.
    outcome: str | None = None
    primary_date: dt.date | None = None


def sample_evenly(items: list, limit: int) -> list:
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def document_from_upload(upload: Upload) -> QueryDocument:
    models = {chunk.embedding_model for chunk in upload.chunks if chunk.embedding is not None}
    return QueryDocument(
        kind="upload",
        id=str(upload.id),
        title=upload.original_filename,
        page_count=upload.page_count,
        passages=[
            QueryPassage(c.page_start, c.page_end, c.text, list(c.embedding) if c.embedding is not None else None)
            for c in upload.chunks
        ],
        vectors_model=models.pop() if len(models) == 1 else None,
        provisions=[ProvisionCitation(**p) for p in upload.provisions],
    )


def document_from_case(session: Session, case: Case) -> QueryDocument:
    chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.case_id == case.id).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    ).all()
    models = {chunk.embedding_model for chunk in chunks if chunk.embedding is not None}
    return QueryDocument(
        kind="case",
        id=case.display_id,
        title=case.title or case.display_id,
        page_count=sum(d.page_count or 0 for d in case.documents) or None,
        passages=[
            QueryPassage(c.page_start, c.page_end, c.text, list(c.embedding) if c.embedding is not None else None)
            for c in chunks
        ],
        vectors_model=models.pop() if len(models) == 1 else None,
        provisions=case_citations(session, [case.id]).get(case.id, []),
        exclude_case_id=case.id,
        outcome=case.outcome,
        primary_date=case.primary_date,
    )


@dataclass
class _Candidate:
    case_id: uuid.UUID
    score: float = 0.0
    # new-case passage index -> (chunk id, similarity) of its closest passage in this case
    best: dict[int, tuple[int, float]] = field(default_factory=dict)
    text_similarity: float | None = None
    shared_keys: list[str] = field(default_factory=list)


def _case_conditions(access: AccessContext, filters: CaseFilters, exclude: uuid.UUID | None) -> list:
    conditions = [access.case_condition(), *filter_conditions(filters)]
    if exclude is not None:
        conditions.append(Case.id != exclude)
    return conditions


def _text_matches(session, access, filters, doc, used, embedder, min_passage_similarity=None) -> dict[uuid.UUID, _Candidate]:
    bar = embedder.min_passage_similarity if min_passage_similarity is None else min_passage_similarity
    session.execute(text(f"SET LOCAL hnsw.ef_search = {NEIGHBOURS_PER_PASSAGE * 4}"))
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    conditions = _case_conditions(access, filters, doc.exclude_case_id)
    candidates: dict[uuid.UUID, _Candidate] = {}
    for index, passage in enumerate(used):
        if passage.vector is None:
            continue
        distance = DocumentChunk.embedding.cosine_distance(passage.vector)
        rows = session.execute(
            select(DocumentChunk.id, DocumentChunk.case_id, (1 - distance).label("similarity"))
            .join(Case, Case.id == DocumentChunk.case_id)
            .where(DocumentChunk.embedding_model == embedder.model_name, *conditions)
            .order_by(distance)
            .limit(NEIGHBOURS_PER_PASSAGE)
        ).all()
        for row in rows:
            if row.similarity < bar:
                break
            candidate = candidates.setdefault(row.case_id, _Candidate(row.case_id))
            if index not in candidate.best or row.similarity > candidate.best[index][1]:
                candidate.best[index] = (row.id, float(row.similarity))
    for candidate in candidates.values():
        candidate.text_similarity = sum(sim for _, sim in candidate.best.values()) / len(used)
    return candidates


def _provision_matches(session, access, filters, doc) -> dict[uuid.UUID, _Candidate]:
    keys = [p.key for p in doc.provisions]
    if not keys:
        return {}
    visible = select(Case.id).where(*_case_conditions(access, filters, doc.exclude_case_id))
    total_cases = session.scalar(select(func.count()).select_from(visible.subquery()))
    rows = session.execute(
        select(DocumentProvision.case_id, DocumentProvision.provision_key)
        .where(DocumentProvision.provision_key.in_(keys), DocumentProvision.case_id.in_(visible))
        .distinct()
    ).all()
    cited_by = Counter(key for _, key in rows)
    # Rarer provisions say more about similarity (inverse document frequency).
    weight = {key: math.log((total_cases + 1) / (count + 0.5)) for key, count in cited_by.items()}
    candidates: dict[uuid.UUID, _Candidate] = {}
    for case_id, key in rows:
        candidate = candidates.setdefault(case_id, _Candidate(case_id))
        candidate.shared_keys.append(key)
        candidate.score += weight[key]
    return candidates


def find_similar_cases(
    session: Session,
    access: AccessContext,
    embedder: Embedder | None,
    doc: QueryDocument,
    filters: CaseFilters,
    limit: int,
    offset: int,
    min_passage_similarity: float | None = None,
) -> SimilarCasesResponse:
    """`min_passage_similarity` replaces the embedder's bar for passage-to-passage matches (a registered case's notes need a lower one)."""
    used = sample_evenly(doc.passages, MAX_QUERY_PASSAGES)
    notices = []
    if len(used) < len(doc.passages):
        notices.append(f"Long document: compared using {len(used)} of its {len(doc.passages)} passages, spread evenly.")

    text_candidates: dict[uuid.UUID, _Candidate] = {}
    if embedder is not None and doc.vectors_model == embedder.model_name and used:
        text_candidates = _text_matches(session, access, filters, doc, used, embedder, min_passage_similarity)
    elif used:
        notices.append(SEMANTIC_UNAVAILABLE)
    provision_candidates = _provision_matches(session, access, filters, doc)

    # Rank fusion of the two lists.
    by_text = sorted(text_candidates.values(), key=lambda c: (-c.text_similarity, str(c.case_id)))
    by_provisions = sorted(provision_candidates.values(), key=lambda c: (-c.score, str(c.case_id)))
    fused: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in (by_text, by_provisions):
        for position, candidate in enumerate(ranking, start=1):
            fused[candidate.case_id] += 1 / (RRF_K + position)
    order = sorted(fused, key=lambda case_id: (-fused[case_id], str(case_id)))
    best_possible = max(bool(by_text) + bool(by_provisions), 1) / (RRF_K + 1)

    page = order[offset : offset + limit]
    results = _build_results(
        session, doc, used, page, fused, best_possible, text_candidates, provision_candidates
    )
    info = QueryDocumentInfo(
        kind=doc.kind,
        id=doc.id,
        title=doc.title,
        page_count=doc.page_count,
        passages_total=len(doc.passages),
        passages_used=len(used),
        provisions=[p.label for p in doc.provisions],
    )
    return SimilarCasesResponse(query=info, total_cases=len(order), results=results, notices=notices)


def _excerpt(text_: str) -> str:
    words = text_.split()
    return " ".join(words[:EXCERPT_WORDS]) + (" …" if len(words) > EXCERPT_WORDS else "")


def _build_results(session, doc, used, page, fused, best_possible, text_candidates, provision_candidates):
    if not page:
        return []
    cases = {case.id: case for case in session.scalars(select(Case).where(Case.id.in_(page)))}
    citations = case_citations(session, page)
    pair_chunk_ids = {
        chunk_id
        for case_id in page
        if case_id in text_candidates
        for chunk_id, _ in sorted(text_candidates[case_id].best.values(), key=lambda x: -x[1])[:PAIRS_SHOWN]
    }
    chunks = {
        chunk.id: chunk for chunk in session.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(pair_chunk_ids)))
    }
    query_keys = {p.key: p.label for p in doc.provisions}

    results = []
    for case_id in page:
        case = cases[case_id]
        by_text = text_candidates.get(case_id)
        by_provisions = provision_candidates.get(case_id)
        case_cites = citations.get(case_id, [])
        cited_keys = {c.key for c in case_cites}
        shared = [query_keys[k] for k in query_keys if k in cited_keys]
        only_new = [label for key, label in query_keys.items() if key not in cited_keys]
        only_this = [c.label for c in case_cites if c.key not in query_keys][:5]

        pairs = []
        if by_text:
            for index, (chunk_id, similarity) in sorted(by_text.best.items(), key=lambda item: -item[1][1])[:PAIRS_SHOWN]:
                mine, theirs = used[index], chunks[chunk_id]
                pairs.append(
                    PassagePair(
                        similarity=round(similarity, 4),
                        new_case=PassageExcerpt(page_start=mine.page_start, page_end=mine.page_end, text=_excerpt(mine.text),
                                                source=mine.source),
                        similar_case=PassageExcerpt(
                            page_start=theirs.page_start, page_end=theirs.page_end, text=_excerpt(theirs.text)
                        ),
                        similar_case_chunk_id=theirs.id,
                        similar_case_document_id=theirs.document_id,
                    )
                )

        reasons = []
        if by_text:
            best = pairs[0]
            mine = best.new_case.source or f"{page_label(best.new_case.page_start, best.new_case.page_end)} of {_subject(doc)}"
            reasons.append(
                f"{len(by_text.best)} of {len(used)} passages of {_subject(doc)} have a close match here "
                f"(closest: {mine} ↔ "
                f"{page_label(best.similar_case.page_start, best.similar_case.page_end)} here, "
                f"similarity {best.similarity:.2f})"
            )
        if shared:
            reasons.append(f"Both cite: {', '.join(shared[:6])}")

        differences = _differences(doc, case, only_new, only_this)
        results.append(
            SimilarCase(
                case=CaseSummary.model_validate(case),
                relevance=round(100 * fused[case_id] / best_possible),
                match_type="text+provisions" if by_text and by_provisions else ("text" if by_text else "provisions"),
                text_similarity=round(by_text.text_similarity, 4) if by_text else None,
                matched_passages=len(by_text.best) if by_text else 0,
                shared_provisions=shared,
                provisions_only_in_new_case=only_new,
                provisions_only_in_this_case=only_this,
                reasons=reasons,
                differences=differences,
                passage_pairs=pairs,
            )
        )
    return results


def _subject(doc: QueryDocument) -> str:
    return {"upload": "the new case", "investigation": "this investigation"}.get(doc.kind, "the selected case")


def _differences(doc: QueryDocument, case: Case, only_new: list[str], only_this: list[str]) -> list[str]:
    differences = []
    if only_new:
        differences.append(f"Cited in {_subject(doc)}, no citation detected here: {', '.join(only_new[:6])}")
    if only_this:
        differences.append(f"Cited here but not detected in {_subject(doc)}: {', '.join(only_this)}")
    if doc.kind == "case":
        # Both are recorded cases, so their recorded facts can be compared directly.
        if doc.outcome and case.outcome:
            if doc.outcome == case.outcome:
                differences.append(f"Same recorded outcome: {case.outcome}")
            else:
                differences.append(f"Different recorded outcome: {doc.outcome} (this case: {case.outcome})")
        if doc.primary_date and case.primary_date and doc.primary_date.year != case.primary_date.year:
            differences.append(f"Decided in different years: {doc.primary_date.year} vs {case.primary_date.year}")
    else:
        # A new case has no recorded outcome yet; state this case's facts for comparison.
        decided = f"decided {case.primary_date.isoformat()}" if case.primary_date else "decision date not recorded"
        outcome = f"recorded outcome: {case.outcome}" if case.outcome else "no outcome recorded in the source"
        differences.append(f"This case was {decided}; {outcome}")
    return differences
