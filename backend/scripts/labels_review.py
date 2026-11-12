"""Have a legal expert check the search-quality labels in a spreadsheet, then bring the review back.

Run from the backend folder (database running, model downloaded):
    uv run python -m scripts.labels_review export
        -> evaluation/review/labels-for-review.csv (open it in Excel; see evaluation/review/README.md)
    uv run python -m scripts.labels_review import --file evaluation/review/labels-for-review.csv --reviewer "Name, role"
        -> updates evaluation/labels.json with the expert's grades and records who reviewed it
    uv run python -m scripts.evaluate
        -> scores the search again, against the reviewed labels
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.models import Case, CaseDocument, DocumentPage
from app.db.session import SessionLocal
from app.embeddings.model import load_embedder
from app.evaluation.review import CaseInfo, ReviewError, apply_review, export_rows, read_csv, write_csv
from scripts.evaluate import EVALUATION_DIR, run_search, run_similar

LABELS = EVALUATION_DIR / "labels.json"
DEFAULT_SHEET = EVALUATION_DIR / "review" / "labels-for-review.csv"
EXCERPT_WORDS = 120


def case_info(session, display_ids: set[str]) -> dict[str, CaseInfo]:
    info = {}
    for case in session.scalars(select(Case).where(Case.display_id.in_(display_ids))):
        first_page = session.scalar(
            select(DocumentPage.text)
            .join(CaseDocument, CaseDocument.id == DocumentPage.document_id)
            .where(CaseDocument.case_id == case.id, DocumentPage.page_number == 1)
            .limit(1)
        )
        words = (first_page or "").split()
        excerpt = " ".join(words[:EXCERPT_WORDS]) + (" …" if len(words) > EXCERPT_WORDS else "")
        info[case.display_id] = CaseInfo(case.title, case.primary_date.year if case.primary_date else None, case.outcome, excerpt)
    return info


def export(out: Path) -> None:
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    embedder = load_embedder()
    with SessionLocal() as session:
        top10 = {q["id"]: run_search(session, embedder, q["query"], "hybrid") for q in labels["queries"]}
        top10 |= {s["id"]: run_similar(session, embedder, s["case"]) for s in labels["similar_cases"]}
        ids = {c for ranked in top10.values() for c in ranked}
        ids |= {c for item in labels["queries"] + labels["similar_cases"] for c in item["relevant"]}
        ids |= {s["case"] for s in labels["similar_cases"]}
        rows = export_rows(labels, top10, case_info(session, ids))
    write_csv(rows, out)
    items = len(labels["queries"]) + len(labels["similar_cases"])
    print(f"Wrote {len(rows)} rows ({items} queries) to {out}")
    print("Give it to the reviewer with evaluation/review/README.md.")


def import_review(sheet: Path, reviewer: str) -> None:
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    try:
        summary = apply_review(labels, read_csv(sheet), reviewer, dt.date.today().isoformat())
    except ReviewError as exc:
        sys.exit(f"Not imported: {exc}")
    LABELS.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(labels["status"])
    print(f"Saved to {LABELS}. Next: uv run python -m scripts.evaluate")
    if summary["rows_reviewed"] < summary["rows_total"]:
        print(f"{summary['rows_total'] - summary['rows_reviewed']} row(s) have no expert grade yet; their draft grades were kept.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export", help="write the review sheet")
    exporter.add_argument("--out", type=Path, default=DEFAULT_SHEET)
    importer = commands.add_parser("import", help="read the reviewed sheet back")
    importer.add_argument("--file", type=Path, required=True)
    importer.add_argument("--reviewer", required=True, help="who reviewed, e.g. 'A. Sharma, advocate'")
    args = parser.parse_args()
    if args.command == "export":
        export(args.out)
    else:
        if len(args.reviewer.strip()) < 3:
            sys.exit("--reviewer must name the person who reviewed the labels")
        import_review(args.file, args.reviewer.strip())


if __name__ == "__main__":
    main()
