# Step 16, phase R-3: station rules, who creates whom, the officer register, promotions

> **Written before the plain case design (2026-11-10).** Where this note says repository, clone, branch or commit, read *case*: see [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md).

Design: [case-management/12-roles-and-stations.md](../case-management/12-roles-and-stations.md). Built 2026-11-10. Phase R-4 adds the screens
and endpoints for the account rules below; here they are rules in the backend, proved by tests.

1. **What each role sees now.**
   - *Super Admin*: every case of the organisation.
   - *Administrator*: every case of the stations they were given.
   - *Supervisor*: every case of their one station (and any case assigned to them).
   - *Investigator*: the cases they are a member of (their own).
   - *Sub Investigator, Analyst, Viewer*: only the cases they were added to.
   Anything outside answers "not found", exactly as for a case that doesn't exist (a 404, never "forbidden").
2. **Where a case is registered.** Every case belongs to one station, set at creation and never changed. A Super Admin may choose any
   station; an Administrator one of theirs (they must say which if they have several); a Supervisor or Investigator their own. The
   case's lead and supervisor must work at that station. A new endpoint `GET /api/v1/stations` lists the stations a person may use;
   the Register-a-case screen shows a station choice only when there is more than one.
3. **Who may be added to a case.** Only people who work at the case's station (a Super Admin anywhere). The "find colleagues" search
   offers only those people.
4. **Who creates whom.** Super Admin makes Administrators; an Administrator makes Supervisors (at one of the Administrator's
   stations); a Supervisor makes Investigators, Sub Investigators, Analysts and Viewers at their station; an Investigator makes
   Investigators, Sub Investigators and Analysts at their station. Never a role above your own; never a second Super Admin.
5. **The officer register.** An account is made only for an officer in `officer_registry`: the ID must exist, belong to nobody else,
   and the role may not be above the highest role the register allows for that officer. The station comes from the register, not
   from what is typed. Only the Super Admin enters officers. A creator cannot give an account a clearance above their own.
6. **Role changes.** A Super Admin, Administrator or Supervisor can move people between roles below their own, within their reach
   and within the register's limit. Nobody changes their own role. Every account, role change and station change is a permanent
   record in the access history (`authorization_events`; migration 0017 added the new kinds).
7. **Stations given to people.** The Super Admin gives an Administrator one or more stations; an Administrator places Supervisors and
   others (exactly one station each) inside the Administrator's own stations. An ended assignment is revoked, never deleted.
8. **Promotions add no power over existing cases.** The moment a role took effect is kept (`users.org_role_since`). Powers that come from
   the role itself (overseeing: cloning, approving, sealing, changing a case's status) reach only cases registered after that moment.
   *Seeing* is not affected, and a case a person is assigned to as its supervisor stays theirs. History is not rewritten.
9. **How it was checked.** 13 new tests (`tests/test_cm_stations_roles.py`) cover every rule above, and I confirmed they can fail:
   switching off the promotion rule or the station scope makes them fail. All earlier tests still pass.
10. **What comes next.** R-4: endpoints and screens to enter officers, create accounts, give stations, promote, and add Sub Investigators
    and Analysts to a case. `scripts/create_user.py` still makes the first accounts (`--station CODE` is new; `--set-org-role` now
    counts as a promotion and is recorded).
