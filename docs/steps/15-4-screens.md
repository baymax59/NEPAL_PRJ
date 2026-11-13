# Step 15.4: Knight Hawk screens (phase CM-4)

> **Partly superseded (2026-11-10).** The screens described here (repository page, branches, commits, graph, review and clone dialogs) were replaced by the case page and its nine tabs. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md). The screens now: [17-3](17-3-plain-case-screens.md). How to start the throwaway database, the API and the web app for the browser runs is unchanged.

Status: **done and verified** (2026-11-07).

| Check | Result |
|---|---|
| Backend tests | 480 pass, 8 of them new |
| Frontend tests | 28 pass, 16 of them new |
| Browser walk-through | 25 of 25 steps pass, covering every screen of specification §21 |
| Docker version | smoke test 8 of 8, CM-4 checks 9 of 9 |

All test data is fictional, and **nothing was created in the development database**: the walk-through uses a separate, throwaway database.

This is part 4 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It puts screens on [15.1](15-1-repository-core.md), [15.2](15-2-evidence.md) and [15.3](15-3-collaboration-and-review.md).

## 1. What this phase does

Knight Hawk now has screens. The application opens on the **Knight Hawk dashboard** after login; the similar-case search (Case Intelligence) stays in the menu, unchanged.

**The look.** A dark navy base with restrained cyan accents, commit IDs in a monospaced font, compact status labels and dense tables (specification §21). A light mode is one click away (sun icon, top right). Colours were checked for readability: body text is about 14:1 on the navy page, dimmed text about 6:1, button text 4.6:1 (WCAG AA needs 4.5:1), and the chart colour passes the lightness and contrast checks in both modes.

**The 20 screens of specification §21:**

