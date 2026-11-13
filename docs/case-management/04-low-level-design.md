# 04. Low-level design

> **Earlier design (superseded on 2026-11-10).** This document describes the first, git-style design of Case Management: an original repository, clones, branches, commits, reviews, merges and invitations. The owner asked for that to be removed completely and replaced by a plain case (permanent folders made at registration, files with versions, a team the Investigator builds directly, one numbered history). **The current design is in [13-plain-case-design.md](13-plain-case-design.md).** It is kept here for the record: where it says repository, clone, branch, commit, review or invitation, read the plain case instead.

For developers. Table details are in [05](05-database-er.md), endpoints in [06](06-api-contracts.md).

## 1. Identifiers

| Thing | Database key | Shown to people |
|---|---|---|
| Case family | UUID | `KH-2026-0001`: organisation prefix, year, sequence per organisation and year |
| Repository | UUID | `KH-2026-0001-ROOT`, `-V1`, `-V2`… (version number per family) |
| Commit | **SHA-256 of its content** (64 hex) | first 10 characters, monospaced |
| Snapshot | SHA-256 of its manifest | (internal) |
| Evidence object (bytes) | SHA-256 of the bytes | first 12 characters |
| Evidence item / version, artifact / version | UUID | `EV-0007 v1`, `NOTE-0003 v2` |
| Official reference | separate table | `FIR 0123/2026, Example Nagar PS`: never used as a key |

## 2. Repository engine

### 2.1 Snapshots: what a commit contains

A **snapshot** is the complete logical content of a repository at a commit: a **manifest** listing every entry.

```json
[{"path": "digital-evidence/screenshots/whatsapp-message.png", "kind": "evidence",
  "item_id": "…", "version_id": "…", "sha256": "…", "status": "active"},
 {"path": "investigation-notes/initial-assessment.md", "kind": "note",
  "item_id": "…", "version_id": "…", "sha256": "…", "status": "active"}]
```

- Entries are sorted by `path`. The manifest's hash is the SHA-256 of its canonical JSON (sorted keys, no spaces).
- Snapshots are stored **once per hash** (`commit_snapshots`) and shared by every commit with the same content. This is the "copy-on-write" the specification asks for: cloning or branching copies no files and no rows of content.
- An entry is never removed. "This note was wrong" becomes a **new version** of the note, or `status: "withdrawn"` with a reason, in a **new** commit. The old commit still shows the old state.

### 2.2 Commits

```
commit_id = sha256(canonical_json({
    "repository_id", "branch_id", "parents": [ordered parent commit ids],
    "author_id", "timestamp": UTC ISO-8601 with microseconds, "message", "change_type",
    "snapshot_hash", "metadata_digest": sha256 of the commit's metadata JSON }))
```

- **Generated on the server only.** Clients never send commit IDs for new commits.
- **Parents** are stored in `commit_parents (commit_id, parent_id, position)`. A parent must already exist, and commits are never updated, so **cycles are impossible by construction** (a commit can only point at older commits). A database trigger also rejects a parent that isn't older.
- One parent = an ordinary commit. Two parents = a **reviewed merge**. Zero parents = only the `ROOT` initial commit.
- `change_type` is one of: `case_created`, `clone_base`, `evidence_added`, `artifact_added`, `artifact_revised`, `entry_withdrawn`, `branch_created`, `findings_merged`, `link_added`, `integration_import`, `timeline_generated`, `report_generated`, `status_changed`.

### 2.3 Branches

- `repository_branches (id, repository_id, name, type, source_commit_id, head_commit_id, status, version, …)`.
- **The only mutable pointer in the engine is a branch head**, and every move is also written to `branch_head_events` (old head, new head, actor, time, reason).
- **Optimistic concurrency:** the client sends the head it last saw (`expected_head`). The update is `UPDATE … SET head_commit_id = :new, version = version + 1 WHERE id = :branch AND head_commit_id = :expected`. If 0 rows change, the API answers `409 Conflict` with the current head, and nobody's work is silently overwritten.
- A head may only move **forward**: the new head must have the old head as an ancestor. This rules out hard resets. *(Built in CM-1: a database trigger accepts a head move only to a new commit of the same repository whose parent is the old head, and only while the repository is active.)*
- Branch status: `active` → `inactive` / `superseded` / `merged`. Branches are never deleted.
- `main` is **protected**: only the lead investigator, through approved reviews, or the clone/case-creation steps may move it, as configured.

