"""Environment-driven service settings.

Single source of truth for configuration (`BACKEND_FOLDER_STRUCTURE.md` §6.2).
This is a **leaf** module: it may import stdlib and ``pydantic_settings`` only,
never any ``app.*`` module.

Settings load from environment variables at first access and are cached by the
``get_settings`` factory. ``main.py`` loads them once at startup.
"""

from __future__ import annotations

from functools import lru_cache
import os
from typing import Any
import typing

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe"
)
_DEV_AUTH_SECRET = "dev-only-insecure-auth-secret"


class Settings(BaseSettings):
    """Configuration for the Fansivibe backend service."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        extra="ignore",
        populate_by_name=True,
    )

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
    # D-01 STEP 1: dedicated abuse budget for unauthenticated ephemeral
    # guest analysis (sliding-window per IP, same local limiter). Separate
    # from the auth/reasoning scopes so guest AI compute never borrows
    # their budgets and vice versa.
    ephemeral_rate_limit_per_minute: int = Field(
        default=30, alias="FANSIVIBE_RATE_LIMIT_EPHEMERAL_PER_MINUTE"
    )
    disable_reasoning: bool = Field(
        default=False, alias="FANSIVIBE_DISABLE_REASONING"
    )
    # Stage F0 mock virtual try-on: provider interface with safe defaults.
    # Only `mock` (deterministic $0 SVG) and `off` exist — no paid
    # provider code path, so a paid model cannot be silently enabled.
    # `tryon_enabled=false` (or provider `off`) fails closed with 503.
    tryon_enabled: bool = Field(
        default=True, alias="FANSIVIBE_TRYON_ENABLED"
    )
    tryon_provider: str = Field(default="mock", alias="FANSIVIBE_TRYON_PROVIDER")
    tryon_consent_version: str = Field(
        default="tryon-v1", alias="FANSIVIBE_TRYON_CONSENT_VERSION"
    )
    tryon_daily_quota_per_user: int = Field(
        default=20, alias="FANSIVIBE_TRYON_DAILY_QUOTA"
    )
    tryon_max_concurrent_jobs_per_user: int = Field(
        default=2, alias="FANSIVIBE_TRYON_MAX_CONCURRENT_JOBS"
    )
    tryon_max_concurrent_jobs_global: int = Field(
        default=10, alias="FANSIVIBE_TRYON_MAX_GLOBAL_CONCURRENT_JOBS"
    )
    tryon_worker_concurrency_limit: int = Field(
        default=10, alias="FANSIVIBE_TRYON_WORKER_CONCURRENCY"
    )
    tryon_rate_limit_per_minute: int = Field(
        default=20, alias="FANSIVIBE_RATE_LIMIT_TRYON_PER_MINUTE"
    )
    tryon_stale_job_timeout_s: int = Field(
        default=300, alias="FANSIVIBE_TRYON_STALE_JOB_TIMEOUT_S"
    )
    tryon_worker_lease_seconds: int = Field(
        default=60, alias="FANSIVIBE_TRYON_WORKER_LEASE_SECONDS"
    )
    tryon_worker_heartbeat_interval_seconds: int = Field(
        default=15, alias="FANSIVIBE_TRYON_WORKER_HEARTBEAT_INTERVAL_SECONDS"
    )

    # Commercial Virtual Try-On Provider Configuration (Phase 5D)
    tryon_commercial_provider_name: str = Field(
        default="generic_commercial", alias="TRYON_COMMERCIAL_PROVIDER_NAME"
    )
    tryon_commercial_api_key: str | None = Field(
        default=None, alias="TRYON_COMMERCIAL_API_KEY", repr=False
    )
    tryon_commercial_endpoint_url: str | None = Field(
        default=None, alias="TRYON_COMMERCIAL_ENDPOINT_URL"
    )
    tryon_commercial_connect_timeout_s: float = Field(
        default=10.0, alias="TRYON_COMMERCIAL_CONNECT_TIMEOUT_S"
    )
    tryon_commercial_inference_timeout_s: float = Field(
        default=60.0, alias="TRYON_COMMERCIAL_INFERENCE_TIMEOUT_S"
    )
    tryon_commercial_max_retries: int = Field(
        default=2, alias="TRYON_COMMERCIAL_MAX_RETRIES"
    )

    # Genlook Commercial Virtual Try-On API Configuration (Phase 5F)
    genlook_api_key: str | None = Field(
        default=None, alias="GENLOOK_API_KEY", repr=False
    )
    genlook_api_base_url: str = Field(
        default="https://api.genlook.app/tryon/v1", alias="GENLOOK_API_BASE_URL"
    )
    genlook_connect_timeout_s: float = Field(
        default=10.0, alias="GENLOOK_CONNECT_TIMEOUT_S"
    )
    genlook_request_timeout_s: float = Field(
        default=30.0, alias="GENLOOK_REQUEST_TIMEOUT_S"
    )
    genlook_poll_interval_s: float = Field(
        default=1.0, alias="GENLOOK_POLL_INTERVAL_S"
    )
    genlook_poll_timeout_s: float = Field(
        default=120.0, alias="GENLOOK_POLL_TIMEOUT_S"
    )
    genlook_max_retries: int = Field(
        default=2, alias="GENLOOK_MAX_RETRIES"
    )
    genlook_keep_for_days: int = Field(
        default=1, alias="GENLOOK_KEEP_FOR_DAYS"
    )
    genlook_ai_label: bool = Field(
        default=True, alias="GENLOOK_AI_LABEL"
    )

    # Operator / Cron Maintenance Authentication (Phase 5E.1)
    operator_api_key: str | None = Field(
        default=None, alias="FANSIVIBE_OPERATOR_API_KEY", repr=False
    )

    # Privacy and Media Retention Policies (Phase 5D)
    tryon_retention_enabled: bool = Field(
        default=True, alias="TRYON_RETENTION_ENABLED"
    )
    tryon_retention_person_photo_hours: int = Field(
        default=24, alias="TRYON_RETENTION_PERSON_PHOTO_HOURS"
    )
    tryon_retention_result_hours: int = Field(
        default=72, alias="TRYON_RETENTION_RESULT_HOURS"
    )
    tryon_retention_failed_jobs_hours: int = Field(
        default=24, alias="TRYON_RETENTION_FAILED_JOBS_HOURS"
    )
    tryon_retention_cancelled_jobs_hours: int = Field(
        default=12, alias="TRYON_RETENTION_CANCELLED_JOBS_HOURS"
    )
    extraction_retention_hours: int = Field(
        default=24, alias="EXTRACTION_RETENTION_HOURS"
    )
    log_level: str = Field(
        default="INFO", alias="FANSIVIBE_LOG_LEVEL"
    )

    # Optional static asset base URL override (e.g. CDN or reverse-proxy host)
    static_asset_base_url: str | None = Field(
        default=None, alias="FANSIVIBE_STATIC_ASSET_BASE_URL"
    )

    # YouTube Data API v3 configuration (optional, secret key)
    youtube_data_api_key: str | None = Field(
        default=None, alias="YOUTUBE_DATA_API_KEY", repr=False
    )

    # Amazon PA-API 5.0 and Rainforest API configuration (DISCOVERY-10B-4)
    amazon_associate_tag: str | None = Field(
        default=None, alias="AMAZON_ASSOCIATE_TAG", repr=False
    )
    amazon_paapi_access_key: str | None = Field(
        default=None, alias="AMAZON_PAAPI_ACCESS_KEY", repr=False
    )
    amazon_paapi_secret_key: str | None = Field(
        default=None, alias="AMAZON_PAAPI_SECRET_KEY", repr=False
    )
    amazon_paapi_region: str = Field(
        default="eu-west-1", alias="AMAZON_PAAPI_REGION"
    )
    rainforest_api_key: str | None = Field(
        default=None, alias="RAINFOREST_API_KEY", repr=False
    )

    # Media Object Storage Configuration (Stage 2 P0-4 / M16)
    media_storage_provider: str = Field(
        default="fake", alias="MEDIA_STORAGE_PROVIDER"
    )
    r2_account_id: str | None = Field(
        default=None, alias="R2_ACCOUNT_ID", repr=False
    )
    r2_access_key_id: str | None = Field(
        default=None, alias="R2_ACCESS_KEY_ID", repr=False
    )
    r2_secret_access_key: str | None = Field(
        default=None, alias="R2_SECRET_ACCESS_KEY", repr=False
    )
    r2_bucket_name: str | None = Field(
        default=None, alias="R2_BUCKET_NAME"
    )
    r2_endpoint_url: str | None = Field(
        default=None, alias="R2_ENDPOINT_URL"
    )
    r2_region: str = Field(
        default="auto", alias="R2_REGION"
    )
    r2_connect_timeout_s: float = Field(
        default=5.0, alias="R2_CONNECT_TIMEOUT_S"
    )
    r2_read_timeout_s: float = Field(
        default=15.0, alias="R2_READ_TIMEOUT_S"
    )
    r2_max_retries: int = Field(
        default=2, alias="R2_MAX_RETRIES"
    )

    # Media Upload Authorization & Idempotency Key Ring (Stage 2 P0-4 / M16)
    media_upload_active_key_id: str = Field(
        default="kver_dev", alias="MEDIA_UPLOAD_ACTIVE_KEY_ID"
    )
    media_upload_previous_key_id: str | None = Field(
        default=None, alias="MEDIA_UPLOAD_PREVIOUS_KEY_ID"
    )
    media_upload_hmac_secret: str | None = Field(
        default=None, alias="MEDIA_UPLOAD_HMAC_SECRET", repr=False
    )
    media_upload_hmac_secret_previous: str | None = Field(
        default=None, alias="MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS", repr=False
    )
    media_upload_key_ring: dict[str, str] = Field(
        default_factory=dict, alias="MEDIA_UPLOAD_KEY_RING", repr=False
    )

    # Weather Provider Configuration (Stage 2 P1-3)
    weather_provider: str = Field(
        default="open_meteo", alias="WEATHER_PROVIDER"
    )
    weather_api_base_url: str = Field(
        default="https://api.open-meteo.com", alias="WEATHER_API_BASE_URL"
    )
    weather_timeout_s: float = Field(
        default=1.5, alias="WEATHER_TIMEOUT_S"
    )
    weather_cache_ttl_s: int = Field(
        default=1800, alias="WEATHER_CACHE_TTL_S"
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
    rate_limit_distributed: bool | None = Field(
        default=None, alias="FANSIVIBE_RATE_LIMIT_DISTRIBUTED"
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
    def effective_r2_endpoint_url(self) -> str | None:
        """Return the configured R2 endpoint URL or derive it from account ID."""
        if self.r2_endpoint_url:
            return self.r2_endpoint_url.rstrip("/")
        if self.r2_account_id:
            if self.r2_account_id.startswith(("http://", "https://")):
                from urllib.parse import urlparse

                parsed = urlparse(self.r2_account_id)
                if parsed.scheme and parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}"
            if self.r2_account_id.endswith(".r2.cloudflarestorage.com"):
                return f"https://{self.r2_account_id.rstrip('/')}"
            return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        return None

    @property
    def effective_media_upload_key_ring(self) -> dict[str, str]:
        """Structured key ring mapping key_version -> HMAC secret."""
        ring = dict(self.media_upload_key_ring)
        active_id = self.media_upload_active_key_id
        if self.media_upload_hmac_secret:
            ring[active_id] = self.media_upload_hmac_secret
        if self.media_upload_hmac_secret_previous:
            prev_id = self.media_upload_previous_key_id or "kver_previous"
            if prev_id not in ring:
                ring[prev_id] = self.media_upload_hmac_secret_previous
        if not ring:
            ring[active_id] = self.auth_secret
        return ring

    @property
    def active_media_upload_hmac_secret(self) -> str:
        """Return the secret corresponding to media_upload_active_key_id."""
        ring = self.effective_media_upload_key_ring
        secret = ring.get(self.media_upload_active_key_id)
        if not secret:
            return self.auth_secret
        return secret

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

    @field_validator("media_upload_key_ring", mode="before")
    @classmethod
    def _parse_media_upload_key_ring(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return {}
            try:
                import json

                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return {str(k).strip(): str(item).strip() for k, item in parsed.items()}
            except Exception:
                return {}
        if isinstance(v, dict):
            return {str(k).strip(): str(item).strip() for k, item in v.items()}
        return {}

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

    @field_validator("database_url", mode="before")
    @classmethod
    def _validate_database_url(cls, v: Any) -> str:
        if v is None:
            raise ValueError("DATABASE_URL must not be None.")
        val = str(v).strip()
        if not val:
            raise ValueError("DATABASE_URL must not be empty.")
        if val.startswith("driver://") or "driver://" in val:
            raise ValueError(
                "DATABASE_URL contains an unresolved placeholder scheme: 'driver://'"
            )
        if "user:pass@localhost/dbname" in val:
            raise ValueError(
                "DATABASE_URL contains an unresolved placeholder template ('user:pass@localhost/dbname')."
            )
        return val

    @field_validator("youtube_data_api_key", mode="before")
    @classmethod
    def _sanitize_youtube_data_api_key(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator("operator_api_key", mode="before")
    @classmethod
    def _sanitize_operator_api_key(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator("genlook_api_key", mode="before")
    @classmethod
    def _sanitize_genlook_api_key(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator(
        "amazon_associate_tag",
        "amazon_paapi_access_key",
        "amazon_paapi_secret_key",
        "rainforest_api_key",
        mode="before",
    )
    @classmethod
    def _sanitize_ecommerce_credentials(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator(
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket_name",
        "r2_endpoint_url",
        mode="before",
    )
    @classmethod
    def _sanitize_storage_credentials(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator("tryon_provider", mode="before")
    @classmethod
    def _normalize_tryon_provider(cls, v: Any) -> str:
        if v is None:
            return "mock"
        val = str(v).strip().lower()
        return val if val else "mock"

    @field_validator("media_storage_provider", mode="before")
    @classmethod
    def _normalize_media_storage_provider(cls, v: Any) -> str:
        if v is None:
            return "fake"
        val = str(v).strip().lower()
        if val in ("cloudflare_r2", "cloudflare", "r2_s3"):
            return "r2"
        if val in ("in_memory", "memory", "mock", "test"):
            return "fake"
        return val if val else "fake"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Skip default .env file loading during pytest unless explicitly overridden."""
        disable_dotenv = os.environ.get("FANSIVIBE_DISABLE_DOTENV", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        in_pytest = "PYTEST_CURRENT_TEST" in os.environ
        default_env_file = cls.model_config.get("env_file")
        explicit_env_file = getattr(dotenv_settings, "env_file", default_env_file) != default_env_file
        if (disable_dotenv or in_pytest) and not explicit_env_file:
            return (init_settings, env_settings, file_secret_settings)
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

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
            # Storage provider aliases
            if "media_storage_provider" not in data and "MEDIA_STORAGE_PROVIDER" not in data:
                provider = (
                    data.get("FANSIVIBE_MEDIA_STORAGE_PROVIDER")
                    or os.environ.get("FANSIVIBE_MEDIA_STORAGE_PROVIDER")
                )
                if provider:
                    data["media_storage_provider"] = provider
            # R2 account id aliases
            if "r2_account_id" not in data and "R2_ACCOUNT_ID" not in data:
                acct = (
                    data.get("CLOUDFLARE_R2_ACCOUNT_ID")
                    or os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID")
                    or data.get("FANSIVIBE_R2_ACCOUNT_ID")
                    or os.environ.get("FANSIVIBE_R2_ACCOUNT_ID")
                )
                if acct:
                    data["r2_account_id"] = acct
            # R2 access key id aliases
            if "r2_access_key_id" not in data and "R2_ACCESS_KEY_ID" not in data:
                key_id = (
                    data.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
                    or os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
                    or data.get("FANSIVIBE_R2_ACCESS_KEY_ID")
                    or os.environ.get("FANSIVIBE_R2_ACCESS_KEY_ID")
                )
                if key_id:
                    data["r2_access_key_id"] = key_id
            # R2 secret access key aliases
            if "r2_secret_access_key" not in data and "R2_SECRET_ACCESS_KEY" not in data:
                secret_key = (
                    data.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
                    or os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
                    or data.get("FANSIVIBE_R2_SECRET_ACCESS_KEY")
                    or os.environ.get("FANSIVIBE_R2_SECRET_ACCESS_KEY")
                )
                if secret_key:
                    data["r2_secret_access_key"] = secret_key
            # R2 bucket name aliases
            if "r2_bucket_name" not in data and "R2_BUCKET_NAME" not in data:
                bucket = (
                    data.get("CLOUDFLARE_R2_BUCKET_NAME")
                    or os.environ.get("CLOUDFLARE_R2_BUCKET_NAME")
                    or data.get("FANSIVIBE_R2_BUCKET_NAME")
                    or os.environ.get("FANSIVIBE_R2_BUCKET_NAME")
                )
                if bucket:
                    data["r2_bucket_name"] = bucket
            # R2 endpoint URL aliases
            if "r2_endpoint_url" not in data and "R2_ENDPOINT_URL" not in data:
                endpoint = (
                    data.get("CLOUDFLARE_R2_ENDPOINT_URL")
                    or os.environ.get("CLOUDFLARE_R2_ENDPOINT_URL")
                    or data.get("FANSIVIBE_R2_ENDPOINT_URL")
                    or os.environ.get("FANSIVIBE_R2_ENDPOINT_URL")
                )
                if endpoint:
                    data["r2_endpoint_url"] = endpoint
            # R2 region aliases
            if "r2_region" not in data and "R2_REGION" not in data:
                region = (
                    data.get("CLOUDFLARE_R2_REGION")
                    or os.environ.get("CLOUDFLARE_R2_REGION")
                    or data.get("FANSIVIBE_R2_REGION")
                    or os.environ.get("FANSIVIBE_R2_REGION")
                )
                if region:
                    data["r2_region"] = region
            # Previous key ID aliases
            if "media_upload_previous_key_id" not in data and "MEDIA_UPLOAD_PREVIOUS_KEY_ID" not in data:
                prev_kid = (
                    data.get("FANSIVIBE_MEDIA_UPLOAD_PREVIOUS_KEY_ID")
                    or os.environ.get("FANSIVIBE_MEDIA_UPLOAD_PREVIOUS_KEY_ID")
                )
                if prev_kid:
                    data["media_upload_previous_key_id"] = prev_kid
        return data

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> typing.Self:
        if self.tryon_provider not in ("mock", "off", "catvton", "commercial", "genlook"):
            raise ValueError(
                "FANSIVIBE_TRYON_PROVIDER must be 'mock', 'off', 'catvton', 'commercial', or 'genlook'."
            )
        if self.auth_expires_in_s < 60:
            raise ValueError("FANSIVIBE_AUTH_EXPIRES_IN_S must be at least 60.")
        if self.tryon_provider == "catvton" and self.is_production:
            raise ValueError(
                "CatVTON is an experimental prototype and cannot be enabled in production."
            )
        if self.tryon_provider == "commercial":
            if not self.tryon_commercial_endpoint_url:
                raise ValueError(
                    "Commercial try-on provider requires TRYON_COMMERCIAL_ENDPOINT_URL."
                )
            if not self.tryon_commercial_api_key:
                raise ValueError(
                    "Commercial try-on provider requires TRYON_COMMERCIAL_API_KEY."
                )
            if self.is_production and len(self.tryon_commercial_api_key) < 16:
                raise ValueError(
                    "Production requires a valid TRYON_COMMERCIAL_API_KEY (at least 16 characters)."
                )
        if self.tryon_provider == "genlook":
            if not self.genlook_api_key:
                raise ValueError(
                    "Genlook try-on provider requires GENLOOK_API_KEY."
                )
            if not self.genlook_api_base_url or not self.genlook_api_base_url.strip():
                raise ValueError(
                    "Genlook try-on provider requires GENLOOK_API_BASE_URL."
                )
            if self.is_production:
                if len(self.genlook_api_key) < 16:
                    raise ValueError(
                        "Production requires a valid GENLOOK_API_KEY (at least 16 characters)."
                    )
                if not self.genlook_api_base_url.strip().lower().startswith("https://"):
                    raise ValueError(
                        "Production requires GENLOOK_API_BASE_URL to use HTTPS."
                    )
        if self.genlook_connect_timeout_s <= 0:
            raise ValueError("GENLOOK_CONNECT_TIMEOUT_S must be greater than 0.")
        if self.genlook_request_timeout_s <= 0:
            raise ValueError("GENLOOK_REQUEST_TIMEOUT_S must be greater than 0.")
        if self.genlook_poll_interval_s <= 0:
            raise ValueError("GENLOOK_POLL_INTERVAL_S must be greater than 0.")
        if self.genlook_poll_timeout_s <= 0:
            raise ValueError("GENLOOK_POLL_TIMEOUT_S must be greater than 0.")
        if self.genlook_max_retries < 0:
            raise ValueError("GENLOOK_MAX_RETRIES must be non-negative.")
        if self.genlook_keep_for_days not in (1, 3, 7):
            raise ValueError("GENLOOK_KEEP_FOR_DAYS must be 1, 3, or 7.")
        if self.tryon_daily_quota_per_user < 1:
            raise ValueError(
                "FANSIVIBE_TRYON_DAILY_QUOTA must be at least 1."
            )
        if self.tryon_max_concurrent_jobs_per_user < 1:
            raise ValueError(
                "FANSIVIBE_TRYON_MAX_CONCURRENT_JOBS must be at least 1."
            )
        if self.tryon_max_concurrent_jobs_global < 1:
            raise ValueError(
                "FANSIVIBE_TRYON_MAX_GLOBAL_CONCURRENT_JOBS must be at least 1."
            )
        if self.tryon_worker_concurrency_limit < 1:
            raise ValueError(
                "FANSIVIBE_TRYON_WORKER_CONCURRENCY must be at least 1."
            )
        if self.tryon_rate_limit_per_minute < 1:
            raise ValueError(
                "FANSIVIBE_RATE_LIMIT_TRYON_PER_MINUTE must be at least 1."
            )
        if self.tryon_stale_job_timeout_s < 30:
            raise ValueError(
                "FANSIVIBE_TRYON_STALE_JOB_TIMEOUT_S must be at least 30."
            )
        if self.tryon_worker_lease_seconds < 10:
            raise ValueError(
                "FANSIVIBE_TRYON_WORKER_LEASE_SECONDS must be at least 10."
            )
        if self.tryon_worker_heartbeat_interval_seconds < 2:
            raise ValueError(
                "FANSIVIBE_TRYON_WORKER_HEARTBEAT_INTERVAL_SECONDS must be at least 2."
            )
        if self.tryon_worker_heartbeat_interval_seconds >= self.tryon_worker_lease_seconds:
            raise ValueError(
                "FANSIVIBE_TRYON_WORKER_HEARTBEAT_INTERVAL_SECONDS must be less than FANSIVIBE_TRYON_WORKER_LEASE_SECONDS."
            )
        if self.tryon_commercial_connect_timeout_s <= 0:
            raise ValueError(
                "TRYON_COMMERCIAL_CONNECT_TIMEOUT_S must be greater than 0."
            )
        if self.tryon_commercial_inference_timeout_s <= 0:
            raise ValueError(
                "TRYON_COMMERCIAL_INFERENCE_TIMEOUT_S must be greater than 0."
            )
        if self.tryon_commercial_max_retries < 0:
            raise ValueError(
                "TRYON_COMMERCIAL_MAX_RETRIES must be non-negative."
            )
        if self.tryon_retention_person_photo_hours < 1:
            raise ValueError(
                "TRYON_RETENTION_PERSON_PHOTO_HOURS must be at least 1."
            )
        if self.tryon_retention_result_hours < 1:
            raise ValueError(
                "TRYON_RETENTION_RESULT_HOURS must be at least 1."
            )
        if self.tryon_retention_failed_jobs_hours < 1:
            raise ValueError(
                "TRYON_RETENTION_FAILED_JOBS_HOURS must be at least 1."
            )
        if self.tryon_retention_cancelled_jobs_hours < 1:
            raise ValueError(
                "TRYON_RETENTION_CANCELLED_JOBS_HOURS must be at least 1."
            )
        if self.extraction_retention_hours < 1:
            raise ValueError(
                "EXTRACTION_RETENTION_HOURS must be at least 1."
            )
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
        if self.ephemeral_rate_limit_per_minute < 1:
            raise ValueError(
                "FANSIVIBE_RATE_LIMIT_EPHEMERAL_PER_MINUTE must be at least 1."
            )
        if self.media_storage_provider not in ("r2", "fake"):
            raise ValueError(
                f"MEDIA_STORAGE_PROVIDER must be 'r2' or 'fake', got '{self.media_storage_provider}'."
            )
        if self.media_storage_provider == "r2":
            if not self.r2_bucket_name:
                raise ValueError("R2 storage provider requires R2_BUCKET_NAME.")
            if not self.r2_access_key_id:
                raise ValueError("R2 storage provider requires R2_ACCESS_KEY_ID.")
            if not self.r2_secret_access_key:
                raise ValueError("R2 storage provider requires R2_SECRET_ACCESS_KEY.")
            if not self.effective_r2_endpoint_url:
                raise ValueError(
                    "R2 storage provider requires R2_ENDPOINT_URL or R2_ACCOUNT_ID."
                )
            if self.r2_connect_timeout_s <= 0:
                raise ValueError("R2_CONNECT_TIMEOUT_S must be greater than 0.")
            if self.r2_read_timeout_s <= 0:
                raise ValueError("R2_READ_TIMEOUT_S must be greater than 0.")
            if self.r2_max_retries < 0:
                raise ValueError("R2_MAX_RETRIES must be non-negative.")
        if self.weather_provider not in ("open_meteo", "off"):
            raise ValueError(
                f"WEATHER_PROVIDER must be 'open_meteo' or 'off', got '{self.weather_provider}'."
            )
        if self.weather_timeout_s <= 0:
            raise ValueError("WEATHER_TIMEOUT_S must be greater than 0.")
        if self.weather_cache_ttl_s < 0:
            raise ValueError("WEATHER_CACHE_TTL_S must be non-negative.")
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
            if any(origin.strip() == "*" for origin in self.cors_origins):
                raise ValueError(
                    "Production CORS must not use wildcard allow_origins=['*']. Specify explicit origins or leave empty."
                )
            for origin in self.cors_origins:
                if origin.strip().lower().startswith("http://"):
                    raise ValueError(
                        "Production CORS origins must use HTTPS, not cleartext HTTP."
                    )
            if self.cors_origin_regex:
                normalized_regex = self.cors_origin_regex.strip()
                if normalized_regex in (".*", ".+", "^.*$", "^.+$", "*"):
                    raise ValueError(
                        "Production FANSIVIBE_CORS_ORIGIN_REGEX must not be a wildcard pattern."
                    )
        if self.is_production:
            # 1. DATABASE_URL must not use default dev credentials, test DBs, or SQLite
            db_lower = self.database_url.lower()
            if (
                self.database_url == _DEFAULT_DATABASE_URL
                or "fansivibe_dev" in db_lower
                or "fansivibe_test" in db_lower
                or "fansivibe_disposable" in db_lower
                or db_lower.startswith("sqlite")
            ):
                raise ValueError(
                    "Production requires DATABASE_URL to be set explicitly without development credentials (fansivibe_dev)."
                )
            # 2. FANSIVIBE_AUTH_SECRET must not be the dev-only placeholder and must be >= 32 chars
            trimmed_auth = self.auth_secret.strip()
            if len(trimmed_auth) < 32:
                raise ValueError(
                    "Production FANSIVIBE_AUTH_SECRET must be at least 32 characters long."
                )
            if (
                self.auth_secret == _DEV_AUTH_SECRET
                or "dev" in trimmed_auth.lower()
                or "insecure" in trimmed_auth.lower()
                or "test-only" in trimmed_auth.lower()
            ):
                raise ValueError(
                    "Production requires FANSIVIBE_AUTH_SECRET to be explicitly set to a secure secret."
                )
            # 3. FANSIVIBE_ALLOW_DEV_TOKEN must not be enabled in production
            if self.allow_dev_token:
                raise ValueError(
                    "FANSIVIBE_ALLOW_DEV_TOKEN cannot be enabled in production."
                )
            # 4. Production cannot silently use fake storage; requires explicit R2 configuration with HTTPS
            if self.media_storage_provider != "r2":
                raise ValueError(
                    "Production requires MEDIA_STORAGE_PROVIDER to be explicitly set to 'r2'."
                )
            r2_url = self.effective_r2_endpoint_url or ""
            if not r2_url.lower().startswith("https://"):
                raise ValueError(
                    "Production requires R2 endpoint URL to use HTTPS."
                )
            # 5. Production media upload HMAC secret must be secure and >= 32 chars
            if self.media_upload_hmac_secret:
                if (
                    len(self.media_upload_hmac_secret) < 32
                    or "dev" in self.media_upload_hmac_secret.lower()
                    or "insecure" in self.media_upload_hmac_secret.lower()
                ):
                    raise ValueError(
                        "Production requires a secure MEDIA_UPLOAD_HMAC_SECRET (at least 32 characters)."
                    )
            if self.media_upload_hmac_secret_previous:
                if (
                    len(self.media_upload_hmac_secret_previous) < 32
                    or "dev" in self.media_upload_hmac_secret_previous.lower()
                    or "insecure" in self.media_upload_hmac_secret_previous.lower()
                ):
                    raise ValueError(
                        "Production requires a secure MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS (at least 32 characters)."
                    )
            active_secret = self.effective_media_upload_key_ring.get(self.media_upload_active_key_id)
            if (
                not active_secret
                or active_secret == _DEV_AUTH_SECRET
                or len(active_secret) < 32
                or "dev" in active_secret.lower()
                or "insecure" in active_secret.lower()
            ):
                raise ValueError(
                    "Production requires a secure MEDIA_UPLOAD_HMAC_SECRET (at least 32 characters)."
                )
            for kid, sec in self.effective_media_upload_key_ring.items():
                if (
                    not sec
                    or sec == _DEV_AUTH_SECRET
                    or len(sec) < 32
                    or "dev" in sec.lower()
                    or "insecure" in sec.lower()
                ):
                    raise ValueError(
                        f"Production requires a secure media upload HMAC secret for key '{kid}' (at least 32 characters)."
                    )
            # 6. Production operator maintenance API key, if configured, must be >= 32 chars
            if self.operator_api_key is not None:
                if (
                    len(self.operator_api_key) < 32
                    or "dev" in self.operator_api_key.lower()
                    or "insecure" in self.operator_api_key.lower()
                ):
                    raise ValueError(
                        "Production FANSIVIBE_OPERATOR_API_KEY must be at least 32 characters and not a dev placeholder."
                    )
        return self


def validate_production_startup(settings: Settings) -> None:
    """Enforce strict fail-closed production startup requirements.

    Executed during FastAPI application startup (`lifespan`) so real
    production deployments never start with mock/off Try-On when enabled,
    missing operator API key, or auth/upload HMAC secret reuse.
    """
    if not settings.is_production:
        return
    if settings.allow_dev_token:
        raise ValueError("FANSIVIBE_ALLOW_DEV_TOKEN cannot be enabled in production.")
    if settings.tryon_enabled and settings.tryon_provider != "genlook":
        raise ValueError(
            "Production requires FANSIVIBE_TRYON_PROVIDER='genlook' when Virtual Try-On is enabled."
        )
    if (
        not settings.operator_api_key
        or len(settings.operator_api_key.strip()) < 32
        or "dev" in settings.operator_api_key.lower()
        or "insecure" in settings.operator_api_key.lower()
    ):
        raise ValueError(
            "Production requires a mandatory FANSIVIBE_OPERATOR_API_KEY (at least 32 characters)."
        )
    has_explicit_upload_secret = bool(
        (settings.media_upload_hmac_secret and settings.media_upload_hmac_secret.strip())
        or settings.media_upload_key_ring.get(settings.media_upload_active_key_id)
    )
    if not has_explicit_upload_secret:
        raise ValueError(
            "Production requires an explicit MEDIA_UPLOAD_HMAC_SECRET separate from FANSIVIBE_AUTH_SECRET."
        )
    if settings.active_media_upload_hmac_secret == settings.auth_secret:
        raise ValueError(
            "Production MEDIA_UPLOAD_HMAC_SECRET must be distinct from FANSIVIBE_AUTH_SECRET."
        )
    raw_workers = os.environ.get("UVICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY")
    if raw_workers is not None:
        try:
            worker_count = int(raw_workers)
        except ValueError:
            worker_count = 1
        if worker_count > 1 and not str(settings.database_url).startswith("postgresql"):
            raise ValueError(
                "Multi-worker execution (UVICORN_WORKERS/WEB_CONCURRENCY > 1) requires a shared PostgreSQL DATABASE_URL."
            )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings (loaded once)."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings (useful in tests when env vars change)."""
    get_settings.cache_clear()
