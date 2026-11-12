# Installation and operations guide

For whoever installs and runs Similar Case Search on a server or office computer. Everything runs in Docker; you need no Python or Node.js. Commands are for Windows PowerShell; on Linux they are the same apart from paths and the line-continuation character.

Before real police records are loaded, the decisions in [DECISIONS.md](DECISIONS.md) must have been made, and `cd backend; uv run python -m scripts.readiness_check` must report every item done.

---

## 1. What you need

| | Minimum | Notes |
|---|---|---|
| Computer | 4 CPU cores, 16 GB RAM, 30 GB free disk | 32 GB RAM if the case assistant runs on the same computer. A graphics card makes the assistant 10–50× faster but isn't required |
| Operating system | Windows 10/11 or Linux | Tested on Windows 11 with Docker Desktop |
| Docker | Docker Desktop (Windows), or Docker Engine with the Compose plugin (Linux) | |
| Disk encryption | **BitLocker** (Windows) or **LUKS** (Linux) on every disk that holds the project, the Docker data or backups | |
| Ollama | only for the case assistant | https://ollama.com/download, then `ollama pull qwen3:4b-instruct-2507-q4_K_M` (2.5 GB) |
| The embedding model | the `models` folder (130 MB) | copy it from a computer where the project ran, or download it once (step 3) |

**Do not put the project, its data or its backups in a cloud-synced folder** (OneDrive, Google Drive, Dropbox): uploads and backups would be copied to the cloud provider. Use e.g. `C:\case-search` or `/opt/case-search`.

## 2. Settings

```powershell
cd C:\case-search
copy .env.example .env
notepad .env
```

