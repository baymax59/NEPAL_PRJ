# Step 14.3: Retention and backups

Status: **done and verified** (2026-11-06). 288 backend tests pass (5 new). A real backup of the running system was taken, checked, and **restored into a new, empty database that then passed the smoke test**.

Part 3 of the 5 parts of Step 14.

## 1. What this module does

**Retention** (`scripts.retention`, run daily):
- Uploaded "new case" documents are deleted after **30 days** (`UPLOAD_RETENTION_DAYS`), with everything derived from them (passages, AI embeddings, the stored file).
- Audit entries are deleted after `AUDIT_RETENTION_DAYS` **only if your organisation sets it**. Until then they are kept: how long an audit trail must be kept is a legal and policy decision, not a technical one.
- `--dry-run` shows what is due without deleting anything. Every run is recorded in the audit log.

**Backups** (`docker compose --profile backup run --rm backup`):
- The whole database, the uploads, and the web server's state (including its certificate authority's private key), in a dated folder, with checksums and a row count per table.
- Backups older than 14 days are removed (`BACKUP_KEEP_DAYS`).

**Restores** (`deploy/restore.sh`):
- `check <backup>` restores into a temporary database, compares every table's row count with the backup, and deletes it again. It changes nothing.
- `apply <backup>` replaces the database and the uploads with the backup.

## 2. Why it is needed

