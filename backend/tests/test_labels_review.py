"""The expert review of the search-quality labels: export to a sheet, import the grades back."""

import copy

import pytest

from app.evaluation.review import DRAFT_STATUS, CaseInfo, ReviewError, apply_review, export_rows, read_csv, write_csv

LABELS = {
    "about": "draft",
    "queries": [{"id": "Q01", "query": "anticipatory bail refused", "need": "bail cases", "relevant": {"A": 2, "B": 1}}],
    "similar_cases": [{"id": "S1", "case": "X", "need": "like X", "relevant": {"C": 2}}],
}
INFO = {
    "A": CaseInfo("A v. State", 2023, "Appeal(s) allowed", "Headnote of A"),
    "X": CaseInfo("X v. Union", 2022, None, "Headnote of X"),
}


def labels():
    return copy.deepcopy(LABELS)


def test_the_sheet_lists_graded_cases_and_the_current_top_results():
    rows = export_rows(labels(), {"Q01": ["D", "A"], "S1": ["C", "E"]}, INFO)

    q01 = [(r["case_id"], r["draft_grade"], r["in_current_top10"]) for r in rows if r["item"] == "Q01"]
    assert q01 == [("A", 2, "yes"), ("B", 1, "no"), ("D", 0, "yes")]  # graded first, then the rest of the top 10
    first = rows[0]
    assert (first["case_title"], first["year"], first["first_page_excerpt"]) == ("A v. State", 2023, "Headnote of A")
    assert first["expert_grade"] == "" and first["expert_comment"] == ""
    s1 = [r for r in rows if r["item"] == "S1"]
    assert s1[0]["query_or_case"] == "Cases similar to X (X v. Union)"
    assert [r["case_id"] for r in s1] == ["C", "E"]


def review(*grades):
    """Rows as the expert returns them: (item, case, grade, comment)."""
    return [{"item": i, "case_id": c, "expert_grade": g, "expert_comment": m} for i, c, g, m in grades]


def test_expert_grades_replace_the_draft_and_blanks_keep_it():
    data = labels()

    summary = apply_review(data, review(("Q01", "A", "1", "only partly on bail"), ("Q01", "B", "", ""),
                                        ("Q01", "D", "2", "missed by the draft"), ("S1", "C", "0", "")), "A. Sharma, advocate", "2026-11-07")

    assert data["queries"][0]["relevant"] == {"A": 1, "B": 1, "D": 2}  # B blank: draft kept
    assert data["similar_cases"][0]["relevant"] == {}  # 0 removes
    assert data["queries"][0]["expert_comments"] == {"A": "only partly on bail", "D": "missed by the draft"}
    assert summary == {"reviewer": "A. Sharma, advocate", "date": "2026-11-07", "rows_total": 4, "rows_reviewed": 3,
                       "grades_changed": 3, "items_fully_reviewed": 1, "items_total": 2}
    assert data["status"].startswith("Reviewed by A. Sharma, advocate on 2026-11-07: 3 of 4 rows, 1 of 2 queries fully")


def test_an_empty_review_leaves_the_labels_a_draft():
    data = labels()

    apply_review(data, review(("Q01", "A", "", "")), "Reviewer", "2026-11-07")

    assert data["queries"][0]["relevant"] == {"A": 2, "B": 1}
    assert data["status"] == DRAFT_STATUS


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (review(("Q01", "A", "3", "")), "Row 2: expert_grade must be 0, 1 or 2"),
        (review(("Q01", "A", "yes", "")), "Row 2: expert_grade must be 0, 1 or 2"),
        (review(("Q99", "A", "2", "")), "Row 2: unknown item 'Q99'"),
        (review(("Q01", "", "2", "")), "Row 2: case_id is empty"),
    ],
)
def test_mistakes_in_the_sheet_are_reported_not_guessed(rows, message):
    with pytest.raises(ReviewError, match=message):
        apply_review(labels(), rows, "Reviewer", "2026-11-07")


def test_the_sheet_survives_a_round_trip_through_a_file(tmp_path):
    rows = export_rows(labels(), {"Q01": ["A"]}, {"A": CaseInfo("Rāmesh v. State – appeal", 2023, None, "x")})
    sheet = tmp_path / "review.csv"
    write_csv(rows, sheet)

    assert read_csv(sheet)[0]["case_title"] == "Rāmesh v. State – appeal"  # non-English characters intact
    (tmp_path / "wrong.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ReviewError, match="no column"):
        read_csv(tmp_path / "wrong.csv")
