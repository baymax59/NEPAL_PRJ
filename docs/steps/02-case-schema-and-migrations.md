# Step 2: Internal case schema + database tables + migrations

Status: **done and verified** (2026-11-03). 23 tests pass.

## 1. What this module does

- **`CaseRecord`** (`app/schemas/case_record.py`) is the single shape that every data source must be converted into. It checks the data on the way in.
- **Database tables** (`app/db/models.py`) store cases, their documents, searchable text chunks, timeline events and import runs.
- **Alembic migrations** (`backend/alembic/`) create the tables and record every later change to them, so every computer and server ends up with the same database structure.
- **`upsert_case_record()`** (`app/ingestion/store.py`) saves a `CaseRecord`. Importing the same record again updates it instead of creating a duplicate.

## 2. Why it is needed

This step makes the "add police records later without rewriting" goal possible. Connectors (Step 3 onward) only have to produce `CaseRecord`s. Search, details pages and chat only read these tables. They never see source-specific formats.

It also enforces the "never invent data" rule in code:
- A blank value (`""`, `"   "`) becomes `None`, so it is counted as missing, never shown as data.
- Each case stores a `missing_fields` list for the data-quality section of the details page.
- The outcome is stored together with the source field it came from (`outcome_source_field`).
- `sensitivity` has no default. Each connector must decide it, and the database rejects any value outside `public / internal / restricted / confidential`.

## 3. Files created or changed

```
backend/
├─ alembic.ini                          Alembic settings (no password in it)
├─ alembic/
│  ├─ env.py                            reads the DB URL from app settings
│  ├─ script.py.mako                    template for new migrations (+ pgvector import)
│  └─ versions/0001_initial_case_schema.py
├─ app/
│  ├─ core/enums.py                     allowed values: sensitivity, statuses, event sources
│  ├─ db/base.py                        Base class, constraint naming, in_check() helper
│  ├─ db/models.py                      the 5 tables
│  ├─ schemas/case_record.py            CaseRecord and its parts
│  └─ ingestion/store.py                upsert_case_record()
└─ tests/
   ├─ conftest.py                       test database + shared fixtures
   ├─ test_case_record.py               validation rules (no DB)
   ├─ test_migrations.py                upgrade / downgrade / models-in-sync
   ├─ test_store.py                     saving and re-importing
   └─ test_health.py                    (now uses the migrated test DB)
```

## 4. Packages

| Package | Version | Purpose |
|---|---|---|
| alembic | 1.20 | database migrations |
| pgvector | 0.5 | `Vector` column type for SQLAlchemy |

## 5. Commands

```powershell
cd backend
uv add alembic pgvector                  # (already done)
uv run alembic upgrade head              # create/update tables in the dev database
uv run alembic current                   # shows: 0001 (head)
uv run pytest -v                         # 23 tests
```

**How to change the database structure later.** You'll do this in several future steps:

```powershell
# 1. edit app/db/models.py
uv run alembic revision --autogenerate -m "describe the change"
# 2. open the new file in alembic/versions/ and READ it. Autogenerate can miss things
#    (e.g. it never adds CREATE EXTENSION, and it can't detect column renames).
uv run alembic upgrade head
uv run pytest                            # test_models_and_migrations_are_in_sync must pass
```

Other useful commands:

```powershell
uv run alembic upgrade head --sql        # print the SQL instead of running it (for review by a DBA)
uv run alembic downgrade -1              # undo the last migration (dev only!)
uv run alembic history                   # list migrations
```

## 6. The code, explained

### The tables

| Table | One row per | Key columns |
|---|---|---|
| `cases` | case | `display_id`, `source_system` + `source_record_id` (unique together), `title`, `category`, `outcome` + `outcome_source_field`, `primary_date`, `dates`, `parties`, `sensitivity`, `missing_fields`, `warnings`, `provenance`, `source_extra` |
| `case_documents` | source file | `doc_type`, `source_uri`, `local_path`, `sha256`, `page_count`, `extraction_status` |
| `document_chunks` | passage of text (~300 words) | `text`, `page_start`/`page_end`, `search_vector` (filled automatically by PostgreSQL for keyword search), `embedding` (384 numbers, for AI search) |
| `case_events` | timeline entry | `event_date`, `date_text` (as written), `description`, `document_id` + `page_number` + `source_excerpt`, `extraction_method` |
| `ingestion_runs` | import run | `source_system`, `parameters`, `stats`, `status` |

