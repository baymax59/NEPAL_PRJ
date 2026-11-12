# Development plan: AI-powered similar-case search

This plan is a roadmap. Each step gets its own detailed guide in `docs/steps/` **when we build it**, covering what it does, why, files, packages, commands, code, how it connects, how to test, expected output and common errors. Guides are written after the step has been run and verified, so the commands and outputs in them are real.

A step starts only after the step before it passes its tests.

---

## 1. Architecture

```
            ┌──────────────────────────── frontend (React + TS + Vite) ───────────────────────────┐
            │  Dashboard · Upload/Search · Result cards · Case details · Compare · Chat panel     │
            └───────────────────────────────────────┬─────────────────────────────────────────────┘
                                                    │ HTTP /api/...
┌───────────────────────────────────────────── backend (FastAPI) ─────────────────────────────────────────────┐
│  api/  ──►  auth/ (who are you, what may you see)  ──►  audit/ (record who did what)                        │
│    │                                                                                                         │
│    ├─► search/      keyword (Postgres full-text) + semantic (pgvector) ──► hybrid ranking                   │
│    ├─► explain/     shared terms, matching passages, differences, source references                         │
│    ├─► cases/       case details assembled from the internal schema                                         │
│    ├─► documents/   PDF/DOCX text extraction, cleaning, chunking (with page numbers)                        │
│    ├─► embeddings/  Sentence Transformers model, batch encoding                                             │
│    └─► chat/        RAG: access-checked retrieval ──► local LLM ──► answer with citations                   │
│                                                                                                              │
│  ingestion/  pipeline: connector ──► normalise to CaseRecord ──► store ──► extract ──► chunk ──► embed      │
│  connectors/ sc_judgments/ (now)        police_records/ (future, authorised)                                │
└──────────────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                       │
                                      PostgreSQL 17 + pgvector (Docker)
```

**The key design rule:** connectors are the only code that knows about a specific source. A connector turns a source record into the shared `CaseRecord` structure. Search, details, explanations and chat only ever see `CaseRecord` data. Adding police records later means writing a new connector and its access rules. The rest of the app stays as it is.

### Folder layout (grows step by step)

```
NEPAL_PRJ/
├─ docker-compose.yml          database (later also backend + frontend)
├─ .env / .env.example         settings and secrets (.env is never committed)
├─ db/init/                    SQL that runs when the database is first created
├─ data/                       git-ignored: raw downloads, processed text, uploads
├─ docs/                       this plan, dataset notes, step guides
├─ backend/
│  ├─ app/
│  │  ├─ main.py               creates the FastAPI app
│  │  ├─ core/                 settings, logging
│  │  ├─ db/                   database session, table models
│  │  ├─ schemas/              CaseRecord + API request/response models
│  │  ├─ connectors/           one sub-package per data source
│  │  ├─ ingestion/            import pipeline
│  │  ├─ documents/            text extraction and chunking
│  │  ├─ embeddings/           embedding model
│  │  ├─ search/               keyword, semantic, hybrid ranking
│  │  ├─ explain/              "why matched" and differences
│  │  ├─ auth/                 users, roles, record-level access
│  │  ├─ audit/                audit log
│  │  ├─ chat/                 RAG chatbot
│  │  └─ api/                  HTTP routes
│  ├─ alembic/                 database migrations
│  ├─ scripts/                 command-line tools (download, ingest, evaluate)
│  └─ tests/
└─ frontend/
```

---

## 2. Internal case schema (`CaseRecord`)

This is the contract between connectors and the rest of the app. It is implemented in Step 2. Any field may be empty. **Empty means "the source doesn't say"**, and the UI shows it that way.

