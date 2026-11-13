# 02. Feature correlation: how the existing system fits into Case Management

> **Earlier design (superseded on 2026-11-10).** This document describes the first, git-style design of Case Management: an original repository, clones, branches, commits, reviews, merges and invitations. The owner asked for that to be removed completely and replaced by a plain case (permanent folders made at registration, files with versions, a team the Investigator builds directly, one numbered history). **The current design is in [13-plain-case-design.md](13-plain-case-design.md).** It is kept here for the record: where it says repository, clone, branch, commit, review or invitation, read the plain case instead.

For everyone. Part A starts from what exists; Part B from what the Case Management specification requires; Part C shows how they work together inside one case.

**Names used:**
- **Case Management**: the new Knight Hawk module.
- **Case Intelligence**: the existing Similar Case Search, now a feature of that module.
- **Knowledge base**: the collection of past cases that Case Intelligence searches. Today that's the Supreme Court judgments; later it also holds imported records and closed Knight Hawk cases.

## A. Every existing feature, and its place in the module

| Existing feature | In Case Management | How |
|---|---|---|
| Login, passwords, lockout, per-computer limit | **Reused** | The same login for the whole module. Adds **MFA** for administrators and supervisors (CM-7) |
| Roles viewer / analyst / admin | **Extended** | Organisation roles become platform administrator, supervisor, investigator, analyst, viewer/auditor. **Per-case roles** (lead, contributor, analyst, viewer) are added on each repository (CM-1, CM-3) |
| Clearance + per-case grants, checked inside every query | **Extended** | Same principle, with three more conditions: the user's **organisation** (tenant), **membership** of the case, and whether a commit is in the **history the user's clone can reach** |
| Audit log (own transaction, fingerprints, refusals recorded) | **Extended** | Becomes **tamper-evident**: each entry holds the hash of the previous one, and signed checkpoints are stored separately (CM-7) |
| Connectors + `CaseRecord` | **Reused** | They keep filling the knowledge base. The police template becomes the import path for authorised records |
| Export inspector + `format.json` | **Reused** | For police exports and other integrations (CM-6) |
| Document pipeline (PDF/Word/text → pages → passages) | **Reused** | Every document added to a case as evidence is processed the same way, **once per unique file** (files are stored by their SHA-256 hash) (CM-5) |
| Keyword + meaning search | **Reused + extended** | Searches the knowledge base as now, and also **within a case** at any commit (CM-5) |
| "Why it matched" explanations | **Reused** | Shown for every similar case found for a repository |
| Similar cases for an upload | **Extended** | Each case repository gets a **Similar Cases** tab. The query is the case's current content; results come from the knowledge base **and** other cases the user may see. A found case can be **linked** to the investigation, recorded as a commit (CM-5) |
| Provision extraction | **Reused** | Suggests offence sections for a case, and links cases that share provisions |
| Timeline extraction | **Extended** | Builds a **timeline-reconstruction artifact** from a case's documents. Each rebuild is a new version, never an overwrite (CM-5) |
| Case assistant (answers only from records, checked citations) | **Extended** | Answers about a case **at a chosen commit**, citing evidence IDs, versions and pages (CM-5) |
| Upload of a new case | **Extended** | An upload can become **evidence in a case**, keeping its SHA-256 hash and provenance |
| Retention job (deletes old uploads) | **Changed** | Case records are **never** deleted by a job. Retention becomes a formal **compliance workflow** with legal holds. Scratch uploads in Case Intelligence keep their 30-day clean-up, since they aren't case records (CM-7) |
| Backups with tested restore | **Extended** | Also cover the evidence store, which uses write-once storage in production (CM-2, CM-7) |
| HTTPS, security headers, size limits | **Reused** | Unchanged. Evidence downloads add short-lived download tokens (CM-2) |
| Docker deployment | **Extended** | Adds a background worker and its queue (CM-7) |
| Readiness check, decisions form, security review | **Extended** | New go-live checks for the module (CM-8) |
| Web interface (React, Mantine, TanStack Query) | **Extended** | New screens: workspace, files, branches, commits, lineage graph, reviews, admin registry. A dark navy theme for the module (CM-4) |