Design choices worth knowing:
- **NULL means "the source doesn't say".** Every core field is nullable on purpose.
- **Lists and source-specific data are stored as JSONB** (`parties`, `dates`, `source_extra`). PostgreSQL's JSON type keeps the schema simple and still lets us query inside it.
- **`primary_date`** is a copy of the first entry in `dates`, kept in its own column so results can be sorted and filtered by year quickly. Connectors must put the most important date first.
- **Allowed values use text + CHECK constraints, not PostgreSQL ENUM types.** Adding a value later is a one-line migration.
- **Two search indexes already exist on `document_chunks`.** A GIN index serves keyword search (Step 5), and an HNSW index serves vector search using cosine distance (Step 6). `EMBEDDING_DIM = 384` must match the embedding model.
- **Documents dropped from a re-import are kept, not deleted.** If a document's checksum changes, it is reset to `pending` so its text is extracted again.

### The test database

`tests/conftest.py` sets `POSTGRES_DB=casesdb_test` **before** the app is imported. It creates that database if it's missing and applies all migrations. Each test runs inside a transaction that is rolled back afterwards, so tests don't affect each other. A safety check refuses to run if the database name doesn't end in `_test`.

## 7. How it connects to other modules

- **Step 3 (connector)** builds `CaseRecord`s from Supreme Court metadata and calls `upsert_case_record()`. It also records an `ingestion_runs` row.
- **Step 4 (documents)** fills `case_documents.page_count`, `extraction_status` and `document_chunks.text`.
- **Step 5 (keyword search)** queries `document_chunks.search_vector`.
- **Step 6 (semantic search)** fills and queries `document_chunks.embedding`.
- **Step 10 (access control)** filters on `cases.sensitivity`. Steps 10–12 add tables via new migrations.

## 8. How to test

```powershell
cd backend
uv run pytest -v
```

| Test file | Proves |
|---|---|
| `test_case_record.py` (12) | blank → missing; sensitivity required and limited; unknown fields rejected; empty outcome rejected; unsafe display IDs rejected; invalid dates rejected |
| `test_migrations.py` (4) | upgrade creates all tables; downgrade removes them and upgrade re-creates them; **models and migrations are in sync**; embedding column is `vector(384)` |
| `test_store.py` (5) | missing fields stay NULL; a full record round-trips with its sources; re-import updates instead of duplicating; a changed file is re-queued; the DB itself rejects an invalid sensitivity |
| `test_health.py` (2) | as in Step 1 |

We also checked that the "in sync" test really fails when a model changes without a migration. Adding a column in memory made it report `New upgrade operations detected: add_column cases.unmigrated_column`.

## 9. Expected output

```
uv run alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial case schema

uv run pytest -v
...
23 passed in ~2s
```

Tables in the dev database: `alembic_version, case_documents, case_events, cases, document_chunks, ingestion_runs` (no rows yet).

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `test_models_and_migrations_are_in_sync` fails with `New upgrade operations detected` | You changed `models.py` without a migration | `uv run alembic revision --autogenerate -m "..."`, review it, `uv run alembic upgrade head` |
| `Target database is not up to date` when autogenerating | The dev DB is behind the latest migration | `uv run alembic upgrade head` first |
| `type "vector" does not exist` | pgvector not enabled in that database | Migration 0001 enables it. On a managed or production server where the app user isn't a superuser, a DBA must run `CREATE EXTENSION vector;` once |
| `ValidationError ... Extra inputs are not permitted` | A connector passed a field name `CaseRecord` doesn't have (typo) | Fix the field name. This is deliberate, so typos can't silently drop data |
| `ValidationError ... sensitivity Field required` | The connector didn't set sensitivity | Set it explicitly for that source |
| `violates check constraint "ck_cases_sensitivity_allowed"` | Code bypassed `CaseRecord` with a bad value | Use the `Sensitivity` enum |
| `duplicate key value violates unique constraint "uq_cases_display_id"` | Two source records produced the same display ID | Make the connector's display IDs unique (e.g. include year/source) |
| Tests stop with `Cannot reach PostgreSQL ... docker compose up -d` | The database container isn't running | `docker compose up -d` from the project root |
| `TypeError: unsupported operand type(s) for \|` when defining a Pydantic model | A field has the same name as its type (e.g. `date: date \| None`) | Write the type as `dt.date` (`import datetime as dt`), as in `case_record.py` |
| `'alembic' is not recognized` | Alembic only exists inside the project's environment | Run `uv run alembic ...` from `backend/` |
