# 📝 Project Progress & Work Done (work_done.md)

This document keeps track of architectural decisions, completed stages, and the history of changes made to the **Placement Buddy Puddy (Puddy)** project.

---

## 🚀 Recent Completed Stages & Commits

Here is the log of completed tasks in this session, divided by stage and tracked by their git commits:

### Stage 1: Production 422 Errors & Grounding Configuration
* **Commit**: `43d5191` — *fix: make jd_file optional in fast-prep route to avoid 422, and remove incompatible thinking_config from grounding calls*
  * **Details**: 
    * Updated the backend `/fast-prep/plan` route parameters to use standard `jd_file: Optional[UploadFile] = None` instead of `File(default=None)`. This prevents FastAPI from throwing a validation error (422) when the client omits the optional JD PDF file field from the form boundary payload.
    * Removed the reasoning `thinking_config` parameters from Google Search grounding calls in `company_report.py` and `interview_questions.py`. Reasoning budgets are unsupported on standard flash models like `gemini-2.5-flash` or `gemini-3.1-flash-lite`, which previously caused grounding failures.

### Stage 2: 100% MongoDB Atlas Vector Search Migration
* **Commit**: `f156370` — *feat: migrate vector database from ChromaDB to MongoDB Atlas Vector Search*
  * **Details**: 
    * Consolidated the database tier by migrating from the local, file-based **ChromaDB** database to **MongoDB Atlas Vector Search**. This resolves file-locking and ephemeral disk-wipe bugs on Render containers.
    * Rewrote `vector_store.py` to insert chunks with `UpdateOne` bulk queries, perform semantic similarity lookup using the Atlas `$vectorSearch` aggregation pipeline, and dynamically map query filters.
    * Removed the heavy `chromadb` dependency from root and backend `requirements.txt` files, making builds faster.
* **Commit**: `4aaf8ae` — *fix: resolve Optional NameError and Pydantic validation error for extra env inputs*
  * **Details**:
    * Fixed a `NameError` in `routes.py` by replacing `Optional` type hints with modern Python 3.10 native type unions (`UploadFile | None`).
    * Configured Pydantic Settings class with `extra = "ignore"` to ignore leftover legacy environment parameters (like `CHROMA_PERSIST_DIR`) instead of throwing validation startup crashes. Cleaned up the unused `chroma_path` property.

### Stage 3: Fast Prep Planner Input "OR" Condition
* **Commit**: `892d3a9` — *fix: make fast prep plan work with only company name or only JD*
  * **Details**:
    * Updated the Fast Prep planner prompt and validation logic in `fast_prep.py` to support building a day-by-day study schedule if *either* the company name or a JD PDF is provided.
    * If only a company is entered and no experiences exist in the database, the LLM will utilize generalized knowledge of that company's SDE interviews rather than failing with a "Not enough data" error.

### Stage 4: Responsive Mobile Layout & Navigation Drawer
* **Commit**: `770fff0` — *style: add responsive mobile top header and toggle drawer state for sidebar*
  * **Details**:
    * Resolved mobile layout overlap issues by adding a frosted top header bar (`.mobile-header`) containing a hamburger menu button and a backdrop overlay (`.sidebar-overlay`) to `App.jsx`, `Sidebar.jsx`, and `index.css`.
    * Configured the drawer menu to slide out on screens <= `1024px` and dismiss automatically when selecting sidebar links or tapping the background backdrop.

### Stage 5: Single-Page Application (SPA) Fallback Routing
* **Commit**: `937fc32` — *fix: configure vercel.json to support React Router fallback routing and api proxy redirects*
  * **Details**:
    * Modified `vercel.json` to handle client-side routing fallback rewrites to `/index.html`, resolving 404 errors when users refresh virtual routes or access pages directly (e.g. `/companies`).
    * Added reverse-proxy mapping rules for `/api` requests to route directly to the Render backend server.

### Stage 6: Production Hardening — 7-Step Senior-Engineering Spec (Steps 7 → 1 → 3 → 2 → 4 → 6)
Implemented high-value-first against the actual codebase. **Kafka (Step 5) was dropped, not deferred** — for this app's scale a broker is overkill (Render has no managed Kafka, and it would add a whole external service to operate for no real gain). Its role — protecting the expensive routes and spreading load — is filled far more simply by the **load balancer + rate limiter** in Stage 7 below.

