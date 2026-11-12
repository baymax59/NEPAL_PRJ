"""Why a case matched: card reasons in search results, and POST /api/cases/{id}/explain."""

import pytest

from app.embeddings.model import get_embedder
from app.explain.indexing import store_provisions
from app.main import app

BAIL_PASSAGES = [
    "The appellant sought anticipatory bail under Section 438 of the Code of Criminal Procedure.",
    "Anticipatory bail was refused by the High Court and the appellant appealed.",
]


@pytest.fixture
def cases(db_session, add_case):
    def add(n, passages, **kwargs):
        case = add_case(n, passages=passages, **kwargs)
        store_provisions(db_session, case.documents[0], [(i + 1, text) for i, text in enumerate(passages)])
        db_session.flush()
        return case

    add(1, BAIL_PASSAGES, title="Bail case", year=2022)
    add(2, ["The accused was convicted under Section 302 IPC after a long trial; bail was denied."], title="Murder", year=2023)
    add(3, BAIL_PASSAGES, title="Restricted bail case", year=2023, sensitivity="restricted")


def search(api, query, **extra):
    return api.post("/api/search", json={"query": query, **extra}).json()["results"]


def explain(api, display_id, query):
    return api.post(f"/api/cases/{display_id}/explain", json={"query": query})


def test_result_cards_say_which_words_matched_and_which_are_missing(api, cases):
    hit = next(h for h in search(api, "anticipatory bail custody") if h["case"]["display_id"] == "TEST-API-1")

    assert "Contains 2 of 3 search words (anywhere in the judgment): anticipatory, bail" in hit["reasons"]
    assert "Words not found: custody" in hit["reasons"]
    assert any(r.startswith("Passage on p.") and "close in meaning" in r for r in hit["reasons"])


def test_result_cards_mention_provisions_cited_in_both(api, cases):
    hit = search(api, "Section 438 CrPC anticipatory bail")[0]

    assert hit["case"]["display_id"] == "TEST-API-1"
    assert "Cites Section 438 CrPC, as in your search" in hit["reasons"]


def test_explanation_lists_shared_and_missing_words_and_provisions(api, cases):
    response = explain(api, "TEST-API-1", "Section 438 CrPC and Section 302 IPC anticipatory bail custody")

    assert response.status_code == 200
    body = response.json()
    assert {t["term"] for t in body["shared_terms"]} >= {"anticipatory", "bail"}
    assert next(t for t in body["shared_terms"] if t["term"] == "bail")["passages"] == 2
    assert "custody" in body["missing_terms"]
    assert [p["label"] for p in body["shared_provisions"]] == ["Section 438 CrPC"]
    assert body["shared_provisions"][0]["pages"] == [1]
    assert body["provisions_only_in_query"] == ["Section 302 IPC"]
    assert "Your search refers to Section 302 IPC; no citation of it was detected in this case" in body["differences"]
    assert any("custody" in d for d in body["differences"])
    assert "does not mean the cases are legally the same" in body["method_note"]


def test_explanation_passages_have_pages_and_say_how_they_matched(api, cases):
    body = explain(api, "TEST-API-1", "anticipatory bail refused").json()

    assert body["passages"]
    for passage in body["passages"]:
        assert passage["page_start"] in (1, 2)
        assert passage["matched_by"]
    assert any("keyword" in p["matched_by"] for p in body["passages"])


def test_explanation_of_an_unrelated_case_says_nothing_matches(api, cases):
    body = explain(api, "TEST-API-2", "pension arrears gratuity").json()

    assert body["passages"] == []
    assert body["shared_terms"] == []
    assert "No passage of this case is close to the search in meaning or wording" in body["differences"]


def test_restricted_or_missing_cases_cannot_be_explained(api, cases):
    restricted = explain(api, "TEST-API-3", "anticipatory bail")
    missing = explain(api, "TEST-API-999", "anticipatory bail")

    assert restricted.status_code == missing.status_code == 404
    assert restricted.json() == missing.json()


def test_without_the_model_the_explanation_uses_wording_only(api, cases):
    app.dependency_overrides[get_embedder] = lambda: None

    body = explain(api, "TEST-API-1", "anticipatory bail").json()

    assert body["notices"] and "unavailable" in body["notices"][0]
    assert body["passages"] and all(p["matched_by"] == ["keyword"] for p in body["passages"])


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "x" * 501}, {"query": "bail", "extra": 1}])
def test_invalid_explain_requests_are_rejected(api, cases, payload):
    assert api.post("/api/cases/TEST-API-1/explain", json=payload).status_code == 422


def test_case_details_list_the_cited_provisions(api, cases):
    body = api.get("/api/cases/TEST-API-2").json()

    assert body["provisions"] == [
        {"key": "ipc|section|302", "label": "Section 302 IPC", "mentions": 1, "pages": [1]}
    ]
