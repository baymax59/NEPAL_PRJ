# 12. Police stations, the seven roles, and a simpler design

Status: **design written 2026-11-10; R-2 (database and role names), the hiding of SHA-256 (part of R-6) and R-3 (station rules, accounts, promotions) and R-4 (the screens and endpoints for people, officers and stations, first-login passwords) and R-5 (station and officer dashboards) built 2026-11-10; R-7 and the rest of R-6 not built yet.** Requested by the user on 2026-11-10. Where the request was
silent, the choice made here is marked **(assumption)** so it can be corrected before building.

> **2026-11-10:** the git-style case design (repositories, V1/V2 clones, branches, commits, merge reviews) is being replaced by the plain case design in [13-plain-case-design.md](13-plain-case-design.md). Where this document speaks of repositories, branches, commits, invitations or reviews, read it as superseded by 13.

## 1. What changes, in one page

| Today | New |
|---|---|
| One organisation, no police stations | The organisation has **police stations**; every case and every officer belongs to a station |
| 5 organisation roles (platform admin, supervisor, investigator, analyst, viewer) + 4 case roles | **7 roles**: Super Admin, Administrator, Supervisor, Investigator, Sub Investigator, Analyst, Viewer |
| Anyone with the role sees the whole organisation | What you see depends on your **station scope** (all / assigned stations / one station / own cases) |
| Accounts made by a command-line script | Accounts made **from the screens by the person above you**, and only for a real officer ID |
| SHA-256 codes shown on screens | **Hidden.** Users see "File is original ✓". The system still checks in the background |
| 14 admin menu items, 12 case tabs | Fewer, plainer screens (section 8) |

Nothing is ever deleted. Every rule below only adds or limits who may *see* or *add*.

## 2. The seven roles

| # | Role | Sees | Made by | Station scope |
|---|---|---|---|---|
| 1 | **Super Admin** | Every case, every station, every officer's reports, progress, performance, closed and pending cases | Created at installation (the first account) | All stations |
| 2 | **Administrator** | Same as Super Admin, but only for the stations the Super Admin gave them | Super Admin (who picks the stations) | Several assigned stations |
| 3 | **Supervisor** | Same as Administrator, for a single station | Administrator (who picks the station) | One station |
| 4 | **Investigator** | Their own cases, their own progress and their older records | Supervisor, or another Investigator of the same station | One station |
| 5 | **Sub Investigator** | Only the cases they are added to | Added to a case by the Supervisor or the case's Investigator | The case |
| 6 | **Analyst** | Only the cases they are added to | Added to a case by the case's Investigator (or the Supervisor) | The case |
| 7 | **Viewer** | Read only | **(assumption)** Added per case, or per station for an auditor, by the Supervisor or higher | As granted |

Rules that apply to all seven:

- **Nobody can delete anything**, including the Super Admin. (Already true: the database has no delete rights.)
- **The Super Admin has full control** — creates cases for any station, reads the documents of any case, creates Administrators.
- **Separate view and login area for the Super Admin** (answered by the user): one extra area in the app (`/kh/super`) and its own
  database login with rights across all stations. It is the same single database, not a second one.
- **Each person can create only the roles directly below** them: Super Admin → Administrator → Supervisor → Investigator.
  An Investigator may also create another Investigator of their own station. Nobody can create a role above or equal to their own,
  except Investigator → Investigator.
- **An account is made only if the officer ID matches the ID in the database** (section 4).

## 3. What each role may do on a case

| Action | Super Admin | Administrator | Supervisor | Investigator | Sub Investigator | Analyst | Viewer |
|---|---|---|---|---|---|---|---|
| Create a case | any station | own stations | own station | own station | – | – | – |
| Open / read a case | all | own stations | own station | own cases | cases added to | cases added to | as granted |
| See the case documents | all | own stations | own station | own cases | cases added to | cases added to | as granted |
| Add and create files | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ (in its folder) | – |
| See files the Investigator uploaded | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Add a Sub Investigator to a case | – | – | ✔ | ✔ | – | – | – |
| Add an Analyst to a case | – | – | ✔ | ✔ | – | – | – |
| Review, approve, merge findings | – | – | ✔ | – | – | – | – |
| Station and officer dashboards | all | own stations | own station | own only | – | – | – |
| Delete anything | never | never | never | never | never | never | never |

Sub Investigator = "helps the Investigator solve the case": add a file, create a file, see the Investigator's files.
Analyst = "analyses the data and adds the result to the folder". (Both map to the existing case roles: Sub Investigator =
`contributor`, Analyst = `analyst`; the Investigator on a case = `lead`.)

