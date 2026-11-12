"""Measure search quality against the labelled examples in evaluation/labels.json.

Run from the backend folder (database running, model downloaded):
    uv run python -m scripts.evaluate            # keyword vs semantic vs hybrid, with current settings
    uv run python -m scripts.evaluate --sweep    # also try other values of k and the similarity cut-offs
Writes the results to evaluation/report.md.
"""

import argparse
import datetime as dt
import json
from pathlib import Path
from statistics import mean

from app.auth.access import ANONYMOUS
from app.cases.queries import get_visible_case
from app.db.session import SessionLocal
from app.embeddings.model import load_embedder
from app.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from app.evaluation.review import DRAFT_STATUS
from app.schemas.cases import CaseFilters
from app.schemas.search import SearchRequest
from app.search import hybrid
from app.similar import service as similar

EVALUATION_DIR = Path(__file__).resolve().parents[1] / "evaluation"
K = 10
METRICS = ("P@5", "R@10", "MRR", "nDCG@10")


def score(ranked: list[str], labels: dict[str, int]) -> dict[str, float]:
    return {
        "P@5": precision_at_k(ranked, labels, 5),
        "R@10": recall_at_k(ranked, labels, K),
        "MRR": reciprocal_rank(ranked, labels),
        "nDCG@10": ndcg_at_k(ranked, labels, K),
    }


def averages(rows: list[dict[str, float]]) -> dict[str, float]:
    return {metric: mean(row[metric] for row in rows) for metric in METRICS}


def run_search(session, embedder, query: str, mode: str) -> list[str]:
    response = hybrid.search(session, ANONYMOUS, embedder, SearchRequest(query=query, mode=mode, limit=K))
    session.rollback()  # ends the transaction, clearing the SET LOCAL index settings
    return [hit.case.display_id for hit in response.results]


def run_similar(session, embedder, display_id: str) -> list[str]:
    case = get_visible_case(session, ANONYMOUS, display_id)
    document = similar.document_from_case(session, case)
    response = similar.find_similar_cases(session, ANONYMOUS, embedder, document, CaseFilters(), K, 0)
    session.rollback()
    return [result.case.display_id for result in response.results]


def table(header: list[str], rows: list[list]) -> str:
    def cell(value):
        return f"{value:.3f}" if isinstance(value, float) else str(value)

    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sweep", action="store_true", help="also try other settings")
    args = parser.parse_args()

    labels = json.loads((EVALUATION_DIR / "labels.json").read_text(encoding="utf-8"))
    queries, similar_items = labels["queries"], labels["similar_cases"]
    embedder = load_embedder()
    report = [
        f"# Search evaluation ({dt.date.today().isoformat()})",
        "",
        f"> {labels['about']}",
        ">",
        f"> **Label status:** {labels.get('status', DRAFT_STATUS)}",
        "",
        f"{len(queries)} search queries and {len(similar_items)} similar-case queries; top {K} results scored. "
        "P@5 = precision in the top 5, R@10 = recall in the top 10, MRR = mean reciprocal rank, "
        "nDCG@10 = ranking quality (1.0 = ideal order).",
    ]

    with SessionLocal() as session:
        # 1. Search modes with the current settings.
        per_mode = {}
        for mode in ("keyword", "semantic", "hybrid"):
            per_mode[mode] = [score(run_search(session, embedder, q["query"], mode), q["relevant"]) for q in queries]
        report += ["", "## Search: keyword vs semantic vs hybrid (current settings)", ""]
        report.append(table(["mode", *METRICS], [[m, *averages(rows).values()] for m, rows in per_mode.items()]))
        report += ["", "nDCG@10 per query:", ""]
        report.append(
            table(
                ["query", "keyword", "semantic", "hybrid"],
                [
                    [f"{q['id']} {q['query'][:60]}", *(per_mode[m][i]["nDCG@10"] for m in per_mode)]
                    for i, q in enumerate(queries)
                ],
            )
        )

        # 2. Similar cases with the current settings.
        similar_rows = [score(run_similar(session, embedder, item["case"]), item["relevant"]) for item in similar_items]
        report += ["", "## Similar cases (current settings)", ""]
        report.append(
            table(
                ["query case", *METRICS],
                [[f"{item['id']} {item['case']}", *row.values()] for item, row in zip(similar_items, similar_rows)]
                + [["**average**", *averages(similar_rows).values()]],
            )
        )

        if args.sweep:
            report += _sweeps(session, embedder, queries, similar_items)

    report_file = EVALUATION_DIR / "report.md"
    report_file.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"\nSaved to {report_file}")


def _sweeps(session, embedder, queries, similar_items) -> list[str]:
    saved = (hybrid.RRF_K, similar.RRF_K, embedder.min_similarity, embedder.min_passage_similarity)
    lines = ["", "## Settings sweep: hybrid search, mean nDCG@10", ""]
    try:
        cutoffs, ks = (0.55, 0.60, 0.65, 0.70), (5, 10, 20, 60)
        rows = []
        for cutoff in cutoffs:
            embedder.min_similarity = cutoff
            row = [f"cut-off {cutoff:.2f}"]
            for k in ks:
                hybrid.RRF_K = k
                row.append(mean(ndcg_at_k(run_search(session, embedder, q["query"], "hybrid"), q["relevant"], K) for q in queries))
            rows.append(row)
        lines.append(table(["semantic cut-off", *(f"k={k}" for k in ks)], rows))

        lines += ["", "## Settings sweep: similar cases, mean nDCG@10", ""]
        rows = []
        for cutoff in (0.75, 0.80, 0.85):
            embedder.min_passage_similarity = cutoff
            row = [f"passage cut-off {cutoff:.2f}"]
            for k in (5, 10, 20):
                similar.RRF_K = k
                row.append(
                    mean(ndcg_at_k(run_similar(session, embedder, i["case"]), i["relevant"], K) for i in similar_items)
                )
            rows.append(row)
        lines.append(table(["passage cut-off", "k=5", "k=10", "k=20"], rows))
    finally:
        hybrid.RRF_K, similar.RRF_K, embedder.min_similarity, embedder.min_passage_similarity = saved
    return lines


if __name__ == "__main__":
    main()
