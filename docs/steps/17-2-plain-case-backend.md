# Step 17, phase G-3: the plain case design, the rest of the backend

Design: [case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) (section 9 lists the choices made here). Built 2026-11-10, on top of
[17-1](17-1-plain-case-core.md). The live application (Docker) was upgraded to this version on 2026-11-11 (see steps/17-5, item 11).

1. **What moved onto the case.** Everything that G-2 had switched off now works on the case itself, with no repository, clone, branch or commit anywhere: links between cases, reports and
   their PDF, similar-case search, the timeline, offence suggestions, the assistant, the intelligence index, the integrations (outside findings), legal holds and retention, the dashboards
   and officer figures, the administration overview, the live notice stream and the contributions page. Their routers are on again in `app/main.py`.
2. **API changes** (the new `docs/case-management/openapi.json` has 120 paths and no git-style names):
   - Reports: `POST/GET /v1/cases/{id}/reports`, `GET /v1/cases/{id}/report-preview`, `/v1/reports/{id}/download-link`, `/v1/reports/{id}/verify`, `/v1/reports/verify-file`.
   - Links: `POST/GET /v1/cases/{id}/links` (`target_case_id` or `knowledge_case`, `link_type`, `reason`).
   - Intelligence: `/v1/cases/{id}/intelligence/{status,prepare,search,similar,ask,offences,timeline}`; no "as of commit" any more.
   - Integrations: `POST /v1/integrations/add-to-case` takes `case_id`; `/v1/cases/{id}/imports`, `/v1/imports/{artifact}`, `/v1/indicators`.
   - New on the workspace: `/v1/contributions/mine`, `/v1/admin/overview`, `/v1/notifications/stream`.
3. **System folders.** Reports, imported findings, links and the rebuilt timeline each live in a folder the case makes the first time it needs one: *reports*, *imports*, *links*, *timeline*.
   Making one is a `folder_added` history entry marked `system`. A report is the note `RPT-0001` in *reports*; each new report is a new version of it. A finding is the file `IMP-0001` in *imports*.
4. **A report says which entry it describes.** Every report records "as of entry N" (the case as it stood at its latest history entry), shows how many entries were withheld, and is vouched for by a
   `report_generated` history entry holding the report's SHA-256 and `as_of_entry`. Later work is not in an earlier report. A report is never edited (a revision is refused with 422; delete is
   405); to change it, generate a new version.
5. **A report shows only what every member may see.** It is built from the shared view (`shared=True`): sealed notes and exhibits are left out for everyone, including the Supervisor who made it.
   The same holds for the timeline (rebuilt from the shared view, not from the view of whoever pressed the button). Any member who may add files can generate a report (Investigator, Sub
   Investigator, Analyst, and the oversight roles); a Viewer cannot (403); someone outside the case gets 404.
6. **Imported findings.** The same record with the same fingerprint is refused (409). The same record with a changed fingerprint becomes a new version of the same file. A finding sent again after it
   was withdrawn is a new file (`IMP-0002`). Identifiers (phone numbers, accounts and so on) are matched only against cases the reader can open, and a sealed finding in another case never matches
   for someone who doesn't oversee that case.
7. **Search and answers** read the case as it stands now: active files the person may see. Withdrawn files stay in the history only.
8. **Officer figures** (dashboards, contributions) count history entries, notes written and exhibits added, instead of commits and reviews.
9. **Live notices** can watch a case, an exhibit or the admin page, and an exhibit the person may not see is not watched.
10. **How it was checked.** The whole backend suite: 536 tests pass (one run at a time, because the tests share one database). Ported to the case in this phase: `test_cm_governance` (7),
    `test_cm_reports_audit` (6), `test_cm_integrations` (10, rewritten), `test_cm_intelligence` (13, rewritten), `test_cm_plain_words` (2), `test_cm_workspace` (11), `test_cm_dashboards` (11).
    I then broke twelve of the new rules one at a time (a report including what only its maker may see, a Viewer generating a report, the same imported record accepted twice, a withdrawn finding
    re-sent becoming a version of the withdrawn file, identifiers matched in cases the reader can't open, a sealed finding in another case still matching, search reading files the person may not
    see, the timeline built from its builder's view, links showing cases the reader can't open, officer dashboards showing cases the viewer can't open, the live stream watching an exhibit the
    person may not see, a hand-over lead still receiving hold notices). Ten were caught at once; two **survived** (the live stream and the hold notices) because no test looked at them. I added
    a test for each (`test_a_page_the_user_may_not_open_gives_no_activity_at_all` now includes a sealed exhibit watched by the lead; new
    `test_a_legal_hold_is_told_to_the_investigator_leading_the_case_now_...`), and then both breaks were caught as well. Every changed file was restored after each check.
11. **Bug found by the tests on the way:** the custody part of a report crashed when an exhibit's id arrived as text instead of a UUID (`governance/reports.py`, `_custody`); now fixed. Two tests
    were also strengthened afterwards: a report made by a Supervisor must leave out a sealed exhibit, and a Supervisor builds the timeline in the sealed-content test.
12. **Parked until G-4/G-5:** `npm run gen:api` (running it now would break the old screens, so it waits for G-4); all screens; the browser scripts, `tests/test_cm_acceptance.py` (listed in
    `tests/conftest.py` `collect_ignore`), the demo seed scripts, the guides, the live-database migration to 0019 (with a backup first) and the Docker rebuild.
