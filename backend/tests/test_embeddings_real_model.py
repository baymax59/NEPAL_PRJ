"""The real embedding model (BAAI/bge-small-en-v1.5).

Skipped if the model hasn't been downloaded yet (run: uv run python -m scripts.embed_chunks).
Loading it takes about 10 seconds.
"""

import math

import pytest

from app.core.config import get_settings
from app.db.models import EMBEDDING_DIM
from app.embeddings.model import load_embedder


def similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # vectors are normalised


@pytest.fixture(scope="module")
def model():
    try:
        return load_embedder()
    except Exception as exc:
        pytest.skip(f"Embedding model not available locally: {type(exc).__name__}")


def test_vectors_match_the_database_column_and_are_normalised(model):
    [vector] = model.embed_passages(["The appeal is allowed."])

    assert len(vector) == EMBEDDING_DIM
    assert math.isclose(sum(x * x for x in vector), 1.0, rel_tol=1e-3)


def test_same_meaning_in_different_words_beats_a_different_topic(model):
    # The related passage shares almost no words with the query: only meaning connects them.
    query = model.embed_query("conviction based only on circumstantial evidence")
    related, unrelated = model.embed_passages(
        [
            "There was no eyewitness; the prosecution relied on a chain of circumstances to prove guilt.",
            "The tenant failed to pay rent and the landlord sought eviction from the premises.",
        ]
    )

    assert similarity(query, related) > similarity(query, unrelated) + 0.1


def test_an_unrelated_query_stays_below_the_configured_cut_off(model):
    query = model.embed_query("recipe for chocolate cake")
    [legal] = model.embed_passages(["The High Court dismissed the writ petition challenging the land acquisition."])

    assert similarity(query, legal) < get_settings().semantic_min_similarity