| Field | Meaning | From SC judgments | From police records (future, to be confirmed with the data owner) |
|---|---|---|---|
| `id` | Internal UUID | generated | generated |
| `display_id` | Short human ID, e.g. `SC-ESCR010007902023` | `SC-` + `cnr` (the neutral citation is not unique) | built from FIR number |
| `source_system` | Which connector | `sc_judgments` | e.g. `police_cctns` |
| `source_record_id` | ID in the original system | `cnr` | FIR / case number |
| `reference_numbers` | Other IDs | `cnr`, `citation` | station code, FIR no. |
| `title` | Short title | `title` | to be confirmed |
| `category` | Case type/category | **empty**, not in source | crime head / sections |
| `court_or_agency` | Where it was handled | `court` | police station / unit |
| `dates` | List of `{kind, date, source_field}` | `decision_date` | registration, chargesheet, … |
| `status` | Current status | **empty** | investigation status |
| `outcome` | Recorded outcome + where it came from | `disposal_nature` | final report / disposal |
| `parties` | List of `{role, name}` | petitioner, respondent | complainant, accused (**sensitive**) |
| `officials` | Judges / officers | `judge` | investigating officer |
| `sensitivity` | `public` / `internal` / `restricted` / `confidential` | `public` | `restricted` or higher |
| `source_extra` | Source-specific fields we keep but don't standardise | other metadata | other fields |
| `provenance` | Source URL/file, checksum, fetched time, connector version | yes | yes |
| `quality` | Missing fields, extraction warnings | computed | computed |

Database tables (Step 2): `cases`, `case_documents`, `document_chunks` (text, page range, full-text index, embedding), `case_events` (timeline with source page), `ingestion_runs`. Later: `users`, `roles`, `case_access_grants`, `audit_log`, `chat_sessions`.

---

## 3. Technology choices

| Need | Choice | Why |
|---|---|---|
| API | FastAPI + Pydantic | Request checking and API docs come built in |
| Database | PostgreSQL 17 + pgvector 0.8.7 (Docker) | One database for records, full-text search **and** vectors, so no separate search server |
| ORM / migrations | SQLAlchemy 2 + Alembic | Standard, works well with pgvector |
| Python packaging | `uv` | Fast, and `uv.lock` pins exact versions |
| PDF / Word text | pypdfium2, python-docx | Accurate, keep page numbers, and permissively licensed. PyMuPDF was rejected because it is AGPL. |
| Embeddings | Sentence Transformers, starting with `BAAI/bge-small-en-v1.5` (384 dimensions) | Runs fine on CPU (this machine has no NVIDIA GPU). We compare against a larger model in Step 9 before deciding. |
| Hybrid ranking | Reciprocal Rank Fusion of keyword + semantic results | Simple and robust. One constant (k), set to 10. The Step 9 evaluation found k made no measurable difference (5–60) |
| Chat model (later) | Ollama running a small open model locally | Case text never leaves the machine. Slow on CPU but fine for a prototype. |
| Frontend | React + TypeScript + Vite + Mantine + TanStack Query | Mantine provides ready-made cards, tabs, filters and tables |
| Tests | pytest (backend), Vitest (frontend) | |

Open-source projects to evaluate when we reach the relevant step. None of these has been checked yet for licence, activity or security, and none is adopted yet:
- **OpenNyAI** (Indian legal NLP: legal entity recognition, rhetorical roles): evaluated in Step 12 and **not adopted for now**. It supports Python 3.8–3.10 and spaCy 3.2 only, its transformer model is slow on CPU, and its licence is stated inconsistently. Could run later as a separate service.
- **InLegalBERT** (`law-ai`), an Indian-legal language model, as a possible embedding upgrade in Step 9.

---

## 4. Roadmap

