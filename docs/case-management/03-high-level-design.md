# 03. High-level design

> **Earlier design (superseded on 2026-11-10).** This document describes the first, git-style design of Case Management: an original repository, clones, branches, commits, reviews, merges and invitations. The owner asked for that to be removed completely and replaced by a plain case (permanent folders made at registration, files with versions, a team the Investigator builds directly, one numbered history). **The current design is in [13-plain-case-design.md](13-plain-case-design.md).** It is kept here for the record: where it says repository, clone, branch, commit, review or invitation, read the plain case instead.

For technical readers: architects, developers, IT.

## 1. Goals and non-goals

**Goals**
- A **GitHub-inspired, immutable** case management module for police investigations of **any case type**.
- Repositories, clones, branches and commits, built on application-controlled metadata. No real Git is involved.
- Immutable evidence with SHA-256 integrity, chain of custody, and a tamper-evident audit trail.
- Collaboration with review and approval, and complete lineage visibility for administrators.
- **Case Intelligence** (similar cases, explanations, search, timeline, assistant) inside every case.
- On-premises, HTTPS, server-side authorisation everywhere, nothing sent to outside services.

**Non-goals**
- Creating official FIRs. Official references are recorded, never generated.
- Collecting data from third parties, or interception.
- Claiming court admissibility.
- Microservices. This is a **modular monolith** with clear internal boundaries.

## 2. Principles (from the specification)

1. A case is a **case family** with one permanent **original repository** (`ROOT`). Its creation metadata never changes.
2. Investigators work in **clones** (`V1`, `V2`…). A clone can start from **any authorised historical commit**, and records its parent repository, source commit and a mandatory reason.
3. An investigator's dashboard shows only their **active** clone. Earlier clones are preserved, not shown as active cases.
4. Administrators see the **whole lineage**, within their organisation.
5. **Evidence bytes never change.** Corrections, transcriptions and analyses are new records referencing the original.
6. **Branches** are lines of enquiry; **files** are evidence and artifacts inside them.
7. **No destructive operations**: no delete, force-push, hard reset, history-rewriting rebase or overwrite. Closing a case is a status, not deletion.

## 3. Logical architecture

```
                                   KNIGHT HAWK PLATFORM (navigation, SSO, notifications: when available)
                                                         │
                                         Authentication · MFA · roles · tenancy
                                                         │
┌──────────────────────────────── CASE MANAGEMENT MODULE (modular monolith, FastAPI) ────────────────────────────────┐
│                                                                                                                     │
│  Case Registry          Repository Engine          Evidence Service           Collaboration         Review & Merge  │
│  case families,         ROOT/clones, branches,     content-addressed store,   members, invites,    review requests, │
│  official refs,         commits (DAG), snapshots,  versions, custody,         tasks, notes,        decisions, merge  │
│  statuses, links        lineage, history, compare  integrity, sealing         comments, notices    commits          │
│                                                                                                                     │
│  Case Intelligence (existing feature): similar cases · explanations · search · timeline · provisions · assistant  │
│                                                                                                                     │
│  Integrations: Add-to-case from Log Analyzer / CDR / IPDR / OSINT / alerts, with provenance                         │
│  Reporting: PDF reports, versions, verification          Governance: legal holds, retention workflow, checkpoints   │
│                                                                                                                     │
│  Audit Engine: append-only, hash-chained events, signed checkpoints (used by every part above)                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
          │                         │                              │                             │
   PostgreSQL + pgvector      Evidence store (write-once:     Background worker + queue      Local AI (Ollama,
   (records, graph, audit)    local volume / S3 Object Lock)  (large imports, reports,       embeddings in process)
                                                              integrity sweeps)
```

| Domain | Owns | Never does |
|---|---|---|
| Case Registry | case families, official references, case type, statuses, links | delete a case |
| Repository Engine | repositories, branches, commits, snapshots, lineage, active assignments | rewrite a commit, move a branch head without an event |
| Evidence Service | evidence items, versions, binary objects, custody, integrity checks, sealing | change stored bytes |
| Collaboration | memberships, invitations, tasks, notes (versioned), comments, notifications | remove contribution history |
| Review & Merge | review requests, decisions, merge commits | hide rejected work |
| Case Intelligence | indexing of evidence text, similarity, explanations, assistant, timeline | see anything the user may not |
| Integrations | imports with provenance | collect data without authorisation |
| Reporting | report generation, versions, verification hashes | claim admissibility |
| Audit Engine | the event chain and checkpoints | allow edits |

Each domain is a Python package under `backend/app/casemgmt/`. The domains talk to each other through service functions, never through each other's tables.

## 4. Deployment

```
Browser ──HTTPS 443──► Caddy (web, TLS, headers) ──► backend (FastAPI, non-root)
                                                          │
                          ┌───────────────┬───────────────┼─────────────────┬────────────────────┐
                    PostgreSQL 17      evidence store   worker (same image)  queue (Valkey)     Ollama (host)
                    + pgvector         (volume or S3    for long jobs        (added in CM-7)    case assistant
                                        Object Lock)
```

