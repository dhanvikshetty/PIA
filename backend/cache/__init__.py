"""Redis-backed caching layer (optional — no-op when REDIS_URL is unset)."""

from backend.cache.redis_cache import cache

__all__ = ["cache"]
