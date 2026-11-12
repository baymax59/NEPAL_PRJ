# Internal security review

For: the project owner and the independent reviewer of decision D11 in [DECISIONS.md](DECISIONS.md).

Date: 6 November 2026. Reviewed by: the development team (with Claude, an AI assistant). **This is an internal review. It is input for the independent security review (D11), not a replacement for it.**

## 1. Scope and method

The whole application as built in Steps 1–14: the backend API, the web interface, the Docker set-up, HTTPS, backups, and the police-records connector template.

| Method | Tool | Result |
|---|---|---|
| Static analysis of the Python code | **bandit** 1.x (Apache-2.0), 5,938 lines in `backend/app` and `backend/scripts` | **0 issues.** One finding (B311, random numbers) was a false positive: it picks a repeatable sample of *public* judgments. It is marked `# nosec B311` with the reason |
| Known vulnerabilities in packages | **pip-audit** (99 Python packages), **npm audit** (all frontend packages) | none known (6 Nov 2026) |
| Secrets in files that go into Git | a scan of all 251 such files for the 6 real secrets and passwords | **none found** |
| Secrets in the Docker images | search of both images for `.env`, credentials, keys, certificates | **none found** |
| Manual review | the areas in section 2, against the code | section 2 |
| Automated tests of the controls | 117 security-related tests among the 325 backend tests | all pass |

## 2. Areas reviewed

| Area | What is in place | Evidence |
|---|---|---|
| **Authentication** | Passwords stored as Argon2 hashes, at least 12 characters. Login tokens (JWT, HS256) expire after 60 minutes. One error message for every failed login. Equal time whether or not a user exists | `test_auth.py` (22 tests) |
| **Guessing passwords** | An account locks for 15 minutes after 5 wrong passwords; one computer may fail at most 20 logins in 15 minutes, for any accounts | `test_auth.py`, `test_hardening.py` |
| **Access to cases** | Every database query includes the user's access condition (clearance + per-case grants), so cases are never fetched first and filtered afterwards. Hidden and missing cases give the same "not found" | `test_access_control.py` (10), `test_police_records.py` (end to end) |
| **Roles** | Upload: analysts and admins only. Audit log: admins only. Uploads belong to their owner | `test_access_control.py`, `test_uploads_similar.py` |
| **Leavers** | `--deactivate` blocks login, and tokens issued earlier stop working on the next request (`is_active` checked every time) | fresh-install test, `docs/steps/14-5-*` |
| **Audit log** | Logins, views, searches (a fingerprint, never the text), uploads, chats, refusals, imports with their authorisation, deactivations, retention runs. Written in its own transaction; a failure to write stops the action | `test_audit.py` (6), `test_chat.py` |
| **SQL injection** | All queries through SQLAlchemy with parameters. The only text-built statements are two `SET LOCAL hnsw.ef_search = <constant>`: numbers from the code, not user input | code search |
| **Uploads** | 20 MB limit (web server: 25 MB). Type checked by content, not just the name. Stored under a random ID outside the web root, never served back. Zip-bomb and page-count limits. Deleted after 30 days | `test_uploads_similar.py` (15), `test_documents_extract.py` |
| **Path traversal** | Uploaded files get generated names. Document paths from connectors must stay inside the data folder (`../` refused) | `test_police_records.py`, code review |
| **Cross-site scripting** | React shows all text as text; search snippets are passed as parts, never as HTML; no `dangerouslySetInnerHTML` or `eval`. Content-Security-Policy allows scripts from this server only | frontend tests; browser check with no CSP violations |
| **Cross-site request forgery** | Not applicable: the token is sent in a header, not a cookie. No cross-origin access is allowed (no CORS settings) | code review |
| **Transport** | HTTPS only (Caddy, TLS 1.2+); plain HTTP only redirects. Security headers on every response; API answers `no-store` | `docs/steps/14-2-*` checks |
| **Exposure** | Only the web server is published, and only on 127.0.0.1 until D7. The database is on 127.0.0.1; the backend isn't published at all. No API docs outside development | 14.1 checks |
| **Secrets** | In `.env` only (git-ignored, not in images). The app refuses to start outside development if the secrets are equal or the database password is weak | `test_hardening.py`, scans above |
| **Containers** | The backend runs as an ordinary user (`app`). Exact image versions; the uv cache stays out of the image | 14.1 |
| **AI assistant** | Retrieval only from cases the user may see (checked first). Document text can't break out of its quoted block. Citations are checked in code. The model has no tools. A planted "say the accused is guilty" instruction was ignored | `test_chat.py` (29), real-model test |
| **Privacy** | The question text isn't logged (fingerprint only). Search text stays out of URLs. Protected identities aren't imported. Inspector output never shows personal data | tests above, `test_police_inspect.py` |
| **Backups** | Checksums; a restore was proven into an empty database. A "proven restorable" marker is checked by the readiness check | `docs/steps/14-3-*` |

## 3. Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | The case assistant's time limit didn't cover the whole answer (one request ran 6½ minutes) | Low (availability) | **Fixed** (Step 13): a total time limit, with tests |
| F2 | `https://127.0.0.1:8443` failed TLS; the HTTP redirect dropped the port | Low | **Fixed**, re-tested in a browser |
| F3 | bandit B311 (random numbers) | — | **Not a risk**: a repeatable sample of public data; marked with the reason |
| F4 | **Password-only login**: no second factor, no single sign-on | Medium | **Recommend before go-live**: connect to the organisation's identity system or add a second factor (D5/D11) |
| F5 | **Audit log not tamper-evident**: someone with direct database access could change it | Medium | **Recommend if policy requires**: hash-chained entries or write-once storage |
| F6 | **Development accounts** whose passwords are in a plain text file (`.dev-credentials.txt`) | Medium | **Must be removed before go-live**: deactivate them and create named accounts. The readiness check reports this (D5) |
| F7 | **Project and backups inside OneDrive**, so data is copied to a cloud service | Medium | **Must change before real data** (D12, D8); the readiness check reports it |
| F8 | A login token can't be withdrawn early, except by deactivating the user; logging out clears only the browser's copy | Low | Accepted: tokens expire after 60 minutes |
| F9 | The per-computer login limit is kept in memory: it resets on restart, and users behind one proxy share it | Low | Accepted; documented (14.2) |
| F10 | The web server container runs as root (official Caddy image default) | Low | Recommend running it as a non-root user (its ports are above 1024, so it can) |
| F11 | Uploaded documents aren't virus-scanned before they are read | Low | Recommend if policy requires: scan uploads (e.g. with the organisation's antivirus) |
| F12 | Caddy's own certificate authority: browsers warn, and its private key sits in the `caddy_data` volume | Info | An organisation certificate (D7); protect the volume like the database |

No finding of high severity. **F4–F7 should be closed before real police records are loaded.** The readiness check (`uv run python -m scripts.readiness_check`) tracks F6 and F7 automatically.

## 4. How to repeat this review

```powershell
cd backend
uvx bandit -r app scripts               # static analysis
uv run --with pip-audit pip-audit       # Python packages
cd ..\frontend; npm audit               # frontend packages
cd ..\backend; uv run pytest -q         # all controls' tests
uv run python -m scripts.readiness_check
```
