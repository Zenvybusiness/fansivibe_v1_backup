"""Unit tests for backend application Settings (app.config.settings).

Validates:
- youtube_data_api_key defaults to unset (None).
- youtube_data_api_key loads from the YOUTUBE_DATA_API_KEY environment variable.
- Empty or whitespace-only values are treated as unset (None).
- Stripping of leading/trailing whitespace for valid keys.
- Direct keyword argument support with alias and field name.
- Secret is not exposed via repr() / string representation.
- get_settings() cache and clear_settings_cache() lifecycle.
- Existing settings defaults, production invariants, and behavior are preserved.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings, clear_settings_cache, get_settings


class TestYouTubeApiKeySettings:
    """Validate YouTube Data API v3 key configuration semantics."""

    def test_defaults_to_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)
        clear_settings_cache()

        settings = Settings()
        assert settings.youtube_data_api_key is None
        assert Settings.model_fields["youtube_data_api_key"].default is None

    def test_loads_from_environment(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "test-youtube-key-12345")
        clear_settings_cache()

        settings = Settings()
        assert settings.youtube_data_api_key == "test-youtube-key-12345"

    def test_empty_string_env_var_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "")
        clear_settings_cache()

        settings = Settings()
        assert settings.youtube_data_api_key is None

    def test_whitespace_only_env_var_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "   \t\n  ")
        clear_settings_cache()

        settings = Settings()
        assert settings.youtube_data_api_key is None

    def test_strips_surrounding_whitespace(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "  test-padded-key  ")
        clear_settings_cache()

        settings = Settings()
        assert settings.youtube_data_api_key == "test-padded-key"

    def test_direct_kwargs_with_field_name(self):
        assert (
            Settings(youtube_data_api_key="direct-key").youtube_data_api_key
            == "direct-key"
        )
        assert Settings(youtube_data_api_key=None).youtube_data_api_key is None
        assert Settings(youtube_data_api_key="").youtube_data_api_key is None
        assert Settings(youtube_data_api_key="   ").youtube_data_api_key is None

    def test_direct_kwargs_with_alias(self):
        assert (
            Settings(YOUTUBE_DATA_API_KEY="direct-alias-key").youtube_data_api_key
            == "direct-alias-key"
        )
        assert Settings(YOUTUBE_DATA_API_KEY=None).youtube_data_api_key is None
        assert Settings(YOUTUBE_DATA_API_KEY="").youtube_data_api_key is None
        assert Settings(YOUTUBE_DATA_API_KEY="   ").youtube_data_api_key is None

    def test_get_settings_cache_and_clear_lifecycle(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "key-one")
        clear_settings_cache()
        s1 = get_settings()
        assert s1.youtube_data_api_key == "key-one"

        # Cached instance returned
        monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "key-two")
        assert get_settings().youtube_data_api_key == "key-one"

        # Cache clear allows fresh load
        clear_settings_cache()
        s2 = get_settings()
        assert s2.youtube_data_api_key == "key-two"

        clear_settings_cache()

    def test_secret_not_exposed_in_repr(self):
        settings = Settings(youtube_data_api_key="secret-sensitive-key-999")
        assert "secret-sensitive-key-999" not in repr(settings)
        assert "secret-sensitive-key-999" not in str(settings)


class TestExistingSettingsPreserved:
    """Validate that existing settings behavior and invariants are unchanged."""

    def test_core_defaults_preserved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)
        monkeypatch.delenv("FANSIVIBE_ALLOW_DEV_TOKEN", raising=False)
        clear_settings_cache()
        settings = Settings(environment="development")

        assert settings.environment == "development"
        assert settings.is_production is False
        assert settings.is_staging is False
        assert settings.is_docs_enabled is True
        assert settings.allow_dev_token is False
        assert settings.log_level == "INFO"
        assert settings.db_pool_size == 5
        assert settings.rate_limit_auth_per_minute == 60
        assert settings.tryon_enabled is True
        assert settings.tryon_provider == "mock"

    def test_production_invariants_still_enforced(self):
        # Default dev settings must still be rejected in production
        with pytest.raises(ValidationError, match="development credentials"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe",
                auth_secret="a" * 32,
                allow_dev_token=False,
            )

    def test_production_succeeds_with_or_without_youtube_key(self):
        s_without = Settings(
            environment="production",
            database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
            auth_secret="a" * 32,
            allow_dev_token=False,
        )
        assert s_without.youtube_data_api_key is None

        s_with = Settings(
            environment="production",
            database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
            auth_secret="a" * 32,
            allow_dev_token=False,
            youtube_data_api_key="prod-dummy-key",
        )
        assert s_with.youtube_data_api_key == "prod-dummy-key"
