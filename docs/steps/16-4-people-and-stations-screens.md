# Step 16, phase R-4: the People and stations screens, first-login passwords

> **Written before the plain case design (2026-11-10).** Where this note says repository, clone, branch or commit, read *case*: see [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md).

Design: [case-management/12-roles-and-stations.md](../case-management/12-roles-and-stations.md). Built 2026-11-10. The rules are the ones of
[phase R-3](16-3-station-rules-and-accounts.md); here people can use them from the screens.

1. **Where.** Menu *People & stations* (Super Admin, Administrator, Supervisor, Investigator), page `/kh/people`, three tabs: **People**,
   **Register of officers**, **Police stations**. What is offered depends on the role; the backend checks every request again and answers
   "not found" for people and stations you cannot reach.
2. **Police stations (Super Admin).** Open a station (code, name, district) and correct its name or district, or mark it inactive. The code is
   permanent and a station is never deleted. Each station shows its people, officers and cases (open ones in brackets). Others see only their own.
3. **The register of officers (Super Admin enters).** Add an officer (ID, name, rank, station, the highest role an account may have), or import a
   CSV file (`officer_number, full_name, rank, station_code, highest_role`). The import is all or nothing: if any row has a problem nothing is
   entered and every problem is listed with its row. Others see the officers of their own stations.
4. **Accounts.** *Create an account* picks an officer who has no account yet; only the roles the creator may make, and the register allows, are
   offered. The username and name are suggested from the officer; the clearance cannot exceed the creator's own; the station comes from the
   register. An Administrator may be given more stations.
5. **The temporary password.** The server makes a random password (like `bhEY-6aFg-Fcn4-rN9F`) and shows it **once**, to the creator, who hands it
   over in private. It is never stored in clear and never written to the audit log.
6. **First login.** The new person can log in with it, but sees only "Choose your own password" until they do (the server refuses every other
   request meanwhile). Nobody else ever knows the real password. Everyone can change theirs later on the Account page.
7. **Looking after people** (Super Admin, Administrator, Supervisor: only people below their own role, at their own stations): change a role
   (the promotion rule applies: a new role adds no power over cases that already exist), set stations (an Administrator several, everyone else one),
   reset a password (a new temporary one), end an account (someone leaves: they cannot log in, their work stays attributed to them) and restore it.
   Each needs a reason and becomes a permanent record in the access history.
8. **Adding people to a case.** On a case the Investigator uses *Add team member*: Sub Investigators (add and create files, see the files),
   Analysts (analyse data, add findings) and Viewers (read only), only people who work at the case's station. (Formerly "contributors".)
9. **How it was checked.** 8 backend tests through the real login and endpoints (the whole chain, refusals and their audit, the password rules,
   listings and what each person may do, role/station/reset/end, CSV all-or-nothing, stations never deleted, nobody manages a peer or a superior);
   I checked they fail when the first-login lock or the "only below you" rule is removed. A 10-step browser tour (`frontend/e2e/people_tour.py`)
   goes through it as real people: Super Admin to Administrator to Supervisor to Investigator, with first logins, a reset and an ended account.
10. **Still to do.** R-5 dashboards (station, officer, case progress); R-7 demonstration, guides and readiness list; the rest of R-6 (simpler menus and
    "commit" to "update" wording). Not built on purpose: a self-service "forgot my password" (a person above resets it) and e-mail (none exists here).
