# Development dataset: Indian Supreme Court Judgments

Verified on 2026-11-03 by listing the bucket and downloading the 2023 metadata file.

## Source

| | |
|---|---|
| Name | Indian Supreme Court Judgments |
| Registry page | https://registry.opendata.aws/indian-supreme-court-judgments/ |
| Code / docs | https://github.com/vanga/indian-supreme-court-judgments |
| Maintainer | Dattam Labs |
| License | **CC-BY-4.0**: free to use, including commercially, **with attribution**. The app must show the source on every case card and details page. |
| Coverage | Judgments from 1950 onward, updated roughly every two months |
| Access | Public S3 bucket `indian-supreme-court-judgments` (region `ap-south-1`). No AWS account needed. Plain HTTPS works. |

Base URL for downloads:

```
https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/
```

## Layout (confirmed)

```
metadata/
  parquet/year=YYYY/metadata.parquet     <- one row per judgment (use this)
  json/year=YYYY/...                     <- raw per-judgment JSON
  tar/year=YYYY/metadata.tar (+ .index.json)
data/
  pdf/year=YYYY/english/{path}_EN.pdf    <- individual PDFs (use these for a small subset)
  tar/year=YYYY/english/english.tar      <- whole year in one archive (2023: 854 files, 382 MB)
  tar/year=YYYY/regional/...             <- translations in Indian languages (not needed)
```

The metadata column `path` links a row to its PDF:
`path = "2023_16_872_887"` -> `data/pdf/year=2023/english/2023_16_872_887_EN.pdf`

## Metadata columns (2023 file: 856 rows)

| Column | Example | Filled (2023) | Use in our app |
|---|---|---|---|
| `title` | `RAM LAL versus STATE OF RAJASTHAN & ORS.` | 856 | Case title |
| `petitioner` | `RAM LAL` | 856 | Party (role: petitioner) |
| `respondent` | `STATE OF RAJASTHAN & ORS.` | 856 | Party (role: respondent) |
| `description` | *(empty)* | **0** | Not usable, so we leave it out |
| `judge` | `D.Y. CHANDRACHUD, A.S. BOPANNA` | 851 | Judges. Multi-judge benches are **comma-separated**, so we split them |
| `author_judge` | *(null)* | **0** | Not usable |
| `citation` | `[2023] 15 S.C.R. 808` | 856 | Reference number |
| `case_id` | `2023 INSC 1047` | 856 | Neutral citation. Reference number only: **not unique** (see below) |
| `cnr` | `ESCR010007902023` | 856 | **Source record ID**: unique in every row checked |
| `decision_date` | `04-12-2023` (DD-MM-YYYY) | 856 | Decision date (must parse day-first) |
| `disposal_nature` | `Appeal(s) allowed` | 845 | **Recorded outcome** (a short label, not a narrative) |
| `court` | `Supreme Court of India` | 856 | Court |
| `available_languages` | `ENG,HIN,PUN` | 856 | Informational |
| `raw_html` | `<select ...>` | 856 | Scraper artefact, **do not import** |
| `path` | `2023_15_808_820` | 856 | Links to the PDF |
| `nc_display`, `scraped_at`, `year` | | 856 | Provenance |

`disposal_nature` values in 2023: Appeal(s) allowed (410), Dismissed (204), Disposed off (143), Case Partly allowed (39), Directions issued (19), Matter referred to larger bench (14), Reference answered (11), *empty* (11), Rejected (2), Case Allowed (2), Dismissed as withdrawn (1).

## What this dataset does **not** contain

These fields are missing, so the app must show them as "not available". It must not guess them.

- **Case category / subject area** (criminal, tax, service, …): not in the metadata. It could be derived later from the judgment text, but it must be labelled *derived* and never shown as a recorded fact.
- **Status**: these are delivered judgments. The source does not say whether there were later reviews or curative petitions.
- **Summary / headnote**: none. Any summary we generate must be labelled *AI-generated*.
- **Timeline of events**: has to be extracted from the judgment text, with page references.
- **Filing date**: not in the metadata, so we cannot reliably calculate how long a case took.

## Findings from checking 2022 + 2023 (1,873 rows, Step 3)

- **`case_id` (neutral citation) is not unique.** 7 values are shared by different judgments with different dates, PDFs and CNRs. For example, `2022 INSC 740` appears on judgments dated 21-07-2022 and 29-09-2022. So we identify records by **`cnr`**, which had no duplicates, and keep the neutral citation as a reference number. Case IDs look like `SC-ESCR010007902023`.
- `decision_date` was a valid DD-MM-YYYY date in every row.
- 45 titles contain double spaces. We collapse repeated whitespace; no other changes are made to titles.
- Some parties are **anonymised by the source** (e.g. a title starting "X versus …"). Even public judgments can concern sensitive matters, so the app must never try to re-identify anyone.
- `description` was empty in every row of both years.

## Starter subset (downloaded in Step 3)

- Metadata for 2022 (1,017 English judgments) and 2023 (856).
- 50 judgments per year chosen by a seeded random sample (seed 42): **100 PDFs, 36.5 MB**, none failed.
- Stored in `data/raw/sc_judgments/` (git-ignored), mirroring the bucket layout. `manifest.json` records each file's URL, SHA-256 checksum and download time.
- Larger samples (`--per-year 200`) or more years add to the existing subset; files already downloaded are not fetched again.

## Things still to check in later steps

- Whether older judgments (e.g. 1950s–1990s) are scanned images that need OCR. All 100 PDFs from 2022–23 have a text layer (0 pages flagged `needs_ocr`). Older years are still unchecked: when they are added, check `case_documents.extraction_status`.
