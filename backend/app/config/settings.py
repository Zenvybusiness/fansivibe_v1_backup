"""Environment-driven service settings.

Single source of truth for configuration (`BACKEND_FOLDER_STRUCTURE.md` §6.2).
This is a **leaf** module: it may import stdlib and ``pydantic_settings`` only,
never any ``app.*`` module.

Settings load from environment variables at first access and are cached by the
``get_settings`` factory. ``main.py`` loads them once at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe"
)


class Settings(BaseSettings):
    """Configuration for the Fansivibe backend service."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = Field(default=_DEFAULT_DATABASE_URL)
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
        default="dev-only-insecure-auth-secret",
        alias="FANSIVIBE_AUTH_SECRET",
    )
    auth_expires_in_s: int = Field(
        default=3600, alias="FANSIVIBE_AUTH_EXPIRES_IN_S"
    )
    vision_host: str = Field(
        default="http://localhost:11434", alias="FANSIVIBE_VISION_HOST"
    )
    vision_model: str = Field(
        default="llama3.2-vision", alias="FANSIVIBE_VISION_MODEL"
    )
    vision_timeout_s: float = Field(
        default=20.0, alias="FANSIVIBE_VISION_TIMEOUT_S"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (loaded once)."""
    return Settings()
