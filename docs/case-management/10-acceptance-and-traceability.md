# 10. Acceptance and traceability

For the people who accept the system: what the master specification asks for, and where each item is proven or delivered. Every proof below runs by itself; the commands are at the end.

**A note on the design.** The master specification (written 2026-11-07) describes a git-style case: an original repository, clones V1 and V2, branches, commits, reviews and merges. On 2026-11-10 the owner asked for that design to be removed completely and replaced by a plain one ([13-plain-case-design.md](13-plain-case-design.md)): a case has permanent folders made at registration, files (notes with versions, exhibits), a team the Investigator builds directly, tasks, links, reports and **one numbered, tamper-evident history**. This document traces every item of the specification to its equivalent in the plain design, and says where an item no longer applies and why. The earlier traceability (to the git-style tests) is in the Git history of this file (the project's own copy before 2026-11-10 is in `backups/20261110-165956-code-before-plain-case-design.tar.gz`).

The specification's final acceptance scenario (§27) is proven three ways:

- **One automated test**, `backend/tests/test_cm_acceptance.py`. It tells the whole story through the HTTP API, then checks the result again independently, from the database records and the stored files.
- **A browser run**, `frontend/e2e/acceptance.py`. Each step is done on screen by the person the specification names, including three checks that pages update by themselves while other people work.
- **The demonstration case KH-2026-0001** (§23). It is seeded by the same story through the running application, `backend/scripts/demo_case.py`, so seeding is itself a run of the scenario on the real system.

## 1. The final acceptance scenario (§27)

The demonstration story: a "KYC update" phishing case with a reported loss of INR 2,50,000. Investigator 1 is Inspector Arun (the case's lead), Investigator 2 is SI Meena Iyer (a Sub Investigator), Dev Patel is the Analyst, the supervisor is DSP Devika Menon and the administrator is Asha Rao. All five are fictional.

| # | Step (§27, word for word) | In the plain design (the story) | Automated test (`test_cm_acceptance.py`) | Browser (`acceptance.py`) |
|---|---|---|---|---|
| 1 | An administrator creates Case A. | The administrator registers KH-2026-0001 with Inspector Arun as lead, a supervisor and a fictional FIR number | `POST /cases` answers 201 with the lead; the case is found in the database by its number | the administrator fills in "Register a case" |
| 2 | The system permanently registers Case A's original repository. | **The case's permanent record:** the folders of its type (ten for a cyber-fraud case), the summary note, and history entry 1 ("case registered"); the history check says it is intact | the folders listed and the first entry are the registration; `history/check` is intact; from the database: every folder, entry 1 with no predecessor | "10 folders made for you", the folders on the overview, history entry 1, "History is intact" |
| 3 | Investigator 1 receives Clone V1. | **Inspector Arun is the case's lead** and finds it among his cases, with that part | `/cases/mine` lists it with the part `lead`; the team is the lead alone | the case on his dashboard: "You: Investigator (case lead)" |
| 4 | Investigator 1 uploads evidence and creates investigation commits. | A complaint summary, the WhatsApp export, the bank statement (PDF), the suspicious-URL record, the bank's access log and an initial assessment: **each is a numbered entry of the history** | each exhibit's recorded SHA-256 equals the file's own; at least 7 history entries | 3 exhibits and a note added through the screens |
| 5 | Investigator 1 creates a CDR analysis branch. | **Investigator 1 adds a folder** (`telecom-requisitions`) for the requisitions: folders are permanent and the Investigator may add more | the folder is created (201, not a system folder), and holds the requisition note; later refused deletion | "New folder" |
| 6 | Investigator 1 invites Investigator 2 as a contributor. | **Investigator 1 adds SI Meena as a Sub Investigator and Dev Patel as an Analyst: straight in, with no invitation and no approval.** They are told by a notice. A Sub Investigator may not add people | both are on the team at once; the case is among their cases; SI Meena was told (`team.added`); her own attempt to add someone is refused; from the database: the team and who added them | "Add team member" twice; SI Meena and Dev find the case in their own lists with no invitation to accept |
| 7 | Investigator 2 submits findings for review. | **She adds the CDR and the IPDR and a findings note straight into the case** (no review request); the Analyst adds an analysis | the findings are visible to the lead at once; the task assigned to her is done | she adds the CDR; the Analyst adds a note. **Live:** Inspector Arun's open file list shows her exhibit without reloading |
| 8 | The supervisor approves the findings. | The lead puts the case to *Pending review*; the supervisor, who oversees it without being on its team, reads the findings and sets *Approved for reporting*, with a reason | the case's status is `approved_for_reporting` | the status dialogs. **Live:** SI Meena's open case page shows the approval without reloading |
| 9 | An approved merge commit is generated. | **The approval is a numbered, tamper-evident entry of the history**, made by the supervisor, in order | the entries are numbered 1, 2, 3 without gaps; the supervisor's approval is one entry; every entry holds the fingerprint of the one before; `history/check` is intact | "History is intact" after the approval |
| 10 | Investigator 1 discovers an incorrect earlier analytical assumption. | His attribution read the bank's UTC time (05:11) as Indian time and named the wrong subscriber. He records the error as a comment on that note | the comment is saved on the note | the note, then the comment in its panel |
| 11 | Investigator 1 selects a historical commit and creates Clone V2. | **He corrects the note with a new version**, based on the version he read (a stale edit is refused), saying why; the correction names the three exhibits it rests on | version 2 exists with its change note, its author and its sources; version 1 is unchanged (from the database) | "New version". **Live:** the administrator's open page of the case shows the correction in its history without reloading |
| 12 | V2 becomes the investigator's active case. | The case goes on: the corrected note is the current version; the case goes on; 3 corroborating findings from the fictional test source are added | the note's current version is 2; three findings were imported | the case among his cases; the new version and a new task |
| 13 | V1 remains preserved and unchanged. | **Version 1 of the wrong note stays**, word for word, as the record of the error; and so does everything written before | version 1's text has the same fingerprint before and after; the history entries written before the correction are identical; the history is intact | the administrator opens the note: version 2 of 2, the wrong attribution still readable, "History is intact" |
| 14 | The administrator can see the original, V1, V2, every commit, all contributors, and all associated history. | The administrator sees **every file and version, the whole team, every history entry, the access history and the audit trail** of the case | the files (withdrawn ones too), the team, the registry listing with its counts, the access history, the audit trail | the case's History, Access history and Audit trail tabs, and its Team |
| 15 | Evidence integrity checks succeed. | All 6 exhibits re-hashed | every check answers `match`; each stored file re-hashed by the test equals its recorded SHA-256; custody is complete | "Verify integrity now": File is original (3 exhibits) |
| 16 | An attempted deletion or destructive history rewrite is rejected and audited. | 6 attempts: delete the case, an exhibit, a folder, a history entry; rewrite an entry; replace an old note version. Plus an edit based on an old version | all 6 answer 405 and are recorded (five against the case or the exhibit, one against the endpoint); the stale edit answers 409; the audit hash chain still verifies; the "refused" view of the trail lists them | `DELETE` a case and `PATCH` a history entry from the browser answer 405; both are in the trail's "Refused and denied" view |
| 17 | The system generates a case report with provenance and integrity information. | RPT-0001 "as of entry N", signed, downloaded and checked | the download's SHA-256 equals the recorded one; the check answers `match`; the PDF's text holds the case, "as of entry N", every exhibit with the result of its check, no fingerprint and no git words, and the reminder that it is not automatically admissible in court | "Generate a signed PDF", download, "Check a report file": Genuine, "the case as of Entry N" |

## 2. The required automated tests (§24)

| Requirement | Proven by (file :: test) |
|---|---|
| **Case creation** | |
| A root repository is created | *(plain design)* the case's folders are made at registration: `test_cm_plain_case` :: `test_registering_a_case_makes_its_folders_at_once`; `test_cm_cases` :: `test_a_new_case_gets_its_folders_a_lead_a_summary_and_a_first_history_entry` |
| An initial commit exists | the first history entry: the same tests; `test_cm_acceptance` step 2 |
| The assigned investigator receives an active working clone | the lead is on the team and finds the case in My cases: `test_cm_cases` (same test); `test_cm_acceptance` step 3 |
| The root remains intact | the registration records (the summary note) can't be revised or withdrawn: `test_cm_plain_case` :: `test_what_each_part_may_do_with_notes`, `test_a_withdrawn_file_leaves_the_current_view_and_stays_in_the_history`; the case, its folders and its history can't be deleted: `test_cm_access_permanence` :: `test_deleting_or_rewriting_history_is_refused_and_audited` |
| **Cloning** | *Not applicable: the plain design has no clones.* The needs behind them are met differently: |
| A clone can be created from a historical commit | a mistake is corrected with a **new version** of the note, the old one kept: `test_cm_plain_case` :: `test_a_revised_note_keeps_its_old_version_and_refuses_a_stale_edit`; `test_cm_acceptance` steps 11 and 13 |
| The source commit belongs to authorized history | a new version names the version it was based on: same test |
| Clone metadata preserves its parent | a new version records the version it replaces and the files it rests on (`derived_from`): `test_notes_name_the_files_they_are_based_on`; `test_cm_acceptance` (from the database rows) |
| Previous clones remain unchanged | earlier versions and earlier history entries stay as written: `test_cm_acceptance` step 13; `test_cm_plain_case` :: `test_the_history_is_one_chain_that_can_be_checked` |
| The new active clone appears correctly | the current version is the newest: `test_cm_acceptance` step 12 |
| **Evidence integrity** | |
| Uploaded evidence receives a SHA-256 hash | `test_cm_evidence` :: `test_adding_evidence_hashes_stores_and_records_it` |
| Historical evidence versions cannot be overwritten | `test_cm_evidence` :: `test_evidence_never_changes_corrections_are_derived_notes`, `test_the_store_never_overwrites_or_keeps_refused_uploads`, `test_the_database_itself_refuses_to_change_evidence` |
| Tampered evidence fails integrity verification | `test_cm_custody_integrity` :: `test_verification_detects_a_tampered_file` |
| Chain-of-custody events remain complete | `test_cm_custody_integrity` :: `test_a_transfer_is_complete_only_when_the_receiver_acknowledges`, `test_a_download_link_works_once_for_its_user_and_is_a_custody_event`; `test_cm_acceptance` (every exhibit's custody) |
| **Authorization** | |
| Investigators cannot access unauthorized cases | `test_cm_access_permanence` :: `test_people_outside_a_case_get_404_exactly_like_for_a_missing_one`; `test_cm_stations_roles` :: `test_each_role_sees_its_stations_and_nothing_across` |
| Investigators cannot enumerate admin-only clones | *(plain design)* nobody can list cases they may not open: the same tests; the administrator's registry refuses supervisors (403) and the admin overview refuses leads (403): `test_cm_access_permanence` :: `test_the_admin_sees_every_case_with_its_team_and_history`, `test_cm_workspace` :: `test_my_contributions_and_the_admin_overview` |
| Contributors cannot grant themselves new privileges | `test_cm_access_permanence` :: `test_team_members_cannot_grant_themselves_privileges`; `test_cm_plain_case` :: `test_the_investigator_adds_a_sub_investigator_and_an_analyst_directly`, `test_who_can_be_added_and_in_which_part`; `test_cm_acceptance` step 6 (a Sub Investigator's attempt to add someone is refused) |
| Cross-tenant access is denied | `test_cm_access_permanence` :: `test_other_organisations_and_lower_clearances_see_nothing` |
| Revoked contributors lose current access | `test_cm_plain_case` :: `test_removing_someone_keeps_what_they_did` |
| Administrators cannot bypass independent storage protection merely through the application | `test_cm_evidence` :: `test_the_store_never_overwrites_or_keeps_refused_uploads`; `test_cm_access_permanence` :: `test_the_database_itself_refuses_to_change_or_delete_the_record`, `test_the_database_allows_only_the_changes_a_record_is_meant_to_have`; `test_cm_governance` :: `test_the_runtime_role_can_not_delete_case_records_nor_edit_permanent_ones`, `test_the_whole_module_works_under_the_runtime_role`. True write-once hardware or object-lock storage is your organisation's decision D14 (document 11) |
| **History** | |
| Historical commits remain accessible to authorized reviewers | the whole history is listed to everyone on the case, and to the administrator: `test_cm_plain_case` :: `test_the_history_is_one_chain_that_can_be_checked`; `test_cm_access_permanence` :: `test_the_admin_sees_every_case_with_its_team_and_history` |
| Normal user operations cannot rewrite existing commits | `test_cm_access_permanence` :: `test_deleting_or_rewriting_history_is_refused_and_audited`, `test_the_database_itself_refuses_to_change_or_delete_the_record`; `test_cm_plain_case` :: `test_the_history_is_one_chain_that_can_be_checked` (an entry changed, with its fingerprint recomputed, or taken out, is found by the check) |
| Branch merges create valid parent relationships | *Not applicable: no branches or merges.* Every history entry holds the fingerprint of the one before: the same test; `test_cm_acceptance` (the chain, from the rows) |
| Concurrent writes cannot silently overwrite each other | `test_cm_plain_case` :: `test_a_revised_note_keeps_its_old_version_and_refuses_a_stale_edit`; `test_cm_acceptance` step 16 (a stale edit answers 409) |
| **No deletion** | |
| Case, clone and commit deletion are unavailable | `test_cm_access_permanence` :: `test_deleting_or_rewriting_history_is_refused_and_audited`; `test_cm_acceptance` step 16 |
| Evidence deletion is unavailable | `test_cm_evidence` :: `test_deleting_or_overwriting_evidence_is_refused_and_audited` |
| Destructive operations are rejected and audited | the tests above; `test_cm_acceptance` step 16 (each attempt in the audit log, against its target) |
| **Admin visibility** | |
| Every created repository is present in the administrative registry | *(plain design)* every case: `test_cm_access_permanence` :: `test_the_admin_sees_every_case_with_its_team_and_history` |
| Original, V1, V2, and their relationships display correctly | *(plain design)* the case, its files and versions, its team and its history display correctly: the same test; `test_cm_acceptance` step 14; browser step 14 |
| Clone lineage can be reconstructed from database records | *(plain design)* the whole history, team and note versions are rebuilt from the tables, and the chain is re-checked: `test_cm_acceptance` :: `test_the_final_acceptance_scenario_works_end_to_end` |

Beyond the list: tests for the reports and the hash-chained audit trail (`test_cm_reports_audit`), governance (`test_cm_governance`), integrations (`test_cm_integrations`), Case Intelligence (`test_cm_intelligence`), live pages (`test_cm_workspace`), the plain words the system writes (`test_cm_plain_words`), the dashboards (`test_cm_dashboards`), stations and roles (`test_cm_stations_roles`) and the demonstration seed's safety rules (`test_cm_acceptance`).

## 3. The working demo data (§23)

| Requirement | Where |
|---|---|
| Case family KH-2026-0001, "Online Banking Fraud Investigation" | `scripts/demo/story.py` (`TITLE`); the seed checks the number will be 0001 |
| Reported loss INR 250000 | the case description and the complaint summary note |
| Original repository KH-2026-0001-ROOT | *(plain design)* the case's permanent record: its ten folders, its summary note and history entry 1, made by the system with the case (step 2) |
| Assigned investigator "Inspector Arun" | the fictional account `demo.arun`, the case's lead |
| Initial clone KH-2026-0001-V1 | *(plain design)* Inspector Arun on the team as lead (step 3) |
| Fictional evidence: WhatsApp fraud message, bank transaction statement, suspicious URL, network log, CDR analysis, IPDR analysis, investigation notes | `scripts/demo/files.py`: six files, byte for byte the same every time (the PDF too), and the notes the story writes |
| At least four commits in V1 | six exhibits and six notes written by the team, each a numbered entry of the history |
| An incorrect analytical finding in a note, then V2 from an earlier valid commit | the attribution note (UTC read as IST), then its **version 2**; version 1 stays |
| V1 permanently stored; V2 the active workspace | steps 12 and 13 |
| A second investigator as contributor; a CDR branch; a review request; approval by the supervisor; a merge commit | SI Meena as a Sub Investigator and Dev as an Analyst, added straight in; the CDR and IPDR in their own folders; the supervisor's approval as a history entry; steps 5 to 9 |
| The admin lineage graph shows V1 and V2 alongside the original | Administration → All cases → KH-2026-0001: its whole history, access history and audit trail (screenshots in the administrator's guide) |
| All demo data fictional | reserved values only: documentation IP addresses (RFC 5737), `.example` domains (RFC 2606), the test mobile network 001-01, test IMEIs, invented names, bank, accounts, FIR and requisition numbers. `test_the_demonstration_data_is_fictional_and_stable` checks the files |

## 4. The required deliverables (§26)

| # | Deliverable | Where |
|---|---|---|
| 1 | High-Level Design | [13-plain-case-design.md](13-plain-case-design.md) (current); [03-high-level-design.md](03-high-level-design.md) (the earlier git-style design) |
| 2 | Low-Level Design | [13-plain-case-design.md](13-plain-case-design.md) section 4; [04-low-level-design.md](04-low-level-design.md) (earlier) |
| 3 | Database ER diagram | [13-plain-case-design.md](13-plain-case-design.md) section 4 (tables changed by migration 0019); [05-database-er.md](05-database-er.md) (earlier) |
| 4 | API contracts and OpenAPI specification | [06-api-contracts.md](06-api-contracts.md), [openapi.json](openapi.json), [09-integration-contract.md](09-integration-contract.md) |
| 5 | Complete backend source code | `backend/app/casemgmt/` (plus `app/auth/`), `backend/scripts/` |
| 6 | Complete frontend source code | `frontend/src/kh/` |
| 7 | Database migrations | `backend/alembic/versions/0007` to `0019` (0019 is the plain case design) |
| 8 | Evidence storage configuration | decision D14 in [../DECISIONS.md](../DECISIONS.md), [../steps/15-2-evidence.md](../steps/15-2-evidence.md), `EVIDENCE_DIR` in `.env.example`, the `appdata` volume in `docker-compose.yml` |
| 9 | Authentication and authorization system | `backend/app/auth/` (passwords, tokens, two-step verification), `backend/app/casemgmt/access.py`, [07-security-and-integrity.md](07-security-and-integrity.md) |
| 10 | Working GitHub-style repository interface | **replaced by the case page** (nine tabs: Overview, Files, Team, Tasks, History, Links, Reports, Insights, Imports): `frontend/src/kh/case/`, [../steps/17-3-plain-case-screens.md](../steps/17-3-plain-case-screens.md) |
| 11 | Clone lineage visualization | *Not applicable (no clones).* The case's numbered **History** tab, its **Check the history** button, and the **relationship graph of linked cases** (`frontend/src/kh/case/LinksTab.tsx`, React Flow) take its place |
| 12 | Example seeded cases | `backend/scripts/demo_case.py` (KH-2026-0001); `backend/scripts/e2e_prepare.py` (fictional accounts and past cases for tests) |
| 13 | Automated tests | `backend/tests/` (the `test_cm_*` files are Case Management), `frontend/src/**/*.test.tsx`, `frontend/e2e/` (walk-through, acceptance run, demonstration tour, people and dashboards tours) |
| 14 | Docker development setup | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/` |
| 15 | Environment configuration examples | `.env.example` |
| 16 | Installation instructions | the root `README.md` (Quick start), [../steps/14-1-docker-full-stack.md](../steps/14-1-docker-full-stack.md), [../steps/14-5-deployment-and-handover.md](../steps/14-5-deployment-and-handover.md) |
| 17 | Administrator user guide | [../guides/administrator-guide.md](../guides/administrator-guide.md) |
| 18 | Investigator user guide | [../guides/investigator-guide.md](../guides/investigator-guide.md) |
| 19 | Security and integrity design documentation | [07-security-and-integrity.md](07-security-and-integrity.md), [../SECURITY_REVIEW.md](../SECURITY_REVIEW.md) |
| 20 | Known limitations and production-readiness checklist | [11-production-readiness.md](11-production-readiness.md), `python -m scripts.readiness_check` |

## 5. Running every proof

```powershell
cd C:\case-search\backend
uv run pytest tests/test_cm_acceptance.py -q          # the 17 steps, end to end, plus the seed's safety rules
uv run pytest -q                                      # every backend test (one run at a time: they share one test database)
cd ..\frontend; npm test                              # every frontend test

# The browser runs (a throwaway database; see docs/steps/15-4-screens.md for starting the API and web app)
cd ..\backend; uv run python -m scripts.e2e_prepare
uv run --with playwright python ..\frontend\e2e\acceptance.py --url http://127.0.0.1:5180 --shots $env:TEMP\kh-acceptance
uv run --with playwright python ..\frontend\e2e\walkthrough.py --url http://127.0.0.1:5180 --shots $env:TEMP\kh-walkthrough
```
