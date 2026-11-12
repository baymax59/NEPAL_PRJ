# Step 14.2: HTTPS and hardening

Status: **done and verified** (2026-11-06). 283 backend tests (10 new) and 12 frontend tests pass. Checked over HTTPS with the smoke test (8/8, certificate verified), in a browser (no security-policy violations), and with a known-vulnerability scan of all packages (none found).

Part 2 of the 5 parts of Step 14. Before this step, the Docker stack (14.1) answered on plain HTTP; now:

| | Before | Now |
|---|---|---|
| Address | http://localhost:8080 | **https://localhost:8443** (http://localhost:8080 only redirects) |
| Login guessing | 5 wrong passwords lock one account (Step 10) | **also** at most 20 failed logins per computer in 15 minutes, for any accounts |
| Browser protections | none set | Content-Security-Policy, no framing, no sniffing, no referrer, API answers never cached |
| Oversized requests | reached the backend | refused by the web server first (25 MB for uploads, 1 MB for everything else) |
| Unsafe settings | accepted | a real installation refuses to start with them |

## 1. What this module does

1. **HTTPS.** Caddy encrypts every connection. Plain HTTP only redirects to HTTPS (`308`, keeping the port and path).
2. **Certificates, two ways** (one setting, `TLS`):
   - `TLS=internal` (default): Caddy runs its own small certificate authority and issues a certificate for `SITE_ADDRESS`. Good for testing and closed networks. Browsers warn until they are told to trust that authority (section 5).
   - `TLS=/certs/site.crt /certs/site.key`: a certificate from your organisation, placed in `deploy/certs/`.
3. **Security headers** on every response (from Caddy), and two more on every API response (from the backend itself, so they hold even without Caddy).
4. **Per-computer login limit** in the backend.
5. **Request size limits** in Caddy.
6. **Start-up check**: outside development, the backend refuses to start if the two secrets are the same, or the database password is short or the example value.
7. **Known-vulnerability scan** of all Python and npm packages.

## 2. Why it is needed

- **Without HTTPS**, passwords, login tokens and case text cross the network readable by anyone on it. Police records make this non-negotiable.
- **Headers** close common browser attacks: a malicious page showing this app in a hidden frame (clickjacking), injected scripts (Content-Security-Policy allows scripts only from this server), and case data left in the browser cache of a shared office computer.
- **Per-computer limit**: the account lockout stops someone guessing one account's password, but not one computer trying a common password on many accounts ("password spraying").
- **Size limits** stop a single oversized request from tying up the backend.
- **Start-up check**: settings copied from a developer's laptop are the most common way a test setup ends up in production.

## 3. Files created or changed

```
deploy/Caddyfile              HTTPS, redirect, security headers, request size limits
deploy/certs/README.md        where your organisation's certificate goes (everything else there is git-ignored)
docker-compose.yml            web: ports 8443 (HTTPS) and 8080 (redirect), SITE_ADDRESS/TLS/WEB_BIND settings;
                              backend: passes CHAT_TIMEOUT_SECONDS and MAX_FAILED_LOGINS_PER_IP
backend/app/auth/ratelimit.py      failed logins per client address, in a sliding 15-minute window
backend/app/api/auth.py            login: refuse with 429 when the address is over the limit (audited)
backend/app/core/headers.py        Cache-Control: no-store and X-Content-Type-Options: nosniff on API answers
backend/app/core/config.py         + max_failed_logins_per_ip, failed_login_window_minutes, start-up check
backend/app/main.py                + the headers middleware
backend/scripts/smoke_test.py      + --ca-file (trust Caddy's authority; certificates are always checked)
backend/tests/test_hardening.py    10 tests;  tests/conftest.py: a fresh login limiter for every test
.env.example, .gitignore (certificates, keys, caddy-root.crt), README.md
```

## 4. Packages

No new packages. Tools used for the scan, not installed in the project: **pip-audit** (Apache-2.0, run with `uv run --with pip-audit`) and **npm audit** (built into npm).

## 5. Commands

