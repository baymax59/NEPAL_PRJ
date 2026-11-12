# Step 10: Login, roles, record-level access and audit log

Status: **done and verified** (2026-11-05). 217 tests pass (38 of them security tests). Checked end to end against the running server.

## 1. What this module does

| Part | What it does |
|---|---|
| **Login** | `POST /api/auth/token` with username + password returns a signed token valid for 60 minutes. Every data endpoint requires it (`Authorization: Bearer <token>`). Only `/api/health` and the login itself work without one. |
| **Roles: what you may *do*** | **viewer**: search, read cases, explanations, similar cases. **analyst**: also upload new cases. **admin**: also read the audit log. |
| **Clearance: what you may *see*** | Each user has a clearance (public → internal → restricted → confidential). A case is visible if its sensitivity is at or below the user's clearance… |
| **Grants: need-to-know** | …or if the user holds an unexpired grant for that one case (`scripts/grant_access.py`). |
| **Upload ownership** | Each upload is visible only to the user who created it. |
| **Audit log** | Records logins (successful and failed), case views, explanations, similar-case requests, searches, uploads, deletions, refusals and audit-log reads. Admins read it with `GET /api/audit`. |

**Roles and clearance are separate on purpose.** An admin with *public* clearance still can't see restricted cases. Administering the system and seeing sensitive records are different permissions, as in police record systems.

## 2. Why it is needed

The goal is a tool for authorised police records. Before any such data is loaded, the system must know who is asking, show each person only what they're cleared for, and keep a record that can't be quietly skipped. It was built now, before the web interface, so the interface is built on top of it rather than having security added later.

## 3. Files created or changed

```
backend/
├─ alembic/versions/0005_users_grants_audit.py   users, case_access_grants, audit_events
├─ app/
│  ├─ auth/passwords.py      Argon2 hashing; equal-time check for unknown users
│  ├─ auth/tokens.py         signed tokens (HS256 only), 60 min lifetime
│  ├─ auth/users.py          create_user(), authenticate() with lockout
│  ├─ auth/access.py         AccessContext: clearance + grants → the condition every query uses
│  ├─ auth/dependencies.py   get_current_user, get_access_context, require_role (refusals audited)
│  ├─ audit/log.py           AuditLog (own transaction, fails closed), fingerprint()
│  ├─ api/auth.py            POST /api/auth/token, GET /api/auth/me
│  ├─ api/audit.py           GET /api/audit (admins)
│  ├─ api/cases.py, search.py, uploads.py   now require login; every action audited
│  ├─ core/config.py         + jwt_secret, audit_secret (required, ≥32 chars), lockout settings
│  ├─ core/enums.py          + Role, AuditOutcome
│  └─ main.py                API docs only in development
├─ scripts/create_user.py    create users / reset passwords
├─ scripts/grant_access.py   grant or revoke access to one case (audited)
└─ tests/
   ├─ conftest.py            users, logged-in clients, audit rows rolled back per test
   ├─ test_auth.py           22 tests
   ├─ test_access_control.py 10 tests
   └─ test_audit.py          6 tests
.env / .env.example          + JWT_SECRET, AUDIT_SECRET
.dev-credentials.txt         (git-ignored) passwords of the 3 development accounts
```

## 4. Packages

| Package | Version | Licence | Purpose |
|---|---|---|---|
| PyJWT | 2.15 | MIT | signed login tokens |
| pwdlib[argon2] | 0.3 | MIT | password hashing (Argon2id) |
| argon2-cffi | 25.1 | MIT | (installed with pwdlib) |

## 5. Commands

```powershell
cd backend
uv run alembic upgrade head                      # applies 0005

# Create users (the password is typed in, not shown; at least 12 characters)
uv run python -m scripts.create_user alice --role analyst --clearance restricted --name "Alice Rao"
uv run python -m scripts.create_user alice --reset-password

# Need-to-know access to a single case (reason required; optional expiry)
uv run python -m scripts.grant_access alice SC-ESCR010000092023 --reason "Assigned to review" --by admin --days 30
uv run python -m scripts.grant_access alice SC-ESCR010000092023 --revoke --by admin
```

