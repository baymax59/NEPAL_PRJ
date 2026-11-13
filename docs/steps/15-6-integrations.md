# Step 15.6: Integrations (phase CM-6)

> **Partly superseded (2026-11-10).** Integrations still work as described, but the contract is now version 2.0: a finding is added to a case (`case_id`) and written into its history, with no repository, branch or head. The git-style design this note describes was replaced by the plain case design: [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md) and the notes [17-1](17-1-plain-case-core.md) to [17-4](17-4-plain-case-browser-checks-and-guides.md). The contract: [09-integration-contract.md](../case-management/09-integration-contract.md).

Status: **done and verified** (2026-11-08).

| Check | Result |
|---|---|
| Backend tests | 503 pass, 10 of them new |
| Frontend tests | 42 pass, 6 of them new |
| Browser walk-through | 33 of 33 steps pass (3 new, one of them over HTTP with a source key), with the real AI models |
| Docker version | rebuilt (migration 0013 applied, its 4 database rules present); smoke test 8 of 8, CM-6 checks 8 of 8 |

All test data is fictional, and **nothing was created in the development database**: the tests use `casesdb_test` and the walk-through the throwaway `casesdb_e2e`.

This is part 6 of the 8 phases of Step 15 ([docs/case-management/08](../case-management/08-implementation-plan.md)). It connects the cases of [15.1](15-1-repository-core.md)–[15.5](15-5-case-intelligence.md) to the other Knight Hawk systems: the Log Analyzer, CDR and IPDR analysis, OSINT and alerting. The contract those systems follow is [docs/case-management/09](../case-management/09-integration-contract.md).

## 1. What this phase does

Another system can now **add a finding to a case** through one connection ("Add to case"). Seven kinds of finding are accepted: log events, alerts, CDR results, IPDR results, open-source information (OSINT), indicators and external reports. Each one:
- becomes a **permanent record** in the case (`IMP-0001`, `IMP-0002`…), kept exactly as received;
- is added by **its own commit** on the branch the investigator chose;
- keeps its **provenance**: the source system, the record's ID and hash there, where the full record stays, the **legal authority** it was obtained under, when it happened, which key sent it and for whom;
- is **audited**, and the case's lead investigator gets a notice.

What you see:

| Where | What |
|---|---|
| **Imported findings** tab of every case workspace | **Findings**: each finding with its kind, source, record ID, when it happened and its identifiers, at any branch or commit. Opening one shows its provenance, the result as the source sent it, every version, and the notes based on it. **Indicators**: every identifier the findings name, and the **other cases** where it appears, with a **Link** button |
| **Add from a source** (in that tab) | The **fictional test source**, standing in for the real systems until they exist: eight invented findings, added through exactly the same rules |
| **Administration → Integration sources** | Each connected system with its **access policy**, its key (shown once), its use and its history. Disable, enable, issue a new key |

### Two credentials for every finding

The person decides, the system vouches:
- **the person's login:** the finding is added for them, with exactly their rights (only branches they may write to);
- **the source's key** (`X-Integration-Key`): only a registered, enabled source can send findings, and only within its policy.

### The access policy of a source

Set once, when an administrator registers the source:
- **which kinds** of finding it may send;
- **which kinds need a legal authority reference**: CDR and IPDR results by default, so a call-record analysis can't enter a case without its requisition number;
- the **lowest case classification** it may send to, so sensitive data never lands in a less protected case;
- its **legal basis**, shown with every finding it sends.

A policy can't be edited: a new policy means a new source, so each finding names the exact policy it was accepted under. Keys are **shown once and stored only as a SHA-256**. Disabling a source or issuing a new key stops the old key at once, and what the source already added stays in the cases.

### Never edited, never duplicated, never lost

- Sending the same record again is refused: nothing is duplicated.
- If the source **changes** its record (a different hash), sending it again adds a **new version** of the same finding. The change note says the hash changed from what to what, and the first version stays readable at its own commit.
- A finding can't be edited in the case: people add a note that refers to it, or withdraw it with a reason. Both stay in the history.
- Only references, hashes and derived results are stored. Raw data (logs, call or IP records) stays in its source system.

### How it connects to the rest of Knight Hawk

