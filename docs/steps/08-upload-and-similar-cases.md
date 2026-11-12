# Step 8: Upload a new case and find similar historical cases

Status: **done and verified** (2026-11-04). 173 tests pass. Demonstrated on real data and a fictional sample.

## 1. What this module does

The main workflow of the application:

1. **Upload** a new case document (PDF, Word `.docx` or plain text, up to 20 MB): `POST /api/uploads`.
2. The file is checked, stored safely, and passed through the same **extract → clean → chunk** steps as the historical judgments. Its passages are embedded and its cited provisions detected.
3. **Find similar historical cases:** `POST /api/uploads/{id}/similar`. Each result has:
   - relevance 0–100 and a **text similarity**;
   - **passage pairs**: a passage of the new case next to its closest passage in the historical case, with pages;
   - shared provisions, and provisions found on only one side;
   - reasons and differences.
4. **Delete** the upload when done: `DELETE /api/uploads/{id}` removes the file and everything derived from it.

There is also **"similar to an existing case"**: `GET /api/cases/{display_id}/similar`. It uses the same engine with a historical case as the query, excludes the case itself, and compares **recorded outcomes and decision years**. It is the basis for the "Compare" action on the details page.

Uploads are **not added to the historical cases**. They are queries, kept in their own tables.

## 2. Why it is needed

This is what the application is for: a user has a new case and wants to see relevant historical cases, and why each one is relevant.

## 3. Files created or changed

```
backend/
├─ alembic/versions/0004_uploads.py      uploads + upload_chunks tables
├─ app/
│  ├─ db/models.py                       + Upload, UploadChunk
│  ├─ uploads/service.py                 safe saving, extraction, embedding, deletion
│  ├─ similar/service.py                 the similarity engine (text + provisions, rank fusion)
│  ├─ schemas/similar.py                 UploadOut, SimilarRequest/Params, SimilarCase, PassagePair ...
│  ├─ api/uploads.py                     POST/GET/DELETE /api/uploads, POST /api/uploads/{id}/similar
│  ├─ api/cases.py                       + GET /api/cases/{id}/similar
│  ├─ documents/extract.py               + zip-bomb check for .docx, 1,000-page limit for PDFs
│  ├─ explain/indexing.py                + count_provisions() (shared with uploads)
│  ├─ embeddings/model.py                + min_passage_similarity
│  └─ core/config.py                     + max_upload_mb, similar_passage_min_similarity
└─ tests/test_uploads_similar.py         15 tests
samples/CASE-1042-fictional.txt          a FICTIONAL test case (labelled as such in the file)
data/uploads/                            (git-ignored) uploaded files, named <random id>.<ext>
data/raw/heldout/                        (git-ignored) unseen judgments used for testing
```

## 4. Packages

| Package | Version | Licence | Purpose |
|---|---|---|---|
| python-multipart | 0.0.33 | Apache-2.0 | FastAPI needs it to receive file uploads |

## 5. Commands

```powershell
cd backend
uv add python-multipart                 # (done)
uv run alembic upgrade head             # applies 0004
uv run uvicorn app.main:app --reload --port 8000
```

In the browser at http://127.0.0.1:8000/docs:
1. `POST /api/uploads` → **Try it out** → choose a file (e.g. `samples/CASE-1042-fictional.txt`) → Execute. Copy the `id`.
2. `POST /api/uploads/{upload_id}/similar` → paste the id, body `{}` (or `{"filters": {"year_from": 2023}, "limit": 5}`).
3. `DELETE /api/uploads/{upload_id}` when finished.
4. `GET /api/cases/SC-ESCR010001322022/similar`: cases similar to an existing case.

From PowerShell (PowerShell 7):

```powershell
$u = Invoke-RestMethod http://127.0.0.1:8000/api/uploads -Method Post -Form @{ file = Get-Item ..\samples\CASE-1042-fictional.txt }
Invoke-RestMethod "http://127.0.0.1:8000/api/uploads/$($u.id)/similar" -Method Post -ContentType application/json -Body '{}'
Invoke-RestMethod "http://127.0.0.1:8000/api/uploads/$($u.id)" -Method Delete
```

## 6. The code, explained

### Accepting a file safely (`uploads/service.py`)

