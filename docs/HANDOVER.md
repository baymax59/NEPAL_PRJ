# Handover: Similar Case Search

For the people taking the system over: the project owner, IT, and the data protection officer.

## 1. Status in one paragraph

A working prototype of AI-assisted similar-case search. It takes a new case document, finds and ranks similar historical cases by keywords and meaning, explains each match with its sources, and shows a structured details page with a timeline and a case assistant (chatbot) that answers only from the case's records. It is built and tested with **public Indian Supreme Court judgments** and with **fictional** police records. It is **not yet approved for real police records**: the decisions in section 4 come first. Everything runs on one computer, in Docker, with no outside services.

## 2. What was built

| Step | What | Guide |
|---|---|---|
| 1–2 | Backend (FastAPI), PostgreSQL + pgvector, the shared case format every source maps to | `docs/steps/01-*`, `02-*` |
| 3 | Supreme Court connector: download, import (CC-BY-4.0 data, attributed on every page) | `03-*` |
| 4 | Document processing: PDF/Word/text, cleaning, passages with page numbers | `04-*` |
| 5–6 | Keyword, meaning-based (AI embeddings) and combined search | `05-*`, `06-*` |
| 7 | "Why it matched": shared terms, provisions, passages, differences | `07-*` |
| 8 | New-case upload → similar cases | `08-*` |
| 9 | Search-quality evaluation (28 queries + 4 similar-case tests) | `09-*` |
| 10 | Logins, roles, clearances, per-case grants, audit log | `10-*` |
| 11 | Web interface: search, result cards, details (sections A–H), compare, upload, audit | `11-*` |
| 12 | Timelines and courts, each with its source page | `12-*` |
| 13 | Case assistant (local AI model, answers cite their sources) | `13-*` |
| 14 | Production readiness: Docker, HTTPS and hardening, retention and backups, police-records connector template, this handover | `14-1-*` … `14-5-*`, [DEPLOYMENT.md](DEPLOYMENT.md) |

## 3. How it was verified

| What | Result |
|---|---|
| Automated tests | **325 backend** tests (search, access control, audit, uploads, chatbot, hardening, retention, police connector…), **12 frontend** tests |
| Search quality (Step 9) | nDCG@10: combined search 0.93, meaning-based 0.94, keyword-only 0.49; similar cases 0.85. **On draft labels written with AI help: to be reviewed by a legal expert** (section 4, item 9) |
| Access control | users never see, find, open or ask the assistant about a case above their clearance; "not found" is identical for hidden and missing cases; attempts are audited |
| Case assistant | 7 answers checked by hand against the judgments: correct citations, "not found" when the records don't say, a planted instruction ignored; **one factual slip** (a section attributed to the wrong Act) |
| Browser | every page in a real browser with no console errors; over HTTPS with no security-policy violations |
| Backups | a backup restored into an empty database, which then passed the smoke test |
| Installation | a clean copy installed by following [DEPLOYMENT.md](DEPLOYMENT.md) alone: built, users created, fictional FIRs imported, smoke test 8/8 over HTTPS, a user deactivated and reactivated, backup and restore check passed (`docs/steps/14-5-*`) |
| Known vulnerabilities | none in 99 Python packages or the npm packages (6 Nov 2026). Repeat monthly |
| Internal security review | static analysis clean, no secrets in Git or images, 12 findings (none high): [SECURITY_REVIEW.md](SECURITY_REVIEW.md) |

## 4. Decisions needed before real police records

None of these is technical, and the system can't make them. Each has a place in the system where the decision is applied.

**To record them:** the sign-off form [DECISIONS.md](DECISIONS.md), with a recommendation for each. **To see what is still open**, decisions and technical checks together: `cd backend; uv run python -m scripts.readiness_check`.

**Tools ready for the people involved:** the legal expert's review sheet (`backend/evaluation/review/`, decision 9); the export inspector and `format.json` for the data owner's first sample (`scripts.police_inspect`, decision 2).

