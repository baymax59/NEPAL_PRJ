# Step 9: Measuring search quality

Status: **done** (2026-11-04). 179 tests pass. Labels are **drafts**: see "Before relying on the numbers" below.

## 1. What this module does

- **`backend/evaluation/labels.json`** holds the test set:
  - **28 search queries.** Q01–Q22 are topic searches, in legal phrasing and in plain language. Q23–Q28 are specific-term searches (names, rare provisions).
  - **4 "find similar cases" queries**, each using an existing judgment as the query.
  - Each lists which of the 100 judgments are relevant: **2** = on topic, **1** = partly relevant.
- **`scripts/evaluate.py`** runs every query through the real search code and scores the top 10 results. It compares keyword, semantic and hybrid search, and with `--sweep` it tries other values of the tunable settings. It writes `backend/evaluation/report.md`.
- **`app/evaluation/metrics.py`** holds the scoring formulas, tested against hand-worked examples.

## 2. Why it is needed

Without measurements, "the search works" is only an impression from a few hand-picked queries. This step:
- compares the search methods on equal terms;
- checks the settings chosen in Steps 6 and 8;
- found a real bug (below);
- is the regression check for future changes: run it again after any search change and compare.

## 3. Files created or changed

```
backend/
├─ evaluation/labels.json          test queries + relevance labels (DRAFT)
├─ evaluation/report.md            latest results (rewritten by each run)
├─ app/evaluation/metrics.py       precision@k, recall@k, reciprocal rank, nDCG@k
├─ scripts/evaluate.py             runs the evaluation
├─ app/search/keyword.py           + normalize_query(): fix for lowercase "or"
└─ tests/
   ├─ test_evaluation_metrics.py   5 tests (hand-worked examples)
   └─ test_api_search.py           + only an uppercase OR widens the search
```

## 4. Packages

None added.

## 5. Commands

```powershell
cd backend
uv run python -m scripts.evaluate            # ~15 s: compare modes with current settings
uv run python -m scripts.evaluate --sweep    # ~1 min: also try other settings
```

Open `backend/evaluation/report.md` for the tables.

## 6. How the labels were made, and their limits

**How:** Claude read the headnote (the summary on page 1) of each of the 100 judgments and decided, for each query, which judgments are relevant. **Labels were not taken from search results**, which would only check the system against itself. Every judgment was considered for every query, not just the ones search returned, so missed relevant cases count against a method.

**Before relying on the numbers:**
- **The labels are AI-drafted and unreviewed.** A legal reviewer should check `labels.json` (each query has a `need` field saying what counts as relevant) and correct the grades.
- **The collection is small:** 100 judgments, mostly 1–6 relevant per query. That makes scores look high, and finding the right case among 100 is easier than among 100,000. Differences under about 0.02 are noise.
- **P@5 has a ceiling.** With fewer than 5 relevant cases, the best possible P@5 is below 1.0 (e.g. 0.4 with 2 relevant cases). Compare P@5 between methods, not against 1.0.
- **Q23–Q28 were added after the first run,** because the first set had no specific-term searches. They were labelled the same way, from headnotes.

**How to extend it:** add a query to `labels.json` with its `need` and the relevant display IDs, then rerun. Good candidates are real searches users make, once the UI exists.

### The measures

| Measure | Meaning |
|---|---|
| **P@5** | Share of the top 5 results that are relevant |
| **R@10** | Share of all relevant cases found in the top 10 |
| **MRR** | 1 ÷ position of the first relevant result, averaged (1.0 = always first) |
| **nDCG@10** | Quality of the order, with highly relevant cases counting more; 1.0 = ideal order |

## 7. Results (2026-11-04)

### Search methods (28 queries)

| mode | P@5 | R@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| keyword | 0.19 | 0.46 | 0.57 | 0.49 |
| semantic | 0.47 | 1.00 | 0.96 | 0.94 |
| **hybrid** (default) | 0.47 | 1.00 | 0.96 | 0.93 |

- **Keyword-only is weak for descriptions.** It needs *every* word present, so plain-language queries (Q02, Q05, Q09–Q13, Q18, Q19, Q21) find nothing. It works for exact phrases and rare names.
- **Semantic and hybrid are equal here.** Hybrid stays the default: on a much larger collection, exact words (party names, citation numbers, rare provisions) matter more, and hybrid also gives highlighted keyword matches.
- **On all six specific-term searches**, semantic and hybrid put the right case first.
- **Weakest queries**:
  - Q09 "a business dispute about unpaid money was turned into a cheating case" (0.63);
  - Q12 "candidate hid a criminal case when applying for a police constable job" (0.62);
  - Q06 "default bail when charge sheet not filed within 90 days" (0.80).
  
  In each, the relevant case is found but not first.

