# 01. What exists today: the Similar Case Search (Steps 0–14)

For everyone. This is what was built before the Case Management module, explained without code.

## What it does, as a user sees it

| Feature | What a user does | What happens |
|---|---|---|
| **Login and roles** | Logs in with a username and password | Sees only the cases their clearance allows (public → internal → restricted → confidential), plus any case they were granted. Three roles: viewer, analyst, admin |
| **Search** | Types a plain-English question, e.g. "murder conviction based only on circumstantial evidence" | Finds cases by words **and** by meaning (AI), ranked by relevance, with the matching passages highlighted |
| **Why it matched** | Opens a result | Sees the shared words, shared legal provisions (e.g. Section 302 IPC), matching passages with page numbers, and what's different |
| **Case details** | Opens a case | Sections A–H: identification, overview (courts, provisions), timeline, outcome, similarity analysis, documents, data quality, actions |
| **Timeline** | Looks at section C | Dated events found in the judgment text, each with its page number |
| **New case: similar cases** | Uploads a new case document (PDF, Word, text) | Gets the most similar past cases, with passage pairs side by side and the differences |
| **Case assistant** | Asks a question about a case | Gets an answer written **only** from that case's records, with sources and page numbers, or "the records don't contain this" |
| **Audit log** | (admin) Opens the audit page | Sees who logged in, searched, viewed, uploaded and asked questions. Search text is stored only as a fingerprint |

## How it is built

```
 Browser (React + Mantine)  ──HTTPS──►  Caddy web server ──►  FastAPI backend ──►  PostgreSQL + pgvector
                                                                    │
                                                    ┌───────────────┼──────────────────┐
                                             Connectors       Document pipeline     AI (on this computer)
                                       (Supreme Court data,  (PDF/Word/text → pages  embeddings: bge-small
                                        police template)      → passages → index)    assistant: Qwen3 4B via Ollama
```

| Part | Where in the code | What it does |
|---|---|---|
| Connectors | `backend/app/connectors/` | Turn each source's records into one shared case format (`CaseRecord`). Supreme Court judgments (public, CC-BY-4.0) and a police-records template (fictional data only) |
| Document pipeline | `backend/app/documents/` | Extract text page by page, remove headers and footers, split into ~300-word passages that remember their pages |
| Search | `backend/app/search/` | Keyword search (PostgreSQL full text) + meaning-based search (embeddings in pgvector), combined by rank fusion |
| Explanations | `backend/app/explain/` | Provisions cited, shared terms, matching passages, differences |
| Similar cases | `backend/app/similar/` | Compares a whole document with every case, passage by passage |
| Extraction | `backend/app/extraction/` | Dates, timeline events, courts, each with its source page |
| Case assistant | `backend/app/chat/` | Retrieval-augmented answers with checked citations; a local model only |
| Security | `backend/app/auth/`, `audit/`, `core/headers.py` | Login (Argon2 passwords, JWT), lockout, per-computer login limit, access checks inside every query, audit log, security headers |
| Operations | `docker-compose.yml`, `deploy/` | One-command Docker deployment, HTTPS (Caddy), backups with a tested restore, retention job |
| Web interface | `frontend/src/` | Search, case details, similar cases, upload, case assistant, audit page |

**Database:** 13 tables. `cases` and their `case_documents`, `document_pages`, `document_chunks` (the passages, with embeddings), `document_provisions`, `case_events` (timeline), `case_entities`; `uploads` and `upload_chunks`; `users`, `case_access_grants`, `audit_events`; `ingestion_runs`.

## How it was checked

- **325 backend + 12 frontend automated tests.**
- **Search quality** measured on 32 test questions: combined search nDCG@10 = 0.93. The test labels were drafted with AI help and await a lawyer's review.
- **Browser checks** of every page, a **security review** (static analysis clean, no secrets in code or images), a **restore test** of the backups, and a **fresh install** from the guide.

## What it is not (yet)

It is a **search-and-understand** tool over a collection of cases. It does **not** manage a live investigation: there are no case workflows, evidence versions, chain of custody, investigators working on a case together, reviews or approvals, and no "never delete" guarantees. **That is what the Case Management module adds.** Document 02 shows how the two fit together.

Detailed step-by-step guides: [`docs/steps/`](../steps/). Installation: [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md).
