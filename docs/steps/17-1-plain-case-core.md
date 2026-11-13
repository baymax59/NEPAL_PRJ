# Step 17, phase G-2: the plain case design, database and core

Design: [case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md). Built 2026-11-10. The live application (Docker) was upgraded to this version on 2026-11-11 (see steps/17-5, item 11).

1. **What was removed.** The tables `case_repositories`, `repository_clone_events`, `repository_branches`, `branch_head_events`, `commit_snapshots`,
   `snapshot_entries`, `repository_commits`, `commit_parents`, `repository_active_assignments`, `repository_members`, `contributor_invitations`,
   `review_requests` and `review_decisions`, and every column that pointed at them. The code for clones, branches, commits, snapshots, merging, review
   requests and invitations is gone (`reviews.py`, `merging.py`, the repository, commit and review endpoints, their tests).
2. **Migration 0019** (`backend/alembic/versions/0019_plain_case_design.py`). It refuses to run if any case exists (nothing is converted: the cases were emptied
   on purpose; take a database backup first, as always). New tables: `case_folders` (permanent), `case_members` (status only), `case_entries` (the history chain,
   permanent). Notes and exhibits get a folder and a status (active or withdrawn, with who, when and why). The downgrade puts the git-style tables back, empty,
   from `backend/alembic/old_git_schema_0018.sql` (made with `pg_dump` from the 0018 database); I compared the downgraded schema with the real 0018 schema: the only
   differences are the order of re-added columns and how Postgres prints equivalent checks. The existing test that walks every migration down to empty and up again passes.
3. **Folders at registration.** `engine.create_case` makes the case's folders at once from its type (in the type's order), the summary note in *case-information*
   (and the FIR reference note if one was given), puts the Investigator on the team as lead, and writes the first history entry. Folders are flat (no sub-folders), named with
   letters, digits, spaces and `. _ -`; the Investigator or Supervisor may add more; none is ever renamed or removed. Reports, imports and links will make their own folders on
   demand (G-3).
4. **Files.** A note is written into a folder and is part of the case at once (`POST /v1/cases/{id}/notes`); `POST /v1/artifacts/{id}/versions` adds a new version (the
   caller names the version it was based on: a stale edit is refused with 409); `POST /v1/artifacts/{id}/withdraw` and `/evidence/{id}/withdraw` withdraw a wrong file with a
   reason. Exhibits are uploaded into a folder (`POST /v1/cases/{id}/evidence`). Files are named by number (`NOTE-0001`, `EV-0001`); a note's `derived_from` lists file numbers.
   `GET /v1/cases/{id}/files` lists exhibits and notes together, folder by folder; withdrawn files show only when asked for.
5. **The history chain** (`history.py`, `case_entries`). Every change of the case is an entry: registration, folders, notes and revisions, exhibits, withdrawals, sealing, status
   changes, official references, team changes, hand-over. Each entry holds the fingerprint of the one before it; the database accepts only the next entry in order and refuses to change
   or delete any. `GET /v1/cases/{id}/history` lists it; `GET /v1/cases/{id}/history/check` recomputes every fingerprint and link ("History is intact").
6. **The team, added directly** (`members.py`). The Investigator who leads the case, its Supervisor, an Administrator of its station or the Super Admin adds a Sub Investigator, an Analyst
   or a Viewer at once (`POST /v1/cases/{id}/team`): no invitation, no acceptance, no approval. The person must work at the case's station, have enough clearance, and their account role
   must allow the part (Viewer account: Viewer only; Analyst: Analyst or Viewer; Sub Investigator: Sub Investigator or Viewer; Investigator and above: any of the three). Removing someone needs a
   reason and keeps what they did attributed to them. The Supervisor (or an Administrator) hands the case to another Investigator with a reason (`POST /v1/cases/{id}/lead`); the old
   lead stays as a Sub Investigator.
7. **What each part may do** (`access.Rights`): the Investigator and the oversight roles add files, revise any note, withdraw files, add folders, manage the team; Sub Investigators and Analysts add
   files and revise their own notes only; Viewers read. An archived case is read-only (its status may still be changed).
8. **Moved to the case:** tasks, comments (on the case, an exhibit, a note or a task), notices (`case.assigned`, `team.added`, `team.removed`, `team.role_changed`), access history, sealing of notes
   and exhibits, the colleague search (`purpose=team`), `GET /v1/cases/mine`.
9. **How it was checked.** 476 backend tests pass (the whole suite except the files parked for G-3). New: 17 tests in `test_cm_plain_case.py` (folders at registration for two case types, notes, versions and
   stale edits, who may do what, withdrawing, exhibits, the history chain including tampering with an entry, with its fingerprint recomputed, and with an entry taken out, the team rules,
   removal, hand-over, archived), 27 in `test_cm_access_permanence.py` (404 like a missing one, other organisations, clearance, the administrators' view, the database refusing to change or
   delete records, the triggers the migration installed). Older tests were ported to the case (cases, evidence, custody, tasks, comments, idempotency, sealing, stations and roles). I broke
   eleven rules one at a time (a Viewer adding, anyone revising any note, a withdrawn file still shown, the history check ignoring the fingerprint or the link to the previous entry, the
   account-role rule, the station rule, a removed member keeping access, the old lead being dropped, an archived case still changing, a stale edit overwriting): each break made a test fail.
10. **Bugs found by the tests on the way:** folders made in one request all had the same moment and came back in alphabetical order (each now has its own); two files made in the same
    transaction listed in the wrong order (files now carry the real clock).
11. **Parked until G-3** (not collected, not wired): links, reports and PDF, similar-case search, timeline, offences, the assistant, integrations, legal holds and retention (the hold check
    still works), the dashboards and officer figures, the administration overview, the live notice stream, the contributions page. Their routers are switched off in `app/main.py`
    and their tests listed in `tests/conftest.py` (`collect_ignore`).
