# How Puddy (PIA) Actually Works — The Honest, Detailed Walkthrough

This document exists because the app grew in layers and it stopped being obvious
what talks to what. It answers, from the **real code** (not assumptions), every
question you had:

- Where is RAG *actually* used? (Short answer: only in **one** feature — the Ask Puddy chat.)
- What is a "pre-generated fallback report for: Amazon"?
- Where is **Groq** used, where is **Gemini** used, and **why two** LLM providers?
- Why does a new company come back in ~1 second with thin content, when Gemini used
  to take 20–30 seconds with richer content?
- What does each feature/tab do, and which endpoint + code file serves it?
- Where is auth? What are all the endpoints?
- What are the rate limiter and the load balancer?
- What actually changed between the old version and this version?

Every claim below points at a specific file so you can verify it yourself.

---

## 0. The one mental model that fixes all the confusion

**There are TWO completely separate "answer engines" in this app. They share almost
no code. Most of your confusion comes from assuming they're the same thing.**

| | **Path A — the RAG engine** | **Path B — the grounded engine** |
|---|---|---|
| Feature | **Ask Puddy** (the chat) | **About Company**, **Fast Prep → Top Asked** |
| What it reads | *Your ingested PDFs* (interview experiences / JDs stored as vectors in MongoDB Atlas) | *The live web* (Google Search) |
| The technique | Real RAG: embed → vector + keyword search → rerank → cite | Google-Search "grounding" (Gemini calls Google Search itself) |
| LLM used | **Groq first, Gemini as fallback** (`chat_invoke`) | **Gemini only** (Groq can't do Google Search) |
| Status right now | **Live** (`WIP = false` in QueryPage.jsx) | **Live** |
| Entry point | `POST /api/query` → [`route_query`](backend/rag/query_router.py:202) | `POST /api/company/about` → [`generate_company_report`](backend/rag/company_report.py:225) |

So when you type a new company name and get a fast answer — **that is Path B (the
grounded engine), not RAG.** RAG is not involved in that at all. Keep this table in
your head for the rest of the doc.

---

## 1. "Where the hell is RAG even used?"

**RAG is used in exactly one place: the `Ask Puddy` chat, served by `POST /api/query`.**
Nothing else in the app uses the RAG pipeline. It is **live** — see §1.3 for the toggle
that turns it on/off.

### 1.1 The actual RAG pipeline (Path A)

When `POST /api/query` is hit ([`routes.py:46`](backend/api/routes.py:46)), it calls
[`route_query`](backend/rag/query_router.py:202), which runs this chain:

```
your question
   │
   ▼
detect_intent()                 ── keyword match → factual_lookup | aggregation | comparison | roadmap
   │                               (query_router.py:46)
   ▼
hybrid_retrieve()               ── the "R" in RAG (retriever.py)
   ├─ dense search: embed the query with all-MiniLM-L6-v2, run MongoDB Atlas $vectorSearch
   ├─ sparse search: BM25 keyword scoring over the same company/doc-type-filtered chunks
   └─ Reciprocal Rank Fusion (RRF, k=60) merges the two ranked lists → top 20
   │
   ▼
rerank()                        ── cross-encoder ms-marco-MiniLM-L-6-v2 re-scores the 20, keeps top 5
   │                               (reranker.py) — degrades to passthrough if the model isn't installed
   ▼
generate_answer()               ── the "G" in RAG (generator.py)
   ├─ builds a prompt containing ONLY those 5 retrieved chunks + a strict "cite your sources" system prompt
   └─ calls chat_invoke() → Groq first, Gemini fallback
   │
   ▼
answer + source citations (file name + page number for every claim)
```

Files that make up the RAG engine, and nothing else uses them:
- [`backend/rag/query_router.py`](backend/rag/query_router.py) — the orchestrator (the *only* caller of the pipeline)
- [`backend/rag/retriever.py`](backend/rag/retriever.py) — hybrid retrieval (Atlas `$vectorSearch` + BM25 + RRF)
- [`backend/rag/reranker.py`](backend/rag/reranker.py) — cross-encoder rerank (top 20 → top 5)
- [`backend/rag/generator.py`](backend/rag/generator.py) — prompt assembly + citation rules
- [`backend/db/vector_store.py`](backend/db/vector_store.py) — the Atlas vector index it searches

### 1.2 What RAG needs to work — ingested PDFs

RAG can only answer from what you've **ingested**. The ingestion pipeline
([`backend/ingestion/pipeline.py`](backend/ingestion/pipeline.py)) does:

1. `pdf_loader.py` — extract plain text per page with PyMuPDF.
2. `chunker.py` — split each page into overlapping chunks (JD: 768 chars / 128 overlap; interview: 512 / 64).
3. `embedder.py` — turn each chunk into a 384-dim vector (all-MiniLM-L6-v2).
4. Store vectors in **Atlas** (`vector_chunks` collection) + run a structured LLM extraction that pulls Q&A/metadata into the structured store.

If nothing is ingested for a company, RAG has nothing to retrieve. That's a big part
of why the app leans on Path B (web grounding) for most features — see §4.

### 1.3 The Ask Puddy on/off toggle

In [`frontend/src/pages/QueryPage.jsx`](frontend/src/pages/QueryPage.jsx) there's a single
`WIP` flag. It's currently `false`, so the chat is **live** — the textarea, submit button,
and `handleSubmit` all work. Set `WIP = true` to instantly show a "work in progress" banner
and disable the chat end-to-end (all four call sites key off this one flag). **The backend
`/api/query` route is always intact** — the flag only gates the UI. This is the "Stage 3 —
Ask Puddu WIP" switch from your notes; it's now flipped on.

---

## 2. "Where is Groq being used?"

**Groq is used only inside one function: [`chat_invoke`](backend/rag/llm_client.py:72)
in `backend/rag/llm_client.py`.** Anything that calls `chat_invoke` uses Groq first.
Anything that doesn't, never touches Groq.

`chat_invoke` tries providers **in order** ([`llm_client.py:92`](backend/rag/llm_client.py:92)):

1. **Groq** (`openai/gpt-oss-20b`) — primary. Fast, and on a totally separate free-tier
   quota from Google.
2. **Gemini lite** (`gemini-3.5-flash-lite`) — fallback, only if Groq is missing,
   rate-limited, or errors.

### Who calls `chat_invoke` (i.e. who uses Groq)

| Caller | Feature | File |
|---|---|---|
| `generate_answer` | Ask Puddy (RAG answer text) | [`generator.py`](backend/rag/generator.py) |
| `analyze_resume` / `analyze_resume_events` | Resume Analyzer | [`analyzer.py:229`](backend/resume/analyzer.py:229), [`:353`](backend/resume/analyzer.py:353) |
| `generate_fast_prep_plan` | Fast Prep → extracting company-specific questions from your ingested corpus | [`fast_prep.py:600`](backend/rag/fast_prep.py:600) |
| Structured extraction during ingestion | Admin → ingest | [`structured_extractor.py`](backend/ingestion/structured_extractor.py) |

### Who does NOT use Groq (uses Gemini directly)

**The grounded features.** `About Company` and `Fast Prep → Top Asked` call the Google
GenAI SDK directly with the Google Search tool — they never go through `chat_invoke`,
so they never use Groq:

- [`company_report.py:_generate_report_uncached`](backend/rag/company_report.py:248) — `genai.Client(...).models.generate_content(... tools=[GoogleSearch()] ...)`
- [`interview_questions.py:_fetch_interview_questions_uncached`](backend/rag/interview_questions.py:230) — same pattern.

The reason is in §3.

---

## 3. "Why two APIs? (Groq + Gemini)"

Because they do two different jobs, and each covers the other's weakness:

1. **Groq can't search the web.** The grounded features (About Company, Top Asked)
   *require* Google Search grounding, which only Gemini offers. So those stay on Gemini,
   period.

2. **Gemini's free-tier text quota is tiny and gets exhausted.** For plain text work
   (RAG answers, resume analysis, extraction) we put **Groq first** because it's fast and
   has a big, *separate* free quota. That takes load off Google so Gemini's limited quota
   is saved for the thing only Gemini can do (grounding).

3. **Fallback = resilience.** If Groq is down or rate-limited, `chat_invoke`
   automatically falls to Gemini lite. Two independent quotas pooled together = far fewer
   hard failures than relying on one 500-requests/day model.

One more subtlety worth knowing: **Google Search grounding draws from a *separate* tool
quota (~1,500/day)** than plain Gemini text generation (~500/day on lite). That's why the
grounded features can use the cheap `-lite` model and still work — the grounding calls
don't compete with the text-generation quota.

---

## 4. "What is a 'pre-generated fallback report for: Amazon'?"

This is the single most confusing log line, so here's exactly what it means.

The grounded engine (About Company / Top Asked) calls Gemini + Google Search live. On
the free tier, Gemini frequently returns **429 RESOURCE_EXHAUSTED** (daily quota hit).
When that happens, we don't want to show the user a raw error — so there's a **safety
net of hand-written reports** baked into the code.

- [`company_report.py`](backend/rag/company_report.py) has a dict `_FALLBACK_REPORTS`
  with hand-written dossiers for **procdna, walmart, google, amazon, microsoft**.
- [`interview_questions.py`](backend/rag/interview_questions.py) has a matching
  `_FALLBACK_QUESTIONS` dict for the same companies.

So the flow on a quota failure ([`company_report.py:292`](backend/rag/company_report.py:292)):

```
try live Gemini + Google Search
   └─ on 429 / any error:
        ├─ if company is one of the 5 famous ones → return _FALLBACK_REPORTS["amazon"]   ← "pre-generated fallback report for: Amazon"
        └─ otherwise                              → return get_generic_fallback(company)  ← a thin generic template
```

**"Pre-generated fallback report for: Amazon"** = *"the live web call failed, so I served
the pre-written Amazon dossier I keep in the code as a backup."* It's not RAG, not a
cache, not the live web — it's a static hand-authored safety net for 5 well-known
companies.

Crucially, these fallbacks are tagged `_fallback: True` and the cache layer refuses to
store anything with that flag ([`redis_cache.py:262`](backend/cache/redis_cache.py:262)),
so a degraded answer never gets frozen into the 24-hour cache.

### 4.1 This directly explains your "1 second, thin content" observation

You typed a **new** company (e.g. "stonex"), got a fast, sparse answer, and thought Groq
was answering without RAG. Here's what actually happened:

1. It hit Path B (grounded About Company / Top Asked), **not** RAG, **not** Groq.
2. Gemini's grounding quota was already exhausted (429s in the logs after heavy use).
3. "stonex" is **not** one of the 5 companies in `_FALLBACK_REPORTS`, so it fell through
   to `get_generic_fallback()` — a thin generic template that returns almost instantly
   (~1s) with sparse content.

That's the whole story: **quota exhausted → generic fallback template**. When it *does*
reach Gemini live, it takes ~10–24s and comes back rich. Amazon/Google/etc. *look* fine
even when quota is blown because they hit the hand-written full dossiers instead of the
thin generic one. Nothing is broken — it's the free-tier quota degrading gracefully.

---

## 5. Every feature → endpoint → code (the full tour)

The left sidebar ([`Sidebar.jsx`](frontend/src/components/Sidebar.jsx)) has these tabs:

| Tab | Route | Backend endpoint | Engine | Notes |
|---|---|---|---|---|
| **Dashboard** | `/` | `GET /api/stats` | — | Counts (chunks, files, companies). |
| **Ask Puddy** | `/query` | `POST /api/query` | **Path A: RAG** | **Live.** The only RAG feature. |
| **About Company** | `/companies` | `POST /api/company/about` | **Path B: grounded** | India-first dossier: overview/pros/cons/salaries/WLB + real web sources. |
| **Fast Prep** | `/fast-prep` | `POST /api/fast-prep/plan` + `POST /api/fast-prep/questions` | Mixed | See §5.1. |
| **HR Qss** | `/hr-questions` | *(none)* | **Static** | Pure frontend list from [`data/hrQuestions`](frontend/src/data). No API, no LLM. |
| **Resume Analyzer** | `/resume` | `POST /api/resume/analyze` (+ `/stream`) | LLM (no RAG) | ATS scoring, in-memory only. |
| **Eval Dashboard** | `/eval` | `POST /api/eval/run`, `GET /api/eval/results` | RAG eval harness | Precision/Recall/MRR across retrieval modes. |
| **Account** | `/login` | `POST /api/auth/*` | Auth | Login/register/logout. |
| **Admin** | `/admin` | `POST /api/ingest`, `/api/ingest/upload` | Ingestion | Feeds the RAG corpus. |

### 5.1 Fast Prep is actually two different things in one tab

This tab is a common source of confusion because its two sub-features use **different
engines**:

- **Study Plan** (`POST /api/fast-prep/plan` → [`fast_prep.py`](backend/rag/fast_prep.py)):
  Mostly **deterministic Python**, not AI. The core-subjects syllabus (OOPS/DBMS/SQL/OS/
  CN/System Design) and the ~85-problem DSA list are **curated banks hard-coded in the
  file**, filtered by difficulty level, and the day-by-day schedule is built by a plain
  Python scheduler (`_build_schedule`). The **only** LLM part is extracting
  company-specific interview questions from *your ingested corpus* via `chat_invoke`
  (Groq→Gemini). Why banks instead of the LLM? Because the LLM kept returning 2 problems
  and a narrow list — the banks guarantee full coverage and non-dead LeetCode links.

- **Top Asked** (`POST /api/fast-prep/questions` → [`interview_questions.py`](backend/rag/interview_questions.py)):
  Pure **Path B grounded** — Gemini + Google Search returns real DSA + core questions the
  company asks, with real source URLs. Loaded lazily (only when you open the tab) so the
  study plan stays fast. Falls back to `_FALLBACK_QUESTIONS` on quota errors (§4).

### 5.2 Resume Analyzer (LLM, but not RAG)

[`analyzer.py`](backend/resume/analyzer.py): extract both PDFs in memory → run instant
regex formatting checks (`_formatting_checks`) → **one** `chat_invoke` call (Groq→Gemini)
that scores the resume against the JD → normalize. Both PDFs are processed in memory and
never persisted. There's also a streaming version (`POST /api/resume/analyze/stream`,
Server-Sent Events) that emits live "extracting → checking → querying → scoring" progress
frames but is still a single model call.

