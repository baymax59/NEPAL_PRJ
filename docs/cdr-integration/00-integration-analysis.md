# CDR Module Integration Analysis

> **Status: DRAFT – awaiting owner decisions listed in §4 before implementation begins.**
> Written 2026-11-12. Covers the CDR India Showcase Package (three developer modules)
> against the Knight Hawk Case Management system (`C:\case-search`).

---

## 1. What the CDR package contains

The package is three separate developer modules that together form a **Call Detail Record (CDR)
Analysis** system designed for the Nepal/India Police. Each module is a FastAPI + React app
with its own PostgreSQL database and authentication scheme.

| Module | Folder | Core purpose |
|---|---|---|
| **D1** | `CDR-Analysis-Developer1/` | Upload CDR files (6 formats), parse, validate, normalize, store CDR records, detect duplicates, track chain of custody |
| **D2** | `CDR_Investigation_System/` | Search CDR records, call frequency analysis, call graph / link analysis, communication anomaly detection, top contacts, CSV export |
| **D3** | `d3-location-investigation/` | Cell tower master data, map, subscriber timeline, movement trajectory, common-tower analysis, co-location, geographic search, investigation summary, PDF/XLS reports, audit trail view, chain-of-custody view, evidence verification |

### D1 feature list in detail

| Feature | File / migration |
|---|---|
| Multi-format file upload: CSV, XLS, XLSX, XML, ASN.1, IPDR | `parsers/*.py`, migration `c55efe12a4b6` |
| Field validation and normalization per row | `services/validation_service.py`, `normalization_service.py` |
| Canonical MSISDN (Nepal `np-msisdn.v1`, India `in-msisdn.v1`) | `services/msisdn_rule.py`, migration `f3b8a1c6d7e2` |
| UTC timestamp normalization (confirmed IANA zone) | `services/normalization_service.py`, `msisdn_dispatch.py` |
| Duplicate detection: file SHA-256 + per-record fingerprint | `services/duplicate_service.py`, migration `a259cd9fc9be` |
| Import batch status tracking | `models/import_batch.py` |
| Chain-of-custody events (append-only) | `models/custody_event.py`, `services/custody_service.py` |
| Evidence source file storage (SHA-256, unencrypted on disk) | `models/source_file.py` |
| File integrity re-verification endpoint | `api/routes/evidence.py` |
| Case registry and case access (provisional) | `models/case_registry.py`, migration `e1ede90aa7cf` |

### D2 feature list in detail

| Feature | Note |
|---|---|
| CDR search (keyword, date, party, cell, type) | Reads own `cdr_records` table |
| Frequency analysis and top contacts | Aggregation queries |
| Call graph / link analysis (which numbers called which) | NetworkX-based |
| Communication anomaly detection (8 rules) | `missing_cell_id`, call bursts, etc. |
| Behaviour profiling | Time-of-day, type distribution |
| Multi-number / IMEI analysis | Cross-subscriber |
| CSV export | Full numbers in export |
| **Own CDR import endpoint** | `POST /api/cdr/import` – CSV only, `ON CONFLICT DO NOTHING` |
| **Own `cdr_records` table** | Incompatible DDL with D1's table |
| **Own case registry** | `cases` table, case-sensitive PK, no access control |
| **Own audit log** | `audit_events` with **full phone numbers** in `parameters` column |

### D3 feature list in detail

| Feature | Module ID |
|---|---|
| Cell tower master data (import, version history, verification) | D3-01 |
| Tower location map (MapLibre GL, offline tiles) | D3-02 |
| Subscriber / device timeline | D3-03 |
| Movement trajectory | D3-04 |
| Common tower analysis | D3-05 |
| Co-location analysis | D3-06 |
| Geographic search | D3-07 |
| Location anomaly detection (impossible travel, etc.) | D3-08 |
| Investigation summary (frozen, versioned) | D3-09 |
| PDF and XLS/XLSX reports with SHA-256 and methodology | D3-10 |
| Audit trail view | D3-11 |
| Chain-of-custody view | D3-12 |
| Evidence file re-verification | D3-13 |
| AES-256-GCM encrypted file store | Phase 0 Step 4 |
| Transactional outbox (event delivery, retries, dead letters) | Phase 0 Step 6 |
| Ports-and-adapters security (identity, authorization, case-access ports) | Phase 0 Step 7 |

