# Step 3: Supreme Court connector + subset download + import

Status: **done and verified** (2026-11-03). 47 tests pass. 100 real cases imported.

## 1. What this module does

1. **Download** (`scripts/sc_download.py`): fetches the metadata Parquet files for chosen years, picks a reproducible random sample of judgments, and downloads their English PDFs into `data/raw/sc_judgments/`. It writes a `manifest.json` recording each file's URL, SHA-256 checksum and download time.
2. **Connector** (`app/connectors/sc_judgments/`): reads the downloaded files (offline) and converts each selected metadata row into a `CaseRecord`.
3. **Import pipeline** (`app/ingestion/pipeline.py`): takes records from **any** connector, saves them with `upsert_case_record()`, and writes an `ingestion_runs` row with counts and failures.

## 2. Why it is needed

This is the first real data in the system. The split also proves the architecture works:
- Download is source-specific and needs the internet.
- The connector is source-specific but offline and repeatable.
- The pipeline is **generic**. A police-records connector would plug into the same `run_import()`.

## 3. Files created

```
backend/
├─ app/
│  ├─ connectors/
│  │  ├─ base.py                     SourceConnector interface + RecordFailure
│  │  └─ sc_judgments/
│  │     ├─ source.py                bucket URL, file layout, safe file-key check, attribution
│  │     ├─ manifest.py              manifest.json model
│  │     ├─ download.py              streaming download, checks, seeded sample
│  │     ├─ mapping.py               metadata row -> CaseRecord (all field decisions)
│  │     └─ connector.py             SupremeCourtConnector
│  ├─ ingestion/pipeline.py          run_import(): generic, any connector
│  └─ core/config.py                 + data_dir setting
├─ scripts/
│  ├─ sc_download.py
│  └─ sc_import.py
└─ tests/
   ├─ test_sc_mapping.py             9 tests using real 2023 rows
   ├─ test_sc_download_and_connector.py  10 tests with a fake in-memory bucket
   └─ test_import_pipeline.py        5 tests

data/raw/sc_judgments/               (git-ignored)
├─ manifest.json
├─ metadata/parquet/year=2022/metadata.parquet
├─ metadata/parquet/year=2023/metadata.parquet
└─ data/pdf/year=YYYY/english/*_EN.pdf   (100 files)
```

## 4. Packages

| Package | Version | Purpose |
|---|---|---|
| httpx | 0.28 | downloads (moved from test-only to a main dependency) |
| pyarrow | 26.0 | reads Parquet files |

## 5. Commands

```powershell
cd backend
uv run python -m scripts.sc_download --years 2022 2023 --per-year 50   # ~30 s, 36.5 MB
uv run python -m scripts.sc_import                                    # ~1.5 s
```

Options:
- `--per-year 200`: a bigger sample. It **adds to** the current one (the same seed always picks the same files first).
- `--years 2019 2020`: add more years.
- `--seed 7`: a different sample. Delete `data/raw/sc_judgments/manifest.json` first.
- `sc_import --years 2023`: import only one year.

Look at the data:

```powershell
cd ..   # project root
docker compose exec db psql -U caseuser -d casesdb -c "SELECT display_id, left(title,50), primary_date, outcome FROM cases ORDER BY primary_date DESC LIMIT 5;"
docker compose exec db psql -U caseuser -d casesdb -c "SELECT status, stats->>'created', stats->>'updated', stats->>'failed' FROM ingestion_runs ORDER BY started_at;"
```

## 6. The code, explained

### Mapping decisions (`mapping.py`)

| Source column | Goes to | Notes |
|---|---|---|
| `cnr` | `source_record_id`, `display_id = SC-<cnr>`, `reference_numbers.cnr` | **The identity.** Rows without it are reported as failures. |
| `case_id` | `reference_numbers.neutral_citation` | Not unique in the source, so not used as the identity |
| `citation` | `reference_numbers.citation` | |
| `title` | `title` | Whitespace tidied, nothing else changed |
| `petitioner` / `respondent` | `parties` | |
| `judge` | `officials` (one per judge) | Split on commas |
| `decision_date` | `dates[0]` (kind `decision`) → `primary_date` | Strict DD-MM-YYYY. An invalid date is left empty with a warning. |
| `disposal_nature` | `outcome` (+ `source_field`, date = decision date) | Blank → no outcome, listed as missing |
| `court` | `court_or_agency` | |
| `available_languages`, `nc_display`, `scraped_at`, `year`, `path` | `source_extra` | Kept for reference |
| `description` | `source_extra` only if non-blank | Meaning undocumented, so it is never treated as a summary |
| `raw_html` | **dropped** | Scraper artefact |
| *(none)* | `category`, `status`, `summary` = empty | Not in the source |
| | `sensitivity = public` | Published judgments |

