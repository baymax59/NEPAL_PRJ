# Step 15.8: Demonstration and acceptance (phase CM-8)

> **Partly superseded (2026-11-10).** The 17-step story, the browser run and the demonstration case were rewritten for the plain case: the same steps, with plain-case equivalents. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md). Traceability: [10-acceptance-and-traceability.md](../case-management/10-acceptance-and-traceability.md); how it was redone: [17-4](17-4-plain-case-browser-checks-and-guides.md).

Status: **built and verified** (2026-11-08). One step remains, and it is yours: loading the demonstration case into your development database (section 5). It was tried and stopped for your explicit go-ahead, because case records can never be deleted.

| Check | Result |
|---|---|
| Backend tests | 525 pass, 10 of them new |
| Frontend tests | 50 pass, 4 of them new |
| The 17-step acceptance scenario, automated | passes, end to end, and is checked again from the database records (`tests/test_cm_acceptance.py`) |
| The 17-step acceptance scenario, in a browser | 17 of 17 steps, plus 3 checks that pages update by themselves while other people work |
| Browser walk-through (regression) | 37 of 37 steps, with the real AI models |
| Seeding the demonstration through a running API | the 17 steps pass; tried in the throwaway database `casesdb_e2e` |
| Read-only tour of the seeded demonstration | 26 of 26 checks; its screenshots illustrate the two user guides |
| Docker version | rebuilt (migration 0015 applied); smoke test passed; CM-7 checks 11 of 11 |

This is part 8 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It proves the whole module against the master specification's final acceptance scenario (§27), seeds the fictional demonstration case of §23, and adds the user guides, the traceability of every requirement, and the production-readiness checklist (§26). It also makes every open page **live**: a page updates by itself, within seconds, when a colleague changes what it shows.

## 1. What this phase does

**The acceptance scenario, as one story.** `backend/scripts/demo/story.py` does the 17 steps of §27 through the HTTP API, as the people of the specification would. It checks every answer and stops with the step's number at the first one that doesn't hold. The same story is used twice:
- the acceptance test runs it against the test database, then checks the outcome again independently, from the database rows and the stored files;
- the seed runs it against the running application to create the demonstration.

**The demonstration case KH-2026-0001**, "Online Banking Fraud Investigation", with a reported loss of INR 2,50,000:
- **Fictional files** (`scripts/demo/files.py`): a WhatsApp export, a bank statement (PDF), a suspicious-URL record, the bank's access log, a CDR and an IPDR, plus four notes.
- **The incorrect earlier assumption** (step 10): the bank's log is in UTC, and reading 05:11 as Indian time points at the wrong subscriber. The investigator records the error on that commit and restarts as V2 from the approved merge. V1 keeps the error on record.
- **Correlation:** the files match the identifiers of the fictional integration test source, so imported findings, matching identifiers and Case Intelligence all connect.

**The seed** (`scripts/demo_case.py`) works through the running application (HTTPS):
- it creates four fictional accounts, whose passwords go only into the git-ignored `.dev-credentials.txt`;
- it tells the story; the evidence goes into the application's own store;
- it refuses in production, refuses while two-step verification is required, refuses when the organisation already has cases (so the number is 0001), and never seeds twice.

**Live pages (real time).** The notice stream now also follows the page that is open, whether a repository, case, review, exhibit or administration page. It sends a fingerprint when what that page shows changes, and the page then re-reads its data once. Reads never change the fingerprint, so a refresh can't cause another one; that matters because every read is audited.

**Three improvements found while testing the scenario:**
1. **Branch choice.** "Add evidence" and "New note" offer only the branches a person may write to, and start on the branch on screen. A contributor assigned to one branch was previously offered `main`, where the server refused her.
2. **Credit after access ends.** "My contributions" counts work in investigations a person can no longer open (a superseded clone), as numbers only.
3. **Audit filter.** The case's audit trail has a **Refused and denied** view, so refusals stand out among the reads.

