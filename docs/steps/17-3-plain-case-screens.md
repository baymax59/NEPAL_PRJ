# Step 17, phase G-4: the plain case design, the screens

Design: [case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) (section 10 lists the choices made here). Built 2026-11-10, on top of
[17-1](17-1-plain-case-core.md) and [17-2](17-2-plain-case-backend.md). The live application (Docker) was upgraded to this version on 2026-11-11 (see steps/17-5, item 11).

1. **What was removed.** Every screen of the git-style design: the repository page and its tabs (Branches, Commits, History as a graph, Investigation graph, Review requests), the clone,
   sync and branch dialogs, the review page, "Shared investigations", "Invitations", "Review requests", and the administrator's "Repository registry" and clone lineage. The words
   *commit, branch, clone, merge, repository, update 14* appear nowhere a person reads. The front end now takes its shapes from the new `openapi.json` (`npm run gen:api`).
2. **The case page** (`/kh/case/:id`, `src/kh/case/`). A header with the case number, status, *your part* (or "you oversee this case"), the Investigator, the Supervisor, priority and
   classification, and the buttons *New note* and *Add exhibit* (shown only to people who may add). Nine tabs, as designed:
   - **Overview:** the folders made at registration (with how many files each holds), the description, the latest six history entries, the facts, the status and official-status buttons, the
     official references, open tasks, the team, legal holds and retention, and the status history. *Hand over the case* appears only for the Supervisor, an Administrator or the Super Admin.
   - **Files:** the permanent folders on the left (with counts), the files of the chosen folder on the right, a switch for withdrawn files, *New folder / New note / Add exhibit*. A file opens in a side panel: a
     note shows its content and every version with the differences, and offers *New version*, *Withdraw* (with a reason) and, to the Supervisor or an Administrator, *Seal*; an exhibit shows its facts
     and opens the exhibit page (integrity check, custody, preview).
   - **Team:** the members and their parts, *Add team member* (the person joins at once and is told by a notice), *Take off the team* (with a reason; never the lead), the hand-over, and the permanent access history.
   - **Tasks, Links, Reports, Insights** (similar cases, search, the assistant, the timeline, offence sections) **and Imports** work on the case as it stands now.
   - **History:** every entry, oldest first, numbered, 100 at a time, with *Check the history* that says "History is intact" or names the first entry that does not check out.
   - **Audit** (Super Admin only), as before.
3. **Other screens.** *My cases* (the cases you are on the team of, with your part; and all the cases you may open), the Dashboard (my cases, open tasks, notes written, exhibits added, recent contributions,
   notices), *Register a case* (station, type of case: the folders it will make are listed on the form; afterwards a summary of the folders made and who leads), *My contributions* (history entries,
   notes written, new versions, exhibits added), the officer and station dashboards (notes written and exhibits added instead of reviews), the administration pages (overview with entries per day,
   *All cases* with entries, files and exhibits, one case with its history, access history and audit trail, investigation activity) and the menus (*My cases*; *Review requests*, *Shared investigations*,
   *Invitations* and *Repository registry* are gone). Notices now lead to the case (`team.added`, `case.assigned`, `task.assigned`, ...).
4. **Small backend additions the screens needed** (all tested): the notice payload carries `case_id`; `GET /v1/cases/{id}/history?latest=N` gives the newest entries (for "Recent activity");
   the note view says whether the person may seal it (`can.seal`); two messages no longer say "SHA-256" (the report preview note, and the reason a stored file was not read).
5. **How it was checked.**
   - 68 front-end tests pass (56 before the new screens: the older ones were ported to the case; 12 new in `src/kh/case/case.test.tsx` for the Files, Team, History and Overview screens, covering who is
     offered what: a Viewer sees no add buttons, only the Investigator or an overseer can add or take off team members, the lead can never be taken off, withdrawing needs a reason and is sent as a
     withdrawal, the history check shows both outcomes). The strict build (`tsc -b` and `vite build`) and the linter are clean.
   - The whole backend suite passes again (the backend changed a little in this phase).
   - A **browser check against the real backend** on a throwaway database (a fresh database brought to migration 0019 from nothing, so that also proves the whole chain of migrations works): the Investigator
     opens *My cases* and the case, sees the nine tabs and none of the old ones, adds a folder, a note and a team member, makes a new version, runs the history check ("History is intact"), generates a signed
     report ("as of entry 10"), opens Links, Insights and Imports; a Viewer sees the files and can add nothing; the Supervisor sees the hand-over; the Supervisor registers a second case in the browser and
     sees its ten folders; the Super Admin opens the administration pages. 0 console errors and 0 failed requests. I looked at the screenshots of each screen.
6. **Found on the way:** the report preview note and one "not read" message still said "SHA-256" (reworded); old comments in the backend still talked about snapshots and repositories (reworded).
7. **Parked until G-5:** the browser scripts in `frontend/e2e/` (still describe the old screens), `tests/test_cm_acceptance.py`, the demo seed scripts, the guides (`docs/steps/15-*`, the administrator's and
   the investigator's guides, the API contract in `09`), the migration of the live database to 0019 (backup first) and the Docker rebuild.
