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

    # CORS configuration (P2-9): explicit origins list, never wildcard in prod.
    cors_origins: list[str] = Field(
        default_factory=list, alias="FANSIVIBE_CORS_ORIGINS"
    )

    # API Documentation (/docs, /redoc, /openapi.json) exposure (P2-9).
    # None means auto: enabled in dev/test, disabled by default in production.
    enable_docs: bool | None = Field(default=None, alias="FANSIVIBE_ENABLE_DOCS")

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def is_docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return not self.is_production

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

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> typing.Self:
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
