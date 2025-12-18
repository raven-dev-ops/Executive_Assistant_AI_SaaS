from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Set


@dataclass
class TokenBucket:
    tokens: float
    last_refill: float


class RateLimitError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate_limited")
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    """Simple in-memory token bucket rate limiter keyed by arbitrary strings."""

    def __init__(
        self,
        per_minute: int,
        burst: int,
        whitelist_ips: Set[str] | None = None,
        disabled: bool = False,
    ) -> None:
        self.rate_per_second = float(per_minute) / 60.0
        self.burst = float(burst)
        self.whitelist_ips = whitelist_ips or set()
        self.disabled = disabled
        self._buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(tokens=self.burst, last_refill=time.time())
        )

    def check(self, key: str, *, ip: str | None = None) -> None:
        """Raise RateLimitError when the caller exceeds their bucket."""
        now = time.time()
        ip_value = ip or key.split(":", 1)[0]
        if ip_value in self.whitelist_ips:
            return
        if self.disabled:
            return

        bucket = self._buckets[key]
        # Refill tokens based on elapsed time.
        elapsed = max(now - bucket.last_refill, 0.0)
        bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate_per_second)
        bucket.last_refill = now

        if bucket.tokens < 1.0:
            retry_after = max(int(1.0 / self.rate_per_second), 1)
            raise RateLimitError(retry_after_seconds=retry_after)

        bucket.tokens -= 1.0