| Step | Module | Status |
|---|---|---|
| 0 | Environment check, dataset selection | **done** |
| 1 | Backend skeleton + PostgreSQL/pgvector | **done**, see `steps/01-backend-and-database.md` |
| 2 | Internal case schema + database tables + Alembic migrations | **done**, see `steps/02-case-schema-and-migrations.md` |
| 3 | Supreme Court connector + download small subset + import metadata | **done**, see `steps/03-sc-connector-and-import.md` |
| 4 | Document processing: PDF/DOCX text extraction, cleaning, chunking | **done**, see `steps/04-document-processing.md` |
| 5 | Case list/details API + keyword search | **done**, see `steps/05-case-api-and-keyword-search.md` |
| 6 | Embeddings + semantic search + hybrid ranking | **done**, see `steps/06-semantic-and-hybrid-search.md` |
| 7 | Similarity explanations: shared terms, provisions, passages, differences | **done**, see `steps/07-match-explanations.md` |
| 8 | "New case" workflow: upload → extract → find similar | **done**, see `steps/08-upload-and-similar-cases.md` |
| 9 | Evaluation: test queries, manual relevance labels, metrics | **done**, see `steps/09-evaluation.md` |
| 10 | Authentication, roles, record-level access, audit log | **done**, see `steps/10-auth-access-audit.md` |
| 11 | Frontend: dashboard, upload, KPI cards, details, compare | **done**, see `steps/11-frontend.md` |
| 12 | Timeline + entity extraction (with source references) | **done**, see `steps/12-timeline-and-entities.md` |
| 13 | Case chatbot (RAG with citations) | **done**, see `steps/13-case-chatbot.md` |
| 14 | Production readiness for authorised police records | **done**, see `steps/14-1-*` to `14-5-*`, `DEPLOYMENT.md`, `HANDOVER.md` |

### Step 1: Backend skeleton + database ✅
- **What:** FastAPI app with `/api/health`, PostgreSQL + pgvector in Docker, settings from `.env`.
- **Why:** everything else needs a working API and database.
- **Done when:** `GET /api/health` returns `{"status":"ok","database":"ok","pgvector":"0.8.7"}` and the tests pass.

### Step 2: Case schema + migrations ✅
- **What:** SQLAlchemy models for `cases`, `case_documents`, `document_chunks`, `case_events`, `ingestion_runs`, plus the Pydantic `CaseRecord`. Alembic creates the tables.
- **Packages:** `alembic`, `pgvector` (Python helper).
- **Connects to:** every later step reads and writes these tables.
- **Test:** migrations run up and down cleanly. A test can save a `CaseRecord` and read it back with empty fields still empty.

### Step 3: Supreme Court connector + subset import ✅
- **What:** `connectors/sc_judgments/` downloads metadata Parquet and about 100 PDFs over HTTPS, then maps each row to a `CaseRecord` (see `DATASET.md`). Includes a `SourceConnector` interface that future connectors also implement.
- **Packages:** `httpx`, `pyarrow`.
- **Test:** mapping tests on fixed sample rows (no network needed), e.g. a missing `disposal_nature` gives `outcome = None` plus a "missing field" entry. Importing twice must not create duplicates.
- **Result:** `uv run python -m scripts.sc_download` then `uv run python -m scripts.sc_import` imported 100 cases (2022–23); re-running updates them without duplicates.

### Step 4: Document processing ✅
- **What:** extract text page by page (pypdfium2 for PDF, python-docx for DOCX), clean headers and footers, and split into about 300-word chunks that remember their page numbers. Flag pages that look scanned (very little text) for later OCR.
- **Packages:** `pypdfium2`, `python-docx`.
- **Result:** 100 judgments → 1,817 pages, 2,672 chunks (median ~287 words), in about 10 s. No running headers left; no scanned pages in 2022–23.
- **Test:** small sample files in `tests/fixtures/`. Check the page numbers and that every chunk points back to its document.

### Step 5: Case API + keyword search ✅
- **What:** `GET /api/cases`, `GET /api/cases/{id}`, `POST /api/search` (keyword). Uses PostgreSQL full-text search (`websearch_to_tsquery`) with a GIN index and highlighted snippets.
- **Test:** known phrases find the right case. Filters (year, outcome) work. Unknown case ID → 404.

### Step 6: Embeddings + hybrid search ✅
- **What:** embed every chunk and store it in pgvector with an HNSW index. Keyword and semantic rankings are merged with Reciprocal Rank Fusion. The score is shown as a 0–100 **relevance** value, never as a probability.
- **Packages:** `sentence-transformers` (installs PyTorch, about 1 GB on first install). The model downloads once to a cache.
- **Test:** a paraphrased query ("murder conviction based only on circumstantial evidence") finds cases that don't use those exact words.
- **Result:** 2,672 chunks embedded in 13 min on CPU (about 3 chunks/s; query embedding about 30–70 ms). Paraphrased queries with 0 keyword hits now find the right cases. Searches take about 100–200 ms.

