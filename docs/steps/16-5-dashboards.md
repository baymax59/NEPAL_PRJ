# Step 16, phase R-5: station and officer dashboards

> **Written before the plain case design (2026-11-10).** Where this note says repository, clone, branch or commit, read *case*: see [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md). The officer figures about reviews became notes written and exhibits added.

Design: [case-management/12-roles-and-stations.md](../case-management/12-roles-and-stations.md) section 7. Built 2026-11-10. Read only: nothing here
changes, deletes or exports anything.

1. **Where.** Menu *Station dashboards* (Super Admin, Administrator, Supervisor) or *My performance* (Investigator). Pages: `/kh/performance` (the stations),
   `/kh/performance/stations/<id>` (one station), `/kh/performance/officers/<id>` (one officer). A Supervisor, or an Administrator with one station, goes
   straight to their station; an Investigator straight to their own page. The Welcome page links to them for the three station roles.
2. **Who sees what.** Super Admin: every station and every officer. Administrator and Supervisor: the stations they are assigned to, and the officers
   **below their own role** who work there, and themselves (not a peer, not someone above). Investigator: only their own page. Sub Investigator,
   Analyst and Viewer: none. Anything outside this answers "not found" (404), exactly like something that does not exist; a role with no dashboards gets
   "forbidden" (403). Every look is in the audit log (`cm.dashboard.stations`, `.station`, `.officer`).
3. **Figures never go beyond what you may open.** Every number is computed over the cases the viewer could open anyway (same station, membership and
   clearance rules as the case lists). Example: an Administrator of station A looking at an officer who also works at B sees only that officer's cases at A;
   a Supervisor with a lower clearance does not count a confidential case in the station's total.
4. **The words** (the screens explain them under each title): *open* = not closed or archived (it includes the two pending groups); *pending* = pending
   evidence or pending review; *closed* = closed or archived; *late task* = still open or in progress after its due date.
5. **A station** shows: open, pending evidence, pending review, closed, new this month, the average days to close (cases now closed, from their first
   closing event; "—" when there are none), the cases open the longest (oldest first), cases by status, opened and closed month by month (six months),
   and each officer below you with their cases (total, open, pending, closed), tasks done and late, reviews approved and sent back, and last activity.
6. **An officer** shows: their cases (led, worked on, or supervised: a case counts once whatever clones or roles they had; work that ended, such as a
   revoked access, stays credited and is marked "no longer on it"), tasks done / open / late, reviews they approved or sent back as reviewer, findings
   they put forward (merged, rejected), updates in the last 30 days, exhibits added, and when they last did something.
7. **How it was checked.** 11 backend tests: every station figure compared with separate database counts (by status, open, closed, pending, new this month),
   the average days to close, the cases open the longest, the month-by-month series, an officer's tasks, reviews, commits and last activity compared with the
   database, an archived case counted as closed, each role's reach (station, rank, peer, above, other station, Investigator only themselves, other roles
   refused), a case a viewer may not open never counted (other station, lower clearance), read only (nothing changes) and audited. I checked that the tests
   fail when I break the viewer's reach, the "officer works at my station" rule, the "late" rule, the "archived counts as closed" rule, or let a Supervisor open a peer.
   5 front-end tests (the screens show the figures in plain words, "—" where nothing can be averaged, late tasks, an ended account, the way back), also checked by breaking them.
   A 7-step browser tour (`frontend/e2e/dashboards_tour.py`): two cases registered and one moved to pending evidence, a second station opened, then the list of
   stations, one station and one officer for the Super Admin (the figures are the ones just made), the Supervisor reaching only their station ("not found" for the other),
   an Investigator only themselves, a Viewer nothing.
8. **Whole-project check after this phase.** 560 backend tests pass (549 before plus these 11), 55 front-end tests pass, and the four browser scripts pass on fresh
   throwaway databases: the walk-through (37 steps), the acceptance scenario (17 steps and 3 live-page checks), the people tour (10) and the dashboards tour (7).
   The real app was rebuilt (no database change: still migration 0018).
9. **Small changes on the way.** The chart panel moved to `src/kh/charts.tsx` (shared with the administration overview); a second chart colour was added for "closed";
   the Welcome page's *Register a case* button now also shows for an Administrator (it was left out in R-4).
10. **Still to do.** R-7 (reload the demonstration, one account per role, update the admin and investigator guides, readiness list, Docker rebuild) and the rest of R-6
   (simpler menus; "commit" to "update" wording on the old screens). Not built on purpose: exporting the figures (a report is the permanent record), a "case process" page
   (the case's own page already shows its status history, updates and reviews), live refresh of these pages.
