"""
Redis caching layer — optional, degrades to a no-op when REDIS_URL is unset.

Mirrors the Mongo→JSON fallback pattern: if Redis is unavailable (env var
missing, package absent, or the server unreachable) every method becomes a safe
no-op and callers behave exactly as they did before caching existed. Local dev
and the free-tier path keep working without a Redis instance.

What it caches (spec priority order):
  1. Grounded company dossiers / interview-question sets — TTL 24h ± 15min
     jitter to prevent synchronized expiry (thundering herd).
  2. Stampede protection — a SETNX lock so only one worker regenerates on a
     miss; concurrent callers wait for the holder to populate, and serve the
     stale value immediately when one exists (stale-while-revalidate).
  3. JWT refresh tokens — stored with the auth expiry so logout can revoke them
     (consumed by the auth layer).

Values are stored as a JSON envelope {_cached_at, _fresh_until, data}. The Redis
key TTL is the freshness window plus a grace period, so a stale value survives
long enough to be served while a refresh runs. The client is created lazily on
first use and a failed connection is remembered so a dead server isn't
retry-stormed on every request.
"""

import json
import time
import random
from typing import Any, Callable, Optional

from loguru import logger

from backend.config import settings


# Lock lifetime for a single regeneration (seconds). Covers a grounded Gemini
# call (~10-24s) plus margin; short enough to self-heal if the holder crashes.
_LOCK_TTL_SECONDS = 45

# On a miss with no stale value, poll this many times for the lock holder to
# populate before giving up and generating uncached ourselves.
_POLL_MAX = 30
_POLL_INTERVAL = 1.0

# Grace added to the freshness window for the hard key TTL, so a just-expired
# value can still be served stale while a refresh runs.
_STALE_GRACE_SECONDS = 24 * 3600

# Freshness-window jitter: ±15 minutes around the base TTL.
_JITTER_SECONDS = 15 * 60