| Feature | What happens with an imported finding |
|---|---|
| Commits and history | Its own commit (`integration_import`); readable at any commit; the commit's metadata names the source, record and hash |
| Branches, reviews, merges | Added on the investigator's branch, reviewed and merged like any other work. The same record on two branches is refused: merge instead |
| Clones | Inherited by every clone made after it |
| Case Intelligence (CM-5) | Searched, used by the assistant and by similar cases like a note. The **timeline** gets an entry for when each finding happened |
| Case links | A shared identifier in another case suggests a link (type "shared evidence or indicator"); the reason is pre-filled for the person to check |
| Sealing and access | A sealed finding is hidden from everyone but the case's supervisor and administrators, also in other cases' matches. Matches show only cases the reader can open |
| Report preview | A section "Findings imported from other systems" with source, record, hash, legal authority and commit |
| Audit and notices | `cm.integration.import` for every attempt (the key and the identifiers are never logged); a notice to the lead without any content |

## 2. Why it is needed

An investigation draws on many systems: the Log Analyzer finds a suspicious login, the CDR analysis shows who called whom, OSINT captures a public post. Until now these results reached a case only as files someone uploaded by hand, with no link back to where they came from. Now each finding carries its provenance, its legal authority and its hash, and stays permanently in the case history. And the same phone number, IP address or account in two cases is noticed, which is often how cases turn out to be connected.

## 3. Files created or changed

| File | What |
|---|---|
| `backend/app/casemgmt/integrations/indicators.py` | **New.** Checks and normal forms of the nine identifier types |
| `backend/app/casemgmt/integrations/contract.py` | **New.** The contract in one place: kinds of finding, limits, hashes, paths |
| `backend/app/casemgmt/integrations/sources.py` | **New.** Registering sources, keys (hashed), disable/enable, new keys, the policy check |
| `backend/app/casemgmt/integrations/imports.py` | **New.** Adding a finding (checks, commit, provenance, identifiers, notice); reading findings, a finding's detail, and identifiers across cases |
| `backend/app/casemgmt/integrations/test_source.py` | **New.** The fictional test source: eight invented findings |
| `backend/app/casemgmt/integrations/api.py` | **New.** 12 endpoints (section 7) |
| `backend/alembic/versions/0013_case_management_integrations.py` | **New.** 4 tables and their database rules |
| `backend/app/casemgmt/models.py`, `enums.py`, `schemas.py` | the tables, value lists and request/response shapes |
| `backend/app/casemgmt/engine.py` | an imported finding can't be revised by a commit |
| `backend/app/casemgmt/intelligence/timeline.py`, `index.py` | timeline entries for imported findings; hashes left out of the searchable text |
| `backend/app/casemgmt/report.py` | the report preview lists imported findings with their provenance |
| `backend/app/core/config.py`, `.env.example`, `docker-compose.yml` | settings `CM_TEST_SOURCE` and `CM_PHONE_COUNTRY_CODE` (the Docker version passes them on) |
| `backend/app/main.py` | the new endpoints |
| `backend/tests/test_cm_integrations.py` | **New.** 10 tests (section 8) |
| `frontend/src/kh/repo/imports/` | **New.** The Imported findings tab: findings, a finding's detail, indicators, "Add from a source", helpers and 6 tests |
| `frontend/src/kh/pages/AdminIntegrationsPage.tsx` | **New.** Administration → Integration sources |
| `frontend/src/kh/repo/LinkCaseDialog.tsx` | **New.** The link dialog, now shared by Similar cases and Indicators |
| `frontend/src/kh/repo/ReportTab.tsx`, `intelligence/TimelineView.tsx`, `labels.ts` | imported findings in the report, the timeline and notices |
| `frontend/src/App.tsx`, `RepositoryLayout.tsx`, `components/AppLayout.tsx` | the new tab, page and menu entry |
| `frontend/src/kh/api.ts`, `types.ts`, `src/api/schema.d.ts` | the new endpoints (types generated from the backend) |
| `frontend/e2e/walkthrough.py` | 3 new steps (section 8) |
| `docs/case-management/09-integration-contract.md` | **New.** The contract for the Knight Hawk systems |
| `docs/case-management/openapi.json` | regenerated: 102 endpoints in the module (12 new) |