## 4. The officer ID rule

New table **`officer_registry`** (the list of real officers): officer ID, name, rank, station. The Super Admin loads it
(one by one or by CSV import; the existing police-records connector can feed it).

- Creating an account asks for the **officer ID**. If the ID is not in the registry, or already belongs to another account,
  the account is **refused** and the refusal is written to the audit log.
- The role the account may get is limited by the rank-to-role table in the registry (e.g. a Constable cannot be made Supervisor).
  **(assumption: the registry has a "highest role" column; the person creating the account picks a role up to that.)**
- Station comes from the registry row; it can't be typed freely.

## 5. Promotions never change old cases

Rule: **a promotion adds no power over cases that already exist.**

- Every case membership stores the role the person had **on that case** (`repository_members.role`). A promotion changes the
  account's role going forward; it does not rewrite memberships, commits or audit events.
- A write is allowed only through the case membership. A promoted Investigator who becomes Supervisor can **see** their new
  station's cases, but on cases created before the promotion they get no new right to **change** anything.
- The promotion itself is a permanent event (`authorization_events`: old role, new role, who, when), so history can always show
  what the person was at the time of each action.

## 6. Database changes (migration 0016, additive)

| New / changed | Purpose |
|---|---|
| `police_stations` (id, organization_id, code, name, district, created_by, created_at) | The stations. Never deleted; may be marked inactive |
| `user_stations` (user_id, station_id, assigned_by, assigned_at, revoked_at) | Which stations a user may see (Super Admin: none needed = all; Administrator: several; Supervisor / Investigator: one) |
| `officer_registry` (officer_id, name, rank, station_id, highest_role, user_id, created_at) | Section 4 |
| `users.officer_id` (FK to the registry, unique) | Links an account to a real officer |
| `case_families.station_id` | Station that owns the case; set once at creation |
| `OrgRole` has the seven roles: `super_admin`, `administrator`, `supervisor`, `investigator`, `sub_investigator`, `analyst`, `viewer`. The old `platform_admin` is renamed **`super_admin`** | Seven roles |
| `MemberRole` is unchanged (`lead`, `contributor`, `analyst`, `viewer`); screens show `lead` as "Investigator (case lead)" and `contributor` as "Sub Investigator" | Memberships are permanent records, so their stored value is not rewritten |

**Changed from the first draft (decided while building R-2):**
- Existing platform admins become **Super Admin**, not Administrator. They already see the whole organisation, and without one Super
  Admin nobody could create stations or Administrators. This answers open question 4 in a way that loses no access.
- `contributor` keeps its stored name instead of being renamed to `sub_investigator` (see above).
- `officer_registry` has no `user_id`; the link is `users.officer_id` (one officer, one account).

Existing cases (the three created by the user and the demonstration case) are put into a default station, **HQ**, by the
migration, so nothing is lost. Docker must be rebuilt after the migration (project rule).

Care points found while reading the code:
- `case_families` has a trigger that allows only status changes. The new `station_id` must be added to the "set once" columns.
- `access.py` holds all case-visibility rules as SQL conditions; the station scope is added there (one place), so every query
  inherits it. The rule "something you may not see answers 404" stays.
- Role names are checked by database CHECK constraints (`in_check`); the migration must replace them.

## 7. Dashboards for Super Admin, Administrator, Supervisor

All figures come from data that already exists; nothing new to record.

- **Per station:** cases open / closed / pending review / pending evidence, new this month, average days to close, oldest open case.
- **Per officer:** their cases by status, reviews approved vs sent back, tasks done vs late, last activity.
- **A case's process:** its status history, commits, review requests (the existing timeline).
- Scope follows the role: Super Admin all stations, Administrator assigned stations, Supervisor one station, Investigator only themselves.
- Read only. No export button removes or alters anything; reports stay permanent.

**Decisions made while building R-5:**
- "Pending" is the user's word and the status names are used: *pending* = pending evidence or pending review; *closed* = closed or archived;
  *open* = everything else (it includes the pending ones).
- An Administrator or Supervisor sees the officers **below** their role who work at their station, and themselves; never a peer or someone above. A Super Admin sees everyone. An Investigator only themselves.
- An officer's "cases" are the cases they lead, work on or supervise, counted once each; work that ended (access revoked) stays credited ("no longer on it").
- The "case process" part is the case's own page (status history, updates, reviews); no separate page was added.
- Figures are never exported from here (a report is the permanent record).

## 8. Making the design simpler

Principle: show people only what their role uses; keep the powerful, technical screens one click deeper.

