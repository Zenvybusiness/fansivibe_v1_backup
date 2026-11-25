"""Unit tests for Phase 5E RunPod Serverless provider-contract compatibility."""

from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.domain.ports.tryon_provider import (
    CatVTONTryOnProvider,
    CommercialTryOnProvider,
    CommercialTryOnProviderConfig,
    FASHN_CATEGORIES,
    MockTryOnProvider,
    ProviderPayloadError,
    TryOnProvider,
    map_wardrobe_category_to_fashn,
)


class TestFashnCategoryMapping:
    @pytest.mark.parametrize(
        ("wardrobe_category", "expected"),
        [
            ("tops", "tops"),
            ("outerwear", "tops"),
            ("upper", "tops"),
            ("shirt", "tops"),
            ("blazer", "tops"),
            ("bottoms", "bottoms"),
            ("lower", "bottoms"),
            ("jeans", "bottoms"),
            ("trousers", "bottoms"),
            ("skirts", "bottoms"),
            ("one-pieces", "one-pieces"),
            ("dresses", "one-pieces"),
            ("jumpsuits", "one-pieces"),
            ("overall", "one-pieces"),
            ("  TOPS  ", "tops"),
        ],
    )
    def test_supported_categories_map_to_fashn_taxonomy(
        self, wardrobe_category: str, expected: str
    ) -> None:
        mapped = map_wardrobe_category_to_fashn(wardrobe_category)
        assert mapped == expected
        assert mapped in FASHN_CATEGORIES

    @pytest.mark.parametrize(
        "unsupported",
        ["footwear", "shoes", "accessories", "bag", "jewelry", "", "   ", "unknown"],
    )
    def test_unsupported_categories_fail_closed(self, unsupported: str) -> None:
        with pytest.raises(ProviderPayloadError, match="Unsupported garment category"):
            map_wardrobe_category_to_fashn(unsupported, correlation_id="corr-5e-1")


class TestProviderContractCompatibility:
    def test_providers_conform_to_protocol_and_accept_async_url_kwargs(self) -> None:
        mock_provider = MockTryOnProvider()
        catvton_provider = CatVTONTryOnProvider()
        commercial_provider = CommercialTryOnProvider(
            CommercialTryOnProviderConfig(
                provider_name="runpod_fashn_pending",
                api_key="test-key-not-live-1234",
                endpoint_url="https://api.runpod.ai/v2/placeholder/run",
            )
        )

        assert isinstance(mock_provider, TryOnProvider)
        assert isinstance(catvton_provider, TryOnProvider)
        assert isinstance(commercial_provider, TryOnProvider)

        # MockTryOnProvider accepts the extended Phase 5E kwargs without breaking
        svg_bytes = mock_provider.render(
            person_digest="abcdef1234567890",
            garment_labels=["item-1"],
            seed="seed-1",
            outfit_source="wardrobe",
            category="tops",
            correlation_id="corr-5e-2",
            job_id="00000000-0000-0000-0000-000000000001",
            person_image_url="https://example.invalid/person?sig=redacted",
            garment_image_url="https://example.invalid/garment?sig=redacted",
            result_upload_url="https://example.invalid/result?sig=redacted",
            is_cancelled_fn=lambda: False,
        )
        assert svg_bytes.startswith(b"<svg")

    def test_commercial_inference_remains_disabled_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("FANSIVIBE_TRYON_PROVIDER", raising=False)
        monkeypatch.delenv("TRYON_COMMERCIAL_API_KEY", raising=False)
        monkeypatch.delenv("TRYON_COMMERCIAL_ENDPOINT_URL", raising=False)
        settings = Settings()
        assert settings.tryon_provider == "mock"
        assert settings.tryon_commercial_api_key is None
        assert settings.tryon_commercial_endpoint_url is None

        with pytest.raises(ValueError, match=r"(?i)catvton.*production"):
            Settings(
                environment="production",
                auth_secret="a" * 32,
                tryon_provider="catvton",
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_account_id="prod-account",
                r2_access_key_id="prod-key",
                r2_secret_access_key="prod-secret",
                media_upload_hmac_secret="b" * 32,
            )

