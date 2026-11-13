# Step 15.5: Case Intelligence inside cases (phase CM-5)

> **Partly superseded (2026-11-10).** Case Intelligence (similar cases, search, timeline, offence sections, the assistant) still works as described, but on the case as it stands now (the files the person may see) instead of 'as of a commit'; its tab is called Insights. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md).

Status: **done and verified** (2026-11-08).

| Check | Result |
|---|---|
| Backend tests | 493 pass, 13 of them new |
| Frontend tests | 36 pass, 8 of them new |
| Browser walk-through | 30 of 30 steps pass (5 new), with the real embedding model and the real AI assistant |
| Docker version | rebuilt (migration 0012 applied); smoke test 8 of 8, CM-5 checks 6 of 6 |

All test data is fictional, and **nothing was created in the development database**: the tests use `casesdb_test` and the walk-through the throwaway `casesdb_e2e`.

This is part 5 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It brings the existing similar-case search (Steps 4–13) into the cases of [15.1](15-1-repository-core.md)–[15.4](15-4-screens.md).

## 1. What this phase does

The similar-case search, now called **Case Intelligence**, works **inside every case**:
- on the case **as it stood at any commit** (a branch's latest commit, or any commit of its history);
- and **only on what you may see there**.

Each case workspace has a new tab, **Case Intelligence**, with five views:

| View | What it does |
|---|---|
| **Similar cases** | Two lists: **other investigations** you may open, and **past cases** of the knowledge base (court judgments, imported records). Each result says why it was found (close passages side by side, provisions cited by both, or the **same file** in both cases), how the cases differ, and has a **Link** button: the link is a commit with your reason |
| **Search** | Search the case's documents and notes by words (with "quoted phrases", -excluded words, OR) and by meaning. Passages are highlighted, with their pages, grouped by exhibit or note |
| **Assistant** | Ask a question about the case at that commit. The answer uses only what you may see there, and cites every fact as [S1], [S2]…: the exhibit or note, its version, the page and the commit. If the records don't say, it tells you so |
| **Timeline** | Dates written in the documents and notes (each with its sentence, exhibit and page), plus dates the records hold (when exhibits were collected, official references). It is saved as a **new version in a commit**; earlier versions stay in the history |
| **Offence sections** | Sections cited in the case's documents and notes (where, and how often), and sections cited by the **most similar past cases** that this case doesn't cite yet. Well-known sections have a short heading, for orientation only |

A bar at the top says **what has been read for you** at that commit:
- documents read, and notes read;
- documents waiting to be read;
- files with no text to read (images, audio, programs, scanned pages without text recognition);
- files that couldn't be read.

**Read now** reads whatever is still waiting.

### Each file is read once

The text of a file is stored once under its SHA-256 hash. The same file can be evidence in ten clones, or in two different cases: it is still read and indexed only once, and all of them share the result (specification: "evidence indexed once per hash"). Notes and analyses are indexed the same way, by the hash of their content.

Before a file's text is read, **its hash is checked** against the hash recorded at upload. A file changed behind the application's back is never read. The check is kept as an integrity check with the reason "indexing".

### The rule of the whole phase: never more than you may see

| Situation | What Case Intelligence does |
|---|---|
| A **sealed** exhibit or note | left out of your search, answers, similar cases and offence sections, exactly as everywhere else, unless you may see sealed items (the case's supervisor and administrators) |
| An exhibit classified **above your clearance** | left out |
| An entry **withdrawn** at that commit | left out: it is history, not the case as it then stood |
| **Another investigation** you can't open | never compared, never shown |
| A **past case** above your clearance (without a grant) | never compared, never shown |
| The **timeline** (part of the case record, read by everyone on the case) | built only from what *every* member may see, whoever rebuilds it, so a supervisor's rebuild can't copy a sealed exhibit's text into it |

### Links to past cases

The Case links tab (CM-4) linked investigations. A link can now also point at a **past case** of the knowledge base, found by Similar cases. It works like any other link:
- it is an artifact at `case-links/kb-<its ID>`, added by its own commit, with a kind and a reason;
- you must be allowed to see that past case;
- the Case links tab shows it with a "past case" label, in the list and in the relationship graph.

## 2. Why it is needed

- **Phase CM-5** of the plan: *evidence documents indexed once per hash; search inside a case at any commit; Similar Cases tab (knowledge base + accessible cases) with explanations and Link; assistant on a chosen commit citing evidence, version, page and commit; timeline-reconstruction artifact; offence-section suggestions*. It is done when *a case finds its similar cases, and the assistant cites evidence*: both now pass in the tests and in the browser.
- **Document 02, Part C** ("Case Intelligence inside an investigation"): all seven points are built.
- **Document 07, "AI misuse"**: retrieval only from what the user may see, documents treated as data, citations checked, "not found" instead of guessing.

## 3. Files created or changed

**Backend**

| File | What changed |
|---|---|
| `alembic/versions/0012_case_management_intelligence.py` | new tables `object_texts`, `object_pages` (permanent) and `object_chunks` (only the meaning vector may change); integrity checks gain the reason `indexing` |
| `app/casemgmt/models.py`, `enums.py` | the three tables; `TextSourceKind`, `TextStatus`, `IntegrityTrigger.INDEXING` |
| `app/casemgmt/intelligence/scope.py` | what may be read at a commit: the user's view, or the shared view (everyone on the case) |
| `app/casemgmt/intelligence/index.py` | reading each file once (hash checked first), notes as text, meaning vectors, the coverage report, the background task after an upload |
| `app/casemgmt/intelligence/search.py` | search inside a case (words and meaning, merged by rank) |
| `app/casemgmt/intelligence/similar.py` | similar cases: the knowledge base (the existing search) and other investigations (text, provisions, same file) |
| `app/casemgmt/intelligence/assistant.py` | the assistant on a snapshot, its sources labelled with exhibit, version, page and commit |
| `app/casemgmt/intelligence/timeline.py` | the reconstructed timeline, as new versions in commits |
| `app/casemgmt/intelligence/offences.py` | offence-section suggestions, with short headings of well-known sections |
| `app/casemgmt/intelligence/api.py` | the 8 endpoints (section 7) |
| `app/casemgmt/links.py`, `workspace_api.py`, `schemas.py` | links to past cases (`knowledge_case`); the new response shapes |
| `app/casemgmt/evidence_api.py` | an upload starts reading the file's text right after the answer is sent; the text preview shares the text decoding |
| `app/casemgmt/api.py` | `Audited.error()`: a failure that isn't the user's (the AI model is down) is audited too |
| `app/similar/service.py`, `app/schemas/similar.py`, `app/chat/service.py` | small additions: a passage can say which exhibit or note it comes from; the query kind "investigation"; the assistant's instructions can be passed in |
| `scripts/e2e_prepare.py` | adds two fictional past cases to the throwaway database |
| `tests/test_cm_intelligence.py` | 13 new tests (section 8) |
| `tests/test_cm_custody_integrity.py` | expects the new "indexing" check (a text exhibit is now checked when it is read) |

**Frontend**

| File | What changed |
|---|---|
| `src/kh/repo/intelligence/` | the tab (`IntelligenceTab.tsx`) and its views: `SimilarView`, `SearchView`, `AssistantView`, `TimelineView`, `OffencesView`, shared pieces (`common.tsx`, `format.ts`) and their tests |
| `src/kh/api.ts`, `src/kh/types.ts`, `src/api/schema.d.ts` | the new endpoints and types (generated from the API description) |
| `src/App.tsx`, `src/kh/repo/RepositoryLayout.tsx` | the tab, loaded only when opened |
| `src/kh/repo/LinksTab.tsx` | links to past cases |
| `e2e/walkthrough.py` | 5 new steps (section 8) |

**Docs:** this guide; `docs/case-management/openapi.json` (regenerated); documents 04, 05, 06, 08 and the README; `DEVELOPMENT_PLAN.md`.

## 4. Packages

None new. Case Intelligence reuses what Steps 4–13 installed: pypdfium2 and python-docx (text), sentence-transformers with BAAI/bge-small-en-v1.5 (meaning, on this computer), pgvector, and Ollama with the chat model (the assistant).

## 5. Commands

The same as [15.4 §5](15-4-screens.md#5-commands): development, Docker, regenerating the frontend types, and the browser walk-through.

The walk-through's assistant step needs **Ollama running** with the chat model (`qwen3:4b-instruct-2507-q4_K_M`); on this laptop an answer takes 1–4 minutes. `scripts.e2e_prepare` now also adds two fictional past cases, using the embedding model if it is downloaded.

To read every document of the development database that is still waiting (for example after restoring a backup), open the case's Case Intelligence tab and press **Read now**, or call `POST /api/v1/repositories/{id}/intelligence/prepare`.

## 6. How it works

**The index.** Three tables, keyed by *what the text was made from* (`evidence` or `artifact`) and *that content's SHA-256*:

| Table | One row per | Changes allowed |
|---|---|---|
| `object_texts` | content: status (`indexed`, `no_text`, `unreadable`), extractor and version, pages, provisions found, warnings | none (permanent) |
| `object_pages` | page: its cleaned text, "looks scanned" | none (permanent) |
| `object_chunks` | passage: text, pages, word search vector, meaning vector | only the meaning vector and its model name (a newer model may recompute them) |

Nothing in the index says *who* may see it: that is decided on every request from the snapshot asked about (`scope.py`), inside the queries.

**When a file is read.**
1. Right after an upload is answered, in the background.
2. If that didn't happen (the server restarted, the model wasn't loaded), the next Case Intelligence request that needs it reads it:
   - notes are always read straight away;
   - documents are read for up to 10 seconds per request;
   - **Read now** keeps going for up to 90 seconds.
3. What isn't ready yet is listed in the "read for you" bar, never guessed.

**Similar cases.** The query is the investigation at that commit, as one document: its summary first, then notes and analyses, then documents. Links, timelines and reports aren't compared: they repeat other text.
- **Past cases:** the existing similar-case search (Step 8), within your clearance and grants.
- **Other investigations:** at most the 100 most recent you may open, each at the latest commit of `main` in the repository you would open. Three signals are merged by rank (Reciprocal Rank Fusion, as in Step 6):
  1. passages close in meaning;
  2. provisions cited by both, rarer ones counting more;
  3. **the same file** (identical SHA-256) as evidence in both.

Relevance (0–100) orders the results; it is not a probability.

**The assistant.** The sources are:
1. S1, the case record at that commit: type, statuses, references, and the exhibits and notes it holds (only those you may see);
2. up to four passages, chosen by meaning and by words from what you may see.

Each passage is labelled `exhibit EV-0002, version 1, pages 3–4, commit 1a2b3c…`. Then the existing rules apply:
- documents are data, never instructions;
- every fact needs a citation;
- citations to sources that don't exist are removed;
- an answer that cites nothing is flagged;
- the exact "not found" sentence is used when the records don't say.

The conversation stays in your browser; the audit log keeps only a fingerprint of the question.

**The timeline.** It uses the existing date recognition (Step 12) on the shared view of the branch's latest commit. The result is stored at `timeline/reconstructed-timeline` as an artifact of type `timeline`, version 1, 2, 3… Each version records:
- the commit it was built from;
- the sources used and not used;
- the method.

Each rebuild is a `timeline_generated` commit and goes through the same branch rules and conflict check as any commit (409 if the branch moved since you looked).

**Offence sections.** The provisions found when each file was read (Step 7's patterns), merged with where they are cited. The 10 most similar past cases add sections they cite that this case doesn't. Procedure, evidence and the Constitution are left out of the suggestions: they say how a case was handled in court, not which offence it concerns. The short headings cover well-known sections of the IPC, the BNS, the IT Act, the NDPS Act and the NI Act. Every answer carries the disclaimer that this is no legal assessment.

## 7. Endpoints in this phase

| Method and path | What it does | Who |
|---|---|---|
| `GET /api/v1/repositories/{id}/intelligence?ref=` | what of that snapshot has been read (the coverage) | members, supervisor, admin |
| `POST /api/v1/repositories/{id}/intelligence/prepare` | `{ref}`: read what is still waiting | same |
| `POST /api/v1/repositories/{id}/intelligence/search` | `{query, ref, mode, limit}`: search inside the case (POST: the words stay out of addresses and logs) | same |
| `GET /api/v1/repositories/{id}/intelligence/similar?ref=&scope=&limit=&offset=` | other investigations and past cases, with why and how they differ | same |
| `POST /api/v1/repositories/{id}/intelligence/ask` | `{question, ref, history}`: the assistant | same |
| `GET /api/v1/repositories/{id}/intelligence/offences?ref=` | sections cited here and by similar past cases | same |
| `GET /api/v1/repositories/{id}/intelligence/timeline?ref=` | the timeline as it stood at that point | same |
| `POST /api/v1/repositories/{id}/intelligence/timeline` | `{branch_id, expected_head}`: rebuild (a new version, a new commit; Idempotency-Key accepted) | writers of that branch |

`POST /api/v1/repositories/{id}/links` also accepts `knowledge_case` (a past case's ID) instead of `target_case_id`. As everywhere: anything you may not see answers 404; deletions answer 405 and are audited. The module now has **90 endpoints** (counted from the OpenAPI description).

## 8. How to test

```powershell
cd C:\case-search\backend;  uv run pytest -q                        # 493 passed
cd C:\case-search\frontend; npm test; npm run lint; npm run build   # 36 passed, no warnings, build OK
```

What the 13 new backend tests prove:

| Test | What it proves |
|---|---|
| a document is read once and shared | read right after the upload, its hash checked first, provisions found; the same file in a second case is not read again |
| the index is permanent | the database refuses to change or delete texts, pages and passages; only meaning vectors may change |
| coverage and a tampered file | an image is listed as "no text to read"; a file changed on disk fails its check, is never read, and the failure is recorded |
| search at any commit | a phone number is found in the FIR and a note; at an earlier commit only in the FIR; meaning-based search works; highlights are plain text |
| audit and access | the search words are never stored (a fingerprint only); outsiders get 404; deletion answers 405 |
| **sealed or inaccessible content never reaches results or answers** | a sealed exhibit is missing from the investigator's search, the assistant's sources, similar cases and the timeline, while the supervisor still finds it; an investigation and a past case the user may not see are never shown |
| similar cases and links | a past case is found with passages and shared provisions; another investigation with the same file; both are linked by commits and then shown as linked |
| a link needs one visible target | a past case above your clearance or unknown answers 404; both or neither target answers 422 |
| **the assistant cites evidence** | the answer cites EV-0001, version 1, page 1, at the exact commit; a made-up citation is removed; at an earlier commit the exhibit isn't a source |
| the model is down | a clear 503, and the failure is audited without the question |
| the timeline | dates from the FIR and the collection date, sorted; an exhibit classified above the case isn't used; a rebuild makes version 2 in a new commit, and version 1 is still there at the old commit; a stale branch answers 409 |
| only writers rebuild it | a supervisor who isn't a member gets 403; no dates gives a clear message |
| offence sections | BNS 318 ("Cheating") and IT Act 66D are found with where they are cited; IPC 420 is suggested from the similar past case; a CrPC section isn't |

The frontend tests check the page and source helpers, the "read for you" bar, the relevance meter, the timeline (entries, sources, rebuild button, empty state) and the assistant (the answer with its source markers and the request it sends).

**The browser walk-through** (5 new steps, with the real embedding model and the real chat model):
1. Similar cases finds the fictional past case FICT-SC-0001 and the second investigation (same file), not the unrelated FICT-SC-0002; the past case is linked in a commit.
2. The search finds the fictional phone number, highlighted.
3. The timeline is built and saved as version 1.
4. The offence sections show BNS 318 "Cheating" and IPC 420 from the similar past case.
5. The assistant answers about the case at that commit and cites at least one source.

## 9. Expected output

```text
493 passed                                          (backend)
Test Files  5 passed (5)   Tests  36 passed (36)    (frontend)
ALL 30 STEPS PASSED in 189 s                        (browser walk-through; the AI answer takes about 90 s of that)
all checks passed                                   (Docker: smoke test 8/8, CM-5 checks 6/6; 0 cases in the development database)
```

## 10. Common errors and fixes

| Problem | Cause | Fix |
|---|---|---|
| `only embedding, embedding_model may change` when adding a meaning vector | PostgreSQL computes generated columns (the word search vector) *after* BEFORE triggers, so the shared status-only check saw it change | `object_chunks` has its own check, which ignores the generated column and still compares the text it comes from (migration 0012) |
| "N waiting to be read" stays | the file wasn't read after the upload (server restart, a large file) | press **Read now**; or wait: the next Case Intelligence request reads documents for 10 seconds |
| "no text" for a scanned PDF | pages that are images need text recognition (OCR), not available yet | the bar lists such files; their title and type still appear in the case record the assistant reads, but their content can't be searched until OCR exists |
| A document "doesn't match its recorded SHA-256" | the stored file was changed or damaged outside the application | it is never read; see Evidence integrity in the admin portal and restore it from a backup |
| The assistant answers 503 | Ollama isn't running, or the model isn't installed | start Ollama; `ollama pull qwen3:4b-instruct-2507-q4_K_M` |
| An answer takes minutes | the AI model runs on this computer's processor | expected on this laptop (1–4 minutes); a server with a graphics card is much faster (document 07) |
| A past case can't be linked (404) | it is above your clearance, or its ID is wrong | ask for a grant on that case (Step 10), or check the ID |
| The admin's integrity counts show more "match" than before | text exhibits are now checked when Case Intelligence reads them | expected: that check is real and recorded (reason "indexing") |
| `Port 5180 is already in use` before a walk-through | a web server from an earlier walk-through is still running | stop that `vite` process (or reuse it if it points at port 8010) |
| A downgrade of migration 0012 fails | an older copy of 0012 had been applied without the new check function | the downgrade uses `DROP FUNCTION IF EXISTS`; downgrade to 0011 and upgrade again |