**Documents:**
- [administrator's guide](../guides/administrator-guide.md) and [investigator's guide](../guides/investigator-guide.md), with screenshots of the demonstration;
- [10-acceptance-and-traceability.md](../case-management/10-acceptance-and-traceability.md): every step of §27, every test of §24, the demo data of §23 and every deliverable of §26, with where it is proven;
- [11-production-readiness.md](../case-management/11-production-readiness.md): known limitations and the go-live checklist.

The readiness check gains two items: no demonstration case in the database, and the demonstration accounts deactivated.

## 2. Why it is needed

The specification says the solution is complete only when its final scenario works end to end. A scenario spread over seven phases' tests doesn't show that. One story, run the same way by a test, by a browser and by the seed, does. The demonstration lets people see the module with realistic data without risking real records. The guides, the traceability table and the readiness checklist are what an organisation needs to accept the system and prepare it for real use.

## 3. Files created or changed

| File | What changed |
|---|---|
| `backend/scripts/demo/files.py`, `story.py` | **New.** The fictional evidence and notes; the 17-step story through the API |
| `backend/scripts/demo_case.py` | **New.** The seed: checks, fictional accounts, the story through the running application, `--show`, `--write-files` |
| `backend/tests/test_cm_acceptance.py` | **New.** The scenario end to end, checked again from the database; the demo data is fictional and stable; the seed's safety rules |
| `backend/app/casemgmt/stream.py`, `workspace_api.py` | live pages: the `watch` scope, the fingerprint, the `activity` event |
| `backend/alembic/versions/0015_case_management_live_pages.py`, `app/casemgmt/models.py` | **New migration.** One index (integrity checks by exhibit) for the fingerprint |
| `backend/app/casemgmt/queries.py`, `schemas.py` | `writable_branches` on a repository; `no_longer_open` on contributions |
| `backend/app/casemgmt/overview.py` | contributions also counted where they can no longer be opened (numbers only) |
| `backend/app/casemgmt/api.py` | the case's audit trail: `show=refused` |
| `backend/app/readiness.py`, `scripts/readiness_check.py` | two go-live items: no demonstration case; demonstration accounts deactivated |
| `backend/tests/test_cm_workspace.py`, `test_cm_members.py`, `test_readiness.py` | live pages (3 tests), writable branches (1), readiness (1), contributions |
| `frontend/src/kh/live.ts`, `components/AppLayout.tsx` | the open page is followed and re-read when it changes |
| `frontend/src/kh/repo/dialogs.tsx`, `helpers.ts`, `RepositoryLayout.tsx` | the branch choice in "Add evidence" and "New note" |
| `frontend/src/kh/pages/InboxPages.tsx`, `repo/AuditTab.tsx` | credited work after access ended; the "Refused and denied" view |
| `frontend/src/kh/kh.test.tsx` | 4 tests: the page followed, the data refreshed, the branch choice |
| `frontend/e2e/acceptance.py`, `demo_tour.py` | **New.** The 17 steps in a browser, with live-page checks; the read-only tour of the demonstration |
| `docs/guides/` | **New.** The two user guides and their 26 screenshots |
| `docs/case-management/10-…`, `11-…` | **New.** Traceability; known limitations and readiness |
| `docs/case-management/openapi.json`, `frontend/src/api/schema.d.ts` | regenerated |

## 4. Packages

None new. The PDF of the demonstration uses ReportLab (CM-7). The browser runs use Playwright through `uv run --with playwright`, as the walk-through does.

## 5. Commands

