"""Lightweight in-memory rate limiting for abuse-prone endpoints (21.2).

Scope (deliberately narrow): credential endpoints (register/login) only.
Broader enforcement (assistant/chat, analysis, write-heavy routes) and
distributed counting (Redis / edge WAF) are Phase 21.3 infrastructure
work — see `docs/PRODUCTION_DEPLOYMENT.md`. This module never invents
an external service: single-process sliding-window counting with
bounded memory, truthful HTTP 429, and fail-open behavior.

Properties:
- Sliding window per (scope, client IP); limits come from `Settings`
  (`FANSIVIBE_RATE_LIMIT_ENABLED`, `FANSIVIBE_RATE_LIMIT_AUTH_PER_MINUTE`,
  `FANSIVIBE_RATE_LIMIT_WINDOW_S`) — no hardcoded production limits.
- Bounded memory: at most `_MAX_BUCKETS` keys; the oldest bucket is
  evicted when full (protection is kept, memory cannot grow).
- Fail-open: any internal error allows the request (availability over
  strictness for a local limiter); only an explicit over-limit denies.
- No secrets logged: keys are (scope, IP) only; denial logs carry the
  scope and configured limit, never tokens, emails, or passwords.
- Deterministic tests: `reset()` clears all buckets; the dependency
  honors `FANSIVIBE_RATE_LIMIT_ENABLED=false` (the test suite disables
  it in `tests/conftest.py` so historical suites never flake).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque

from fastapi import Request

from app.api.errors import ApiError, rate_limited
from app.config.settings import get_settings

logger = logging.getLogger("fansivibe.api.rate_limit")

# Upper bound on tracked (scope, ip) buckets — prevents unbounded growth
# when facing a distributed scan. Oldest bucket evicted past this.
_MAX_BUCKETS = 10_000

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = {}


def _prune(bucket: deque[float], *, now: float, window_s: float) -> None:
    cutoff = now - window_s
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()


def check(
    key: str,
    *,
    limit: int,
    window_s: float,
    now: float | None = None,
) -> tuple[bool, int]:
    """Record one hit for `key`; return (allowed, retry_after_seconds).

    Pure sliding-window counter (no settings access — fully deterministic
    for tests via `now`). `retry_after_seconds` is 0 when allowed.
    """
    current = time.monotonic() if now is None else now
    with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            if len(_buckets) >= _MAX_BUCKETS:
                # Evict the oldest bucket (insertion order) to stay bounded.
                _buckets.pop(next(iter(_buckets)))
            bucket = _buckets[key] = deque()
        _prune(bucket, now=current, window_s=window_s)
        if len(bucket) < limit:
            bucket.append(current)
            return True, 0
        retry_after = max(1, int(math.ceil(bucket[0] + window_s - current)))
        return False, retry_after


def reset() -> None:
    """Clear all buckets (test isolation only)."""
    with _lock:
        _buckets.clear()


def bucket_count() -> int:
    """Number of tracked buckets (tests/observability; no key material)."""
    with _lock:
        return len(_buckets)


def _client_ip(request: Request) -> str:
    try:
        if request.client is not None and request.client.host:
            return request.client.host
    except Exception:
        pass
    return "unknown"


async def auth_rate_limit(request: Request) -> None:
    """FastAPI dependency: sliding-window guard for register/login.

    Raises truthful 429 (`RATE_LIMITED`) when the caller's IP exceeds
    `rate_limit_auth_per_minute` within `rate_limit_window_s`. Disabled
    entirely when `FANSIVIBE_RATE_LIMIT_ENABLED=false`. Fails open on
    any internal error — a broken local limiter must never take down
    authentication.
    """
    try:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        allowed, retry_after = check(
            f"auth:{_client_ip(request)}",
            limit=settings.rate_limit_auth_per_minute,
            window_s=float(settings.rate_limit_window_s),
        )
        if allowed:
            return
    except ApiError:
        raise
    except Exception:
        logger.warning("Rate limiter error; failing open for auth endpoint.")
        return
    raise rate_limited(retry_after_s=retry_after)