**Development accounts** were created for you. Their passwords are in `.dev-credentials.txt` in the project root (git-ignored, local only):

| username | role | clearance |
|---|---|---|
| admin | admin | confidential |
| analyst | analyst | restricted |
| viewer | viewer | public |

**Using the API docs** (http://127.0.0.1:8000/docs): click **Authorize**, enter a username and password, then **Authorize** again. Every request from the docs page is then sent logged in.

From PowerShell:

```powershell
$t = (Invoke-RestMethod http://127.0.0.1:8000/api/auth/token -Method Post -Body @{ username = "viewer"; password = "<from .dev-credentials.txt>" }).access_token
$h = @{ Authorization = "Bearer $t" }
Invoke-RestMethod http://127.0.0.1:8000/api/auth/me -Headers $h
Invoke-RestMethod http://127.0.0.1:8000/api/search -Method Post -Headers $h -ContentType application/json -Body '{"query":"anticipatory bail"}'
```

## 6. The code, explained

### Login (`auth/users.py`, `auth/passwords.py`, `auth/tokens.py`)

- **Passwords** are stored only as **Argon2id** hashes and must be at least 12 characters.
- **One message for every failure.** Wrong password, unknown user, deactivated or locked account all get the same answer, *"Incorrect username or password, or the account is locked."* An attacker can't learn which accounts exist. Only the audit log knows the real reason.
- **Equal timing.** An unknown username is checked against a dummy hash, so it takes as long to reject as a wrong password.
- **Lockout.** After 5 wrong passwords in a row the account is locked for 15 minutes; even the right password is refused meanwhile. Both numbers are settings.
- **Tokens:**
  - **What's in them:** only who the user is (`sub`), with issue and expiry times, signed with `JWT_SECRET`.
  - **What's accepted:** only HS256. Unsigned (`alg: none`), forged, expired and garbage tokens are rejected, and tests cover each.
  - **Changes apply immediately:** the role, clearance and active status are read from the database on every request, so deactivating a user or lowering their clearance takes effect at once, even for tokens already issued.
- **Secrets are required.** `JWT_SECRET` and `AUDIT_SECRET` must be at least 32 characters. The app refuses to start with the placeholder `change-me`.

### Seeing cases (`auth/access.py`)

`AccessContext.case_condition()` = *sensitivity ≤ clearance* **OR** *case has an unexpired grant for this user*.

It is part of the SQL of **every** case query: the list, filter counts, details, keyword and semantic search, explanations, and similar cases (both as the query and in the results). Records the user may not see are never loaded. A case above your clearance gives exactly the same 404 as a case that doesn't exist.

### Audit log (`audit/log.py`)

| Action | Recorded details |
|---|---|
| `auth.login` | success / rejected + reason (`wrong_password`, `unknown_user`, `locked`, …); the typed username; **never the password** |
| `search` | **fingerprint** of the search text (HMAC with `AUDIT_SECRET`) + its length, mode, filters, result count; **never the text** |
| `case.list`, `case.view`, `case.explain`, `case.similar` | case ID; outcome **success / denied / not_found**. "Denied" means the case exists but the user may not see it, though the user saw "not found". Explanations store the query fingerprint only |
| `upload.create`, `.view`, `.similar`, `.delete` | upload ID; on create the file's SHA-256 and size, **never the file name** (it may contain people's names) |
| `role.denied` | the endpoint attempted, the user's role and the roles required |
| `audit.read`, `grant.create`, `grant.revoke` | who read the log or changed access |

- **Its own transaction.** The audit record is written even if the request then fails.
- **Fails closed.** If the audit record can't be written, the request fails rather than going unrecorded.
- **Fingerprint, not text.** The search fingerprint lets an investigator holding `AUDIT_SECRET` confirm whether a particular search was made, while the log alone reveals nothing about what people searched for.
- **No foreign keys.** Audit rows keep usernames and IDs as plain text, so the record outlives deleted users and cases.

## 7. How it connects to other modules

