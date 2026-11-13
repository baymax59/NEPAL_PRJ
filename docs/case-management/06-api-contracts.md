# 06. API contracts

For developers. FastAPI generates the full OpenAPI specification: it is kept in this folder as [`openapi.json`](openapi.json) (114 endpoints under `/api/v1`, plus the earlier similar-case search endpoints under `/api/`), the front end's TypeScript types are generated from it (`npm run gen:api`), and development builds serve it at `/openapi.json` with interactive pages at `/docs` on the backend. The module's endpoints are under **`/api/v1`**; the similar-case search of Steps 0 to 14 stays under `/api/...`.

This document was rewritten on 2026-11-10 for the plain case design ([13-plain-case-design.md](13-plain-case-design.md)). The earlier git-style endpoints (repositories, clones, branches, commits, reviews, invitations, snapshots, compare, graph) no longer exist. The table below is generated from `openapi.json`, so it matches the code; the descriptions are the ones the endpoints carry.

## 1. Conventions for every endpoint

| Topic | Rule |
|---|---|
| Authentication | `Authorization: Bearer <token>`. Privileged actions need two-step verification when `CM_MFA_REQUIRED` is on |
| Authorisation | Checked on the server, inside the database query, for every request. The user interface hides nothing that matters for security. What each part of a case may do is in document 13, section 3 |
| Not visible | `404 {"detail": "Not found"}`, identical for missing and forbidden, and audited |
| Visible but not allowed | `403` |
| Conflicting update | `409`. A new version of a note names the version it is based on (`expected_version`); if someone made a newer one, the answer is `409` and nothing is saved: read the note again |
| Destructive request | **There are no DELETE routes for case resources.** Any `DELETE`, `PUT` or `PATCH` on `/api/v1`, and any attempt at a history-rewriting `POST` (`reset`, `rebase`, `rewrite`…), gets `405` and is audited as `cm.destructive_operation.rejected`. A mistake is corrected with a new version of a note, or by withdrawing a file with a reason |
| Validation | `422` with the field errors |
| Creating things | `POST` with an optional `Idempotency-Key` header; a repeated key returns the original result (header `Idempotent-Replay: true`) |
| Lists | `?limit=` (default 50, max 200) and `?cursor=`, plus filters. The response includes `next_cursor`. The history is paged by entry number: `?limit=` and `?after=<number>`, or `?latest=<n>` for the newest few |
| Times | ISO-8601 in UTC; original timezones are kept in separate fields |
| IDs | UUIDs in paths; files by their number (`NOTE-0001`, `EV-0001`, `RPT-0001`) in text; history entries by their number (1, 2, 3…) |

## 2. Endpoints

### Cases