### Step 7: Explanations ✅
- **What:** for each result, list shared legal terms, shared statutes/sections cited (e.g. "Section 302 IPC", "Article 21", found by pattern matching), the best-matching passage pairs with page numbers, and differences (words not found, provisions only in the query). Case-vs-case differences (outcome, year) need a whole case as the query, so they arrive in Step 8. No LLM is needed for this.
- **Test:** every explanation item links to a real chunk. There are no explanations without a source.
- **Result:** 582 distinct provisions found across the 100 judgments. Each search result card carries short reasons, and `POST /api/cases/{id}/explain` gives the full breakdown. Absences are worded as "not found / not detected", because detection can miss unusual citation styles.

### Step 8: New-case workflow ✅
- **What:** `POST /api/uploads` (PDF/DOCX/TXT, size and type checked, stored outside the web root). The file is extracted and searched with the same pipeline. The upload is kept as a "query case" and is not added to the historical database. A long uploaded document is split into chunks, embedded without the query instruction, and its chunk matches are combined per historical case. Explanations then also compare the two cases: outcome, decision year, and provisions cited by only one of them.
- **Test:** uploading a historical judgment returns that same case as the top result (sanity check). Bad file types are rejected.
- **Result:** uploading Boby's own judgment returns Boby first (text similarity 1.0). An unseen 2023 judgment (John Anthonisamy, circumstantial-evidence murder) returns four circumstantial-evidence murder appeals. The fictional CASE-1042 (cheating FIR, s.482 quashing) returns Vijay Kumar Ghai v. State of West Bengal first. A 20-page upload takes about 11 s on CPU; the search about 1 s.

### Step 9: Evaluation ✅
- **What:** about 20 test queries. For each, you label the top 10 results as relevant, partly relevant or not relevant. A script calculates precision@5 and nDCG@10 for keyword-only, semantic-only and hybrid search, and for two embedding models.
- **Output:** a table that shows which setup works best on *your* labels.
- **Result:** 28 queries + 4 similar-case queries, with draft labels (AI-written from headnotes, to be reviewed). nDCG@10: keyword 0.49, semantic 0.94, hybrid 0.93; similar cases 0.85. Found and fixed a bug (lowercase "or" turned queries into OR searches). The settings sweeps showed no gain from changing k or the cut-offs, so all were kept. **Not done yet:** comparing a second embedding model (e.g. bge-base). It needs a full re-embed (30+ min on this CPU) and a larger collection to show a reliable difference.

### Step 10: Auth, access control, audit ✅
- **What:** login (JWT), roles (`viewer`, `analyst`, `admin`), record-level rules (sensitivity level + explicit grants). **One access-filter function is used by every query**: search, details, documents and chat retrieval. The audit log records user, action, case and time. Raw search text is not logged for restricted sources.
- **Packages:** `pyjwt`, `pwdlib[argon2]`.
- **Test:** a viewer cannot open a restricted case by ID, cannot find it in search, and cannot get it through chat. Each attempt is audited.
- **Result:** every data endpoint needs a login. Roles (viewer/analyst/admin) control actions; clearance + per-case grants control which cases are seen, inside every query. Uploads are private to their owner. The audit log records logins, views, searches (fingerprint only), uploads, denied attempts and role refusals. 38 security tests.

### Step 11: Frontend ✅
- **What:** dashboard, search/upload page, result cards with sort and filters, details page (sections A–H), compare view, and a placeholder for the chat panel.
- **Commands:** `npm create vite@latest frontend -- --template react-ts`, then add Mantine, React Router and TanStack Query.
- **Test:** component tests. Click through the full flow manually against the real backend.
- **Result:** React 19 + TypeScript + Vite + Mantine. Login, search with stat tiles and result cards, case details (sections A–H), compare, upload, audit log, dark mode. Checked in a real browser (Playwright): every page loads with no console errors. Screenshots in `docs/images/`.

