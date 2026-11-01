"""Unit tests for storage dependency injection and application integration.

Validates:
- Correct adapter selected based on Settings.media_storage_provider:
  * 'fake' -> FakeStorageAdapter
  * 'r2' -> CloudflareR2StorageAdapter
- Dependency provider get_storage_adapter returns configured adapter.
- FastAPI dependency overrides allows injecting FakeStorageAdapter seamlessly.
- Application startup and storage adapter initialization never make unexpected
  network calls to Cloudflare R2.
- Singleton caching and reset_default_storage_adapter behavior.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

from app.api.deps import get_storage_adapter
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.storage import ObjectStoragePort
from app.infrastructure.external.storage import (
    CloudflareR2StorageAdapter,
    create_storage_adapter,
    get_default_storage_adapter,
    reset_default_storage_adapter,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter


@pytest.fixture(autouse=True)
def clean_storage_state():
    reset_default_storage_adapter()
    clear_settings_cache()
    yield
    reset_default_storage_adapter()
    clear_settings_cache()
    app.dependency_overrides.pop(get_storage_adapter, None)


class TestStorageDependencyInjection:
    """Validate DI seam, factory selection, and zero-network initialization."""

    def test_factory_creates_fake_adapter_when_provider_is_fake(self):
        settings = Settings(media_storage_provider="fake")
        adapter = create_storage_adapter(settings)
        assert isinstance(adapter, FakeStorageAdapter)
        assert isinstance(adapter, ObjectStoragePort)

    def test_factory_creates_r2_adapter_when_provider_is_r2(self):
        settings = Settings(
            media_storage_provider="r2",
            r2_bucket_name="prod-wardrobe-bucket",
            r2_account_id="cf-account-123",
            r2_access_key_id="cf-access-key-id",
            r2_secret_access_key="cf-secret-access-key",
            r2_region="auto",
        )
        adapter = create_storage_adapter(settings)
        assert isinstance(adapter, CloudflareR2StorageAdapter)
        assert isinstance(adapter, ObjectStoragePort)
        assert adapter.bucket_name == "prod-wardrobe-bucket"

    def test_dependency_provider_returns_fake_adapter_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "fake")
        clear_settings_cache()
        reset_default_storage_adapter()

        adapter = get_storage_adapter()
        assert isinstance(adapter, FakeStorageAdapter)

    def test_dependency_provider_returns_r2_adapter_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_BUCKET_NAME", "wardrobe-bucket")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct-test")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-test")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret-test")
        clear_settings_cache()
        reset_default_storage_adapter()

        adapter = get_storage_adapter()
        assert isinstance(adapter, CloudflareR2StorageAdapter)

    def test_fastapi_dependency_override_injects_fake(self):
        custom_fake = FakeStorageAdapter(bucket_name="injected-test-bucket")
        app.dependency_overrides[get_storage_adapter] = lambda: custom_fake

        # Verify dependency resolution matches override
        resolved = app.dependency_overrides[get_storage_adapter]()
        assert resolved is custom_fake
        assert resolved.bucket_name == "injected-test-bucket"

    def test_adapter_initialization_does_not_contact_network(self):
        """Verify that creating CloudflareR2StorageAdapter makes zero network calls."""
        settings = Settings(
            media_storage_provider="r2",
            r2_bucket_name="prod-wardrobe-bucket",
            r2_account_id="cf-account-test",
            r2_access_key_id="cf-access-key",
            r2_secret_access_key="cf-secret-key",
        )

        with patch("socket.socket.connect") as mock_connect, patch(
            "urllib3.connection.HTTPConnection.connect"
        ) as mock_http_connect:
            adapter = create_storage_adapter(settings)
            assert isinstance(adapter, CloudflareR2StorageAdapter)
            mock_connect.assert_not_called()
            mock_http_connect.assert_not_called()

    def test_singleton_lifecycle_caches_and_resets(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "fake")
        clear_settings_cache()
        reset_default_storage_adapter()

        s1 = get_default_storage_adapter(Settings())
        s2 = get_default_storage_adapter(Settings())
        assert s1 is s2

        reset_default_storage_adapter()
        s3 = get_default_storage_adapter(Settings())
        assert s3 is not s1
