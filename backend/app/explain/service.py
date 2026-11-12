"""Explain why a case matched a query: shared words and provisions, closest passages, differences.

Everything is computed from the stored case text; nothing is generated. Each point can be
checked against the page it refers to. It explains why the *search* returned the case. It
doesn't say the cases are legally alike, and METHOD_NOTE says so to the user.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Case, DocumentChunk
from app.embeddings.model import Embedder
from app.explain.citations import case_citations
from app.explain.provisions import Provision, extract_provisions
from app.schemas.cases import CaseSummary, ProvisionCitation
from app.schemas.explain import MatchExplanation, TermMatch
from app.search.keyword import chunk_snippets, to_tsquery
from app.search.passages import interleave, to_passage

METHOD_NOTE = (
    "Produced automatically from the case text: the search words it contains, statutory provisions "
    "found by pattern matching, and the passages closest to the search in meaning or wording. "
    "It shows why the search returned this case. It does not mean the cases are legally the same, "
    "and provisions are detected automatically, so check the cited pages."
)
SEMANTIC_UNAVAILABLE = "Meaning-based comparison unavailable (embedding model not loaded); wording only."
MAX_WORDS_SHOWN = 6
PASSAGES_IN_EXPLANATION = 5

# Words as typed, skipping excluded words ("-murder") and the OR operator.
_QUERY_WORD = re.compile(r"(?<![\w-])(-?)([A-Za-z][A-Za-z'’-]*)")


@dataclass
class QueryTerm:
    word: str  # as typed
    lexemes: list[str]  # its stems, as stored in the search index


@dataclass
class QueryProfile:
    text: str
    terms: list[QueryTerm]
    provisions: list[Provision]


def build_query_profile(session: Session, query: str) -> QueryProfile:
    words: list[str] = []
    for excluded, word in _QUERY_WORD.findall(query):
        if not excluded and word != "OR" and word.lower() not in {w.lower() for w in words}:
            words.append(word)
    rows = (
        session.execute(
            text(
                "SELECT w, tsvector_to_array(to_tsvector('english', w)) AS lexemes "
                "FROM unnest(CAST(:words AS text[])) WITH ORDINALITY AS t(w, n) ORDER BY n"
            ),
            {"words": words},
        ).all()
        if words
        else []
    )
    terms = [QueryTerm(row.w, list(row.lexemes)) for row in rows if row.lexemes]  # common words have none
    provisions = list({p.key: p for p in extract_provisions(query)}.values())
    return QueryProfile(query, terms, provisions)


def term_counts(session: Session, case_ids: list[uuid.UUID], profile: QueryProfile) -> dict[uuid.UUID, dict[str, int]]:
    """For each case: how many of its passages contain each query stem."""
    lexemes = sorted({lexeme for term in profile.terms for lexeme in term.lexemes})
    if not lexemes or not case_ids:
        return {}
    rows = session.execute(
        text(
            "SELECT ch.case_id, lexeme, count(*) AS passages "
            "FROM document_chunks ch CROSS JOIN LATERAL unnest(tsvector_to_array(ch.search_vector)) AS lexeme "
            "WHERE ch.case_id = ANY(:case_ids) AND lexeme = ANY(:lexemes) GROUP BY ch.case_id, lexeme"
        ),
        {"case_ids": case_ids, "lexemes": lexemes},
    ).all()
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    for row in rows:
        counts[row.case_id][row.lexeme] = row.passages
    return counts


def split_terms(profile: QueryProfile, counts: dict[str, int]) -> tuple[list[TermMatch], list[str]]:
    found, missing = [], []
    for term in profile.terms:
        passages = [counts.get(lexeme, 0) for lexeme in term.lexemes]
        if all(passages):
            found.append(TermMatch(term=term.word, passages=min(passages)))
        else:
            missing.append(term.word)
    return found, missing


def page_label(page_start: int | None, page_end: int | None) -> str:
    if page_start is None:
        return "a passage"
    return f"p.{page_start}" if page_start == page_end else f"pp.{page_start}–{page_end}"


def _short_list(items: list[str]) -> str:
    shown = ", ".join(items[:MAX_WORDS_SHOWN])
    return shown + (f" (+{len(items) - MAX_WORDS_SHOWN} more)" if len(items) > MAX_WORDS_SHOWN else "")


def reasons_for(
    profile: QueryProfile,
    counts: dict[str, int],
    citations: list[ProvisionCitation],
    closest: tuple[str, float] | None,
) -> list[str]:
    """Short, checkable reasons for a result card. `closest` = (page label, similarity)."""
    reasons = []
    query_keys = {p.key for p in profile.provisions}
    cited_keys = {c.key for c in citations}
    shared = [c.label for c in citations if c.key in query_keys]
    if shared:
        reasons.append(f"Cites {_short_list(shared)}, as in your search")
    found, missing = split_terms(profile, counts)
    if found:
        # "Anywhere": keyword *search* needs all words in one passage, so a case can contain
        # every word and still be matched by meaning only. Saying where avoids that confusion.
        reasons.append(
            f"Contains {len(found)} of {len(profile.terms)} search words (anywhere in the judgment): "
            f"{_short_list([t.term for t in found])}"
        )
    if closest:
        reasons.append(f"Passage on {closest[0]} is close in meaning to your search (similarity {closest[1]:.2f})")
    # Absences are worded as what was checked: words are matched literally, and provisions are
    # detected by patterns that can miss unusual citation styles.
    if missing:
        reasons.append(f"Words not found: {_short_list(missing)}")
    not_detected = [p.label for p in profile.provisions if p.key not in cited_keys]
    if not_detected:
        reasons.append(f"No citation detected of: {_short_list(not_detected)}")
    return reasons


def explain_case(session: Session, case: Case, embedder: Embedder | None, query: str) -> MatchExplanation:
    """Full explanation for one case the caller is allowed to see (checked by the caller)."""
    profile = build_query_profile(session, query)
    tsquery = to_tsquery(query)
    query_vector = embedder.embed_query(query) if embedder else None

    semantic: list[tuple[int, float]] = []
    if query_vector is not None:
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        rows = session.execute(
            select(DocumentChunk.id, (1 - distance).label("similarity"))
            .where(DocumentChunk.case_id == case.id, DocumentChunk.embedding_model == embedder.model_name)
            .order_by(distance)
            .limit(3)
        ).all()
        semantic = [(row.id, float(row.similarity)) for row in rows if row.similarity >= embedder.min_similarity]
    keyword_ids = session.scalars(
        select(DocumentChunk.id)
        .where(DocumentChunk.case_id == case.id, DocumentChunk.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, tsquery).desc(), DocumentChunk.id)
        .limit(3)
    ).all()

    semantic_ids = [chunk_id for chunk_id, _ in semantic]
    chosen = interleave(semantic_ids, list(keyword_ids), PASSAGES_IN_EXPLANATION)
    snippets = chunk_snippets(session, chosen, tsquery, query_vector)
    passages = [to_passage(chunk_id, snippets[chunk_id], set(semantic_ids)) for chunk_id in chosen]

    counts = term_counts(session, [case.id], profile).get(case.id, {})
    citations = case_citations(session, [case.id]).get(case.id, [])
    closest = None
    if semantic:
        best = snippets[semantic[0][0]]
        closest = (page_label(best.page_start, best.page_end), semantic[0][1])

    found, missing = split_terms(profile, counts)
    query_keys = {p.key for p in profile.provisions}
    cited_keys = {c.key for c in citations}
    only_in_query = [p.label for p in profile.provisions if p.key not in cited_keys]

    differences = []
    if missing:
        differences.append(f"Words from your search not found in the case text: {', '.join(missing)}")
    differences.extend(
        f"Your search refers to {label}; no citation of it was detected in this case" for label in only_in_query
    )
    if not passages:
        differences.append("No passage of this case is close to the search in meaning or wording")

    return MatchExplanation(
        case=CaseSummary.model_validate(case),
        query=query,
        reasons=reasons_for(profile, counts, citations, closest),
        shared_terms=found,
        missing_terms=missing,
        shared_provisions=[c for c in citations if c.key in query_keys],
        provisions_only_in_query=only_in_query,
        case_provisions=citations[:10],
        passages=passages,
        differences=differences,
        notices=[] if query_vector is not None else [SEMANTIC_UNAVAILABLE],
        method_note=METHOD_NOTE,
    )
