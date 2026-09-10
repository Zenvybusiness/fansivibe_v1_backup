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
