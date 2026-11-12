"""POST /api/search in keyword mode. Hybrid and semantic modes: test_search_hybrid.py."""

import pytest


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
        outcome="Appeal(s) allowed",
        passages=[
            "The suit concerned possession of land and an ex-parte decree.",
            "Bail is not relevant here, but the decree for demolition was challenged.",
        ],
    )
    add_case(
        3,
        title="Murder case",
        year=2023,
        outcome="Dismissed",
        passages=["The accused was convicted of murder; anticipatory bail had been denied earlier."],
    )
    add_case(
        4,
        title="Restricted case",
        year=2023,
        sensitivity="restricted",
        passages=["Anticipatory bail was granted to the accused."],
    )


def search(api, query, **extra):
    return api.post("/api/search", json={"query": query, "mode": "keyword", **extra})


def found(response) -> list[str]:
    return [hit["case"]["display_id"] for hit in response.json()["results"]]


def test_words_are_matched_by_their_stem(api, cases):
    # "appeals" matches "appealed" in case 1.
    assert found(search(api, "appeals")) == ["TEST-API-1"]


def test_the_case_with_more_matching_text_ranks_first(api, cases):
    response = search(api, "anticipatory bail")

    assert response.status_code == 200
    assert response.json()["total_cases"] == 2
    assert found(response) == ["TEST-API-1", "TEST-API-3"]
    hits = response.json()["results"]
    assert hits[0]["keyword_rank"] > hits[1]["keyword_rank"]
    assert hits[0]["matching_passages"] == 2


def test_phrases_exclusions_and_or(api, cases):
    assert found(search(api, '"anticipatory bail" -murder')) == ["TEST-API-1"]
    assert sorted(found(search(api, "demolition OR murder"))) == ["TEST-API-2", "TEST-API-3"]


def test_only_an_uppercase_OR_widens_the_search(api, cases):
    # A lowercase "or" in an everyday sentence once matched almost every judgment.
    assert found(search(api, "murder or demolition")) == []  # no case mentions both
    assert found(search(api, "Or murder demolition")) == []
    assert sorted(found(search(api, "murder OR demolition"))) == ["TEST-API-2", "TEST-API-3"]
    assert found(search(api, '"bail or demolition"')) == []  # inside quotes: left as typed


def test_passages_give_pages_and_highlight_the_search_words(api, cases):
    hit = search(api, "anticipatory bail").json()["results"][0]

    assert len(hit["passages"]) == 2
    assert {(p["page_start"], p["page_end"]) for p in hit["passages"]} == {(1, 1), (2, 2)}
    highlighted = {part["text"].lower() for p in hit["passages"] for part in p["snippet"] if part["match"]}
    assert highlighted == {"anticipatory", "bail"}


def test_filters_narrow_the_search(api, cases):
    response = search(api, "anticipatory bail", filters={"year_from": 2023})

    assert found(response) == ["TEST-API-3"]


def test_pagination(api, cases):
    first = search(api, "anticipatory bail", limit=1)
    second = search(api, "anticipatory bail", limit=1, offset=1)
    beyond = search(api, "anticipatory bail", limit=1, offset=5)

    assert found(first) == ["TEST-API-1"]
    assert found(second) == ["TEST-API-3"]
    assert first.json()["total_cases"] == second.json()["total_cases"] == beyond.json()["total_cases"] == 2
    assert found(beyond) == []


def test_restricted_cases_are_never_found(api, cases):
    response = search(api, "granted")

    assert response.json()["total_cases"] == 0
    assert found(response) == []


def test_a_query_of_only_common_words_explains_the_empty_result(api, cases):
    body = search(api, "the of and").json()

    assert body["total_cases"] == 0
    assert "common words" in body["notices"][0]


def test_snippets_are_plain_text_even_with_odd_characters_in_the_source(api, add_case):
    add_case(1, title="Odd", year=2023, passages=["Stray \x02marker\x03 characters near anticipatory bail."])

    hit = search(api, "anticipatory bail").json()["results"][0]

    parts = hit["passages"][0]["snippet"]
    assert all("\x02" not in p["text"] and "\x03" not in p["text"] for p in parts)
    assert [p["text"] for p in parts if p["match"]] == ["anticipatory", "bail"]


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 501},
        {"query": "bail", "limit": 101},
        {"query": "bail", "filters": {"year_from": 2024, "year_to": 2020}},
        {"query": "bail", "unexpected": True},
        {"query": "bail", "mode": "magic"},
    ],
)
def test_invalid_search_requests_are_rejected(api, body):
    assert api.post("/api/search", json=body).status_code == 422
