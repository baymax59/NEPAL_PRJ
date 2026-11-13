# 08. Implementation plan

> **Earlier design (superseded on 2026-11-10).** This document describes the first, git-style design of Case Management: an original repository, clones, branches, commits, reviews, merges and invitations. The owner asked for that to be removed completely and replaced by a plain case (permanent folders made at registration, files with versions, a team the Investigator builds directly, one numbered history). **The current design is in [13-plain-case-design.md](13-plain-case-design.md).** It is kept here for the record: where it says repository, clone, branch, commit, review or invitation, read the plain case instead. The rebuild's own plan is document 13, section 6.

For everyone. The module is built in **8 phases**, in the same way as Steps 0–14: **each phase is built, tested and documented before the next one starts**, with a guide per phase in `docs/steps/` (`15-1-…`, `15-2-…`).

## Phases

| Phase | What it delivers | Proven by | Done when |
|---|---|---|---|
| **CM-1 Repository core** | Organisations and roles; case families; ROOT + initial commit + `main` + V1 created automatically; commits with server-side SHA-256 and shared snapshots; branches with forward-only, conflict-safe heads; **clone from any authorised historical commit**; history, compare, read-only snapshots; lineage; **no-deletion** (405 + audit, database triggers). API only | ~40 automated tests | acceptance steps 1–3, 5, 10–14 and 16 pass through the API. **Done 2026-11-07:** 51 tests, see `steps/15-1-repository-core.md` |
| **CM-2 Evidence** | Content-addressed, write-once evidence store; upload with SHA-256 and content checks; evidence items and versions; derived artifacts; chain of custody with acknowledgement; integrity verification; sealing; signed downloads; virtual folders per case type | tests incl. a **deliberately tampered file failing verification** | acceptance steps 4 and 15. **Done 2026-11-07:** 60 tests, see `steps/15-2-evidence.md`; new decision D14 (evidence storage) |
| **CM-3 Collaboration and review** | Members, invitations (organisation and clearance checks, supervisor approval), revocation; tasks; versioned notes; comments; review requests; decisions; **two-parent merge commits** with conflict detection; notifications | tests incl. "contributors cannot grant themselves privileges", "revoked contributors lose access" | acceptance steps 6–9. **Done 2026-11-07:** 36 tests, see `steps/15-3-collaboration-and-review.md`; also assigned branches, Idempotency-Key, sealed notes |
| **CM-4 Screens** | Investigator workspace (GitHub-like overview, files and evidence, branches, commits, compare, history, clone dialog, contributors, tasks, reviews); admin portal (registry, **React Flow lineage graph**, evidence integrity, audit); dark navy theme | component tests + Playwright walk-through | every screen of spec §21 works in a browser. **Done 2026-11-07:** all 20 screens, 25-step browser walk-through, see `steps/15-4-screens.md`; also live notices (SSE), case links and a report preview |
| **CM-5 Case Intelligence inside cases** | Evidence documents indexed once per hash; search inside a case at any commit; **Similar Cases** tab (knowledge base + accessible cases) with explanations and **Link**; assistant on a chosen commit citing evidence, version, page and commit; timeline-reconstruction artifact; offence-section suggestions | tests incl. "sealed or inaccessible content never reaches results or answers" | a case finds its similar cases, and the assistant cites evidence. **Done 2026-11-08:** 13 tests and 5 browser steps (real models), see `steps/15-5-case-intelligence.md`; also links to past cases and "the same file" between investigations |
| **CM-6 Integrations** | **Add-to-case** API with provenance for log events, alerts, CDR, IPDR, OSINT and indicators (IP, domain, phone, IMEI, IMSI); a fictional test source; the integration contract for Knight Hawk | tests incl. provenance and access policy | an imported finding appears as an immutable reference, with a commit and an audit event. **Done 2026-11-08:** 10 tests and 3 browser steps (one over HTTP with a source key), see `steps/15-6-integrations.md` and the contract, document 09; also identifiers matched across cases, source keys stored only as hashes, a fixed policy per source with its legal basis |
| **CM-7 Reports and governance** | PDF reports (ReportLab) with provenance, hashes, custody and approvals; report versions and verification; **hash-chained audit**; legal holds; retention as a compliance workflow; audit checkpoints and chain verification; TOTP MFA for privileged roles; runtime database role without delete rights; background worker (Valkey + RQ) | tests incl. "a changed report fails verification" and "an edited audit row breaks the chain" | acceptance step 17. **Done 2026-11-08:** 12 tests and 4 new browser steps (the walk-through's API on the application's own database login), see `steps/15-7-reports-and-governance.md`; a small worker instead of Valkey + RQ (decision 10); new go-live decisions D15 and D16 |
| **CM-8 Demo and acceptance** | Fictional demo case **KH-2026-0001 "Online banking fraud"**, seeded with evidence, V1 commits, a wrong finding, V2 from an earlier commit, a contributor, a CDR branch, an approved review and a merge; the **17-step acceptance scenario** as one automated test; admin and investigator guides; readiness checklist | the scenario test + a browser run | all 17 steps pass end to end. **Done 2026-11-08:** `tests/test_cm_acceptance.py` (the 17 steps, checked again from the database) and `frontend/e2e/acceptance.py` (the 17 steps in a browser, plus 3 live-page checks); the seed `scripts.demo_case` tells the same story through the running application; live pages; documents 10 (traceability) and 11 (limitations and readiness); the two user guides. See `steps/15-8-demo-and-acceptance.md` |

