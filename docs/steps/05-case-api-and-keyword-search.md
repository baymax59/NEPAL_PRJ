# Step 5: Case API + keyword search

Status: **done and verified** (2026-11-04). 107 tests pass. Tested against the 100 real judgments.

## 1. What this module does

Four endpoints:

| Endpoint | Returns |
|---|---|
| `GET /api/cases` | A page of case summaries (the fields a result card needs), with filters, sorting and paging |
| `GET /api/cases/filters` | Values for the filter controls: year range, outcomes and sources, with counts |
| `GET /api/cases/{display_id}` | Everything the details page needs, grouped by its sections |
| `POST /api/search` | Cases ranked by keyword relevance, each with its best passages (page numbers + highlighted words) |

It also adds the **access-control hook** that every case query passes through.

## 2. Why it is needed

This is the first time the data can be reached over HTTP. The frontend (Step 11) is built on these endpoints. Keyword search is also half of the hybrid search in Step 6, where AI similarity is added alongside it.

## 3. Files created or changed

```
backend/app/
├─ auth/access.py            AccessContext + get_access_context(): public records only until Step 10
├─ connectors/registry.py    attribution text per source
├─ schemas/cases.py          CaseFilters, CaseListParams, CaseSummary, CaseDetail, FilterOptions ...
├─ schemas/search.py         SearchRequest, SearchResponse, Passage, SnippetPart
├─ schemas/case_record.py    + DISPLAY_ID_PATTERN (shared with the API path check)
├─ cases/queries.py          list_cases, get_case_detail, filter_options
├─ search/keyword.py         keyword_search
├─ api/cases.py, api/search.py
├─ main.py                   + the two routers
└─ documents/clean.py        + ligature fix (see section 6)
backend/tests/
├─ conftest.py               + `api` client and `add_case` fixtures
├─ test_api_cases.py         13 tests
└─ test_api_search.py        15 tests
```

No new packages: everything uses PostgreSQL's built-in full-text search.

## 4. Packages

None added.

## 5. Commands

```powershell
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

Open **http://127.0.0.1:8000/docs**. Every endpoint is listed there, and **Try it out** lets you call it from the browser.

From PowerShell:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/cases?year_from=2023&outcome=Dismissed&limit=3"
Invoke-RestMethod "http://127.0.0.1:8000/api/cases/filters"
Invoke-RestMethod "http://127.0.0.1:8000/api/cases/SC-ESCR010000092023"
Invoke-RestMethod "http://127.0.0.1:8000/api/search" -Method Post -ContentType "application/json" `
  -Body '{"query": "\"circumstantial evidence\" murder", "filters": {"year_from": 2023}, "limit": 5}'
