# Step 14.4: Police-records connector (template)

Status: **done and verified** (2026-11-06), as a **template**. 300 backend tests pass (12 new). Tested only with the **fictional** sample export in `samples/police-records-FICTIONAL/`. **No real police data has been used, and none may be until access is authorised.**

Part 4 of the 5 parts of Step 14.

## 1. What this module does

It reads a police-records export (a folder with `records.csv` and one FIR document per row) and turns each row into the same internal `CaseRecord` the Supreme Court connector produces (Step 2). From there everything already works: storage, document processing, search, explanations, similar cases, timelines, the case assistant, access control and audit.

What makes it a **template**: the column names are an assumption (`fields.py`), modelled on a typical FIR register. The rules around them are meant to stay:

| Rule | How |
|---|---|
| Never less than **restricted** | `restricted` unless the export says `confidential`; "public" or "internal" in the export is raised to restricted, with a warning |
| **Identities protected by law are never imported** | `protected_identity=yes`: the record becomes `confidential`, party names are left out, a warning says so |
| **Nothing made up** | no title (an FIR has none, so the case ID is shown); missing or unreadable values stay empty, with a warning |
| **No personal data in messages** | warnings and failures name the column, never its value |
| **Every import is authorised and traceable** | the import script requires `--authorisation "<who, reference>"`, stored with the import run and in the audit log |
| **Files stay inside the data folder** | document names must be plain file names (`../` refused); the export is copied to `data/police_raw/` |

## 2. Why it is needed

The project's purpose is to search authorised police records later (spec, sections 1–2). The design (Step 1) promised that adding them means writing a connector and its access rules, not changing the rest of the application. This step proves that promise with a working connector, its tests, and an end-to-end check of who can see what, all before real data is involved.

## 3. Files created or changed

```
backend/app/connectors/police_records/
├─ fields.py        PLACEHOLDER field list: column -> CaseRecord field; identity; date formats
├─ mapping.py       one row -> CaseRecord, with the rules above
└─ connector.py     reads data/police_raw/<export>/records.csv (handles Excel's marker and line breaks in fields)
backend/scripts/police_import.py      --authorisation required; --dry-run checks without storing anything
backend/tests/test_police_records.py  12 tests
samples/police-records-FICTIONAL/     README, records.csv (3 FIRs), FICT-0001.txt, FICT-0002.txt: all invented
```

## 4. Packages