**Rough effort:** each phase is about one to two working sessions of the kind used for Steps 13–14; CM-4 (the screens) is the largest.

## The acceptance scenario (spec §27) by phase

| Step | | Phase |
|---|---|---|
| 1–3 | Admin creates Case A → original repository → Investigator 1 receives V1 | CM-1 |
| 4 | Uploads evidence and commits | CM-2 ✅ (commits: CM-1) |
| 5 | Creates a CDR analysis branch | CM-1 |
| 6–9 | Invites Investigator 2 → findings submitted → supervisor approves → merge commit | CM-3 ✅ |
| 10–13 | Wrong earlier assumption → clone V2 from a historical commit → V2 active, V1 preserved | CM-1 |
| 14 | Admin sees the original, V1, V2, every commit, contributors and history | CM-1 (API), CM-4 (graph) ✅ |
| 15 | Evidence integrity checks succeed | CM-2 ✅ |
| 16 | A deletion or history rewrite is rejected and audited | CM-1 |
| 17 | A report with provenance and integrity information | CM-7 |
| 1–17 | All of them, end to end, as one story | CM-8 ✅ |

## Decisions taken (with reasons in [03 §6](03-high-level-design.md))

| # | Decision | Can be changed? |
|---|---|---|
| 1 | Built **inside this project**: no Knight Hawk platform code exists on this computer. Connection points are defined for later | yes, when the platform is provided |
| 2 | **Mantine** (already in use) instead of Tailwind + shadcn/ui, which the spec allows as an "equivalent accessible component library" | yes, at a cost |
| 3 | **Content-addressed write-once store** behind an interface: local volume first, S3 Object Lock for production. MinIO only after a licence check (AGPL-3.0) | yes |
| 4 | **Valkey** instead of Redis (licence), added in CM-7. *Replaced by decision 10* | yes |
| 5 | Commits are **SHA-256 of their content** (Git-like); no real Git | no: it is the integrity design |
| 6 | ROOT receives one commit and is then frozen; all work happens in clones | no: spec Rule 2 |
| 7 | Case Intelligence stays usable on its own (its current menu) **and** inside every case | yes |
| 8 | **All case types:** a configurable list, folder templates and suggested branch types per type; nothing crime-specific is required | — |
| 9 | Existing endpoints stay under `/api/...`; the module's are under `/api/v1/...` | — |
| 10 | **Background jobs**: a small worker (`scripts.worker`) whose runs are recorded in PostgreSQL, instead of Valkey + RQ: three daily jobs need no queue, and one service less must be run and secured (CM-7) | yes, if jobs grow |

## What only your organisation can provide

- The **Knight Hawk platform** code, if it exists somewhere else (for SSO, menus, Log Analyzer screens).
- The real **role and unit structure**, the **case types** in use, and **report formats** per court or jurisdiction.
- The **write-once storage** (hardware or service), and who holds the **checkpoint key**.
- Answers to [`DECISIONS.md`](../DECISIONS.md): they apply to this module too.

## How progress is shown

After each phase:
1. The full test suite runs (all existing tests must keep passing).
2. A guide is written in `docs/steps/15-N-*.md`.
3. `DEVELOPMENT_PLAN.md` is updated.
4. The readiness check grows with the module's go-live items.