| Risk | Protection |
|---|---|
| Wrong or dangerous file types | Only `.pdf`, `.docx`, `.txt`, **and** the content must match (PDF signature, valid Word zip, UTF-8 text) |
| Huge files | Streamed to disk in 1 MB blocks, rejected past `MAX_UPLOAD_MB` (20) → HTTP 413 |
| "Zip bomb" Word files | Total unpacked size checked before opening (limit 100 MB) |
| Enormous PDFs | More than 1,000 pages refused |
| Path tricks in the filename (`..\..\evil.txt`) | The user's filename is **never** used as a path: files are stored as `data/uploads/<random UUID>.<ext>`. The name is kept only for display, cleaned of folders and control characters |
| Half-accepted files | If anything fails (bad type, no text, database error), the stored file is deleted at once |
| Scanned documents | Rejected with a clear message (no text; OCR isn't supported yet) |
| Keeping sensitive data | `DELETE /api/uploads/{id}` removes the file and all derived data |

**Not yet in place (planned):**
- **Owner-only access to uploads**: done in Step 10. Each upload is visible only to the user who created it.
- **Upload size limit at the web server (Step 14).** In production, a reverse proxy (e.g. nginx `client_max_body_size`) should cap request size before the application sees it.

### Finding similar cases (`similar/service.py`)

Two signals, merged by rank (Reciprocal Rank Fusion, k = 10, as in Step 6):

1. **Text.** Every passage of the new case is compared with the stored passages using pgvector. For each historical case, each new-case passage keeps its **closest** match there, if that match scores at least **0.80**. The text similarity is the **average over all new-case passages** (0 where a passage has no match). So a case ranks high only if *much* of the new case is echoed in it, not because one sentence matches.
2. **Shared provisions**, weighted by rarity: weight = log(cases / cases citing it). Sharing "Section 27 of the Evidence Act" counts more than sharing Article 14, which many judgments cite.

Long documents are **sampled evenly** to 60 passages, which keeps an upload to about 20 seconds on a CPU. The response says when this happens.

**Why the passage cut-off is 0.80** (measured on the real data). Comparing every passage of three judgments with every other judgment:

| Query judgment | Typical best match in an *unrelated* judgment (median) | Top 1% | Best related judgments (mean best match) |
|---|---|---|---|
| Boby (murder, circumstantial evidence) | 0.72 | 0.84 | Vahitha 0.83, Harvinder Singh 0.82, Prakash Nishad 0.81: all circumstantial-evidence murder appeals |
| M.L. Patil (pension) | 0.76 | 0.85 | Priyanka 0.85, Anie Lukose 0.82, KPTCL 0.82: all service-law cases |
| Gostho Behari Das (demolition) | 0.73 | 0.82 | nothing above 0.79: no close analogue among the 100 |

Legal text is so alike that even unrelated passages score about 0.72. 0.80 keeps roughly the top 10% of matches, the distinctive ones. That is why this cut-off is separate from, and higher than, the 0.60 used for short search queries.

### Reasons and differences

Every result includes:
- **reasons:** "21 of 29 passages of the new case have a close match here (closest: pp.9–10 of the new case ↔ p.32 here, similarity 0.98)" and "Both cite: Section 302 IPC, Section 313 CrPC";
- **differences:** provisions cited only on one side. When the query is an *existing* case, also "Different recorded outcome: …" and "Decided in different years: …". When the query is an upload (no recorded outcome yet), the historical case's own decision date and recorded outcome are given for comparison;
- **passage pairs:** the 3 closest pairs, the start of each passage with its pages;
- **`relevance_note`:** neither score is a probability, and similar text doesn't make cases legally equivalent.

## 7. How it connects to other modules

- Reuses Step 4 (extract/clean/chunk), Step 6 (embeddings, pgvector, rank fusion) and Step 7 (provisions, page labels).
- **Step 9** evaluates these results with labelled examples and tunes both cut-offs (0.60, 0.80) and k.
- **Step 10** adds `owner_id` checks on uploads and audit-logs every upload, search and deletion.
- **Step 11** builds the upload screen, the result cards (relevance, reasons, passage pairs) and the compare view (`/api/cases/{id}/similar`).
- **Step 14** adds a retention job that deletes old uploads automatically.

## 8. How to test

```powershell
cd backend
uv run pytest tests/test_uploads_similar.py -v
```

| Test | Proves |
|---|---|
| text upload stored and described | stored as `<uuid>.txt`; passages and provisions detected |
| PDF and Word accepted | page count for PDF; none for Word |
| unacceptable files rejected and not kept | `.exe` → 415; HTML renamed `.pdf` → 422; empty → 422; scanned PDF → 422; nothing left on disk |
| size limit | → 413 |
| filename never used as a path | `..\..\evil.txt` is stored as `<uuid>.txt` inside `uploads/` |
| similar cases for an upload | the right cases first, `text+provisions`, relevance 100, shared provisions, reasons, passage pairs with pages, historical outcome given; restricted cases never returned |
| filters | year filter excludes older cases |
| similar to an existing case | excludes itself; "Different recorded outcome" and "Decided in different years" |
| restricted case as the query | → 404 |
| no model | upload warns; similarity uses provisions only and says so |
| long documents | 60 of N passages used, with a notice |
| get and delete | after delete: 404 and the file is gone |

## 9. Expected output (real data)

Run through the real API (`data/raw/heldout/` holds the unseen judgment):

**Sanity check: upload Boby's own judgment** (20 pages, 29 passages, 11 s):
```
100  text+provisions  text=1.0  BOBY versus STATE OF KERALA
     + 29 of 29 passages of the new case have a close match here
```

**Unseen judgment: John Anthonisamy v. State (2023)**, murder on circumstantial evidence (10 pages, 5.5 s, search 0.7 s):
```
 92  text+provisions  BOBY versus STATE OF KERALA        Both cite: Section 302 IPC, Section 201 IPC, Section 313 CrPC
 92  text+provisions  VAHITHA versus STATE OF TAMIL NADU  11 of 15 passages have a close match here
 77  text+provisions  PRAKASH NISHAD versus STATE OF MAHARASHTRA
 72  text+provisions  HARVINDER SINGH versus STATE OF HIMACHAL PRADESH
```
All four are circumstantial-evidence murder appeals.

**Fictional CASE-1042**: a cheating/criminal breach of trust FIR (s.406/420/120B IPC), accused seeks quashing under s.482 CrPC (0.8 s):
```
100  text+provisions  VIJAY KUMAR GHAI & ORS. versus THE STATE OF WEST BENGAL
     + 2 of 2 passages of the new case have a close match here (similarity 0.85)
     + Both cite: Section 120B IPC, Section 406 IPC, Section 420 IPC, Section 482 CrPC
```
*Vijay Kumar Ghai* (2022) concerns exactly this: whether a commercial dispute was given a criminal colour.

**Similar to an existing case**, `GET /api/cases/SC-ESCR010001322022/similar` (M.L. Patil, pension, 0.4 s):
```
100  text  STATE OF U.P. & ORS. versus SMT. PRIYANKA     6 of 6 passages ... | Different recorded outcome: Case Partly allowed (this case: Dismissed)
```

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `Form data requires "python-multipart" to be installed` | Package missing | `uv add python-multipart` |
| 415 "Only PDF, Word (.docx) and plain text…" | Other file type (e.g. `.doc`, `.jpg`) | Save as PDF, `.docx` or `.txt` |
| 422 "Unsupported file type" for a `.pdf` | The file isn't really a PDF | Re-export it as PDF |
| 422 "No text could be found…" | Scanned document | OCR is a later addition; use a text-based PDF |
| 413 | Larger than 20 MB | Split the file, or raise `MAX_UPLOAD_MB` in `.env` |
| 422 "Text file is not valid UTF-8" | Text saved in another encoding | Save as UTF-8 |
| Upload takes 10–20 s | Embedding passages on the CPU | Expected (about 3 passages/s) |
| `notices`: "Text comparison unavailable…" | Embedding model not in `models/` | `uv run python -m scripts.embed_chunks` |
| Few or no results for a short upload | Few passages to compare, and the 0.80 cut-off | Expected; shared provisions still count. Step 9 tunes the cut-off |
| `UnicodeEncodeError` printing results in a script | Windows console encoding (e.g. the "↔" symbol) | Run Python with `-X utf8`, or set `PYTHONIOENCODING=utf-8` |
