from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Protocol

redis: Any | None
try:  # Optional Redis dependency, mirroring services/sessions.py
    import redis as _redis
except Exception:  # pragma: no cover - redis is optional
    redis = None
else:
    redis = _redis

logger = logging.getLogger(__name__)


class IdempotencyStore(Protocol):
    """Best-effort store for webhook replay/idempotency keys."""

    def set_if_new(self, key: str, ttl_seconds: int) -> bool:
        """Return True if key was stored (not seen), False if already present."""

    def clear(self) -> None:
        """Clear all keys (intended for tests only)."""


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}

    def set_if_new(self, key: str, ttl_seconds: int) -> bool:
        now = time.time()
        if ttl_seconds > 0:
            expired = [k for k, ts in self._seen.items() if now - ts > ttl_seconds]
            for expired_key in expired:
                self._seen.pop(expired_key, None)
        if key in self._seen:
            return False
        self._seen[key] = now
        return True

    def clear(self) -> None:
        self._seen.clear()


class RedisIdempotencyStore:
    def __init__(self, client: Any, key_prefix: str = "idempotency") -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._fallback = InMemoryIdempotencyStore()

    def _key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    def set_if_new(self, key: str, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            # Treat replay protection disabled as always-new.
            return True
        try:
            # SET NX EX provides an atomic check+set with expiry.
            ok = self._client.set(self._key(key), "1", nx=True, ex=int(ttl_seconds))
            return bool(ok)
        except Exception:
            # Redis failures should never block request handling.
            logger.warning("redis_idempotency_set_failed", exc_info=True)
            return self._fallback.set_if_new(key, ttl_seconds=ttl_seconds)

    def clear(self) -> None:
        self._fallback.clear()
        try:
            pattern = f"{self._key_prefix}:*"
            keys = list(self._client.scan_iter(match=pattern))
            if keys:
                self._client.delete(*keys)
        except Exception:  # pragma: no cover - defensive
            logger.warning("redis_idempotency_clear_failed", exc_info=True)


def _create_idempotency_store() -> IdempotencyStore:
    backend = os.getenv("IDEMPOTENCY_STORE_BACKEND", "memory").lower()
    # Prefer Redis when REDIS_URL is present so multi-replica deployments get
    # shared replay protection without requiring an extra config knob.
    if backend == "memory" and os.getenv("REDIS_URL"):
        backend = "redis"
    if backend == "redis":
        if redis is None:
            logger.warning(
                "idempotency_store_backend_redis_unavailable_falling_back"
            )
        else:
            try:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                client = redis.from_url(redis_url)
                prefix = os.getenv("IDEMPOTENCY_KEY_PREFIX", "idempotency")
                return RedisIdempotencyStore(client, key_prefix=prefix)
            except Exception:
                logger.warning(
                    "idempotency_store_backend_redis_init_failed_falling_back",
                    exc_info=True,
                )
    return InMemoryIdempotencyStore()


idempotency_store: IdempotencyStore = _create_idempotency_store()