```powershell
docker compose --profile app up -d --build     # then open https://localhost:8443

# Copy Caddy's certificate authority (its public certificate only) to this folder
docker compose --profile app cp web:/data/caddy/pki/authorities/local/root.crt caddy-root.crt

# Smoke test over HTTPS, checking the certificate against that authority
cd backend
uv run python -m scripts.smoke_test --url https://localhost:8443 --ca-file ..\caddy-root.crt --username analyst

# Known-vulnerability scan
uv run --with pip-audit pip-audit
cd ..\frontend; npm audit
```

**Making the browser trust Caddy's authority** (optional; otherwise the browser shows a warning you can click through on this computer only). For the current Windows user, no administrator rights needed:

```powershell
certutil -addstore -user Root caddy-root.crt
```

Chrome and Edge then trust `https://localhost:8443`. Firefox keeps its own list: set `security.enterprise_roots.enabled` to `true` in `about:config`. **On a real network, use a certificate from your organisation instead** (section 1). Distributing your own authority to every computer is a decision for your IT department.

## 6. The code, explained

### `deploy/Caddyfile`

- `{$SITE_ADDRESS:localhost}:{$HTTPS_PORT:8443}` is the site. Values come from `.env` through Docker Compose, with the defaults shown.
- `tls {$TLS:internal}`: the whole setting is substituted before Caddy reads the file, so `TLS=/certs/site.crt /certs/site.key` becomes `tls /certs/site.crt /certs/site.key`.
- **The redirect.** With the HTTPS port set globally (`https_port`), Caddy treats that port as standard and leaves it out of redirects: `http://localhost:8080/x` went to `https://localhost/x`, which fails. With the port in the site address, the redirect keeps it. Found by the redirect check in section 8.
- **Headers**:

  | Header | Effect |
  |---|---|
  | `Content-Security-Policy` | scripts, styles, images and API calls only from this server; no plugins; no framing. Inline styles are allowed (the interface library uses them); inline scripts are not |
  | `X-Frame-Options: DENY` | no other site can show this one in a frame (older browsers) |
  | `X-Content-Type-Options: nosniff` | the browser uses the declared content type, never guesses |
  | `Referrer-Policy: no-referrer` | addresses (which contain case IDs) aren't passed to other sites |
  | `Permissions-Policy` | no camera, microphone or location |
  | `Cross-Origin-Opener-Policy: same-origin` | other sites' windows can't reach into this one |
  | `-Server` | the server software isn't announced |

  `Strict-Transport-Security` (browsers then refuse plain HTTP for this name for a year) is written but switched off. Switch it on once the real address and certificate are final: on `localhost` it would also affect other development servers on this computer.
- **Size limits**: `request_body { max_size … }`. Caddy closes the connection on an oversized request, so a client sees a dropped connection rather than an error page. The backend's own 20 MB upload limit still applies (a 22 MB upload passes Caddy and gets the backend's message).

### `app/auth/ratelimit.py`

