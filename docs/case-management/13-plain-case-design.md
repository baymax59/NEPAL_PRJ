# 13. The plain case design (replaces the git-style design)

Status: **design written 2026-11-10 (phase G-1); G-2 (database and core) built 2026-11-10, see [steps/17-1](../steps/17-1-plain-case-core.md); G-3 (the rest of the backend) built 2026-11-10, see [steps/17-2](../steps/17-2-plain-case-backend.md); G-4 (the screens) built 2026-11-10, see [steps/17-3](../steps/17-3-plain-case-screens.md); G-5 (browser checks, demonstration, guides) built 2026-11-10, see [steps/17-4](../steps/17-4-plain-case-browser-checks-and-guides.md); the live database and the Docker application were cleared of case data and upgraded to this version on 2026-11-11 (steps/17-5, item 11).** Asked for by the user on 2026-11-10: remove the git-style design completely,
keep the folders that are created automatically when a case is registered, and let the Investigator set the Sub Investigator and the Analyst.
The user chose **"remove it completely"** (not just hide it) and **"Sub Investigator and Analyst add straight into the case"** (no approval step).
A full copy of the code before this change is in `backups/20261110-165956-code-before-plain-case-design.tar.gz` (the project has no Git history, so this copy is the way back).

## 1. In plain words

**Today** a case is built like Git: an original copy (ROOT) plus numbered working copies (V1, V2), each with branches, saved updates (commits),
merging of findings after a review, a graph of updates, compare and clone screens.

**After this change** a case is simply:

- **Folders**, created automatically when the case is registered (from the case type, e.g. *case-information, complainant, digital-evidence…*). Kept as the user likes it.
- **Files** in those folders: exhibits (uploaded files) and notes / analyses / timelines / transcriptions (written in the system).
- **A team**: the Investigator who leads the case, and the Sub Investigators, Analysts and Viewers the Investigator (or the Supervisor) adds to it. Added directly: no invitation to accept, no approval step.
- **Tasks**, **comments**, **links to other cases**, **signed reports**, **similar-case search and timeline** (all as today, but on the case itself).
- **A history**: one plain list, oldest first, of everything that happened in the case: who added which file, who joined, who was removed, status changes, reports. Entry numbers 1, 2, 3…

**Gone:** the original copy and V1/V2 copies, branches ("lines of enquiry"), saved updates and their numbers ("Update 14"), merging, review requests as a merge step, the
update graph, comparing two updates, the historical snapshot viewer, "Start a corrected version from here", invitations to accept.
A mistake is corrected the way a paper file would be: a **new version** of the note (the old one stays visible), or the wrong file is **withdrawn with a reason** (it stays in the history).

**Kept exactly:** stations and the seven roles, accounts and officer register, the promotion rule, dashboards, the case workflow statuses (Registered … Closed, Archived), official references,
evidence checks ("File is original"), chain of custody, legal holds and retention, the signed audit trail, nothing is ever deleted, and the Super Admin cannot delete anything.

## 2. How the permanent record is kept without Git

| Safety today | How it is kept |
|---|---|
| Nothing is deleted or rewritten | Same: database rules refuse DELETE and changes to history; the app's database user has no DELETE right; withdrawing a file keeps it. |
| A saved update can be proved unchanged (commit hashes) | **A chain of history entries per case.** Each entry holds the fingerprint of the one before it, so changing, removing or reordering any entry is detected by *History check* (silent; the screen says "History is intact"). Simpler than the commit graph: one line, no branches. |
| A file is the original | Unchanged: every uploaded file is fingerprinted, stored write-once, re-checked on demand ("File is original / was changed"). |
| A note can be corrected without losing the old text | Unchanged: each edit is a new version of the note (append-only). |
| Who saw or did what | Unchanged: the signed, chained audit trail records every request. |
| A report matches the case at one moment | A report is made **for the case as it is now** and records "as of entry N" and the version of every file it lists; the PDF is stored write-once and can be checked byte for byte, as today. |
| No two people overwrite each other (expected head) | Each note has a version number; a change names the version it was based on and is refused with "someone changed it, reload" if it is out of date. Adding a new file never conflicts. |

