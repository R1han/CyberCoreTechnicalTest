"""
Ask-Docs — Rate Limiter (per-IP, in-memory)
"""
from __future__ import annotations

import time
from collections import defaultdict

from app.config import settings


class RateLimiter:
    """Simple sliding-window per-IP rate limiter."""

    def __init__(self, max_requests: int = settings.rate_limit_per_minute, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        hits = self._hits[ip]
        # Prune old entries
        self._hits[ip] = [t for t in hits if now - t < self.window]
        if len(self._hits[ip]) >= self.max_requests:
            return False
        self._hits[ip].append(now)
        return True


rate_limiter = RateLimiter()