```powershell
cd C:\case-search\backend

# The acceptance scenario, then every test
uv run pytest tests/test_cm_acceptance.py -q
uv run pytest -q
cd ..\frontend; npm test; cd ..\backend

# Load the demonstration into the development database, through the Docker version.
# Once only: case records can't be deleted. Never into a database meant for real records.
uv run python -m scripts.demo_case
uv run python -m scripts.demo_case --show                         # is it there? which accounts exist?
uv run python -m scripts.demo_case --write-files $env:TEMP\kh-demo # the six fictional files, to open and read

# The 17 steps in a browser, on the throwaway database (API on 8010, web app on 5180 as in docs/steps/15-4)
uv run python -m scripts.e2e_prepare
$env:POSTGRES_DB = 'casesdb_e2e'; $env:POSTGRES_APP_USER = 'caseapp'; uv run python -m scripts.db_roles
uv run --with playwright python ..\frontend\e2e\acceptance.py --url http://127.0.0.1:5180 --shots $env:TEMP\kh-acceptance

# A read-only tour of the seeded demonstration (it reads the demo passwords from .dev-credentials.txt)
uv run --with playwright python ..\frontend\e2e\demo_tour.py --url https://localhost:8443 --shots $env:TEMP\kh-tour

# Go-live readiness
uv run python -m scripts.readiness_check
```

## 6. How it works

**The story** checks what each step must show, not only that a request was accepted. For example:
- step 2: a commit to ROOT is refused;
- step 13: V1's commit list is the same before and after V2 is created;
- step 16: six deletion and rewrite attempts answer 405 and appear in the audit log against their targets, and a write based on an old head answers 409;
- step 17: the downloaded PDF's SHA-256 equals the recorded one, and checking the file answers `match`.

The test then rebuilds the lineage from the tables, reads the merge's two parents from `commit_parents`, re-hashes every stored file, verifies the audit hash chain, and reads the report's text with the application's own PDF reader.

**The demonstration's files** are generated from text in the code. The PDF is made in ReportLab's "invariant" mode, so every file has the same SHA-256 every time. Only reserved values are used:
- documentation IP addresses (RFC 5737);
- `.example` domains (RFC 2606);
- the test mobile network 001-01 and test IMEIs;
- invented names, bank, accounts, FIR and requisition numbers.

A test checks the files for real-looking addresses, domains and phone numbers.

**The seed** creates the accounts with the same function as `scripts.create_user`. It writes their passwords to the credentials file before saving the accounts, so a password is never lost, and it never prints them. It then logs in through `/api/auth/token` and runs the story. Nothing goes into the case tables except through the API.

**Live pages:**
1. The browser works out the open page from its address and tells the stream (`?watch=repository:<id>` and so on).
2. Every 5 seconds the server computes one row of values for that page: branch heads, statuses, members and invitations, task events, comments, review statuses and decisions, custody, deliberate integrity checks, seals, report checks, legal holds, retention decisions.
3. It sends a 16-character fingerprint when the values change. The browser then re-reads that page's data (only the queries on screen).

Further details:
- **Access:** the scope follows the same rules as the pages, checked at every poll. A page the user may not open never produces an `activity` event, exactly like one that doesn't exist.
- **No loops:** previews, downloads and background reading of documents are left out of the values, because they are reads, so a refresh never causes another.
- **Admin pages** cover the whole organisation and refresh at most every 15 seconds.
- **Reconnecting:** the fingerprint survives the stream's reconnection every 10 minutes, so a change made in between isn't missed.

**Writable branches** use the server's own rule (`access.works_on`): the lead may write to every active branch, a contributor to the branches assigned to them or made by them, and nobody to a superseded clone.

**Credited work** compares two counts of the person's commits, exhibits, reviews and merged findings: the ones they can still open, and all of them. Only the difference is shown, as numbers.

## 7. Endpoints in this phase

No new endpoints (128 paths). Four answers gained something:

| Method and path | What changed |
|---|---|
| `GET /api/v1/notifications/stream?watch=…` | `watch` = `repository:<id>`, `case:<id>`, `review:<id>`, `evidence:<id>` or `admin`; adds the event `activity` (a fingerprint, never case content); the watched page is recorded in the stream's audit event |
| `GET /api/v1/repositories/{id}` | `writable_branches`: the branches you may commit to |
| `GET /api/v1/contributions/mine` | `no_longer_open`: your work in investigations you can no longer open (numbers only) |
| `GET /api/v1/admin/cases/{id}/audit?show=refused` | only what was refused or denied |