## 3. The team (the user's second request)

- **Who adds:** the case's Investigator (its lead), the case's Supervisor, an Administrator of the station, the Super Admin. Nobody adds themselves.
- **Who can be added:** an active person who works at the case's station, with enough clearance, whose account role allows it: a Viewer account → Viewer only; an Analyst account → Analyst or Viewer;
  a Sub Investigator account → Sub Investigator or Viewer; an Investigator account → Sub Investigator, Analyst or Viewer (another Investigator can help on this case).
- **How:** *Add team member* on the case's Team tab: choose the person and their part. They are told by a notice. No acceptance, no approval. Removing someone needs a reason; what they did stays credited to them.
- **Handing a case to another Investigator** (replaces "clone with a new assignee"): the Supervisor or an Administrator chooses the new lead with a reason; the old lead stays as Sub Investigator unless removed.

What each part may do in a case:

| | Investigator (lead) | Sub Investigator | Analyst | Viewer | Supervisor / Administrator / Super Admin |
|---|---|---|---|---|---|
| See all files of the case | yes | yes | yes | yes | yes (within station and clearance) |
| Add and create files, new versions of their own notes | yes | yes | yes (analyses, notes, files) | no | yes |
| New version of someone else's note | yes | no | no | no | yes |
| Withdraw a file (with a reason) | yes | no | no | no | yes |
| Add folders | yes | no | no | no | yes |
| Tasks: create / assign | yes | create | create | no | yes |
| Add or remove team members | yes | no | no | no | yes |
| Change the workflow status | yes (except closing, archiving, reopening) | no | no | no | closing, archiving, reopening: Supervisor / Administrator / Super Admin |
| Seal a note, official reference, hold | no | no | no | no | Supervisor / Administrator / Super Admin (as today) |

(The promotion rule still decides which cases an Administrator's or Super Admin's *powers* reach.)

## 4. Data: what changes

The live database has **no cases** (the user emptied it), so nothing has to be converted. Migration 0019 refuses to run if any case exists (and, as always, a database backup is taken first by hand),
drops the git tables and creates the plain ones.

- **Removed tables:** `case_repositories`, `repository_clone_events`, `repository_branches`, `branch_head_events`, `commit_snapshots`, `snapshot_entries`, `repository_commits`,
  `commit_parents`, `repository_active_assignments`, `contributor_invitations`, `review_requests`, `review_decisions`.
