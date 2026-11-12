"""A legal expert's review of the search-quality labels (HANDOVER.md, decision 9).

The labels in evaluation/labels.json were drafted with AI help. This makes checking them practical:
- export_rows(): one spreadsheet row per (query, case) pair worth judging. Every case the draft graded,
  plus every case the system currently returns in its top 10, so relevant cases the draft missed show
  up as well as wrongly graded ones.
- apply_review(): takes the expert's grades back. A blank grade keeps the draft grade; 0 removes the case;
  1 or 2 sets it. Who reviewed, when and how much is recorded in the labels file.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COLUMNS = [
    "item", "kind", "query_or_case", "information_need",
    "case_id", "case_title", "year", "recorded_outcome", "first_page_excerpt",
    "draft_grade", "in_current_top10", "expert_grade", "expert_comment",
]
REQUIRED = {"item", "case_id", "expert_grade", "expert_comment"}
DRAFT_STATUS = "DRAFT: not yet reviewed by a legal expert"


class ReviewError(ValueError):
    """The review file can't be used as it is; the message says where and why."""


@dataclass(frozen=True)
class CaseInfo:
    title: str | None
    year: int | None
    outcome: str | None
    excerpt: str  # the start of the judgment's first page (the headnote, in the Supreme Court Reports)


def _items(labels: dict[str, Any]) -> list[dict[str, Any]]:
    return labels["queries"] + labels["similar_cases"]


def export_rows(labels: dict[str, Any], top10: dict[str, list[str]], info: dict[str, CaseInfo]) -> list[dict[str, Any]]:
    rows = []
    for item in _items(labels):
        similar = "case" in item
        ranked = top10.get(item["id"], [])
        graded = item["relevant"]
        # Graded cases first (2, then 1), then the rest of the current top 10 in rank order.
        candidates = sorted(
            set(graded) | set(ranked),
            key=lambda c: (-graded.get(c, 0), ranked.index(c) if c in ranked else len(ranked), c),
        )
        if similar:
            query_case = info.get(item["case"])
            question = f"Cases similar to {item['case']}" + (f" ({query_case.title})" if query_case and query_case.title else "")
        else:
            question = item["query"]
        for case_id in candidates:
            meta = info.get(case_id, CaseInfo(None, None, None, ""))
            rows.append(
                {
                    "item": item["id"],
                    "kind": "similar cases" if similar else "search",
                    "query_or_case": question,
                    "information_need": item.get("need", ""),
                    "case_id": case_id,
                    "case_title": meta.title or "",
                    "year": meta.year or "",
                    "recorded_outcome": meta.outcome or "",
                    "first_page_excerpt": meta.excerpt,
                    "draft_grade": graded.get(case_id, 0),
                    "in_current_top10": "yes" if case_id in ranked else "no",
                    "expert_grade": "",
                    "expert_comment": "",
                }
            )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel then shows names with accents and Indian characters correctly.
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ReviewError(f"The file has no column(s) {', '.join(sorted(missing))}. Was it saved as CSV from the exported sheet?")
        return list(reader)


def apply_review(labels: dict[str, Any], rows: list[dict[str, str]], reviewer: str, date: str) -> dict[str, Any]:
    """Update `labels` in place with the expert's grades; returns a summary of what changed."""
    items = {item["id"]: item for item in _items(labels)}
    per_item: dict[str, dict[str, int]] = {}
    reviewed = changed = 0
    for number, row in enumerate(rows, start=2):  # row 1 is the header, as in Excel
        item = items.get((row.get("item") or "").strip())
        if item is None:
            raise ReviewError(f"Row {number}: unknown item {row.get('item')!r}")
        case_id = (row.get("case_id") or "").strip()
        if not case_id:
            raise ReviewError(f"Row {number}: case_id is empty")
        counts = per_item.setdefault(item["id"], {"rows": 0, "reviewed": 0})
        counts["rows"] += 1
        grade = (row.get("expert_grade") or "").strip()
        comment = (row.get("expert_comment") or "").strip()
        if comment:
            item.setdefault("expert_comments", {})[case_id] = comment
        if not grade:
            continue  # not reviewed: the draft grade stays
        if grade not in {"0", "1", "2"}:
            raise ReviewError(f"Row {number}: expert_grade must be 0, 1 or 2 (or empty), not {grade!r}")
        reviewed += 1
        counts["reviewed"] += 1
        new = int(grade)
        if new != item["relevant"].get(case_id, 0):
            changed += 1
        if new == 0:
            item["relevant"].pop(case_id, None)
        else:
            item["relevant"][case_id] = new

    for item_id, counts in per_item.items():
        items[item_id]["review"] = counts
    fully = sum(1 for c in per_item.values() if c["rows"] and c["reviewed"] == c["rows"])
    summary = {
        "reviewer": reviewer,
        "date": date,
        "rows_total": len(rows),
        "rows_reviewed": reviewed,
        "grades_changed": changed,
        "items_fully_reviewed": fully,
        "items_total": len(items),
    }
    labels["review"] = summary
    labels["status"] = (
        f"Reviewed by {reviewer} on {date}: {reviewed} of {len(rows)} rows, "
        f"{fully} of {len(items)} queries fully; {changed} grade(s) changed from the draft."
        if reviewed
        else DRAFT_STATUS
    )
    return summary