| # | Decision | Who decides | Where it is applied | Status |
|---|---|---|---|---|
| 1 | **Legal basis and authorisation** to process police records here (DPDP Act 2023, police data policies), and for what purpose | Legal / data protection officer | `--authorisation` on every import, stored and audited | open |
| 2 | **The real export**: field list, codes, identity rule, how updates and deletions arrive (`docs/steps/14-4-*`, section 7) | Data owner, with a developer | `app/connectors/police_records/fields.py`, `mapping.py`, and their tests | open |
| 3 | **Protected identities** (victims of sexual offences, children): is "confidential, names not imported" right? Must FIR texts be redacted too? (The template doesn't redact texts.) | Legal / data owner | `mapping.py` | open |
| 4 | **Retention periods**: uploads, audit log, records; closed, sealed or expunged cases | Data protection officer | `UPLOAD_RETENTION_DAYS` (now 30), `AUDIT_RETENTION_DAYS` (now: keep) | open |
| 5 | **Who may see what**: roles and clearances per job; the per-case grant process; joiners and leavers | Management | `scripts.create_user`, `scripts.grant_access` | open |
| 6 | **Hosting**: which computer, where, who administers it; disk encryption | IT | [DEPLOYMENT.md](DEPLOYMENT.md), section 1 | open |
| 7 | **Network and certificate**: who can reach it; certificate from the organisation | IT / security | DEPLOYMENT.md, section 7 | open |
| 8 | **Backups**: an encrypted place that is not cloud-synced, a second copy, who runs the monthly restore check | IT | `BACKUP_DIR`; DEPLOYMENT.md, section 6 | open |
| 9 | **Expert review of the search-quality labels** (`backend/evaluation/labels.json`), then re-run the evaluation | A legal expert | `uv run python -m scripts.evaluate` | open |
| 10 | **Use of the AI**: the assistant's answers are checked against their sources and never decide guilt or action; staff told so | Management | the disclaimers in the interface | open |
| 11 | **Independent security review** before real data | Security | | open |
| 12 | **Move the project out of OneDrive**: the development copy is in a OneDrive folder, so its uploads and backups would be copied to the cloud | IT / developer | DEPLOYMENT.md, section 1 | open |

## 5. Known limitations

- **Search quality is measured on 100 Supreme Court judgments with draft labels.** Police records are untested: there are none yet.
- **English only. No OCR**: scanned documents are flagged, not read.
- **Case assistant**:
  - slow without a graphics card (2–4 minutes per answer), and one question at a time;
  - a small model can be wrong (one slip in seven checked answers), so every answer lists its sources.
- **Login is by password only.** No single sign-on or second factor, which police systems usually require. The design allows adding it.
- **The audit log is protected by access rules, not made tamper-evident** (no hash chain, no write-once storage). Add that if your policy requires it.
- **The per-computer login limit** is kept in memory and resets on restart. Behind one proxy, users share it.
- **The police connector is a template** (placeholder fields). FIR texts are not redacted.
- **Not done** (planned in Step 9): comparing a larger embedding model.
- **No automatic monitoring or alerts.** There is a health address (`/api/health`) for a monitoring tool to watch.

## 6. Components and licences

| Component | Licence |
|---|---|
| Indian Supreme Court Judgments dataset (Dattam Labs) | CC-BY-4.0: credit shown on every page with its data |
| Embedding model BAAI/bge-small-en-v1.5 | MIT |
| Chat model Qwen3 4B Instruct 2507 (via Ollama, MIT) | Apache-2.0 |
| PostgreSQL / pgvector | PostgreSQL licence |
| Python libraries (FastAPI, SQLAlchemy, sentence-transformers, PyTorch, pypdfium2, python-docx, …) | MIT / BSD / Apache-2.0. PyMuPDF was rejected because it is AGPL |
| Web interface (React, Mantine, TanStack Query, Vite) | MIT |
| Caddy web server | Apache-2.0 |

The sample case `samples/CASE-1042-fictional.txt` and `samples/police-records-FICTIONAL/` are invented and labelled as such.

## 7. Where things are

```
README.md                  quick start for developers
docs/DEPLOYMENT.md         installing and running it (IT)
docs/HANDOVER.md           this document
docs/DEVELOPMENT_PLAN.md   the roadmap, every step marked done
docs/steps/                one guide per step: what, why, files, commands, code, tests, expected output, errors
docs/DATASET.md            the Supreme Court data: fields, decisions, licence
backend/                   API, connectors, search, AI, scripts, tests
frontend/                  web interface
deploy/                    web server configuration, backup and restore scripts, certificate folder
samples/                   fictional test material
docker-compose.yml         database; the whole application (--profile app); backups (--profile backup)
```
