# Step 17, completion report (2026-11-11)

The final state of Knight Hawk Case Management and Case Intelligence, how it was verified, and what is left for people to do. Everything the software
needs is built and checked; what is left are decisions and actions that only your organisation can take.

## 1. What exists

- **Case Intelligence** (Steps 0 to 14): the similar-case search over the 100 imported Supreme Court judgments (keyword, meaning and both), match
  explanations, uploads of a new case, the timeline and entities, the case assistant, authentication, roles, the audit log, production set-up.
- **Case Management** (Step 15, rebuilt as a plain case in 17-1 to 17-4): a case with the folders made at registration, files (exhibits that never
  change, notes with versions, wrong files withdrawn with a reason), a team built directly by the Investigator, one numbered tamper-evident history with
  a check, links, signed reports, insights inside the case, integrations, legal holds and retention, dashboards, people, stations and roles.
- **Added in 17-5 and after:** a formatted description written in a compose window; "Reported by" (or Unknown); officers creating their own
  login (view-only until a Supervisor or Administrator raises role and clearance); change of clearance; each person's profile (email, phone, job title, a photo) and
  the teams they are on; chat inside a case (the team group and private messages between two members); the case assistant made fast enough to answer within the limit; the similar-case comparison inside a case made to find past cases;
  the blue log in page and the new typeface; Tasks and the Governance heading removed from the screens.
- **The live application** (Docker, https://localhost:8443) runs all of it, on a cleared database (migration **0025**) with the 100 past judgments and one
  account, the Super Admin `superadmin`.

The administration **Governance** screen (audit chain buttons, scheduled checks, retention policies, the list of holds) was removed on 2026-11-12 at the owner's request; the backend is unchanged: the worker still checks and signs the audit chain every day, and legal holds and retention decisions are still made on each case.

## 2. How it was verified (all passing on 2026-11-11)

| Check | Result |
|---|---|
| Backend tests (`uv run pytest -q`, one run at a time) | **601 passed** |
| Front-end tests, strict type check, linter, production build | **97 passed**, all clean |
| Browser, fresh throwaway database each: walkthrough / acceptance / people / dashboards / accounts and registration | **36 / 17 + 3 live checks / 10 / 7 / 5 / 3 steps passed** (the last two are the accounts and registration tour and the chat tour) |
| Browser tour of the seeded demonstration (pictures of the guides) | **25 checks passed** |
| Acceptance scenario (spec section 27) as one automated test | **5 passed** |
| Static analysis (Bandit, medium and high), `npm audit`, `pip-audit` | no findings, 0 vulnerabilities, none known |
| Official backup and its restore check (`2026-11-11T132647Z`) | passed |
| The live application in a browser (log in, register form, profile, past-case search over 100 cases) | checked, no errors |
| Security review of the changes of this day | `SECURITY_REVIEW.md` section 5 (findings F8 to F13) |

Rules proved by breaking them on purpose (a test failed each time): the cleaning of formatted text, the name check and the "already has an account" check
of signing up, the clearance ceiling, "only these three fields" of the profile, the lower bar of the past-case comparison.

## 3. Found and fixed while completing it

The formatted description cleaning; clearing a profile field with an empty value was refused; the case assistant timing out (the model used 6 of 12
processor threads and a long prompt); the Insights tab finding no past case for any case (a bar of 0.80 meant for comparing two judgments); the log in
page still talking about repositories and clones; the demonstration still creating tasks that no screen shows; two tests that depended on the developer's
`.env`; the order of two versions made at the same moment; the readiness items "test source off" and "a recent backup".

## 4. The readiness check

`uv run python -m scripts.readiness_check` reports **14 of 37** go-live items done. The open ones cannot be done by the software:

| Open item | Who and what |
|---|---|
| Decisions D1 to D16 (`docs/DECISIONS.md`) | Your organisation: legal basis, protected identities, who may see what, retention periods and disposal, hosting, network, backups, use of the AI, independent security review, evidence storage, keys |
| Certificate from the organisation, HSTS | The organisation's certificate for the server, then HSTS on in `deploy/Caddyfile` |
| Audit log retention period | A decision (D4): how long the similar-case search's own events are kept (`AUDIT_RETENTION_DAYS`) |
| Two-step verification required (`CM_MFA_REQUIRED=true`) | The Super Admin sets up an authenticator app under **Account**; then switch it on |
| Development account (`superadmin`'s password in `.dev-credentials.txt`) | Keep the password in a password manager, then delete the file or change the password |
| Search-quality labels reviewed by a legal expert (D9) | A legal expert reviews the 32 queries |
| Police connector adapted to the real export (D2) | Needs the real export format |

## 5. How to run everything again

```powershell
cd C:\case-search\backend
uv run pytest -q                                   # all backend tests (one run at a time: they share one test database)
cd ..\frontend; npx tsc -b; npm run lint; npx vitest run; npm run build
```

Browser scripts (`frontend/e2e/`): make a throwaway database, start the API with the fictional test source ON (it is off in the live `.env`), start
the web app against it, then run a script:

```powershell
cd C:\case-search\backend
$env:E2E_DB = "casesdb_e2e"            # any name containing _e2e; never the live database
uv run python -m scripts.e2e_prepare
$env:CM_TEST_SOURCE = "true"; $env:POSTGRES_DB = "casesdb_e2e"
uv run uvicorn app.main:app --port 8010          # in one window
cd ..\frontend; $env:API_PROXY = "http://127.0.0.1:8010"; npx vite --port 5180     # in another
cd ..\backend
uv run --with playwright==1.64.1 python ../frontend/e2e/walkthrough.py --url http://127.0.0.1:5180 --shots shots
```

The other scripts: `acceptance.py`, `people_tour.py`, `dashboards_tour.py`, `accounts_tour.py` (each needs a fresh `e2e_prepare` first) and
`demo_tour.py` (after `uv run python -m scripts.demo_case`, see `docs/guides/administrator-guide.md` section 11).

## 6. Not built, on purpose

OCR of scanned pages; Indian-script fonts in the signed PDF; single sign-on; write-once evidence storage outside the application; court-specific
report formats; high availability. Each is listed with its reason in `docs/case-management/11-production-readiness.md` section 3.

## 7. Housekeeping

- **Nothing is committed to Git** (the owner's rule); the work is in the working folder `C:\case-search`. A first commit is the owner's call.
- **Backups** are in `C:\case-search\backups\` (git-ignored). The older ones from this day's changes can be deleted once you are satisfied.
- **The old copy of the project** in the OneDrive folder (`NEPAL_PRJ`) is out of date: delete it, to avoid working in the wrong folder.
- **The preview was deleted** on 2026-11-12 (its web server, its API, its throwaway database `casesdb_e2e` and its temporary files). Only the live application and the test database `casesdb_test` remain. To make a throwaway environment again, follow section 5 (`e2e_prepare` makes the database; `python -m scripts.demo_case` seeds the demonstration; the 100 past judgments can be copied from the live database with `pg_dump --data-only --on-conflict-do-nothing` of the tables `ingestion_runs, cases, case_documents, document_pages, document_chunks, document_provisions, case_entities, case_events`).
