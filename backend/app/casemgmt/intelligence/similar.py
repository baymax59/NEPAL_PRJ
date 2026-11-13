"""Similar cases for an investigation (spec §21 Similar Cases; docs/case-management/02 Part C.1).

The query is the investigation as it stands, as far as the user may see it: its case summary,
notes and analyses, and the text of its documents. Two kinds of results, shown separately because they are
different things:

- Past cases in the knowledge base (court judgments, imported records), found by the existing similar-case
  search (similar/service.py), within the user's clearance and grants.
- Other investigations of the user's organisation that the user may open. Found the
  same way: passages close in meaning, provisions cited by both, and one more signal only investigations have:
  the same file (identical SHA-256) is evidence in both.

Every result says why it matched and how the cases differ, and can be linked to the investigation.
Similar text does not make two cases the same; METHOD_NOTE says so.
"""

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.casemgmt import queries
from app.casemgmt.access import case_condition
from app.casemgmt.case_types import case_type
from app.casemgmt.enums import ArtifactType, TextSourceKind, TextStatus
from app.casemgmt.intelligence import index
from app.casemgmt.intelligence.scope import GENERATED_TYPES, Source
from app.casemgmt.intelligence.scope import sources as case_sources
from app.casemgmt.links import FOLDER as LINK_FOLDER
from app.casemgmt.models import ArtifactVersion, CaseFamily, ObjectChunk
from app.casemgmt.storage import EvidenceStore
from app.core.config import get_settings
from app.db.models import User
from app.embeddings.model import Embedder
from app.schemas.cases import CaseFilters, ProvisionCitation
from app.similar.service import (
    MAX_QUERY_PASSAGES,
    NEIGHBOURS_PER_PASSAGE,
    RRF_K,
    QueryDocument,
    QueryPassage,
    find_similar_cases,
    sample_evenly,
)

MAX_OTHER_CASES = 100  # the most recent investigations the user may open
OTHER_EMBED_LIMIT = 400  # passages of other investigations embedded per request, at most (the rest next time)
PAIRS_SHOWN = 3
EXCERPT_WORDS = 50
METHOD_NOTE = (
    "Found automatically by comparing this investigation's text (summary, notes and documents you may see) "
    "with past cases and other investigations: passages close in meaning, statutory provisions cited by both, "
    "and, between investigations, identical files. It shows why a case was found. It does not mean the cases are "
    "legally the same, or that the same people are involved: check the passages before linking a case."
)
# Not compared: links repeat the linked case's title, and generated timelines and reports repeat the documents.
NOT_COMPARED = {ArtifactType.LINK.value, *GENERATED_TYPES}


def _comparable(sources: list[Source]) -> list[Source]:
    return [s for s in sources if s.artifact_type not in NOT_COMPARED]


def _excerpt(text: str) -> str:
    words = text.split()
    return " ".join(words[:EXCERPT_WORDS]) + (" …" if len(words) > EXCERPT_WORDS else "")


def _provisions(texts, keys) -> dict[str, ProvisionCitation]:
    merged: dict[str, ProvisionCitation] = {}
    for key in keys:
        text = texts.get(key)
        for p in text.provisions if text is not None else []:
            if p["key"] in merged:
                merged[p["key"]].mentions += p["mentions"]
            else:
                merged[p["key"]] = ProvisionCitation(key=p["key"], label=p["label"], mentions=p["mentions"], pages=[])
    return merged


# ---------------------------------------------------------------- the query: the investigation


@dataclass
class Query:
    doc: QueryDocument
    sources: list[Source]
    keys: set[tuple[str, str]]  # what was compared
    evidence_shas: dict[str, list[Source]]  # exhibits, by file hash (for "the same file")


