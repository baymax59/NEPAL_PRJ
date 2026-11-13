# Step 16, phase R-6 (done early): SHA-256 hidden from the screens

> **Written before the plain case design (2026-11-10).** Where this note says repository, clone, branch or commit, read *case*: see [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md).

Design: [case-management/12-roles-and-stations.md](../case-management/12-roles-and-stations.md) section 9. Built 2026-11-10 at the user's request
("remove SHA-256"; earlier choice: *hide it from the screens, keep checking silently*).

1. **What the user sees now.** No hash, checksum or long code on any screen, form or PDF report. An exhibit shows **"File is original"**
   or **"File was changed"** (and "File missing"); a report check says "Genuine" or "Not recognised".
2. **What did not change.** The system still fingerprints every file when it arrives and re-checks it (the Verify button, the daily check,
   the admin Evidence integrity page). That is what makes tampering detectable. The fingerprints stay in the database and in the API
   answers (programs need them); the screens just never read them for display.
3. **Commits are "Update 14".** A commit used to be shown as a 10-character code. The server now numbers the commits a repository can
   see (1, 2, 3 ... oldest first): `GET /api/v1/repositories/{repo_id}/commit-numbers`. Screens show "Update 14"; the link still opens the commit.
   Numbers are for reading only: commits are still identified by their IDs (in the address of the page and in the API).
4. **Screens changed.** Evidence detail, file explorer (file and version details), commit details, snapshot viewer, upload dialog, imports
   (drawer and list), signed reports list, report preview, verify-a-report page, admin evidence integrity table, admin governance (audit
   checkpoints no longer list hashes or key fingerprints), the case page of the similar-case search (source checksum row), the login page and
   explanatory texts.
5. **PDF reports.** The exhibit table has "File integrity" (Original / CHANGED since it arrived / FILE MISSING, with the date) instead of a
   hash column; notes, imported findings and reviews no longer print hashes; page footers and the lineage table say "Update N". A test
   fails if any 16-character code or the words "SHA-256" appear in a report.
6. **Old reports** already generated keep their original content (they are permanent and verify as before).
7. **Tests.** Backend: the report tests check that the case report and the evidence register contain no codes; new tests check the update
   numbers (consecutive, newest highest, a stranger gets 404) and that no system-written message contains a code. Frontend: the commit label test shows "Update 14" and never the code. Browser scripts were updated to the new wording.
8. **Not done (on purpose).** The checks themselves, the database columns, the audit chain and the signed checkpoints are unchanged; removing
   them would let evidence be swapped without anyone noticing. If you really want the fingerprints gone from the system, say so and I will
   write down what that costs first.
9. **Text the system writes.** Some commit messages and review notes written by the server used to mention a code ("Branch x created from
   c582360566", "cloned from ROOT at 9e8337ea4b", "merged as ..."). New ones are written without codes. Older ones are permanent records
   and stay as stored; what is *shown* passes through `app/casemgmt/plain.py`, which turns a code into "an earlier update" (a 10-digit
   phone number is left alone). The audit log page shows "(recorded)" instead of a code; the custody method "sha256" is shown as
   "automatic file check" on screen and in the PDF register.
10. **Plain words.** Text that still says "commit" in places will become "update" in the wider simplification (phase R-6 of the design).
11. **Go back.** `git revert` of this change; no database change was made.