| Setting | What to put |
|---|---|
| `POSTGRES_PASSWORD`, `JWT_SECRET`, `AUDIT_SECRET` | **three different** long random values. Make each with `docker run --rm python:3.12.16-slim-trixie python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SITE_ADDRESS` | the name people will type, e.g. `cases.police.example` (default `localhost`) |
| `TLS` | `internal` (Caddy's own certificate authority) or `/certs/site.crt /certs/site.key` (your organisation's certificate, placed in `deploy\certs\`) |
| `HTTPS_PORT`, `HTTP_PORT` | `443` and `80` on a server; the defaults `8443`/`8080` for a test |
| `WEB_BIND` | `127.0.0.1` = this computer only. To serve the network, the server's own address (section 7) |
| `UPLOAD_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS` | as decided by your organisation (HANDOVER.md) |
| `BACKUP_DIR`, `BACKUP_KEEP_DAYS` | an encrypted, non-synced folder; how many days of backups to keep |

**Keep a copy of `.env`** in your organisation's password safe. It is not in the backups. The backend refuses to start if the two secrets are equal or the database password is weak.

## 3. Install

```powershell
# 1. The embedding model: copy the "models" folder into C:\case-search\models,
#    OR download it once (needs internet). On Linux first: mkdir models; sudo chown 10001 models
docker compose --profile app run --rm -e HF_HUB_OFFLINE=0 backend python -c "from app.embeddings.model import load_embedder; load_embedder(allow_download=True)"

# 2. Build and start (the first build takes several minutes; the database tables are created automatically)
docker compose --profile app up -d --build
docker compose --profile app ps                 # backend "healthy", web "Up", db "healthy"

# 3. The first administrator (the password is typed, not shown; at least 12 characters)
docker compose --profile app run --rm backend python -m scripts.create_user yourname --role admin --clearance confidential --name "Your Name"
```

Open `https://<SITE_ADDRESS>:<HTTPS_PORT>` (e.g. https://localhost:8443) and log in. With `TLS=internal`, browsers warn until they trust Caddy's certificate authority (section 7).

## 4. Load data

**The public Supreme Court sample** (for demonstrations; needs internet; about 20 minutes, mostly AI embeddings):

```powershell
docker compose --profile app run --rm backend sh -c "python -m scripts.sc_download && python -m scripts.sc_import && python -m scripts.process_documents && python -m scripts.embed_chunks && python -m scripts.extract_provisions && python -m scripts.extract_timeline"
```

**Authorised police records** (only after the decisions in HANDOVER.md; the connector is a template until the real field list is known, see `docs/steps/14-4-police-records-connector.md`):

```powershell
# Check first: nothing is stored, nothing personal is printed
docker compose --profile app run --rm -v D:\exports\2026-11:/exports/2026-11:ro backend python -m scripts.police_import --folder /exports/2026-11 --authorisation "Approved by <name>, ref <number>" --dry-run
# Import, then process the FIR documents
docker compose --profile app run --rm -v D:\exports\2026-11:/exports/2026-11:ro backend python -m scripts.police_import --folder /exports/2026-11 --authorisation "Approved by <name>, ref <number>"
docker compose --profile app run --rm backend sh -c "python -m scripts.process_documents && python -m scripts.embed_chunks && python -m scripts.extract_provisions && python -m scripts.extract_timeline"
```

## 5. Check it works

```powershell
# Caddy's certificate authority (public certificate only), to check HTTPS properly
docker compose --profile app cp web:/data/caddy/pki/authorities/local/root.crt caddy-root.crt

# From inside Docker, nothing else installed (the password is typed)
docker compose --profile app run --rm backend python -m scripts.smoke_test --url http://backend:8000 --api-only --username yourname
```

Every line should say `PASS`. If your data doesn't match the default search, add `--search "<words that occur in your cases>"`.

## 6. Daily operation

| When | What | Command |
|---|---|---|
| Every night | backup | `docker compose --profile backup run --rm backup` |
| Every night | retention | `docker compose --profile app run --rm backend python -m scripts.retention` |
| Every month | prove a backup restores | `docker compose --profile backup run --rm backup /deploy/restore.sh check <backup>` |
| Every month | known-vulnerability check | see section 8 |
| When needed | look at the audit log | in the web interface as an administrator, or `docker compose --profile app logs --since 24h backend` |

Schedule the nightly jobs with Task Scheduler or cron: the exact commands are in `docs/steps/14-3-retention-and-backups.md`, section 5.

**People joining, changing role, leaving:**

```powershell
docker compose --profile app run --rm backend python -m scripts.create_user alice --role analyst --clearance restricted --name "Alice Rao"
docker compose --profile app run --rm backend python -m scripts.create_user alice --reset-password
docker compose --profile app run --rm backend python -m scripts.create_user alice --deactivate --by yourname
docker compose --profile app run --rm backend python -m scripts.grant_access alice FIR-PS0001-2026-0042 --reason "Assigned to review" --days 30 --by yourname
```

A deactivated user can't log in, and tokens issued earlier stop working. Their audit history is kept. Every grant and deactivation is recorded in the audit log.

## 7. Serving other computers on the network

Do this with your IT department; it is the step that exposes the system.

1. **A certificate** for `SITE_ADDRESS` from your organisation's certificate authority, in `deploy\certs\` (`TLS=/certs/site.crt /certs/site.key`). The alternative is to install Caddy's `caddy-root.crt` on every client computer (e.g. by group policy); that is a decision for IT.
2. `HTTPS_PORT=443`, `HTTP_PORT=80`, `WEB_BIND=<the server's address>`; then `docker compose --profile app up -d`.
3. **Firewall**: allow 443 (and 80, which only redirects) from the office network only. Nothing else: the database (5433) stays on 127.0.0.1.
4. Once the address and certificate are final, switch on `Strict-Transport-Security` in `deploy\Caddyfile` (it is written there, commented out).
5. If many users reach the server through one proxy address, raise `MAX_FAILED_LOGINS_PER_IP`.

## 8. Updating to a new version

```powershell
docker compose --profile backup run --rm backup                  # 1. back up first
git pull                                                         # 2. or copy the new version over the folder (keep .env)
docker compose --profile app up -d --build                       # 3. rebuild; database changes run automatically at start
docker compose --profile app run --rm backend python -m scripts.smoke_test --url http://backend:8000 --api-only --username yourname
```

If the new version misbehaves: go back to the previous version's files, then `restore.sh apply` the backup from step 1 (`docs/steps/14-3-retention-and-backups.md`).

**Known-vulnerability check** (monthly, and before every update), on a computer with the development tools: `cd backend; uv run --with pip-audit pip-audit` and `cd frontend; npm audit`. If something is reported, update that package, run all tests, and rebuild.

## 9. Secrets: what changing each one does

| Secret | Change it when | Effect of changing |
|---|---|---|
| `JWT_SECRET` | suspected leak; staff with server access leave | everyone is logged out, nothing else |
| `AUDIT_SECRET` | suspected leak | fingerprints of searches in the existing audit log can no longer be matched to new ones. The log itself is unaffected |
| `POSTGRES_PASSWORD` | suspected leak | change it in the database first (`docker compose exec db psql -U caseuser -d casesdb -c "ALTER USER caseuser PASSWORD '<new>'"`), then in `.env`, then `docker compose --profile app up -d` |
| Caddy's authority key (`caddy_data` volume) | suspected leak | delete the volume and restart `web`; distribute the new `root.crt` |

## 10. If something goes wrong

| Situation | First steps |
|---|---|
| An account may be compromised | `--deactivate` it; look at its entries in the audit log (administrator page, filter by user); reset its password; tell your security officer |
| Data may have leaked | Stop public access (`docker compose --profile app stop web`); keep the logs and the audit log (back up now); inform your data protection officer, as your incident procedure and the DPDP Act require |
| The site is down | `docker compose --profile app ps` and `... logs --tail 100 backend`; then the troubleshooting tables in `docs/steps/` (14-1 for Docker, 14-2 for HTTPS) |
| The case assistant fails | Is Ollama running on the host? Everything else works without it (`docs/steps/13-case-chatbot.md`, section 10) |
| The disk failed | New disk, install as in sections 1–3, then `restore.sh apply` the latest backup |