---

## 6. The complete endpoint list

All under prefix `/api` ([`routes.py`](backend/api/routes.py) + [`auth/routes.py`](backend/auth/routes.py)):

**Features**
- `POST /api/query` — RAG chat (Ask Puddy). *[the only RAG endpoint]*
- `POST /api/company/about` — grounded company dossier.
- `POST /api/fast-prep/plan` — study plan (curated banks + scheduler + corpus questions).
- `POST /api/fast-prep/questions` — grounded "Top Asked" questions.
- `POST /api/resume/analyze` — ATS resume analysis (single JSON response).
- `POST /api/resume/analyze/stream` — same, as SSE progress stream.

**Data / admin**
- `POST /api/ingest` — run ingestion over the server `./data` dir.
- `POST /api/ingest/upload` — upload PDFs then ingest.
- `GET  /api/companies` — list ingested companies.
- `GET  /api/companies/{name}` — one company's structured detail + questions.
- `GET  /api/stats` — vector/structured/file counts.

**Eval**
- `POST /api/eval/run` — run the retrieval eval harness.
- `GET  /api/eval/results` — last eval results.

**Auth** (see §7)
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`,
  `POST /api/auth/logout`, `GET /api/auth/me`.

**Ops**
- `GET /api/health`, `GET /health` — liveness (never rate-limited).

---

## 7. "Where is auth?"

Auth lives in [`backend/auth/`](backend/auth) and is **fully built but deliberately
optional** — the design decision is that **all feature routes stay public**; auth only
protects routes you explicitly opt in with `Depends(get_current_user)`.

- [`security.py`](backend/auth/security.py) — password hashing with **bcrypt** (passwords
  are SHA-256+base64 pre-hashed first so long passwords aren't truncated at bcrypt's
  72-byte limit), and **PyJWT** tokens: access token (30 min) + refresh token (7 days).
- [`routes.py`](backend/auth/routes.py) — `register` / `login` / `refresh` / `logout` /
  `me`. Users live in a `users` collection in the structured store; register does an
  app-level duplicate-email check (the store has no unique index).
- [`deps.py`](backend/auth/deps.py) — `get_current_user` validates the
  `Authorization: Bearer <token>` header. Attach it to any route you want to lock.

**Refresh-token security:** refresh tokens are tracked in **Redis** by their `jti`.
Refresh is **single-use** (the old one is revoked and a new one issued — rotation), and
logout revokes the token server-side. Without Redis, refresh still works on
signature+expiry but can't be server-side revoked (documented degradation).

Frontend: [`api.js`](frontend/src/services/api.js) stores both tokens in `localStorage`
and automatically attaches the Bearer header to every request when present;
[`LoginPage.jsx`](frontend/src/pages/LoginPage.jsx) is the UI.

---

## 8. The rate limiter

[`backend/middleware/rate_limit.py`](backend/middleware/rate_limit.py) — a Starlette
middleware implementing a **per-client fixed-window** limiter:

- **Two budgets:** expensive routes (LLM / grounded / ingest / auth) get **12 requests/min**;
  ordinary reads get **60/min**. The "expensive" list is matched by URL prefix
  (`_EXPENSIVE_PREFIXES`). Auth is throttled to blunt credential-stuffing.
- **Client identity** = forwarded IP (`X-Forwarded-For`, since we're behind Render's
  proxy) + a short hash of any Bearer token — so two people behind one office IP don't
  share a bucket.
- **Backing store** mirrors the cache's degrade-to-no-op pattern: it uses Redis
  `INCR`+`EXPIRE` when available (so the limit is **global across all workers and
  instances**), and falls back to a per-worker in-process counter when Redis is absent.
- Over the limit → **HTTP 429** with a `Retry-After` header. Health checks and CORS
  preflight (`OPTIONS`) are never limited.
- It's registered **before** CORS in [`main.py:87`](backend/main.py:87) on purpose, so
  CORS stays the outermost layer and a 429 still carries CORS headers (otherwise the
  browser couldn't even read the error).

---

## 9. The load balancer

There's no separate nginx — "load balancing" here is two layers, both boring on purpose:

1. **Within one instance:** the app runs under **gunicorn with 2 Uvicorn workers**
   (`render.yaml`: `gunicorn backend.main:app -k uvicorn.workers.UvicornWorker -w 2
   --timeout 120`). gunicorn spreads incoming requests across the 2 workers, so one slow
   ~20s grounded Gemini call doesn't block every other request, and a crashed worker is
   respawned automatically.
2. **Across instances:** Render's own router balances traffic across however many
   instances you scale to.

Why only 2 workers? Each worker loads its **own** copy of the sentence-transformers model
(torch, ~0.5–1 GB RAM). So worker count is **memory-bound**, not CPU-bound — raise `-w`
only after moving to a bigger Render instance. `--timeout 120` stops gunicorn's default
30s worker timeout from killing legitimately slow grounded calls.

This (plus the rate limiter) is what replaced the originally-planned Kafka event
backbone — a broker was overkill for this app's scale and Render has no managed Kafka.

---

## 10. Caching + stampede protection

[`backend/cache/redis_cache.py`](backend/cache/redis_cache.py) caches the two expensive
grounded results (company dossiers, Top Asked) so a repeated company is instant instead
of a fresh 10–24s Gemini call. This is "Stage 2" from your notes. It has three
production behaviours worth knowing:

- **TTL 24h ± 15 min jitter** — the random offset stops many keys from expiring at the
  exact same second and hammering Gemini all at once (thundering herd).
- **Stampede protection** — on a cache miss, a Redis `SETNX` lock means only **one**
  worker regenerates; other concurrent callers wait for it to populate instead of all
  calling Gemini simultaneously.
- **Stale-while-revalidate** — when a value has just expired, the old value is served
  *immediately* while one worker refreshes it in the background. Users never wait on a
  refresh.
- **Degrades to a no-op** when `REDIS_URL` is unset — local dev works with zero Redis.
- Never caches `error`/`_fallback` results, so degraded answers don't get stuck (§4).

The same Redis instance also backs the rate limiter counters (§8) and the JWT
refresh-token store (§7).

---

## 11. Where data lives

| Data | Store | Detail |
|---|---|---|
| Chunk embeddings (for RAG) | **MongoDB Atlas** `vector_chunks` | Queried via `$vectorSearch` (index `vector_index`, field `embedding`, 384-dim, cosine). |
| Structured metadata (companies, extracted questions, users, ingested-file log) | **MongoDB** (or a JSON-file fallback) | [`mongo_store.py`](backend/db/mongo_store.py). |
| Grounded dossiers, Top Asked, rate-limit counters, refresh tokens | **Redis** (optional) | [`redis_cache.py`](backend/cache/redis_cache.py); no-op if unset. |
| Resume + JD PDFs | **nowhere** | Processed in memory, never persisted. |

This is "Stage 1" from your notes: the vector store was **ChromaDB in early dev** and is
now **MongoDB Atlas Vector Search in production** — one cloud DB for both vectors and
structured data, no local file-locking / disk-wipe problems on Render.

---

## 12. What changed: old version → this version

Your "Stage by Stage" notes, mapped onto what's in the code today:

### Stage 1 — Vector storage: Chroma (dev) → MongoDB Atlas Vector Search (prod)
Retrieval moved off local ChromaDB onto Atlas `$vectorSearch`. Fixes ephemeral-disk and
file-lock issues on Render; consolidates vectors + structured data into one cluster.
(`vector_store.py`, `render.yaml`.)

### Stage 2 — Cache stampede protection for Redis
Added the Redis cache with **TTL jitter**, a **regeneration lock** (SETNX), and
**stale-while-revalidate**, so expensive grounded calls are cached safely and never cause
a thundering herd. (`redis_cache.py`.)

### Stage 3 — Ask Puddu WIP → live
The RAG chat was gated behind a "work in progress" banner while the ingested corpus was
grown; that gate is now flipped off (`WIP = false` in `QueryPage.jsx`), so the chat is
live. The `WIP` flag remains as a one-line kill-switch to re-gate it anytime.

### Plus the broader hardening in this version (was not in the old one)
- **Groq added as primary LLM** with Gemini fallback (`chat_invoke`) — saves Gemini quota.
- **Model swap** to `gemini-3.5-flash-lite` everywhere (~25× the daily headroom of the
  old 2.5-flash).
- **JWT auth** (register/login/refresh-rotation/logout), feature routes stay public.
- **Rate limiter** (per-client fixed window, 12/min expensive, 60/min normal).
- **Load balancer** (gunicorn 2 workers + Render's router) — replaced the planned Kafka.
- **Resume analyzer** reconciled to a single `chat_invoke` path + SSE streaming.
- **Grounded scanner** hardened: `thinking_budget=512` to cap latency, salary-staleness
  caveat, `_fallback` results never cached.
- Dead code / stale ChromaDB references cleaned up; unused imports removed.

---

## 13. Deployment topology (one glance)

```
Browser
  │  https://puddy.krupakara.space
  ▼