- **Admin menu 14 → 6:** Overview · Cases · Stations & Officers · Reviews · Audit · Settings. (Repository registry, clone lineage,
  evidence registry, contributors, compliance, reports, access policies move inside Cases / Settings as tabs.)
- **Case tabs 12 → 7:** Overview · Files · Branches · History · People · Tasks · Reviews. (Commits and History merge; Graph, Reports,
  Intelligence and Imports become sections inside these.)
- **Plain words:** "Clone Investigation" → "Start a corrected version from here"; "Commit" → "Saved update"; "Branch" → "Line of enquiry".
  The technical names stay in the API and in the audit log.
- **One place to add people:** a single "People" tab for Sub Investigators and Analysts.

## 9. SHA-256 hidden from the screens (answered by the user; **built 2026-11-10**, see [steps/16-2-hide-sha256.md](../steps/16-2-hide-sha256.md))

- **Hidden:** no hash, checksum or long hex code on any screen, in the PDF reports, or in the file-upload form. Commits are shown as
  "Update 14" (numbered by the server: `GET /repositories/{id}/commit-numbers`); the long ID stays in the API and in page addresses.
- **Kept silently:** the system still fingerprints every file on upload and re-checks it. The user sees only
  **"File is original"** or **"File was changed"**, and the "Verify" button.
- **API:** the `sha256` fields stay in the responses (programs need them to check files); screens never read them for display.
- **Why not remove it entirely:** the fingerprint is what makes tampering with evidence detectable; the signed audit chain and the
  report check are built on it. The user chose "hide, don't remove".

## 10. Build order

| Phase | Content | Test that it works |
|---|---|---|
| **R-1** | This document | Reviewed by the user |
| **R-2** | Migration 0016: stations, user_stations, officer_registry, role enums, default HQ station | Migration up and down on the test database; old cases keep their data |
| **R-3** (**done 2026-11-10**, see [steps/16-3](../steps/16-3-station-rules-and-accounts.md)) | Station scope in `access.py`; the seven roles' rules; who may create whom; officer-ID check; promotion rule | New tests: each role sees only its stations; cross-station is 404; promotion gives no write on old cases |
| **R-4** (**done 2026-11-10**, see [steps/16-4](../steps/16-4-people-and-stations-screens.md)) | Account creation from the screens (create Administrator / Supervisor / Investigator, assign stations, add Sub Investigator and Analyst to a case) | Browser walk-through per role |
| **R-5** (**done 2026-11-10**, see [steps/16-5](../steps/16-5-dashboards.md)) | Dashboards (station, officer, case process) | Figures equal the database counts |
| **R-6** | Hide SHA-256 (**done 2026-11-10**); simpler menus and plain words | Search of every screen and PDF finds no hash; integrity tick still works |
| **R-7** | Update the demonstration (stations, one account per role), guides, readiness list, Docker rebuild | All existing tests pass, plus the new ones |

**Decisions made while building R-3** (they follow the wording of the request; say if one is wrong):
- A **Supervisor sees every case of their station** (as the request says: "just like Administrator, but a single station"); only the
  *assigned* Supervisor of a case approves, seals or clones it. Seeing is wider than doing.
- Super Admin and Administrator keep overseeing powers (clone, approve, seal, status), but only over cases registered after their role
  took effect (the promotion rule). The first Super Admin accounts were never promoted, so they are unaffected.
- A Super Admin may promote (never create) a Supervisor to Administrator: role changes work on anyone below the actor's own rank.
- The Viewer cannot be created by an Investigator; a Supervisor or above can.

**Decisions made while building R-4:**
- The creator never knows a new person's password: a random temporary one is shown once, and its owner must replace it at the first login
  (migration 0018: `users.must_change_password`; while it is set the server answers only "who am I" and "change my password").
- Resets, endings and restorations of accounts are permanent records in the access history, like role and station changes.
- Only the Super Admin enters officers and opens stations. There is no "forgot my password" by e-mail; a person above resets it.

## 11. Questions still open

1. **Viewer:** the request gave no description. Assumed read-only, added per case or per station. Correct?
2. **Rank → highest role** in the officer registry (section 4): is a rank table available, or should the person creating the account decide?
3. **Case "closed" and "pending"** wording for the dashboards: use the existing workflow states (Closed / Archived = closed; Pending Evidence,
   Pending Review = pending), unless the force uses other words.
4. **Existing accounts:** the demonstration accounts and the user's own accounts are moved to the HQ station with their current roles
   (platform admin → Administrator). Is that acceptable?