## 4. Packages

None new.

## 5. Commands

```powershell
# Bring the database up to date (the Docker version does this by itself when it starts)
cd C:\case-search\backend; uv run alembic upgrade head

# The tests of this phase, then all of them
uv run pytest tests/test_cm_integrations.py -q
uv run pytest -q
cd C:\case-search\frontend; npm test; npx tsc -b; npm run lint
```

Settings (in `.env`):

| Setting | Default | Meaning |
|---|---|---|
| `CM_TEST_SOURCE` | `true` | The fictional test source. **Set `false` in production** |
| `CM_PHONE_COUNTRY_CODE` | `91` | The country of a phone number written without its country code |

To try it: log in as a platform administrator, open **Administration → Integration sources**, press **Add the fictional test source** (copy or close the key: the built-in source doesn't need it). Then in a case: **Imported findings → Add from a source**.

## 6. How it works

**Adding a finding** (`imports.add_to_case`). Everything is checked before anything is written:
1. The key → an enabled source (`sources.authenticate`). The person → may write to the branch, and the branch hasn't moved (`engine.writable_branch`, the same check as every commit).
2. The source's policy (`sources.check_policy`): same organisation, an allowed kind, the legal authority where required, the case classified high enough.
3. The finding (`contract.py`, `indicators.py`): record ID, hash format, summary, times with a timezone and not in the future, identifiers, the size of the result.
4. Its path: `imports/<source>/<folder>/<record>`. If the record ID loses characters on the way to a path, a short hash of it is added, so two different IDs never share a path.
5. A new artifact (`IMP-…`) or, for a record whose hash changed, a new version of the same one, then a commit `integration_import` and the branch moved forward.
6. The provenance row (`integration_imports`), one row per identifier (`integration_indicators`), and the notice. The API writes the audit event in the same transaction: all saved, or nothing.

**The database keeps it permanent** (migration 0013):

| Table | Kind | What |
|---|---|---|
| `integration_sources` | status-only | a source and its policy; only `status` and the key fields may change |
| `integration_source_events` | permanent | registered, disabled, enabled, key replaced: who, when, why |
| `integration_imports` | permanent | the provenance of each finding version, and the commit that added it |
| `integration_indicators` | permanent | each identifier a finding names, in its normal form |

**Identifiers across cases** (`imports.other_cases`). A match is shown only if the reader can open the other case, the finding is in the history of a repository they can open there, and it isn't sealed (unless they supervise that case). Otherwise nothing is shown, not even a count.

**The fictional test source** registers like any source (it is marked `fictional`), but sends from inside the server, only its own fixed catalogue: it can't be used to send anything else. Its findings use reserved example values only: documentation IP ranges, `.example` domains, the test mobile network 001-01, a test IMEI.

## 7. Endpoints in this phase

| Method and path | What | Who |
|---|---|---|
| `GET /api/v1/integrations/contract` | the contract as data | signed-in users |
| `POST /api/v1/integrations/add-to-case` | add a finding (login + `X-Integration-Key`) | a source, for a person who may write to the branch |
| `GET /api/v1/repositories/{id}/imports?ref=` | findings at a branch or commit | people who can open the case |
| `GET /api/v1/repositories/{id}/imports/{artifact_id}?ref=` | one finding: provenance, versions, uses, matches | people who can open the case |
| `GET /api/v1/repositories/{id}/indicators?ref=` | identifiers and the other cases where they appear | people who can open the case |
| `GET /api/v1/integrations/sources` | sources, policies, use, history | platform administrators |
| `POST /api/v1/integrations/sources` | register a source (the key is in the answer, once) | platform administrators |
| `POST /api/v1/integrations/sources/test-source` | register the fictional test source | platform administrators |
| `POST /api/v1/integrations/sources/{id}/status` | disable or enable, with a reason | platform administrators |
| `POST /api/v1/integrations/sources/{id}/key` | issue a new key, with a reason | platform administrators |
| `GET /api/v1/integrations/test-source` and `POST …/send` | the fictional findings, and adding one to a case | people who may write to the branch |

As everywhere in the module: no DELETE (405, audited), not visible answers 404, every request audited.

## 8. How to test

**Backend** (`tests/test_cm_integrations.py`, 10 tests, all fictional):

| Test | Proves |
|---|---|
| an imported finding is an immutable reference with a commit and an audit event | **the phase's acceptance**: `IMP-0001` with its provenance, an `integration_import` commit, the audit event (without the key or the identifiers); absent at the earlier commit; can't be revised by a commit; the database refuses changes and deletions; DELETE answers 405 |
| the same record twice is refused, a changed record becomes a new version | 409 for a duplicate; version 2 when the hash changes, version 1 intact at its commit; withdrawn and sent again |
| the source key and its policy are enforced | no key, a wrong key, a disabled source, a replaced key, a kind not allowed, a missing legal authority, a missing or zone-less time, a bad hash, a wrong IMEI check digit, too large a result, a case classified too low, a source of another organisation; nothing refused leaves anything behind |
| only people who may write to the branch can add findings | outsiders 404, viewers 403, contributors not on `main` but on their branch; the lead's notice carries no content |
| identifiers are matched only where the reader may look | the lead of case A doesn't see case B's match until they're on case B; the supervisor does; linking; a sealed finding disappears from matches |
| imported findings join the case record | found by Case Intelligence search, dated in the timeline, listed in the report, inherited by a clone |
| administrators manage sources; a key is shown only once | only the hash is stored; defaults; history of every change |
| the contract describes itself | 7 kinds of finding, 9 identifier types |
| the fictional test source | needs registering; adds through the same rules; a changed record becomes version 2; turned off by the setting |
| repeated safely with an Idempotency-Key | one commit, the same answer |

**Frontend** (`src/kh/repo/imports/imports.test.tsx`, 6 tests): times shown in their own timezone; the suggested link reason; the finding's detail with provenance, versions and a pre-filled link; the indicators table; the test source asking for registration, and adding a finding to the branch at its latest commit.

**Browser walk-through**: 3 new steps after Case Intelligence:
1. The administrator registers the fictional test source; its key is shown once.
2. The investigator adds a CDR and an IPDR result from it; each finding shows its requisition number and record ID.
3. A request **over HTTP with the source's key and the investigator's login**, as a real system would send it, adds an alert to the second case. The Indicators view of the first case then shows the suspect's phone number in both cases, already linked. The administrator's audit trail shows `cm.integration.import`.

## 9. Expected output

```
uv run pytest tests/test_cm_integrations.py -q       10 passed
uv run pytest -q                                     503 passed
npm test                                             Tests  42 passed (42)

Browser walk-through (the 3 new steps):
  [ok] CM-6 integration sources: the fictional test source registered by an administrator, its key shown once
  [ok] CM-6 add to case: a CDR and an IPDR result from the test source, each a permanent record with its provenance, in its own commit
  [ok] CM-6 the contract over HTTP (source key + login) adds an alert to KH-2026-0002; the suspect's phone is found in both cases, already linked
ALL 33 STEPS PASSED

Docker: smoke test 8/8, CM-6 checks 8/8 (read-only or refused requests); the development database: 0 cases, 0 sources, 0 imports
```

## 10. Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `403 A valid integration key (header X-Integration-Key) is required` | the request has no key, or a malformed one | send the source's key in `X-Integration-Key` |
| `403 This integration key isn't valid: it may have been replaced` | an administrator issued a new key | ask for the new key |
| `403 … may add only: …` | the kind of finding isn't in the source's policy | register a source with the right policy |
| `422 … needs authority_ref` | a CDR or IPDR result without its legal authority | send the requisition or order number |
| `409 … already holds this record, exactly as received` | the same record with the same hash was sent again | nothing to do: it is already in the case |
| `422 This record is already in … on branch …` | the record was imported on another branch | merge that branch, or bring yours up to date with it |
| `422 … needs a timezone` | a time like `2026-03-04T10:41:00` | add the zone: `2026-03-04T10:41:00+05:30` |
| "The fictional test source isn't registered yet" | no administrator has registered it | Administration → Integration sources → Add the fictional test source |
| The Imported findings tab offers no "Add from a source" | you can only read this repository | the lead adds findings on `main`, contributors on their own branches |