### 2.4 Repositories and cloning

`case_repositories (id, case_family_id, version_number, kind: root|clone, parent_repository_id, source_commit_id, source_branch_id, reason, status, created_by, created_at)`

- `ROOT` (version 0) receives the initial commit only and is then **frozen**. Its creation metadata never changes.
- **Clone algorithm** (`POST /repositories/{id}/clones`, one serialisable transaction):
  1. Load the source repository and check the user may **clone** from it (§6).
  2. Check that `source_commit` is **reachable** from one of the source repository's branch heads (an ancestor). This prevents cloning from a sibling's history the user may not see.
  3. Lock the case family row (`SELECT … FOR UPDATE`) and allocate the next version number.
  4. Insert the new repository: parent repository, source commit, source branch, reason (required, 10–1000 characters), creator.
  5. Insert a **clone base commit** in the new repository, with parent = `source_commit` and snapshot = the source commit's snapshot (same hash, no copying).
  6. Create branch `main` with its head at the clone base commit.
  7. Add memberships from the request: the new assigned investigator becomes **lead**. Contributors are **not** copied from the parent automatically; each copied membership is validated against policy.
  8. Move the user's **active assignment** for the family to the new repository. Mark the previous clone `superseded`: a status change plus an event, nothing else.
  9. Write the audit events: `cm.repository.cloned`, `cm.assignment.moved`, `cm.repository.status_changed` (all Case Management events start with `cm.`).
  If any step fails, the whole transaction rolls back and no partial clone exists.
- **Inherited history:** a clone's history is everything reachable from its branch heads. That includes commits in ancestor repositories **up to the source commit**, and none of the sibling's later commits.

### 2.5 History, compare and historical views (read-only)

- **History** of a branch: a recursive query over `commit_parents` from the head, newest first, paginated.
- **Compare A…B:** load both manifests and report every path as `added`, `revised` (different version), `withdrawn` or `unchanged`, plus the commits between them.
- **Historical view:** `GET /repositories/{id}/snapshot/{commit}` returns the manifest at that commit. Every UI action on it is read-only. Its only "write" button is **Clone from this commit**.

### 2.6 Merging approved findings

1. Find the **merge base**: the nearest common ancestor of the review's source branch head and the target branch head.
2. Do a three-way comparison of the manifests (base, source, target):
   - entries changed only on the source are taken;
   - entries changed only on the target are kept;
   - the **same path changed differently on both sides is a conflict**.
3. With **no conflicts**, create a commit with **two parents** (target head, source head), `change_type = findings_merged`, linked to the review decision.
4. With **conflicts**, nothing is merged. The review shows the conflicting paths. The author resolves them by committing **new versions** on the source branch, which updates the review for another decision. Nothing is overwritten.

## 3. Evidence

### 3.1 Three layers

| Layer | Table | Changes? |
|---|---|---|
| **Object**: the bytes | `evidence_objects (sha256, size, mime_type, storage_key, stored_at)` | **never** |
| **Version**: one state of an exhibit or artifact | `evidence_versions` / `artifact_versions` | **never**; a new version is a new row |
| **Item**: the exhibit or artifact as a whole | `evidence_items` / `artifacts` | only status fields (`sealed`), each change with an event |

An **evidence item** is an original exhibit. It has exactly one original version, and its bytes are immutable. **Artifacts** are everything people write or derive: notes, analyses, transcriptions, timelines, reports. They can have many versions, each pointing to the original evidence it was derived from (`derived_from_version_id`).

### 3.2 Adding evidence

1. Check the size limit, then stream the upload to a temporary file while computing SHA-256.
2. Check that the content type matches the bytes (magic numbers), and optionally scan for malware (ClamAV).
3. `EvidenceStore.put(sha256, file)`. Local store: `objects/ab/cd/<sha256>`, written with exclusive create and then made read-only; an existing hash is **not rewritten**. S3: `PutObject` with Object Lock retention in COMPLIANCE mode.
4. Insert the object (if new), item, version and **custody event** (`ingested`: collector, collection time, authority/reference, source system, hash).
5. Create a commit on the chosen branch that adds the entry under the chosen folder path.
6. Queue Case Intelligence processing. This is skipped if the object hash was processed before. *(CM-5.)*

