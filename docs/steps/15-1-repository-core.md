# Step 15.1: Case Management repository core (phase CM-1)

> **Partly superseded (2026-11-10).** This note is entirely about the repository engine (repositories, clones, branches, commits, snapshots). The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md). What replaced it: [17-1](17-1-plain-case-core.md).

Status: **done and verified** (2026-11-07). 376 backend tests pass (51 new). This phase is the **API only**: the screens come in phase CM-4. All test data is fictional. **Nothing was created in the development database**, because case history there can never be removed (that is the point of the module), and the demo case number `KH-2026-0001` is kept free for phase CM-8.

Part 1 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)).

## 1. What this phase does

A police case is managed like a GitHub repository, and **nothing is ever deleted**.

| Idea | In plain words | How it is built |
|---|---|---|
| **Case family** | One investigation for its whole life, e.g. `KH-2026-0001`. Any type of case | `case_families`; the number is per organisation and year; FIR and other official numbers are stored separately and never used as the key |
| **ROOT** | The permanent original record, made when the case is registered | version 0; it receives **one** commit (the case information) and is then **frozen for good** |
| **Clones V1, V2…** | Working copies investigators use | the first clone (V1) is made automatically for the lead investigator |
| **Commit** | A saved change, with author, time and message | its ID is the **SHA-256 of its content**, made on the server. Anyone can recompute it to check nothing changed |
| **Snapshot** | The complete content at a commit | stored **once** and shared: a clone or a new branch copies nothing |
| **Versions** | Editing a note makes a new version; the old one stays | `artifacts` + `artifact_versions` |
| **Withdrawn** | "This was wrong" | the entry is marked withdrawn **with a reason** in a new commit; older commits still show it |
| **Branch** | A line of enquiry, e.g. `cdr-analysis` | starts at a commit; its head **only moves forward**; `main` is protected |
| **Clone from history** | Restart from an earlier point when an assumption was wrong | the new clone starts **at any commit of its history**; the old clone is kept unchanged and marked **superseded** |
| **Active workspace** | Each investigator sees only their current clone of a case | moves to the new clone when they re-clone |
| **Lineage** | Where every clone came from | administrators see every repository, branch, commit and contributor |

## 2. Why it is needed

It is the foundation of the module: evidence (CM-2), reviews and merges (CM-3), the screens (CM-4) and Case Intelligence inside cases (CM-5) are all built on repositories, commits and snapshots. It implements rules 1–10 of the specification: the case is a repository, ROOT is permanent, investigators work in clones, a clone can start from a historical commit with a mandatory reason, only the active clone is shown, the administrator sees everything, branches are not files, no destructive version-control actions, and closing is not deleting.

## 3. Files created or changed

```
backend/app/casemgmt/
├─ enums.py          fixed value lists (roles, statuses, change types…)
├─ hashing.py        canonical JSON, SHA-256 of snapshots and commits
├─ case_types.py     10 case types with folder templates and branch types; any other type is accepted too
├─ models.py         16 tables (see docs/case-management/05)
├─ errors.py         404 / 403 / 409 / 422 errors
├─ access.py         who may see and do what: conditions inside the SQL of every query
├─ engine.py         creating cases, commits, branches, clones; history, compare; statuses
├─ queries.py        read-only views: case lists, workspaces, repository pages, lineage, admin registry
├─ schemas.py        request and response shapes
└─ api.py            27 endpoints under /api/v1, plus the 405 answer to deletions and rewrites
backend/alembic/versions/0007_case_management_core.py   the tables, 20 database rules (triggers), the placeholder organisation
backend/app/db/models.py      users: organisation + Case Management role
backend/app/auth/users.py     create_user: Case Management role and organisation
backend/app/main.py           the module's router and error handler
backend/scripts/create_user.py   --org-role (new users), --set-org-role ... --by (existing users, audited)
backend/app/casemgmt/organisations.py, scripts/organisation.py   the organisation's name and case-number prefix (D13)
backend/alembic/versions/0008_organisation_prefix_until_first_case.py   the prefix may change only until the first case
backend/tests/test_cm_cases.py, test_cm_history.py, test_cm_clones_access.py, test_cm_organisation.py   51 tests
backend/tests/cm_support.py, conftest.py (cm_user, cm_client)                     test helpers
```

