"""GET /api/cases, /api/cases/filters, /api/cases/{display_id}."""

import pytest


@pytest.fixture
def cases(add_case):
    add_case(1, title="A versus STATE", year=2022, outcome="Dismissed")
    add_case(2, title="B versus UNION", year=2023, outcome="Appeal(s) allowed")
    add_case(3, title="C versus BANK", year=2023, outcome=None)
    add_case(4, title="RESTRICTED versus X", year=2023, outcome="Dismissed", sensitivity="restricted")


def ids(response) -> list[str]:
    return [item["display_id"] for item in response.json()["items"]]


def test_list_returns_only_visible_cases_newest_first(api, cases):
    response = api.get("/api/cases")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert ids(response) == ["TEST-API-2", "TEST-API-3", "TEST-API-1"]


def test_list_items_have_card_fields_and_honest_gaps(api, cases):
    item = next(i for i in api.get("/api/cases").json()["items"] if i["display_id"] == "TEST-API-3")

    assert item["title"] == "C versus BANK"
    assert item["primary_date"] == "2023-06-01"
    assert item["outcome"] is None
    assert "outcome" in item["missing_fields"]


def test_list_filters_by_year_and_outcome(api, cases):
    assert ids(api.get("/api/cases", params={"year_from": 2023})) == ["TEST-API-2", "TEST-API-3"]
    assert ids(api.get("/api/cases", params={"outcome": "Dismissed"})) == ["TEST-API-1"]
    both = api.get("/api/cases", params=[("outcome", "Dismissed"), ("outcome", "Appeal(s) allowed")])
    assert ids(both) == ["TEST-API-2", "TEST-API-1"]


def test_list_sorting_and_pagination(api, cases):
    response = api.get("/api/cases", params={"sort": "date_asc", "limit": 1, "offset": 1})

    assert response.json()["total"] == 3
    assert ids(response) == ["TEST-API-2"]


@pytest.mark.parametrize(
    "params",
    [
        {"year_from": 2024, "year_to": 2020},
        {"limit": 500},
        {"sort": "random"},
        {"unexpected": "1"},
    ],
)
def test_invalid_list_parameters_are_rejected(api, params):
    assert api.get("/api/cases", params=params).status_code == 422


def test_case_details_show_sources_and_data_quality(api, add_case):
    add_case(1, title="A versus STATE", year=2022, outcome="Dismissed")

    response = api.get("/api/cases/TEST-API-1")

    assert response.status_code == 200
    body = response.json()
    assert body["display_id"] == "TEST-API-1"
    assert body["outcome"] == "Dismissed"
    assert body["outcome_source_field"] == "disposal_nature"
    assert body["dates"] == [{"kind": "decision", "value": "2022-06-01", "source_field": "decision_date"}]
    assert body["timeline"] == []
    assert body["summary"] is None
    assert "category" in body["missing_fields"]
    assert body["provenance"]["connector"] == "test_connector"
    assert body["attribution"] is None
    [document] = body["documents"]
    assert document["source_uri"] == "https://example.org/1.pdf"
    assert document["extraction_status"] == "pending"
    assert "local_path" not in document  # internal file locations are never exposed


def test_case_details_include_the_timeline_and_courts_named(api, add_case, db_session):
    from app.extraction.indexing import store_timeline_and_entities

    case = add_case(1, title="A versus STATE", year=2022, outcome="Dismissed")
    store_timeline_and_entities(
        db_session,
        case.documents[0],
        [
            (1, "From the Judgment and Order dated 10.01.2021 of the High Court of Kerala in CRA No. 1 of 2020."),
            (2, "The FIR was registered on 05.03.2018 and the Kerala High Court later heard the appeal."),
        ],
    )

    body = api.get("/api/cases/TEST-API-1").json()

    assert [(e["event_type"], e["event_date"], e["page_number"]) for e in body["timeline"]] == [
        ("dated_mention", "2018-03-05", 2),
        ("order_under_appeal", "2021-01-10", 1),
        ("judgment", "2022-06-01", None),
    ]
    assert body["timeline"][-1]["extraction_method"] == "source_field"
    assert body["courts"] == [{"name": "High Court of Kerala", "mentions": 2, "pages": [1, 2]}]


def test_supreme_court_cases_carry_the_licence_attribution(api, add_case):
    add_case(1, title="A versus STATE", year=2022, source_system="sc_judgments")

    assert "CC-BY-4.0" in api.get("/api/cases/TEST-API-1").json()["attribution"]


def test_restricted_case_looks_exactly_like_a_missing_one(api, cases):
    restricted = api.get("/api/cases/TEST-API-4")
    missing = api.get("/api/cases/TEST-API-999")

    assert restricted.status_code == missing.status_code == 404
    assert restricted.json() == missing.json() == {"detail": "Case not found"}


def test_malformed_case_id_is_rejected(api):
    assert api.get("/api/cases/bad id!").status_code == 422


def test_filter_options_count_only_visible_cases(api, cases):
    body = api.get("/api/cases/filters").json()

    assert body["years"] == {"min": 2022, "max": 2023}
    assert body["outcomes"] == [
        {"value": "Appeal(s) allowed", "count": 1},
        {"value": "Dismissed", "count": 1},  # the restricted "Dismissed" case isn't counted
    ]
    assert body["source_systems"] == [{"value": "test_source", "count": 3}]