- **New:** `case_folders` (case, name, added by, when; permanent; created from the case type at registration), `case_members` (replaces `repository_members`: case, person, part, added by, removed by/when),
  `case_entries` (the history chain: number per case, kind, actor, time, what it is about, previous entry's fingerprint, its own fingerprint; append-only).
- **Moved from "repository" to "case":** evidence items and versions, artifacts and versions (a note's folder and name are now columns), tasks and task events, comments, case links, report exports,
  integration imports, integration indicators, notifications' targets. Their `repository_id`, `branch_id`, `commit_id` columns go; they point at the case and, where useful, at the history entry that recorded them.
- **Unchanged tables:** organisations, stations, user stations, officer register, users, case families, official references, status events, authorization events (access history), custody, integrity checks, object texts / pages / chunks,
  integration sources, report verifications and downloads, audit checkpoints, legal holds, retention, job runs, idempotency keys.
- **Names on screens and in the API:** *case, folder, file, note, version, team, history, entry*. No *commit, branch, clone, merge, snapshot, repository, hash* anywhere a person reads.

## 5. API and screens

- **Endpoints (new, all under the case):** `GET/POST /v1/cases/{id}/folders`, `GET /v1/cases/{id}/files`, `POST /v1/cases/{id}/notes`, `POST /v1/notes/{id}/versions`, `POST /v1/cases/{id}/evidence`,
  `POST /v1/files/{id}/withdraw`, `GET /v1/cases/{id}/history`, `GET /v1/cases/{id}/history/check`, `GET/POST /v1/cases/{id}/team`, `POST /v1/cases/{id}/team/{user}/remove`, `POST /v1/cases/{id}/lead`,
  and the existing tasks, comments, links, reports, similar cases, search, timeline, offences, assistant, imports under `/v1/cases/{id}/…`. Integrations' `add-to-case` takes a `case_id` (contract in 09 updated).
- **Endpoints removed:** repositories, branches, commits, clones, snapshots, compare, graph, reviews, invitations, workspaces, commit numbers.
- **Case page tabs:** Overview · Files · Team · Tasks · History · Links · Reports · Insights (similar cases, timeline, offences, assistant) · Imports. (Menu "Review requests", "Shared investigations", "Invitations", and the admin "Repository registry" go; "My active cases" becomes "My cases".)
- **Dashboards:** the officer figures about reviews (approved, sent back, merged) are replaced by *files added* and *notes written*; everything else stays.

## 6. Build order

| Phase | Content | Test that it works |
|---|---|---|
| **G-1** | This document, and a copy of the current code | Reviewed by the user |
| **G-2** (**done 2026-11-10**) | Migration 0019 and the core: folders at registration, files (notes, exhibits, versions, withdraw), the history chain with its check, the team (direct add, remove, hand-over), access rules by part | New tests; the migration up and down on the test database |
| **G-3** (**done 2026-11-10**) | The rest of the backend on the case: tasks, comments, notices and live updates, links, reports and PDF, similar-case search and timeline, integrations, legal holds and retention, dashboards, admin lists; all old tests ported or removed with a reason; OpenAPI regenerated | Whole backend suite green; mutation checks on the new rules |
| **G-4** (**done 2026-11-10**) | The screens: case page and its tabs, My cases, Dashboard, menus, admin pages, Register case; front-end tests | Strict build and tests green |
| **G-5** (**done 2026-11-11, live application upgraded**) | Browser scripts rewritten (walk-through, acceptance, tours), guides, readiness list, traceability of the old acceptance steps; then the migration on the live database (backup first) and the Docker rebuild | Every browser script passes on a fresh database (done); the live application runs migration 0021 (done 2026-11-11) |

The real app kept running the old version until the live upgrade on 2026-11-11, so nothing the user used was broken while this was built.

## 7. Choices made for the user (say if one is wrong)

1. Folders become real, permanent folders at registration; the Investigator and Supervisor may add more (never remove or rename).
2. A Sub Investigator or Analyst may make new versions of **their own** notes only; adding folders stays with the Investigator and above. **Withdrawing** a file is for the Investigator who leads the case alone (changed 2026-11-12, decision 19 below): nobody who oversees the case, the Supervisor included, can withdraw (delete) anything.
3. A Viewer account can only be a Viewer on a case.
4. The case status "Pending review" stays (the Supervisor's decision before reporting); it is no longer tied to a review request.
5. The Investigator cannot close, archive or reopen a case (as today: the Supervisor decides).
6. Old numbers like "Update 14" are replaced by "Entry 14" in the history and in reports.

## 8. Decisions made while building G-2 (say if one is wrong)

1. Folders are flat (no sub-folders). Their names use letters, digits, spaces and `. _ -`.
2. A file is named by its number (`NOTE-0001`, `EV-0001`), not by a path; a note's sources are listed by file number.
3. A Supervisor, Administrator or Super Admin who oversees a case may add files to it even if not on its team (the design table said so); a Viewer never.
4. Comments are written by whoever may add files; Viewers read them.
5. Status changes, sealing, official references and every team change are entries of the history chain, besides their own records.
6. The case summary and the FIR reference note (made at registration) can't be revised or withdrawn.

## 9. Decisions made while building G-3 (say if one is wrong)

1. Reports, imported findings, links and the reconstructed timeline each live in a **system folder** the case makes the first time it needs one: *reports*, *imports*, *links*, *timeline*. They are flat and permanent like every other folder; making one is an entry of the history (marked "system").
2. A report says **"as of entry N"**: the case as it stood at its latest history entry when the report was made. The report is a file that is never edited; a new report is a new version of the same report file (`RPT-0001` version 2). There is no "open the case as it was at that update": the history says what changed, entry by entry.
3. A finding that an outside system sent again **after it was withdrawn** becomes a **new file** (`IMP-0002`), not a new version of the withdrawn one. A finding sent again with a **changed** fingerprint while it is active becomes a new version of the same file; sent again unchanged, it is refused (409).
4. The live notice stream can watch a **case**, an **exhibit** or the **admin** page (it used to watch repositories and reviews too, which no longer exist).
5. The officer figures on the dashboards count **history entries, notes written and exhibits added** (instead of commits and reviews).
6. Search, the assistant, similar cases and offence suggestions read the case **as it stands now** (active files the person may see). A withdrawn file is not read; it stays in the history.
19. **A withdrawn file disappears for the team and stays, highlighted, for the Supervisor (owner request, 2026-11-12).** Once the Investigator who leads the case withdraws a file (for example a bank statement), the Investigator, Sub Investigators, Analysts and Viewers no longer see it anywhere: not in the Files tab (the *Show withdrawn files* switch is gone), not by its link, not in reports, search or the assistant (it is hidden like a sealed file, `access.hidden_file_ids` / `may_see_item` / `artifacts.get_artifact`). Whoever **oversees** the case (its Supervisor, the Administrator of the station, the Super Admin) still sees it in the Files tab, **in red**, with who withdrew it, when and why (`withdrawn_by`, `withdrawn_at`, `withdrawn_reason`). The right to withdraw is now `open and role == lead` (`Rights.withdraw`): a Supervisor, Administrator or Super Admin has no *Withdraw* button and the API answers 403. Not changed: sealing stays with the overseers (it hides a file, it deletes nothing), the history still lists the *withdrawn* entry for everyone who can read it (it is the permanent record), and the dashboard counts of withdrawn files are unchanged.
20. **The case number can be changed (owner request, 2026-11-12: "KH-2026-0001: make this editable"; the owner chose *change the number after registration*).** Whoever oversees the case (its Supervisor, the Administrator of the station, the Super Admin) can change the number while the case is open, with a reason and, where required, a verified two-step login (`Rights.rename_case`, `engine.change_case_number`, `POST /v1/cases/{id}/number`). The case's own id (a UUID) never changes, so links, files and the history chain are untouched. The old number is kept in `case_number_changes` (append-only, migration 0026, the database refuses to change or delete a row); it still finds the case in the case lists, appears as *Formerly ...* under the title, and is **never given to another case** (nor can anyone type a number that another case has or had). The new number is 3 to 32 characters (letters, digits, spaces, `. / _ -`); numbers of the system's own form `CODE-YYYY-NNNN` can't be typed, so a later case can never be given one that is taken (a case may return to its own first number). The change is a numbered history entry (`case_renumbered`: old, new, who, why). The database trigger of `case_families` now lets `display_id` change besides the statuses and the supervisor; everything else of the case stays locked. Reports and history entries already written keep the number they carried when they were written (they are permanent and signed); the report check compares the recorded file, so it is not affected. Archived cases keep their number.
7. Legal hold and retention behave as before; an archived case is read-only, and the holds and retention checks use the team's leads from `case_members`.

## 10. Decisions made while building G-4 (say if one is wrong)

1. The case page is at `/kh/case/:id` with the nine tabs; the old `/kh/repo/...` and `/kh/review/...` addresses are gone. The tab called *Case Intelligence* is now **Insights** (`/insights`).
2. On the Files tab the folders are listed on the left with their counts; a file opens in a side panel. A note offers *New version* (to whoever may revise it), *Withdraw* (Investigator or an overseer) and *Seal*
   (Supervisor, Administrator or Super Admin only). An exhibit opens its own page for integrity, custody and preview.
3. The history is shown oldest first, 100 entries at a time, with a *Check the history* button. The Overview shows only the latest six (a new `latest` option of the history call).
4. *Take off the team* needs a reason and is never offered for the lead; handing the case over is a separate button for the Supervisor, an Administrator or the Super Admin.
5. Notices carry the case's id, so each one leads to its case.
6. No screen or message a person reads says *SHA-256*, *commit*, *branch*, *clone* or *repository* any more (the report preview note and the "not read" reason were reworded).
7. *My cases* lists the cases you are on the team of (with your part); *All cases I can open* lists the rest, with "oversight only" where you see a case without being on its team.

## 11. Decisions made while building G-5 (say if one is wrong)

1. The demonstration is seeded through the real API with five fictional accounts: an administrator, a Supervisor, the Investigator who leads, a Sub Investigator and an Analyst. It refuses to run on a database that already holds cases.
2. The browser scripts run only against a throwaway database (`casesdb_e2e`); nothing in them touches the real `casesdb`.
3. The two invitation settings (`CM_INVITATION_APPROVAL`, `CM_INVITATION_DAYS`) were removed: a team member is added straight in, so nothing is left for them to control.
4. The integration contract is version 2.0 (a finding is added to a case).
5. Nine pictures of the removed repository screens were deleted from the guides; the other 16 were retaken from the new demonstration, plus 9 new ones.
6. The live database holds one test case made under the old design. Migration 0019 refuses to run while any case exists, and the application never deletes cases, so the owner decides what happens to it before the live migration (back it up, clear it, or convert it).

## 12. Changes after G-5: the description and who reported the case (say if one is wrong)

1. **The description is written in a small compose window** (opened by the *Description* button of the Register a case form, in the middle of the screen) with a formatting bar like an email: undo and redo, font, size, bold, italic, underline, text colour, alignment, numbered and bulleted lists, remove formatting.
2. **Two copies of the description.** The plain text stays in `description` and is what the signed reports, the similar-case search, the assistant and the history read, so no formatting marks ever appear there. The formatted copy goes in the new `description_html` (migration 0020) and is only used to show the description on the case page. The server cleans it before it is stored (`app/casemgmt/rich_text.py`: only the formatting of the bar survives; scripts, links, images, event handlers and every other style are removed) and the page cleans it once more before showing it. Existing cases have no formatted copy and show their plain text.
3. **Reported by** (migration 0021): the person who reported the case (name, phone, email, address). Nothing is required. *Unknown* records that no one was there to report it, and cannot be combined with details. Blank entries count as nothing recorded. It is written once, at registration, like the other facts of the case (the database allows only status changes on a case afterwards). The case page shows it in the *About* box: the details, *Unknown*, or *not recorded*. It is not yet part of the signed PDF report.
4. New libraries: `nh3` (backend, cleans the formatted text) and Tiptap and DOMPurify (front end, the editor and the second cleaning).
5. **Tasks are no longer shown anywhere** (the case tab, the *Assigned tasks* page, counters and columns). The backend task code and its data were left in place, so this is reversible; removing it completely would need a migration and is not done.
6. **Past-case comparison from a registered case** uses its own bar, `case_similar_passage_min_similarity` = 0.70 (the whole-document bar stays 0.80): see steps/17-5, item 9.
7. **Officers create their own login** (steps/17-5, item 13): only for an officer in the register with a matching name; it starts as Viewer with public clearance; a Supervisor or Administrator raises role and clearance (migration 0022 adds the clearance change to the access history).
8. **Profile of a login** (steps/17-5, item 14): email, phone and job title, filled in and updated by the person on My profile or at sign-up (migration 0023); official details stay from the register.
