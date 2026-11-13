# Step 15.3: Case Management collaboration and review (phase CM-3)

> **Partly superseded (2026-11-10).** Tasks, comments and notices still exist, now on the case. Contributors, invitations, review requests and merging no longer exist: the Investigator adds Sub Investigators and Analysts directly, and their work goes straight into the case. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md).

Status: **done and verified** (2026-11-07). 472 backend tests pass (36 new). This phase is the **API only**: the screens come in phase CM-4. All test data is fictional. **Nothing was created in the development database.**

Part 3 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It builds on [15.1, the repository core](15-1-repository-core.md), and [15.2, evidence](15-2-evidence.md).

## 1. What this phase does

Several people can now work on one case, and findings reach the case's main line only after the supervisor approves them, the way pull requests work on GitHub.

| Idea | In plain words | How it is built |
|---|---|---|
| **Invitation** | The lead asks a colleague to join a repository | same organisation, enough clearance, a role their organisation role allows: contributor, analyst or viewer. Nobody invites themselves; the lead role only comes with a clone |
| **Approval** | The supervisor agrees first | by default for contributors and analysts invited by a lead (`CM_INVITATION_APPROVAL`, decision D13); viewers and invitations by the supervisor don't need it |
| **Assigned branches** | "Work on the CDR branch" | an invitation can assign branches (never `main`); the contributor may then commit to them as well as to branches they create |
| **Revocation** | Someone leaves the case | access ends on the next request; everything they did stays attributed to them |
| **Access history** | Who had access, when, granted by whom | `authorization_events`: every membership granted or revoked, permanently (clones included) |
| **Task board** | "Request the call records by Friday" | tasks with an assignee, a due date, a status (open, in progress, done, cancelled) and a history of every change |
| **Comments** | Remarks on a commit, exhibit, note, review or task | permanent; editing adds a new version; viewers read only |
| **Review request** | "Please review my findings" | a branch's changes proposed for `main` (or another branch): what it adds, its evidence, its commits, any conflicts |
| **Decision** | approve / request changes / reject | by the case's supervisor or an administrator, never the author; each decision is permanent and names the exact branch head reviewed |
| **Merge** | Approved findings join the main line | a new commit with **two parents** (main's head, the branch's head); the branch is marked merged |
| **Conflict** | The same note changed differently on both sides | nothing is merged; the author brings main's changes into the branch, choosing for each conflict, and asks again |
| **Notifications** | "You were invited", "your review was approved" | a notice per person, kept, marked read when read |
| **Idempotency-Key** | Pressing "save" twice saves once | a create request repeated with the same key returns the first answer instead of a duplicate |
| **Sealed notes** | A transcription of a sealed recording | notes and analyses can now be sealed too, like exhibits |

## 2. Why it is needed

