# Step 14.1: The whole application in Docker

Status: **done and verified** (2026-11-06). The stack starts in about 20 seconds; the smoke test passes all 8 checks from this computer and from inside Docker; an upload survives a full restart; checked in a browser with no console errors.

Part 1 of the 5 parts of Step 14 (production readiness). **Since 14.2 the address is https://localhost:8443**; the commands below are up to date. The others: 14.2 HTTPS and hardening, 14.3 retention and backups, 14.4 police-records connector template, 14.5 deployment and handover guide.

## 1. What this module does

One command starts the database, the backend and the web interface. The server needs only **Docker** (plus Ollama for the case assistant): no Python, no Node.js, no uv.

```
                      ┌───────────── Docker ───────────────────────────────────────────┐
browser ── port 8443 ─┤► web (Caddy) ── /api/* ──► backend (FastAPI) ──► db (PostgreSQL)│
                      │   └ serves the built web interface   │                          │
                      └───────────────────────────────────────┼──────────────────────────┘
                                                              └──► Ollama on the host (case assistant)
```

Development is unchanged: `docker compose up -d` still starts only the database.

## 2. Why it is needed

- **A server shouldn't need development tools.** The images contain exactly what the application needs, in pinned versions; the same images run on any machine with Docker.
- **Fewer ways in.** Only the web server is published. The backend has no port of its own outside Docker, and the database stays on `127.0.0.1`.
- **Restarts are automatic** after a crash or a reboot (`restart: unless-stopped`).
- **Uploads stay out of the project folder.** In development they live in `data/uploads/`, which on this computer is inside OneDrive and so is copied to the cloud. In Docker they live in a Docker volume. (Real police records must never be stored in a synced folder; see 14.5.)

## 3. Files created or changed

```
docker-compose.yml          + backend and web services (profile "app"), volumes appdata, caddy_data, caddy_config
deploy/Caddyfile            the web server: built web interface + /api passed to the backend
backend/Dockerfile          Python 3.12 image; installs exactly uv.lock; runs as a non-root user
backend/.dockerignore       keeps .venv and caches out of the image
backend/pyproject.toml      + torch as a direct dependency, from the CPU-only index on Linux
backend/uv.lock             re-locked: Linux gets torch 2.15.0+cpu; 13 NVIDIA packages and Triton removed
backend/scripts/smoke_test.py   checks a running installation end to end (8 checks)
frontend/Dockerfile         builds the web interface with Node.js, then serves it with Caddy
frontend/.dockerignore      keeps node_modules and old builds out
README.md                   how to start it
```

## 4. Images and packages

| Image | Version (pinned) | Licence | Used for |
|---|---|---|---|
| `python` | 3.12.16-slim-trixie (Debian 13) | PSF | the backend |
| `ghcr.io/astral-sh/uv` | 0.13.0 | MIT / Apache-2.0 | installing the exact versions in `uv.lock` (build only) |
| `node` | 24.19.0-alpine | MIT | building the web interface (build only, not in the final image) |
| `caddy` | 2.11.9-alpine | Apache-2.0 | the web server (and HTTPS in 14.2) |
| `pgvector/pgvector` | 0.8.7-pg17 | PostgreSQL | the database, unchanged |

**PyTorch.** On Linux, the standard PyTorch package brings several GB of NVIDIA graphics-card libraries. This application runs on the CPU, so `pyproject.toml` now takes PyTorch from PyTorch's CPU-only index on Linux. Windows already used a CPU-only build, so development is unchanged. uv applies such a source only to packages listed directly, so `torch` is now listed as a direct dependency.

| Image | Size (as Docker Desktop reports it) |
|---|---|
| backend | 2.5 GB, of which PyTorch is 0.8 GB. The first build came to 4.4 GB: uv's download cache (1.4 GB) had stayed inside the image. The Dockerfile now mounts that cache only during the build. |
| web | 93 MB |

The first build takes about 5 minutes on this computer. After a code-only change, a rebuild takes seconds, because the package layer is reused.

## 5. Commands

```powershell
# Build and start everything (the first build downloads packages and takes several minutes)
docker compose --profile app up -d --build

# Open https://localhost:8443 and log in as before (HTTPS since 14.2)

# Check it from inside Docker: the password is typed, not shown
docker compose --profile app run --rm backend python -m scripts.smoke_test --url http://backend:8000 --api-only --username analyst

# Logs, status, stop
docker compose --profile app logs -f backend
docker compose --profile app ps
docker compose --profile app down          # stops; data is kept
```

The database must contain cases. On this computer it already does (Steps 3–12). On a new server, run the import steps once inside the backend container, e.g. `docker compose --profile app run --rm backend python -m scripts.sc_import`.

## 6. The code, explained

### `backend/Dockerfile`

1. Starts from the official Python 3.12 slim image and copies in `uv`.
2. **Installs the packages before copying the code**, so rebuilding after a code change reuses the slow package layer.
3. `uv sync --frozen --no-dev` installs exactly what `uv.lock` records, without test tools. `--frozen` refuses to change versions during a build.
4. Creates a user `app` with no login shell, and runs as that user, not as root.
5. On start: `alembic upgrade head` (brings the tables up to date), then `uvicorn`. `--proxy-headers` makes the audit log record the user's address rather than the web server's; that is safe only because the backend can't be reached except through the web server.