- For each client address, the times of its failed logins in the last 15 minutes (older ones dropped; empty entries removed so the table doesn't grow).
- At 20 or more, the login endpoint answers **429** "Too many failed logins from this computer" with `Retry-After`, **without checking the password**. A correct password doesn't get through while blocked, which is what makes guessing pointless.
- Successful logins aren't counted. The attempt is audited (`auth.login`, rejected, reason `too_many_failures_from_address`).
- **The address is the real client's.** Caddy sets `X-Forwarded-For` and ignores any value the client sent. The backend trusts that header only because nothing but Caddy can reach it (14.1).
- **Limits of the approach**:
  - **In memory:** it resets when the backend restarts, and applies per backend process (there is one).
  - **Shared addresses:** if many users reach the server through one address (an office proxy), they share the allowance; raise `MAX_FAILED_LOGINS_PER_IP`.
  - **Docker Desktop (Windows, Mac):** connections from the host computer all arrive from Docker's gateway address. On a Linux server, real client addresses are kept.

### `app/core/headers.py`

A small ASGI middleware. It adds `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` to every API response, including errors.

### `config.py`: start-up check

A `model_validator` runs when the settings load. Outside `ENVIRONMENT=development` it collects problems and stops the backend with a message naming the setting:

```
Unsafe settings for ENVIRONMENT=production: JWT_SECRET and AUDIT_SECRET must be different
```

(Secrets shorter than 32 characters were already refused in Step 10.)

## 7. Security notes

- `caddy-root.crt` is only the **public** certificate of Caddy's authority, safe to copy. Its **private key** stays in the `caddy_data` volume: anyone with it could issue certificates this server's users trust. Back it up like the database (14.3) and keep it as private.
- Your organisation's private key goes in `deploy/certs/`, which Git ignores (`*.key`, `*.pem` too). Never e-mail or commit it.
- `WEB_BIND=127.0.0.1` still keeps the site to this computer. Opening it to a network is part of 14.5, with your IT department.

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_hardening.py tests/test_auth.py -v
```

| Test | Proves |
|---|---|
| API responses (success, "log in first", "not found") | all carry `no-store` and `nosniff` |
| one computer trying many accounts | after 3 failures (test limit) on three different accounts, even the right password for a fourth gets 429 with `Retry-After`; audited |
| successful logins aren't counted | 5 good logins with a limit of 2 all succeed |
| per address, wears off | another address isn't affected; after the window, nothing is blocked or kept |
| unsafe settings (3 cases) | same secrets, short password, example password: refused outside development |
| development | the same settings are allowed on a developer's computer |

Checks against the running stack:

| Check | Result |
|---|---|
| Without Caddy's authority / with it | refused ("certificate not trusted") / HTTP 200 |
| `http://localhost:8080/cases/X?a=1` | `308` to `https://localhost:8443/cases/X?a=1`; following it reaches the app |
| Headers on the page and on the API | all of the table above; API also `no-store`; no `Server` header |
| 2 MB search request / 30 MB upload | refused by the web server (connection closed) |
| 22 MB upload | passes the web server; backend answers 413 "File is larger than 20 MB" |
| Normal search afterwards | HTTP 200 |
| 21 failed logins from this computer | 20 × 401, then 429; the right password also gets 429, `Retry-After` 898 s; a backend restart clears it |
| Smoke test over HTTPS with `--ca-file` | 8/8 |
| Browser over HTTPS: log in, search, case details, case assistant, new-case page | works; **no security-policy violations**, no console errors |
| `pip-audit` (99 Python packages) / `npm audit` (all packages) | no known vulnerabilities |

## 9. Expected output

```
> uv run python -m scripts.smoke_test --url https://localhost:8443 --ca-file ..\caddy-root.crt --username analyst
PASS  web page: HTTP 200
PASS  health: {'status': 'ok', 'database': 'ok', 'pgvector': '0.8.7'}
...
all checks passed

> uv run --with pip-audit pip-audit
No known vulnerabilities found
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Browser: "Your connection is not private" | It doesn't trust Caddy's own authority | Click **Advanced → Continue/Proceed** (this computer only), or trust it once (section 5), or use your organisation's certificate |
| Browser: "This site can't provide a secure connection" at `https://127.0.0.1:8443` | No certificate for the IP address: browsers send no name (SNI) for an IP, and inside Docker Caddy can't tell which one is meant | Fixed on 2026-11-06: the Caddyfile also serves `127.0.0.1` and sets `default_sni 127.0.0.1`. Restart `web` after updating |
| Smoke test: `CERTIFICATE_VERIFY_FAILED` | `--ca-file` missing or pointing at an old certificate | Copy `root.crt` again (section 5). It changes only if the `caddy_data` volume is deleted |
| `http://localhost:8080` doesn't load the page | It only redirects; the site is on HTTPS | Use `https://localhost:8443` |
| Login: "Too many failed logins from this computer" | 20 failures from this address in 15 minutes | Wait (the message says how long), or restart the backend. If users share an address, raise `MAX_FAILED_LOGINS_PER_IP` |
| Backend won't start: "Unsafe settings for ENVIRONMENT=…" | Settings meant for a developer's computer | Fix what the message names; secrets: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Upload "network error" for a very large file | Over 25 MB: the web server closes the connection | Files must be under 20 MB (Step 8) |
| A page looks broken or a feature does nothing, with "Refused to …" in the browser console | Something new violates the Content-Security-Policy | Load it from this server instead, or (only if really needed) extend the policy in `deploy/Caddyfile` |
| Certificate error after changing `SITE_ADDRESS` | The certificate is for the old name | Restart `web`; Caddy issues a new one (internal), or install the right certificate |
