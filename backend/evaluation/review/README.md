# Reviewing the search-quality labels: instructions for the legal reviewer

Thank you for checking these. The system's search quality is measured against **relevance grades**: for 28 test searches and 4 "find similar cases" tests, which Supreme Court judgments a lawyer would want to see. The grades so far were **drafted with AI help** and need an expert's judgment before the measurements can be relied on.

## The file

`labels-for-review.csv`: open it in Excel. One row = one search (or "cases similar to …") and one judgment.

| Column | Meaning |
|---|---|
| `item` | Q01–Q28: a search; S1–S4: "find cases similar to this one" |
| `query_or_case` | what was searched for, or the case whose similar cases are wanted |
| `information_need` | **what the person searching actually needs**: judge relevance against this |
| `case_id`, `case_title`, `year`, `recorded_outcome` | the judgment being judged |
| `first_page_excerpt` | the start of the judgment's first page (in these reports, the headnote) |
| `draft_grade` | the AI-assisted draft: 2, 1 or 0 |
| `in_current_top10` | whether the system currently shows this judgment in its first 10 results |
| **`expert_grade`** | **your grade: please fill in** |
| `expert_comment` | optional: anything worth explaining |

## Grades

- **2**: on the topic: a lawyer researching this would want this judgment.
- **1**: partly relevant, or a closely related issue.
- **0**: not relevant.
- **Leave empty** if you can't decide: the draft grade is then kept for that row.

The rows the draft graded 1 or 2 come first for each search, then the other judgments the system returns (draft grade 0). Please look at those too: a relevant judgment the draft missed is just as important to catch as a wrong grade.

If the excerpt isn't enough, open the judgment in the system: search for its case ID and open the details page.

## When you've finished (or part of it)

1. Save in Excel with **File → Save As → "CSV UTF-8 (Comma delimited) (\*.csv)"**. The UTF-8 part matters: it keeps names intact.
2. Return the file. The developer imports it with:
   `uv run python -m scripts.labels_review import --file evaluation/review/labels-for-review.csv --reviewer "Your name, role"`
   Your name and the date are recorded with the grades.

The review can be done in parts: rows left empty keep their draft grades, and the file can be exported again later showing the grades as they stand. There are about 320 rows; at half a minute each, that is roughly 2–3 hours in total.
