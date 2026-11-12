"""Hybrid and semantic search (with FakeEmbedder), and the rank-fusion maths."""

import uuid

import pytest
from sqlalchemy import update

from app.db.models import DocumentChunk
from app.embeddings.model import get_embedder
from app.main import app
from app.search.hybrid import RRF_K, fuse
from app.search.keyword import KeywordCandidate
from app.search.semantic import SemanticCandidate


@pytest.fixture
def cases(add_case):
    add_case(
        1,
        title="Bail case",
        year=2022,
        outcome="Dismissed",
        passages=[
            "The appellant sought anticipatory bail under Section 438 of the Code of Criminal Procedure.",
            "Anticipatory bail was refused by the High Court and the appellant appealed.",
        ],
    )
    add_case(
        2,
        title="Land case",
        year=2023,
        passages=["The suit concerned possession of land and an ex-parte decree for demolition."],
    )
    add_case(
        3,
        title="Murder case",
        year=2023,
        passages=[
            "The accused was convicted of murder after a long trial with many witnesses; "
            "anticipatory bail had been denied earlier."
        ],
    )
    add_case(
        4,
        title="Restricted case",
        year=2023,
        sensitivity="restricted",
        passages=["Anticipatory bail refused by the High Court; the appellant appealed."],
    )


def search(api, query, **extra):
    return api.post("/api/search", json={"query": query, **extra})


def found(response) -> list[str]:
    return [hit["case"]["display_id"] for hit in response.json()["results"]]


def test_hybrid_is_the_default_and_explains_its_scores(api, cases):
    body = search(api, "anticipatory bail").json()

    assert body["mode"] == "hybrid"
    assert "not a probability" in body["relevance_note"]
    top = body["results"][0]
    assert top["case"]["display_id"] == "TEST-API-1"
    assert top["match_type"] == "keyword+semantic"
    assert top["relevance"] == 100  # first in both rankings
    assert top["keyword_rank"] > 0
    assert top["semantic_similarity"] > 0


def test_hybrid_finds_cases_that_strict_keyword_search_misses(api, cases):
    # Keyword search needs every word; "refused" and "appealed" only occur in case 1.
    query = "anticipatory bail refused appealed"

    assert found(search(api, query, mode="keyword")) == ["TEST-API-1"]
    hybrid = search(api, query).json()["results"]
    by_id = {hit["case"]["display_id"]: hit for hit in hybrid}
    assert "TEST-API-3" in by_id  # shares "anticipatory bail", found by meaning
    assert by_id["TEST-API-3"]["match_type"] == "semantic"
    assert by_id["TEST-API-3"]["keyword_rank"] is None


def test_when_only_meaning_based_search_finds_anything_its_best_match_scores_100(api, cases):
    # No case contains "prearrest" or "custody", so keyword search finds nothing.
    body = search(api, "prearrest custody anticipatory bail refused").json()
    keyword_only = search(api, "prearrest custody anticipatory bail refused", mode="keyword").json()

    assert keyword_only["total_cases"] == 0
    assert body["results"][0]["match_type"] == "semantic"
    assert body["results"][0]["relevance"] == 100


def test_lower_ranked_results_score_clearly_lower(api, add_case):
    # Case n mentions the query (8 - n) times among n times as much other text, so both
    # methods rank case 1 first and case 7 last.
    for n in range(1, 8):
        add_case(
            n, title=f"Case {n}", year=2023, passages=["Anticipatory bail. " * (8 - n) + "Unrelated filler text. " * n]
        )

    relevances = [hit["relevance"] for hit in search(api, "anticipatory bail").json()["results"]]

    assert relevances[0] == 100
    assert relevances[-1] < 60


def test_relevance_is_between_0_and_100_and_never_increases_down_the_list(api, cases):
    relevances = [hit["relevance"] for hit in search(api, "anticipatory bail appeal").json()["results"]]

    assert relevances == sorted(relevances, reverse=True)
    assert all(0 <= r <= 100 for r in relevances)


def test_passages_say_how_they_matched(api, cases):
    hit = search(api, "anticipatory bail").json()["results"][0]

    for passage in hit["passages"]:
        assert set(passage["matched_by"]) <= {"keyword", "semantic"}
        assert passage["matched_by"]
        assert 0 < passage["similarity"] <= 1
    assert any("keyword" in p["matched_by"] and "semantic" in p["matched_by"] for p in hit["passages"])


def test_semantic_mode_respects_access_and_filters(api, cases):
    everything = found(search(api, "anticipatory bail refused appealed", mode="semantic"))
    filtered = found(search(api, "anticipatory bail", mode="semantic", filters={"year_from": 2023}))

    assert "TEST-API-4" not in everything  # restricted
    assert "TEST-API-1" not in filtered  # decided in 2022
    assert "TEST-API-3" in filtered


def test_unrelated_query_finds_nothing_by_meaning(api, cases):
    body = search(api, "chocolate strawberry recipe", mode="semantic").json()

    assert body["results"] == []


def test_vectors_from_another_model_are_ignored(api, cases, db_session):
    db_session.execute(update(DocumentChunk).values(embedding_model="some-other-model"))

    assert found(search(api, "anticipatory bail", mode="semantic")) == []


def test_without_the_model_hybrid_falls_back_to_keyword_search(api, cases):
    app.dependency_overrides[get_embedder] = lambda: None

    hybrid = search(api, "anticipatory bail")
    semantic = search(api, "anticipatory bail", mode="semantic")

    assert hybrid.json()["mode"] == "keyword"
    assert found(hybrid) == ["TEST-API-1", "TEST-API-3"]
    assert "unavailable" in hybrid.json()["notices"][0]
    assert found(semantic) == []
    assert "unavailable" in semantic.json()["notices"][0]


def test_fusion_rewards_agreement_between_methods():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    keyword = [KeywordCandidate(a, 2.0, 3, []), KeywordCandidate(b, 1.0, 1, [])]
    semantic = [SemanticCandidate(b, 0.8), SemanticCandidate(c, 0.7)]

    fused = fuse(keyword, semantic)

    # b: 2nd in keyword + 1st in semantic beats a (1st in keyword only).
    assert [r.case_id for r in fused] == [b, a, c]
    assert fused[0].score == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert fused[0].keyword is not None and fused[0].semantic is not None
    assert fused[1].semantic is None
