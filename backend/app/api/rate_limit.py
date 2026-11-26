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

from datetime import datetime, timedelta, timezone
import logging
import math
import threading
import time
from collections import deque

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errors import ApiError, rate_limited
from app.config.settings import Settings, get_settings

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


def prune_expired_buckets(
    session: Session | None = None,
    *,
    older_than_s: float = 3600.0,
    now: datetime | None = None,
) -> int:
    """Delete expired rate_limit_buckets rows using ix_rate_limit_buckets_window_start."""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(seconds=max(60.0, float(older_than_s)))
    own_session = False
    db = session
    if db is None:
        from app.infrastructure.db.session import SessionLocal

        db = SessionLocal()
        own_session = True
    try:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            return 0
        res = db.execute(
            text("DELETE FROM rate_limit_buckets WHERE window_start < :cutoff_ts"),
            {"cutoff_ts": cutoff},
        )
        db.commit()
        return int(res.rowcount or 0)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        if own_session:
            try:
                db.close()
            except Exception:
                pass


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


def is_distributed_enabled(settings: Settings) -> bool:
    """Return True when PostgreSQL-backed multi-worker/instance rate limiting is active."""
    explicit = getattr(settings, "rate_limit_distributed", None)
    if explicit is not None:
        return bool(explicit)
    return bool(settings.is_production or settings.is_staging)


def check_distributed(
    key: str,
    *,
    limit: int,
    window_s: float,
    session: Session | None = None,
    now: datetime | None = None,
) -> tuple[bool, int]:
    """Atomic PostgreSQL-backed rate limit counter shared across workers and instances."""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(seconds=float(window_s))

    own_session = False
    db = session
    if db is None:
        from app.infrastructure.db.session import SessionLocal

        db = SessionLocal()
        own_session = True

    try:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            return check(key, limit=limit, window_s=window_s)

        row = db.execute(
            text(
                """
                INSERT INTO rate_limit_buckets (bucket_key, window_start, hit_count)
                VALUES (:bucket_key, :now_ts, 1)
                ON CONFLICT (bucket_key) DO UPDATE
                SET
                    hit_count = CASE
                        WHEN rate_limit_buckets.window_start <= :cutoff_ts THEN 1
                        ELSE LEAST(rate_limit_buckets.hit_count + 1, 2147483647)
                    END,
                    window_start = CASE
                        WHEN rate_limit_buckets.window_start <= :cutoff_ts THEN :now_ts
                        ELSE rate_limit_buckets.window_start
                    END
                RETURNING hit_count, window_start
                """
            ),
            {
                "bucket_key": key,
                "now_ts": current,
                "cutoff_ts": cutoff,
            },
        ).one()
        db.commit()
        hit_count = int(row[0])
        window_start = row[1]
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)
        if hit_count <= limit:
            return True, 0
        elapsed = (current - window_start).total_seconds()
        retry_after = max(1, int(math.ceil(float(window_s) - elapsed)))
        return False, retry_after
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        if own_session:
            try:
                db.close()
            except Exception:
                pass


def _check_for_request(
    *,
    scope: str,
    request: Request,
    limit: int,
    window_s: float,
    settings: Settings,
) -> tuple[bool, int]:
    key = f"{scope}:{_client_ip(request)}"
    if is_distributed_enabled(settings):
        try:
            return check_distributed(key, limit=limit, window_s=window_s)
        except Exception as exc:
            logger.warning(
                "Distributed rate limiter unavailable for %s (%s); falling back to process limiter.",
                scope,
                type(exc).__name__,
            )
    return check(key, limit=limit, window_s=window_s)


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
        allowed, retry_after = _check_for_request(
            scope="auth",
            request=request,
            limit=settings.rate_limit_auth_per_minute,
            window_s=float(settings.rate_limit_window_s),
            settings=settings,
        )
        if allowed:
            return
    except ApiError:
        raise
    except Exception:
        logger.warning("Rate limiter error; failing open for auth endpoint.")
        return
    raise rate_limited(retry_after_s=retry_after)


class ConcurrencyLimiter:
    """Bounded concurrency semaphore to protect single-process resources (e.g. Ollama VRAM)."""

    def __init__(self, limit: int = 2) -> None:
        self._limit = max(1, limit)
        self._semaphore = threading.Semaphore(self._limit)
        self._active = 0
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active

    def acquire(self, timeout: float = 1.0) -> bool:
        acquired = self._semaphore.acquire(blocking=True, timeout=timeout)
        if acquired:
            with self._lock:
                self._active += 1
        return acquired

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
        self._semaphore.release()


_reasoning_limiter: ConcurrencyLimiter | None = None
_limiter_lock = threading.Lock()


def get_reasoning_concurrency_limiter() -> ConcurrencyLimiter:
    global _reasoning_limiter
    with _limiter_lock:
        if _reasoning_limiter is None:
            settings = get_settings()
            _reasoning_limiter = ConcurrencyLimiter(
                limit=settings.reasoning_concurrency_limit
            )
        return _reasoning_limiter


def reset_reasoning_concurrency_limiter() -> None:
    global _reasoning_limiter
    with _limiter_lock:
        _reasoning_limiter = None


def reasoning_rate_limit(request: Request) -> None:
    """FastAPI dependency: sliding-window rate limit for fashion reasoning."""
    try:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        allowed, retry_after = _check_for_request(
            scope="reasoning",
            request=request,
            limit=settings.reasoning_rate_limit_per_minute,
            window_s=60.0,
            settings=settings,
        )
        if allowed:
            return
    except ApiError:
        raise
    except Exception:
        logger.warning("Rate limiter error; failing open for reasoning endpoint.")
        return
    raise rate_limited(retry_after_s=retry_after)


async def ephemeral_rate_limit(request: Request) -> None:
    """FastAPI dependency: sliding-window rate limit for ephemeral guest
    analysis (D-01 STEP 1).

    Dedicated `ephemeral:` scope (per client IP) with its own budget
    (`ephemeral_rate_limit_per_minute`, same window as auth) — guest AI
    compute never borrows the auth/reasoning budgets. Disabled with the
    suite-wide `FANSIVIBE_RATE_LIMIT_ENABLED=false` like the other scopes;
    fails open on internal error, same contract as the auth limiter.
    """
    try:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        allowed, retry_after = _check_for_request(
            scope="ephemeral",
            request=request,
            limit=settings.ephemeral_rate_limit_per_minute,
            window_s=float(settings.rate_limit_window_s),
            settings=settings,
        )
        if allowed:
            return
    except ApiError:
        raise
    except Exception:
        logger.warning("Rate limiter error; failing open for ephemeral endpoint.")
        return
    raise rate_limited(retry_after_s=retry_after)


async def tryon_rate_limit(request: Request) -> None:
    """FastAPI dependency: sliding-window rate limit for Virtual Try-On submissions/retries."""
    try:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        limit = int(getattr(settings, "tryon_rate_limit_per_minute", 20))
        allowed, retry_after = _check_for_request(
            scope="tryon",
            request=request,
            limit=limit,
            window_s=float(settings.rate_limit_window_s),
            settings=settings,
        )
        if allowed:
            return
    except ApiError:
        raise
    except Exception:
        logger.warning("Rate limiter error; failing open for try-on endpoint.")
        return
    try:
        from app.telemetry.metrics import get_metrics_collector

        get_metrics_collector().record_tryon_quota_rejection("rate_limit")
    except Exception:
        pass
    logger.warning(
        "TryOn rate limit exceeded [event=tryon_quota_rejected, reason=rate_limit, limit=%d]",
        limit,
    )
    raise rate_limited(retry_after_s=retry_after)