## 4. Packages

None new.

## 5. Commands

```powershell
cd backend
uv run alembic upgrade head          # adds the Case Management tables (already done on this computer)
uv run pytest tests/test_cm_cases.py tests/test_cm_history.py tests/test_cm_clones_access.py -q

# Case Management roles. Existing users were given one automatically:
#   admin -> platform_admin, analyst -> investigator, viewer -> viewer
uv run python -m scripts.create_user ravi --role analyst --org-role supervisor --clearance restricted --name "Ravi K"
uv run python -m scripts.create_user ravi --set-org-role investigator --by admin

# The organisation's name and case-number prefix (decision D13), before the first real case:
uv run python -m scripts.organisation --show
uv run python -m scripts.organisation --set-up TSP --name "Example State Police" --by admin
```

**Trying the API:** start the backend (`uv run uvicorn app.main:app --port 8000`), open http://127.0.0.1:8000/docs, click **Authorize**, log in, and use the **case management** section. Be aware that **a case you create there can never be deleted** from that database (by design), and it takes the next case number.

**Development only: removing all Case Management data.** `uv run alembic downgrade 0006` then `uv run alembic upgrade head` removes the module's tables and everything in them, then recreates them empty (Case Management roles set with `--set-org-role` go back to the defaults). Never do this on a real installation: it is the one way around the protections, and only someone with database administration rights can do it. Phase CM-7 adds the audit chain that makes such a reset detectable.

## 6. How it works

### Creating a case (`POST /api/v1/cases`)

One transaction creates: the case family `KH-<year>-<number>` → the case summary (and the FIR reference, if given) as the first versions → **ROOT** with its branch `main` and the **initial commit** → ROOT is frozen → **V1** cloned from that commit, with the lead investigator as `lead` and V1 as their active workspace. Platform admins, supervisors and investigators may create cases; the lead and supervisor must belong to the same organisation, have a suitable role and **enough clearance** for the case's classification.

### Commits (`POST /api/v1/repositories/{id}/commits`)

The request names the branch, the **head it last saw** (`expected_head`), a message and the changes: `add`, `revise` or `withdraw` (with a reason). The server stores new versions, builds the new snapshot (shared if identical), computes the commit ID (`sha256` of repository, branch, ordered parents, author, UTC time to the microsecond, message, change type, snapshot hash and metadata digest), and moves the branch head **only if it is still the head the client saw**. Otherwise: **409** with the current head, and nothing is saved. Every head move is logged in `branch_head_events`.

### Cloning (`POST /api/v1/repositories/{id}/clones`)

