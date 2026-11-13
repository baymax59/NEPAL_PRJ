# Step 15.2: Case Management evidence (phase CM-2)

> **Partly superseded (2026-11-10).** Evidence, custody, integrity checks and sealing described here still exist unchanged; they now belong to the case (a folder, a file number) instead of a repository and a commit. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md). Read 'commit' as 'history entry'.

Status: **done and verified** (2026-11-07). 436 backend tests pass (60 new). This phase is the **API only**: the screens come in phase CM-4. All test data is fictional. **Nothing was created in the development database**: evidence there could never be removed (by design), and the demo case `KH-2026-0001` is kept for phase CM-8.

Part 2 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It builds on [15.1, the repository core](15-1-repository-core.md).

## 1. What this phase does

Cases can now hold **evidence**: photos, screenshots, statements, bank statements, call records, recordings, device images, any file. Evidence is tamper-evident and never deleted.

| Idea | In plain words | How it is built |
|---|---|---|
| **Exhibit** | One piece of evidence, e.g. `EV-0003` | `evidence_items`: title, type, classification, where it came from, who collected it and when |
| **Original** | The file exactly as received. It never changes | `evidence_versions`: **exactly one** per exhibit (the database refuses a second one) |
| **Fingerprint** | The file's SHA-256: change one byte and it changes completely | computed while the file arrives; recorded with the exhibit, in its commit and in its custody record |
| **Write-once store** | Where the files are kept | each file is stored **once**, under its fingerprint (`objects/ab/cd/<sha256>`). It is never overwritten and is made read-only. The same file uploaded twice is stored once |
| **Commit** | Adding an exhibit is a saved change, like a note | change type `evidence_added`; same branch rules and "reload and try again" protection as other commits |
| **Derived artifact** | A transcription, analysis or correction of an exhibit | a note or analysis that names the exhibit in `derived_from`; the original stays untouched |
| **Chain of custody** | Who had the exhibit, when, and what was done with it | `chain_of_custody_events`: collected, ingested, transferred, acknowledged/declined, accessed, verified, sealed/unsealed |
| **Acknowledged transfer** | A handover is complete only when the receiver confirms it | the receiver's confirmation re-checks the fingerprint, proving the file arrived intact |
| **Integrity check** | "Is the stored file still exactly what was received?" | recompute the SHA-256 and compare: `match`, `mismatch` (changed) or `missing` |
| **Sealing** | Hide a sensitive exhibit (e.g. a protected witness) | only the supervisor and administrators still see it; nothing is removed; sealing and unsealing are custody events |
| **Download link** | How a file is opened | a link that works **once**, for **5 minutes**, for **one person**; the fingerprint is checked before sending |
| **Folders** | A GitHub-like file explorer per case | virtual folders: suggested by the case type, or made by the paths of entries |

## 2. Why it is needed

Specification §9 (evidence and files), §11 (evidence at a historical state), §20 (immutability and chain of custody) and acceptance steps **4** (evidence uploaded and committed) and **15** (integrity checks succeed). It is also the base for Case Intelligence inside a case (CM-5, which reads evidence text), integrations (CM-6, which add evidence references) and reports (CM-7, which list evidence, hashes and custody).

## 3. Files created or changed