* **Step 7 — Ask Puddy WIP banner + model swap**
  * Swapped all three model fields (`llm_model`, `llm_extraction_model`, `llm_grounding_model`) to `gemini-3.5-flash-lite` (25× the RPD headroom of the old 2.5-flash) in `config.py`, `.env`, `.env.example`.
  * `QueryPage.jsx` shows a "work in progress" banner, disables the input + submit, and short-circuits `handleSubmit` (`WIP = true`). Backend `/api/query` left intact.

* **Step 1 — ATS Analyzer: single-call + SSE streaming**
  * Reconciled the LLM path: `analyze_resume` now calls `chat_invoke` (Groq-primary → Gemini-fallback), single-sourced with the rest of the app.
  * Added `POST /api/resume/analyze/stream` — a `StreamingResponse` (SSE over POST) yielding `stage` progress frames (extracting → format checks → querying → scoring) then a final `result` JSON. Non-streaming `/api/resume/analyze` kept for back-compat.
  * Frontend `analyzeResumeStream()` reads the SSE body via a `ReadableStream` reader (EventSource can't POST multipart); `ResumePage.jsx` shows live stage text instead of a static spinner.

* **Step 3 — Company Scanner refinements**
  * Added a `salary_caveat` schema field stamped server-side at request time ("as of {date} — verify independently").
  * Restored `thinking_config=ThinkingConfig(thinking_budget=512)` on grounded calls to cap latency (matches the documented intent).
  * Tagged fallback returns with `_fallback: True` so degraded results are never cached.

* **Step 2 — Redis Caching Layer** (`backend/cache/redis_cache.py`, new)
  * Grounded dossier + Top-Asked cache: JSON envelope `{_cached_at, _fresh_until, data}`, **TTL 24h ± 15min jitter** to desync expiry.
  * **Stampede protection**: `SETNX` lock so only one worker regenerates on a miss; others poll or serve stale.
  * **Stale-while-revalidate**: an expiring value is served immediately while the lock holder refreshes inline.
  * **Degrades to no-op** when `REDIS_URL` is unset (mirrors the Mongo→JSON fallback) — local dev works with no Redis.
  * `_default_should_cache` refuses to store `error`/`_fallback` results. Refresh-token helpers added for Step 6.
  * Config: `redis_url`, `cache_ttl_hours` + env fallback; added to `render.yaml` + `.env.example`.

* **Step 4 — Quick Prep RAG cleanup**
  * Vector store was already Atlas `$vectorSearch` — added `sentence-transformers` (torch) to root + backend requirements so dense retrieval runs in prod; deleted `chroma_data/` + `test_chroma/`; removed the broken `docker-compose.yml`; fixed all "ChromaDB" docstrings across `retriever.py`, `embedder.py`, `vector_store.py`. (Atlas `vector_index`, dim 384 cosine, created via the Atlas UI — ops step.)

* **Step 6 — JWT Auth** (`backend/auth/`, new)
  * `security.py` — bcrypt hashing (SHA-256 pre-hash to dodge the 72-byte limit) + PyJWT access (30 min) / refresh (7 day) tokens.
  * `routes.py` — `POST /api/auth/register|login|refresh|logout` + `GET /api/auth/me`. App-level duplicate-email check (the store has no unique index). Refresh tokens tracked in Redis by `jti`; **refresh is single-use (rotated)** and **revoked on logout**. Without Redis, refresh degrades to signature+expiry only.
  * `deps.py` — `get_current_user` validates `Authorization: Bearer`. **Existing feature routes stay public by design** — only opt-in routes require login.
  * Config: `jwt_secret`, `jwt_algorithm`, `access_token_expire_minutes`, `refresh_token_expire_days` + env fallback; `JWT_SECRET` added to `render.yaml` + `.env.example`.
  * Frontend: `LoginPage.jsx` (login/register/signed-in states), token storage + auto-Bearer in `api.js`, sidebar "Account" link. Verified end-to-end (register 201 → protected `/me` 200 → refresh rotation → logout revokes).

### Stage 7: Load Balancer + Rate Limiter (replaces Kafka)
Two small, boring pieces of infra that do the job Kafka was meant to — without a broker to run.

* **Load balancer — gunicorn multi-worker** (`render.yaml`, `requirements.txt`)
  * Start command is now `gunicorn backend.main:app -k uvicorn.workers.UvicornWorker -w 2 --timeout 120 --bind 0.0.0.0:$PORT`. gunicorn runs **2 Uvicorn workers** behind the one port Render exposes and spreads incoming requests across them — so one slow grounded call no longer blocks every other request, and a crashed worker is respawned without downtime.
  * **Two layers of balancing**: gunicorn balances across *workers within* the instance; Render's own router balances across *scaled instances*. No nginx needed — Render is already the front door.
  * Worker count kept at **2** on purpose: each worker loads its own copy of the sentence-transformers model (torch, ~0.5–1 GB), so `-w` is memory-bound, not CPU-bound. Raise it only after moving to a larger Render instance. `--timeout 120` stops the default 30s worker timeout from killing slow (15–30s) grounded Gemini calls.

* **Rate limiter — per-client fixed window** (`backend/middleware/rate_limit.py`, new)
  * Starlette `BaseHTTPMiddleware`: each client gets N requests per 60s window; over the limit returns **HTTP 429** with a `Retry-After` header. The window number is baked into the counter key, so it "resets" naturally as a new key appears — no background cleanup.
  * **Two budgets**: expensive routes (LLM / grounded research / auth / ingest) get **12/min**; ordinary reads get **60/min**. Auth endpoints are throttled to blunt credential-stuffing. Health checks + CORS preflight (`OPTIONS`) are never limited.
  * **Client identity** = forwarded IP (`X-Forwarded-For`, since we sit behind Render's proxy) + a short hash of any Bearer token, so two users behind one office IP don't share a bucket.
  * **Backing store mirrors the cache's degrade-to-no-op pattern**: uses Redis `INCR`+`EXPIRE` (`incr_fixed_window`) when available, so the limit is **global across all workers and instances**; falls back to a per-worker in-process counter when Redis is absent (looser, but never breaks the app). Added `rate_limit_*` config fields (`config.py`) + registered **inside** CORS in `main.py` so 429s still carry CORS headers.
  * Verified: burst test — request #6 → 429 at limit 5, `Retry-After` present, health route exempt, new window resets, separate clients independent.

---

## 🚀 Historical Accomplishments

### 1. Split-Cloud Deployment Architecture
* **Frontend (React/Vite)**: Deployed on **Vercel** as a high-performance static build.
  * *Reasoning:* Static builds on Vercel are fast, robust, and free of cold-starts.
  * *File modified:* `vercel.json` (restricted to static-build targets, removed Python builders).
* **Backend (FastAPI)**: Deployed on **Render** as a Python web service.
  * *Reasoning:* Bypasses Vercel's Serverless Function size limit (250MB) and file-locking constraints on database folders (e.g., ChromaDB).
  * *File created:* `render.yaml` (Render Blueprint configuration for one-click deployment).

### 2. Groq Provider Integration (`groq integ`)
* Added **Groq** as the primary provider for non-grounded LLM completions (like Resume ATS parsing, database query intent routing, and structured entity extraction).
* Implemented a fallback chain inside `llm_client.py`:
  1. Primary: **Groq** (`ChatGroq` model via `openai/gpt-oss-20b` or custom key configuration).
  2. Fallback: **Gemini (lite)** when Groq is rate-limited or unconfigured.
  * *Reasoning:* Groq has a separate, generous free tier which helps save Gemini API quotas. Gemini remains the primary provider for grounded research (since it uses Google Search).

### 3. Anti-Quota Exhaustion (429) Fallback System
* Implemented a robust fallback system in `company_report.py` and `interview_questions.py`:
  * On Gemini `429 RESOURCE_EXHAUSTED` (daily limit reached), the system catches the error.
  * It returns **high-quality, pre-generated dossiers/questions** for popular target companies: **Google, Walmart, Amazon, Microsoft, and ProcDNA**.
  * For other companies, it compiles a dynamic template report instead of failing with a raw error.

---

## 🛠️ Current Project State & Config

### 1. Database Connectors
* Consolidates both structured metadata and vector search into a single remote **MongoDB Atlas** cluster.
* Uses the `$vectorSearch` pipeline stage and a custom Atlas Search Index to query document embeddings.

### 2. Server API Link
* Configured Vercel rewrites to proxy `/api` routes directly to the Render backend server URL.

---

## 🚀 Current Deployment Status (Live)

* **Backend Service**:
  * **Status**: **Live & Healthy**
  * **Platform**: Render
  * **Endpoint**: `https://placement-intelligence-assistant-pia-rag.onrender.com`
  * **Database**: MongoDB Atlas Cluster connected.
  * **LLM Engine**: Groq (primary) + Gemini (fallback) fully integrated.

* **Frontend UI**:
  * **Status**: **Live & Fully Connected**
  * **Platform**: Vercel
  * **Domain**: `https://puddy.krupakara.space`
  * **CORS Settings**: Fully configured on Render backend to permit requests from the Vercel app domain.
