"""Search inside a case (spec: "find every mention of this phone number in the case").

Keyword search (PostgreSQL full text, the same syntax as the knowledge-base search: stems, "quoted phrases",
-excluded words, OR) and meaning-based search (pgvector) over the passages of what the user may see in the
case, merged by rank (Reciprocal Rank Fusion). Results are grouped by document or note, best first, with
highlighted snippets and the pages they are on. Highlights are plain-text parts, never HTML.
"""

from collections import defaultdict

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from app.casemgmt.enums import TextStatus
from app.casemgmt.intelligence import index
from app.casemgmt.intelligence.scope import Source, source_view
from app.casemgmt.models import ObjectChunk
from app.embeddings.model import Embedder
from app.search.hybrid import RRF_K, SEMANTIC_UNAVAILABLE_NOTICE, STOPWORDS_ONLY_NOTICE
from app.search.keyword import HEADLINE_OPTIONS, MARK_END, MARK_START, has_search_terms, split_highlights, to_tsquery

CANDIDATES = 300  # passages per method, before grouping
PASSAGES_PER_SOURCE = 4
NOTHING_READ = "Nothing in this case has been read for Case Intelligence yet: prepare its documents first."


def _keys(keys) -> object:
    return tuple_(ObjectChunk.source_kind, ObjectChunk.sha256).in_(list(keys))


def _snippets(session: Session, chunk_ids: list[int], tsquery, query_vector) -> dict[int, dict]:
    if not chunk_ids:
        return {}
    clean_text = func.translate(ObjectChunk.text, MARK_START + MARK_END, "")
    columns = [ObjectChunk.id, ObjectChunk.page_start, ObjectChunk.page_end,
               func.ts_headline("english", clean_text, tsquery, HEADLINE_OPTIONS).label("headline"),
               ObjectChunk.search_vector.op("@@")(tsquery).label("contains_terms")]
    if query_vector is not None:
        columns.append((1 - ObjectChunk.embedding.cosine_distance(query_vector)).label("similarity"))
    rows = session.execute(select(*columns).where(ObjectChunk.id.in_(chunk_ids))).all()
    return {row.id: {"page_start": row.page_start, "page_end": row.page_end, "snippet": split_highlights(row.headline),
                     "contains_terms": bool(row.contains_terms),
                     "similarity": round(float(row.similarity), 4) if query_vector is not None and row.similarity is not None else None}
            for row in rows}


def search_case(session: Session, embedder: Embedder | None, sources: list[Source], query: str, mode: str, limit: int) -> dict:
    """Passages of these sources matching the query, grouped by source. `sources` must already be the user's view."""
    notices: list[str] = []
    empty = {"mode": mode, "total_sources": 0, "total_passages": 0, "results": [], "notices": notices}
    by_key = index.keys_by_source(sources)
    keys = {k for k, t in index.texts_for(session, by_key).items() if t.status == TextStatus.INDEXED}
    tsquery = to_tsquery(query)
    if not has_search_terms(session, tsquery):
        notices.append(STOPWORDS_ONLY_NOTICE)
        return empty
    if not keys:
        notices.append(NOTHING_READ)
        return empty

    query_vector = None
    if mode != "keyword":
        if embedder is None:
            notices.append(SEMANTIC_UNAVAILABLE_NOTICE)
            if mode == "semantic":
                return empty
            mode = "keyword"
        else:
            query_vector = embedder.embed_query(query)

    scores: dict[int, float] = defaultdict(float)
    key_of: dict[int, tuple[str, str]] = {}
    keyword_ids: set[int] = set()
    semantic_ids: set[int] = set()
    mentions: dict[tuple[str, str], int] = {}
    if mode != "semantic":
        matches = ObjectChunk.search_vector.op("@@")(tsquery)
        rank = func.ts_rank_cd(ObjectChunk.search_vector, tsquery)
        rows = session.execute(select(ObjectChunk.id, ObjectChunk.source_kind, ObjectChunk.sha256)
                               .where(_keys(keys), matches).order_by(rank.desc(), ObjectChunk.id).limit(CANDIDATES)).all()
        for position, row in enumerate(rows, start=1):
            scores[row.id] += 1 / (RRF_K + position)
            key_of[row.id] = (row.source_kind, row.sha256)
            keyword_ids.add(row.id)
        # Every matching passage counts, not only the best ones ("every mention").
        mentions = {(r.source_kind, r.sha256): r.n for r in session.execute(
            select(ObjectChunk.source_kind, ObjectChunk.sha256, func.count().label("n")).where(_keys(keys), matches)
            .group_by(ObjectChunk.source_kind, ObjectChunk.sha256))}
    if query_vector is not None:
        session.execute(text(f"SET LOCAL hnsw.ef_search = {CANDIDATES}"))
        session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        distance = ObjectChunk.embedding.cosine_distance(query_vector)
        rows = session.execute(select(ObjectChunk.id, ObjectChunk.source_kind, ObjectChunk.sha256, (1 - distance).label("similarity"))
                               .where(_keys(keys), ObjectChunk.embedding_model == embedder.model_name)
                               .order_by(distance).limit(CANDIDATES)).all()
        for position, row in enumerate(r for r in rows if r.similarity >= embedder.min_similarity):
            scores[row.id] += 1 / (RRF_K + position + 1)
            key_of[row.id] = (row.source_kind, row.sha256)
            semantic_ids.add(row.id)

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for chunk_id in sorted(scores, key=lambda c: (-scores[c], c)):
        groups[key_of[chunk_id]].append(chunk_id)
    page = list(groups.items())[:limit]
    snippets = _snippets(session, [c for _, ids in page for c in ids[:PASSAGES_PER_SOURCE]], tsquery, query_vector)

    results = []
    for key, chunk_ids in page:
        holders = by_key[key]
        passages = []
        for chunk_id in chunk_ids[:PASSAGES_PER_SOURCE]:
            found = snippets[chunk_id]
            matched_by = (["keyword"] if chunk_id in keyword_ids or found["contains_terms"] else []) + (
                ["semantic"] if chunk_id in semantic_ids else [])
            passages.append({"chunk_id": chunk_id, "page_start": found["page_start"], "page_end": found["page_end"],
                             "snippet": found["snippet"], "matched_by": matched_by, "similarity": found["similarity"]})
        results.append({"source": source_view(holders[0]), "also_in": [source_view(s) for s in holders[1:]],
                        # Passages containing the words (all of them, not only those shown); else the close ones found.
                        "matching_passages": mentions.get(key) or len(chunk_ids),
                        "passages": passages})
    if mode == "hybrid" and not keyword_ids:
        notices.append("No passage contains all the words; the results are close in meaning only.")
    return {"mode": mode, "total_sources": len(groups), "total_passages": len(scores), "results": results, "notices": notices}
