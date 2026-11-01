"""Unit tests for storage and Cloudflare R2 configuration in Settings.

Validates:
- Storage settings default safely to 'fake' without requiring credentials.
- Settings load accurately from environment variables and aliases.
- Credential validation fails closed when 'r2' is selected without required secrets.
- Fake storage works with zero R2 credentials in dev and test environments.
- Secrets (r2_secret_access_key, r2_access_key_id) are excluded from repr/str logging.
- Error messages do not leak secrets or credentials.
- Provider normalization and effective endpoint derivation behave correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings, clear_settings_cache, get_settings


class TestStorageConfiguration:
    """Validate storage configuration settings, sanitization, and invariant checks."""

    def test_storage_defaults_to_fake_without_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("MEDIA_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("FANSIVIBE_MEDIA_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)
        clear_settings_cache()

        settings = Settings()
        assert settings.media_storage_provider == "fake"
        assert settings.r2_account_id is None
        assert settings.r2_access_key_id is None
        assert settings.r2_secret_access_key is None
        assert settings.r2_bucket_name is None
        assert settings.effective_r2_endpoint_url is None

    def test_loads_r2_settings_from_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acc-123456789")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-id-abcdef")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-key-xyz-789")
        monkeypatch.setenv("R2_BUCKET_NAME", "fansivibe-wardrobe-prod")
        monkeypatch.setenv("R2_ENDPOINT_URL", "https://custom.endpoint.com")
        monkeypatch.setenv("R2_REGION", "auto")
        monkeypatch.setenv("R2_CONNECT_TIMEOUT_S", "7.5")
        monkeypatch.setenv("R2_READ_TIMEOUT_S", "20.0")
        monkeypatch.setenv("R2_MAX_RETRIES", "3")
        clear_settings_cache()

        settings = Settings()
        assert settings.media_storage_provider == "r2"
        assert settings.r2_account_id == "acc-123456789"
        assert settings.r2_access_key_id == "key-id-abcdef"
        assert settings.r2_secret_access_key == "secret-key-xyz-789"
        assert settings.r2_bucket_name == "fansivibe-wardrobe-prod"
        assert settings.r2_endpoint_url == "https://custom.endpoint.com"
        assert settings.effective_r2_endpoint_url == "https://custom.endpoint.com"
        assert settings.r2_region == "auto"
        assert settings.r2_connect_timeout_s == 7.5
        assert settings.r2_read_timeout_s == 20.0
        assert settings.r2_max_retries == 3

    def test_derives_effective_endpoint_from_account_id(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "cloudflare-account-abc")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-key-id")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret-key")
        monkeypatch.setenv("R2_BUCKET_NAME", "my-wardrobe-bucket")
        monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)
        clear_settings_cache()

        settings = Settings()
        assert (
            settings.effective_r2_endpoint_url
            == "https://cloudflare-account-abc.r2.cloudflarestorage.com"
        )

    def test_loads_from_cloudflare_and_fansivibe_aliases(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("MEDIA_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)

        monkeypatch.setenv("FANSIVIBE_MEDIA_STORAGE_PROVIDER", "cloudflare_r2")
        monkeypatch.setenv("CLOUDFLARE_R2_ACCOUNT_ID", "cf-account-999")
        monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "cf-key-999")
        monkeypatch.setenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "cf-secret-999")
        monkeypatch.setenv("CLOUDFLARE_R2_BUCKET_NAME", "cf-bucket-999")
        clear_settings_cache()

        settings = Settings()
        assert settings.media_storage_provider == "r2"
        assert settings.r2_account_id == "cf-account-999"
        assert settings.r2_access_key_id == "cf-key-999"
        assert settings.r2_secret_access_key == "cf-secret-999"
        assert settings.r2_bucket_name == "cf-bucket-999"
        assert (
            settings.effective_r2_endpoint_url
            == "https://cf-account-999.r2.cloudflarestorage.com"
        )

    def test_missing_bucket_fails_when_r2_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acc-123")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-123")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-123")
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "R2 storage provider requires R2_BUCKET_NAME" in str(excinfo.value)

    def test_missing_access_key_fails_when_r2_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acc-123")
        monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-123")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket-123")
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "R2 storage provider requires R2_ACCESS_KEY_ID" in str(excinfo.value)

    def test_missing_secret_key_fails_when_r2_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acc-123")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-123")
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket-123")
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "R2 storage provider requires R2_SECRET_ACCESS_KEY" in str(excinfo.value)

    def test_missing_endpoint_and_account_id_fails_when_r2_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-123")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-123")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket-123")
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "R2 storage provider requires R2_ENDPOINT_URL or R2_ACCOUNT_ID" in str(
            excinfo.value
        )

    def test_invalid_storage_provider_fails(self):
        with pytest.raises(ValidationError) as excinfo:
            Settings(media_storage_provider="invalid_storage_provider")
        assert "MEDIA_STORAGE_PROVIDER must be 'r2' or 'fake'" in str(excinfo.value)

    def test_secrets_are_excluded_from_repr_and_str(self):
        secret_value = "super-sensitive-secret-value-never-log"
        access_key_value = "sensitive-access-key-id-never-log"
        settings = Settings(
            media_storage_provider="fake",
            r2_secret_access_key=secret_value,
            r2_access_key_id=access_key_value,
        )

        repr_str = repr(settings)
        assert secret_value not in repr_str
        assert access_key_value not in repr_str
        assert "r2_secret_access_key" not in repr_str

    def test_empty_string_and_whitespace_sanitized_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("R2_ACCOUNT_ID", "   ")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "   \t\n  ")
        monkeypatch.setenv("R2_BUCKET_NAME", "   ")
        clear_settings_cache()

        settings = Settings()
        assert settings.r2_account_id is None
        assert settings.r2_access_key_id is None
        assert settings.r2_secret_access_key is None
        assert settings.r2_bucket_name is None

    def test_whitespace_is_stripped_from_valid_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_ACCOUNT_ID", "  account-padded  ")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "  key-padded  ")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "  secret-padded  ")
        monkeypatch.setenv("R2_BUCKET_NAME", "  bucket-padded  ")
        clear_settings_cache()

        settings = Settings()
        assert settings.r2_account_id == "account-padded"
        assert settings.r2_access_key_id == "key-padded"
        assert settings.r2_secret_access_key == "secret-padded"
        assert settings.r2_bucket_name == "bucket-padded"

    def test_production_cannot_silently_use_fake_storage(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("FANSIVIBE_ENV", "production")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://prod_user:prod_pass@prod-db.internal:5432/fansivibe_prod",
        )
        monkeypatch.setenv("FANSIVIBE_AUTH_SECRET", "p" * 32)
        monkeypatch.setenv("FANSIVIBE_ALLOW_DEV_TOKEN", "false")
        monkeypatch.delenv("MEDIA_STORAGE_PROVIDER", raising=False)
        monkeypatch.delenv("FANSIVIBE_MEDIA_STORAGE_PROVIDER", raising=False)
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "Production requires MEDIA_STORAGE_PROVIDER to be explicitly set to 'r2'" in str(
            excinfo.value
        )

    def test_production_requires_explicit_r2_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("FANSIVIBE_ENV", "production")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://prod_user:prod_pass@prod-db.internal:5432/fansivibe_prod",
        )
        monkeypatch.setenv("FANSIVIBE_AUTH_SECRET", "p" * 32)
        monkeypatch.setenv("FANSIVIBE_ALLOW_DEV_TOKEN", "false")
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
        monkeypatch.delenv("CLOUDFLARE_R2_BUCKET_NAME", raising=False)
        clear_settings_cache()

        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "R2 storage provider requires R2_BUCKET_NAME" in str(excinfo.value)

    def test_production_with_valid_r2_configuration_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("FANSIVIBE_ENV", "production")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://prod_user:prod_pass@prod-db.internal:5432/fansivibe_prod",
        )
        monkeypatch.setenv("FANSIVIBE_AUTH_SECRET", "p" * 32)
        monkeypatch.setenv("FANSIVIBE_ALLOW_DEV_TOKEN", "false")
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_BUCKET_NAME", "prod-wardrobe-bucket")
        monkeypatch.setenv("R2_ACCOUNT_ID", "cf-acc-prod-123456")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "cf-key-prod-123456")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "cf-secret-prod-123456")
        clear_settings_cache()

        settings = Settings()
        assert settings.is_production is True
        assert settings.media_storage_provider == "r2"
        assert settings.r2_bucket_name == "prod-wardrobe-bucket"
        assert (
            settings.effective_r2_endpoint_url
            == "https://cf-acc-prod-123456.r2.cloudflarestorage.com"
        )

    def test_development_and_test_allow_fake_storage_without_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        for env_name in ("development", "test"):
            monkeypatch.setenv("FANSIVIBE_ENV", env_name)
            monkeypatch.delenv("MEDIA_STORAGE_PROVIDER", raising=False)
            monkeypatch.delenv("FANSIVIBE_MEDIA_STORAGE_PROVIDER", raising=False)
            monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
            monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
            monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
            monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
            clear_settings_cache()

            settings = Settings()
            assert settings.is_production is False
            assert settings.media_storage_provider == "fake"
            assert settings.r2_bucket_name is None
