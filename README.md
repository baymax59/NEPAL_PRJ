# Similar Case Search

An AI-assisted tool that takes a new case document, searches a database of historical cases, and shows the most similar cases as cards. Each card opens a structured details page that explains why the case matched.

Similarity scores show **relevance for review**. They do not mean two cases are legally equivalent.

- Development data: [Indian Supreme Court Judgments](https://registry.opendata.aws/indian-supreme-court-judgments/) (CC-BY-4.0, Dattam Labs). See [docs/DATASET.md](docs/DATASET.md).
- Roadmap: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md): all steps (0–14) done
- Step guides: [docs/steps/](docs/steps/)
- **Installing and running it** (IT): [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Handover** (status, verification, decisions needed before real police records, limitations): [docs/HANDOVER.md](docs/HANDOVER.md)
- **Before real police records**: the sign-off form [docs/DECISIONS.md](docs/DECISIONS.md), the [internal security review](docs/SECURITY_REVIEW.md), and `cd backend; uv run python -m scripts.readiness_check`

## Demo setup (one command, Windows PowerShell)

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/), [uv](https://docs.astral.sh/uv/). Node.js and Git are optional for the full dev workflow. [Ollama](https://ollama.com/) is needed for the case assistant.

```powershell
git clone https://github.com/baymax59/NEPAL_PRJ.git
cd NEPAL_PRJ
.\demo-setup.ps1
```

`demo-setup.ps1` generates `.env` with secure random secrets, starts PostgreSQL + the full HTTPS stack on **https://localhost:8443**, imports 100 Supreme Court judgment samples, computes AI embeddings (~13 min on CPU), and creates three demo accounts:

| Account | Password | Role |
|---|---|---|
| `admin` | `Admin@Nepal2024!` | Admin — sees everything, audit log |
| `analyst` | `Analyst@Nepal2024!` | Upload new cases, CDR analysis |
| `viewer` | `Viewer@Nepal2024!` | Read-only search and case details |

Credentials are also saved to `.dev-credentials.txt` (git-ignored). Pass `-SkipData` to skip data import and start the app immediately.

---

## Manual quick start (Windows, PowerShell)

Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/), Git. Node.js is needed from Step 11. [Ollama](https://ollama.com/) is needed for the case assistant (Step 13).

```powershell
copy .env.example .env              # set POSTGRES_PASSWORD, JWT_SECRET and AUDIT_SECRET in .env
docker compose up -d                # PostgreSQL 17 + pgvector on 127.0.0.1:5433

cd backend
uv sync
uv run alembic upgrade head          # create the database tables
uv run python -m scripts.sc_download # download a 100-judgment sample (~37 MB)
uv run python -m scripts.sc_import   # import it (safe to re-run)
uv run python -m scripts.process_documents   # extract text, split into searchable chunks
uv run python -m scripts.embed_chunks        # AI embeddings (downloads ~130 MB model once; ~13 min on CPU)
uv run python -m scripts.extract_provisions  # statutory provisions cited (Section 302 IPC, Article 21, ...)
uv run python -m scripts.extract_timeline    # case timelines (dated events with pages) and courts named
uv run python -m scripts.evaluate            # measure search quality against evaluation/labels.json
uv run pytest -v
uv run uvicorn app.main:app --reload --port 8000
```

Check: http://127.0.0.1:8000/api/health should return `{"status":"ok","database":"ok","pgvector":"0.8.7"}`.

**Or run the whole application in Docker** (Step 14.1): database, backend and web interface, with nothing else installed but Docker (and Ollama for the case assistant). The database must already contain cases, e.g. from the steps above:

```powershell
docker compose --profile app up -d --build     # first build takes several minutes
# open https://localhost:8443 (or https://127.0.0.1:8443); http://localhost:8080 redirects there
```

The browser warns about the certificate until it trusts Caddy's own certificate authority; see [docs/steps/14-2-https-and-hardening.md](docs/steps/14-2-https-and-hardening.md). Check that it works (the password is read from the keyboard, not shown):

```powershell
docker compose --profile app cp web:/data/caddy/pki/authorities/local/root.crt caddy-root.crt
cd backend
uv run python -m scripts.smoke_test --url https://localhost:8443 --ca-file ..\caddy-root.crt --username analyst
```

**The web interface for development** (Step 11). In a second terminal:

```powershell
cd frontend
npm install       # first time only
npm run dev       # then open http://localhost:5173 (or http://127.0.0.1:5173); the backend must be running too
```

Screenshots of every page: [docs/images/](docs/images/).

**The case assistant** (Step 13). On any case's details page, **Ask the case assistant** answers questions using only that case's records, citing them as [S1], [S2]… It needs Ollama running with the model installed once (about 2.5 GB):

```powershell
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

Everything runs on this computer. Without a graphics card an answer takes about 2–4 minutes. If Ollama isn't running, the assistant says so; everything else keeps working.

**Logging in.** Every data endpoint needs a login (Step 10). Create a user:

```powershell
uv run python -m scripts.create_user alice --role analyst --clearance restricted
```

Development accounts `admin`, `analyst` and `viewer` already exist on this machine; their passwords are in `.dev-credentials.txt` (git-ignored). In the API docs, click **Authorize** and log in.

Try the API in the browser at http://127.0.0.1:8000/docs:
- `GET /api/cases`: list cases (filters: `year_from`, `year_to`, `outcome`, `source_system`)
- `GET /api/cases/{display_id}`: full case details, including cited provisions
- `POST /api/cases/{display_id}/explain`: why a case matched a search (`{"query": "..."}`)
- `POST /api/cases/{display_id}/chat`: ask the case assistant (`{"question": "..."}`; optional `history`, `compare_with`)
- `POST /api/uploads`: upload a new case (PDF/DOCX/TXT). Try `samples/CASE-1042-fictional.txt`
- `POST /api/uploads/{id}/similar`: similar historical cases, with matched passage pairs and differences
- `GET /api/cases/{display_id}/similar`: cases similar to an existing case
- `DELETE /api/uploads/{id}`: remove an upload and everything derived from it
- `POST /api/search`: hybrid keyword + meaning-based search, e.g. `{"query": "illegal building ordered to be pulled down"}` (add `"mode": "keyword"` or `"semantic"` to compare)