### Similar cases (4 query judgments)

| query judgment | P@5 | R@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| S1 Boby (circumstantial-evidence murder) | 1.00 | 1.00 | 1.00 | 0.95 |
| S2 M.L. Patil (pension arrears) | 0.40 | 0.75 | 1.00 | 0.66 |
| S3 Khajan Singh (s.24(2) land acquisition) | 1.00 | 1.00 | 1.00 | 1.00 |
| S4 Qamar Ghani Usmani (default bail) | 0.40 | 0.75 | 1.00 | 0.77 |
| **average** | 0.70 | 0.88 | 1.00 | 0.85 |

**Where it falls short:**
- **Pension (S2):** the matches include service-law cases that aren't about pensions, because their wording is similar.
- **Default bail (S4):** the collection has only loosely related bail cases.

### Settings sweeps (mean nDCG@10)

| hybrid: semantic cut-off | k=5 | k=10 | k=20 | k=60 |
|---|---|---|---|---|
| 0.55 / 0.60 / 0.65 | 0.93 | **0.93** | 0.93 | 0.93 |
| 0.70 | 0.89 | 0.89 | 0.89 | 0.89 |

| similar cases: passage cut-off | k=5 | k=10 | k=20 |
|---|---|---|---|
| 0.75 | 0.85 | 0.85 | 0.85 |
| **0.80** | 0.85 | **0.85** | 0.85 |
| 0.85 | 0.76 | 0.76 | 0.76 |

**Decision: keep all settings** (semantic cut-off 0.60, passage cut-off 0.80, k = 10):
- **k** makes no measurable difference.
- **Raising either cut-off** by 0.05–0.10 clearly hurts.
- **Lowering** gains nothing measurable.

### Bug found by the evaluation, and fixed

Hybrid scored 0.56 on Q10 "pension of retired employee wrongly fixed **or** denied". The cause: PostgreSQL's web-search syntax treats a lowercase "or" as the OR operator, so the query became *"(pension AND retired AND employee AND wrongly AND fixed) **OR** denied"*. That matched 40 of the 100 judgments, including a murder appeal and a NEET admission case.

**Fix** (`keyword.normalize_query`): only an uppercase **OR** is an operator, as the API documentation always said. A lowercase "or" outside quotes is a common word. After the fix Q10 scores 0.93, and a test guards it.

## 8. How to test

```powershell
cd backend
uv run pytest tests/test_evaluation_metrics.py tests/test_api_search.py -v
```

- `test_evaluation_metrics.py`: each measure against a hand-worked example (e.g. nDCG for the order B, X, A = 2.5 / 5.393).
- `test_only_an_uppercase_OR_widens_the_search`: "murder or demolition" → no results (both words required); "murder OR demolition" → either word; "or" inside quotes is left as typed.

The evaluation itself is a measurement, not a pass/fail test. Run it after changes to search, chunking, cleaning or the model, and compare `report.md`.

## 9. Expected output

```
uv run python -m scripts.evaluate --sweep
...
| keyword  | 0.186 | 0.463 | 0.571 | 0.488 |
| semantic | 0.471 | 1.000 | 0.964 | 0.936 |
| hybrid   | 0.471 | 1.000 | 0.964 | 0.933 |
...
Saved to ...\backend\evaluation\report.md
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError` / `AttributeError: 'NoneType'` for a similar-case query | The `case` ID in `labels.json` doesn't exist (e.g. after a different import) | Check the display ID in `/api/cases` |
| All semantic scores are 0 | Model not downloaded, or chunks not embedded | `uv run python -m scripts.embed_chunks` |
| Scores change after re-importing or re-processing | Different text or chunks: expected | Compare `report.md` before and after; investigate big drops |
| A score seems wrong for a query | The label may be wrong. They're drafts | Fix the grade in `labels.json` (check the judgment's headnote), rerun |
| `UnicodeEncodeError` printing the report | Windows console encoding | Run with `uv run python -X utf8 -m scripts.evaluate` |
