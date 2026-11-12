# Step 4: Document processing (extract → clean → chunk)

Status: **done and verified** (2026-11-04). 77 tests pass. All 100 judgments processed.

## 1. What this module does

For every imported document:
1. **Extract** the text page by page (PDF), or as one block (Word, plain text).
2. **Clean** each page: remove margin markers, page numbers and running headers/footers, fix pdfium's special characters, and join broken lines.
3. **Store pages** in the new `document_pages` table (one row per page).
4. **Chunk** the text into overlapping passages of up to 300 words that remember their page range, stored in `document_chunks`.
5. **Set the status:** `extracted`, `needs_ocr` (scanned pages) or `failed` (with a reason). A case whose documents are all extracted becomes `text_extracted`.

## 2. Why it is needed

Search works on **chunks**. Keyword search (Step 5) and AI search (Step 6) compare passages, not whole 80-page judgments. Each chunk's page range is what lets an explanation say "matched passage on pages 4–5". Page text also feeds the details page's "extracted text" view and chatbot citations.

## 3. Files created or changed

```
backend/
├─ alembic/versions/0002_document_pages_and_extraction_info.py   new table + 2 columns
├─ app/
│  ├─ db/models.py                 + DocumentPage, CaseDocument.extractor / extracted_at
│  └─ documents/
│     ├─ extract.py                PDF (pypdfium2), DOCX (python-docx), TXT; type from content
│     ├─ clean.py                  page-furniture removal
│     ├─ chunk.py                  sentence-based, overlapping, page-aware chunks
│     └─ processing.py             runs it all, stores results, sets statuses
├─ scripts/process_documents.py
└─ tests/
   ├─ conftest.py                  + build_pdf(): makes real PDFs for tests (incl. "scanned" pages)
   ├─ test_documents_extract.py    6 tests
   ├─ test_documents_clean.py      11 tests (2 added in Step 5)
   ├─ test_documents_chunk.py      8 tests
   └─ test_documents_processing.py 7 tests
```

## 4. Packages