None (Python's own `csv`).

## 5. Commands

```powershell
cd backend

# Check an export: every row is read and reported (case IDs and column messages only); nothing is stored
uv run python -m scripts.police_import --folder ..\samples\police-records-FICTIONAL --authorisation "FICTIONAL SAMPLE: no real data" --dry-run

# Import it, then process its documents like the Supreme Court data
uv run python -m scripts.police_import --folder <export folder> --authorisation "<who authorised it, reference>"
uv run python -m scripts.process_documents
uv run python -m scripts.embed_chunks
uv run python -m scripts.extract_provisions
uv run python -m scripts.extract_timeline
```

The fictional sample was **not** imported into the development database, so the Supreme Court demo stays as it was. The tests import it into the test database instead (section 8). To see it in the web interface, run the import above without `--dry-run`, then log in as `analyst` (restricted clearance). The FIRs appear under the source "police_records"; `viewer` never sees them.

## 6. The code, explained

### The placeholder mapping (`fields.py`)

| Export column (assumed) | Becomes | Notes |
|---|---|---|
| `police_station_code`, `fir_year`, `fir_number` | case ID `FIR-<station>-<year>-<number>`; source ID `<station>/<year>/<number>`; reference numbers | an FIR number is unique within one station and one year. All three required |
| `police_station_name` | court or agency | |
| `district` | source extra | |
| `registration_date` | dates: registration (**first**, so it drives sorting and year filters) | day-first: `14-07-2026`, `14/07/2026`, `14.07.2026`, or `2026-07-14` |
| `occurrence_date` | dates: occurrence | |
| `acts_sections` | category | e.g. `BNS 318(4), 316(2)` |
| `complainant_name` | parties: complainant | **personal data** |
| `accused_names` | parties: accused (`;`-separated) | **personal data** |
| `investigating_officer` | officials | |
| `investigation_status` | status | |
| `final_report_type`, `final_report_date` | outcome (with its date); dates: final report | e.g. "Chargesheet filed", "Closure report" |
| `brief_facts` | summary | **personal data** (the narrative names people) |
| `sensitivity` | sensitivity | only `confidential` is kept as given; everything else becomes `restricted` |
| `protected_identity` | `yes`/`true`/`1`: confidential, no party names | see section 7 |
| `fir_document` | the FIR document (PDF, `.docx` or `.txt`) | processed and searched like a judgment |
| any other column | source extra | kept, shown on the details page, not standardised |

### `mapping.py`

`map_row()` returns a `CaseRecord`, or a `RecordFailure` when a row can't be identified. The import pipeline (Step 3) stores records, reports failures, and is safe to re-run: the same FIR is updated, never duplicated.

### `connector.py`

Reads the CSV as UTF-8, ignoring the invisible marker Excel puts at the start of files it saves. It lets the `csv` module handle line breaks inside quoted fields: FIR narratives exported from spreadsheets often contain them. The file's checksum and date go into each record's provenance.

### `scripts/police_import.py`

1. Refuses to run without `--authorisation` (at least a few characters: who, and their reference).
2. `--dry-run`: reads a temporary copy and prints one line per FIR (ID, sensitivity, documents, number of warnings), the totals and the warnings. **No names or narratives are printed.**
3. Otherwise: copies the export to `data/police_raw/<folder>/` (refusing to overwrite an earlier copy without `--replace`), imports it, and records `ingestion.import` in the audit log with the authorisation and the counts.

## 7a. Adapting to the real export: a settings file, not code (added 2026-11-06)

Most real exports will differ from the placeholder in names, not in meaning. Those differences are now settings:

1. **Inspect a small authorised sample** with the data owner:
   ```powershell
   uv run python -m scripts.police_inspect --folder <sample folder> [--records-file <name>.csv]
   ```
   It lists every template field it found, under which column name, how full each column is, which date formats occur, the code values (statuses, report types…), duplicate FIR identities and missing documents. It never shows names, narratives or the values of unrecognised columns.
2. It ends with a **suggested `format.json`**: the file name, column names (`"fir_number": "FIR No"` …), date formats and "yes" values. Check it with the data owner and save it in the export folder.
3. `police_import` then reads the export through that file. Tested (`tests/test_police_inspect.py`) with the fictional export rewritten the way a real one might look: renamed columns, another file name, dates with times. The inspector recognised every column, and the import produced the same records **with no code change**, protection rules included.

Code changes are still needed if the *meaning* differs, e.g. one combined FIR ID instead of three columns, or several rows per FIR.

## 7. Before importing real data: questions for the data owner

The template can't answer these; your organisation and the data owner must.

1. **Authority.** Who authorises access, on what legal basis, and for what purpose? Record the reference with every import (`--authorisation`).
2. **The real field list.** Column names, formats, code lists (e.g. status values) and which columns exist at all. Then update `fields.py` and `mapping.py`, and change the tests to match **before** importing.
3. **Identity.** Is station + year + FIR number really unique? How are corrections and re-registrations shown?
4. **Protected identities.** Victims of sexual offences (Section 72 BNS, formerly 228A IPC), children (Section 74 Juvenile Justice Act 2015; Section 23 POCSO Act) and others. How does the export mark them, and is "confidential, names not imported" the right handling? Should names also be removed from FIR texts and narratives, which the template does **not** do?
5. **Who may see what.** Which roles and clearances; should access follow the police station or district (per-case grants exist, Step 10)?
6. **Retention.** How long may records, uploads and audit entries be kept (14.3), and what must happen when a case is closed, sealed or expunged?
7. **Updates.** Full export each time, or changes only? How often? How are deletions communicated?
8. **Documents.** Format, scanned or text, language. Scanned FIRs need OCR (not built); text in Indian languages needs other models.

## 8. How to test

```powershell
cd backend; uv run pytest tests/test_police_records.py -v
```

| Test | Proves |
|---|---|
| a row becomes a restricted case record | every mapped field; no title; unknown columns kept; document path inside the export folder; no warnings |
| final report | becomes the outcome, with its date |
| **protected identities** | confidential; no parties; the names appear nowhere in the stored record |
| never less than restricted (5 cases) | `restricted`/blank stay restricted, `confidential` is kept, `public`/`internal` are raised with a warning |
| unidentifiable rows | reported by column; the person's name in that row is not in the message |
| bad date, unsafe document name | flagged, left out, never guessed; the bad value isn't repeated |
| the connector on the sample folder | 3 records; a line break inside a quoted field is read correctly; checksum recorded |
| **end to end** | the fictional export imported into the test database and its FIR texts processed. A **viewer** (public clearance) sees none of the FIRs and gets "not found" by ID. An **analyst** (restricted) sees FIR 0001 and 0002 and finds 0001 by its text ("advance for cotton yarn"), but not the confidential 0003. An **admin** (confidential) sees all three |

## 9. Expected output

```
> uv run python -m scripts.police_import --folder ..\samples\police-records-FICTIONAL --authorisation "FICTIONAL SAMPLE: no real data" --dry-run
  FIR-PS9999-2026-0001     restricted    documents 1  warnings 0
  FIR-PS9999-2026-0002     restricted    documents 1  warnings 0
  FIR-PS9999-2026-0003     confidential  documents 0  warnings 1
Would import 3 record(s): {'restricted': 2, 'confidential': 1}; 0 could not be read
  warning (1x): Identities protected by law: party names were not imported
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `records.csv not found` | Wrong folder, or the file is named differently | Point `--folder` at the folder that holds `records.csv` |
| `--authorisation must say who authorised the import` | Missing or too short | Give the name and reference of the authorisation |
| `... already exists. Use --replace` | This export folder was imported before | `--replace` to import it again (cases are updated, not duplicated) |
| `Missing police_station_code, ...: the FIR can't be identified` | Empty identity columns, or different column names | Check the header row against `fields.py` |
| Every row fails, or names land in the wrong fields | The real export's columns differ from the placeholder | Expected until step 7.2 is done: update `fields.py` and `mapping.py` and their tests |
| `... is not a recognised date` | A date format the template doesn't know | Add the format to `DATE_FORMATS` in `fields.py`, with a test |
| Garbled characters (e.g. `Ã©`) | The file isn't UTF-8 | Export as UTF-8, or add the right encoding to `connector.py` |
| FIR text not searchable | Documents not processed yet, or a scanned PDF | Run `scripts.process_documents`; scanned files need OCR (not built) |