| Method and path | What it does |
|---|---|
| `GET /api/v1/case-types` | The kinds of case, with the folders each one gets at registration and the kinds of evidence it expects. |
| `POST /api/v1/cases` | Register a case: its folders are made at once from its type, with the summary note and the first history entry; the lead joins the team. |
| `GET /api/v1/cases` | The cases the user may open (filter by `q`, `workflow_status`, `case_type`; paged). |
| `GET /api/v1/cases/mine` | The cases you are on the team of, with your part in each (the investigator's "My cases"). |
| `GET /api/v1/cases/{case_id}` | One case: its facts, official references, status history, folders, team and what the user may do in it (`can`). |
| `GET /api/v1/cases/{case_id}/access-history` | Everyone added to or removed from this case's team, oldest first (permanent). |
| `POST /api/v1/cases/{case_id}/lead` | Hand the case to another Investigator (the supervisor or an administrator decides). The old lead stays as a Sub Investigator. |
| `POST /api/v1/cases/{case_id}/official-references` | Record an official reference (FIR, complaint…). It is added, never edited. |
| `POST /api/v1/cases/{case_id}/status` | Change the workflow status or the official status (allowed changes only; a reason is kept in the history). |

### Folders, files and notes

| Method and path | What it does |
|---|---|
| `POST /api/v1/artifacts/{artifact_id}/seal` | Hide a note or analysis from everyone but the supervisor and administrators. Nothing is removed. |
| `POST /api/v1/artifacts/{artifact_id}/unseal` | Open a sealed note to the team again (supervisor or administrator). |
| `GET /api/v1/artifacts/{artifact_id}/versions` | Every version of a note or analysis, oldest first. |
| `POST /api/v1/artifacts/{artifact_id}/versions` | A new version of a note. The old text stays; if someone revised it since you opened it, nothing is overwritten (409). |
| `POST /api/v1/artifacts/{artifact_id}/withdraw` | Withdraw a wrong note, with a reason. It leaves the case's current view and stays in the history. |
| `GET /api/v1/cases/{case_id}/files` | The case's files (exhibits and notes), in one folder or in all. A withdrawn file shows only when asked for. |
| `GET /api/v1/cases/{case_id}/folders` | The case's folders, with how many files each holds. |
| `POST /api/v1/cases/{case_id}/folders` | Add a folder to the case (the Investigator who leads it, or its supervisor). Folders are never renamed or removed. |
| `POST /api/v1/cases/{case_id}/notes` | Write a note, analysis, transcription or timeline in a folder of the case. It is part of the case at once. |

### The team

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/team` | Everyone who is or was on the team, with their part, who added them and when. |
| `POST /api/v1/cases/{case_id}/team` | Add a Sub Investigator, Analyst or Viewer to the case: at once, no invitation to accept (the Investigator who leads the case, its supervisor or an administrator). |
| `POST /api/v1/cases/{case_id}/team/{member_id}/remove` | End someone's place on the team. Everything they did stays attributed to them. |
| `GET /api/v1/colleagues` | People the user could choose: a new case's lead or supervisor (who work at the case's station), or someone to add to a case's team (who works at the case's station). |

### The history

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/history` | Everything that happened in the case, oldest first (permanent). |
| `GET /api/v1/cases/{case_id}/history/check` | Re-check the case's whole history: every entry is recomputed and must follow the one before it. |

### Evidence

| Method and path | What it does |
|---|---|
| `POST /api/v1/cases/{case_id}/evidence` | Upload an exhibit (multipart/form-data) into a folder of the case. |
| `GET /api/v1/evidence/{evidence_id}` | One exhibit: its facts, provenance, custody and what the user may do with it (`can`). |
| `GET /api/v1/evidence/{evidence_id}/custody` | The exhibit's chain of custody, oldest first. |
| `POST /api/v1/evidence/{evidence_id}/custody` | Transfer an exhibit, or acknowledge or decline a pending transfer. |
| `POST /api/v1/evidence/{evidence_id}/download-token` | A one-time download link for the original file (it is a custody event). |
| `GET /api/v1/evidence/{evidence_id}/preview` | A safe text view: text files, and the text of PDFs and Word files. Nothing is ever rendered or run. |
| `POST /api/v1/evidence/{evidence_id}/seal` | Hide an exhibit from everyone but the case's supervisor and administrators. Nothing is removed. |
| `POST /api/v1/evidence/{evidence_id}/unseal` | Open a sealed exhibit to the team again (supervisor or administrator). |
| `POST /api/v1/evidence/{evidence_id}/verify` | Recompute the stored file's SHA-256 and compare it with the one recorded when it was added. |
| `GET /api/v1/evidence/{evidence_id}/versions` | The original (an exhibit's only version) and the analyses, transcriptions and notes derived from it. |
| `POST /api/v1/evidence/{evidence_id}/withdraw` | Withdraw a wrong exhibit, with a reason. It leaves the case's current view and stays in the history and the chain of custody. |

### Tasks and comments

| Method and path | What it does |
|---|---|
| `POST /api/v1/cases/{case_id}/comments` | Comment on the case, an exhibit, a note or a task. Editing adds a replacing comment; the earlier wording stays. |
| `GET /api/v1/cases/{case_id}/comments` | The comments on one subject (`target_type`, `target_id`), oldest first. |
| `POST /api/v1/cases/{case_id}/tasks` | Create a task, optionally assigned to someone on the team. |
| `GET /api/v1/cases/{case_id}/tasks` | The case's tasks. |
| `GET /api/v1/tasks/mine` | Open tasks assigned to me, in cases I can still open (the investigator's "Assigned tasks"). |
| `GET /api/v1/tasks/{task_id}` | One task with its history of changes. |
| `POST /api/v1/tasks/{task_id}/assign` | Assign or reassign a task. |
| `POST /api/v1/tasks/{task_id}/status` | Move a task along (open, in progress, done, cancelled). |

### Links

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/links` | The case's links (withdrawn ones marked), and the cases that link to it. |
| `POST /api/v1/cases/{case_id}/links` | Link this case to another one the user can open, or to a past case they may see, with a reason. |

### Reports

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/report-preview` | What a report on the case as it stands contains, with provenance and integrity information (a preview). |
| `POST /api/v1/cases/{case_id}/reports` | A PDF report of the case as it stands, kept write-once and added to the case as a new report version. |
| `GET /api/v1/cases/{case_id}/reports` | The report versions of the case. |
| `POST /api/v1/reports/verify-file` | Check a copy someone holds (printed from a download, e-mailed): is it byte for byte a report Knight Hawk generated? The file is only hashed, never kept. |
| `GET /api/v1/reports/{export_id}` | One signed report version, with the history of its checks and downloads. |
| `POST /api/v1/reports/{export_id}/download-link` | A one-time link to the report's PDF; the stored copy is re-checked before it is sent. |
| `POST /api/v1/reports/{export_id}/verify` | Hash the stored copy again and compare it with the hash recorded when the report was generated. |

### Case Intelligence inside a case

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/intelligence` | What of this case Case Intelligence has read: documents, notes, passages, and what is missing and why. |
| `POST /api/v1/cases/{case_id}/intelligence/ask` | Ask about the case. Answers cite exhibit or note, version and page. |
| `GET /api/v1/cases/{case_id}/intelligence/offences` | Sections cited in this case's documents and notes, and sections cited by the most similar past cases (prompts only). |
| `POST /api/v1/cases/{case_id}/intelligence/prepare` | Read the documents and notes of this case that haven't been read yet (each file once, whatever case holds it). |
| `POST /api/v1/cases/{case_id}/intelligence/search` | Search the documents and notes of this case (POST: the words stay out of URLs). |
| `GET /api/v1/cases/{case_id}/intelligence/similar` | Past cases (knowledge base) and other investigations similar to this one, with why. |
| `GET /api/v1/cases/{case_id}/intelligence/timeline` | The reconstructed timeline (if one was built and you may see it). |
| `POST /api/v1/cases/{case_id}/intelligence/timeline` | Rebuild the timeline from the case as it stands: a new version of the timeline note. |

### Imported findings

| Method and path | What it does |
|---|---|
| `GET /api/v1/cases/{case_id}/imports` | The findings imported into the case. |
| `GET /api/v1/cases/{case_id}/imports/{artifact_id}` | One imported finding: provenance, versions, what uses it, and the other cases where its identifiers appear. |
| `GET /api/v1/cases/{case_id}/indicators` | Every identifier the case's imported findings name, with the other cases (that you can open) where it appears. |
| `POST /api/v1/integrations/add-to-case` | Add a finding from an outside system to a case the person may add to: an immutable reference, a history entry and an audit event. |
| `GET /api/v1/integrations/contract` | What a finding may contain: item types, identifier types, limits and headers (version 1.0). |
| `GET /api/v1/integrations/sources` | The organisation's integration sources, with their access policies, key prefixes, use and history. |
| `POST /api/v1/integrations/sources` | Register a source with its policy. Its key is in the answer, this once. |
| `POST /api/v1/integrations/sources/test-source` | Register the built-in fictional test source (it stands in for the real systems until they exist). |
| `POST /api/v1/integrations/sources/{source_id}/key` | Issue a new key for a source; the old key stops working at once. The new key is in the answer, this once. |
| `POST /api/v1/integrations/sources/{source_id}/status` | Enable or disable a source, with a reason. Disabling stops its key at once; what it added stays. |
| `GET /api/v1/integrations/test-source` | The fictional findings the test source can add to a case, and whether an administrator has registered it. |
| `POST /api/v1/integrations/test-source/send` | Add one fictional finding of the test source to a case you may add to, exactly as a real source would. |

### Legal holds and retention

| Method and path | What it does |
|---|---|
| `GET /api/v1/admin/governance` | The audit chain, its checkpoints, the scheduled jobs, the active legal holds and the security settings. (No screen uses it since 2026-11-12: the Governance page was removed; the endpoint remains for tools.) |
| `GET /api/v1/admin/retention` | Retention policies, and the cases due for review. |
| `POST /api/v1/admin/retention/policies` | Add a retention policy. |
| `POST /api/v1/admin/retention/policies/{policy_id}/retire` | Retire a retention policy (it stays on record). |
| `GET /api/v1/cases/{case_id}/governance` | The case's legal holds, retention decisions and review date. |
| `POST /api/v1/cases/{case_id}/legal-holds` | Place a legal hold: the case can't be archived, nor a retention decision approved, until it is released. |
| `POST /api/v1/cases/{case_id}/retention-decisions` | Propose a retention decision about a case; a different person decides it. |
| `POST /api/v1/legal-holds/{hold_id}/release` | Release a legal hold, with a reason. |
| `POST /api/v1/retention-decisions/{decision_id}/decide` | Approve or refuse a retention decision proposed by someone else. |
| `POST /api/v1/retention-decisions/{decision_id}/withdraw` | Withdraw a retention decision you proposed. |

### Notices, dashboards and the live stream

| Method and path | What it does |
|---|---|
| `GET /api/v1/contributions/mine` | What the user did: history entries, notes, new versions and exhibits, with the latest entries. |
| `GET /api/v1/dashboards/officers/{user_id}` | One officer's figures and cases. |
| `GET /api/v1/dashboards/stations` | The stations the user may follow, with their figures. |
| `GET /api/v1/dashboards/stations/{station_id}` | One station: figures, months, officers. |
| `GET /api/v1/notifications` | The user's notices, newest first. |
| `POST /api/v1/notifications/read-all` | Mark every notice as read. |
| `GET /api/v1/notifications/stream` | Tells the browser when the user's notices change (counts only) and, for the page it has open, when what that page shows has changed (a fingerprint only: the page then re-reads its data). Without a database connection held open. |
| `POST /api/v1/notifications/{notification_id}/read` | Mark one notice as read. |

### People and stations

| Method and path | What it does |
|---|---|
| `GET /api/v1/people/accounts` | Accounts the user may manage. |
| `POST /api/v1/people/accounts` | Make the account of a registered officer. A temporary password comes back once. |
| `POST /api/v1/people/accounts/{user_id}/active` | End an account (someone leaves) or restore it. Their work stays, attributed to them. |
| `POST /api/v1/people/accounts/{user_id}/reset-password` | A new temporary password, shown once; the owner must replace it at their next login. |
| `POST /api/v1/people/accounts/{user_id}/role` | A promotion or demotion. It adds no power over cases that already exist. |
| `POST /api/v1/people/accounts/{user_id}/stations` | Set the stations a person works at (an Administrator: one or more; everybody else: exactly one). |
| `GET /api/v1/people/capabilities` | What the user may do on the People screens. |
| `GET /api/v1/people/officers` | The register as far as the viewer can reach. `free=true`: only officers who have no account yet. |
| `POST /api/v1/people/officers` | Enter one officer in the register (the Super Admin only). |
| `POST /api/v1/people/officers/import` | Enter many officers from a CSV file. All or nothing: any problem is listed and nothing is entered. |
| `GET /api/v1/people/stations` | The stations the viewer can reach, with how many people, officers and cases each has. |
| `POST /api/v1/people/stations` | Open a police station (the Super Admin only). Stations are never deleted. |
| `POST /api/v1/people/stations/{station_id}` | Correct a station's name or district, or mark it inactive (the Super Admin only). Its history stays. |
| `GET /api/v1/stations` | The police stations the user may register cases at: every station for a Super Admin, else their own. |

### Administration

| Method and path | What it does |
|---|---|
| `POST /api/v1/admin/audit/checkpoints` | Sign the audit chain as it stands now (a checkpoint), and keep the signed record in the write-once store. |
| `POST /api/v1/admin/audit/verify` | Recompute the whole audit chain and check every signed checkpoint, now. The result is recorded as a job run. |
| `GET /api/v1/admin/cases` | Every case of the organisation, with its counts (Super Admin). |
| `GET /api/v1/admin/cases/{case_id}/access-history` | The access history of a case (the administrators' team history). |
| `GET /api/v1/admin/cases/{case_id}/audit` | The case's audit trail: every Case Management event about the case. |
| `GET /api/v1/admin/evidence-integrity` | Every exhibit of the organisation with its latest integrity check: failures first, then never checked. |
| `POST /api/v1/admin/jobs/{job}/run` | Run one of the scheduled jobs now (it is recorded like the worker's runs). |
| `GET /api/v1/admin/overview` | The organisation's figures: cases, files, history entries per day, evidence integrity, tasks (Super Admin). |

### Downloads (one-time links)

| Method and path | What it does |
|---|---|
| `GET /api/v1/evidence-downloads/{token}` | Follow a download link. No login header: the link names its user, whose access is checked again now. |
| `GET /api/v1/report-downloads/{token}` | Follow a one-time link. The stored copy is checked against its recorded hash before it is sent. |

## 3. Examples

**Register a case.** The folders are made at once, from the case's type, and the lead is on the team.

```json
POST /api/v1/cases
{ "title": "Online banking fraud", "case_type": "cyber_fraud",
  "description": "plain text: what reports, search and the assistant read",
  "description_html": "<p><strong>optional</strong>: the same text with the writer's formatting</p>",
  "priority": "high", "classification": "restricted", "jurisdiction": "Example Nagar PS",
  "lead_investigator_id": "…", "supervisor_id": "…",
  "official_reference": { "ref_type": "FIR", "number": "0123/2026", "issuing_authority": "Example Nagar PS" },
  "reported_by": { "name": "Meera Nair", "phone": "+91 …", "email": "meera@example.org", "address": "…" } }

201 { "case_id": "…", "display_id": "KH-2026-0001",
      "folders": ["case-information", "complainant", "digital-evidence", "cdr-analysis", "…"],
      "lead": { "id": "…", "username": "inv.arun", "display_name": "SI Arun Kumar" } }
```

- `description_html` is cleaned by the server (only bold, italic, underline, lists, colour, font, size and alignment survive; scripts, links, images and
  other styles are removed). The case detail returns it as `description_html` (null when there is none); the plain `description` is always there.
- `reported_by` is optional, as is every field in it. `{ "unknown": true }` records that no one was there to report the case; `unknown` can't be
  combined with details (422). The case detail returns `reported_by`: null (nothing recorded), `{ "unknown": true, … }`, or the details.

**Write a note into a folder.** It is part of the case at once; the answer names the history entry that recorded it.

```json
POST /api/v1/cases/{case_id}/notes
{ "folder": "investigation-notes", "artifact_type": "note", "title": "Initial assessment",
  "content": { "text": "…" }, "derived_from": ["EV-0001"] }

201 { "file": { "id": "…", "display_id": "NOTE-0001", "folder": "investigation-notes", "version_number": 1, "…": "…" }, "entry": 7 }
```

**Correct a note with a new version.** The old version stays.

```json
POST /api/v1/artifacts/{artifact_id}/versions
{ "content": { "text": "…the corrected text…" }, "expected_version": 1, "note": "The bank's log is in UTC, not IST" }

201 { "version": { "version_number": 2, "…": "…" }, "entry": 12 }      409 if version 1 is no longer the newest
```

**Add a Sub Investigator or an Analyst to the team.** Straight in: no invitation, no approval.

```json
POST /api/v1/cases/{case_id}/team
{ "user_id": "…", "role": "sub_investigator" }            (or "analyst" or "viewer")

201 { "case": { "…": "…" }, "team": [ { "user": { "…": "…" }, "role": "lead", "…": "…" }, { "user": { "…": "…" }, "role": "sub_investigator", "…": "…" } ] }
```

**Check the history.**

```json
GET /api/v1/cases/{case_id}/history/check

200 { "entries": 41, "intact": true, "first_problem": null, "problem": null }
```

**Withdraw a wrong file.** It leaves the current view and stays in the history.

```json
POST /api/v1/evidence/{evidence_id}/withdraw        (or /api/v1/artifacts/{artifact_id}/withdraw)
{ "reason": "Uploaded to the wrong case" }
```

## 4. Officers creating their own login (public)

`GET /api/auth/registration` answers `{ "enabled": true }` (the log in page shows "Create your own login" only then). `POST /api/auth/register` takes exactly `officer_number`, `full_name`, `username` and `password` (12 characters or more); nothing else is accepted, so a role, clearance or station can never be asked for. It works only for an officer who is in the register, whose name matches and who has no account yet; every refusal is the same `422` message. The login starts as Viewer with `public` clearance at the officer's station (from the register) and is answered `201 { username, display_name, org_role, station, message }`. At most `MAX_SIGNUPS_PER_IP` attempts per `SIGNUP_WINDOW_MINUTES` from one address (`429` with `Retry-After`); `404` when `SELF_REGISTRATION=false`. The Super Admin and the Administrators and Supervisors of the station get a notice of kind `account.self_registered`.

`POST /api/v1/people/accounts/{id}/clearance` with `{ "clearance", "reason" }` raises or lowers a person's clearance: only people below the caller's role, at the caller's station (a Super Admin anywhere), never one's own, never above the caller's own clearance, with a reason kept as a `clearance_changed` entry of the access history. Each account row says what the caller may do in `can.change_clearance` and `can.allowed_clearances`.

## 5. The profile of a login

`GET /api/auth/profile` returns the caller's own profile: the official details from the register (`officer_number`, `rank`, `stations`, `display_name`, `org_role`, `clearance`: read-only) and `email`, `phone`, `job_title`, `profile_updated_at`. `POST /api/auth/profile` with `{ email, phone, job_title }` updates only the caller's own profile (there is no id: nobody can change another person's; any other field is refused with `422`; an empty value clears a field; `email` and `phone` must look right). The audit event `user.profile_updated` lists the fields that changed, never their values. `POST /api/auth/register` also accepts optional `email` and `phone`. `GET /api/auth/me` carries the same three fields and `profile_updated_at` (null until the person has saved their profile once: the dashboard asks for it until then). `GET /api/v1/people/accounts` rows carry `email`, `phone` and `job_title` for the people above.

`POST /api/auth/profile/photo` (multipart, one field `file`) sets the caller's own profile photo; `POST /api/auth/profile/photo/remove` takes it off; `GET /api/auth/photo/{user_id}` returns the small JPEG (`404` when there is none, or the person is in another organisation; `401` when not logged in; `X-Content-Type-Options: nosniff`). Only JPEG, PNG and WebP are accepted, at most 2 MB and 24 million pixels; the server decodes the picture and draws it again as a 256 x 256 JPEG, so metadata and anything appended to the file are gone. Refusals are `422` with a message. People in the API (`Person`, the People list rows, `/auth/me`, `/auth/profile`) carry `photo` or `photo_updated_at`, which change whenever the photo does.

## 6. Chat inside a case

All under `/api/v1/cases/{case_id}/chat`, and only for the people on the case's team (anyone else, including a Supervisor who only oversees the case, gets `404`). `GET /threads` lists the conversations as the caller sees them: the team (`key: "group"`) and one with each other active member (`key` is that person's id), each with its latest message and `unread`. `GET /messages?with=<key>&after=<message id>&limit=` returns one conversation, oldest first (the latest `limit`, or those after `after`). `POST /messages` with `{ "to": <person id or null>, "body": 1 to 4000 characters }` writes to the team or privately (`422` for an empty or over-long message, for oneself or somebody not on the team; `403` once the case is archived). `POST /read` with `{ "thread", "up_to" }` says how far the caller has read (and clears that conversation's notice). A message is permanent: `PUT`, `PATCH` and `DELETE` answer `405` and the database refuses them. The case detail carries `can.chat` (is on the team) and `can.write_chat` (and the case is not archived). A message notifies the other member(s) with kind `chat.message`, once per unread conversation. The audit event `cm.chat.sent` records the case, team or private, and the length, never the text; reading is not audited (the screens ask every few seconds).