```
backend/app/casemgmt/
├─ filetypes.py        NEW  what a file really is, from its first bytes; disguised files refused
├─ storage.py          NEW  the write-once evidence store (local folder now; S3 Object Lock later, D14)
├─ evidence.py         NEW  adding exhibits, who sees them, integrity, sealing, download links
├─ custody.py          NEW  chain of custody: transfers, acknowledgements, access records
├─ evidence_views.py   NEW  read-only views: lists, details, folder tree, integrity report
├─ evidence_api.py     NEW  13 endpoints under /api/v1
├─ models.py, enums.py, errors.py, schemas.py   6 new tables; new value lists; 410/413/415 errors; request/response shapes
├─ engine.py           commits: "derived_from"; the branch checks shared with uploads (writable_branch)
├─ access.py           sealed / too highly classified evidence is hidden from views
├─ queries.py, api.py  snapshots, comparisons, commit details hide what the viewer may not see; evidence count in the registry
└─ case_types.py       suggested evidence types
backend/alembic/versions/0009_case_management_evidence.py   the tables and 7 more database rules
backend/app/documents/extract.py   extract_known(): text of a stored PDF or Word file (previews)
backend/app/core/config.py         EVIDENCE_DIR, MAX_EVIDENCE_MB, EVIDENCE_DOWNLOAD_MINUTES, EVIDENCE_ACCEPT_PROGRAMS
backend/app/retention.py           Case Management audit events are never deleted by retention (a conflict found in this phase)
backend/app/readiness.py, scripts/readiness_check.py   new check: evidence store not in a cloud-synced folder
backend/scripts/verify_evidence.py   NEW  the daily integrity check of every stored file
backend/tests/test_cm_evidence.py, test_cm_custody_integrity.py, test_cm_filetypes.py   59 tests (+1 in test_retention.py)
deploy/Caddyfile                   evidence uploads may be up to 110 MB (other API requests: 1 MB)
docker-compose.yml, .env.example   the new settings
docs/DECISIONS.md                  NEW decision D14: evidence storage
```

## 4. Packages

None new.

## 5. Commands

```powershell
cd backend
uv run alembic upgrade head        # adds the evidence tables (already done on this computer)
uv run pytest tests/test_cm_evidence.py tests/test_cm_custody_integrity.py tests/test_cm_filetypes.py -q

# The daily integrity check (exit code 1 if any file changed or is missing): schedule it on the server.
uv run python -m scripts.verify_evidence --by admin
```

After a new migration, rebuild the Docker version: `docker compose --profile app up -d --build` (from the project folder).