| # | Screen | Where | What you see |
|---|---|---|---|
| 1 | Login | `/login` | the three rules (nothing deleted, history never rewritten, evidence never overwritten) and the login form |
| 2 | Admin dashboard | `/kh/admin` | counts (cases, originals, active and superseded clones, commits, exhibits, reviews, tasks), commits per day, cases by status and type (each chart has a table view), evidence integrity, recent activity |
| 3 | Investigator dashboard | `/kh` | active cases, open tasks, reviews to decide, invitations to answer, recent notices and contributions |
| 4 | All cases registry | `/kh/admin/cases` | the columns of specification §14: case ID, title, official reference, type, original, number of clones, active clone, lead, last activity, status, evidence count, priority |
| 5 | New case registration | `/kh/cases/new` | one form creates the case, its original repository and the lead's clone V1; then a summary of what was created |
| 6 | Repository overview | `/kh/repo/{id}` | the header of specification §15 (repository ID, title, case family, official reference, status, lead, branch selector, History, Clone investigation, Add evidence, Add contributor), latest commit, folders, description, lineage, work in progress |
| 7 | Files and evidence explorer | `…/files` | folders at any branch or commit; each entry opens with its content, its versions and the differences between them, revise, withdraw, seal and comments |
| 8 | Evidence detail and integrity | `/kh/evidence/{id}` | SHA-256, **Verify integrity now**, provenance, chain of custody (hand over, acknowledge, decline), derived analyses, text preview, one-time download link, sealing |
| 9 | Branch management | `…/branches` | each branch's status, latest commit and how far ahead of or behind `main` it is; new branch, review, bring up to date, change status |
| 10 | Commit timeline | `…/commits` | commits by day per branch; merges marked; inherited commits marked; browse or clone from any commit |
| 11 | Commit comparison | `…/compare` | two branches or commits: what was added, revised or withdrawn, with line-by-line differences |
| 12 | Historical snapshot viewer | `…/history` | the history of `main` back to the original; pick any commit to see the case exactly as it was then (read-only) |
| 13 | Clone investigation dialog | button in the header or on any commit | always shows the source commit and asks for the reason (at least 10 characters), then asks for confirmation |
| 14 | Clone lineage graph | `/kh/admin/cases/{id}` (all of it) and `…/graph` (what an investigator may see) | one lane per repository or branch; each clone drawn from its real source commit; merges with two parents |
| 15 | Contributor management | `…/contributors` | members, invitations (approve, refuse, cancel), end someone's access (with a reason), the permanent access history |
| 16 | Investigation task board | `…/tasks` and `/kh/tasks` | open, in progress, done and cancelled columns; each task's history and comments |
| 17 | Review requests | `…/reviews`, `/kh/reviews`, `/kh/review/{id}` | findings, changes with differences, commits, decisions, merge (two-parent commit), resolving conflicts (keep mine, take main's, or write a combined version) |
| 18 | Case links and relationship graph | `…/links` | links to and from other cases, each with its kind and reason, as a list and a graph |
| 19 | Report generation | `…/reports` | a printable report of one exact commit: case, lineage, evidence with hashes, custody and integrity, notes, approvals, contributors; "not automatically admissible in court" |
| 20 | Audit history | `…/audit` and the admin case page | every request about the case, including refusals; the full audit log stays at `/audit` |

**The difference between originals, clones and history is always visible** (specification §21):
- a violet **Original** label, and a cyan **Clone** label;
- status labels: **Active**, **Superseded**, **Frozen**;
- an "inherited" label on commits made in an earlier repository;
- a violet banner whenever you look at a historical commit.

**Every sensitive action asks for confirmation**, and the dialog says what happens instead of deleting. A reason is required for:
- ending someone's access;
- withdrawing an entry;
- sealing or unsealing;
- changing a status;
- declining a handover;
- withdrawing a review.

**What the backend added for the screens:**

| Addition | Why |
|---|---|
| **Choosing colleagues by name** | inviting someone, or choosing a lead or supervisor, by typing a name. Only people who could actually be chosen are listed, and clearances are never shown |
| **Live notices** | the bell updates by itself (Server-Sent Events). The stream carries counts only, never case content |
| **Dashboard figures** | the admin overview and "My contributions" |
| **Case links** | a link is case content, like a note: a commit with a reason, reviewed and merged like other work |
| **Report preview** | everything a report on one commit contains, assembled with the same access rules as everything else |
| **Organisation role on `/api/auth/me`** | so the menu offers the administrator's portal only to administrators |

## 2. Why it is needed

- **Specification §21** (the 20 screens and their look), §14 (the administrator's portal and lineage graph), §15 (the investigator's workspace and its navigation) and §16 (separate official and internal statuses).
- **Acceptance step 14**: the administrator sees the original, V1, V2, every commit, the contributors and the history. Now also as a graph.
- Until now, everything was reachable only through the API.

## 3. Files created or changed

**Backend**

| File | What it is |
|---|---|
| `app/casemgmt/colleagues.py` | choosing colleagues (lead, supervisor, invitee) |
| `app/casemgmt/overview.py` | the admin overview and "My contributions" |
| `app/casemgmt/stream.py` | the live notice stream |
| `app/casemgmt/links.py` | case links |
| `app/casemgmt/report.py` | the report preview |
| `app/casemgmt/workspace_api.py` | the 7 new endpoints |
| `app/casemgmt/schemas.py` | their shapes |
| `alembic/versions/0011_case_management_links.py` | the `case_links` table (permanent) |
| `app/casemgmt/models.py` | the `CaseLink` model |
| `app/casemgmt/enums.py` | the `LinkType` values |
| `app/casemgmt/engine.py` | a link can't be edited (withdraw it and link again) |
| `app/db/session.py` | `get_session_factory` (short database sessions for the stream) |
| `app/schemas/auth.py` | `org_role` on the current user |
| `app/main.py` | the new router |
| `scripts/export_openapi.py` | writes the API description |
| `scripts/e2e_prepare.py` | prepares the walk-through's throwaway database |
| `tests/test_cm_workspace.py` | 8 tests |
| `tests/conftest.py` | the stream uses the test's session |

**Frontend**

Everything for Knight Hawk is in `src/kh/`:

| File | What it is |
|---|---|
| `api.ts`, `types.ts` | the typed API (the types are generated, see section 5) |
| `labels.ts` | words and colours for every status |
| `ui.tsx` | shared pieces: labels, commit IDs, hashes, people, confirmation dialog, panels |
| `time.ts` | dates and times |
| `feedback.ts` | messages after an action, and the Idempotency-Key of a form |
| `content.tsx`, `diff.ts` | showing notes and their differences |
| `live.ts` | the live notices |
| `pickers.tsx` | choosing a colleague, branch or commit |
| `Comments.tsx` | comment threads |
| `Brand.tsx` | the Knight Hawk mark |
| `graph/CommitGraph.tsx`, `graph/colors.ts` | the graphs (React Flow) |
| `repo/` | the repository workspace: layout, the 12 tabs, dialogs, bringing a branch up to date |
| `pages/` | dashboards, cases, registration, case, review, evidence, the personal lists, the administrator's portal |
| `kh.test.tsx` | 16 tests |

Also changed or added in the frontend:
- `src/App.tsx`: the routes;
- `src/components/AppLayout.tsx`: the new menu, the bell and the user menu;
- `src/pages/LoginPage.tsx`: the new login screen;
- `src/theme.ts`: the theme;
- `src/styles.css`: the chart colour and print layout;
- `src/auth/guards.tsx`: `RequireOrgRole`;
- `src/api/client.ts`: headers, and error bodies kept on errors;
- `src/api/types.ts`: the organisation role;
- `src/api/schema.d.ts`: generated;
- `vite.config.ts`: `API_PROXY`;
- `e2e/walkthrough.py`: the browser walk-through.

**Docs:** this guide, plus `docs/case-management/openapi.json` (the OpenAPI specification, a deliverable of specification §26). Documents 05, 06 and 08, the README and `DEVELOPMENT_PLAN.md` are updated.

## 4. Packages

| Package | Version | Licence | Used for |
|---|---|---|---|
| `@xyflow/react` (React Flow) | 12.12.0 | MIT | the lineage, investigation and relationship graphs (named in specification §3) |
| `@mantine/charts` | 9.7.4 | MIT | the dashboard charts, built on Recharts (named in specification §3) |
| `recharts` | 3.10.1 | MIT | used by `@mantine/charts` |
| `openapi-typescript` | 7.13.0 | MIT | generates `src/api/schema.d.ts`. It is not installed in the project: `npm run gen:api` downloads it with the TypeScript 5 it needs (the project uses TypeScript 7) |
| Playwright for Python | (latest, via `uv run --with playwright`) | Apache-2.0 | the browser walk-through only |

Versions are pinned exactly. `npm audit` reports 0 vulnerabilities. React Flow 12.12.1 was 5 days old, so the September release 12.12.0 is used.

## 5. Commands

**Development** (two windows):

```powershell
cd C:\case-search\backend;  uv run uvicorn app.main:app --port 8000
cd C:\case-search\frontend; npm run dev          # http://127.0.0.1:5173
```

**The Docker version:**

```powershell
cd C:\case-search; docker compose --profile app up -d --build; docker compose restart web   # https://localhost:8443
```

**After changing the backend's API**, regenerate the frontend types:

```powershell
cd C:\case-search\backend;  uv run python -m scripts.export_openapi ../docs/case-management/openapi.json
cd C:\case-search\frontend; npm run gen:api
```

**The browser walk-through** (four windows, or background jobs):

```powershell
# 1. A throwaway database with six fictional accounts (it is re-created each time).
cd C:\case-search\backend; uv run python -m scripts.e2e_prepare

# 2. The API on that database, on port 8010.
$env:POSTGRES_DB = 'casesdb_e2e'; $env:EVIDENCE_DIR = "$env:TEMP\kh-e2e-evidence"
uv run uvicorn app.main:app --port 8010

# 3. The web app pointed at that API, on port 5180.
cd C:\case-search\frontend; $env:API_PROXY = 'http://127.0.0.1:8010'; npx vite --port 5180 --strictPort

# 4. The walk-through (from backend/). Screenshots go to the folder you name.
cd C:\case-search\backend; uv run --with playwright python ..\frontend\e2e\walkthrough.py --url http://127.0.0.1:5180 --shots $env:TEMP\kh-screens
```

To look around the walk-through's data yourself, log in at `http://127.0.0.1:5180` as `kh.admin`, `kh.supervisor`, `kh.arun`, `kh.meena`, `kh.dev` or `kh.viewer`. The password is `Fictional-walkthrough-1`: test-only accounts in a throwaway database.

## 6. How it works

**Navigation.** The menu has three parts:
- **Investigation**, for everyone: dashboard, my active cases, assigned tasks, review requests, shared investigations, invitations, notifications, my contributions.
- **Administration**, for administrators only.
- **Case Intelligence**: the similar-case search.

A case opens in your active clone, shown GitHub-style with 12 tabs. Old clones are not in your case list: you reach their history through the clone you work in, as the specification requires.

**Access is decided by the backend.** The screens hide what you can't use, but that is only for clarity. Every button's permission comes from the backend (the `can` flags), and the backend checks every request again. A viewer who opens a case they aren't on gets "Not found", exactly as for a case that doesn't exist.

**Safe writes.**
- Every create action sends an `Idempotency-Key` that stays the same while the dialog is open, so a double click saves once.
- Every commit sends the branch head it was based on, so a colleague's simultaneous change is refused (409) instead of overwritten.
- After an action, the parts of the page it affects reload.
- Adding a note or an exhibit from the explorer opens the folder it went into.

**Live notices.** Browsers can't send the login header with their built-in event source, so the stream is read with `fetch`.
- The backend checks the notices every 5 seconds, using a short database session each time, and sends the unread count and the newest notice's number.
- When they change, the page fetches the notices through the normal audited endpoint, refreshes the lists they concern, and shows a short message.
- The stream ends when the login expires, and after 10 minutes, when the browser reconnects.
- Through Caddy, the first event arrives at once: no buffering.

**Graphs.** Each lane is a repository (the administrator's lineage) or a branch (the investigation graph), and commits run left to right in time.
- A link that goes to another lane leaves its commit vertically, so it is clear which commit a clone or a merge starts from. This shows the real parent and source commit, not just version numbers (specification §14).
- A diamond is a merge, with two parents.
- A dashed line is a clone, or a branch starting from that commit.
- A violet line brings in merged findings.

**Case links.** Linking case A to case B adds a `link` entry at `case-links/<case ID>` in a commit on a branch you may write to, with the kind (for example "same person of interest") and your reason.
- On a working branch, the link reaches `main` through a review, like everything else.
- Withdrawing a link is an ordinary commit; the link stays in the history.
- The `case_links` table indexes links so that case B can show "linked from A", but only to people who can open case A.
- Linking needs access to both cases.

**Report preview.** The report is built by the backend from one commit, with the same access rules as the screens (a sealed exhibit is left out, and the report says so). Printing it in the browser does not create a report version: signed, versioned PDF reports that can be verified later come in phase CM-7, and the preview says this.

**Charts.** The chart colour was checked with a palette validator for each mode: the bright cyan of the buttons is too light for chart bars on the navy background, so the charts use the next darker step. Each chart can switch to a table of the same numbers.

**Loading.** The charts and graph drawing are large, so the administrator's pages, the investigation graph and case links load the first time they are opened. The rest of the application loads at once (707 kB, 202 kB compressed). The build still warns that this main chunk is over 500 kB. That is a suggestion, not an error; it can be split further later.

## 7. Endpoints in this phase

| Method and path | What it does | Who |
|---|---|---|
| `GET /api/v1/colleagues?purpose=lead\|supervisor\|invite&classification=&repo_id=&q=` | people who could be chosen: active, same organisation, a suitable role, enough clearance; for an invitation, not already members, with the roles each could have and whether an invitation is open | those who may register cases / invite |
| `GET /api/v1/notifications/stream` | Server-Sent Events: `notices` (unread count, newest number), `expired`, `reconnect` | any logged-in user |
| `GET /api/v1/contributions/mine` | your commits in repositories you can open, and your totals | any user |
| `GET /api/v1/admin/overview` | the organisation's figures within your clearance | platform admin |
| `GET /api/v1/repositories/{id}/links?ref=` | links at a branch or commit (withdrawn ones marked), and cases that link to this one | members |
| `POST /api/v1/repositories/{id}/links` | link another case you can open, with a kind and a reason (a commit) | writers of the branch |
| `GET /api/v1/repositories/{id}/report-preview?ref=` | what a report on that commit contains | members |

`GET /api/auth/me` now also returns `org_role` and `organization_id`. The module now has 82 endpoints (counted from the OpenAPI description).

## 8. How to test

```powershell
cd C:\case-search\backend;  uv run pytest -q                        # 480 passed
cd C:\case-search\frontend; npm test; npm run lint; npm run build   # 28 passed, no warnings, build OK
```

What the new tests prove:
- **Backend:**
  - colleague lists contain only people who could be chosen, and never their clearance;
  - a contributor can't search for people to invite;
  - the admin overview counts correctly, and only admins see it;
  - the live stream sends counts only, refuses missing or invalid logins, and ends when the login is no longer valid;
  - links need access to both cases;
  - links are commits;
  - links can't be edited, and a withdrawn link stays in the history;
  - the database refuses to change or delete link records;
  - the report preview describes one commit, with hashes, custody, integrity checks and approvals, and leaves out sealed exhibits for those who may not see them.
- **Frontend:**
  - the line-difference algorithm;
  - the stream parser;
  - notice wording;
  - path names;
  - times;
  - the allowed status changes;
  - the original, clone and superseded labels;
  - the commit-ID link;
  - the confirmation dialog, which requires a reason;
  - showing notes and differences.
- **Browser walk-through** (section 5). Five fictional people play a case, and each step checks something visible, through all 20 screens. Along the way it also checks that:
  - the investigator's bell updates **without reloading**;
  - a deletion and a history rewrite are refused (405) and appear in the audit history;
  - a viewer who isn't on the case gets "Not found".

## 9. Expected output

```text
480 passed                                          (backend)
Test Files  4 passed (4)   Tests  28 passed (28)    (frontend)
ALL 25 STEPS PASSED in 41 s                         (browser walk-through)
all checks passed                                   (Docker: smoke test 8/8, CM-4 checks 9/9; 0 cases in the development database)
```

## 10. Common errors and fixes

| Problem | Cause | Fix |
|---|---|---|
| `Property 'gutter' does not exist` / `Property 'in' does not exist` | Mantine 9 renamed props | `Grid gap=…`, `Collapse expanded=…` |
| White text on a bright button (2.5:1) | Mantine picks the text colour of a filled button from the light-mode shade | the same filled shade in both modes (`primaryShade: { light: 8, dark: 8 }`); links keep the bright shade |
| A multi-select can't be clicked in a test | Mantine hides its input when it is neither searchable nor has a placeholder | `searchable` and a placeholder |
| `npm install openapi-typescript` fails (ERESOLVE) | it needs TypeScript 5; the project uses 7 | `npm run gen:api` (runs it with its own TypeScript 5) |
| The walk-through fails at "1 ahead" or finds an old case | creating a branch is a commit too; the database kept the last run's cases | re-run `scripts.e2e_prepare` before every walk-through (case records can't be deleted, so the whole database is re-created) |
| `'charmap' codec can't encode` in the walk-through | the Windows console can't print some characters | the walk-through prints plain text |
| Playwright `InvalidSelectorError … unexpected symbol` | a regular expression containing `/` | match plain text instead |
| A field isn't found by its label in Playwright | required fields add " *" to the label | the walk-through's `field()` helper accepts both |
| `document.fonts` is undefined in tests | jsdom doesn't have it; auto-growing text areas use it | a stub in `src/test/setup.ts` |
| The bell shows nothing new | the stream reconnects every 10 minutes, or the login expired | it reconnects by itself; after a new login it works again |