### Safety and reliability

- **Path safety:** the source's `path` value becomes a file name. Anything other than letters, digits, `_` and `-` is refused, so a bad value like `../../x` can't write outside the data folder.
- **Download checks:** each file must return HTTP 200, PDFs must start with `%PDF-`, and there's a 50 MB size limit. Files are written to a `.part` file and renamed only when complete. Connection failures are retried 3 times.
- **Resumable:** the manifest is saved every 10 files. Re-running skips what's already there and retries only the failures.
- **Pipeline:**
  - Each record is saved in its own savepoint, so one bad record doesn't stop the rest.
  - A record that appears twice in one run is reported, not merged.
  - A crash still leaves the run marked `failed` with an error summary.
  - Failure messages store only the error *type*, because database error messages can contain record contents. That matters for police data later.

## 7. How it connects to other modules

- Uses `CaseRecord` and `upsert_case_record()` from Step 2.
- **Step 4** picks up every `case_documents` row with `extraction_status = 'pending'`, opens its `local_path` (relative to `data_dir`), extracts text and creates chunks.
- **Step 14** adds `app/connectors/police_records/`, which implements the same `SourceConnector` and is imported with the same `run_import()`.
- The attribution text in `source.py` (`ATTRIBUTION`) is shown in the UI from Step 11.

## 8. How to test

```powershell
cd backend
uv run pytest -v
```

| Test file | Proves |
|---|---|
| `test_sc_mapping.py` | A real row maps correctly; `raw_html` and blanks are never imported; a missing outcome isn't guessed; benches split; bad dates warn; a missing PDF warns; a missing CNR fails; two judgments sharing a neutral citation stay separate |
| `test_sc_download_and_connector.py` | Files and checksums are saved; HTML error pages, oversized files and unsafe keys are refused; samples are reproducible and grow as supersets; re-runs only retry failures; the connector yields only selected rows; a deleted PDF is noticed |
| `test_import_pipeline.py` | Counts are correct; re-import updates without duplicates; in-run duplicates are reported; a database rejection doesn't stop the rest; a crash is recorded |

None of these tests need the internet: a fake in-memory "bucket" stands in for S3.

## 9. Expected output

```
[2022] downloading metadata ...
[2022] 1017 English judgments available, 50 selected
...
PDFs:       100 downloaded (36.5 MB), 0 failed

Run 24a964d6-...: succeeded
  seen 100 | created 100 | updated 0 | failed 0 | with warnings 0
```

A second `sc_import` gives `created 0 | updated 100`. In the database: 100 cases, 100 documents (all `pending`), decision dates from 2022-01-04 to 2023-12-07. Outcomes: Appeal(s) allowed 51, Dismissed 27, Disposed off 16, Case Partly allowed 4, Matter referred to larger bench 1, Case Allowed 1. Every case's `missing_fields` is `["category", "status", "summary"]`.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `manifest.json not found. Run: uv run python -m scripts.sc_download` | Import before download | Run the download first |
| `PDFs: ... N failed` with `Network error: ConnectError` | No internet, proxy or firewall | Check the connection and re-run; only failures are retried |
| `failed: ...: HTTP 403/404` | File not in the bucket (rare) | That case is still imported, with a warning, and without a document |
| `Existing subset used seed 42; delete ... to start a new one` | Changed `--seed` | Delete `data/raw/sc_judgments/manifest.json` (and the PDFs if you want) |
| Import shows `failed` with `Same source record appeared twice` | The source has the same CNR twice | Expected protection: the first is kept. Check the source rows. |
| Import shows `Database rejected the record (UniqueViolation)` | Two records produced the same `display_id` | Check the connector's ID rule |
| `UnicodeEncodeError` printing titles in the terminal | Windows console encoding | Set `$env:PYTHONIOENCODING = "utf-8"` first |
| Very slow or locked files under `data/` | The project is inside OneDrive and it is syncing the PDFs | Move the project outside OneDrive, or pause OneDrive sync |
