# Step 15: CDR Analysis integration

Status: **done and verified** (2026-11-12). 28 new tests (6 session + 12 proxy + 10 frontend). The integration is optional: when no CDR services are running the button is still shown but CDR Analysis opens to a "service not configured" message; the rest of the application is unaffected.

## 1. What this module does

It embeds the three CDR Analysis services (D1 import backend, D2 analytics front-end, D3 geospatial front-end) into the host application as a **case-scoped tab page**. A user opens a case they can already see, clicks **CDR Analysis**, and all 15 analysis views appear in iframes — Import & Evidence, Search & Analytics, Call Graph, Frequency & Behaviour, Top Contacts, Common Contacts, Devices & SIMs, Map & Location, Timeline, Common Towers, Co-location, Anomalies, Audit Trail, Chain of Custody, and Reports.

**Security architecture** — the whole point of integrating here rather than linking out:

| Requirement | How it is met |
|---|---|
| A user can only open CDR data for a case they are authorised to see | `GET /api/cdr/session` checks case visibility before issuing the cookie |
| CDR D2 analyst identity is never forgeable from the browser | `X-Analyst-Id` forwarded to D2 is always taken from the validated session JWT, never from the incoming request |
| CDR D3 data cannot be accessed for a different case | URL `case_id` is compared to the session `case_id`; mismatch → 403 |
| CDR credentials never appear in browser storage, URLs, or response bodies | Issued as an `httpOnly SameSite=Strict` cookie scoped to `/api/cdr`; the response body contains only display metadata |
| CDR backend CSP headers cannot override the host's CSP | `content-security-policy` is stripped from upstream responses |

## 2. Why it is needed

Investigators using the case-search tool need to move from "I found the case" to "I see the call records for this case" without signing in again or navigating to a separate system. Embedding the CDR services under the host's session keeps authentication in one place and enforces the same case-scoped access rules that already govern document search.

## 3. Files created or changed

```
backend/app/api/cdr_session.py      GET /api/cdr/session — validates login and case access; sets cdr_session cookie
backend/app/api/cdr_proxy.py        /api/cdr/proxy/d1/, /api/cdr/proxy/d2/, /api/cdr/cases/{id}/ — authenticated reverse proxy
backend/app/core/config.py          CDR_D1_JWT_KEY, CDR_D1_API_URL, CDR_D2_API_URL, CDR_D3_API_URL, CDR_MSISDN_RULE, CDR_TIMEZONE
backend/app/main.py                 cdr_router and cdr_proxy_router included
backend/tests/test_cdr_session.py   6 session-bridge security tests
backend/tests/test_cdr_proxy.py     12 proxy-layer security tests

frontend/src/pages/CdrAnalysisPage.tsx      15-tab page; iframes carry the httpOnly cookie automatically
frontend/src/api/endpoints.ts               getCdrSession() added
frontend/src/api/types.ts                   CdrSession interface added
frontend/src/App.tsx                        /cases/:displayId/cdr route added
frontend/src/pages/CaseDetailsPage.tsx      "CDR Analysis" button added to the Actions section
frontend/src/test/CdrAnalysisPage.test.tsx  10 frontend tests
frontend/vite.config.ts                     Dev-server proxy for /cdr/d1/api, /cdr/d2/api, /cdr/d3/api

.env.example    CDR_D1_JWT_KEY, CDR_D1_API_URL, CDR_D2_API_URL, CDR_D3_API_URL,
                CDR_MSISDN_RULE, CDR_TIMEZONE, CDR_D1_PORT, CDR_D2_PORT, CDR_D3_PORT
```

## 4. Packages

`httpx` (already a dependency — used for the async upstream requests).

## 5. Environment variables

Add these to `.env` when CDR services are running. All are optional; the application starts without them.

