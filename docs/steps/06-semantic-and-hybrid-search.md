# Step 6: Embeddings + semantic search + hybrid ranking

Status: **done and verified** (2026-11-04). 126 tests pass. All 2,672 real chunks embedded.

## 1. What this module does

- **Embeddings:** every chunk of judgment text gets a vector of 384 numbers from a local AI model (`BAAI/bge-small-en-v1.5`). Texts with similar *meaning* get similar vectors, even with different words. Vectors are stored in `document_chunks.embedding` (pgvector).
- **Semantic search:** the query is embedded too, and PostgreSQL finds the passages closest in meaning (cosine similarity, via the HNSW index).
- **Hybrid search:** keyword results (Step 5) and semantic results are merged into one ranking. Each result gets a **relevance 0–100**, a **match type** (`keyword+semantic`, `keyword`, `semantic`) and the **similarity** of its best passage.

## 2. Why it is needed

Keyword search only finds the words you type. Users describe situations in their own words, and judgments use legal phrasing. On the real data:

| Query (paraphrased) | Keyword only | Hybrid: top result |
|---|---|---|
| "illegal building ordered to be pulled down" | **0** | G.N.R. Babu v. B.C. Muthappa (p.3); Gostho Behari Das v. Dipak Kumar Sanyal (p.9). Both are demolition cases |
| "retired government servant denied pension arrears" | **0** | M.L. Patil v. State of Goa (pension arrears), similarity 0.77 |
| "can the accused get pre-arrest bail" | **0** | Bail judgments (Senthil Balaji; Bhagwan Singh v. Dilip Kumar) |
| "conviction based only on circumstantial evidence" | 3 | The same 3, now matched by **both** methods |
| "chocolate cake recipe" | 0 | **0** (the similarity cut-off filters out unrelated matches) |

## 3. Files created or changed

```
backend/app/
├─ core/config.py            + embedding_model, model_cache_dir, semantic_min_similarity, preload_models
├─ embeddings/model.py       Embedder interface + SentenceTransformerEmbedder, loaded once, never downloads in the API
├─ embeddings/indexing.py    embed_pending_chunks(): resumable, model-aware, marks cases "indexed"
├─ search/semantic.py        nearest passages via pgvector, grouped per case
├─ search/keyword.py         refactored into reusable pieces (candidates, snippets)
├─ search/hybrid.py          Reciprocal Rank Fusion, relevance, passages from both methods
├─ schemas/search.py         + mode, relevance, match_type, semantic_similarity, matched_by, notices
├─ api/search.py             uses hybrid search; embedder injected as a dependency
└─ main.py                   preloads the model in the background at startup
backend/scripts/embed_chunks.py
backend/tests/
├─ conftest.py                    + FakeEmbedder (word hashing) used by API tests
├─ test_search_hybrid.py          11 tests
├─ test_embeddings_indexing.py    4 tests
├─ test_embeddings_real_model.py  3 tests with the real model (skipped if not downloaded)
└─ test_api_search.py             now pins mode "keyword"; +1 validation case
models/                           (git-ignored) the downloaded model, ~130 MB
```

## 4. Packages

| Package | Version | Licence |
|---|---|---|
| sentence-transformers | 6.2 | Apache-2.0 |
| torch (CPU build) | 2.15 | BSD-3-Clause and other permissive licences |
| transformers, tokenizers, huggingface-hub, safetensors | 5.22 / 0.23 / 2.4 / 0.8 | Apache-2.0 |
| numpy, scipy, scikit-learn | 2.5 / 1.18 / 1.9 | BSD |
| **Model** `BAAI/bge-small-en-v1.5` | | MIT |

The install took about 6.5 minutes (PyTorch is large).

## 5. Commands

```powershell
cd backend
uv add sentence-transformers                 # (done) installs PyTorch
uv run python -m scripts.embed_chunks        # first run downloads the model to models/, then embeds
uv run uvicorn app.main:app --reload --port 8000
```

Try it at http://127.0.0.1:8000/docs → `POST /api/search`:

```json
{"query": "illegal building ordered to be pulled down"}
{"query": "illegal building ordered to be pulled down", "mode": "keyword"}
{"query": "anticipatory bail", "mode": "semantic", "filters": {"year_from": 2023}}
```

