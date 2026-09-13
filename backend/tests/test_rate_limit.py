"""21.2 — local auth rate limiter (DB-free).

Covers the sliding-window counter, the truthful 429 shape, settings
validation, and the FastAPI dependency (register/login guard) without
touching the database. The historical suite runs with
`FANSIVIBE_RATE_LIMIT_ENABLED=false` (see `tests/conftest.py`); these
tests enable counting explicitly per-test.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api import rate_limit
from app.api.errors import rate_limited
from app.config.settings import Settings, clear_settings_cache


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/auth/login",
            "headers": [],
        }
    )


@pytest.fixture(autouse=True)
def _isolated_limiter():
    rate_limit.reset()
    clear_settings_cache()
    yield
    rate_limit.reset()
    clear_settings_cache()


class TestSlidingWindow:
    def test_allows_up_to_limit_then_denies_truthfully(self):
        for _ in range(3):
            allowed, retry = rate_limit.check(
                "k1", limit=3, window_s=60.0, now=1000.0
            )
            assert allowed is True
            assert retry == 0
        allowed, retry = rate_limit.check("k1", limit=3, window_s=60.0, now=1000.0)
        assert allowed is False
        assert retry >= 1

    def test_window_slides_and_readmits(self):
        assert rate_limit.check("k2", limit=1, window_s=10.0, now=0.0)[0] is True
        assert rate_limit.check("k2", limit=1, window_s=10.0, now=5.0)[0] is False
        # Oldest hit aged out at t=10 -> allowed again.
        assert rate_limit.check("k2", limit=1, window_s=10.0, now=10.0 + 0.5)[0] is True

    def test_keys_are_independent(self):
        assert rate_limit.check("a", limit=1, window_s=60.0, now=0.0)[0] is True
        assert rate_limit.check("b", limit=1, window_s=60.0, now=0.0)[0] is True
        assert rate_limit.check("a", limit=1, window_s=60.0, now=0.0)[0] is False
        assert rate_limit.check("b", limit=1, window_s=60.0, now=0.0)[0] is False

    def test_reset_clears_buckets(self):
        assert rate_limit.check("k3", limit=1, window_s=60.0, now=0.0)[0] is True
        rate_limit.reset()
        assert rate_limit.check("k3", limit=1, window_s=60.0, now=0.0)[0] is True

    def test_memory_stays_bounded(self):
        for i in range(rate_limit._MAX_BUCKETS + 50):
            rate_limit.check(f"key-{i}", limit=1, window_s=60.0, now=0.0)
        assert rate_limit.bucket_count() <= rate_limit._MAX_BUCKETS


class TestRateLimitedShape:
    def test_truthful_429_with_retry_hint(self):
        err = rate_limited(retry_after_s=42)
        assert err.status_code == 429
        assert err.code == "RATE_LIMITED"
        assert err.details == {"retry_after": 42}

    def test_invalid_retry_fails_safe_to_default(self):
        err = rate_limited(retry_after_s=-5)
        assert err.status_code == 429
        assert err.details["retry_after"] >= 1


class TestSettings:
    def test_defaults(self):
        # Code defaults (conftest disables the limiter via env for the
        # suite, so assert the field defaults, not the env-resolved value).
        fields = Settings.model_fields
        assert fields["rate_limit_enabled"].default is True
        assert fields["rate_limit_auth_per_minute"].default == 60
        assert fields["rate_limit_window_s"].default == 60

    def test_rejects_non_positive_limits(self):
        with pytest.raises(ValidationError, match="RATE_LIMIT_AUTH_PER_MINUTE"):
            Settings(rate_limit_auth_per_minute=0)
        with pytest.raises(ValidationError, match="RATE_LIMIT_WINDOW_S"):
            Settings(rate_limit_window_s=0)


class TestAuthRateLimitDependency:
    def test_disabled_allows_unlimited(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_ENABLED", "false")
        clear_settings_cache()
        for _ in range(10):
            asyncio.run(rate_limit.auth_rate_limit(_request()))

    def test_enabled_denies_over_limit_with_429(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from app.api.errors import ApiError

        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_AUTH_PER_MINUTE", "2")
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_WINDOW_S", "60")
        clear_settings_cache()
        asyncio.run(rate_limit.auth_rate_limit(_request()))
        asyncio.run(rate_limit.auth_rate_limit(_request()))
        with pytest.raises(ApiError) as exc_info:
            asyncio.run(rate_limit.auth_rate_limit(_request()))
        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "RATE_LIMITED"
