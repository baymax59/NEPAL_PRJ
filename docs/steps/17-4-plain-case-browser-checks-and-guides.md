# Step 17, phase G-5: the plain case design, browser checks, demonstration and guides

Design: [case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) (section 11 lists the choices made here). Built 2026-11-10, on top of
[17-1](17-1-plain-case-core.md), [17-2](17-2-plain-case-backend.md) and [17-3](17-3-plain-case-screens.md).

**Status of the live application: upgraded on 2026-11-11** (see steps/17-5, item 11). Everything below was first checked on throwaway databases (`casesdb_test`, `casesdb_e2e`).

1. **Acceptance test rewritten** (`backend/tests/test_cm_acceptance.py`, 5 tests). It follows the 17 steps of the specification's section 27 on the plain case: the administrator registers a case;
   the ten folders and history entry 1 appear at once; the Investigator leads it; exhibits and notes are added; a folder is added; the Sub Investigator and the Analyst join straight in (no approval);
   they add their findings; the Supervisor approves, and the approval is a numbered, tamper-evident history entry; a wrong analysis is corrected with a new version and a reason, the old version stays
   unchanged; the Administrator sees every file, version, team member, history entry and access change; every exhibit is re-hashed; six deletion or rewrite attempts are refused (405) and audited, and a stale edit
   is refused (409); a signed report "as of entry N" is generated and its downloaded copy matches its recorded checksum.
2. **Demonstration seed rewritten** (`backend/scripts/demo/`, `backend/scripts/demo_case.py`): the same 17 steps through the real API, with five fictional accounts (an administrator, a Supervisor, the Investigator
   who leads, a Sub Investigator and an Analyst). It refuses to run against a database that already holds cases, and its credentials go to a git-ignored file.
3. **Browser scripts rewritten** (`frontend/e2e/`, Playwright, against the real backend on a throwaway database):
   - `walkthrough.py`: 37 steps (registration with its ten folders, the files, the team added at once, tasks and live notices, history and its check, the Supervisor's approval, a new note version, a withdrawal,
     links, the signed report, similar cases, in-case search, timeline, offence sections, the assistant, integrations, the administration pages, the refused deletions in the audit trail, governance,
     legal hold, hand-over, access enforced by the backend, two-step verification). **37 of 37 pass.**
   - `acceptance.py`: the 17 steps of the specification in the browser, plus 3 live-update checks. **All pass.**
   - `people_tour.py` (10 checks) and `dashboards_tour.py` (7 checks). **All pass.**
   - `demo_tour.py`: a read-only tour of the seeded demonstration that takes the pictures for the guides. **26 of 26 pass** (the first run failed on one wrong note title in the script itself, "(fictional)", which the
     seed does not put in that title; fixed in the script, the product was right).
4. **Guides.** `docs/guides/investigator-guide.md` and `administrator-guide.md` describe the plain case; their 25 pictures in `docs/guides/img/` were retaken from the seeded demonstration. Nine old pictures of the
   removed screens (repository page, commits, clone dialog, graph, lineage, superseded and wrong-commit views, contributor contributions, the old add-evidence dialog) were removed: nothing referenced them.
5. **Documents brought up to date:** `docs/case-management/06-api-contracts.md` (generated), `09-integration-contract.md` (version 2.0), `10-acceptance-and-traceability.md`, `11-production-readiness.md`,
   the case-management `README.md`, banners on the older design documents and step notes, `docs/DECISIONS.md`, the root `README.md` and `docs/DEVELOPMENT_PLAN.md`.
6. **Small clean-ups:** the two invitation settings (`CM_INVITATION_APPROVAL`, `CM_INVITATION_DAYS`) were removed from the code, `.env.example` and `docker-compose.yml` (nothing uses invitations any more);
   the integration contract version is now 2.0.
7. **Final checks (2026-11-10).**
   - Backend: **541 tests pass** (one run at a time, on `casesdb_test`).
   - Front end: **69 tests pass**, the strict build (`tsc -b`, `vite build`) and the linter are clean. One of the 69 failed once while the backend suite was running at the same time (a timeout on a busy
     computer); it passes alone and on a quiet computer. Run the two suites one after the other.
   - The seed and the tour were run on a fresh throwaway database (`casesdb_e2e`): all 17 seed steps and all 26 tour checks pass.
8. **Still to do (needs the owner's decision, because the live database holds one test case and cases can never be deleted by the application):** back up the live database, deal with
   that one test case (KH-2026-0001 "bank robbery": 2 repositories, 2 commits, no evidence), migrate to 0019, rebuild the Docker application, and, only if the owner says so, seed the demonstration
   into the live database.