After importing more documents, run `process_documents` and then `embed_chunks` again. Only new chunks are embedded.

## 6. The code, explained

### Embeddings (`embeddings/model.py`)

- The model runs **locally on the CPU**. No case text is sent to an outside service, which matters for police data later.
- **Short queries** are prefixed with BGE's retrieval instruction ("Represent this sentence for searching relevant passages: "). Passages are not. Step 8 (a whole document as the query) embeds its chunks like passages.
- Vectors are **normalised**, so similarity = cosine, between −1 and 1.
- The API loads the model **only from `models/`**; it never downloads during a request. If the model is missing, search **falls back to keyword search** and says so in `notices`.
- At startup the model loads in a background thread (~10 s), so the API answers keyword searches right away and the first semantic search isn't slow.

### Indexing (`embeddings/indexing.py`)

- Embeds chunks with no vector, or with a vector **from a different model**. Switching models re-embeds everything, and search only uses vectors from the current model, so incompatible vectors are never compared.
- Commits after each batch: an interrupted run resumes where it stopped.
- A case becomes `indexed` once **all** its chunks are embedded with the current model.
- **Speed: about 3 chunks/second on this CPU** (790 s for 2,672 chunks of ~280 words). That's expected: each ~400-token chunk needs roughly 28 billion operations. A query is short and takes 30–70 ms. For tens of thousands of documents, options are a GPU, an ONNX/OpenVINO-optimised model (sentence-transformers supports `backend="onnx"`), or running it overnight.

### Semantic search (`search/semantic.py`)

- `ORDER BY embedding <=> query` (cosine distance) uses the **HNSW index**. `SET LOCAL hnsw.ef_search = 400` and `hnsw.iterative_scan = strict_order` make the index return enough rows even when access rules or filters remove some.
- The access condition and filters are part of the same SQL query, exactly as in keyword search.
- **Cut-off `semantic_min_similarity = 0.60`.** Measured on the real data:

  | Query | Best match | Typical passage (median) |
  |---|---|---|
  | conviction based only on circumstantial evidence | 0.81 (Boby) | 0.55 |
  | anticipatory bail | 0.72 | 0.59 |
  | demolition of an illegal building | 0.70 | 0.52 |
  | pension arrears for retired employees | 0.73 | 0.49 |
  | arbitration award set aside | 0.76 | 0.56 |
  | *recipe for chocolate cake with strawberries* | **0.46** | 0.36 |
  | *football world cup final score* | **0.56** | 0.46 |

  0.60 removes clearly unrelated matches. It is a **noise filter, not a verdict**: anything above it is only "worth showing", and the ranking decides the order. It is model-specific, so it lives in settings next to the model name. Re-measure it whenever the model changes.

### Hybrid ranking (`search/hybrid.py`)

1. Keyword search returns its best cases (up to 200), and semantic search returns its best cases (up to 200).
2. **Reciprocal Rank Fusion:** each list contributes `1 / (k + position)` to a case's score. A case ranked well by both rises to the top; a case found by only one still appears. This works on **positions**, so the two very different score scales never need to be combined.
3. **Relevance = score ÷ best possible score × 100.** The best possible score is first place in every method that found something. So:
   - 100 = ranked first by every method that found matches;
   - if keyword search finds nothing (paraphrased query), the best meaning-based match gets 100;
   - a case found by only one method, while the other method found other cases, gets at most 50.
4. `k = 10` (not the common 60). With 60, on our short lists, the 40th weak result still scored about 61, which a user could read as "fairly relevant". With 10, scores fall off sensibly: 2nd ≈ 92, 3rd ≈ 85, 5th ≈ 73, 20th ≈ 37. To be tuned with real relevance labels in Step 9.
5. Each result shows up to 3 passages, alternating the best semantic and best keyword ones. Every passage says **how it matched** (`matched_by`) and its similarity to the query.

**Every response includes `relevance_note`** saying the score orders results and is **not a probability or legal equivalence**. The UI must show it.

### Testing without the real model

