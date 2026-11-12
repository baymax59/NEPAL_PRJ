"""The ranking-quality measures, checked against hand-worked examples."""

import math

import pytest

from app.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank

LABELS = {"A": 2, "B": 1, "C": 2}


def test_precision_counts_relevant_results_in_the_top_k():
    assert precision_at_k(["A", "X", "B", "Y", "Z"], LABELS, 5) == pytest.approx(2 / 5)


def test_recall_is_the_share_of_relevant_cases_found():
    assert recall_at_k(["X", "C", "Y"], LABELS, 3) == pytest.approx(1 / 3)
    assert recall_at_k([], {}, 10) == 0.0


def test_reciprocal_rank_uses_the_first_relevant_result():
    assert reciprocal_rank(["X", "Y", "B"], LABELS) == pytest.approx(1 / 3)
    assert reciprocal_rank(["X"], LABELS) == 0.0


def test_ndcg_is_1_for_the_ideal_order_and_lower_otherwise():
    assert ndcg_at_k(["A", "C", "B"], LABELS, 10) == pytest.approx(1.0)
    worse = ndcg_at_k(["B", "X", "A"], LABELS, 10)
    # Worked by hand: DCG = 1/log2(2) + 3/log2(4) = 2.5; ideal = 3 + 3/log2(3) + 1/log2(4) = 5.3928...
    assert worse == pytest.approx(2.5 / (3 + 3 / math.log2(3) + 0.5))


def test_ndcg_of_an_empty_result_list_is_0():
    assert ndcg_at_k([], LABELS, 10) == 0.0
