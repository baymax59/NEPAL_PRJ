"""Semantic search: find passages whose meaning is close to the query, via pgvector.

Finds related wording even when the words differ ("conviction resting on circumstantial
evidence" vs "no eyewitness; chain of circumstances"). Similarity is a measure of closeness
in meaning between texts, never proof that two cases are legally equivalent.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.cases.queries import filter_conditions
from app.db.models import Case, DocumentChunk
from app.schemas.cases import CaseFilters

# How many nearest passages to collect before grouping them into cases.
CHUNK_POOL = 400


@dataclass
class SemanticCandidate:
    case_id: uuid.UUID
    similarity: float  # of the case's best passage (cosine, -1..1)
    chunks: list[tuple[int, float]] = field(default_factory=list)  # (chunk_id, similarity), best first


def semantic_candidates(
    session: Session,
    access: AccessContext,
    query_vector: list[float],
    *,
    model_name: str,
    min_similarity: float,
    filters: CaseFilters,
    limit: int,
) -> list[SemanticCandidate]:
    # Let the vector index return enough rows, and keep scanning when filters remove some.
    session.execute(text(f"SET LOCAL hnsw.ef_search = {CHUNK_POOL}"))
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    rows = session.execute(
        select(DocumentChunk.id, DocumentChunk.case_id, (1 - distance).label("similarity"))
        .join(Case, Case.id == DocumentChunk.case_id)
        .where(
            DocumentChunk.embedding_model == model_name,  # never mix vectors from different models
            access.case_condition(),
            *filter_conditions(filters),
        )
        .order_by(distance)
        .limit(CHUNK_POOL)
    ).all()

    by_case: dict[uuid.UUID, SemanticCandidate] = {}
    for row in rows:  # already ordered best-first
        if row.similarity < min_similarity:
            break
        candidate = by_case.setdefault(row.case_id, SemanticCandidate(row.case_id, float(row.similarity)))
        candidate.chunks.append((row.id, float(row.similarity)))
    return list(by_case.values())[:limit]
