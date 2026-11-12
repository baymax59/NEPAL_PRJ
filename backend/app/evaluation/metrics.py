"""Standard ranking-quality measures, computed from a ranked list of case IDs and graded labels.

labels: {case_id: grade}, grade 2 = on topic, 1 = partly relevant; anything missing = 0.

- precision@k: share of the top k that are relevant (grade >= 1).
- recall@k: share of all relevant cases that appear in the top k.
- reciprocal rank: 1 / position of the first relevant result (0 if none in the list).
- nDCG@k: rewards putting the most relevant cases highest; 1.0 = the ideal order.
"""

import math


def precision_at_k(ranked: list[str], labels: dict[str, int], k: int) -> float:
    return sum(1 for case_id in ranked[:k] if labels.get(case_id, 0) > 0) / k


def recall_at_k(ranked: list[str], labels: dict[str, int], k: int) -> float:
    relevant = {case_id for case_id, grade in labels.items() if grade > 0}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def reciprocal_rank(ranked: list[str], labels: dict[str, int]) -> float:
    for position, case_id in enumerate(ranked, start=1):
        if labels.get(case_id, 0) > 0:
            return 1 / position
    return 0.0


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(position + 1) for position, grade in enumerate(grades, start=1))


def ndcg_at_k(ranked: list[str], labels: dict[str, int], k: int) -> float:
    ideal = _dcg(sorted(labels.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return _dcg([labels.get(case_id, 0) for case_id in ranked[:k]]) / ideal