---

## 2. What Knight Hawk already has (do not duplicate)

| Capability | Where in Knight Hawk |
|---|---|
| Case management (registration, lifecycle, team, history) | `backend/app/casemgmt/` |
| Role-based access: super_admin → viewer, oversees/open flags | `backend/app/casemgmt/access.py` |
| JWT authentication + strong-auth requirement | `backend/app/auth/` |
| Append-only audit history (hash-chained, signed checkpoints) | `backend/app/audit/` |
| File and evidence management (notes, exhibits, versions, withdrawal) | `backend/app/casemgmt/files.py`, `artifacts.py` |
| File upload endpoint | `backend/app/api/uploads.py` |
| PostgreSQL database (Alembic, migrations 0001–0026) | `backend/alembic/versions/` |
| React + Mantine 9 UI with Knight Hawk design | `frontend/src/kh/` |
| Docker deployment (Caddy HTTPS, PostgreSQL 17 + pgvector) | `docker-compose.yml` |

---

## 3. What will be integrated (after owner decisions in §4)

The following CDR capabilities fit naturally into Knight Hawk as a new **CDR Analysis** tab on
each case. Knight Hawk cases become the case authority; the CDR module reads case IDs and
access decisions from Knight Hawk's APIs.

### 3A. Features that will be integrated cleanly

| CDR capability | Integration plan |
|---|---|
| **D1 CDR file import** (CSV, XLS, XLSX, XML, ASN.1, IPDR) | New evidence type in Knight Hawk's file system. Import wizard as a dialog on the case's Files tab. |
| **D1 CDR record storage and normalization** | New DB schema `cdr_d1` in Knight Hawk's PostgreSQL instance, accessed by a new backend package `app/cdr/`. |
| **D1 duplicate detection** | Integrated into the import pipeline; duplicates shown in the import wizard result. |
| **D1 custody events** | Fed into Knight Hawk's existing audit trail (same hash-chain mechanism). |
| **D2 CDR search** | New search panel on the case, reads from D1's normalized records via a read-only projection. |
| **D2 call graph / link analysis** | New "Call Graph" section on a case. |
| **D2 frequency and top contacts** | Charts in the CDR Analysis tab. |
| **D2 anomaly detection** | Flags shown alongside records. |
| **D3 tower master data** | New "Towers" admin screen (administrator / supervisor only). |
| **D3 timeline** | "Timeline" view under CDR Analysis on a case. |
| **D3 movement trajectory** | Interactive map on CDR Analysis. |
| **D3 common tower / co-location** | "Links" view on CDR Analysis. |
| **D3 geographic search** | Filter on the map view. |
| **D3 investigation summary** | Frozen summary document per case. |
| **D3 PDF report** | Download button on the case (with the statutory disclaimer notices). |
| **D3 evidence re-verification** | Button on the evidence row to re-verify file integrity. |
| **D3 audit trail and custody views** | These read Knight Hawk's existing audit chain, so no extra data is stored. |

### 3B. What is NOT integrated (removed with reasoning)

Each item below is kept out of the integration. The reasoning is provided so the owner group
can decide if any item should be re-examined.