Vercel (static React build)
  │  /api/*  ──proxy──►  Render
  ▼
Render web service
  ├─ gunicorn (2 uvicorn workers)        ← load balancing within the instance
  │    ├─ RateLimitMiddleware            ← 429s abusers
  │    ├─ CORS
  │    └─ FastAPI routes
  │         ├─ Path A (RAG)   → Atlas $vectorSearch + BM25 + rerank + Groq/Gemini
  │         └─ Path B (grounded) → Gemini + Google Search
  ├─ MongoDB Atlas   (vectors + structured data)
  └─ Redis           (cache + rate-limit counters + refresh tokens)   [optional]
```

---

## 14. Quick "who does what" cheat-sheet

- **RAG?** Only `Ask Puddy` (`/api/query`) — now live (`WIP = false`).
- **Groq?** Only via `chat_invoke` → RAG answers, resume analysis, corpus extraction, ingestion.
- **Gemini (grounded)?** About Company + Top Asked (needs Google Search; Groq can't).
- **Gemini (fallback)?** The second half of every `chat_invoke` if Groq fails.
- **"Pre-generated fallback report"?** A hand-written backup dossier for 5 famous
  companies, served when the live Gemini call fails on quota.
- **Fast 1s thin answer for a new company?** Gemini quota exhausted → generic fallback
  template (not RAG, not Groq).
- **Auth?** `backend/auth/`, JWT, optional, feature routes public.
- **Rate limiter?** `backend/middleware/rate_limit.py`, 12/60 per minute.
- **Load balancer?** gunicorn 2 workers + Render's router (no Kafka).
- **Cache?** `backend/cache/redis_cache.py`, 24h ± jitter, stampede lock, SWR.
