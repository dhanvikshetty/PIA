# 🧠 Placement Buddy Puddy — Deep Dive Technical README

> A complete code-level walkthrough of every component, an honest bug/issue report, and concrete improvement suggestions. Written after reading every single file in the project.

---

## 📋 Table of Contents

1. [What This Project Actually Is](#1-what-this-project-actually-is)
2. [Full Data Flow — End to End](#2-full-data-flow--end-to-end)
3. [Component-by-Component Breakdown](#3-component-by-component-breakdown)
   - 3.1 [config.py — Settings](#31-configpy--settings)
   - 3.2 [main.py — FastAPI Entry Point](#32-mainpy--fastapi-entry-point)
   - 3.3 [ingestion/pdf_loader.py](#33-ingestionpdf_loaderpy)
   - 3.4 [ingestion/chunker.py](#34-ingestionchunkerpy)
   - 3.5 [ingestion/embedder.py](#35-ingestionembedderpy)
   - 3.6 [ingestion/structured_extractor.py](#36-ingestionstructured_extractorpy)
   - 3.7 [ingestion/pipeline.py](#37-ingestionpipelinepy)
   - 3.8 [db/vector_store.py](#38-dbvector_storepy)
   - 3.9 [db/mongo_store.py](#39-dbmongo_storepy)
   - 3.10 [rag/retriever.py](#310-ragretrieverpy)
   - 3.11 [rag/reranker.py](#311-ragrerankerpy)
   - 3.12 [rag/query_router.py](#312-ragquery_routerpy)
   - 3.13 [rag/generator.py](#313-raggeneratorpy)
   - 3.14 [resume/analyzer.py](#314-resumeanalyzerpy)
   - 3.15 [eval/run_eval.py](#315-evalrun_evalpy)
   - 3.16 [api/routes.py & schemas.py](#316-apiroutespy--schemaspy)
   - 3.17 [Frontend](#317-frontend)
4. [Bugs and Real Issues Found](#4-bugs-and-real-issues-found)
5. [What Could Be Much Better](#5-what-could-be-much-better)
6. [What Is Actually Done Well](#6-what-is-actually-done-well)

---

## 1. What This Project Actually Is

Puddy is a **Retrieval-Augmented Generation (RAG)** system built specifically for college placement preparation. The core idea is:

- You dump company interview experience PDFs and job description PDFs into a `data/` folder
- The system ingests them, chunks them, embeds them into a vector database (ChromaDB), and also runs an LLM to extract structured facts (interview questions, company metadata, salary packages)
- When a student asks a question like *"What SQL questions did ProcDNA ask?"*, the system doesn't just do a keyword search — it does a **hybrid search** (dense semantic vectors + BM25 keyword), **fuses** both result lists using Reciprocal Rank Fusion (RRF), then **re-ranks** the top 20 results with a cross-encoder, then feeds the top 5 into Gemini to generate a cited answer
- There's also a resume analyzer that extracts skills from an uploaded resume and compares them against JD skills to produce a gap analysis
- There's a quantitative eval harness that benchmarks the pipeline using labeled Q&A pairs

The tech stack is: **FastAPI** backend, **React 19 + Vite** frontend, **ChromaDB** for vectors, **JSON files** as the structured store (with MongoDB as a declared but unimplemented option), **sentence-transformers** for embeddings, **cross-encoder** for reranking, and **Google Gemini 2.5-Flash** as the LLM.

---

## 2. Full Data Flow — End to End

### Ingestion Flow

```
PDF files in data/
    │
    ▼
pdf_loader.py
  - Opens each PDF with PyMuPDF (fitz)
  - Extracts text page by page
  - Auto-detects doc_type from folder name (interview_experiences/ → "interview_experience")
  - Extracts company name from filename (Amazon.pdf → "Amazon", ProcDNA_JD.pdf → "ProcDNA")
  - Returns list of Document objects (text + metadata per page)
    │
    ▼
chunker.py
  - Groups documents by doc_type
  - Applies different chunk sizes per type:
      interview_experience: 512 chars, 64 overlap
      job_description:      768 chars, 128 overlap
      aptitude_material:    1024 chars, 128 overlap
  - Uses LangChain's RecursiveCharacterTextSplitter
  - Generates deterministic chunk_id = "{filename}_chunk_{index}_{md5_hash[:8]}"
  - Returns list of chunked Document objects
    │
    ├──────────────────────────────────────────┐
    ▼                                          ▼
embedder.py                         structured_extractor.py
  - Calls vector_store.embed_texts()   - Filters to interview_experience + job_description
  - Computes embeddings in batch           chunks only
  - Calls vector_store.add_chunks()    - Groups chunks by company
  - Upserts into ChromaDB              - Extracts CompanyMetadata via Gemini structured output
    (idempotent via chunk_id)          - Extracts InterviewQuestionsList per chunk concurrently
                                         (asyncio.Semaphore(5) to rate-limit API calls)
                                       - Stores results in JSON flat files (json_data/)
    │
    ▼
pipeline.py
  - Coordinates all 4 steps above
  - MD5-hashes each file for deduplication (skips already-ingested files)
  - Records ingested files in json_data/ingested_files.json
  - Returns summary dict
```

### Query Flow

```
User question (e.g. "What SQL questions did ProcDNA ask?")
    │
    ▼
api/routes.py  POST /api/query
    │
    ▼
rag/query_router.py  route_query()
  - Auto-detects company from query by matching against known companies in store
  - Detects intent via keyword matching:
      "all questions", "how many", "list all" → "aggregation"
      "compare", "vs", "versus"               → "comparison"
      "roadmap", "study plan"                 → "roadmap"
      everything else                         → "factual_lookup"
    │
    ├── aggregation → handle_aggregation()
    │     - Queries structured store for known questions first
    │     - Still runs hybrid retrieval and appends structured data as first chunk
    │     - Generates answer
    │
    ├── comparison → handle_comparison()
    │     - Retrieves top-10 chunks per company separately
    │     - Merges all chunks, re-ranks combined set
    │     - Generates answer
    │
    └── factual_lookup / roadmap → handle_factual_lookup()
          │
          ▼
        rag/retriever.py  hybrid_retrieve()
          - Builds ChromaDB metadata filter (where clause) for company/doc_type
          - Dense retrieval: queries ChromaDB with embedded query vector → top 20
          - BM25 retrieval:
              * Fetches ALL chunks matching the filter from ChromaDB
              * Builds BM25Okapi index on those chunks
              * Scores and sorts → top 20
          - RRF fusion: merges both lists using 1/(k+rank) formula
          → returns top 20 fused results
          │
          ▼
        rag/reranker.py  rerank()
          - Creates (query, chunk_text) pairs for every chunk
          - Runs cross-encoder/ms-marco-MiniLM-L-6-v2 on all pairs
          - Sorts by cross-encoder score
          → returns top 5
          │
          ▼
        rag/generator.py  generate_answer()
          - Formats top 5 chunks into a context string with source headers
          - Sends [SystemMessage, HumanMessage] to Gemini 2.5-Flash
          - System prompt instructs: cite every claim, never hallucinate,
            treat context as untrusted (prompt injection guard)
          → returns {answer, sources, chunks_used}
```

### Resume Analysis Flow

```
User uploads resume PDF + specifies target company
    │
    ▼
api/routes.py  POST /api/resume/analyze
    │
    ▼
resume/analyzer.py  analyze_resume()
  1. Extract text from PDF bytes in-memory (fitz, never saved to disk)
  2. extract_skills(resume_text) — Gemini extracts skills, normalizes names
  3. get_jd_skills(company):
       - Check structured store for company info (fast path)
       - If not found, run hybrid_retrieve() on JD docs and extract skills from results
  4. Set intersection/difference math:
       matched = resume_skills ∩ jd_skills
       missing = jd_skills − resume_skills
       extra   = resume_skills − jd_skills
       match_score = |matched| / |jd_skills| × 100
  5. LLM generates ranked recommendations for top missing skills
  → returns full gap analysis dict
```

---


## 3. Component-by-Component Breakdown

### 3.1 `config.py` — Settings

Uses `pydantic-settings` with a `Settings` class. All config is loaded from `.env` via `BaseSettings`. The interesting part is `get_chunk_config(doc_type)` — a single method that returns the right chunk size and overlap depending on whether the doc is an interview experience, job description, or aptitude material. This is the right pattern; chunking strategy is correctly treated as a config concern, not hardcoded in the chunker.

A singleton `settings` instance is created at module load time and imported everywhere.

**What's good:** Environment-driven, typed, defaults everywhere, clean method for chunk config.
**What's missing:** No validation that `google_api_key` is actually set before making LLM calls — it just silently uses an empty string.

---

### 3.2 `main.py` — FastAPI Entry Point

Sets up the FastAPI app with CORS, registers the single `router` from `api/routes.py`, and uses `lifespan` context manager to pre-initialize the vector store on startup (which loads the embedding model). Logging is via `loguru` — stderr in development, rotating file logs in non-Vercel environments.

Vercel detection (`os.environ.get("VERCEL")`) sets `HOME` and `HF_HOME` to `/tmp` because Vercel's serverless functions have a read-only filesystem except `/tmp`.

**What's good:** Clean lifespan pattern, proper CORS config, Vercel compatibility.
**What's missing:** There is no `Dockerfile.backend` in the repo, but `docker-compose.yml` references it. You can't actually docker-compose up without it.

---

### 3.3 `ingestion/pdf_loader.py`

Two public functions: `load_pdf(file_path)` and `load_pdfs_from_directory(directory)`. Uses `fitz` (PyMuPDF) to open PDFs and extract text page by page. Each page becomes one `Document` dataclass instance.

The `detect_doc_type()` function maps parent folder names to internal doc type strings. `extract_company_name()` strips common prefixes/suffixes (`_JD`, `Interview_Experience_`, etc.) from the filename stem.

**Subtle issue in `extract_company_name`:** The last line has a ternary condition:
```python
return stem.strip("_").replace("_", " ") if "_" in stem and len(stem.split("_")) > 2 else stem.strip("_")
```
This means a filename like `My_Company.pdf` (one underscore, two parts) does NOT get underscores replaced with spaces — it returns `My_Company` instead of `My Company`. Only filenames with more than 2 underscore-separated parts get spaces. This is inconsistent and will cause company name mismatches downstream when filtering.

---

### 3.4 `ingestion/chunker.py`

Groups documents by `doc_type`, creates a `RecursiveCharacterTextSplitter` per group, then further groups by `source_file` and sorts by page number before splitting. This ensures chunk ordering within a file is stable.

Chunk IDs are deterministic: `{safe_filename}_chunk_{index}_{md5_of_text[:8]}`. Because ChromaDB uses `upsert`, re-ingesting the same file with identical content produces the same IDs and simply overwrites — no duplicates.

**What's good:** Doc-type-aware chunking sizes, deterministic IDs for idempotency.
**Issue:** The `chunk_index` counter resets to 0 for every `source_file` within a `doc_type` group. If you have two files of the same doc_type with similar content, it's possible (though unlikely due to the content hash in the ID) to get an ID collision.

---

### 3.5 `ingestion/embedder.py`

Thin wrapper. Calls `vector_store.embed_texts(texts)` in batch and then `vector_store.add_chunks(...)`. ChromaDB batch limit of 500 is handled in `vector_store.add_chunks`, not here.

**What's good:** Correctly delegates everything to the vector store.
**Issue:** If `embed_texts` fails partway through a large batch (network/OOM), there's no partial recovery — the whole ingestion step fails and needs to be re-run.

---

### 3.6 `ingestion/structured_extractor.py`

This is the most complex ingestion file. It uses Gemini's `with_structured_output()` to extract two Pydantic models:

- `CompanyMetadata` — company name, salary, role, skills, rounds, eligibility
- `InterviewQuestionsList` — list of `InterviewQuestion` objects with round, difficulty, topic

Questions are extracted **concurrently** using `asyncio.Semaphore(5)` to cap parallel Gemini API calls. Each chunk gets its own async task. The sync entrypoint `extract_and_store()` detects whether an event loop is already running and either uses `asyncio.run()` (CLI) or spawns a new thread with its own event loop (FastAPI).

Deduplication: before inserting a question, it checks `find_one("interview_questions", {"question": q["question"], "company": q["company"]})`. This is an exact string match — paraphrased duplicates will still be inserted.

**What's good:** Concurrent extraction is smart, Pydantic validation prevents malformed data, semaphore prevents API rate-limit hammering.
**Issues:**
- Only the first 3 chunks of a company are used for `CompanyMetadata` extraction — this might miss salary or role info that only appears later in the document.
- The deduplication check does a full collection scan on every question (O(n) per question). With 100+ questions this gets slow.
- If Gemini returns an empty `questions` list, it silently skips — no warning that extraction yielded nothing for that chunk.

---

### 3.7 `ingestion/pipeline.py`

The orchestrator. It:
1. Finds all PDFs recursively under `data/`
2. Filters out already-ingested files by MD5 hash
3. Loads → chunks → embeds → extracts (steps 1–4)
4. Marks each file as ingested in `json_data/ingested_files.json`

The `--force` flag skips the hash check and re-ingests everything. `--skip-extraction` skips the LLM structured extraction step (useful if you have no API key or want a faster run).

**Issue:** The file hash is computed twice per file — once in `is_already_ingested()` and again in `mark_as_ingested()`. This is a minor inefficiency that's easy to fix by computing the hash once and passing it along.

---

### 3.8 `db/vector_store.py`

Wraps ChromaDB. On `initialize()`, it tries `PersistentClient` (disk-backed) and falls back to `EphemeralClient` (in-memory). Then loads `sentence-transformers/all-MiniLM-L6-v2`; if that's unavailable, falls back to ChromaDB's built-in `DefaultEmbeddingFunction` (ONNX-based).

Key methods:
- `embed_text(text)` / `embed_texts(texts)` — compute vectors
- `add_chunks(...)` — upserts in batches of 500
- `similarity_search(query, top_k, where)` — dense search with optional metadata filter
- `get_all_chunks(where)` — fetches all matching chunks for BM25 index building
- `get_stats()` — returns `{total_chunks: N}`

**Critical issue:** `get_all_chunks()` with no limit fetches **every single chunk** from the collection matching the filter. If you have 10,000 chunks for a company, it loads all 10,000 into memory to build a BM25 index on every single query. This will cause severe memory and latency problems at scale.

**Issue:** The `embedding_model` property calls `self.initialize()` if the model is None, which would re-initialize the entire client. This could cause subtle state bugs.

---

### 3.9 `db/mongo_store.py`

Despite the filename, this file contains the `JSONStore` class and `get_structured_store()` factory. MongoDB is declared as an option in config (`use_mongodb: bool`) but the factory function just logs a warning and returns a `JSONStore` anyway — **MongoDB is never actually used**. The file is misleadingly named.

`JSONStore` stores each collection as a JSON file in `json_data/`. The in-memory `_cache` dict means reads are fast after the first load, but all writes flush the entire collection to disk. For small datasets this is fine; for 500+ questions it will be noticeably slow.

`find()` does a full linear scan with Python `dict.get()` comparisons — no indexing.

**Issue:** Thread safety. Multiple concurrent requests (FastAPI handles them concurrently) can both read `_cache`, modify it, and write to disk, potentially causing a race condition where one write overwrites another. This is a real bug under concurrent load.

---

### 3.10 `rag/retriever.py`

Two public functions: `hybrid_retrieve()` and `dense_only_retrieve()` (for eval baseline).

`hybrid_retrieve()` builds a ChromaDB `where` filter from `company` and `doc_type` params, runs dense and BM25 retrieval, then fuses with `reciprocal_rank_fusion()`.

RRF implementation is correct: `score = weight / (k + rank + 1)`. The `k=60` constant is from the original RRF paper. Results are deduplicated by chunk ID — whichever list sees the chunk first wins for metadata (this is fine since the metadata is identical either way).

**Issue:** BM25 index is **rebuilt from scratch on every single query**. There's no caching of the BM25 index. If the same company filter is used repeatedly, you're re-fetching and re-indexing identical data every time.

**Issue:** If `company` contains a space (e.g. "My Company") and ChromaDB metadata was stored without that space, the filter silently returns nothing and the retrieval returns empty results — no error, just a wrong answer.

---

### 3.11 `rag/reranker.py`

Lazy singleton pattern for `CrossEncoder`. If `sentence-transformers` is not installed, it gracefully degrades: assigns `rerank_score=1.0` to all chunks and returns the top-k. This is the right graceful degradation behavior.

If the number of chunks is already ≤ `top_k`, it skips re-ranking entirely (also correct — no point running the model on 3 chunks when you want 5).

**What's good:** Clean lazy loading, graceful fallback, clear debug logging of score range.
**No real bugs here.**

---

### 3.12 `rag/query_router.py`

Keyword-based intent detection. The `INTENT_KEYWORDS` dict maps intents to trigger phrases. This is fast but brittle — a query like *"I don't want all questions, just the hard ones"* would match "all questions" and trigger aggregation mode incorrectly.

`extract_company_from_query()` looks up known companies from the structured store and checks if any company name appears as a substring in the query. Case-insensitive.

**Issue:** `handle_comparison()` only looks up companies from the **structured store** (`companies` collection). If a company was ingested but structured extraction was skipped (no API key), it won't appear in the store and comparison queries for it will silently retrieve nothing.

**Issue:** The `roadmap` intent is detected but routes to `handle_factual_lookup()` — there's no dedicated roadmap handler. The intent is detected and then ignored.

**Issue:** `extract_company_from_query()` builds the company list partly from `ingested_files` collection by stripping PDF filename patterns. This filename-parsing logic is duplicated from `pdf_loader.py`'s `extract_company_name()` — two separate places doing the same thing, and they may not produce identical results.

---

### 3.13 `rag/generator.py`

Builds a prompt with a strict system message (cite everything, don't use external knowledge, treat context as untrusted) and a user message with the formatted context chunks.

Each chunk in the context is labeled with `[Chunk N | Source: file, Page P | Company: C | Type: T]` headers so the LLM can produce citations.

The `stream=False` parameter is accepted but streaming is never actually implemented — the code always calls `llm.invoke()` regardless.

**Issue:** `stream` parameter is a dead feature — it's accepted in the function signature but ignored. The frontend has no streaming support either, so every query waits for the full response before displaying anything. For long answers this creates a blank-screen wait.

**Issue:** The LLM is re-instantiated on every call (`_get_llm()` creates a new `ChatGoogleGenerativeAI` object each time). This is unnecessary object creation overhead, though likely minor.

---

### 3.14 `resume/analyzer.py`

Extracts text from uploaded PDF bytes in-memory, calls Gemini twice (once for resume skills, once for gap analysis), and does set math for matched/missing/extra skills.

The LLM is asked to return JSON in the prompts via a manually formatted prompt string, and the response is parsed with `json.loads()` after stripping markdown code fences. This is fragile — any deviation in LLM output format causes a `json.loads` exception and falls back to basic recommendations.

**Issue:** Skills are compared after `.lower()` normalization, but the LLM might extract "ReactJS" from a resume and "React" from a JD. These are the same skill but won't match as equal strings. The skill normalization instructions in the prompt are best-effort — the LLM doesn't always follow them perfectly.

**Issue:** The `EXTRACT_SKILLS_PROMPT` truncates text to 4000 characters. A detailed 3-page resume that has important skills listed after the first 4000 characters will have those skills silently dropped.

**Issue:** `get_jd_skills()` falls back to RAG retrieval if the company isn't in the structured store, but the RAG query is `"Required skills and qualifications for {company}"` with `doc_type="job_description"`. If no JD was ingested for that company, it returns empty skills and the analyzer shows an error — this is correct, but the error message says "ingest JD documents first" even if you did ingest them (just without structured extraction). The error message is misleading.

---

### 3.15 `eval/run_eval.py`

Runs three retrieval modes (dense only, hybrid, hybrid + rerank) against a labeled eval set of 30 Q&A pairs (`eval_set.json`). Computes Precision@K, Recall@K, and MRR per question, then aggregates. Optionally scores answer faithfulness with an LLM-as-judge prompt.

The eval set uses `expected_source_chunks` — a list of expected source filenames. A retrieved chunk is considered "relevant" if its `source_file` contains any string from `expected_source_chunks`. This is a substring match, which is reasonable.

**Issue:** `run_single_eval()` returns a tuple `(metrics, chunks)` but the function signature docstring only mentions `dict`. The caller in `run_full_eval()` correctly unpacks it, but it's undocumented.

**Issue:** Running evaluation triggers actual Gemini API calls when `include_faithfulness=True`. With 30 questions × 3 modes, that's up to 90 generation calls + 90 faithfulness judge calls = 180 API calls per eval run. There's no cost warning anywhere.

**Issue:** `eval_results.json` is committed to the repo (it's in the `backend/eval/` folder), but the `.gitignore` doesn't exclude it. Eval results from your local machine (which contain internal file paths) get pushed to version control.

---

### 3.16 `api/routes.py` & `schemas.py`

10 endpoints total. All follow a consistent pattern: validate with Pydantic schemas, call the appropriate service function, catch exceptions and raise `HTTPException(500)`.

**Issue in `list_companies()`:** After fetching companies from the structured store, it does a second pass over `ingested_files` to add companies that exist as files but not in the store. The company name extraction here (`f.get("file_name", "").replace(".pdf", "").replace("_JD", "").replace("_", " ")`) is much simpler than the logic in `pdf_loader.extract_company_name()`. These two will produce different names for the same file. For example, `Walmart_JD.pdf` becomes `Walmart JD` here but `Walmart` in the PDF loader. This causes duplicate company entries in the UI.

**Issue in `upload_and_ingest()`:** After saving uploaded files, it runs `run_pipeline()` on the entire `settings.data_dir` — not just the newly uploaded files. This means every upload re-processes the whole data directory (though the hash check will skip already-ingested files, the pipeline still scans every file).

**Issue:** `ResumeAnalyzeResponse` schema has an `error` field that can be set alongside valid data (e.g., `error=None` with a full analysis). The route raises `HTTPException` only `if "error" in result and not result.get("match_score")`. If `match_score` is 0 (a real valid score), a legitimate error would be swallowed. `match_score=0` is a valid result (no skills matched), not an error state.

---

### 3.17 Frontend

React 19 with Vite. Six pages: Dashboard, QueryPage, CompaniesPage, CompanyDetailPage, ResumePage, EvalPage, AdminPage. Single `APIService` class in `services/api.js`.

All API calls go to `/api/...` (relative URLs), which Vite proxies to `http://localhost:8000` in dev and Vercel routes to the backend service in production.

**Issue in `Dashboard.jsx`:** Uses an undefined component `<MessageSquareIcon />` referenced inside the JSX... wait, it IS defined at the bottom of the file as a local function. But it's declared after the `export default function Dashboard()` that uses it — this works due to function hoisting but is poor practice and will confuse linters.

**Issue in `api.js`:** `ingest()` appends `skip_extraction` and `force` as raw boolean values to FormData: `formData.append('skip_extraction', skipExtraction)`. FormData converts everything to strings, so `false` becomes the string `"false"`. FastAPI's `Form(default=False)` with a bool type will receive the string `"false"` — which Python's bool coercion does NOT convert to `False`. The string `"false"` is truthy. **This means the Admin panel's "skip extraction" toggle is broken — it always reads as True when any value is sent.**

**Issue:** No error boundary components. Any unhandled exception in any page crashes the entire React tree to a blank screen.

**Issue:** The `package.json` pins `react` at `^19.2.7` and `react-router-dom` at `^7.18.1`. React 19 is still relatively new and has known compatibility issues with some ecosystem libraries. `lucide-react` at `^1.23.0` is very recent; `recharts` at `^3.9.1` is also very new. Using `^` (caret) ranges means `npm install` on a fresh machine could pull different minor versions. For a stable project, exact versions (`=`) or a lockfile-only install should be enforced.

---


## 4. Bugs and Real Issues Found

These are actual bugs — things that are either broken, will break under certain conditions, or produce silently wrong results.

---

### 🔴 Bug 1 — FormData Boolean Coercion (Admin Panel Broken)

**File:** `frontend/src/services/api.js` → `ingest()` function

**Problem:**
```js
formData.append('skip_extraction', skipExtraction);  // false → "false" (string)
formData.append('force', force);                     // false → "false" (string)
```
FastAPI receives the string `"false"` for a `bool` Form field. Python evaluates `bool("false")` as `True` because any non-empty string is truthy. So toggling "Skip Extraction" OFF in the Admin UI actually passes `True` to the backend — the toggle is inverted.

**Fix:**
```js
formData.append('skip_extraction', skipExtraction ? 'true' : 'false');
// OR better: don't use Form booleans, use JSON body for this endpoint
```

---

### 🔴 Bug 2 — `mongo_store.py` Thread Safety Race Condition

**File:** `backend/db/mongo_store.py` → `JSONStore`

**Problem:** FastAPI runs handlers concurrently. Two simultaneous requests (e.g., a query and an ingestion) can both call `_load()` → modify `_cache` → both call `_save()`. The second save overwrites the first, silently dropping inserted data.

**Fix:** Add a `threading.Lock()` around `_save()` and any cache mutations:
```python
import threading

class JSONStore:
    def __init__(self, ...):
        self._lock = threading.Lock()

    def insert(self, collection, document):
        with self._lock:
            data = self._load(collection)
            ...
            self._save(collection)
```

---

### 🔴 Bug 3 — Company Name Mismatch Between PDF Loader and Routes

**File:** `backend/api/routes.py` → `list_companies()` and `backend/ingestion/pdf_loader.py` → `extract_company_name()`

**Problem:** Two different parsing functions produce different names from the same filename. In `pdf_loader.py`, `Walmart_JD.pdf` → `Walmart`. In `routes.py`, the same file → `Walmart JD` (because the route does `.replace("_JD", "").replace("_", " ")` without the leading `_`). The structured store has `Walmart` but the companies list endpoint can add a second entry `Walmart JD`. The UI then shows two "Walmart" companies and filtering breaks.

**Fix:** Extract company name in a single shared utility function used everywhere. Remove the inline parsing in `routes.py`.

---

### 🟡 Bug 4 — `stream` Parameter in Generator is Dead Code

**File:** `backend/rag/generator.py` → `generate_answer()`

**Problem:** The function accepts `stream: bool = False` but always calls `llm.invoke()`. Streaming is never implemented. The frontend blocks until the full response is ready.

**Fix:** Either remove the parameter or implement actual streaming with `llm.stream()` and FastAPI's `StreamingResponse`. Streaming would significantly improve perceived performance for long answers.

---

### 🟡 Bug 5 — BM25 Index Rebuilt on Every Query

**File:** `backend/rag/retriever.py` → `hybrid_retrieve()`

**Problem:** Every query calls `vector_store.get_all_chunks(where=where)` to fetch the full filtered corpus, then builds a new `BM25Okapi` from scratch. With even 500 chunks per company, this is re-tokenizing and re-indexing the same data on every request.

**Fix:** Cache BM25 indexes keyed by filter signature:
```python
_bm25_cache: dict[str, tuple[BM25Okapi, list[dict]]] = {}

def _get_bm25_index(where_key: str, where: dict):
    if where_key not in _bm25_cache:
        chunks = vector_store.get_all_chunks(where=where)
        corpus = [_tokenize(c["text"]) for c in chunks]
        _bm25_cache[where_key] = (BM25Okapi(corpus), chunks)
    return _bm25_cache[where_key]
```
Invalidate the cache when new documents are ingested.

---

### 🟡 Bug 6 — MD5 Hash Computed Twice Per File

**File:** `backend/ingestion/pipeline.py` → `is_already_ingested()` and `mark_as_ingested()`

**Problem:**
```python
# in is_already_ingested():
file_hash = compute_file_hash(file_path)   # First read + hash
...
# in mark_as_ingested():
"file_hash": compute_file_hash(file_path),  # Second read + hash of same file
```
The file is read and hashed twice — once to check, once to record.

**Fix:** Compute hash once in `run_pipeline()` and pass it to both functions.

---

### 🟡 Bug 7 — Resume Skill Comparison is Case-Sensitive After Lowercasing, But Not Normalized

**File:** `backend/resume/analyzer.py` → `analyze_resume()`

**Problem:** Skills are lowercased before comparison, but `"reactjs"` and `"react"` are treated as different skills. The LLM extraction prompt asks for normalization but doesn't reliably produce it. Real resumes with "ReactJS", "React.js", "React JS" may all fail to match "React" from the JD.

**Fix:** Implement a fuzzy skill matching step using something like `rapidfuzz` (already indirectly available) or a skills synonym dictionary. At minimum, normalize common variants:
```python
SKILL_ALIASES = {"reactjs": "react", "react.js": "react", "nodejs": "node.js", ...}
def normalize_skill(s): return SKILL_ALIASES.get(s.lower(), s.lower())
```

---

### 🟡 Bug 8 — `roadmap` Intent is Detected but Never Handled Differently

**File:** `backend/rag/query_router.py` → `route_query()`

**Problem:**
```python
elif intent == "roadmap":
    return handle_factual_lookup(query, company, doc_type)  # Same as default!
```
Roadmap queries get the exact same treatment as factual lookups. The intent is detected (wasted computation) and then ignored. A roadmap query like "give me a 1-week study plan for Amazon" would retrieve 5 random chunks and probably give a poor answer.

**Fix:** Either implement a dedicated roadmap handler that retrieves from aptitude material and interview experience documents together, or remove the `roadmap` intent entirely to avoid confusion.

---

### 🟡 Bug 9 — `upload_and_ingest()` Rescans the Entire Data Directory

**File:** `backend/api/routes.py` → `upload_and_ingest()`

**Problem:** After saving an uploaded file, it calls `run_pipeline(data_dir=settings.data_dir)` which rescans the entire `data/` directory. The hash check prevents re-ingesting old files, but it still opens and hashes every PDF to check. With 50+ files this is noticeable.

**Fix:** Pass only the newly saved file paths to the pipeline:
```python
result = run_pipeline(data_dir=settings.data_dir, specific_files=saved_files)
```
Then add a `specific_files` param to `run_pipeline()`.

---

### 🟡 Bug 10 — Missing `Dockerfile.backend` (Docker Compose Won't Work)

**File:** `docker-compose.yml`

**Problem:** The compose file references `Dockerfile.backend` in the project root, but this file does not exist in the repository. Running `docker-compose up` will immediately fail with a build error.

**Fix:** Add `Dockerfile.backend` (and a `frontend/Dockerfile`) to the repo.

---

### 🟡 Bug 11 — `sentence-transformers` Not in `requirements.txt`

**File:** `backend/requirements.txt`

**Problem:** The comment says `# (removed sentence-transformers to prevent PyTorch Vercel build failures)`. So on a fresh install, `sentence-transformers` is not installed. The code falls back to ChromaDB's `DefaultEmbeddingFunction`. BUT — the cross-encoder reranker (`reranker.py`) also imports from `sentence_transformers` (`CrossEncoder`). Without the package, reranking is silently disabled for every query. The fallback exists, but you're running a degraded pipeline by default without any obvious warning to the user.

**Fix:** Separate requirements into `requirements.txt` (Vercel/minimal) and `requirements-full.txt` (local dev with full ML stack). Document clearly that local dev needs the full install.

---


## 5. What Could Be Much Better

These are not bugs — the project works — but these are the areas where quality, scale, and professionalism could be significantly improved.

---

### 🚀 Improvement 1 — Implement Real Streaming Responses

Right now every query blocks until Gemini finishes generating the full answer. For a 500-word response, that's 5–8 seconds of blank screen.

FastAPI supports `StreamingResponse` and LangChain supports `llm.stream()`. With these, the frontend can display tokens as they arrive — a much better UX.

```python
# generator.py
from fastapi.responses import StreamingResponse

async def stream_answer(query, chunks):
    context = format_context(chunks)
    llm = _get_llm()
    async for chunk in llm.astream(messages):
        yield chunk.content

# routes.py
return StreamingResponse(stream_answer(query, chunks), media_type="text/event-stream")
```

---

### 🚀 Improvement 2 — Replace JSONStore with SQLite

The current JSON file store has no indexing, no transactions, and a thread-safety bug. SQLite is a zero-dependency, single-file embedded database that gives you:
- Indexed queries (O(log n) instead of O(n))
- Atomic writes (no race conditions)
- SQL for aggregations instead of Python list comprehensions

It requires only the standard library (`import sqlite3`). This would fix Bugs 2, and make the `find()`, `count()`, and `distinct()` calls dramatically faster.

---

### 🚀 Improvement 3 — BM25 Index Caching / Pre-build at Startup

As noted in Bug 5, BM25 is rebuilt from scratch every query. The fix is to pre-build BM25 indexes per company at startup (or after each ingestion) and cache them. This alone could reduce query latency by 50%+ for large collections.

A simple approach: after ingestion completes, trigger a background task that builds and caches a BM25 index for each company.

---

### 🚀 Improvement 4 — Implement MongoDB Support Properly

The `mongo_store.py` file is named MongoDB but contains a JSON store. If you plan to scale beyond a demo, MongoDB (or SQLite) with proper indexing is essential. The `get_structured_store()` factory function already has a hook for it — just implement the `MongoStore` class with the same interface as `JSONStore`.

---

### 🚀 Improvement 5 — Implement Streaming for Frontend

Beyond the backend streaming (Improvement 1), the frontend `api.js` service should use the Fetch Streaming API (`response.body.getReader()`) or Server-Sent Events to display partial answers as they arrive, with a typing cursor effect. This is a polish item but dramatically changes how the product feels.

---

### 🚀 Improvement 6 — Add a Skills Normalization Layer

For the resume analyzer to work reliably, skill normalization is critical. Consider using a package like `skillNer` or maintaining a YAML-based skills synonym map. At minimum:

```python
# skills_normalizer.py
ALIASES = {
    "reactjs": "react", "react.js": "react",
    "nodejs": "node.js", "node": "node.js",
    "postgresql": "postgres", "pg": "postgres",
    "ml": "machine learning",
    ...
}
def normalize(skill: str) -> str:
    return ALIASES.get(skill.strip().lower(), skill.strip().lower())
```

Apply this before set comparison in `analyze_resume()`.

---

### 🚀 Improvement 7 — Add Authentication for Admin Routes

Right now `/api/ingest`, `/api/ingest/upload`, and `/api/eval/run` are completely open — anyone who knows the URL can trigger ingestion or run expensive eval jobs. Add even basic API-key authentication:

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(key: str = Security(api_key_header)):
    if key != settings.admin_api_key:
        raise HTTPException(403, "Invalid API key")
```

---

### 🚀 Improvement 8 — Add React Error Boundaries

A single unhandled JavaScript error in any component (e.g., a malformed API response) crashes the whole app to a blank white screen. Add an `ErrorBoundary` component:

```jsx
class ErrorBoundary extends React.Component {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) return <div className="error-state">Something went wrong: {this.state.error.message}</div>;
    return this.props.children;
  }
}
```

Wrap each page in `<ErrorBoundary>` in `App.jsx`.

---

### 🚀 Improvement 9 — Add Query History / Conversation Memory

The current chat interface has no memory — each query is fully independent. For a "placement prep" use case, students want to ask follow-up questions: *"What about their HR round?"* after asking about technical rounds. This requires maintaining a conversation history and passing it to the LLM.

LangChain has `ConversationBufferMemory` and `ChatMessageHistory` for this. The backend would need to accept an optional `conversation_id` and `history` field in `QueryRequest`.

---

### 🚀 Improvement 10 — Add `Dockerfile.backend` and `frontend/Dockerfile`

The project has a `docker-compose.yml` but no actual Dockerfiles. Add them:

**`Dockerfile.backend`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "backend.main"]
```

**`frontend/Dockerfile`:**
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

---

### 🚀 Improvement 11 — Eval Set is Too Small and File-Path Dependent

The 30-question `eval_set.json` uses `expected_source_chunks` that contain literal local filenames (e.g., `"Walmart.pdf"`). This means the eval set is tied to your specific file names — if you rename a file or run on a different dataset, all eval scores go to zero. The eval set should use content-based identifiers or at least relative names, and should be extended to 100+ questions for statistical significance.

---

### 🚀 Improvement 12 — Add Proper Logging for LLM Costs

Every Gemini API call costs money (tokens in + tokens out). There is currently zero cost tracking. Add token usage logging:

```python
response = llm.invoke(messages)
usage = response.usage_metadata  # LangChain exposes this
logger.info(f"LLM call | input_tokens={usage.input_tokens} | output_tokens={usage.output_tokens}")
```

Accumulate this in a simple counter and expose it on the `/api/stats` endpoint.

---

## 6. What Is Actually Done Well

It's not all problems — this project has a lot of genuinely good engineering:

**Architecture is sound.** The separation between ingestion, retrieval, and generation is clean. Each module has a clear single responsibility. The pipeline orchestrator is a good conductor pattern.

**Hybrid retrieval is correctly implemented.** The RRF formula is correct, weights are configurable, and the decision to filter by metadata *before* vector search (not after) is the right approach — it keeps the BM25 corpus bounded and the dense search focused.

**Idempotent ingestion.** The MD5 hash deduplication means you can re-run the ingestion pipeline safely without duplicating data. The deterministic chunk IDs (ChromaDB upsert) reinforce this for the vector store.

**Graceful degradation everywhere.** If `sentence-transformers` isn't installed → falls back to DefaultEmbeddingFunction. If ChromaDB PersistentClient fails → falls back to EphemeralClient. If Gemini fails → returns an error response instead of crashing. If structured extraction fails per-chunk → logs and continues. The system doesn't crash, it degrades.

**Pydantic structured output for extraction.** Using `llm.with_structured_output(CompanyMetadata)` is the right way to get guaranteed-schema LLM outputs. Without this, JSON parsing of free-text LLM responses is fragile.

**Concurrent extraction with rate limiting.** `asyncio.Semaphore(5)` on the Gemini calls during ingestion is thoughtful — prevents hitting API rate limits while still being faster than sequential processing.

**Privacy guardrail for resumes.** The resume text is explicitly never logged or stored. This is a real, functioning guardrail (not just a comment) because the `analyze_resume()` function has no calls to any store's `insert()`.

**System prompt injection protection.** The generator's system prompt explicitly tells the LLM not to follow instructions found in context chunks. This is the correct mitigation for prompt injection attacks via uploaded documents.

**Cross-encoder reranking.** Using a cross-encoder (full attention) as a second-stage ranker over the bi-encoder (independent encoding) first stage is the production-standard approach. It catches subtleties the bi-encoder misses and is fast enough (top-20 → top-5) on CPU.

**Quantitative evaluation harness.** Having Precision@K, Recall@K, and MRR metrics with a labeled ground-truth set is much better than "it feels like it works." The LLM-as-judge faithfulness scoring for answer quality is also a good inclusion.

**Config-driven, not hardcoded.** Chunk sizes, weights, model names, top-k values — all in `config.py` with env var overrides. You can tune the pipeline without touching code.

---

*README generated after reading every file in the project: `main.py`, `config.py`, `requirements.txt`, `ingestion/pipeline.py`, `ingestion/pdf_loader.py`, `ingestion/chunker.py`, `ingestion/embedder.py`, `ingestion/structured_extractor.py`, `rag/retriever.py`, `rag/reranker.py`, `rag/query_router.py`, `rag/generator.py`, `db/vector_store.py`, `db/mongo_store.py`, `api/routes.py`, `api/schemas.py`, `resume/analyzer.py`, `eval/run_eval.py`, `frontend/src/App.jsx`, `frontend/src/services/api.js`, `frontend/src/pages/Dashboard.jsx`, `frontend/package.json`, `docker-compose.yml`, `vercel.json`, `.gitignore`.*