Docker Compose for development and single-server installs, as today. The design keeps Kubernetes possible: the backend is stateless, and the evidence store and database are external services.

## 5. Main flows

**Create a case** (one database transaction):
1. Validate the input.
2. Create the case family and the `ROOT` repository.
3. Create the initial commit, holding the case summary and official references.
4. Create branch `main`, then clone `V1` from `ROOT`'s initial commit.
5. Make `V1` the lead investigator's active workspace.
6. Write the audit events.

**Clone an investigation** (one transaction):
1. Check that the source commit is in history the user may see.
2. Create the new repository, recording its parent repository, source commit and reason.
3. Create a base commit whose parent is the source commit, and point `main` at it.
4. Move the active assignment to the new clone, and mark the old clone `Superseded`. Nothing in the old clone changes.
5. Write the audit events.

**Add evidence:**
1. Stream the upload, hashing it with SHA-256 as it arrives.
2. Store the bytes write-once, under the hash.
3. Create the evidence item and its version, plus a custody event ("ingested").
4. Commit on the chosen branch.
5. Queue text extraction and indexing for Case Intelligence. A file already processed (same hash) is reused.

**Branch, review, merge:**
1. Create a branch from a commit and commit work on it.
2. Open a review request. The supervisor approves it.
3. Create a **two-parent merge commit** on `main`. Conflicting changes to the same file are not overwritten: they become a new reviewable version.

**Add to case** from the Log Analyzer, CDR, IPDR, OSINT or alerts:
1. Call the integration API with the source system, source record ID and source hash.
2. Store an immutable reference record.
3. Commit, and write an audit event.

**Similar cases for a case:**
1. Build a query document from the active snapshot.
2. Run the existing similar-case search over the knowledge base and other accessible cases.
3. Show why each matched, with a "Link" action.

**Report:**
1. Generate a PDF from a chosen commit: identification, timeline, evidence inventory with hashes, custody, findings, approvals, commit references.
2. Store it as a versioned artifact with its own hash, and log the export.

## 6. Technology choices

| Need | Choice | Why (and how it differs from the specification's suggested stack) |
|---|---|---|
| API | FastAPI, Pydantic, SQLAlchemy 2, Alembic | As specified; already in use |
| Database | PostgreSQL 17 + pgvector | As specified; already in use (pgvector serves Case Intelligence) |
| Frontend | React, TypeScript, Vite, TanStack Query, React Router, **Mantine** | The specification allows "shadcn/ui **or equivalent** accessible component library" and says to **reuse existing infrastructure**. Mantine is already in use, so there is one design system instead of two. Dark navy theme via Mantine's theme |
| Lineage and investigation graphs | **React Flow** (`@xyflow/react`, MIT) | As specified |
| Diffs | a read-only side-by-side text/JSON diff (`diff` library, BSD) | Lighter than Monaco for read-only comparison; Monaco remains an option |
| Dashboards | Recharts (MIT) | As specified |
| Live notifications | Server-Sent Events | Simpler than WebSockets for one-way notices |
| Evidence storage | **Content-addressed, write-once store** behind an interface: a local volume (development, single server) and **S3 Object Lock in compliance mode** (production) | The specification asks for MinIO "subject to verified immutability support". MinIO is **AGPL-3.0**, and how its free edition is distributed has changed recently, so it needs a licence check first. The interface keeps MinIO, Ceph or any S3 store with Object Lock possible |
| Queue and worker | **Valkey** (BSD-3, the open-source Redis fork) + RQ (BSD) | Redis 7.4+ is no longer under an open-source licence; Valkey is a drop-in replacement |
| PDF reports | ReportLab (BSD) | Pure Python on Windows and Linux |
| MFA | TOTP via `pyotp` (MIT) | Works with any authenticator app; no outside service |
| Malware scanning | ClamAV (GPL-2.0) as a **separate** service | Optional; a separate process, so its licence doesn't affect this code |
| Tests | pytest, HTTPX, Playwright, TypeScript strict | As specified; already in use |

## 7. Integration with the rest of Knight Hawk

No Knight Hawk platform code exists on this computer yet (checked 7 Nov 2026), so the module is built standalone with clear connection points:

| Connection point | Now | When the platform exists |
|---|---|---|
| Login | the module's own login (JWT) | OpenID Connect / SSO from the platform; the module's roles stay the same |
| Navigation | the module's own menu | embedded under the platform menu |
| Log Analyzer, CDR, IPDR, OSINT, alerts | an **"Add to case" API** + a fictional test source | the platform's screens call the same API |
| Notifications | the module's own notices (SSE) | forwarded to the platform's notification service |

## 8. Size assumptions

Built for the order of tens of thousands of cases, hundreds of evidence items per case, and up to about 100 concurrent users on one server. Snapshots store full manifests (a list of entries), shared between commits when identical. Very large raw datasets (log or CDR dumps) stay in their source systems: only references, hashes and derived results are stored.