### Step 12: Timeline + entities ✅
- **What:** pick out dated events and entities (parties, statutes, courts) from the judgment text. Every item stores its document and page and is labelled *auto-extracted, verify against source*. The OpenNyAI evaluation happens here. (Statutory provisions are already extracted in Step 7: `app/explain/provisions.py`.)
- **Result:** 1,236 timeline events for the 100 judgments (judgment 100, order under appeal 91, dated mentions 1,045; median 10 per case), each with page and method. 43 distinct courts named. OpenNyAI not adopted (Python 3.8–3.10 / spaCy 3.2 only, slow on CPU, licence stated inconsistently); rule-based extraction instead.

### Step 13: Chatbot ✅
- **What:** Ollama + a small local model. Order of operations: access check → retrieve chunks only from cases the user may see → answer **only** from those chunks with [document, page] citations → say "the records don't contain this" when nothing relevant was retrieved. Text inside documents is treated as data, never as instructions.
- **Test:** questions about restricted cases give no leakage. Questions with no answer in the records get "not found", not a guess.
- **Result:** "Ask the case assistant" on every details page, with Qwen3 4B Instruct (Apache-2.0) running locally in Ollama. Every answer lists its sources (the case record + judgment passages with pages); citations are checked in code. Restricted cases give the same 404 as missing ones, and the model is never called. On the real judgments it answered with citations, said "not found" for a fact the records don't contain, and ignored an instruction planted in a source. Of 7 answers checked by hand, one had a factual slip (a section attributed to the wrong Act), which is why the sources are always listed. About 2–4 minutes per answer on this CPU, with a hard limit of 280 seconds.

### Step 14: Production readiness for police records ✅
- **What:** a `police_records` connector built against the real field list (once access is authorised), encryption in transit and at rest, a retention and deletion job, backups, and the full stack in Docker Compose. Legal and policy requirements (including India's Digital Personal Data Protection Act, 2023, and internal police data policies) **must be confirmed with your organisation**. This plan doesn't replace that review.
- **Built in five parts, each tested before the next:**

  | Part | What | Done when |
  |---|---|---|
  | 14.1 ✅ | The whole app in Docker Compose: database, backend, frontend (production build), one command to start | `docker compose up` gives a working app on one address; data survives a restart. **Done:** `docker compose --profile app up -d`; smoke test 8/8; an upload survives a full restart |
  | 14.2 ✅ | HTTPS and hardening: TLS in front of the app, security headers, login rate limit, refusing to start with unsafe settings | plain HTTP is refused or redirected; tests for headers, rate limit and startup checks. **Done:** https://localhost:8443; smoke test 8/8 with the certificate checked; no security-policy violations; no known-vulnerable packages |
  | 14.3 ✅ | Retention and backups: delete old uploads and audit entries after a set period; backup + **tested** restore | a restore into an empty database passes the test suite's checks. **Done:** uploads deleted after 30 days, audit entries only once a period is set; backup in 9 s; restored into an empty database, which passed the smoke test |
  | 14.4 ✅ | Police-records connector template: field mapping from a placeholder field list, `restricted` by default, fictional sample data only | mapping tests pass; nothing real is used until access is authorised. **Done:** connector + import script (authorisation required); protected identities imported as confidential without names; end-to-end test of who sees what |
  | 14.5 ✅ | Deployment and handover guide: install, operate, back up, update; the items your organisation must decide or sign off | a new person can install it from the guide alone. **Done:** `docs/DEPLOYMENT.md` and `docs/HANDOVER.md`; a clean copy installed from the guide alone passed every check |

---

## 5. Ground rules (apply to every step)

1. **Never invent data.** Empty source field → empty in the database → "Not available in source" in the UI.
2. **Label AI output.** Summaries, derived categories and extracted timelines are marked as generated and link to their source passage.
3. **Similarity is relevance, not equivalence.** Every score display says so.
4. **Access check before retrieval.** Never fetch first and filter afterwards.
5. **Attribution.** The CC-BY-4.0 source is credited on every page that shows its data.