**Trying the API:** as in [15.1](15-1-repository-core.md#5-commands): http://127.0.0.1:8000/docs, section **case management: evidence**. Anything you add there is **permanent** in that database.

## 6. How it works

### Adding an exhibit (`POST /api/v1/repositories/{id}/evidence`)

A form upload (`multipart/form-data`) with the file and: `branch_id`, `expected_head` (the head you last saw), `folder` (e.g. `digital-evidence/screenshots`), `title`, and optionally `name`, `evidence_type`, `description`, `classification`, `source`, `collected_at` (**with a timezone**, e.g. `2026-11-02T14:30:00+05:30`), `collected_by`, `collection_authority`, `source_system`, `source_record_id`, `source_hash`, `message`.

1. The file is received into `incoming/`, hashed on the way; over the size limit or empty: refused.
2. **Checks:** branch rules (lead on `main`, others on their own branches; analysts add analyses, not original evidence; viewers and supervisors don't add evidence), the head is still current (else 409), the path is free (originals are never replaced), the classification is at least the case's and at most your clearance, and the **content matches the name**.
3. Only then is the file moved into the store, under its fingerprint, read-only. A refused upload leaves nothing behind.
4. One transaction records: the exhibit `EV-…`, its original version, the commit, custody events `collected` (if collection details were given) and `ingested`, and the provenance (if `source_system` was given).
5. If the case already has an exhibit with the same bytes, the answer lists it under `duplicates` (both stay: the same file can be two exhibits, e.g. found on two phones).

### File types: decided from the bytes

The first bytes of a file say what it is (a PDF starts with `%PDF-`, a PNG with `\x89PNG`…). About 40 kinds are recognised, including phone photos (HEIC), call recordings (AMR), packet captures, EnCase images (E01) and SQLite databases (e.g. chat exports).

| Upload | Result |
|---|---|
| Content agrees with the name | accepted |
| A program named `statement.pdf`, text named `photo.jpg` | **refused (415)**: renamed files are what this guards against |
| A disk or memory image (`.dd`, `.raw`, `.img`, `.mem`), which has no signature | accepted as raw data |
| A program with its real name (`.exe`, `.apk`), a script, an HTML page, an SVG | accepted, marked **active content**: never previewed or opened; downloads are always plain data. `EVIDENCE_ACCEPT_PROGRAMS=false` refuses programs (D14) |

### Who sees an exhibit

You see an exhibit if you can open a repository whose history contains the commit that added it, your clearance covers the exhibit's classification, and it isn't sealed (or you are the case's supervisor or an administrator). So:

- A clone **inherits** the evidence added before its source commit: same exhibit, nothing copied.
- Evidence added to V1 **after** V2's source commit is not in V2. The lead, now working in V2, gets **404**; the supervisor and administrators still see it.
- Anything you may not see answers **404, exactly as for something that doesn't exist**, and is audited as `denied`. Sealed exhibits are also left out of lists, folders, snapshots, comparisons and commit details.

### Chain of custody (`GET`/`POST /api/v1/evidence/{id}/custody`)

| Action | Who | What happens |
|---|---|---|
| (added) | the uploader | `ingested`, with the fingerprint; the uploader is the first custodian. `collected` records the collection details given |
| `transfer` to an officer (`to_user_id`, `reason`, `method`, `authorization_ref`) | the current custodian, the supervisor, an admin | `transferred`, **pending**: the sender stays custodian. Only one transfer at a time (409). The receiver must be able to see the exhibit |
| `acknowledge` (`transfer_event_id`) | the receiver only | the fingerprint is re-checked and recorded; `acknowledged`; the receiver becomes custodian |
| `decline` (`transfer_event_id`, `reason`) | the receiver, the sender or the supervisor | `declined`; custody doesn't change |
| `transfer` to an outside body (`to_external`, `receipt_reference`) | as above | complete when recorded (the receipt is the acknowledgement). Bringing it back is a transfer to an officer, recorded by the supervisor |
| download / preview | anyone who can see it | `accessed`, with the fingerprint checked at that moment |
| verify | anyone who can see it | `verified`, with the result |
| seal / unseal (`reason`) | supervisor, admin | `sealed` / `unsealed` |

Times are stored in UTC, with the timezone they were given in. Events are never edited: a mistake is corrected by a new event.

### Integrity

- `POST /api/v1/evidence/{id}/verify` recomputes the fingerprint now: `match`, `mismatch` or `missing`, recorded with who checked and when.
- **Before any download or preview** the fingerprint is checked. A changed or missing file is **not sent**; the failure is recorded (even though the request is refused) and appears in the administrators' report.
- `GET /api/v1/admin/evidence-integrity`: every exhibit with its latest check, **failures first**, then never-checked ones.
- `scripts.verify_evidence` checks every stored file; schedule it daily.
- A test deliberately changes one word in a stored file: verification reports `mismatch`, the download is refused, and the report lists it first.

### Downloads and previews

- `POST /api/v1/evidence/{id}/download-token` gives a link like `/api/v1/evidence-downloads/<token>`. It works **once**, for **5 minutes**, for **the person it was made for**, and needs no login header (so a browser can follow it). When it is used, that person's access is checked **again**: if they were removed from the case, or the exhibit was sealed meanwhile, it fails. The file is sent as an **attachment**, as plain data (`application/octet-stream`, `nosniff`), never displayed by the browser.
- The link's signing key is separate from the login key: a download link can't be used to log in, and a login can't be used as a download link (tested).
- `GET /api/v1/evidence/{id}/preview`: text files, and the text of PDFs and Word files (up to 25 MB, 200,000 characters). Images, audio and video: "download it" for now (image previews come with the screens, CM-4). Active content: **never**.

### Derived artifacts

A commit change can name its sources: `{"op": "add", "path": "cdr-analysis/call-network", "artifact_type": "analysis", "content": {...}, "derived_from": ["cdr-analysis/call-records.csv"]}`. `GET /api/v1/evidence/{id}/versions` shows the original and every analysis, transcription or note derived from it (that you can see). Revising an original is refused: "original evidence never changes: add an analysis that refers to it".

### Folders (`GET /api/v1/repositories/{id}/tree?ref=main&path=`)

The folders and entries directly under a path, at a branch or any historical commit. At the top, the case type's suggested folders are listed even when empty (e.g. for cyber fraud: `complainant`, `digital-evidence`, `cdr-analysis`, `ipdr-analysis`, `osint`…). Any case type works; unknown types get the general folders.

### "Nothing is deleted": the evidence layers

| Layer | Evidence, in this phase |
|---|---|
| 1. API | no delete routes. DELETE, PUT, PATCH, `…/delete`, `…/overwrite` on evidence answer **405** and are audited against the exhibit (`KH-2026-0001/EV-0001`) |
| 2. Services | no function changes or removes an exhibit, its file, its custody or its checks |
| 3. Database | 5 more permanent tables (objects, versions, provenance, custody, checks); exhibits may only change their seal fields; an exhibit can't get a second version; its version must come from a commit of its own case. Total: 27 rules |
| 4. Storage | files never overwritten, read-only, re-hashed before reuse. **Against server administrators the local folder only detects changes**: real write-once storage is decision D14 |
| 5. Detection | integrity checks before every access, on request and daily |

### Audit events

`cm.evidence.added`, `cm.evidence.list`, `cm.tree.read`, `cm.evidence.view`, `cm.evidence.versions`, `cm.custody.read`, `cm.custody.transferred`, `cm.custody.acknowledged`, `cm.custody.declined`, `cm.evidence.verified`, `cm.evidence.download_link`, `cm.evidence.downloaded`, `cm.evidence.previewed`, `cm.evidence.sealed`, `cm.evidence.unsealed`, `cm.admin.evidence_integrity`, `cm.evidence.integrity_sweep` (the script). File names are never written to the audit log (they can contain names of people); exhibits are named by case and exhibit number. Case Management audit events are now excluded from audit retention.

## 7. Endpoints in this phase

| Area | Endpoints |
|---|---|
| In a repository | `POST /api/v1/repositories/{id}/evidence` (upload), `GET …/evidence?ref=&folder=`, `GET …/tree?ref=&path=` |
| One exhibit | `GET /api/v1/evidence/{id}`, `GET …/versions`, `GET`/`POST …/custody`, `POST …/verify`, `POST …/download-token`, `GET …/preview`, `POST …/seal`, `POST …/unseal` |
| Download | `GET /api/v1/evidence-downloads/{token}` (no login header; the link itself is the permission) |
| Administration | `GET /api/v1/admin/evidence-integrity` |
| Changed | commits accept `derived_from`; `GET /api/v1/case-types` and repository pages list `evidence_types`; repository pages say `can.add_evidence`; the admin registry shows `evidence_count`; snapshots and folder views describe evidence entries (type, size, MIME type) |

40 endpoints in the module so far.

**Not in this phase yet:** image and media previews (CM-4); evidence text in search and the assistant (CM-5); adding evidence from the Log Analyzer, CDR/IPDR and OSINT systems (CM-6); malware scanning (ClamAV), write-once S3 storage, reports and exports with custody, the hash-chained audit log (CM-7). Sealing applies to exhibits; notes and analyses derived from a sealed exhibit stay visible (withdraw them if needed; sealing artifacts is planned with CM-3).

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_cm_evidence.py tests/test_cm_custody_integrity.py tests/test_cm_filetypes.py -v
```

| Test | Proves |
|---|---|
| **adding evidence** | `EV-0001`, SHA-256 and size correct, type from the bytes, commit `evidence_added` with the right parent, head moved; the file stored once under its hash, read-only; custody `collected` (time converted to UTC, timezone kept) and `ingested`; audited without the file name |
| same bytes twice | one stored file, one object row; the second exhibit lists the first as a duplicate |
| **the store never overwrites** | a second copy isn't written; a changed stored file is detected (and not "repaired"); over-limit and empty uploads leave nothing; paths outside the store refused |
| **content must match the name** | a program named `.pdf` and text named `.jpg` refused (415); empty 422; over the limit 413; nothing stored. Honestly named programs and HTML accepted and marked; programs refused when switched off |
| who may add evidence | viewers, analysts and supervisors 403; contributors only on their own branch; a stale head 409 |
| paths and details | a used path, a bad folder, a time without timezone or in the future, a classification below the case or above your clearance, a bad type: 422 |
| **originals never change** | revising evidence refused; analyses derived from it listed (two versions); withdrawing keeps it on record and in older commits |
| **history across clones** | V2 inherits the exhibit added before its source commit (no copy); the later one is 404 for the lead (identical to missing) and visible to the supervisor; strangers and other organisations 404 |
| **sealing** | only the supervisor seals; for the lead it vanishes from detail, lists, snapshots, folders, commit details and downloads, and can't be withdrawn; the supervisor still sees it; unsealing brings it back; custody events |
| classification | an exhibit above a member's clearance is invisible to them |
| folders | template folders with counts; nested folders; entries with file details; bad paths 422 |
| **deletion and overwriting** | 5 attempts: 405, audited against the exhibit; the file still verifies |
| **the database itself refuses** | 11 direct SQL attempts (change or delete objects, versions, provenance, custody, checks, exhibits; rename an exhibit) fail; a second or "v2" version fails; filing a version under another case fails; sealing is allowed |
| acceptance steps 4 and 15 | four fictional exhibits (WhatsApp screenshot, bank statement, suspicious URL, network log) committed, an assessment derived from them, every integrity check `match`; the admin report and registry agree |
| **acknowledged transfers** | pending until the receiver acknowledges; a second transfer 409; others can't acknowledge; the fingerprint recorded at receipt; the former custodian can't transfer again |
| declines and outside bodies | receiver and sender can decline; invalid transfers 422; a laboratory transfer needs a receipt; the supervisor brings it back |
| **tampering detected** | one word changed in a stored file: `mismatch`, download refused (409) and the failure kept on record, admin report lists it first; a deleted file: `missing`, preview refused |
| integrity sweep | every stored file checked; the changed one reported |
| **download links** | work once without a login header; attachment, plain data, `nosniff`, `no-store`; custody `accessed`; reuse 410; forged or expired 404; not usable as a login (and the reverse); fail after the user is removed or the exhibit sealed |
| previews | text and PDF text shown; images: "download it"; active content never; only real previews are custody events |
| file types (`test_cm_filetypes.py`) | 20 kinds recognised from their bytes; 7 disguised files refused |

## 9. Expected output

```
> uv run pytest -q
........................................................................ [ 16%]
...
436 passed in 80.59s (0:01:20)
```

The Docker version was rebuilt (`docker compose --profile app up -d --build`, then `docker compose restart web` for the new Caddyfile). Over HTTPS: the smoke test passed 8/8, and six evidence checks that create no case data passed. The new backend answers; the admin integrity report shows 0 exhibits, so nothing was added to the development database; a 2 MB evidence upload reaches the backend while other API requests are still limited to 1 MB; an invalid download link answers 404; deleting evidence answers 405 (that refusal is in the audit log, as designed). The go-live check now shows 7 of 27 items done (new: D14, and "evidence store outside cloud-synced folders", which passes).

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `415 … doesn't match its name` | The file's content isn't what its extension says | Check it's the right file. If it is, upload it with its real extension |
| `415 … Disguised files are refused` | A program with a document or image name | Upload it under its real extension (`.exe`, `.apk`…), if it is evidence |
| `413 … larger than the limit` | Over `MAX_EVIDENCE_MB` (100 MB) | Raise `MAX_EVIDENCE_MB` **and** the limit in `deploy/Caddyfile` (D14), or keep huge images on forensic storage |
| `413` from the web server, with an HTML page | Over the web server's limit | The Caddyfile limit must be a little above `MAX_EVIDENCE_MB`; restart `web` after changing it |
| `422 … needs a timezone` | `collected_at` like `2026-11-02T14:30:00` | Add the offset: `2026-11-02T14:30:00+05:30` |
| `422 … already used in this branch` | Another entry has that path | Choose another `name`. Originals are never replaced |
| `403 Analysts add analyses…` | Analysts don't add original evidence | Add an analysis with `derived_from` naming the exhibit |
| `404` for an exhibit that exists | Not in your repository's history, sealed, or above your clearance | Expected. Ask the supervisor |
| `409 … waiting for its receiver` | A transfer is pending | The receiver acknowledges or declines it first |
| `409 … doesn't match the fingerprint` on download or preview | **The stored file changed or is missing** | Don't repair or replace it. Report it; keep the server as it is; see the admin integrity report |
| `410 This download link was already used` | Links work once | Ask for a new link |
| `scripts.verify_evidence` exits with 1 | A changed or missing file | As above: report, don't repair |
| The Docker backend restarts in a loop after the update | Its image doesn't know migration 0009 | `docker compose --profile app up -d --build` |
