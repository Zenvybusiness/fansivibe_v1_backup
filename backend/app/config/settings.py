"""Environment-driven service settings.

Single source of truth for configuration (`BACKEND_FOLDER_STRUCTURE.md` §6.2).
This is a **leaf** module: it may import stdlib and ``pydantic_settings`` only,
never any ``app.*`` module.

Settings load from environment variables at first access and are cached by the
``get_settings`` factory. ``main.py`` loads them once at startup.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
import typing

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe"
)
_DEV_AUTH_SECRET = "dev-only-insecure-auth-secret"


class Settings(BaseSettings):
    """Configuration for the Fansivibe backend service."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    # Environment designation ('development', 'test', 'production', 'staging').
    environment: str = Field(default="development", alias="FANSIVIBE_ENV")

    database_url: str = Field(default=_DEFAULT_DATABASE_URL)

    # Database connection pool configuration (P2-9)
    db_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    db_pool_timeout_s: float = Field(
        default=30.0, alias="DATABASE_POOL_TIMEOUT_S"
    )
    db_pool_recycle_s: int = Field(
        default=1800, alias="DATABASE_POOL_RECYCLE_S"
    )

    dev_token: str = Field(default="dev", alias="FANSIVIBE_DEV_TOKEN")
    # D-AUTH-1 — local email/password provider (the backend acts as its own
    # IdentityProvider behind the verify→Principal seam). The dev-token
    # fallback in `api/deps.py` is active ONLY when this flag is true
    # (tests/dev); production paths must leave it false so no shared
    # bootstrap identity can silently become production identity.
    allow_dev_token: bool = Field(
        default=False, alias="FANSIVIBE_ALLOW_DEV_TOKEN"
    )
    # HMAC secret minting/verifying JWT access tokens. The default is a
    # dev-only placeholder — production MUST set FANSIVIBE_AUTH_SECRET.
    auth_secret: str = Field(
        default=_DEV_AUTH_SECRET,
        alias="FANSIVIBE_AUTH_SECRET",
    )
    auth_expires_in_s: int = Field(
        default=3600, alias="FANSIVIBE_AUTH_EXPIRES_IN_S"
    )

    # AI Vision / Ollama configuration
    vision_host: str = Field(
        default="http://localhost:11434", alias="FANSIVIBE_VISION_HOST"
    )
    vision_model: str = Field(
        default="llama3.2-vision", alias="FANSIVIBE_VISION_MODEL"
    )
    vision_timeout_s: float = Field(
        default=20.0, alias="FANSIVIBE_VISION_TIMEOUT_S"
    )
    # 21.2 (H5) — typed kill-switch for vision in production: when true,
    # scans fail closed with `analyzer_unavailable` (no network I/O, no
    # fake AI result). Accepts 1/true/yes/on (case-insensitive).
    # The adapter also honors the legacy `FANSIVIBE_DISABLE_VISION=1`
    # process env for backwards compatibility.
    disable_vision: bool = Field(
        default=False, alias="FANSIVIBE_DISABLE_VISION"
    )

    # AI Fashion Reasoning / Ollama configuration (Phase 3AL)
    reasoning_host: str = Field(
        default="http://localhost:11434", alias="FANSIVIBE_OLLAMA_HOST"
    )
    reasoning_model: str = Field(
        default="qwen2.5vl:3b", alias="FANSIVIBE_OLLAMA_MODEL"
    )
    reasoning_timeout_s: float = Field(
        default=60.0, alias="FANSIVIBE_REASONING_TIMEOUT_S"
    )
    reasoning_connect_timeout_s: float = Field(
        default=5.0, alias="FANSIVIBE_OLLAMA_CONNECT_TIMEOUT"
    )
    reasoning_temperature: float = Field(
        default=0.0, alias="FANSIVIBE_REASONING_TEMPERATURE"
    )
    reasoning_max_retries: int = Field(
        default=1, alias="FANSIVIBE_REASONING_MAX_RETRIES"
    )
    reasoning_concurrency_limit: int = Field(
        default=2, alias="FANSIVIBE_REASONING_CONCURRENCY_LIMIT"
    )
    reasoning_keep_alive: str = Field(
        default="15m", alias="FANSIVIBE_REASONING_KEEP_ALIVE"
    )
    reasoning_rate_limit_per_minute: int = Field(
        default=30, alias="FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE"
    )
    disable_reasoning: bool = Field(
        default=False, alias="FANSIVIBE_DISABLE_REASONING"
    )
    log_level: str = Field(
        default="INFO", alias="FANSIVIBE_LOG_LEVEL"
    )

    # CORS configuration (P2-9): explicit origins list, never wildcard in prod.
    cors_origins: list[str] = Field(
        default_factory=list, alias="FANSIVIBE_CORS_ORIGINS"
    )

    # Optional origin regex (e.g. local Flutter Web dev servers on any port).
    # Explicit env override; when unset, non-production defaults to a
    # loopback-only pattern (see `effective_cors_origin_regex`).
    cors_origin_regex: str | None = Field(
        default=None, alias="FANSIVIBE_CORS_ORIGIN_REGEX"
    )

    # Whether browsers may send credentials (cookies / client certs).
    # Fansivibe auth is Bearer-token based (no cookies), so this defaults
    # to False. Enable only with explicit non-wildcard origins.
    cors_allow_credentials: bool = Field(
        default=False, alias="FANSIVIBE_CORS_ALLOW_CREDENTIALS"
    )

    # API Documentation (/docs, /redoc, /openapi.json) exposure (P2-9).
    # None means auto: enabled in dev/test, disabled by default in production.
    enable_docs: bool | None = Field(default=None, alias="FANSIVIBE_ENABLE_DOCS")

    # Local rate limiting (21.2): sliding-window guard for credential
    # endpoints (register/login). Single-process only — distributed
    # enforcement (Redis/edge) is Phase 21.3 infrastructure work.
    rate_limit_enabled: bool = Field(
        default=True, alias="FANSIVIBE_RATE_LIMIT_ENABLED"
    )
    rate_limit_auth_per_minute: int = Field(
        default=60, alias="FANSIVIBE_RATE_LIMIT_AUTH_PER_MINUTE"
    )
    rate_limit_window_s: int = Field(
        default=60, alias="FANSIVIBE_RATE_LIMIT_WINDOW_S"
    )

    @property
    def is_staging(self) -> bool:
        return self.environment.strip().lower() == "staging"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def is_docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return not (self.is_production or self.is_staging)

    @property
    def effective_cors_origin_regex(self) -> str | None:
        """Regex allowing local Flutter Web dev servers (any port).

        - Explicit `FANSIVIBE_CORS_ORIGIN_REGEX` always wins when set.
        - Otherwise non-production defaults to loopback-only
          `https?://(localhost|127.0.0.1)(:<port>)?` so `flutter run -d chrome`
          works on any ephemeral port without hardcoding one.
        - Production and staging with no explicit regex return None (no regex CORS).
        """
        if self.cors_origin_regex:
            return self.cors_origin_regex
        if not (self.is_production or self.is_staging):
            return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        return None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    import json

                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [
                            str(item).strip()
                            for item in parsed
                            if str(item).strip()
                        ]
                except Exception:
                    pass
            return [item.strip() for item in val.split(",") if item.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @model_validator(mode="before")
    @classmethod
    def _resolve_aliases(cls, data: Any) -> Any:
        import os
        if isinstance(data, dict):
            # Prefer FANSIVIBE_OLLAMA_BASE_URL, fallback to FANSIVIBE_OLLAMA_HOST
            if "reasoning_host" not in data and "FANSIVIBE_OLLAMA_HOST" not in data:
                url = data.get("FANSIVIBE_OLLAMA_BASE_URL") or os.environ.get("FANSIVIBE_OLLAMA_BASE_URL")
                if url:
                    data["reasoning_host"] = url
            # Prefer FANSIVIBE_OLLAMA_MODEL, fallback to FANSIVIBE_REASONING_MODEL
            if "reasoning_model" not in data and "FANSIVIBE_OLLAMA_MODEL" not in data:
                model = data.get("FANSIVIBE_REASONING_MODEL") or os.environ.get("FANSIVIBE_REASONING_MODEL")
                if model:
                    data["reasoning_model"] = model
            # Prefer FANSIVIBE_OLLAMA_TIMEOUT, fallback to FANSIVIBE_REASONING_TIMEOUT_S
            if "reasoning_timeout_s" not in data and "FANSIVIBE_REASONING_TIMEOUT_S" not in data:
                timeout = data.get("FANSIVIBE_OLLAMA_TIMEOUT") or os.environ.get("FANSIVIBE_OLLAMA_TIMEOUT")
                if timeout:
                    data["reasoning_timeout_s"] = float(timeout)
        return data

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> typing.Self:
        if self.rate_limit_auth_per_minute < 1:
            raise ValueError(
                "FANSIVIBE_RATE_LIMIT_AUTH_PER_MINUTE must be at least 1."
            )
        if self.rate_limit_window_s < 1:
            raise ValueError("FANSIVIBE_RATE_LIMIT_WINDOW_S must be at least 1.")
        if self.reasoning_concurrency_limit < 1:
            raise ValueError(
                "FANSIVIBE_REASONING_CONCURRENCY_LIMIT must be at least 1."
            )
        if self.reasoning_timeout_s <= 0:
            raise ValueError("FANSIVIBE_REASONING_TIMEOUT_S must be greater than 0.")
        if self.reasoning_connect_timeout_s <= 0:
            raise ValueError("FANSIVIBE_OLLAMA_CONNECT_TIMEOUT must be greater than 0.")
        if self.reasoning_rate_limit_per_minute < 1:
            raise ValueError(
                "FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE must be at least 1."
            )
        if self.is_production or self.is_staging:
            # Staging and production both forbid wildcard origins with credentials
            if self.cors_allow_credentials and any(
                origin.strip() == "*" for origin in self.cors_origins
            ):
                raise ValueError(
                    f"{self.environment.capitalize()} CORS must not use allow_origins=['*'] together "
                    "with allow_credentials=True."
                )
        if self.is_production:
            # 1. DATABASE_URL must not use default dev credentials or dev URL
            if (
                self.database_url == _DEFAULT_DATABASE_URL
                or "fansivibe_dev" in self.database_url
            ):
                raise ValueError(
                    "Production requires DATABASE_URL to be set explicitly without development credentials (fansivibe_dev)."
                )
            # 2. FANSIVIBE_AUTH_SECRET must not be the dev-only placeholder and must be >= 32 chars
            if self.auth_secret == _DEV_AUTH_SECRET:
                raise ValueError(
                    "Production requires FANSIVIBE_AUTH_SECRET to be explicitly set to a secure secret."
                )
            if len(self.auth_secret) < 32:
                raise ValueError(
                    "Production FANSIVIBE_AUTH_SECRET must be at least 32 characters long."
                )
            # 3. FANSIVIBE_ALLOW_DEV_TOKEN must not be enabled in production
            if self.allow_dev_token:
                raise ValueError(
                    "FANSIVIBE_ALLOW_DEV_TOKEN cannot be enabled in production."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (loaded once)."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings (useful in tests when env vars change)."""
    get_settings.cache_clear()
