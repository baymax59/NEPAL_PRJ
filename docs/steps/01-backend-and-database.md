# Step 1: Backend skeleton + PostgreSQL/pgvector

Status: **done and verified** (2026-11-03).

## 1. What this module does

- Runs **PostgreSQL 17 with the pgvector extension** in Docker. This one database will hold case records, the keyword search index and the AI embeddings.
- Runs a **FastAPI** web API with one endpoint, `GET /api/health`. It reports whether the API can reach the database and which pgvector version is installed.
- Loads settings (database user, password, port) from a `.env` file, so no secrets are written into the code.

## 2. Why it is needed

Every later step stores data in this database or adds endpoints to this API. The health check lets you confirm in about a second that the basics work before you debug anything more complicated.

## 3. Files created

```
NEPAL_PRJ/
├─ docker-compose.yml           defines the database container
├─ .env.example                 template settings (committed to Git)
├─ .env                         your real settings + generated password (NOT committed)
├─ .gitignore
├─ db/init/01-extensions.sql    enables pgvector when the database is first created
└─ backend/
   ├─ pyproject.toml            Python dependencies + pytest settings
   ├─ uv.lock                   exact versions of every package (commit this)
   ├─ .python-version           3.12
   ├─ app/
   │  ├─ main.py                creates the FastAPI app and mounts routes under /api
   │  ├─ core/config.py         Settings class, which reads .env
   │  ├─ db/session.py          database engine + get_db() per-request session
   │  └─ api/health.py          GET /api/health
   └─ tests/test_health.py
```

## 4. Packages

| Package | Version installed | Purpose |
|---|---|---|
| fastapi | 0.162 | web framework |
| uvicorn[standard] | 0.54 | server that runs FastAPI |
| sqlalchemy | 2.1 | talks to the database from Python |
| psycopg[binary] | 3.3 | PostgreSQL driver used by SQLAlchemy |
| pydantic-settings | 2.16 | reads `.env` into a typed `Settings` object |
| pytest, httpx (dev only) | 9.2, 0.28 | tests |

Docker image: `pgvector/pgvector:0.8.7-pg17`.

## 5. Commands

You only need these if you set the project up from scratch, for example on another computer. On this machine they have already been run.

```powershell
# from the project root
copy .env.example .env          # then edit .env and set a strong POSTGRES_PASSWORD
docker compose up -d            # start the database
docker compose ps               # STATUS should say "(healthy)"

cd backend
uv sync                         # creates backend/.venv with Python 3.12 + exact package versions
uv run pytest -v                # run tests
uv run uvicorn app.main:app --reload --port 8000   # start the API
```

Then open:
- http://127.0.0.1:8000/api/health for the health check
- http://127.0.0.1:8000/docs for interactive API docs, where you can try endpoints in the browser

Everyday use:

```powershell
docker compose up -d     # start the DB (it also restarts automatically with Docker Desktop)
docker compose stop      # stop the DB, keep data
docker compose logs db   # view database logs
```

## 6. The code, explained

- **`app/core/config.py`**: `Settings` reads `POSTGRES_*` values from `.env` in the project root, wherever you run the command from. The password is a `SecretStr`, so it shows as `**********` if it is ever printed or logged. `database_url` builds the connection URL safely, even if the password has special characters.
- **`app/db/session.py`**: creates one shared `engine` (a pool of database connections). `get_db()` is a FastAPI *dependency*: each request gets its own session, and the session is always closed afterwards, even after an error.
- **`app/api/health.py`**: runs `SELECT 1` and reads the pgvector version. If the database can't be reached, it returns **HTTP 503** with `"database": "unavailable"`. The real error is written to the server log, not sent to the caller, so connection details (user names, hosts) never leak to the browser.
- **`app/main.py`**: `create_app()` builds the app and puts every route under `/api`. In Step 11 the frontend dev server sends all `/api` calls to the backend with one setting.

## 7. How it connects to other modules

- Step 2 adds table models that use the same `engine`/`get_db`, and Alembic migrations that use the same `Settings.database_url`.
- Every future router (`cases`, `search`, `uploads`, `chat`) is added in `main.py` the same way as the health router.
- `docker-compose.yml` gets `backend` and `frontend` services in Step 14.

## 8. How to test

```powershell
cd backend
uv run pytest -v
```

| Test | What it proves |
|---|---|
| `test_health_reports_database_and_pgvector` | The API reaches the **real** database and pgvector is enabled. Needs `docker compose up -d`. |
| `test_health_returns_503_without_leaking_details_when_database_is_down` | A database failure gives a clean 503, and the error text (containing "password") is **not** sent to the client. No database needed. |

## 9. Expected output

```
tests/test_health.py::test_health_reports_database_and_pgvector PASSED
tests/test_health.py::test_health_returns_503_without_leaking_details_when_database_is_down PASSED
2 passed, 1 warning in ~2s
```

`GET http://127.0.0.1:8000/api/health` returns:

```json
{"status":"ok","database":"ok","pgvector":"0.8.7"}
```

The one warning (`Using httpx with starlette.testclient is deprecated`) comes from the testing library. It is harmless and does not affect the app.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Every DB call takes ~60 s; tests take minutes | `POSTGRES_HOST=localhost` on Windows tries IPv6 (`::1`) first. The database only listens on IPv4. | Use `POSTGRES_HOST=127.0.0.1` (already set). We measured 60 s → 0.03 s. |
| `docker compose up` fails: `port is already allocated` | Something else uses the port. On this machine your earlier `case-search-db` container uses 5432. | Keep `POSTGRES_PORT=5433`, or pick another free port in `.env`. |
| `password authentication failed` after changing `POSTGRES_PASSWORD` | The password is only applied the **first** time the volume is created | Either change it back, or reset with `docker compose down -v` (**deletes all DB data**) and then `docker compose up -d` |
| `Set POSTGRES_PASSWORD in .env` error from compose | `.env` missing or the line is empty | `copy .env.example .env` and set a password |
| `error during connect ... docker_engine` | Docker Desktop isn't running | Start Docker Desktop and wait until it says "Engine running" |
| Health returns 503 `"database":"unavailable"` | DB stopped, or wrong host/port/password in `.env` | `docker compose ps`, check `.env`, look at the uvicorn console for the logged error |
| `pgvector` is `null` in health | The init script didn't run (the volume existed before it was added) | `docker compose exec db psql -U caseuser -d casesdb -c "CREATE EXTENSION IF NOT EXISTS vector;"` (Step 2's migration also does this) |
| `ModuleNotFoundError: No module named 'app'` | pytest/uvicorn run from the wrong folder | Run from `backend/` |
| `uv` uses Python 3.14 / packages fail to build | `.python-version` missing | Keep `backend/.python-version` = `3.12`, then `uv sync` |
| Random file-lock or "access denied" errors in `.venv` or `node_modules` | The project is inside **OneDrive**, which syncs thousands of package files | Move the project to a folder outside OneDrive (e.g. `C:\dev\NEPAL_PRJ`), then run `uv sync` again |