class RedisCache:
    """Thin Redis wrapper that no-ops cleanly when Redis is unavailable."""

    def __init__(self):
        self._client = None
        self._resolved = False   # have we attempted a connection yet?
        self._enabled = False    # is a live client available?

    # -- connection -------------------------------------------------------

    def _resolve(self):
        """Lazily create + ping the client once; remember the outcome."""
        if self._resolved:
            return
        self._resolved = True
        url = (settings.redis_url or "").strip()
        if not url:
            logger.info("Redis cache disabled (REDIS_URL unset) — running no-op.")
            return
        try:
            import redis
            client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            client.ping()
            self._client = client
            self._enabled = True
            logger.info("Redis cache connected.")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — cache running no-op.")
            self._client = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        self._resolve()
        return self._enabled

    # -- low-level ops (guarded; safe defaults on any failure) ------------

    def get_json(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.warning(f"Redis get failed for {key}: {e}")
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if not self.enabled:
            return
        try:
            self._client.set(key, json.dumps(value), ex=max(1, int(ttl_seconds)))
        except Exception as e:
            logger.warning(f"Redis set failed for {key}: {e}")

    def delete(self, key: str) -> None:
        if not self.enabled:
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete failed for {key}: {e}")

    def exists(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists failed for {key}: {e}")
            return False

    def incr_fixed_window(self, key: str, ttl_seconds: int) -> Optional[int]:
        """
        Atomic counter for a fixed-window rate limiter. Increments `key` and,
        on the FIRST hit of a new window (count == 1), sets its TTL so the
        window self-expires. Returns the new count, or None if Redis is
        unavailable (caller then falls back to an in-process counter).
        """
        if not self.enabled:
            return None
        try:
            count = self._client.incr(key)
            if count == 1:
                self._client.expire(key, max(1, int(ttl_seconds)))
            return int(count)
        except Exception as e:
            logger.warning(f"Redis incr failed for {key}: {e}")
            return None

    def _acquire_lock(self, key: str, ttl: int = _LOCK_TTL_SECONDS) -> bool:
        """SETNX-style lock. Returns True iff we now hold it."""
        if not self.enabled:
            return False
        try:
            return bool(self._client.set(key, "1", nx=True, ex=ttl))
        except Exception as e:
            logger.warning(f"Redis lock acquire failed for {key}: {e}")
            return False

    def _release_lock(self, key: str) -> None:
        self.delete(key)

    # -- high-level: cached generation with stampede + SWR ----------------

    def _ttl_hours(self, override: Optional[int]) -> int:
        return int(override if override is not None else settings.cache_ttl_hours)

    def _fresh_window(self, ttl_hours: int) -> int:
        """Base TTL in seconds ± jitter, to desynchronize expiry."""
        base = ttl_hours * 3600
        return max(60, base + random.randint(-_JITTER_SECONDS, _JITTER_SECONDS))

    def _envelope(self, data: Any, fresh_window: int) -> dict:
        now = time.time()
        return {"_cached_at": now, "_fresh_until": now + fresh_window, "data": data}

    def get_or_generate(
        self,
        namespace: str,
        key: str,
        generator: Callable[[], Any],
        ttl_hours: Optional[int] = None,
        should_cache: Optional[Callable[[Any], bool]] = None,
    ) -> Any:
        """
        Return a cached value or generate it, with stampede protection and
        stale-while-revalidate.

        - No Redis → just call generator() (no-op cache).
        - Fresh hit → return cached data immediately.
        - Stale hit → if we win the refresh lock, regenerate inline and update;
          otherwise return the stale value now (another worker is refreshing).
        - Miss → the lock winner generates; others poll briefly for the winner
          to populate, then fall back to generating uncached.

        `should_cache(result)` gates what gets stored (default: a dict without an
        "error" key). Fallback/error results are returned but never cached.
        """
        if not self.enabled:
            return generator()

        full_key = f"{namespace}:{key}"
        lock_key = f"lock:{full_key}"
        ttl_hours = self._ttl_hours(ttl_hours)
        ok = should_cache or _default_should_cache

        def _generate_and_store():
            result = generator()
            if ok(result):
                self.set_json(
                    full_key,
                    self._envelope(result, self._fresh_window(ttl_hours)),
                    ttl_seconds=self._fresh_window(ttl_hours) + _STALE_GRACE_SECONDS,
                )
            return result

        env = self.get_json(full_key)
        if env and isinstance(env, dict) and "data" in env:
            if time.time() < env.get("_fresh_until", 0):
                return env["data"]                      # fresh HIT
            # stale — refresh inline if we win the lock, else serve stale now
            if self._acquire_lock(lock_key):
                try:
                    result = generator()
                    if ok(result):
                        self.set_json(
                            full_key,
                            self._envelope(result, self._fresh_window(ttl_hours)),
                            ttl_seconds=self._fresh_window(ttl_hours) + _STALE_GRACE_SECONDS,
                        )
                        return result
                    return env["data"]                  # gen failed → serve stale
                finally:
                    self._release_lock(lock_key)
            return env["data"]                          # SWR: serve stale now

        # MISS — one worker generates, others wait for it to populate
        if self._acquire_lock(lock_key):
            try:
                return _generate_and_store()
            finally:
                self._release_lock(lock_key)

        for _ in range(_POLL_MAX):
            time.sleep(_POLL_INTERVAL)
            env = self.get_json(full_key)
            if env and isinstance(env, dict) and "data" in env:
                return env["data"]
        return generator()   # holder never populated → generate uncached

    # -- refresh-token store (consumed by the auth layer) -----------------

    def store_refresh_token(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        self.set_json(f"refresh:{jti}", {"user_id": user_id}, ttl_seconds)

    def refresh_token_user(self, jti: str) -> Optional[str]:
        rec = self.get_json(f"refresh:{jti}")
        return rec.get("user_id") if isinstance(rec, dict) else None

    def revoke_refresh_token(self, jti: str) -> None:
        self.delete(f"refresh:{jti}")


def _default_should_cache(result: Any) -> bool:
    """Cache only successful dict results (no error / no fallback marker)."""
    return (
        isinstance(result, dict)
        and not result.get("error")
        and not result.get("_fallback")
    )


# Singleton — import `cache` everywhere.
cache = RedisCache()