`{source_commit, reason, assigned_investigator_id?}`. The commit must be in the source repository's **reachable history**; a commit that isn't (for example a sibling clone's later work) answers exactly like one that doesn't exist. The new clone's base commit has the source commit as its parent and the **same snapshot**. The assignee's previous clone is marked `superseded`, its memberships end, and it never changes again. Contributors are not copied: they are invited again (CM-3). All of it is one transaction: a failure leaves nothing behind (tested).

**Inherited history:** V2's history is its own commits, then the source commit and everything before it, back to ROOT. It never includes V1's commits made after the source commit.

### Who sees what

| Who | Sees | May also |
|---|---|---|
| Platform admin | every repository of their organisation, within their clearance; the registry, full lineage and the case's audit trail | clone, change statuses, record official references |
| Supervisor | the cases they supervise | the same, for those cases |
| Lead investigator | their active clone and its history | commit to `main` and any branch, create branches, clone, change the workflow status (except closing, archiving, reopening) |
| Contributor | the clone they are a member of | create branches, commit to **their own** branches |
| Analyst (member) | the same | add and revise analyses and notes on their own branches; no withdrawals |
| Viewer (member) | the same | read only |
| Anyone else, another organisation, or too low a clearance | nothing: **404, exactly as for a missing case**, and audited (`denied` vs `not_found` in the log) | — |

### Statuses: they change, each with an event; nothing is deleted

| Status | Values | Rules |
|---|---|---|
| Workflow (case) | registered, open, under investigation, pending evidence, pending review, approved for reporting, investigation completed, closed, archived, reopened | allowed transitions only; closing, archiving and reopening are the supervisor's or admin's decision. Closing a case changes no repository |
| Official (case) | as written in the official record | supervisor or admin |
| Repository | active, frozen, superseded, archived | supervisor or admin: freeze, reactivate, archive. ROOT stays frozen; superseded and archived are final |
| Branch | active, inactive, superseded | lead, supervisor or admin; `main` stays active |

### "Nothing is deleted": the layers

| Layer | In this phase |
|---|---|
| 1. API | **done:** no delete routes. DELETE, PUT and PATCH anywhere under `/api/v1`, and actions such as `reset`, `rebase`, `squash`, `amend`, answer **405** and are audited (`cm.destructive_operation.rejected`), recorded against the case they aimed at |
| 2. Services | **done:** no function updates or deletes a permanent record |
| 3. Database | **done:** 20 triggers. 10 tables can never change or be deleted (commits, snapshots, versions…); 6 tables only change their status columns; a commit's parent must be older; commits only go into active repositories; a branch head only moves to a new child commit of the same repository; ROOT stays frozen, superseded and archived clones stay so |
| 4. Write-once storage | CM-2 (evidence files) and CM-7 |
| 5. Detection | commit and snapshot IDs can already be recomputed (`verified` in the API). The hash-chained audit log with external checkpoints comes in CM-7, together with a database account that has no delete rights |

### Audit events

`cm.case.created`, `cm.case.view`, `cm.cases.list`, `cm.case.repositories`, `cm.case.status_changed`, `cm.reference.added`, `cm.workspaces.list`, `cm.repository.view`, `cm.repository.cloned`, `cm.assignment.moved`, `cm.repository.status_changed`, `cm.lineage.read`, `cm.contributors.list`, `cm.branches.list`, `cm.branch.view`, `cm.branch.created`, `cm.branch.status_changed`, `cm.history.read`, `cm.commit.created`, `cm.commit.view`, `cm.compare`, `cm.snapshot.read`, `cm.content.read`, `cm.admin.registry`, `cm.admin.lineage`, `cm.admin.audit`, `cm.admin.repositories`, `cm.destructive_operation.rejected`. A successful change and its audit event are saved together (both or neither); refusals are rolled back and still recorded. Search text is stored only as a fingerprint, as everywhere else.

## 7. Endpoints in this phase

| Area | Endpoints |
|---|---|
| Cases | `POST /api/v1/cases`, `GET /api/v1/cases`, `GET /api/v1/cases/{id}`, `GET …/{id}/repositories`, `POST …/{id}/official-references`, `POST …/{id}/status`, `GET /api/v1/case-types` |
| Repositories | `GET /api/v1/workspaces/active`, `GET /api/v1/repositories/{id}`, `POST …/clones`, `GET …/lineage`, `POST …/status`, `GET …/contributors` |
| Branches | `GET`/`POST …/branches`, `GET …/branches/{id}`, `POST …/branches/{id}/status` |
| Commits | `GET …/commits?branch=&limit=&cursor=`, `POST …/commits`, `GET …/commits/{commit}`, `GET …/compare?base=&head=` (branch names or commits), `GET …/snapshot/{commit}`, `GET …/snapshot/{commit}/{path}` |
| Administration | `GET /api/v1/admin/cases`, `GET /api/v1/admin/cases/{id}/lineage`, `GET /api/v1/admin/cases/{id}/audit`, `GET /api/v1/admin/repositories` |

Commits can be given by full ID or their first 10+ characters. Lists take `limit` (max 200) and return `next_cursor`.

**Not in this phase yet:** evidence and custody (CM-2); invitations, tasks, comments, reviews and merges (CM-3); the screens (CM-4); search, similar cases, the assistant and timelines inside a case (CM-5); integrations (CM-6); reports, MFA, the audit chain, an auditor role and a database account without delete rights (CM-7); the demo case and the full 17-step scenario (CM-8). The `Idempotency-Key` header described in the API contracts is planned with CM-3.

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_cm_cases.py tests/test_cm_history.py tests/test_cm_clones_access.py -v
```

| Test | Proves |
|---|---|
| a new case | ROOT (frozen), initial commit, `main`, V1 with the same snapshot; the lead's workspace; the case summary at the first commit; audited |
| case numbers, case types | numbers follow on; any type is accepted (an unlisted one gets the general template) |
| who may create cases; suitable lead and supervisor | viewers and analysts get 403 (audited); wrong role or too low a clearance: 422 |
| workflow and official status | only allowed transitions; closing is the supervisor's; history of every change; closing a case changes no repository |
| official references | added, never edited; duplicates 409; only supervisor or admin |
| commits and versions | parents, head moves, the head-move log; revising keeps version 1 readable at the old commit; withdrawing needs a reason and keeps the entry in history |
| invalid changes | 6 kinds refused, nothing saved |
| **stale head** | 409 with the current head; no commit saved |
| history | newest first, paged, inherited from ROOT |
| branches | start at main's head; separate from main; compare shows the difference; duplicate or bad names refused; inactive branches refuse commits; never removed |
| **integrity** | every commit ID and snapshot hash recomputes; a changed message no longer matches; the ID covers every field and is the same in any timezone |
| shared snapshots | a clone and a new branch add no snapshot |
| **cloning from a historical commit** | V2 from C1: its history has C1 and earlier, not C2/C3; V1 superseded and unchanged (head still C3); the lead sees only V2; the three audit events |
| reason and reachability | a short reason is refused; a sibling's later commit answers exactly like a missing one |
| **a failed clone leaves nothing behind** | a failure injected at the last step: no repository, branch, commit or membership added; V1 still active |
| **404 for the invisible** | a stranger gets the same answer for a hidden repository and a missing one; the audit log records `denied` vs `not_found` |
| organisations and clearance | another organisation's admin and an admin with too low a clearance see nothing |
| repository roles | viewers read only; contributors can't commit to `main` or to others' branches; analysts can't withdraw; only lead, supervisor or admin clone |
| freezing | the supervisor freezes and reactivates a clone; commits refused while frozen; ROOT can't be reopened |
| **the admin's view** | ROOT, V1, V2; every commit including the superseded work; revoked memberships; clone events; the registry; the case's audit trail; nobody else |
| lineage | V2 → V1 → ROOT, with source commits |
| **deletion and rewriting** | 6 attempts (DELETE, PUT, PATCH, reset, rebase): 405, audited against the case; everything still there |
| **the database itself refuses** | 11 direct SQL attempts (rewrite, delete, rename, moving a head backwards, reopening ROOT) fail; a superseded clone can't be reactivated or receive a commit even through the engine |
| acceptance steps 1–3, 5, 10–14, 16 | the specification's scenario for this phase, through the API |
| the migration | all 20 rules are installed |
| **the organisation's prefix** (`test_cm_organisation.py`) | set before the first case (new cases use it); refused afterwards, by the code and by the database; names can still change; invalid prefixes refused |

## 9. Expected output

```
> uv run pytest -q
........................................................................ [ 19%]
...
376 passed in 53.29s
```

The Docker stack was rebuilt (`docker compose --profile app up -d --build`); the smoke test passed 8/8 over HTTPS and the new endpoints answer there.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `404 Not found` for a case or repository that exists | You may not see it: not a member, another organisation, clearance too low, or your clone was superseded | Expected. Ask the supervisor; the audit log shows `denied` |
| `409 The branch has changed since you last looked at it` | Someone committed first | Reload, then commit on top of the new head (`current_head` is in the answer) |
| `403 Only the lead investigator commits directly to main` | Contributors work on their own branches | Create a branch; reviews and merges come in CM-3 |
| `403 … is superseded / frozen: its history is preserved` | The clone was replaced or frozen | Work in your active clone (`GET /api/v1/workspaces/active`) |
| `422 Say why the investigation is cloned` | The reason is under 10 characters | Give a real reason: it is kept with the clone forever |
| `422 … already exists: revise it instead` | `add` on an existing path | Use `revise` (a new version) |
| `422 … can't go from X to Y` | Not an allowed status transition | The message lists the allowed next statuses |
| `405 Case history is permanent` | A delete, overwrite or rewrite | By design. Make a new commit, withdraw an entry with a reason, or clone from an earlier commit |
| The Docker backend restarts in a loop after an update | Its image doesn't know the latest migration | `docker compose --profile app up -d --build` |