- Every earlier endpoint now uses the logged-in user's `AccessContext`. The anonymous "public only" context remains only for offline tools such as `scripts/evaluate.py`.
- **Step 11 (frontend):**
  - a login screen calls `POST /api/auth/token` and sends the token with every request;
  - `GET /api/auth/me` decides what to show (e.g. no upload button for viewers);
  - an admin page shows the audit log.
- **Step 13 (chatbot)** must retrieve passages through the same `case_condition()`, so it can never quote a case the user may not see.
- **Step 14 (production):**
  - replace local passwords with the organisation's single sign-on (OIDC, e.g. Keycloak or Azure AD);
  - add HTTPS;
  - retention rules for audit logs and uploads;
  - user management in the interface (today it's the command-line scripts).

## 8. How to test

```powershell
cd backend
uv run pytest tests/test_auth.py tests/test_access_control.py tests/test_audit.py -v
```

| Test file | Proves |
|---|---|
| `test_auth.py` | login works and `/me` reports the right role and clearance; wrong password and unknown user get identical answers; lockout after 5 failures (even the right password is refused) and unlock afterwards; deactivated users can't log in or use old tokens; passwords stored only as Argon2 hashes; short passwords refused; **all 10 data endpoints refuse callers without a token**; forged, expired, unknown-user, unsigned and garbage tokens are refused; the health check needs no login |
| `test_access_control.py` | one case per sensitivity level: listing and search show only what the clearance allows; a case above clearance gives the same 404 as a missing case (details, explanation, similar); similar-case results exclude unseen cases (with a positive control); a grant opens exactly one case; an expired grant opens nothing; the admin role doesn't bypass clearance; viewers can't upload; another user's upload is "not found" |
| `test_audit.py` | searches recorded with a fingerprint and **without the text**; views recorded as success / **denied** / not_found; uploads recorded **without the file name**; failed logins recorded **without the password**; role refusals recorded; only admins read the log, and reading is recorded |

## 9. Expected output (end-to-end check on the running server)

```
1. no login:            GET /api/cases -> 401
2. wrong password:      -> 401 Incorrect username or password, or the account is locked. Try again later.
3. viewer login:        -> 200; me = viewer / viewer / clearance public
4. viewer search:       -> 67 cases
5. viewer upload:       -> 403 Your role does not allow this action
6. analyst upload:      -> 201; top similar: VIJAY KUMAR GHAI & ORS. versus THE STATE OF WEST BENGAL
7. viewer reads analyst's upload -> 403
8. analyst deletes it   -> 204
9. analyst reads audit  -> 403
10. admin reads audit:
     admin    auth.login      success
     analyst  upload.delete   success   8da30dbf-…
     analyst  upload.create   success   8da30dbf-…  {'sha256': '8ac76bc5…', 'size_bytes': 1902}
     viewer   search          success              {'query_fingerprint': 'a88c3421…', 'query_length': 17, 'total': 67}
     viewer   auth.login      rejected             {'reason': 'wrong_password'}
```

This run showed that refusals by role (steps 5, 7, 9) were not yet in the audit log. That was fixed: they are now recorded as `role.denied`, and a test covers it.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| App won't start: `jwt_secret … at least 32 characters` / `Field required` | `JWT_SECRET` / `AUDIT_SECRET` missing or too short in `.env` | Generate each: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Every request returns 401 | No token, an expired token (60 min), or `JWT_SECRET` changed since login | Log in again |
| Login keeps failing with the right password | Account locked after 5 wrong attempts | Wait 15 minutes, or `scripts.create_user <name> --reset-password` (also unlocks) |
| 403 "Your role does not allow this action" | e.g. a viewer uploading | Use an analyst account, or change the role in the database |
| A case "doesn't exist" for one user but does for another | Clearance or grant difference, by design | Check the user's clearance; grant access if there is a need to know |
| `/docs` returns 404 | `ENVIRONMENT` isn't `development` | Expected outside development |
| `create_user` fails in a script or pipeline | It asks for the password interactively | Use `--password-stdin` |
| Audit log shows `denied` for a case the user "couldn't find" | The user tried to open a case above their clearance | Expected, and worth reviewing |