- **Keep personal data no longer than needed.** Uploads are new case documents: with police records, often FIRs naming complainants and accused. Keeping them indefinitely "just in case" is what data protection law (India's Digital Personal Data Protection Act, 2023) and police data policies generally forbid. The exact periods must come from your organisation (14.5).
- **A backup that has never been restored is a hope, not a backup.** The check mode makes restoring routine and harmless. This step also proved a complete restore works (section 8).

## 3. Files created or changed

```
backend/app/retention.py            what is due, deletion through the existing delete_upload, audit record
backend/scripts/retention.py        the daily job (--dry-run)
backend/app/core/config.py          + upload_retention_days (30), audit_retention_days (not set = keep)
backend/tests/test_retention.py     4 tests;  test_hardening.py + 1 (empty setting = keep)
deploy/backup.sh                    database dump, archives, row counts, checksums, old backups removed
deploy/restore.sh                   check (temporary database) and apply
docker-compose.yml                  + "backup" service (profile backup); backend gets the retention settings
.gitattributes                      *.sh always with Unix line endings (a Windows line ending breaks them in Linux)
.gitignore                          + backups/
.env.example                        + UPLOAD_RETENTION_DAYS, AUDIT_RETENTION_DAYS, BACKUP_DIR, BACKUP_KEEP_DAYS
```

## 4. Packages

None. The backup service uses the database's own image (`pgvector/pgvector:0.8.7-pg17`), so `pg_dump` and `pg_restore` always match the server's PostgreSQL version.

## 5. Commands

```powershell
# Retention: see first, then delete
docker compose --profile app run --rm backend python -m scripts.retention --dry-run
docker compose --profile app run --rm backend python -m scripts.retention

# Back up now; then check the backup restores (changes nothing)
docker compose --profile backup run --rm backup
docker compose --profile backup run --rm backup /deploy/restore.sh check 2026-11-06T094931Z

# Disaster recovery: put a backup back (replaces the database and the uploads)
docker compose --profile app stop backend web
docker compose --profile backup run --rm backup /deploy/restore.sh apply 2026-11-06T094931Z
docker compose --profile app up -d
```

**Running them every night.** This is a decision for whoever runs the server, so nothing is scheduled automatically. On Windows (Task Scheduler), with the project in `C:\case-search`:

```powershell
schtasks /Create /TN "Case search backup"    /SC DAILY /ST 02:00 /TR "docker compose -f C:\case-search\docker-compose.yml --profile backup run --rm backup"
schtasks /Create /TN "Case search retention" /SC DAILY /ST 02:30 /TR "docker compose -f C:\case-search\docker-compose.yml --profile app run --rm backend python -m scripts.retention"
```

On Linux (`crontab -e`), with the project in `/opt/case-search`:

```
0 2 * * *  cd /opt/case-search && docker compose --profile backup run --rm backup >> /var/log/case-search-backup.log 2>&1
30 2 * * * cd /opt/case-search && docker compose --profile app run --rm backend python -m scripts.retention >> /var/log/case-search-retention.log 2>&1
```

## 6. The code, explained

### `app/retention.py`

1. Works out the cut-off dates from "now" and the two settings.
2. Finds the uploads created before the cut-off and counts the audit entries before theirs (if set).
3. Unless it is a dry run: deletes each upload with the existing `delete_upload()` (Step 8: file, rows, passages, embeddings), then the audit entries in one statement.
4. Records `retention.run` in the audit log as `system:retention`, with the counts and cut-offs. That entry is new, so it is never deleted by the same run.

`AUDIT_RETENTION_DAYS` can be left empty in `.env`: Docker Compose then passes an empty value, which counts as "not set".

### `deploy/backup.sh`

| File | What | Why |
|---|---|---|
| `database.dump` | `pg_dump --format=custom` | compressed; `pg_restore` can restore it whole or table by table |
| `row-counts.txt` | rows per table, right after the dump | something to check a restore against |
| `uploads.tar.gz` | the `appdata` volume | uploaded documents |
| `caddy-data.tar.gz` | the `caddy_data` volume | Caddy's certificate authority and certificates (14.2): without it, every browser that trusts the old authority would need the new one |
| `SHA256SUMS` | checksums of all of the above | a damaged or altered file is detected before anything is restored |

**Not in the backup:** `.env`, which holds the secrets. Keep a copy of it somewhere as safe as a password manager. Without the same `AUDIT_SECRET`, fingerprints in the old audit log can no longer be matched to new searches; a new `JWT_SECRET` only means everyone logs in again.

### `deploy/restore.sh`

- Both modes first verify the checksums.
- `check` uses a temporary database `restore_check`. `pg_restore --exit-on-error` stops at the first problem. Every table's restored row count is compared with `row-counts.txt`, both archives are listed, and the database is dropped. Exit code 0 = passed. Rows written *during* a backup (e.g. someone using the site at 02:00) can make the audit table differ by a few rows, which is expected.
- `apply` runs `pg_restore --clean --if-exists` into the real database, then empties the uploads volume and unpacks the archive. Stop `backend` and `web` first, so nobody writes while the database is being replaced.

## 7. Security notes

- **Backups hold everything**: case records, uploads, password hashes, the audit log, and Caddy's private key. Store them on an **encrypted disk** (BitLocker on Windows, LUKS on Linux), **not in a cloud-synced folder**, and keep a second copy in another place, as your organisation's policy requires. The default `BACKUP_DIR=./backups` is inside the project folder, which on this development computer is inside OneDrive. That is acceptable only for the public Supreme Court sample.
- Retention deletion is permanent, and backups still contain deleted uploads until those backups expire (14 days by default). State this in the retention policy.

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_retention.py -v
```

| Test | Proves |
|---|---|
| old uploads deleted with their files and passages | a 31-day-old upload goes (row, passages, file); a 29-day-old one stays |
| a dry run deletes nothing | reports what is due; row and file still there |
| audit entries kept unless a period is set | not set: an 8-year-old entry stays; set to 365: it goes, a 10-day-old one stays |
| every run is audited | `retention.run` by `system:retention` with the counts |
| empty setting | `AUDIT_RETENTION_DAYS=""` (how Compose passes an unset value) means keep |

Checks on the running system:

| Check | Result |
|---|---|
| Backup | 9 s: `database.dump` 8 MB, 14 tables, 6,804 rows, archives, checksums |
| `restore.sh check` | checksums OK; all 14 tables equal (e.g. `document_chunks` 2,672 = 2,672); archives readable; temporary database dropped; 15 s |
| **Full restore into a new, empty database** | restored at migration `0006 (head)`; a separate backend on it passed the smoke test: login with the restored accounts, 100 cases, search in `hybrid` mode (embeddings restored), case details, login required; test database removed. Live data untouched |
| Retention dry run, in Docker and on the host | nothing due yet; "Audit entries: kept" |

## 9. Expected output

```
> docker compose --profile backup run --rm backup
Backing up to 2026-11-06T094931Z/
-rw-r--r-- 1 root root    2357 Nov  6 09:49 caddy-data.tar.gz
-rw-r--r-- 1 root root 8036755 Nov  6 09:49 database.dump
...
Tables: 14, rows: 6804
Done: 2026-11-06T094931Z

> docker compose --profile backup run --rm backup /deploy/restore.sh check 2026-11-06T094931Z
database.dump: OK
...
  cases                              100       100  ok
  document_chunks                   2672      2672  ok
...
Restore check passed: 2026-11-06T094931Z

> docker compose --profile app run --rm backend python -m scripts.retention --dry-run
Due for deletion (dry run, nothing deleted): 0 upload(s) older than 30 days (before 2026-10-07 09:51 UTC)
Audit entries: kept (AUDIT_RETENTION_DAYS is not set; your organisation decides the period)
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `set: Illegal option -` or `\r: not found` | The script was saved with Windows line endings | `.gitattributes` prevents this for files from Git. Otherwise convert the file to Unix (LF) line endings |
| `pg_dump: error: server version mismatch` | Backup service image differs from the database image | Keep both on the same image (`docker-compose.yml`) |
| `FAILED` in the checksum check | A backup file is damaged or was changed | Use another backup; find out why (disk, copying, tampering) |
| `restore.sh check` reports DIFFERENT for `audit_events` | Someone used the site during the backup | Expected for the audit table; any other table: investigate |
| `apply` hangs | The application is still connected to the database | `docker compose --profile app stop backend web` first |
| `No backup folder …` | Wrong name, or `BACKUP_DIR` points elsewhere | `dir backups` (or your `BACKUP_DIR`); names look like `2026-11-06T094931Z` |
| Retention deletes nothing although uploads are old | Wrong days setting, or the job runs against another database | `--dry-run` shows the cut-off date it uses |