```
# --- CDR Analysis integration ---
# CDR_D1_JWT_KEY must match the D1 backend's AUTH_JWT_KEY.
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
CDR_D1_JWT_KEY=change-me-same-as-d1-auth-jwt-key

# Base URLs for the three CDR backends (defaults shown):
CDR_D1_API_URL=http://127.0.0.1:55491
CDR_D2_API_URL=http://127.0.0.1:55492
CDR_D3_API_URL=http://127.0.0.1:55493

# India profile:
CDR_MSISDN_RULE=in-msisdn.v1
CDR_TIMEZONE=Asia/Kolkata

# Vite dev-server proxy ports (only needed if you changed the default CDR ports):
# CDR_D1_PORT=55491
# CDR_D2_PORT=55492
# CDR_D3_PORT=55493
```

## 6. How the session handshake works

```
Browser                      Host backend                  CDR D1/D2/D3
  |                               |                               |
  | GET /api/cdr/session          |                               |
  |   ?case_id=SC-2023-0001       |                               |
  |   Authorization: Bearer <JWT> |                               |
  |------------------------------>|                               |
  |                               | 1. verify host JWT            |
  |                               | 2. check case visibility      |
  |                               | 3. mint cdr_session cookie    |
  |<--Set-Cookie: cdr_session=... |                               |
  |   (httpOnly, SameSite=Strict) |                               |
  |                               |                               |
  | GET /api/cdr/proxy/d2/search  |                               |
  |   Cookie: cdr_session=...     |                               |
  |------------------------------>|                               |
  |                               | 4. validate cookie JWT        |
  |                               | 5. inject X-Analyst-Id        |
  |                               |   from session, not browser   |
  |                               |------------------------------>|
  |                               |<------ upstream response -----|
  |<-- response (CSP stripped) ---|                               |
```

The browser sends the `cdr_session` cookie automatically with every same-origin iframe request because the cookie's `Path` is `/api/cdr`. JavaScript cannot read the cookie (`httpOnly`).

## 7. The code, explained

### `cdr_session.py` — session bridge

`GET /api/cdr/session?case_id=<id>` requires a valid host login (the existing `CurrentUser` dependency). It calls `get_visible_case()` with the user's `AccessContext`: if the case isn't visible to this user, it returns 403. On success it mints a short-lived (1 hour) HS256 JWT containing `sub`, `analyst_id`, `role`, `case_id`, `purpose="cdr_session"` and a `jti` nonce, then sets it as an `httpOnly` cookie scoped to `Path=/api/cdr`. The response body returns only the case ID, analyst display name, role, MSISDN rule and timezone — no credentials.

### `cdr_proxy.py` — reverse proxy

Three route groups:

| Endpoint | Backend | Added by proxy |
|---|---|---|
| `/api/cdr/proxy/d1/{path}` | D1 (import) | `Authorization: Bearer <D1 JWT>` signed with `CDR_D1_JWT_KEY` |
| `/api/cdr/proxy/d2/{path}` | D2 (analytics) | `X-Analyst-Id` from the session (browser-supplied value is dropped) |
| `/api/cdr/cases/{case_id}/{path}` | D3 (geo) | nothing — but `case_id` in the URL must match `case_id` in the cookie |

All three validate the `cdr_session` cookie first (401 if missing or expired). Only safe, non-identifying request headers are forwarded (`accept`, `content-type`, `content-length`, `range`, `accept-language`). `content-security-policy`, `transfer-encoding` and `server` are stripped from upstream responses.

### `CdrAnalysisPage.tsx` — frontend shell

Calls `GET /api/cdr/session` with React Query. While it loads, shows a spinner. On success, renders 15 `<Tabs>`, each loading an iframe. The iframe `src` values never contain tokens or analyst IDs: auth is carried by the cookie.

Three `src` patterns:
- D1: `/cdr/d1/` (the dev-server proxy rewrites to `http://127.0.0.1:55491/`)
- D2: `/cdr/d2/<view>?case_id=<id>` (via `/api/cdr/proxy/d2/`)
- D3: `/cdr/d3/cases/<id>/<view>` (via `/api/cdr/cases/<id>/`)

A DEV-ONLY authentication notice and a synthetic-map disclaimer are shown until a real identity provider and approved map tile source are configured.

## 8. How to test

```powershell
# Backend (no DB needed: proxy tests use mocked dependencies)
cd backend
uv run pytest tests/test_cdr_session.py tests/test_cdr_proxy.py -v

# Frontend
cd frontend
npm test -- --reporter=verbose src/test/CdrAnalysisPage.test.tsx
```