## B. Every Case Management requirement, and what it builds on

The section numbers refer to the specification.

| § | Requirement | Status | Builds on |
|---|---|---|---|
| 2 | No deletion, no history rewriting, no evidence overwriting | **New** | API (no destructive endpoints), service rules, database triggers, write-once storage |
| 5–6 | Case families, original repository, automatic creation of V1 | **New** | Users, audit |
| 7 | Clone from any authorised historical commit | **New** | (the core of the module) |
| 8 | Investigation branches | **New** | |
| 9 | Evidence explorer, immutable originals, versions, sealing | **New** | Document pipeline, upload checks, size limits |
| 10 | Commits as a directed acyclic graph, server-side hashes | **New** | |
| 11 | History, compare, read-only historical view | **New** | |
| 12 | Contributors, invitations, revocation | **New** | Clearance and grants |
| 13 | Review requests and approved merges | **New** | |
| 14 | Admin registry and lineage graph | **New** | Audit page |
| 15 | Investigator workspace (active clone only) | **New** | Web interface |
| 16 | Separate statuses (official, workflow, clone, review) | **New** | |
| 17 | Log analyzer, CDR, IPDR, OSINT, alerts: "Add to case" | **New** | Connectors, provenance fields, export inspector |
| 18 | Normalised schema with constraints | **Extended** | 13 existing tables, Alembic migrations |
| 19 | Versioned REST API with OpenAPI | **Extended** | FastAPI. New routes under `/api/v1` |
| 20 | Security, chain of custody, tamper-evident audit | **Extended** | Auth, audit, HTTPS, backups |
| 21 | 20 screens, dark navy theme | **Extended** | React, Mantine |
| 22 | PDF reports with integrity information | **New** | Timeline, provisions |
| 23 | Fictional demo case KH-2026-0001 | **New** | Fictional samples |
| 24 | Automated tests | **Extended** | 325 + 12 existing tests |
| — | Similar cases, explanations, assistant, timeline **inside a case** | **New** | All of Case Intelligence |

## C. Case Intelligence inside an investigation

What an investigator gets that a plain case tracker wouldn't:

1. **Similar Cases tab.** "Which past cases look like this one?" The query is the active clone's current summary, notes and document evidence. Results come from the knowledge base and from other cases the investigator may access. Each result shows why it matched, and can be **linked** to the case (a commit records the link).
2. **Search inside a case**, at any commit: "find every mention of this phone number in V2 as it stood at commit C5".
3. **Case assistant on a chosen state of the case:** "What does the bank statement say about the transfer on 3 March?" It answers only from that snapshot, citing **evidence ID, version, page and commit**.
4. **Timeline reconstruction:** dates and events extracted from the evidence documents become a timeline artifact. Rebuilding it creates a new version, never an overwrite.
5. **Provisions and offence sections** detected in FIRs and documents suggest the crime category and connect cases.
6. **Content-addressed processing:** a file is stored once under its SHA-256 hash. If the same file is evidence in several clones, it is extracted and indexed once, and every clone shares the result.
7. **Access is never bypassed:** Case Intelligence sees only what the user may see. A sealed exhibit, or a sibling clone the user may not access, never appears in their results or answers.

## D. All types of cases

- **Case type** is a configurable list (cyber fraud, financial fraud, theft, robbery, murder, missing person, narcotics, cyber stalking, civil dispute, other…) plus custom types per organisation. **No field is specific to one crime**: fields like "reported loss" are optional.
- **Folder templates per case type.** A fraud case starts with `complainant/`, `digital-evidence/`, `cdr-analysis/`…; a missing-person case with `last-seen/`, `witness-statements/`…; everything stays editable.
- **Branch types** are suggestions per case type, not a fixed list.
- **Similarity works across types:** it matches meaning and provisions, whatever the type.