`FakeEmbedder` (in `conftest.py`) turns each word into one of 384 slots, so texts sharing words are "similar". It understands no meaning, but it is instant and deterministic. That makes it right for testing the plumbing: SQL, fusion, filters, access control and fallback. The **real** model is tested separately on what matters: a paraphrase beats an unrelated text, and an unrelated query stays under the cut-off.

## 7. How it connects to other modules

- Uses chunks from Step 4 and the HNSW index from Step 2. Keeps Step 5's keyword search as one half of the ranking.
- **Step 7** turns `matched_by`, passages and similarities into a readable "why it matched / how it differs" explanation.
- **Step 8** embeds an uploaded document's chunks with `embed_passages` and reuses semantic search per chunk.
- **Step 9** measures keyword vs semantic vs hybrid (`mode`) on labelled queries and tunes `k` and the cut-off.
- **Step 13** (chatbot) retrieves passages with the same access-checked semantic search.

## 8. How to test

```powershell
cd backend
uv run pytest -v          # ~17 s, of which ~10 s is loading the real model once
```

| Test file | Proves |
|---|---|
| `test_search_hybrid.py` | Hybrid is the default and explains its scores; finds cases strict keyword search misses; a paraphrase-only search scores its best match 100; lower ranks score clearly lower; relevance 0–100 and never increasing down the list; passages say how they matched; semantic mode respects access rules and filters; an unrelated query finds nothing; vectors from another model are ignored; without the model, hybrid falls back to keywords with a notice; the fusion maths |
| `test_embeddings_indexing.py` | Missing vectors are filled and the case marked `indexed`; nothing redone when complete; a model switch re-embeds all; a crash leaves the case unindexed and a rerun resumes with only the missing chunk |
| `test_embeddings_real_model.py` | 384 dimensions and unit length; "conviction based only on circumstantial evidence" is closer to "no eyewitness… chain of circumstances" than to a rent dispute; a cake recipe stays below the 0.60 cut-off |

## 9. Expected output

```
uv run python -m scripts.embed_chunks
Model BAAI/bge-small-en-v1.5 loaded in 54.7s        (first time, includes download; ~10 s afterwards)
Embedded 2672 chunks in 790.4s (3 chunks/s)
```

All 100 cases become `indexed`.

`POST /api/search {"query": "retired government servant denied pension arrears"}`:

```
100  semantic  sim=0.774  SHRI M.L. PATIL (DEAD) THROUGH LRS versus THE STATE OF GOA  p.1
 92  semantic  sim=0.710  STATE OF RAJASTHAN & ORS versus DR. HAMIR SINGH CHOUHAN    p.5
 85  semantic  sim=0.708  UNION OF INDIA & ORS. versus EX. SEP. R. MUNUSAMY          p.10
```

The same query with `"mode": "keyword"` finds 0 cases. Searches take about 100–200 ms.

## 10. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `notices`: "Meaning-based search is unavailable…" | Model not in `models/` (never downloaded, or folder moved) | `uv run python -m scripts.embed_chunks` |
| Semantic search finds nothing, keyword works | Chunks not embedded yet, or embedded with another model | `uv run python -m scripts.embed_chunks` |
| `RuntimeError: ... produces N-dimensional vectors, but the database stores 384` | `EMBEDDING_MODEL` changed to a model of a different size | Use a 384-dimension model, or change `EMBEDDING_DIM` with a migration and re-embed everything |
| First search after starting takes ~10 s | The model was still loading | Wait a few seconds after startup; keyword search works meanwhile |
| `embed_chunks` is slow (about 3 chunks/s) | CPU inference on long passages | Expected. Run it once after imports; it resumes if interrupted. For large volumes see section 6 |
| `uv add sentence-transformers` takes many minutes | PyTorch is about 200 MB+ to download, plus dependencies | Expected; only once |
| Warnings about symlinks from Hugging Face on Windows | Windows without Developer Mode can't create symlinks in the model cache | Harmless: files are copied instead |
| A clearly unrelated case appears with low relevance | It passed the 0.60 cut-off and the list is ranked | Expected: low relevance means weak. Step 9 tunes the cut-off with labelled examples |
| Same query gives slightly different order after re-embedding | Chunk text changed (e.g. after `--reprocess`) | Expected; re-run `embed_chunks` after reprocessing |