### `frontend/Dockerfile`

Two stages. The first uses Node.js to run `npm ci` (exact versions from `package-lock.json`) and `npm run build`. The second is just Caddy plus the built files; Node.js isn't in the final image.

### `deploy/Caddyfile`

- `/api/*` goes to `backend:8000` (Docker's internal name for the backend container).
- Everything else is a file from the built web interface. Unknown paths such as `/cases/SC-…` get `index.html`, and the app shows the right page.
- `admin off`: Caddy's own management endpoint is switched off.
- It is mounted from the project, so it can be changed without rebuilding.

### `docker-compose.yml`

- **Profiles.** `backend` and `web` have `profiles: ["app"]`, so they start only with `--profile app`. Plain `docker compose up -d` is still database-only for development.
- **Settings.** The backend gets the database password and the two secrets from `.env` (Compose refuses to start without them). Inside Docker the database host is `db` and the API runs as `production` (no interactive API docs).
- **The embedding model** is mounted from `./models` and `HF_HUB_OFFLINE=1` stops any attempt to download it: the server makes no outside connections for it.
- **Ollama** stays on the host. The backend reaches it at `host.docker.internal:11434`.
- **Volumes**: `pgdata` (database, as before), `appdata` (uploads), `caddy_data`/`caddy_config` (Caddy's state, including certificates in 14.2).

### `scripts/smoke_test.py`

Eight checks against a running installation: web page, health, login, who-am-I, case list, search, case details, and that the API refuses requests without a login (`--api-only` skips the web page when pointed straight at the backend). It reads the password from the keyboard or standard input and never prints it or the login token. Exit code 0 means every check passed, so it can be used in scripts. It is reused in 14.2 (over HTTPS) and 14.3 (after a restore).

## 7. Security notes

- Containers run the backend as a non-root user.
- Only the web server's port is published, and only on `127.0.0.1` for now. 14.2 adds HTTPS before anything is opened to the network.
- The interactive API docs are off in Docker (production mode).
- Secrets come from `.env`, which is never copied into an image (it is outside the build folders).

## 8. How to test

```powershell
docker compose --profile app up -d --build
docker compose --profile app ps          # backend "healthy", web "Up"
docker compose --profile app run --rm backend python -m scripts.smoke_test --url http://backend:8000 --api-only --username analyst
```

| Check | How | Result |
|---|---|---|
| Starts | `docker compose --profile app up -d` | backend healthy, web up, in about 20 s |
| Works end to end | smoke test from this computer (port 8080) and from inside Docker | 8 of 8 checks, both ways |
| Meaning-based search inside Docker | the smoke test's search | `mode hybrid`: the model loads from `./models` without going online |
| Case assistant can reach Ollama | from the backend container to `host.docker.internal:11434` | Ollama answered (version 0.40.14) |
| Backend not published | `docker compose --profile app port backend 8000` | no published port |
| API docs hidden | `/api/docs`, `/api/openapi.json` | 404 (`/docs` shows the normal web app) |
| Data survives a restart | upload the fictional sample, `down`, `up`, fetch it again, then delete it | 201, then 200 after the restart, then 204 |
| In a browser | Playwright: log in, open a case, open the case assistant | works; no console errors |

The automated tests are unchanged and still pass (273 backend, 12 frontend).

## 9. Expected output

```
> docker compose --profile app ps
case-search-backend-1  Up 12 seconds (healthy)  8000/tcp
case-search-db-1       Up 4 hours (healthy)     127.0.0.1:5433->5432/tcp
case-search-web-1      Up 34 minutes            127.0.0.1:8080->80/tcp

> ... scripts.smoke_test --url http://web --username analyst
PASS  web page: HTTP 200
PASS  health: {'status': 'ok', 'database': 'ok', 'pgvector': '0.8.7'}
PASS  login: HTTP 200
PASS  who am I: role analyst, clearance restricted
PASS  case list: 100 cases visible
PASS  search: 43 cases, mode hybrid
PASS  case details: SC-ESCR010007962023
PASS  login required: HTTP 401 without a login
all checks passed
```

The web build prints a warning that one JavaScript file is larger than 500 kB: the whole web interface is a single file. It loads in about half a second here; splitting it is optional.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `Set POSTGRES_PASSWORD in .env` / `Set JWT_SECRET in .env` | `.env` missing or incomplete | `copy .env.example .env` and fill in the values |
| `docker compose up` starts only the database | The `--profile app` part is missing | `docker compose --profile app up -d` |
| Port 8443 or 8080 already in use | Another program uses it | Set `HTTPS_PORT` / `HTTP_PORT` (any free ports) in `.env` |
| Search works but only by keywords; the smoke test notes "meaning-based search is off" | The embedding model isn't in `./models` | Copy the `models` folder from a computer where `scripts.embed_chunks` has run |
| The case assistant says "The chat model is not running" | Ollama isn't running on the host, or (on Linux) listens only on 127.0.0.1 | Start Ollama. On Linux set `OLLAMA_HOST=0.0.0.0` for Ollama and allow only the Docker network through the firewall, or set `DOCKER_OLLAMA_URL` |
| `alembic` error when the backend starts | The database is older or newer than the code | `docker compose --profile app logs backend`; restore the matching version (14.3) |
| A code change doesn't show up | The image wasn't rebuilt | `docker compose --profile app up -d --build` |