*Built in CM-2 (`evidence.py`, `storage.py`, `filetypes.py`):* steps 1–5. The content check refuses files whose bytes contradict their name; honestly named programs, scripts, HTML and SVG are accepted and marked as active content (never previewed). A refused upload never reaches the store. The version's ID is chosen before the commit, so the snapshot can name the version and the version its commit. ClamAV scanning and S3 Object Lock are not built yet (decision D14).

### 3.3 Integrity verification

`POST /evidence/{id}/verify`:
1. Re-read the bytes from the store and recompute SHA-256.
2. Compare with the recorded hash.
3. Write an `evidence_integrity_checks` row (result, checker, time) and a custody event (`verified`).

A periodic job verifies everything and reports failures to administrators. A test deliberately changes a stored file and expects **failure**.

### 3.4 Sealing, downloads, previews

- **Sealed** evidence disappears from general investigator views and from Case Intelligence. It remains visible to those with the `seal` permission and to auditors. Sealing and unsealing are events with a reason; nothing is removed.
- **Downloads** use short-lived signed tokens (HMAC, 5 minutes, bound to user and version), and are logged as custody events (`accessed`).
- **Previews:** text is shown as text, images are re-encoded to PNG on the server, and PDFs are shown as extracted text and page images. HTML, SVG and scripts are **never** rendered inline. *(CM-2: text, and the text of PDF and Word files; images and page images come with the screens, CM-4.)*
- *Built in CM-2:* download links are single-use (the link's ID is unique in the custody events), signed with a key derived from, but different from, the login key, and access is re-checked when they are used. The fingerprint is re-checked before every download or preview; a changed file is not sent, and the failed check is kept.

## 4. Chain of custody

`chain_of_custody_events (evidence_version_id, event_type, from_custodian, to_custodian, at (UTC) + original timezone, reason, method, verification_sha256, acknowledged_by, acknowledged_at, authorization_ref)`

The event types are: `collected`, `ingested`, `transferred`, `accessed`, `verified`, `sealed`, `unsealed`, `exported`. A transfer is complete only when the receiver **acknowledges** it, which adds a second event. This table is append-only; corrections are new events.

*Built in CM-2 (`custody.py`):* the acknowledgement is its own event (`acknowledged`, with `related_event_id` pointing at the transfer and the fingerprint re-checked at that moment), and so is `declined` (refused by the receiver or withdrawn by the sender or supervisor); rows are never updated. Custodians are users (`*_custodian_id`) or outside bodies (`*_custodian_name`); a transfer to an outside body needs a receipt reference and is complete when recorded.

## 5. Collaboration and review

- **Members:** `repository_members (repository_id, user_id, role: lead|contributor|analyst|viewer, branch_scope, granted_by, granted_at, revoked_by, revoked_at)`. Revoking sets `revoked_at`; every past contribution stays attributed.
- **Invitations:** `pending` → (`approved` by supervisor, when policy requires) → `accepted` | `declined` | `expired` | `cancelled`.
  - The invitee must be in the **same organisation** with sufficient **clearance**.
  - A lead cannot invite external users or grant a role above their own.
  - Nobody can change their own membership.
- **Tasks:** an assignee, a status (`open` → `in_progress` → `done` / `cancelled`) and a link to a branch or commit.
- **Notes** are artifacts with versions: an edit is a new version.
- **Comments** are append-only; an "edited" comment is a new comment referencing the old one.
- **Review requests:** `draft` → `submitted` → `changes_requested` ⇄ `submitted` → `approved` → `merged`; or → `rejected`; or → `superseded`.
  - Each decision is a `review_decisions` row (reviewer, decision, comment, time).
  - Rejected content stays on its branch and in history.

*Built in CM-3 (`members.py`, `tasks.py`, `comments.py`, `reviews.py`, `merging.py`):*
- **Invitations:** `awaiting_approval` → `pending` → `accepted`, or `refused` / `declined` / `cancelled` / `expired` (14 days). Approval is needed for a lead's invitations of contributors and analysts (`CM_INVITATION_APPROVAL`, decision D13). An organisation role limits the repository roles: viewer → viewer; analyst → analyst or viewer; others → contributor, analyst or viewer.
- **Assigned branches** (`branch_scope`, spec §12 "work on assigned branches"): set with the invitation, copied into the membership, never changed. Writing to a branch (commits, evidence, bringing it up to date, opening a review) is allowed for the lead, the branch's creator and members it is assigned to.
- **Access history:** `authorization_events` records every membership granted or revoked, including those a clone grants and ends.
- **Reviews:** a decision names the source head it was about; a merge needs the latest decision to be an approval of the current head. A branch with no content changes can't be reviewed. One open review per branch.
- **Resolving conflicts** (§2.6 step 4, made concrete): the author brings the target's changes into the branch with a two-parent commit (`branch_synced`), choosing for each conflict: mine, theirs, or a new version derived from both. Committing alone on the branch couldn't resolve a conflict, because the merge base wouldn't move.
- **One path, one entry:** a new path can't be added on one branch while another branch of the repository uses it, so add/add conflicts can't occur.

## 6. Authorisation

### 6.1 Inputs to every decision

1. The user's **organisation** (tenant).
2. The **organisation role**: platform_admin, supervisor, investigator, analyst, viewer/auditor.
3. The **repository membership role**: lead, contributor, analyst, viewer.
4. **Clearance** ≥ the case's classification (public < internal < restricted < confidential, as now).
5. For commits: whether the commit is **reachable** from a repository the user may see.

### 6.2 Who sees which repository (applied inside the SQL of every query, never by filtering afterwards)

```
platform_admin  : every repository in their organisation, within their clearance
supervisor      : repositories of families they supervise
everyone else   : repositories where they have an active (not revoked) membership
                  + ancestors of those repositories, **read-only, up to the source commit**
```

Anything else returns **404, exactly as for a missing case** (the Step 10 principle), and the attempt is audited.

### 6.3 What each role may do (on repositories they can see)

| Action | Lead | Contributor | Analyst | Viewer/Auditor | Supervisor | Platform admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Read active content and history | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Commit on own branches / add evidence | ✓ | ✓ | ✓ (analysis) | – | – | – |
| Create a branch | ✓ | ✓ | ✓ | – | – | – |
| Move protected `main` (other than via an approved merge) | ✓* | – | – | – | – | – |
| Open a review request | ✓ | ✓ | ✓ | – | – | – |
| Approve or merge a review | – | – | – | – | ✓ | ✓ |
| Clone the investigation | ✓ | – | – | – | ✓ | ✓ |
| Invite contributors | ✓ (policy) | – | – | – | ✓ | ✓ |
| Seal or unseal evidence | – | – | – | – | ✓ | ✓ |
| Change statuses | ✓ (workflow) | – | – | – | ✓ | ✓ |
| See the full lineage, all clones, the audit trail | – | – | – | auditor: read | own families | ✓ |

\* The default policy allows the lead to commit directly to `main`; this can be switched to "review required".

## 7. Statuses: four separate fields

| Field | Values | Changed by |
|---|---|---|
| Official police status | `registered`, `under_investigation`, `chargesheeted`, `closed`, … (recorded from official sources) | authorised workflow / integration |
| Internal workflow status | `registered`, `open`, `under_investigation`, `pending_evidence`, `pending_review`, `approved_for_reporting`, `investigation_completed`, `closed`, `archived`, `reopened` | lead / supervisor, by an allowed-transitions table (CM-1: `engine.WORKFLOW_TRANSITIONS`; closed, archived and reopened are the supervisor's or admin's decision) |
| Clone status | `active`, `under_review`, `superseded`, `frozen`, `archived` | the engine / supervisor |
| Review status | as in §5 | the review workflow |

Every change is a `case_status_events` row. Closing a clone never closes the official case.

## 8. Audit engine: tamper-evident

- Every event gets a `sequence` (gap-free, assigned under a transaction-level advisory lock), and `prev_hash` and `hash`:

  ```
  hash = sha256(prev_hash || canonical_json(event))
  ```

- **Live pages** (*built in CM-8*): the notice stream also follows the page the browser has open (`watch=repository:<id>`, `case:<id>`, `review:<id>`, `evidence:<id>`, `admin`). Every 5 seconds it computes one row of values for that page (branch heads, statuses, memberships, task events, comments, reviews, custody, deliberate integrity checks, seals, report checks, holds, retention decisions) and sends a 16-character fingerprint when it changes; the page then re-reads its data. Reads are left out (previews, downloads, indexing), so a refresh never causes another. The scope follows `access.repository_condition`, checked at every poll.
- **Checkpoints:** every 1,000 events, or daily, `{sequence, hash, time}` is signed with HMAC (a key **outside** the database) and written to the write-once evidence store. *Built in CM-7:* the chain covers every Case Management event (`cm.*`); a database trigger assigns the sequence and both hashes as each event is written (one writer at a time), and chained events can't be changed or deleted. The similar-case search's events stay outside the chain under their retention rule. Checkpoints are signed with `CM_CHECKPOINT_KEY` by the worker (daily, or after 1,000 events) or by an administrator, and kept in the write-once store too; `POST /api/v1/admin/audit/verify` checks everything.
- **Verification** recomputes the chain from a checkpoint. Any edited, removed or re-ordered event breaks the chain from that point on.
- The existing audit rules stay: its own transaction, failures fail the request, fingerprints instead of search text, and refusals are recorded. A rejected destructive attempt is recorded as `cm.destructive_operation.rejected`.

## 9. Immutability: five layers

1. **API:** no DELETE routes for case-history resources. Any DELETE or rewrite attempt gets `405`, and is audited.
2. **Services:** no update functions for immutable records.
3. **Database:** triggers raise an error on `UPDATE`/`DELETE` of append-only tables. The application's runtime database role has **no** `DELETE` privilege on them (CM-7). *Built in CM-7:* the role `cm_runtime` (no DELETE on any case record, no UPDATE on permanent ones; grants derived from the rules by `cm_grant_runtime()`), and a login of its own for the application (`scripts.db_roles`). Migrations use the owner login.
4. **Storage:** write-once objects (S3 Object Lock in compliance mode in production).
5. **Detection:** the hash chain with external checkpoints, plus periodic evidence verification.

Layers 1–3 stop users and application bugs. Layers 4–5 stop or **detect** a database administrator going around the application, as the specification requires.

## 10. Case Intelligence inside a case

- **Text index keyed by object hash:** `object_texts (sha256, pages)` and `object_chunks (sha256, chunk_index, text, page_start, page_end, embedding, search_vector)`. They are filled once per unique object by the existing extraction, cleaning, chunking and embedding code. *Built in CM-5:* notes and analyses are indexed too (by their content's hash); a file's hash is checked before it is read (integrity check `indexing`); the timeline is built from the shared view (what every member may see), so sealed content never enters the record.
- **Repository-scoped retrieval:** take the snapshot manifest at commit C, keep the active, unsealed entries the user may see, map them to their object hashes, and search only those chunks.
- **Similar Cases:**
  1. Build a `QueryDocument` from the snapshot's case summary, notes and document text, exactly as for an upload (`similar/service.py`).
  2. Search the knowledge base and the latest snapshots of other case families the user may access.
  3. Return the results with explanations. **Link** creates a `case_links` row and a `link_added` commit.
- **Assistant:**
  1. Retrieve from the snapshot.
  2. Label the sources `S1…` with **evidence ID, version, page and commit ID**.
  3. Keep the existing citation checking and the "not found" behaviour.
- **Timeline:** run the existing date and event extraction over the snapshot's documents. Store the result as a **new version** of the artifact `timeline/timeline.json` in a `timeline_generated` commit.

## 10a. Integrations (*built in CM-6*)

- **Add to case:** the source is identified by its key (only its SHA-256 is stored), the person by their login; the person's rights apply (`writable_branch`, as for every commit). Then the source's policy (organisation, allowed kinds, legal authority where required, minimum case classification), then the finding (record ID, hash, times with a timezone, identifiers, at most 64,000 bytes of derived result).
- **Storage:** an artifact of type `import` at `imports/<source>/<folder>/<record>` and its own commit `integration_import`; the provenance in `integration_imports`, the identifiers (normal form) in `integration_indicators`. The same record again is refused (409); a changed record (new hash) is a new version of the same artifact; the same record on another branch is refused (merge instead). An imported finding can't be revised by a commit: notes refer to it, or it is withdrawn.
- **Across cases:** an identifier's matches are shown only in cases the reader can open, for findings in the history of a repository they can open, and not sealed (unless they supervise that case).
- **Connected features:** the timeline gets an entry per finding with `observed_at`; Case Intelligence reads findings like notes; the report preview lists them with their provenance; the lead gets a notice without content.

## 11. Errors and idempotency

| Situation | Answer |
|---|---|
| Not visible, or doesn't exist | `404` (the same either way) |
| Visible but not allowed | `403` |
| Branch head moved since you looked | `409`, with the current head |
| Destructive operation | `405`, audited |
| Invalid input | `422` |

Create operations accept an `Idempotency-Key` header. Repeating a request with the same key returns the first result instead of creating a duplicate. *(Built in CM-3: per user, 24 hours; the same key with a different request is refused.)*