def query_document(session: Session, family: CaseFamily, sources: list[Source], embedder: Embedder | None) -> Query:
    """The investigation as one query document: its passages in order (summary, notes, documents), with their sources."""
    compared = _comparable(sources)
    order = sorted(compared, key=lambda s: (s.artifact_type != ArtifactType.CASE_SUMMARY.value, s.kind == TextSourceKind.EVIDENCE, s.path))
    by_key = index.keys_by_source(order)
    texts = index.texts_for(session, by_key)
    keys = [k for k in by_key if k in texts and texts[k].status == TextStatus.INDEXED]
    grouped: dict[tuple[str, str], list[ObjectChunk]] = defaultdict(list)
    for chunk in session.scalars(select(ObjectChunk).where(tuple_(ObjectChunk.source_kind, ObjectChunk.sha256).in_(keys))
                                 .order_by(ObjectChunk.chunk_index)) if keys else []:
        grouped[(chunk.source_kind, chunk.sha256)].append(chunk)
    passages = []
    model = embedder.model_name if embedder else None
    for key in keys:
        source = by_key[key][0]
        for chunk in grouped[key]:
            vector = list(chunk.embedding) if chunk.embedding is not None and chunk.embedding_model == model else None
            passages.append(QueryPassage(chunk.page_start, chunk.page_end, chunk.text, vector,
                                         source=source.label(chunk.page_start, chunk.page_end)))
    provisions = sorted(_provisions(texts, keys).values(), key=lambda p: (-p.mentions, p.label))
    doc = QueryDocument(kind="investigation", id=family.display_id, title=family.title, page_count=None, passages=passages,
                        vectors_model=model if any(p.vector is not None for p in passages) else None,
                        provisions=provisions)
    shas: dict[str, list[Source]] = defaultdict(list)
    for source in compared:
        if source.kind == TextSourceKind.EVIDENCE:
            shas[source.sha256].append(source)
    return Query(doc, sources, set(keys), shas)


# ---------------------------------------------------------------- links already made


def linked_targets(session: Session, sources: list[Source]) -> tuple[set[str], set[str]]:
    """(case family IDs, knowledge-base display IDs) this case already links to (active links the user may see)."""
    version_ids = [s.version_id for s in sources if s.artifact_type == ArtifactType.LINK.value and s.path.startswith(LINK_FOLDER + "/")]
    families, knowledge = set(), set()
    for content in session.scalars(select(ArtifactVersion.content).where(ArtifactVersion.id.in_(version_ids))) if version_ids else []:
        if (target := (content or {}).get("target") or {}).get("case_id"):
            families.add(str(target["case_id"]))
        if (case := (content or {}).get("knowledge_case") or {}).get("display_id"):
            knowledge.add(str(case["display_id"]))
    return families, knowledge


# ---------------------------------------------------------------- other investigations


@dataclass
class Other:
    family: CaseFamily
    sources: list[Source]


def other_investigations(session: Session, viewer: User, family: CaseFamily) -> list[Other]:
    """The other cases the viewer may open, with what the viewer may read in each."""
    families = list(session.scalars(
        select(CaseFamily).where(CaseFamily.id != family.id, case_condition(viewer))
        .order_by(CaseFamily.created_at.desc()).limit(MAX_OTHER_CASES)))
    return [Other(other, _comparable(case_sources(session, viewer, other))) for other in families]


@dataclass
class _Candidate:
    family_id: uuid.UUID
    best: dict[int, tuple[int, float, tuple[str, str]]] = field(default_factory=dict)  # query passage -> (chunk, similarity, key)
    text_similarity: float = 0.0
    provision_score: float = 0.0
    shared_provisions: list[str] = field(default_factory=list)
    shared_files: list[dict] = field(default_factory=list)