### Backend tests

| Test | Proves |
|---|---|
| `test_session_requires_auth` | 401 without a host login |
| `test_session_inaccessible_case_returns_403` | 403 when `get_visible_case` returns None |
| `test_session_returns_case_id_matching_request` | 200; case_id in body matches the requested ID |
| `test_no_cross_case_leakage` | 403 when the case isn't visible (same as above, explicit name) |
| `test_session_sets_httponly_cookie` | `cdr_session` cookie is `HttpOnly` |
| `test_response_body_contains_no_credentials` | body has no `d1_token`, `d2_analyst_id` or `subject` |
| D1: `test_no_cookie_returns_401` | 401 with no cookie |
| D1: `test_expired_cookie_returns_401` | 401 with an expired cookie |
| D1: `test_valid_cookie_reaches_proxy` | 200 when cookie is valid |
| D2: `test_no_cookie_returns_401` | 401 with no cookie |
| D2: `test_expired_cookie_returns_401` | 401 with expired cookie |
| D2: `test_case_mismatch_returns_403` | 403 when cookie's case_id differs from query param |
| D2: `test_x_analyst_id_comes_from_session_not_browser` | X-Analyst-Id forwarded is the session value, not the browser-supplied one |
| D3: `test_no_cookie_returns_401` | 401 with no cookie |
| D3: `test_expired_cookie_returns_401` | 401 with expired cookie |
| D3: `test_case_id_mismatch_returns_403` | 403 when URL case_id differs from cookie's case_id |
| D3: `test_matching_case_id_passes_and_routes_to_d3` | 200; target URL contains case_id and path segment |
| D3: `test_different_case_in_cookie_cannot_access_another_case` | 403 when cookie is for a different case |

### Frontend tests

| Test | Proves |
|---|---|
| shows loader while fetching session | spinner visible during pending query |
| displays case ID badge after session loads | case_id shown in the page |
| shows back link to host case page | link target is `/cases/<displayId>` |
| fetches session with the correct case_id | getCdrSession called with the right ID |
| shows error when session fetch fails | error alert shown on 403 |
| renders all 15 canonical CDR tabs | all 15 tabs present |
| shows DEV-ONLY authentication notice | advisory visible |
| shows synthetic map notice | map disclaimer visible |
| no credentials appear in any iframe src URL | no `token=`, `analyst.id=` or `bearer` in src attributes |
| does not show standalone CDR case selector | no "select a case" prompt (the case is already set by the route) |

## 9. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| CDR Analysis button opens to a blank / "service not configured" screen | CDR services are not running | Start D1, D2, D3 and set their URLs in `.env`; restart the backend |
| `401` on every CDR proxy request | `cdr_session` cookie not set, or the browser sent it on the wrong path | Open `/api/cdr/session?case_id=<id>` directly to check; cookie is scoped to `Path=/api/cdr` |
| D1 returns 401 (D1 auth failed) | `CDR_D1_JWT_KEY` doesn't match D1's `AUTH_JWT_KEY` | Set both to the same value |
| D2 returns 403 (wrong analyst) | Analyst ID mismatch between host user UUID and D2's known analysts | Register the user in D2, or align how D2 identifies analysts |
| Map tab shows "no tiles" | No approved map tile provider configured | Configure the tile provider in D3; this is expected in development |
| `ValidationError: CDR_D1_JWT_KEY` | Key is set but shorter than the minimum | Generate a new key: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Vite proxy 502 on `/cdr/d1/api` | CDR D1 not running on the expected port | Check `CDR_D1_PORT` in `.env`; default is 55491 |

## 10. Deployment notes

In Docker (`docker-compose.yml`) the CDR backend URLs must point to the container network names or the host machine. `host.docker.internal` works on Windows and Mac:

```
CDR_D1_API_URL=http://host.docker.internal:55491
CDR_D2_API_URL=http://host.docker.internal:55492
CDR_D3_API_URL=http://host.docker.internal:55493
```

The `cdr_session` cookie's `secure` flag is set automatically in production (`ENVIRONMENT != development`), so HTTPS is required (Step 14.2 sets this up).
