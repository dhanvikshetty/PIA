"""
Per-client fixed-window rate limiting.

A fixed window is the simplest limiter that still stops abuse: each client gets
N requests per W-second window; the window resets wholesale when it rolls over.
We embed the window number in the counter key so the count "resets" naturally as
a new key appears — no background sweeping, no sliding-log bookkeeping.

Backing store (mirrors the cache's degrade-to-no-op pattern):
  - Redis when available  → counters are shared across every gunicorn worker and
    every Render instance, so the limit is global and correct under scale-out.
  - In-process dict fallback → when Redis is absent (local dev, Redis down) each
    worker counts on its own. Looser, but the app never breaks for lack of Redis.

Expensive routes (LLM / grounded research / auth) get a tighter budget than
ordinary reads. Health checks and CORS preflight (OPTIONS) are never limited.
"""

import time
import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from backend.config import settings
from backend.cache.redis_cache import cache


# Routes that trigger an LLM call, Google-Search grounding, a DB write, or auth —
# all far more costly (or abuse-sensitive) than a plain read. Matched by prefix.
_EXPENSIVE_PREFIXES = (
    "/api/query",
    "/api/company/about",
    "/api/companies/",       # {name} detail triggers grounded generation
    "/api/resume/analyze",
    "/api/fast-prep",
    "/api/ingest",
    "/api/eval/run",
    "/api/auth/",            # login/register — throttle credential stuffing
)

# Never rate-limited: liveness probes and CORS preflight.
_EXEMPT_PATHS = ("/api/health", "/health")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter; Redis-backed with an in-process fallback."""

    def __init__(self, app):
        super().__init__(app)
        # client_key -> [window_bucket, count]; only used when Redis is absent.
        self._local: dict[str, list] = {}

    def _client_id(self, request) -> str:
        """Identify the caller: real IP (via X-Forwarded-For behind Render's
        proxy) plus a short hash of any Bearer token, so two users behind one IP
        don't share a bucket."""
        xff = request.headers.get("x-forwarded-for", "")
        ip = xff.split(",")[0].strip() if xff else (
            request.client.host if request.client else "unknown"
        )
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            tok = auth[7:].strip()
            ip += ":" + hashlib.sha256(tok.encode()).hexdigest()[:12]
        return ip

    def _limit_for(self, path: str) -> int:
        if any(path.startswith(p) for p in _EXPENSIVE_PREFIXES):
            return settings.rate_limit_expensive
        return settings.rate_limit_default

    def _count(self, key: str, bucket: int, window: int) -> int:
        """Increment and return the count for this window. Redis first (shared),
        else an in-process bucket that self-resets when the window rolls over."""
        redis_key = f"ratelimit:{key}:{bucket}"
        n = cache.incr_fixed_window(redis_key, window)
        if n is not None:
            return n
        entry = self._local.get(key)
        if entry is None or entry[0] != bucket:
            entry = [bucket, 0]
        entry[1] += 1
        self._local[key] = entry
        return entry[1]

    async def dispatch(self, request, call_next):
        if not settings.rate_limit_enabled or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        window = max(1, settings.rate_limit_window_seconds)
        now = time.time()
        bucket = int(now // window)
        limit = self._limit_for(path)
        key = f"{self._client_id(request)}:{limit}"

        count = self._count(key, bucket, window)
        if count > limit:
            retry_after = int((bucket + 1) * window - now) or 1
            logger.warning(f"Rate limit hit: {path} client={key} ({count}/{limit})")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests — please slow down.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