def _match_investigations(session: Session, query: Query, others: list[Other], embedder: Embedder | None,
                          used: list[QueryPassage]) -> dict[uuid.UUID, _Candidate]:
    key_families: dict[tuple[str, str], set[uuid.UUID]] = defaultdict(set)
    for other in others:
        for source in other.sources:
            key_families[source.key].add(other.family.id)
    texts = index.texts_for(session, key_families)
    indexed = [k for k, t in texts.items() if t.status == TextStatus.INDEXED]
    candidates: dict[uuid.UUID, _Candidate] = {}

    if embedder is not None and query.doc.vectors_model == embedder.model_name and indexed:
        for i, passage in enumerate(used):
            if passage.vector is None:
                continue
            distance = ObjectChunk.embedding.cosine_distance(passage.vector)
            rows = session.execute(
                select(ObjectChunk.id, ObjectChunk.source_kind, ObjectChunk.sha256, (1 - distance).label("similarity"))
                .where(tuple_(ObjectChunk.source_kind, ObjectChunk.sha256).in_(indexed), ObjectChunk.embedding_model == embedder.model_name)
                .order_by(distance).limit(NEIGHBOURS_PER_PASSAGE)).all()
            for row in rows:
                if row.similarity < embedder.min_passage_similarity:
                    break
                key = (row.source_kind, row.sha256)
                for family_id in key_families[key]:
                    candidate = candidates.setdefault(family_id, _Candidate(family_id))
                    if i not in candidate.best or row.similarity > candidate.best[i][1]:
                        candidate.best[i] = (row.id, float(row.similarity), key)
        for candidate in candidates.values():
            candidate.text_similarity = sum(sim for _, sim, _ in candidate.best.values()) / len(used)

    # Provisions cited by both, weighted by rarity among these investigations.
    query_keys = {p.key: p.label for p in query.doc.provisions}
    cited = {other.family.id: set(_provisions(texts, {s.key for s in other.sources})) for other in others}
    counts = Counter(key for keys in cited.values() for key in keys if key in query_keys)
    for other in others:
        shared = [key for key in query_keys if key in cited[other.family.id]]
        if shared:
            candidate = candidates.setdefault(other.family.id, _Candidate(other.family.id))
            candidate.shared_provisions = [query_keys[k] for k in shared]
            candidate.provision_score = sum(math.log((len(others) + 1) / (counts[k] + 0.5)) for k in shared)

    # The same file as evidence in both.
    for other in others:
        theirs: dict[str, list[Source]] = defaultdict(list)
        for source in other.sources:
            if source.kind == TextSourceKind.EVIDENCE and source.sha256 in query.evidence_shas:
                theirs[source.sha256].append(source)
        if theirs:
            candidate = candidates.setdefault(other.family.id, _Candidate(other.family.id))
            candidate.shared_files = [{"sha256": sha, "here": [s.display_id for s in query.evidence_shas[sha]],
                                       "there": [s.display_id for s in found]} for sha, found in sorted(theirs.items())]
    return candidates


def similar_investigations(session: Session, viewer: User, family: CaseFamily, query: Query, embedder: Embedder | None,
                           store: EvidenceStore, linked: set[str], limit: int) -> tuple[list[dict], int, list[str]]:
    notices: list[str] = []
    others = other_investigations(session, viewer, family)
    if not others:
        return [], 0, notices
    # Other investigations' notes are indexed now if needed (quick); their documents only by their own requests.
    index.prepare(session, store, embedder, [s for o in others for s in o.sources], evidence_seconds=0,
                  embed_limit=OTHER_EMBED_LIMIT)
    texts = index.texts_for(session, (s.key for o in others for s in o.sources))
    not_ready = sum(1 for o in others for s in o.sources if s.kind == TextSourceKind.EVIDENCE and s.key not in texts
                    and index.unreadable_reason(s) is None)
    if not_ready:
        notices.append(f"{not_ready} document(s) of other investigations haven't been read yet, so they weren't compared. "
                       "They are read when someone works with those cases.")

    used = sample_evenly(query.doc.passages, MAX_QUERY_PASSAGES)
    candidates = _match_investigations(session, query, others, embedder, used)
    rankings = [
        sorted((c for c in candidates.values() if c.best), key=lambda c: (-c.text_similarity, str(c.family_id))),
        sorted((c for c in candidates.values() if c.shared_provisions), key=lambda c: (-c.provision_score, str(c.family_id))),
        sorted((c for c in candidates.values() if c.shared_files), key=lambda c: (-len(c.shared_files), str(c.family_id))),
    ]
    fused: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for position, candidate in enumerate(ranking, start=1):
            fused[candidate.family_id] += 1 / (RRF_K + position)
    best_possible = max(sum(1 for r in rankings if r), 1) / (RRF_K + 1)
    order = sorted(fused, key=lambda f: (-fused[f], str(f)))[:limit]

    by_id = {o.family.id: o for o in others}
    chunk_ids = {chunk for f in order for chunk, _, _ in sorted(candidates[f].best.values(), key=lambda b: -b[1])[:PAIRS_SHOWN]}
    chunks = {c.id: c for c in session.scalars(select(ObjectChunk).where(ObjectChunk.id.in_(chunk_ids)))} if chunk_ids else {}
    results = []
    for family_id in order:
        candidate, other = candidates[family_id], by_id[family_id]
        holders = index.keys_by_source(other.sources)
        pairs = []
        for i, (chunk_id, similarity, key) in sorted(candidate.best.items(), key=lambda item: -item[1][1])[:PAIRS_SHOWN]:
            mine, theirs = used[i], chunks[chunk_id]
            pairs.append({"similarity": round(similarity, 4),
                          "this_case": {"source": mine.source, "page_start": mine.page_start, "page_end": mine.page_end,
                                        "text": _excerpt(mine.text)},
                          "other_case": {"source": holders[key][0].label(theirs.page_start, theirs.page_end),
                                         "page_start": theirs.page_start, "page_end": theirs.page_end, "text": _excerpt(theirs.text)}})
        reasons = []
        if pairs:
            reasons.append(f"{len(candidate.best)} of {len(used)} passages of this investigation have a close match there "
                           f"(closest: {pairs[0]['this_case']['source']} ↔ {pairs[0]['other_case']['source']}, "
                           f"similarity {pairs[0]['similarity']:.2f})")
        if candidate.shared_provisions:
            reasons.append(f"Both cite: {', '.join(candidate.shared_provisions[:6])}")
        for shared in candidate.shared_files[:3]:
            reasons.append(f"The same file is evidence in both: {', '.join(shared['here'])} here and {', '.join(shared['there'])} "
                           f"there")
        here, there = case_type(family.case_type)["label"], case_type(other.family.case_type)["label"]
        differences = [f"Same case type: {here}" if family.case_type == other.family.case_type else f"Case type: {here} here, {there} there",
                       f"That case is {other.family.workflow_status.replace('_', ' ')}"]
        match_type = [name for name, present in (("text", bool(candidate.best)), ("provisions", bool(candidate.shared_provisions)),
                                                 ("same_file", bool(candidate.shared_files))) if present]
        results.append({
            "case": queries.case_ref(other.family),
            "relevance": round(100 * fused[family_id] / best_possible), "match_type": match_type,
            "text_similarity": round(candidate.text_similarity, 4) if candidate.best else None,
            "matched_passages": len(candidate.best), "shared_provisions": candidate.shared_provisions,
            "shared_files": candidate.shared_files, "passage_pairs": pairs, "reasons": reasons, "differences": differences,
            "linked": str(family_id) in linked,
        })
    return results, len(fused), notices