## 8. How to test

1. `uv run pytest tests/test_cm_acceptance.py -q`: 5 tests, including the scenario.
2. The browser run (section 5) prints the 17 steps and the 3 live checks.
3. After seeding, open https://localhost:8443:
   1. Log in as `demo.arun` (the password is in `.dev-credentials.txt`): his active workspace is KH-2026-0001-V2.
   2. In another browser window, log in as `demo.admin` and open **All cases & lineage** → KH-2026-0001: ROOT, V1 superseded, V2 active.
   3. Add a note in V2 as `demo.arun`: the administrator's graph shows the new commit within about 15 seconds, without reloading.
4. `uv run python -m scripts.readiness_check`: with the demonstration loaded, the two new items are OPEN, as they should be for a development database.

## 9. Expected output

```text
uv run pytest tests/test_cm_acceptance.py -q                     5 passed
uv run pytest -q                                                 525 passed
npm test                                                         Tests  50 passed (50)

uv run python -m scripts.demo_case
Seeding the FICTIONAL demonstration case through https://localhost:8443 (the 17 steps of spec section 27):
  [ok]  1. An administrator creates Case A.  KH-2026-0001 'Online Banking Fraud Investigation', by the administrator
  [ok]  2. The system permanently registers Case A's original repository.  KH-2026-0001-ROOT (status frozen), ... further commits refused (403)
  ...
  [ok] 13. V1 remains preserved and unchanged.  KH-2026-0001-V1 is superseded: its 14 commits are unchanged, ...
  [ok] 16. An attempted deletion or destructive history rewrite is rejected and audited.  6 deletion/rewrite attempts refused with 405 and audited; a stale write refused with 409
  [ok] 17. The system generates a case report with provenance and integrity information.  RPT-0001 version 1 (3 pages) ...
Demonstration case ready: KH-2026-0001 "Online Banking Fraud Investigation" (FICTIONAL).

Browser run:
  [ok]    live: Inspector Arun's open branch list showed SI Meena's new commit without reloading
  [ok]    live: SI Meena's open review showed the supervisor's approval without reloading
  [ok]    live: the administrator's open lineage graph showed V2 without reloading
ALL 17 ACCEPTANCE STEPS PASSED (and 3 live-page checks)
```

## 10. Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `Not seeding: The organisation already has N case(s)` | the demonstration must be the first case, to get number 0001 | use a fresh development database, or `--any-number` to accept another number |
| `Not seeding: ENVIRONMENT is production` | fictional data never goes into production | seed a development or training database |
| `The account demo.arun exists but its password isn't in .dev-credentials.txt` | the account was made elsewhere | `scripts.create_user demo.arun --reset-password`, then add its line to the file |
| `demo.arun couldn't log in through …` | the API uses another database than the script | the same `POSTGRES_DB` for both (the Docker version and `.env` share the development database) |
| `Stopped: Step N (...) failed: ...` | the running application answered unexpectedly | the message names the request and the answer. The steps before it are kept, permanently |
| The lead gets "Not found" on V1 after cloning | a superseded clone's memberships end; its history is reached through V2, up to V2's source commit | by design: administrators and the supervisor still see V1 in full |
| A contributor's dashboard is empty after V2 | contributors are not copied into a new clone | invite them again; their work stays credited to them |
| The "Add evidence" form offered `main` to a contributor | before this phase the header button ignored the branch on screen | fixed: only writable branches are offered |
| `'charmap' codec can't encode` in a browser run | the Windows console | the scripts print plain text and replace what the console can't show |
| A browser check can't find a refusal in the audit trail | every read is recorded too, so refusals move to older pages | the **Refused and denied** view |
| The pages don't follow changes in development | the API was not restarted after a backend change | restart uvicorn (Docker rebuilds do it) |