| Item | Why it is removed | Risk if kept |
|---|---|---|
| **D2's own CDR import endpoint** (`POST /api/cdr/import`) | Exact duplicate of D1, CSV only. Running it on the same database would silently ignore D1's normalized rows and create its own incompatible table. The integration audit classifies this as a Blocker (DB-01). | Data corruption if both import paths write to the same DB. |
| **D2's own `cdr_records` table** | Incompatible schema (different PK, `event_timestamp NOT NULL`, India-only MSISDN rule). The audit classifies this as a Blocker (DB-01, DB-02). | Breaks all cross-module joins; phone-number normalization diverges. |
| **D2's own `cases` table** | Knight Hawk is the case authority. D2's table has no access control, case-sensitive PK, and no link to Knight Hawk's case IDs. The audit classifies this as High severity (DB-05). | A different case list; investigators see cases they should not. |
| **D1's `case_registry` / `case_access` tables** | Same reason: Knight Hawk already has a richer, access-controlled case system. Having a second registry creates divergence. | Two sources of truth for which cases exist; a case closed in Knight Hawk stays open in D1. |
| **D3's separate token / SAMPLE auth system** | Knight Hawk uses signed JWT tokens issued by its own auth service. D3's SAMPLE tokens (`SAMPLE-D3-v1-DEV.*`) are explicitly DEV-only and refused in production. D3 already has the right design (ports and adapters) to plug in a production identity provider. | A second login screen and credentials; investigators need two logins. |
| **D2's `audit_events` table (full phone numbers)** | The integration audit flags this as High severity (DB-06). D2 stores raw subscriber identifiers in `audit_events.parameters`. Knight Hawk's audit trail never stores raw identifiers; D3's approach (pseudonyms via HMAC) is correct. | GDPR / data-protection exposure; audit logs contain data the analyst is not authorized to see. |
| **D2's trusted `X-Analyst-Id` header auth** | Dev-only mechanism with no token validation. Would be a critical auth bypass if left in a production build. | Complete auth bypass for anyone who can forge the header. |
| **D2's India MSISDN rule as a database default** (`Asia/Kolkata` default timezone, `+91` normalization) | Knight Hawk's CDR integration follows the agreed `np-msisdn.v1` / `in-msisdn.v1` rule applied by D1. D2's hard-coded India default conflicts and is already removed in the integration plan. | Nepal numbers mis-labelled as unknown; subscriber identity collisions. |
| **D3's DEV-ONLY sign-in badge** | Knight Hawk handles login. The badge is correct on the CDR standalone demo but has no meaning inside Knight Hawk. | Confusing UX – investigators see "DEV-ONLY sign-in" on a production case screen. |
| **D3's Redis dependency** (see §4-D) | Knight Hawk does not use Redis. D3's current background work (outbox delivery) uses PostgreSQL leases, not Redis. Redis was planned for future Celery workers that have not been implemented. | An extra container that is never used adds deployment complexity and attack surface. |

---

## 4. Owner decisions required before implementation begins

Please give a yes/no decision on each of these. The team can answer all at once or one at a
time; the item number identifies where implementation is blocked.

---

### Decision 4-A — PostGIS (D3 maps and location analysis)

D3's location features (map, movement, geographic search, co-location) use PostGIS spatial
queries. Knight Hawk's current PostgreSQL 17 instance does **not** have PostGIS.

**Option 1 (Recommended):** Add the PostGIS extension to Knight Hawk's existing PostgreSQL
container. PostGIS installs as a single extension; the Docker image `postgis/postgis:17-3.5`
is a drop-in replacement for `postgres:17`. All CDR location tables live in schema `cdr_d3`
in the same database. No second container.

**Option 2:** Run D3's location service in a separate PostGIS container alongside Knight Hawk's
database. Knight Hawk's backend calls D3's HTTP API for location data. This keeps databases
separate but adds a container and an internal API to maintain.

**Question:** Which option?

---

### Decision 4-B — Offline map tiles

D3's map currently uses a **synthetic grid** with no real geography (no roads, borders, place
names). The package notes require keeping the disclaimer "Base map source is not configured"
visible. For real investigations the map needs real geographic data.

Options (all offline, no data leaves the server):

**Option 1 (Recommended):** Download a country-level OpenStreetMap extract (Nepal or India,
~300 MB) and serve it with `martin` (a tile server, Rust binary, runs in Docker). No external
network calls.

**Option 2:** Keep the synthetic grid. The map shows tower dots with no background. Only the
geographic-search polygon tool is affected.

**Question:** Real tiles or synthetic grid?

---

### Decision 4-C — CDR reports (D3-10): court-evidence disclaimers

D3's PDF reports currently carry the statutory notice:

> "NOT CERTIFIED: development reports are not official or certified forensic reports."

The integration audit document and the package itself state this notice must stay visible even
in production (it reflects a real limitation: the reports are not certified by a recognized
forensic authority). Similarly, the map notice "DEMO MAP – NOT FOR COURT EVIDENCE" must remain
on the location map.

**Question:** Confirm that both notices will remain visible in the production build.

---

### Decision 4-D — Redis

D3 includes a Redis container in its Docker setup. As noted in §3B, Redis is not used by
any currently implemented feature; the outbox delivery runs on PostgreSQL leases.

**Recommendation:** Do not add Redis to Knight Hawk's deployment. The outbox can use
PostgreSQL job queues (there are several well-tested libraries, or D3's existing
PostgreSQL-lease outbox). Redis can be re-added when a Celery-based background job is
actually needed.