# ---------------------------------------------------------------- both together


def case_passage_bar(embedder: Embedder | None) -> float | None:
    """How close a passage of a registered case must be to a passage of a past judgment: lower than between two judgments (see the
    setting), and never stricter than that."""
    if embedder is None:
        return None
    return min(get_settings().case_similar_passage_min_similarity, embedder.min_passage_similarity)


def similar_for_case(session: Session, viewer: User, access: AccessContext, embedder: Embedder | None, store: EvidenceStore,
                     family: CaseFamily, sources: list[Source], *, scope: str, limit: int, offset: int) -> dict:
    query = query_document(session, family, sources, embedder)
    linked_families, linked_knowledge = linked_targets(session, sources)
    notices: list[str] = []
    if not query.doc.passages:
        notices.append("Nothing of this investigation has been read yet, so there is nothing to compare: add a summary, "
                       "notes or documents, or prepare its documents.")
    investigations, investigations_total = [], 0
    if scope in ("all", "investigations") and (query.doc.passages or query.evidence_shas):
        investigations, investigations_total, found_notices = similar_investigations(
            session, viewer, family, query, embedder, store, linked_families, limit)
        notices += found_notices
    knowledge = None
    if scope in ("all", "knowledge_base") and query.doc.passages:
        knowledge = find_similar_cases(session, access, embedder, query.doc, CaseFilters(), limit, offset, case_passage_bar(embedder))
        notices += [n for n in knowledge.notices if n not in notices]
    info = {"kind": "investigation", "id": family.display_id, "title": family.title, "page_count": None,
            "passages_total": len(query.doc.passages), "passages_used": min(len(query.doc.passages), MAX_QUERY_PASSAGES),
            "provisions": [p.label for p in query.doc.provisions]}
    return {
        "query": info,
        "investigations": investigations,
        "investigations_total": investigations_total,
        "knowledge_base": [{**r.model_dump(), "linked": r.case.display_id in linked_knowledge} for r in knowledge.results] if knowledge else [],
        "knowledge_total": knowledge.total_cases if knowledge else 0,
        "notices": notices,
        "method_note": METHOD_NOTE,
    }
