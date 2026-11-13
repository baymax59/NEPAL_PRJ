# Step 15.7: Reports and governance (phase CM-7)

> **Partly superseded (2026-11-10).** Signed reports, the audit chain, two-step verification, legal holds and retention still work as described. A report now describes the case 'as of entry N' of its history (not 'at a commit'), and is a new version of one report file. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md).

Status: **done and verified** (2026-11-08).

| Check | Result |
|---|---|
| Backend tests | 515 pass, 12 of them new |
| Frontend tests | 46 pass, 4 of them new |
| Browser walk-through | 37 of 37 steps pass (4 new, and step 19 now generates, downloads and checks a signed report), with the API on the application's own database login and the real AI models |
| Docker version | rebuilt (migration 0014 applied; the API connects as its own login, which can't delete; the worker ran its 3 jobs); smoke test 8 of 8, CM-7 checks 11 of 11 |

All test data is fictional, and **nothing was created in the development database**: the tests use `casesdb_test` and the walk-through the throwaway `casesdb_e2e`.

This is part 7 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It completes acceptance step 17, "a report with provenance and integrity information", and adds the governance the design promised: a tamper-evident audit trail, legal holds, retention as a formal decision, two-step verification, a database login that can't delete case records, and a worker for the daily checks.

## 1. What this phase does

| Part | What you get |
|---|---|
| **Signed PDF reports** | **Reports → Generate a signed PDF**: a case report (evidence with hashes, notes, imported findings, timeline, approved reviews, contributors) or an evidence register (exhibits with their full chain of custody), of one commit. The PDF is kept write-once with its **SHA-256**, committed as a report version (`RPT-0001` v1, v2…), and downloaded through one-time links. **Check** re-hashes the stored copy; **Check a report file** tells anyone whether a copy they hold is, byte for byte, a report Knight Hawk generated |
| **Tamper-evident audit trail** | Every Case Management event carries the hash of the one before it. An edited, removed or re-ordered event is detected. **Checkpoints** sign the chain with a key kept outside the database, and are also written to the write-once store, so even someone who recomputes every hash is detected |
| **Legal holds** | On each case's page: place a hold (with the order it follows) or release it, with a reason. While a hold is active, the case can't be archived and no decision to archive, transfer or dispose of it can be approved |
| **Retention as a decision** | Policies say when closed cases are due for review. A decision (retain, archive, transfer, dispose) is **proposed by one person and decided by another**. Archiving makes the case read-only; an approved disposal is **recorded only**: Knight Hawk never deletes a record |
| **Two-step verification** | **Account → Two-step verification**: scan a QR code into an authenticator app; the login then asks for a code. With `CM_MFA_REQUIRED=true`, administrators and supervisors must have logged in with a code for privileged actions: approvals, merges, sealing, access changes, legal holds, retention decisions, integration sources, checkpoints |
| **A database login without DELETE** | The application connects as its own login (role `cm_runtime`): it **can't delete** any case record, and **can't edit** permanent ones. A test runs the whole module under it |
| **The worker** | A small service (`scripts.worker`, Docker service `worker`) runs three daily jobs: sign the audit chain, verify it, and re-hash every stored evidence file. A problem notifies every platform administrator |
| **Administration → Governance** | The audit chain (verify now, sign now, checkpoints), the scheduled checks (run now), legal holds in force, retention (policies, cases due for review, decisions waiting for a second person), and the five settings go-live depends on |

### What a report contains, and what it doesn't

Anyone who can open a case can open its reports. So a report holds only what **every member of the case may see** at that commit: sealed exhibits and notes, and exhibits classified above the case, are left out and **counted** ("2 entries are not included"). The PDF says which commit it describes, that the commit's hashes were recomputed and match, who generated it and why, and that it is **not automatically admissible in court**. Every page carries the report's ID and version, the commit and "page n of m".

### What the audit chain can and can't prove

The application can't change history; the database refuses edits and deletions of chained events. Someone with full control of the database could switch that rule off, edit an event and recompute every hash, and the chain would look whole. But it no longer matches the checkpoints, which are signed with a key **they don't hold** and also kept in the write-once store. That is why the checkpoint key must be held by someone other than the database administrators (decision D16). It is detection, not prevention (docs/case-management/07 §2).

## 2. Why it is needed

The specification's acceptance step 17 asks for a report with provenance and integrity information that can be relied on later. A report is only useful if its recipient can check it hasn't been altered, which is what the recorded SHA-256 and "Check a report file" give. The rest makes the "nothing is deleted, nothing is rewritten" promise verifiable rather than a claim: anyone tampering with the audit trail is detected, the application itself can't delete case records, retention and disposal are formal decisions by two people, and privileged actions need a second factor.

## 3. Files created or changed

| File | What |
|---|---|
| `backend/app/casemgmt/governance/audit_chain.py` | **New.** Verifying the chain, signing checkpoints, checking them (key, event, stored file) |
| `backend/app/casemgmt/governance/pdf.py` | **New.** The PDF layout (ReportLab), page header and footer with "page n of m" |
| `backend/app/casemgmt/governance/reports.py` | **New.** Generating, committing, listing, checking (stored and submitted copies) and downloading reports |
| `backend/app/casemgmt/governance/holds.py` | **New.** Legal holds |
| `backend/app/casemgmt/governance/retention.py` | **New.** Policies, cases due for review, two-person decisions, archiving on approval |
| `backend/app/casemgmt/governance/jobs.py` | **New.** The three scheduled jobs, their runs and notices |
| `backend/app/casemgmt/governance/api.py` | **New.** 20 endpoints (section 7); 122 in the module |
| `backend/app/auth/mfa.py`, `app/api/auth.py`, `app/auth/tokens.py`, `app/auth/dependencies.py` | **New / changed.** Two-step verification: set-up, confirmation, the login's second step, "this login used a code", the check on privileged actions |
| `backend/alembic/versions/0014_case_management_governance.py` | **New.** 9 tables, the audit chain (columns, hash function, 2 rules, the chain of the events recorded so far), the role `cm_runtime` and its grants |
| `backend/scripts/worker.py`, `scripts/db_roles.py` | **New.** The worker; the application's database login |
| `backend/app/casemgmt/engine.py`, `reviews.py`, `members.py`, `artifacts.py`, `evidence.py`, `integrations/sources.py` | privileged actions check two-step verification; archiving checks legal holds; generated reports can't be revised |
| `backend/app/casemgmt/report.py` | the shared view (what every member may see), for signed reports |
| `backend/app/core/config.py`, `app/db/session.py` | the new settings; the application connects with its own login when one is set |
| `backend/app/readiness.py`, `scripts/readiness_check.py` | six new go-live checks (decision D16) |
| `backend/tests/test_cm_reports_audit.py`, `tests/test_cm_governance.py` | **New.** 11 tests (section 8); `test_cm_clones_access.py` and `test_readiness.py` updated |
| `backend/Dockerfile`, `docker-compose.yml`, `.env.example` | a font for the PDFs; the database login at start; the `worker` service; the new settings |
| `frontend/src/kh/repo/SignedReports.tsx` | **New.** Signed reports in the Reports tab |
| `frontend/src/kh/pages/VerifyReportPage.tsx`, `AccountPage.tsx`, `AdminGovernancePage.tsx`, `CaseGovernancePanel.tsx` | **New.** Check a report file; two-step verification; Administration → Governance; legal holds and retention on each case's page |
| `frontend/src/pages/LoginPage.tsx`, `src/auth/*`, `src/api/*` | the login's second step |
| `frontend/src/kh/pages/governance.test.tsx` | **New.** 4 tests |
| `frontend/e2e/walkthrough.py` | 4 new steps, and step 19 now generates, downloads and checks a signed report |
| `docs/DECISIONS.md` | decisions D15 (retention, legal holds, disposal) and D16 (two-step verification, keys, the database login) |

## 4. Packages

| Package | Licence | Why |
|---|---|---|
| ReportLab 5.1 | BSD | the PDF reports |
| pyotp 2.10 | MIT | two-step verification codes (TOTP, RFC 6238) |
| cryptography 50 | Apache-2.0 / BSD | encrypting the two-step verification secrets |
| segno 1.6 | BSD | the QR code for the authenticator app |
| fonts-dejavu-core (Docker image) | free font licence | characters beyond Western European in the PDFs |

**Valkey and RQ were not added**, although document 08 planned them for this phase: three daily jobs don't need a queue, and one service less has to be run and secured. The worker records its runs in PostgreSQL. See decision 10 in document 08.

## 5. Commands

```powershell
# Database up to date, then the application's own login and its grants (Docker does both at every start)
cd C:\case-search\backend; uv run alembic upgrade head; uv run python -m scripts.db_roles

# The worker: once, or keep it running (Docker runs it as the service "worker")
uv run python -m scripts.worker --once
uv run python -m scripts.worker --run audit_verify

# The tests of this phase, then all of them
uv run pytest tests/test_cm_reports_audit.py tests/test_cm_governance.py -q
uv run pytest -q
cd C:\case-search\frontend; npm test; npx tsc -b; npm run lint
```

Settings (`.env`; on this computer the three keys were generated and written there, never shown):

| Setting | Default | Meaning |
|---|---|---|
| `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD` | `caseapp`, not set | the application's own database login. Without a password, the owner login is used |
| `CM_CHECKPOINT_KEY` | not set (derived from `AUDIT_SECRET`) | signs the audit checkpoints. **Hold it apart from the database administrators** (D16) |
| `MFA_KEY` | not set (derived from `JWT_SECRET`) | encrypts the two-step verification secrets |
| `CM_MFA_REQUIRED` | `false` | require two-step verification for privileged actions by administrators and supervisors. Turn on once they have set it up |
| `CM_WORKER_INTERVAL` | `300` | how often (seconds) the worker looks for due jobs |

## 6. How it works

**A report** (`reports.generate`): the same branch checks as every commit (`writable_branch`), then the report data from the **shared view**, the PDF, the write-once store (under its SHA-256), a new version of `reports/case-report` or `reports/evidence-register` whose content holds the hash, a `report_generated` commit, and the `report_exports` row. Because the hash is in the artifact's content, and the content's hash is in the snapshot, and the snapshot's hash is in the commit ID, the commit chain itself vouches for the file. A **download** first re-hashes the stored copy; a changed copy is refused (409) and the failed check is kept. Every check is recorded (`report_verifications`), every download too (`report_downloads`).

**The audit chain** (migration 0014): a database trigger gives every `cm.*` event, as it is written, the next sequence number, the previous event's hash and its own hash:

```
hash = sha256(previous hash | sequence | id | time | user | action | outcome | target | address | details)
```

One transaction at a time extends the chain (an advisory lock). Chained events can't be updated or deleted (a second rule). Events of the similar-case search (`search`, `auth.login`…) stay outside the chain, under their own retention rule (Step 14.3). **Verifying** recomputes every hash in order, then checks each checkpoint: its HMAC signature with the current key, that the chain still has the signed hash at that point, and that its file in the write-once store is intact.

**The database login** (`scripts.db_roles`): the role `cm_runtime` gets SELECT and INSERT everywhere, UPDATE except on permanent tables, and DELETE only on the tables of the similar-case search that the application really deletes from (reprocessing a document, removing an upload, audit retention outside the chain, resetting two-step verification). The grants are derived from the database rules each time, so a new table is covered automatically. The login is a member of the role and nothing else.

**Two-step verification** (`app/auth/mfa.py`): TOTP codes of 30 seconds, one step of clock drift accepted, each code usable once; the secret is encrypted with `MFA_KEY`. The password step returns a 5-minute ticket instead of a token; the ticket and a code return a token that records the second step (`"amr": ["pwd", "otp"]`).

## 7. Endpoints in this phase

| Method and path | What | Who |
|---|---|---|
| `POST /api/v1/repositories/{id}/reports` | generate a signed report of a commit | people who may write to the branch |
| `GET /api/v1/repositories/{id}/reports?ref=` | report versions at a branch or commit | people who can open the case |
| `GET /api/v1/reports/{id}` | one report version, with its checks and downloads | people who can open the case |
| `POST /api/v1/reports/{id}/download-link`, `GET /api/v1/report-downloads/{token}` | a one-time download | people who can open the case |
| `POST /api/v1/reports/{id}/verify` | re-hash the stored copy | people who can open the case |
| `POST /api/v1/reports/verify-file` | check a copy someone holds (the file is only hashed) | any signed-in user; details only with access |
| `GET /api/v1/cases/{id}/governance` | the case's holds and retention | people who can open the case |
| `POST /api/v1/cases/{id}/legal-holds`, `POST /api/v1/legal-holds/{id}/release` | place or release a hold | the case's supervisor, administrators |
| `POST /api/v1/cases/{id}/retention-decisions`, `POST /api/v1/retention-decisions/{id}/decide`, `…/withdraw` | propose, decide (another person), withdraw | supervisor, administrators |
| `GET /api/v1/admin/retention`, `POST /api/v1/admin/retention/policies`, `…/{id}/retire` | retention overview and policies | platform administrators |
| `GET /api/v1/admin/governance` | chain, checkpoints, jobs, holds, settings | platform administrators |
| `POST /api/v1/admin/audit/verify`, `POST /api/v1/admin/audit/checkpoints`, `POST /api/v1/admin/jobs/{job}/run` | verify, sign, run a job now | platform administrators |
| `GET /api/auth/mfa`, `POST /api/auth/mfa/setup`, `…/confirm`, `…/disable`, `POST /api/auth/mfa/login` | two-step verification | every user |

## 8. How to test

**Backend** (11 new tests, all fictional):

| Test | Proves |
|---|---|
| a report is a signed PDF kept with its hash, **and a changed report fails verification** | the downloaded file's SHA-256 is the recorded one; its text holds the case, the report's ID, the exhibit's hash and the disclaimer; a link works once; a submitted copy is recognised, one changed byte and it isn't; a stored copy changed behind the application's back fails its check and its download is refused, and every check is kept |
| reports have versions, follow the shared view and are never edited | a sealed exhibit is left out and counted, even in the supervisor's report; version 2 after version 1; versions at an earlier commit; no revision; no DELETE; outsiders get 404, and only "genuine" when checking a copy |
| Case Management events form a chain, **and an edited audit row breaks it** | links between events; search and login events outside the chain; the database refuses edits; an edit made by switching the rule off is detected; recomputing every hash is detected by the checkpoint; a deleted event leaves a gap; the other administrators are notified |
| a checkpoint needs the right key and its stored file | another key and a forged file are both detected; only administrators verify |
| the worker runs due jobs once a day, records them, warns about changed evidence | three runs, audited; nothing due right after; a changed exhibit gives a warning and a notice |
| a legal hold blocks archiving and disposal decisions until released | the lead can't place a hold; archiving refused; "retain" still possible; release with a reason |
| retention is decided by a second person and never deletes anything | the proposer can't decide (also a database rule); archiving on approval makes the repositories read-only; an approved disposal is recorded, and the history is still there |
| retention policies show the cases due for review | a case closed two years ago is due; a waiting decision or a "retain" takes it off the list |
| two-step verification and privileged actions | QR code; confirmation; the login's second step; a code works once; "this login used a code"; with the setting on, a hold needs a login with a code; ordinary work isn't affected |
| the runtime role can't delete case records nor edit permanent ones | its privileges on every permanent, status-only and deletable table |
| **the whole module works under the runtime role** | a case, evidence, commits, an invitation, a branch, a review, a merge and a report, under the application's own login; DELETE and editing permanent records refused |

**Frontend** (4 new tests): signed reports listed with their check, and generating one from the branch head; a genuine and a changed file at "Check a report file"; the login's second step.

**Browser walk-through**: step 19 now generates a signed PDF, downloads it and checks the downloaded copy (acceptance step 17), and new steps verify and sign the audit chain, place a legal hold, and turn on two-step verification and log in with a code. The walk-through's API ran under the application's own database login.

## 9. Expected output

```
uv run pytest tests/test_cm_reports_audit.py tests/test_cm_governance.py -q    11 passed
uv run pytest -q                                                                515 passed
npm test                                                                        Tests  46 passed (46)

Browser walk-through (API on the application's own database login):
  [ok] 19 report generation: a signed PDF (RPT-0001 version 1) with provenance and integrity, kept with its SHA-256
  [ok] 17 acceptance: the downloaded report checked byte for byte against its recorded SHA-256 (genuine)
  [ok] CM-7 governance: the audit chain recomputed and intact, then signed (a checkpoint, kept outside the database too)
  [ok] CM-7 legal hold placed on KH-2026-0002 by the supervisor: it can't be archived, nor a disposal approved, until released
  [ok] CM-7 two-step verification: the administrator turned it on and logged in again with a code
ALL 37 STEPS PASSED

Docker: backend log "Running upgrade 0013 -> 0014" and "Database login 'caseapp' is ready"; the worker ran
audit_checkpoint, audit_verify and evidence_sweep (ok); the API connects as caseapp and "DELETE FROM case_families"
is refused (permission denied); smoke test 8/8; CM-7 checks 11/11; the development database: 0 cases
```

## 10. Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `403 Two-step verification is required for …` | `CM_MFA_REQUIRED=true`, and this login didn't use a code | Account → Two-step verification, then log out and in again with a code |
| "That code isn't valid" when turning it on | the phone's clock is off, or the code changed while typing | check the phone's time is set automatically; enter the code shown now |
| `409 The stored copy of this report no longer matches …` | the report's file was changed or replaced in the store | an administrator checks the evidence store; the failed check is on record |
| A checkpoint shows "signed with another key" | `CM_CHECKPOINT_KEY` changed since it was signed | keep the old key to check old checkpoints; new ones use the new key |
| The audit chain is "broken" | an event was changed, removed or re-ordered in the database | treat it as a security incident: the report names the first event affected |
| `permission denied for table …` in the server log | the application's own login tried something it may never do | a bug to report; nothing was changed |
| The worker shows "never run" | the worker isn't running | Docker: `docker compose --profile app up -d worker`; otherwise `uv run python -m scripts.worker` |
| "No hold placed" / no "Place a hold" button | only the case's supervisor or an administrator places holds | ask them |