**Question:** Confirm Redis is not added yet.

---

### Decision 4-E — D1 source-file encryption

D1 stores CDR source files (the uploaded CDR files) on disk **unencrypted**, protected only
by filesystem permissions and a SHA-256 hash. D3's own files use AES-256-GCM.

Knight Hawk's existing evidence files (documents, images) are stored according to the platform's
standard (accessible to authorized users through the API).

**Option 1 (Recommended):** Encrypt D1 CDR source files using the same AES-256-GCM pattern
D3 uses. The key is stored in Knight Hawk's key management. This aligns CDR evidence with the
rest of Knight Hawk's security model.

**Option 2:** Keep D1 source files unencrypted. The hash chain still guarantees integrity;
only confidentiality of the uploaded file on disk is weaker.

**Question:** Encrypt CDR source files (Option 1) or not (Option 2)?

---

### Decision 4-F — D2 anomaly alert: "direction" search bug

D2 has a known internal inconsistency (confirmed in code): when searching by `direction=incoming`
with a phone number, the results actually return calls that number *made* (outgoing), not
calls it *received*. This is because D2 internally treats "incoming" as "B-party originated".
The bug is encoded as expected behavior in D2's own tests.

**Recommendation:** Fix the semantic so that `direction=incoming` returns calls *received* by
the searched number, matching the plain-language meaning and D1's `incoming` definition.

**Question:** Fix the direction bug (Recommended) or preserve D2's current behavior?

---

### Decision 4-G — Shared audit and custody stores (C-05 / C-06)

The CDR integration audit recommends a **shared custody and audit store** that all three CDR
modules write to. Knight Hawk already has an append-only, hash-chained audit trail. The
question is how CDR events relate to it.

**Option 1 (Recommended):** CDR custody events (file received, hashed, verified, etc.) and
CDR audit events (import started, record search, report exported) are written into Knight
Hawk's existing audit trail as new event kinds. The hash chain covers them. No second store.

**Option 2:** Keep D3's transactional outbox and deliver events to a future shared CDR store.
This matches D3's original design but requires a second audit system to be built and operated.

**Question:** Use Knight Hawk's audit trail for CDR events (Option 1) or build a separate CDR
audit store (Option 2)?

---

## 5. What happens next

Once the team responds to §4:

1. **Alembic migration** — new schema `cdr_d1` and `cdr_d3` inside Knight Hawk's PostgreSQL.
   D1 tables: `cdr_import_batches`, `cdr_source_files`, `cdr_records`, `cdr_duplicate_detections`,
   `cdr_custody_events`, `cdr_validation_errors`. D3 tables: `cdr_towers`, `cdr_tower_versions`,
   `cdr_location_findings`, etc. All under schema prefixes so they never clash with
   Knight Hawk's existing tables.

2. **Backend package** — `backend/app/cdr/` with sub-packages: `parsers/`, `import_service/`,
   `analytics/`, `location/`, `reports/`. All routes under `/api/v1/cdr/`. All routes use
   Knight Hawk's existing `require_auth` / `require_case_access` dependencies.

3. **Frontend** — New "CDR Analysis" tab on each case's layout. Uses Mantine 9 and Knight Hawk
   design tokens. MapLibre GL JS for the location map (same library D3 uses; no external tiles
   if Decision 4-B chooses Option 2 / 4-A Option 2 stays).

4. **Tests** — New files `backend/tests/test_cdr_import.py`, `test_cdr_analytics.py`,
   `test_cdr_location.py`, `test_cdr_reports.py`. Mutation-checked. No test data in `casesdb`.

5. **Documentation** — This folder (`docs/cdr-integration/`) expands with one file per major
   component; the main `README.md` and `docs/HANDOVER.md` are updated.

---

## 6. Decisions log (filled as decisions are confirmed)

| Decision | Status | Date | Answer |
|---|---|---|---|
| 4-A PostGIS option | Pending | — | — |
| 4-B Map tiles | Pending | — | — |
| 4-C Report disclaimers | Pending | — | — |
| 4-D Redis | Pending | — | — |
| 4-E Source-file encryption | Pending | — | — |
| 4-F Direction bug fix | Pending | — | — |
| 4-G Audit store | Pending | — | — |