Specification §12 (multi-investigator collaboration: roles, invitation workflow, revocation), §13 (the review system and its statuses), §15 (the investigator's assigned tasks and notifications), §19 (idempotency) and acceptance steps **6–9**: Investigator 1 invites Investigator 2 → Investigator 2 submits findings → the supervisor approves → an approved merge commit is generated. It completes what CM-1 and CM-2 started: branches now have a way back into `main`, and that way is reviewed.

## 3. Files created or changed

```
backend/app/casemgmt/
├─ members.py          NEW  invitations (checks, approval, accept, decline, cancel, expiry), revocation
├─ tasks.py            NEW  the task board: create, status, assign; every change in task_events
├─ comments.py         NEW  comments on commits, exhibits, notes, reviews, tasks; edits as new versions
├─ reviews.py          NEW  review requests, decisions, two-parent merges, bringing a branch up to date
├─ merging.py          NEW  merge base and three-way comparison of snapshots (conflict detection)
├─ artifacts.py        NEW  a note's version history; sealing notes and analyses
├─ notifications.py    NEW  notices for users
├─ idempotency.py      NEW  the Idempotency-Key header
├─ collab_views.py     NEW  read-only views
├─ collab_api.py       NEW  34 endpoints under /api/v1
├─ models.py, enums.py, schemas.py   9 new tables; assigned branches; sealable notes; new value lists and shapes
├─ engine.py           access history for clones; the "one path, one entry" rule; assigned branches; a snapshot fix (below)
├─ access.py           assigned branches (works_on); sealed notes hidden from views
├─ api.py, evidence_api.py   Idempotency-Key on creating cases, clones, branches, commits and evidence
├─ custody.py          a pending evidence transfer notifies its receiver
└─ queries.py          members show their assigned branches; repository pages say can.invite and can.open_review
backend/alembic/versions/0010_case_management_collaboration_and_review.py   tables, assigned branches, 9 more database rules
backend/app/core/config.py, .env.example, docker-compose.yml   CM_INVITATION_APPROVAL, CM_INVITATION_DAYS
backend/tests/test_cm_members.py, test_cm_tasks_comments.py, test_cm_reviews.py, test_cm_idempotency_sealing.py   35 tests (+1 in test_cm_history.py)
docs/DECISIONS.md      D13: the invitation policy
```

## 4. Packages

None new.

## 5. Commands

```powershell
cd backend
uv run alembic upgrade head        # adds the collaboration tables (already done on this computer)
uv run pytest tests/test_cm_members.py tests/test_cm_tasks_comments.py tests/test_cm_reviews.py tests/test_cm_idempotency_sealing.py -q
```

After a new migration, rebuild the Docker version: `docker compose --profile app up -d --build`. Trying the API: as in [15.1](15-1-repository-core.md#5-commands), section **case management: collaboration and review**. Anything created there is permanent.

## 6. How it works

### Invitations (`POST /api/v1/repositories/{id}/invitations`)

`{user_id, role: contributor | analyst | viewer, message?, branch_ids?}`, by the lead investigator, the case's supervisor or an administrator.

```
lead invites ──► awaiting approval ──(supervisor approves)──► pending ──(invitee accepts)──► accepted
                        │                                       │
                        └─(refused, with a reason)              ├─(declined by the invitee)
                                                                ├─(cancelled by the inviter, lead or supervisor)
                                                                └─(expired after 14 days)
supervisor or admin invites, or a viewer is invited ───────────► pending
```

| Check | Refused with |
|---|---|
| The invitee is an active user of the same organisation | 422 |
| Their clearance covers the case's classification | 422 |
| Their organisation role allows the repository role (viewer → viewer; analyst → analyst or viewer; investigator, supervisor, admin → contributor, analyst or viewer) | 422 |
| Not yourself; never the lead role; assigned branches belong to the repository and aren't `main` | 422 |
| Not already a member; no other open invitation for them | 409 |
| The inviter is the lead, the supervisor or an administrator; the repository is active | 403 |

Accepting (`POST /api/v1/invitations/{id}/accept`, the invitee only) creates the membership with its assigned branches, an access-history record, and, if they have no workspace for the case yet, a workspace (so the case appears on their dashboard). `GET /api/v1/invitations/mine` lists what waits for your answer and, for supervisors, what waits for your approval.

### Revocation and access history

`POST /api/v1/repositories/{id}/members/{user_id}/revoke {reason}`, by the lead, the supervisor or an administrator. Nobody revokes themselves; the lead changes only by cloning with a new assignee. Access ends on the next request (404, like a missing case), their workspace ends, and they are notified. Their commits, comments and tasks stay, attributed to them. `GET /api/v1/repositories/{id}/access-history` (and `/api/v1/admin/cases/{id}/access-history` for administrators) lists every membership granted or revoked, including the ones a clone ends, permanently.

### What each role may do now (adds to 15.1)

| | Lead | Contributor | Analyst | Viewer | Supervisor | Admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Invite | ✓ (approval for contributors and analysts) | – | – | – | ✓ | ✓ |
| Approve or refuse invitations | – | – | – | – | ✓ | ✓ |
| Revoke a member | ✓ (not the lead) | – | – | – | ✓ | ✓ |
| Commit to a branch | any, including main | own + assigned | own + assigned (analyses) | – | – | – |
| Create tasks / comment | ✓ | ✓ | ✓ | – (reads) | ✓ | ✓ |
| Open a review | any branch | own + assigned | own + assigned | – | – | – |
| Decide on a review | – | – | – | – | ✓ (if not its author) | ✓ |
| Merge approved findings | – | – | – | – | ✓ | ✓ |
| Seal notes and analyses | – | – | – | – | ✓ | ✓ |

### Reviews

```
draft ──► submitted ──► approved ──► merged
             ▲  │          │
             │  ▼          └─(new commits on the branch: submit again for a fresh decision)
       changes_requested
any open status ──► rejected (final, by the reviewer) or superseded (withdrawn)
```

- **Open** (`POST /api/v1/repositories/{id}/reviews`): `{source_branch_id, target_branch_id? (main), title, description?, findings?, reviewer_id?, linked_task_ids?, draft?}`. The branch must have content the target doesn't have, must be active, not `main`, and yours (or assigned to you; the lead: any). One open review per branch. The reviewer is the case's supervisor unless you name an administrator.
- **Look** (`GET /api/v1/reviews/{id}`): what the branch adds, revises and withdraws (compared with where it left the target), the evidence among those changes, its commits, how far the target moved on, **conflicts**, every decision, the history of statuses, and whether it can be merged now.
- **Decide** (`POST /api/v1/reviews/{id}/decisions` `{decision, comment}`): approve, request changes (comment required), reject (comment required). Never by the author. Each decision records the exact branch head it was about.
- **Merge** (`POST /api/v1/reviews/{id}/merge`), by the supervisor or an administrator, only when the review is approved, the approval is for the branch **as it is now**, and nothing conflicts. The result is a commit on the target with **two parents**, target head first; the branch's commits become part of the target's history, each still credited to its author; the branch is marked `merged` and takes no more commits.
- `GET /api/v1/reviews/inbox`: reviews waiting for your decision, and your own open ones.

### Conflicts, and bringing a branch up to date

The **merge base** is the latest commit both branches share. An entry changed on one side only is taken from that side. An entry changed **differently on both sides** is a conflict, and nothing is merged.

The author resolves it with `POST /api/v1/repositories/{id}/branches/{branch_id}/sync` `{expected_head, from_branch_id? (main), resolutions: [...]}`. That brings the target's changes into the branch as a commit with two parents (the branch's head, the target's head). Every conflicting entry needs a resolution:

| Resolution | Effect |
|---|---|
| `{"path": …, "take": "mine"}` | keep the branch's version |
| `{"path": …, "take": "theirs"}` | take the target's version |
| `{"path": …, "content": {…}, "note": …}` | a **new version** combining both, derived from both (notes and analyses changed on both sides) |

Without a resolution for every conflict: 409 with the list, and nothing changes. The review then shows no conflicts, but its approval is no longer current (the branch changed), so the author submits again for a fresh decision.

**One path, one entry:** a new path can't be added on one branch while another branch of the same repository uses it (422 "already used on branch …"). Two different entries at one path could never be merged without one of them dropping out of view.

### Tasks, comments, notifications

- **Tasks** (`POST`/`GET /api/v1/repositories/{id}/tasks`, `GET /api/v1/tasks/{id}`, `POST …/status`, `POST …/assign`, `GET /api/v1/tasks/mine`): assigned to members who work on the repository (not viewers). Status `open → in progress → done`, cancel with a reason, reopen with a reason. Changed by the assignee, the creator, the lead or the supervisor; `expected_version` gives "reload and try again" instead of overwriting. A frozen or superseded repository's board stays as it was.
- **Comments** (`POST`/`GET /api/v1/repositories/{id}/comments?target_type=&target_id=`): on a commit (short IDs work), exhibit, note, review or task you can see. Edit = `replaces_comment_id`; both versions stay. A sealed exhibit's comments disappear with it for those who can't see it.
- **Notifications** (`GET /api/v1/notifications?unread_only=`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`): invitations (received, waiting for approval, approved, refused, accepted, declined, cancelled), revocation, task assigned and status changes, review submitted, decided, merged and withdrawn, comments on your review or task, and a pending evidence transfer. Each says the case, the repository and who did it, never file names or evidence content. Only you can see yours. The live feed (Server-Sent Events) comes with the screens (CM-4).

### Idempotency-Key

Creating a case, clone, branch, commit, exhibit, invitation, task, comment or review accepts an `Idempotency-Key` header (8–100 letters, digits, `_ . : -`). The first answer is stored with the change; repeating the same request with the same key within 24 hours returns it (header `Idempotent-Replay: true`) instead of a duplicate. The same key with a different request: 422. Keys are per user. Replays are audited (`replayed: true`).

### Notes and analyses: history and sealing

- `GET /api/v1/artifacts/{id}/versions`: every version you can see, oldest first, with content and what each was derived from. After cloning from an earlier commit, you see the versions up to that commit; the supervisor sees all.
- `POST /api/v1/artifacts/{id}/seal` / `unseal` `{reason}` (supervisor, admin): hidden like a sealed exhibit (detail, snapshots, folders, comparisons, commit details, comments); can't be revised or withdrawn by others; each change recorded with its reason (`case_status_events`, field `seal`).

### A fix to phase CM-1

Saving a snapshot that already existed (identical content written again) failed with a duplicate-key error. Asked how many rows "insert unless it exists" had inserted, the database driver answers −1 ("unknown"), which was read as "inserted". No earlier test produced identical content, but a merge can. The code now asks for the inserted row back (`RETURNING`), which is reliable, and a regression test covers it.

### "Nothing is deleted": collaboration records

No delete routes; `DELETE`/`PUT`/`PATCH` anywhere under `/api/v1` answer 405 and are audited. Database rules (9 more, 36 in total): access history, task history, comments, review decisions and idempotency keys can never change; invitations, tasks, reviews and notifications only change their status fields (an invitation's role or assigned branches, a task's title, a review's title or branches, a notice's content: never); notes and analyses only change their seal fields; a membership's assigned branches never change.

### Audit events

`cm.invitation.created/approved/refused/accepted/declined/cancelled`, `cm.invitations.list/mine`, `cm.member.revoked`, `cm.access_history.read`, `cm.admin.access_history`, `cm.task.created/view/status_changed/assigned`, `cm.tasks.list/mine`, `cm.comment.added`, `cm.comments.list`, `cm.review.opened/view/submitted/decided/withdrawn/merged`, `cm.reviews.list/inbox`, `cm.branch.synced`, `cm.artifact.versions/sealed/unsealed`, `cm.notifications.list/read_all`, `cm.notification.read`. All of them appear in the case's audit trail for administrators.

## 7. Endpoints in this phase

| Area | Endpoints |
|---|---|
| Members | `POST`/`GET /api/v1/repositories/{id}/invitations`, `GET /api/v1/invitations/mine`, `POST /api/v1/invitations/{id}/approve · refuse · accept · decline · cancel`, `POST /api/v1/repositories/{id}/members/{user_id}/revoke`, `GET /api/v1/repositories/{id}/access-history`, `GET /api/v1/admin/cases/{id}/access-history` |
| Tasks | `POST`/`GET /api/v1/repositories/{id}/tasks`, `GET /api/v1/tasks/mine`, `GET /api/v1/tasks/{id}`, `POST …/status`, `POST …/assign` |
| Comments | `POST`/`GET /api/v1/repositories/{id}/comments` |
| Reviews | `POST`/`GET /api/v1/repositories/{id}/reviews`, `GET /api/v1/reviews/inbox`, `GET /api/v1/reviews/{id}`, `POST …/submit · decisions · withdraw · merge`, `POST /api/v1/repositories/{id}/branches/{branch_id}/sync` |
| Notes | `GET /api/v1/artifacts/{id}/versions`, `POST …/seal · unseal` |
| Notifications | `GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all` |

34 new endpoints; 74 in the module.

**Not in this phase yet:** the live notification feed (Server-Sent Events) and every screen (CM-4); Case Intelligence inside cases (CM-5); integrations (CM-6); reports, MFA, the hash-chained audit log (CM-7); the demo case and the complete 17-step scenario (CM-8).

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_cm_members.py tests/test_cm_tasks_comments.py tests/test_cm_reviews.py tests/test_cm_idempotency_sealing.py -v
```

| Test | Proves |
|---|---|
| **invite → approve → accept** | awaiting approval; no access before acceptance; supervisor's and invitee's lists; contributor afterwards (reads, branches, commits); workspace; access history; notices to all three |
| viewers and supervisors | viewers need no approval; invitations by the supervisor need none |
| suitable colleagues only | other organisation, too low a clearance, wrong organisation role, yourself, an inactive user, the lead role, `main` as an assigned branch: 422; already invited: 409 |
| **contributors cannot grant themselves privileges** | can't invite (anyone or themselves), approve, accept others' invitations, revoke themselves or the lead; no request changes a role (PUT/PATCH/DELETE 405) |
| **revoked contributors lose access** | 404 at once on the repository and its commits; workspace gone; their commit still credited to them; member record shows who revoked; access history; notice; the lead can't be revoked |
| declined, refused, cancelled, expired | each recorded; an expired invitation answers 410 and doesn't block a new one |
| **assigned branches** | a contributor commits to the lead's CDR branch she was assigned, not to others or to main |
| clones and access history | V1's grants and revocations, V2's lead; contributors not copied; the admin's case-wide history |
| the database refuses (8) | access history, invitations, assigned branches, notifications: no edits or deletions beyond their status |
| **task board** | assignment and notice; viewers and outsiders refused; status flow; 409 on a stale version; reasons to reopen; full history; reassignment; a frozen board stays as it was; the database refuses edits |
| **comments** | short commit IDs; edits keep both versions; only your own, only the newest; viewers read only; unreachable commits 404; a sealed exhibit's comments vanish for the lead |
| comments on reviews | reach the author |
| notifications | private (404 for others); read; unread only; read-all |
| **acceptance steps 6–9** | the lead's CDR branch, a contributor invited and assigned to it, approved and accepted; evidence and an analysis derived from it; review submitted to the supervisor; approved; merged: two parents in the right order, verified, the contributor's commits in main's history, branch merged and closed to commits, notices, every commit ID recomputes |
| review rules | someone else's branch 403; main or an empty branch 422; the reviewer must supervise; drafts; one open review per branch; only the author submits; authors and leads don't decide; comments required; changes requested → resubmitted; reject is final and the findings stay on their branch; withdrawal |
| **stale approval** | a commit after approval blocks the merge (409) until submitted and approved again |
| main moved on | a merge still works when main changed elsewhere |
| **conflicts** | two notes changed on both sides: listed, merge refused; resolving one by a combined version (derived from both) and one by "theirs"; a fresh approval; the merged result |
| one path, one entry | a path used on another branch can't be added (notes and evidence) |
| the database refuses (5) | review decisions never change; reviews only their status |
| **Idempotency-Key** | a repeated case, commit and upload give the same answer once; different request 422; bad key 422; keys per user; replays audited; 24 hours |
| **sealed notes** | only the supervisor seals; hidden from the lead everywhere (history, snapshot, commit, revising, comments); unsealed again; both recorded |
| note history | three versions; after cloning from the first commit the lead sees only version 1, the supervisor all three |
| snapshot fix (`test_cm_history.py`) | storing identical content again reuses it |

## 9. Expected output

```
> uv run pytest -q
........................................................................ [ 15%]
...
472 passed in 121.15s (0:02:01)
```

The Docker version was rebuilt; its backend applied migration 0010 when it started. Over HTTPS: the smoke test passed 8/8, and seven collaboration checks that create no data passed (notifications, review inbox, invitations, tasks, an invitation to a missing repository answering 404, deleting a review answering 405, and the development database still holding no cases).

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `422 … can be invited as: …` | The organisation role doesn't allow that repository role | Choose an allowed role, or ask an administrator to change the person's organisation role |
| `422 This invitation is awaiting approval` on accept | The supervisor hasn't approved yet | Wait for the approval notice |
| `410 This invitation has expired` | Older than 14 days | Ask for a new invitation |
| `409 … already has an open invitation` | Invited before | Accept, decline or cancel the open one first |
| `403 You can commit only to branches you created or were assigned` | Not your branch | Ask the lead to assign it to you (a new invitation with `branch_ids` after the current membership is revoked), or work on a branch of your own |
| `422 … already used on branch …` | Another branch has an entry at that path | Choose another path |
| `422 … has nothing that main doesn't already have` | The branch's content equals the target's | Commit your findings first |
| `409 … changed since it was approved` on merge | New commits after approval | The author submits again; the supervisor decides again |
| `409 Some entries were changed differently on both branches` | Conflicts | The author calls `…/branches/{id}/sync` with a resolution for each listed path, then submits again |
| `403 Nobody reviews their own findings` | The author tried to decide | Another supervisor or an administrator decides |
| `422 This Idempotency-Key was already used for a different request` | A key reused for something else | Use a new key for each new request |
| `409 The task has changed since you last looked at it` | Someone changed it first | Reload and try again |