| Package | Version | Licence | Purpose |
|---|---|---|---|
| pypdfium2 | 5.14 | BSD-3-Clause / Apache-2.0 | PDF text (Chrome's PDF engine) |
| python-docx | 1.2 | MIT | Word documents |
| lxml | 6.1 (installed with python-docx) | BSD-3-Clause | |

**Why not PyMuPDF** (suggested in the original spec)? It is licensed under the **AGPL-3.0**. If the app is offered to users over a network, the AGPL can require publishing the whole application's source code under the same licence. That is a real risk for an internal police deployment. pypdfium2 gives comparable results under a permissive licence. Extraction lives in `extract.py` alone, so the library can be swapped later if your organisation approves PyMuPDF.

## 5. Commands

```powershell
cd backend
uv add pypdfium2 python-docx                       # (already done)
uv run alembic upgrade head                        # applies 0002
uv run python -m scripts.process_documents         # only documents still 'pending'
uv run python -m scripts.process_documents --reprocess   # all documents again (e.g. after changing clean.py)
```

Look at the results:

```powershell
cd ..
docker compose exec db psql -U caseuser -d casesdb -c "SELECT extraction_status, count(*) FROM case_documents GROUP BY 1;"
docker compose exec db psql -U caseuser -d casesdb -c "SELECT page_start, page_end, word_count, left(text, 200) FROM document_chunks LIMIT 3;"
```

## 6. The code, explained

### What the real PDFs looked like (and the cleaning rules that came from it)

| Found in raw pdfium output | Rule in `clean.py` |
|---|---|
| Lines `A` `B` … `H` at the top of every page: SCR margin markers | Drop lines that are a single capital letter |
| `205` alone on a line | Drop lines that are only a number |
| `204 SUPREME COURT REPORTS [2022] 11 S.C.R.` at the top of even pages; case title + `[ABHAY S. OKA, J.]` at the bottom of odd pages | **Repetition rule:** a line in the top 3 (or bottom 3) recurring in that same position on ≥30% of pages, ignoring digits, is a header (or footer) |
| On page 1, pdfium merges header and footer: `362 SUPREME COURT REPORTS [2022] 3 S.C.R. [2022] 3 S.C.R. 362` | A line that *starts with* a repeated header (20+ characters) also counts |
| `U+FFFE` inside words: `tax￾payer` | Becomes `-` (pdfium's marker for a compound hyphen) |
| `U+F0B7 U+F020` before list items | Become `•` and a space (Symbol-font bullet) |
| `multi-` / `storeyed` split over lines | Joined as `multi-storeyed`; other line breaks become spaces |
| `12. In our view …` | Numbered paragraphs start on a new line |
| `off ence`, `fi led`, `Offi cer`: about 2,500 words split after a fi/fl/ff ligature (the space is really in the PDF). *Added in Step 5.* | Rejoin when one piece never appears on its own elsewhere in the document. After "ff", only when the right piece starts with a vowel, so `plaintiff has` and `cut off date` stay apart. Splits fell from 2,556 to 332, and nearly all of the 332 are real word pairs. |

**Two bugs found by checking real output, both fixed with tests:**
1. 24 first pages kept their header, because of the merged line above. Fixed by the "starts with" rule.
2. That fix then removed real text. On some first pages the petitioner line (`SHRI M.L. PATIL (DEAD) THROUGH LRS`) is also the start of the running title printed at the **bottom** of later pages. Fixed by checking top and bottom positions separately.

After both fixes: 0 of 1,817 pages contain the running header, and 0 first pages lose their opening line.

### Chunking (`chunk.py`)

- Text is split into sentences. Sentences are packed into a chunk until the next one would pass **300 words**.
- The next chunk starts with up to **50 words** (whole sentences) from the end of the previous one. A point that spans a boundary is still found intact.
- Any "sentence" over 250 words (tables, unpunctuated text) is cut first, so a chunk never exceeds ~300 words (~400 tokens). That fits the embedding model's 512-token limit in Step 6.
- Each chunk records `page_start` / `page_end`. Word documents have no fixed pages, so their chunks have `NULL` pages rather than invented ones.

### Processing (`processing.py`)

- **Path safety:** `local_path` must resolve to a file **inside** the data folder. Anything else is refused.
- **Scanned pages:** a page with fewer than 30 characters of text **and** an image is flagged `needs_ocr`. If more than half the pages are like that, the document's status is `needs_ocr`; otherwise it is `extracted` with a warning naming the pages. OCR itself is not part of this step.
- **Re-processing** deletes the document's old pages and chunks first, then writes new ones.
- **One bad file never stops the batch.** Each document runs in its own savepoint. Its error is stored as a short, safe message, e.g. `PDF could not be opened (password-protected)`.
- The **keyword index fills itself.** `search_vector` is a generated column, so PostgreSQL updates it whenever chunk text is written.

## 7. How it connects to other modules

- Reads documents created by Step 3's import (`extraction_status = 'pending'`, `local_path`).
- **Step 5** searches `document_chunks.search_vector` (already filled) and shows `document_pages` text.
- **Step 6** fills `document_chunks.embedding` for each chunk.
- **Step 8** uses the same `extract` → `clean_pages` → `chunk_pages` functions on an uploaded file, without storing it as a historical case.

## 8. How to test

```powershell
cd backend
uv run pytest -v
```

| Test file | Proves |
|---|---|
| `test_documents_extract.py` | Per-page PDF text; image-only pages detected; Word paragraphs + tables; UTF-8 text; damaged PDF → clear error; file type decided by content, not name |
| `test_documents_clean.py` | Special characters fixed; margin letters and page numbers removed; alternating headers/footers removed with body intact; merged first-page header removed **without** losing the party line; short fragments like "v." never remove sentences; one-off lines kept; short documents left alone; mid-page repeats kept; line joining and numbered paragraphs |
| `test_documents_chunk.py` | Empty input; single chunk; ≤300 words; real overlap of 1–50 words; every sentence included; page ranges incl. a chunk crossing a page break; unpunctuated text split; `None` pages kept |
| `test_documents_processing.py` | Pages + chunks stored and the case marked; keyword index filled ("appeal" finds "appeals"); re-processing replaces cleanly; only pending documents by default; missing file → `failed`; path outside data folder refused; scanned document → `needs_ocr` |

The tests build their own PDFs (`build_pdf` in `conftest.py`), so they don't depend on the downloaded data.

## 9. Expected output

```
processed 100/100

Documents: extracted 100 | needs_ocr 0 | failed 0
In database: 1817 pages, 2672 chunks (average 277 words)   (2,687 before the Step 5 ligature fix)
Took ~10s
```

Chunk sizes: minimum 25, median 287, maximum 300 words. All 100 cases are `text_extracted`. A first page now begins like `SHRI M.L. PATIL (DEAD) THROUGH LRS v. THE STATE OF GOA AND ANR. (Civil Appeal No. 4100 of 2022) MAY 20, 2022 …`.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `relation "document_pages" does not exist` | Migration 0002 not applied | `uv run alembic upgrade head` |
| `Documents: ... failed N` with `Document file is missing from the data folder` | PDFs deleted or `data_dir` changed | Re-run `scripts.sc_download` (it re-fetches missing files), then `process_documents` |
| `PDF could not be opened (password-protected)` | Encrypted PDF | Get an unencrypted copy from the source; it can't be processed as is |
| Many documents `needs_ocr` | Scanned judgments (likely in older years) | Expected. OCR (e.g. Tesseract) would be a later addition |
| A header still appears in page text | A layout the rules don't cover | Add a failing test to `test_documents_clean.py` using that page's lines, fix `clean.py`, then `--reprocess` |
| Real text missing from pages after changing `clean.py` | The cleaning rule is too broad | Check a few `document_pages` rows by hand. Both bugs above were found this way |
| A run takes minutes instead of ~10 s | Seen once and not reproduced (the rerun took 13 s). Probably other activity on the machine, such as OneDrive syncing `data/` | Re-run. If it repeats, pause OneDrive or move the project out of OneDrive |
| Words run together, e.g. `theappellant` | Spacing missing in the PDF itself | Can't be fixed reliably. Search still works on most of the text |
| Words like `suff er` or `aff ront` still split | The ligature rule stays cautious when the right piece could be a real word or starts with a consonant | A small residue (about 15 cases in 100 judgments) is accepted rather than risk gluing real words together |