```

Search syntax: `"exact phrase"`, `-excluded`, `word OR word`. Words match by stem, so `appeals` finds *appealed*.

## 6. The code, explained

### Access control, built in from now on (`auth/access.py`)

- Every query that reads cases adds `access.case_condition()` to its `WHERE` clause. Records the caller may not see are **never loaded**; they are not fetched first and filtered afterwards.
- Until login exists (Step 10) every request gets the **anonymous** context, which sees `public` records only. All Supreme Court data is public, so everything works, and a restricted record can't leak before authentication is built.
- A restricted case and a non-existent case get the **identical** 404 response. That stops anyone from probing which case IDs exist.

### Case endpoints (`cases/queries.py`)

- **Filters:** `year_from`/`year_to` (on the case's main date), `outcome` (repeatable), `source_system`. A year filter excludes cases with **no recorded date**: an unknown date can't be claimed to fall inside a range.
- **Sorting:** `date_desc` (default), `date_asc`, `title`. Ties are broken by case ID, so paging is stable.
- **Input checking:** unknown parameters, a reversed year range, `limit` over 100 or a bad case ID → **422** with an explanation.
- **Details** return the sections of the details page: identification, overview (only what the source records), outcome **with its source field**, timeline (empty until Step 12), documents, and data quality/provenance, plus the CC-BY **attribution** for Supreme Court data. Internal file paths (`local_path`) are never returned.

### Keyword search (`search/keyword.py`)

1. `websearch_to_tsquery('english', query)` turns the text into a search expression. If it contains only common words ("the of and"), the API returns a **notice** explaining why nothing matched.
2. Every matching chunk the caller may see is ranked with `ts_rank_cd`. The **GIN index** built in Step 2 makes the match fast (72 ms on the real data).
3. A case's `keyword_rank` is the **sum of its 3 best chunks**, so one strong passage and several decent ones both count. The number is only for ordering results; it is not shown as a "relevance %". Step 6 introduces the user-facing relevance score.
4. `ts_headline` builds a snippet for each of those 3 passages, marking matched words with invisible control characters. The API splits the snippet into `{"text", "match"}` parts. **No HTML is generated**, so text inside a judgment can never inject markup into the web page. Stray control characters in the source are removed first.
5. The search uses `POST` so the query text travels in the request body, not the URL. URLs end up in server and proxy logs, and a query may later describe sensitive facts.

### Fix to Step 4 found while testing search: ligature splits

A real snippet showed `verifi cation`. Measuring showed **2,556** words split after a *fi / fl / ff* ligature (`off ence` 229 times, `fi led` 216, `offi cer` 75...). Keyword search could not find those words. The space is really in the PDFs (pdfium reports it as genuine), so the fix is a cleaning rule, decided **per document**:
- A piece is a *fragment* if it never appears on its own anywhere else in the document.
- After *fi/fl*, join if the left piece is a fragment (`fi`, `offi`, `verifi` never stand alone).
- After *ff*, many real words end that way (`off`, `staff`, `plaintiff`), so join only if the right piece is a fragment **and** starts with a vowel (`ence`, `ect`, `erent`).

Result: 2,556 → 332 splits, and nearly all of the remaining 332 are real word pairs (`plaintiff has`, `off the`, `tariff at`). `verification`, `first`, `officer` and `benefit` now have zero split occurrences.

## 7. How it connects to other modules

- Reads tables filled by Steps 3–4: cases, documents, `document_chunks.search_vector`.
- **Step 6** adds semantic (embedding) search and merges both rankings. `POST /api/search` gains `mode`, `relevance`, `match_type` and `semantic_similarity`, and the single `notice` field became a `notices` list. Keyword-only behaviour described here is still available with `"mode": "keyword"`.
- **Step 7** adds "why it matched" explanations to each search hit.
- **Step 10** replaces `get_access_context()` with the logged-in user's permissions. Nothing else changes, because every query already uses it.
- **Step 11**'s frontend calls exactly these endpoints.

## 8. How to test

```powershell
cd backend
uv run pytest -v
```

| Test file | Proves |
|---|---|
| `test_api_cases.py` | Only visible cases listed, newest first; card fields with honest gaps; year/outcome filters (including repeated `outcome`); sorting + paging; bad parameters → 422; details include outcome source, dates, provenance and documents, never `local_path`; CC-BY attribution on Supreme Court cases; **restricted and missing cases give identical 404s**; malformed ID → 422; filter counts exclude restricted cases |
| `test_api_search.py` | Stemming; the case with more matching text ranks first; phrases, exclusions, OR; passages carry pages and highlight exactly the query words; filters; paging (incl. beyond the end); **restricted cases never found**; common-words notice; snippets stay plain text even with control characters in the source; invalid requests → 422 |

## 9. Expected output (real data)

```
GET /api/cases/filters      years 2022–2023; outcomes: Appeal(s) allowed 51, Dismissed 27, Disposed off 16, ...
GET /api/cases?year_from=2023&outcome=Dismissed     total 14

GET /api/cases/SC-ESCR010000092023
  BOBY versus STATE OF KERALA, decided 2023-01-12, "Appeal(s) allowed" [from disposal_nature]
  references cnr / citation [2023] 1 S.C.R. 335 / neutral_citation 2023 INSC 23
  documents: judgment, 20 pages, extracted;   missing: category, status, summary
  attribution: Indian Supreme Court Judgments dataset (Dattam Labs), CC-BY-4.0

POST /api/search {"query": "\"circumstantial evidence\" murder"}   → 3 cases
  1. BOBY versus STATE OF KERALA   p.1–2: "Criminal Trial – [Murder] case – Case resting entirely on
     [circumstantial] [evidence] …"
POST /api/search {"query": "offence"}   → 30 cases in 72 ms
POST /api/search {"query": "the of and"} → 0 cases + notice explaining why
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `422` with `extra_forbidden` | Misspelled or unsupported parameter/field | Check the name against http://127.0.0.1:8000/docs |
| `422` "year_from must not be after year_to" | Range reversed | Swap the values |
| `404 Case not found` for a case you expect | Wrong ID, **or** the case isn't visible to you (restricted) | IDs look like `SC-ESCR010000092023`. Restricted cases are deliberately indistinguishable from missing ones |
| Search returns 0 with a notice about common words | Only stopwords in the query | Add specific terms |
| A word you can see in the PDF isn't found | The PDF text has an extraction problem (e.g. words run together) | Check `document_pages.text` for that page. If it's a cleaning issue, add a test and fix `clean.py`, then `--reprocess` |
| Highlighted parts show as plain text in your own client | Expected: snippets are `{text, match}` parts, not HTML | Render `match: true` parts with highlighting yourself |
| `/api/cases/filters` returns a case-not-found error | A route-order mistake (if you edit `api/cases.py`) | Keep `/filters` declared **before** `/{display_id}` |
| PowerShell mangles JSON quotes in `-Body` | Shell quoting | Use single quotes around the JSON, as above, or build it with `ConvertTo-Json` |
