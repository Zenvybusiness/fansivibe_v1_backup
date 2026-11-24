"""Tests for Phase 5D: VTON Production Readiness, Commercial Provider Architecture,
Cloudflare R2 Storage Hardening, Job Reliability, Privacy Retention, and Operational Controls.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import ApiError
from app.application.tryon import (
    InMemoryTryOnJobRepository,
    RetentionCleanupSummary,
    cleanup_retention_data,
    execute_tryon_inference,
    recover_interrupted_jobs,
    submit_job,
)
import app.application.tryon as tryon_app
from app.config.settings import Settings, get_settings
from app.domain.ports.repositories import TryOnJobRecord, WardrobeItemRecord
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageObjectMetadata,
    StoragePayloadError,
    StoragePermissionError,
)
from app.domain.ports.tryon_provider import (
    CommercialProviderConfigurationError,
    CommercialTryOnProvider,
    CommercialTryOnProviderConfig,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderQuotaExceededError,
    ProviderTransientError,
    TryOnProviderError,
)
from app.infrastructure.external.storage import (
    CloudflareR2StorageAdapter,
    validate_scoped_object_key,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

USER_A = uuid4()
USER_B = uuid4()


def _create_test_image_bytes(
    format: str = "PNG",
    size: tuple[int, int] = (256, 256),
    color: tuple[int, int, int] = (100, 100, 100),
) -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format)
    return buf.getvalue()


VALID_PNG_BYTES = _create_test_image_bytes("PNG")
VALID_JPEG_BYTES = _create_test_image_bytes("JPEG")
VALID_WEBP_BYTES = _create_test_image_bytes("WEBP")


class InMemoryWardrobeRepo:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add_item(
        self,
        user_id: UUID,
        item_id: UUID,
        category: str = "tops",
        name: str = "Test Shirt",
    ) -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        record = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name=name,
            category=category,
            color="navy",
            material="cotton",
            is_favorite=False,
            image_ref={"key": f"users/{user_id}/wardrobe/{item_id}/input.webp"},
            created_at=now,
            updated_at=now,
        )
        self.items[(user_id, item_id)] = record
        return record

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        return self.items.get((user_id, item_id))


# ==============================================================================
# 1. Provider Configuration Validation Tests
# ==============================================================================
class TestProviderConfigurationValidation:
    def test_catvton_rejected_in_production(self):
        with pytest.raises(ValueError, match=r"(?i)catvton.*production"):
            Settings(
                environment="production",
                secret_key="a" * 32,
                tryon_provider="catvton",
            )

    def test_mock_fails_closed_in_production(self):
        with patch.object(get_settings(), "environment", "production"):
            with patch.object(get_settings(), "tryon_provider", "mock"):
                with pytest.raises(ApiError) as excinfo:
                    submit_job(
                        user_id=str(USER_A),
                        idempotency_key="mock-prod-fail",
                        consent_accepted=True,
                        consent_version="tryon-v1",
                        outfit_source="wardrobe",
                        garment_ids=[str(uuid4())],
                        person_bytes=VALID_PNG_BYTES,
                        person_content_type="image/png",
                    )
                assert excinfo.value.status_code == 503

    def test_commercial_provider_missing_endpoint_rejected_in_production(self):
        with pytest.raises(ValueError, match=r"(?i)endpoint_url"):
            Settings(
                environment="production",
                secret_key="a" * 32,
                tryon_provider="commercial",
                tryon_commercial_endpoint_url=None,
                tryon_commercial_api_key="sk_live_1234567890abcdef",
            )

    def test_commercial_provider_missing_api_key_rejected_in_production(self):
        with pytest.raises(ValueError, match=r"(?i)api_key"):
            Settings(
                environment="production",
                secret_key="a" * 32,
                tryon_provider="commercial",
                tryon_commercial_endpoint_url="https://api.commercial-vton.com/v1/tryon",
                tryon_commercial_api_key=None,
            )

    def test_commercial_provider_insecure_placeholder_rejected_in_production(self):
        with pytest.raises(ValueError, match=r"(?i)at least 16 characters"):
            Settings(
                environment="production",
                secret_key="a" * 32,
                tryon_provider="commercial",
                tryon_commercial_endpoint_url="https://api.commercial-vton.com/v1/tryon",
                tryon_commercial_api_key="test-key",
            )

    def test_timeout_and_quota_validation(self):
        with pytest.raises(ValueError, match=r"(?i)greater than 0"):
            Settings(
                environment="development",
                tryon_commercial_inference_timeout_s=0,
            )

        with pytest.raises(ValueError, match=r"(?i)at least 1"):
            Settings(
                environment="development",
                tryon_daily_quota_per_user=0,
            )

        with pytest.raises(ValueError, match=r"(?i)at least 1"):
            Settings(
                environment="development",
                tryon_max_concurrent_jobs_per_user=0,
            )

    def test_commercial_config_repr_masks_credentials(self):
        config = CommercialTryOnProviderConfig(
            provider_name="commercial",
            endpoint_url="https://api.commercial-vton.com/v1/tryon",
            api_key="very_secret_production_key_value_123456",
        )
        repr_str = repr(config)
        assert "very_secret_production_key_value_123456" not in repr_str
        assert "..." in repr_str
        assert "https://api.commercial-vton.com/v1/tryon" in repr_str


# ==============================================================================
# 2. Commercial Provider Abstraction Tests
# ==============================================================================
class TestCommercialTryOnProvider:
    @pytest.fixture
    def valid_config(self):
        return CommercialTryOnProviderConfig(
            provider_name="commercial",
            endpoint_url="https://api.commercial-vton.com/v1/tryon",
            api_key="test-secret-key-12345678",
            connect_timeout_s=5.0,
            inference_timeout_s=15.0,
            max_retries=2,
            backoff_factor=1.0,
        )

    def test_input_magic_bytes_validation(self, valid_config):
        provider = CommercialTryOnProvider(valid_config)

        # Invalid person bytes
        with pytest.raises(ProviderPayloadError, match=r"(?i)unsupported or corrupt format"):
            provider.render(
                person_digest="digest-1",
                garment_labels=["shirt"],
                seed="seed-1",
                outfit_source="wardrobe",
                person_bytes=b"NOT_AN_IMAGE_PAYLOAD",
                garment_bytes=VALID_PNG_BYTES,
                category="tops",
            )

        # Invalid garment bytes
        with pytest.raises(ProviderPayloadError, match=r"(?i)unsupported or corrupt format"):
            provider.render(
                person_digest="digest-1",
                garment_labels=["shirt"],
                seed="seed-1",
                outfit_source="wardrobe",
                person_bytes=VALID_PNG_BYTES,
                garment_bytes=b"CORRUPT_GARMENT_BYTES",
                category="tops",
            )

    def test_successful_render_with_correlation_id(self, valid_config):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = VALID_WEBP_BYTES
        mock_response.headers = {"content-type": "image/webp"}
        mock_client.post.return_value = mock_response

        provider = CommercialTryOnProvider(valid_config, http_client=mock_client)

        result = provider.render(
            person_digest="digest-123",
            garment_labels=["navy polo"],
            seed="seed-abc",
            outfit_source="wardrobe",
            person_bytes=VALID_JPEG_BYTES,
            garment_bytes=VALID_PNG_BYTES,
            category="upper",
            correlation_id="corr-test-123",
        )

        assert result == VALID_WEBP_BYTES
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["headers"]["X-Correlation-ID"] == "corr-test-123"
        assert "Bearer test-secret-key-12345678" in call_kwargs["headers"]["Authorization"]

    def test_output_magic_bytes_validation(self, valid_config):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"error": "something bad happened"}'  # Non-image
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"error": "something bad happened"}
        mock_client.post.return_value = mock_response

        provider = CommercialTryOnProvider(valid_config, http_client=mock_client)

        with pytest.raises(ProviderPayloadError, match=r"(?i)missing image payload"):
            provider.render(
                person_digest="digest-123",
                garment_labels=["navy polo"],
                seed="seed-abc",
                outfit_source="wardrobe",
                person_bytes=VALID_PNG_BYTES,
                garment_bytes=VALID_PNG_BYTES,
                category="upper",
            )

    def test_transient_failure_retries_and_succeeds(self, valid_config):
        mock_client = MagicMock()
        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.text = "Service Temporarily Unavailable"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.content = VALID_PNG_BYTES
        success_response.headers = {"content-type": "image/png"}

        mock_client.post.side_effect = [fail_response, success_response]

        provider = CommercialTryOnProvider(valid_config, http_client=mock_client)

        with patch("time.sleep"):  # Skip real delays in tests
            result = provider.render(
                person_digest="digest-123",
                garment_labels=["navy polo"],
                seed="seed-abc",
                outfit_source="wardrobe",
                person_bytes=VALID_PNG_BYTES,
                garment_bytes=VALID_PNG_BYTES,
                category="upper",
            )

        assert result == VALID_PNG_BYTES
        assert mock_client.post.call_count == 2

    def test_non_transient_failures_do_not_retry(self, valid_config):
        mock_client = MagicMock()

        # 401 Unauthorized -> ProviderAuthError
        auth_response = MagicMock()
        auth_response.status_code = 401
        auth_response.text = "Unauthorized"
        mock_client.post.return_value = auth_response

        provider = CommercialTryOnProvider(valid_config, http_client=mock_client)

        with pytest.raises(ProviderAuthError):
            provider.render(
                person_digest="digest-123",
                garment_labels=["navy polo"],
                seed="seed-abc",
                outfit_source="wardrobe",
                person_bytes=VALID_PNG_BYTES,
                garment_bytes=VALID_PNG_BYTES,
                category="upper",
            )
        assert mock_client.post.call_count == 1

        # 429 Quota Exceeded -> ProviderQuotaExceededError
        mock_client.reset_mock()
        quota_response = MagicMock()
        quota_response.status_code = 429
        quota_response.text = "Rate limit reached"
        mock_client.post.return_value = quota_response

        with pytest.raises(ProviderQuotaExceededError):
            provider.render(
                person_digest="digest-123",
                garment_labels=["navy polo"],
                seed="seed-abc",
                outfit_source="wardrobe",
                person_bytes=VALID_PNG_BYTES,
                garment_bytes=VALID_PNG_BYTES,
                category="upper",
            )
        assert mock_client.post.call_count == 1

    def test_health_check(self, valid_config):
        mock_client = MagicMock()
        provider = CommercialTryOnProvider(valid_config, http_client=mock_client)

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        mock_client.get.return_value = ok_resp

        health_ok = provider.check_health()
        assert health_ok["status"] == "healthy"
        assert health_ok["provider"] == valid_config.provider_name

        err_resp = MagicMock()
        err_resp.status_code = 500
        mock_client.get.return_value = err_resp

        health_err = provider.check_health()
        assert health_err["status"] == "degraded"


# ==============================================================================
# 3. Cloudflare R2 Storage Hardening Tests
# ==============================================================================
class TestCloudflareR2StorageHardening:
    @pytest.fixture
    def mock_s3_client(self):
        return MagicMock()

    @pytest.fixture
    def r2_adapter(self, mock_s3_client):
        return CloudflareR2StorageAdapter(
            bucket_name="test-r2-bucket",
            endpoint_url="https://test.r2.cloudflarestorage.com",
            access_key_id="test-key",
            secret_access_key="test-secret",
            region_name="auto",
            s3_client=mock_s3_client,
        )

    def test_key_scoping_validation(self):
        uid = uuid4()
        # Valid key
        validate_scoped_object_key(f"users/{uid}/tryon/photo.jpg", user_id=uid)

        # Path traversal attempts
        with pytest.raises(StoragePayloadError, match=r"(?i)path traversal"):
            validate_scoped_object_key(f"users/{uid}/../other/photo.jpg", user_id=uid)

        with pytest.raises(StoragePayloadError, match=r"(?i)path traversal"):
            validate_scoped_object_key(f"users/{uid}\\photo.jpg", user_id=uid)

        with pytest.raises(StoragePayloadError, match=r"(?i)path traversal"):
            validate_scoped_object_key(f"/users/{uid}/photo.jpg", user_id=uid)

        # Wrong user scope
        other_uid = uuid4()
        with pytest.raises(StoragePermissionError):
            validate_scoped_object_key(f"users/{other_uid}/tryon/photo.jpg", user_id=uid)

    @pytest.mark.anyio
    async def test_put_object_content_type_validation(self, r2_adapter):
        # Invalid mime type rejected
        with pytest.raises(StoragePayloadError, match=r"(?i)unsupported content_type"):
            await r2_adapter.put_object(
                key="users/u1/test.exe",
                data=b"data",
                content_type="application/x-msdownload",
            )

    @pytest.mark.anyio
    async def test_idempotent_delete_object_handles_not_found(self, r2_adapter, mock_s3_client):
        error = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
            "DeleteObject",
        )
        mock_s3_client.delete_object.side_effect = error

        result = await r2_adapter.delete_object("users/u1/tryon/missing.jpg")
        assert result is True  # Idempotent deletion

    @pytest.mark.anyio
    async def test_safe_batch_deletion(self, r2_adapter, mock_s3_client):
        mock_s3_client.delete_object.return_value = {}

        keys = ["users/u1/1.jpg", "users/u1/2.jpg", "users/u1/3.jpg"]
        deleted_keys, failed_keys = await r2_adapter.delete_objects_safe(keys)
        assert len(deleted_keys) == 3
        assert len(failed_keys) == 0
        assert mock_s3_client.delete_object.call_count == 3

    @pytest.mark.anyio
    async def test_r2_health_check(self, r2_adapter, mock_s3_client):
        mock_s3_client.head_bucket.return_value = {}
        health = await r2_adapter.check_health()
        assert health["status"] == "healthy"

        mock_s3_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}},
            "HeadBucket",
        )
        health_fail = await r2_adapter.check_health()
        assert health_fail["status"] == "unhealthy"


# ==============================================================================
# 4. Job Reliability and State Machine Protection Tests
# ==============================================================================
class TestJobReliabilityAndStateProtection:
    @pytest.fixture(autouse=True)
    def setup_in_memory_env(self):
        tryon_app.reset_for_tests()
        yield
        tryon_app.reset_for_tests()

    def test_duplicate_submission_with_idempotency_key_returns_existing_job(self):
        storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = InMemoryWardrobeRepo()
        item = wardrobe_repo.add_item(USER_A, uuid4())

        # First submission
        job1, created1 = submit_job(
            user_id=str(USER_A),
            idempotency_key="idemp-12345",
            consent_accepted=True,
            consent_version="tryon-v1",
            outfit_source="wardrobe",
            garment_ids=[str(item.id)],
            person_bytes=VALID_PNG_BYTES,
            person_content_type="image/png",
            job_repo=job_repo,
            wardrobe_repo=wardrobe_repo,
            storage=storage,
        )
        assert created1 is True

        # Duplicate submission with same key
        job2, created2 = submit_job(
            user_id=str(USER_A),
            idempotency_key="idemp-12345",
            consent_accepted=True,
            consent_version="tryon-v1",
            outfit_source="wardrobe",
            garment_ids=[str(item.id)],
            person_bytes=VALID_PNG_BYTES,
            person_content_type="image/png",
            job_repo=job_repo,
            wardrobe_repo=wardrobe_repo,
            storage=storage,
        )
        assert created2 is False
        assert job1.id == job2.id
        assert job2.idempotency_key == "idemp-12345"

    def test_stale_worker_cannot_overwrite_cancelled_or_completed_job(self):
        job_repo = tryon_app._IN_MEMORY_REPO
        job_id = uuid4()
        now = datetime.now(timezone.utc)

        record = TryOnJobRecord(
            id=job_id,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="cancelled",
            consent_version="tryon-v1",
            consent_accepted_at=now,
            created_at=now,
            updated_at=now,
        )
        job_repo._jobs[job_id] = record

        # Worker attempts to transition cancelled job to completed via update_result
        res = job_repo.update_result(
            job_id=job_id,
            result_media_ref={"key": "some_key.webp"},
            completed_at=now,
        )
        # Should return existing record with status unchanged
        assert res is not None
        assert res.status == "cancelled"

        # Verify job is still cancelled
        curr = job_repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert curr.status == "cancelled"
        assert curr.result_media_ref is None

    def test_interrupted_job_startup_recovery(self):
        job_repo = tryon_app._IN_MEMORY_REPO
        now = datetime.now(timezone.utc)

        queued_id = uuid4()
        processing_id = uuid4()

        job_repo._jobs[queued_id] = TryOnJobRecord(
            id=queued_id,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=now,
            created_at=now,
            updated_at=now,
        )

        job_repo._jobs[processing_id] = TryOnJobRecord(
            id=processing_id,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="processing",
            consent_version="tryon-v1",
            consent_accepted_at=now,
            created_at=now,
            updated_at=now,
        )

        recovered = recover_interrupted_jobs(job_repo)
        assert recovered == 2

        q_job = job_repo.get_by_id(user_id=USER_A, job_id=queued_id)
        p_job = job_repo.get_by_id(user_id=USER_A, job_id=processing_id)

        assert q_job.status == "failed"
        assert q_job.error_code == "INTERRUPTED_BY_RESTART"
        assert "while queued" in q_job.error_message

        # Processing job must NOT have been re-inferred (protects against duplicate commercial billing)
        assert p_job.status == "failed"
        assert p_job.error_code == "INTERRUPTED_BY_RESTART"
        assert "during inference" in p_job.error_message


# ==============================================================================
# 5. Operational Controls and Privacy Retention Tests
# ==============================================================================
class TestOperationalControlsAndPrivacyRetention:
    @pytest.fixture(autouse=True)
    def setup_in_memory_env(self):
        tryon_app.reset_for_tests()
        yield
        tryon_app.reset_for_tests()

    def test_image_dimension_limits(self):
        storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = InMemoryWardrobeRepo()
        item = wardrobe_repo.add_item(USER_A, uuid4())

        # Too small (<64px)
        tiny_bytes = _create_test_image_bytes("PNG", size=(32, 32))
        with pytest.raises(ApiError) as excinfo:
            submit_job(
                user_id=str(USER_A),
                idempotency_key=str(uuid4()),
                consent_accepted=True,
                consent_version="tryon-v1",
                outfit_source="wardrobe",
                garment_ids=[str(item.id)],
                person_bytes=tiny_bytes,
                person_content_type="image/png",
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )
        assert excinfo.value.status_code == 422
        field_errors = excinfo.value.details.get("field_errors", [])
        assert any("64x64" in str(d) for d in field_errors)

    def test_concurrent_active_job_limit(self):
        storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = InMemoryWardrobeRepo()
        item = wardrobe_repo.add_item(USER_A, uuid4())

        # With max concurrent = 2
        with patch.object(get_settings(), "tryon_max_concurrent_jobs_per_user", 2):
            # Submit 1
            submit_job(
                user_id=str(USER_A),
                idempotency_key="c1",
                consent_accepted=True,
                consent_version="tryon-v1",
                outfit_source="wardrobe",
                garment_ids=[str(item.id)],
                person_bytes=VALID_PNG_BYTES,
                person_content_type="image/png",
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )
            # Submit 2
            submit_job(
                user_id=str(USER_A),
                idempotency_key="c2",
                consent_accepted=True,
                consent_version="tryon-v1",
                outfit_source="wardrobe",
                garment_ids=[str(item.id)],
                person_bytes=VALID_PNG_BYTES,
                person_content_type="image/png",
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )
            # Submit 3 should raise 429
            with pytest.raises(ApiError) as excinfo:
                submit_job(
                    user_id=str(USER_A),
                    idempotency_key="c3",
                    consent_accepted=True,
                    consent_version="tryon-v1",
                    outfit_source="wardrobe",
                    garment_ids=[str(item.id)],
                    person_bytes=VALID_PNG_BYTES,
                    person_content_type="image/png",
                    job_repo=job_repo,
                    wardrobe_repo=wardrobe_repo,
                    storage=storage,
                )
            assert excinfo.value.status_code == 429

    def test_daily_quota_enforcement(self):
        storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = InMemoryWardrobeRepo()
        item = wardrobe_repo.add_item(USER_A, uuid4())

        with patch.object(get_settings(), "tryon_daily_quota_per_user", 2):
            submit_job(
                user_id=str(USER_A),
                idempotency_key="q1",
                consent_accepted=True,
                consent_version="tryon-v1",
                outfit_source="wardrobe",
                garment_ids=[str(item.id)],
                person_bytes=VALID_PNG_BYTES,
                person_content_type="image/png",
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )
            submit_job(
                user_id=str(USER_A),
                idempotency_key="q2",
                consent_accepted=True,
                consent_version="tryon-v1",
                outfit_source="wardrobe",
                garment_ids=[str(item.id)],
                person_bytes=VALID_PNG_BYTES,
                person_content_type="image/png",
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )
            # 3rd job exceeds daily quota -> 429
            with pytest.raises(ApiError) as excinfo:
                submit_job(
                    user_id=str(USER_A),
                    idempotency_key="q3",
                    consent_accepted=True,
                    consent_version="tryon-v1",
                    outfit_source="wardrobe",
                    garment_ids=[str(item.id)],
                    person_bytes=VALID_PNG_BYTES,
                    person_content_type="image/png",
                    job_repo=job_repo,
                    wardrobe_repo=wardrobe_repo,
                    storage=storage,
                )
            assert excinfo.value.status_code == 429

    @pytest.mark.anyio
    async def test_privacy_retention_cleanup(self):
        storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        now = datetime.now(timezone.utc)

        # 1. Job with expired person photo (>24h)
        job_expired_photo = uuid4()
        photo_key = f"users/{USER_A}/tryon/{job_expired_photo}/person.png"
        await storage.put_object(photo_key, VALID_PNG_BYTES, content_type="image/png")
        job_repo._jobs[job_expired_photo] = TryOnJobRecord(
            id=job_expired_photo,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="completed",
            consent_version="tryon-v1",
            consent_accepted_at=now - timedelta(hours=25),
            created_at=now - timedelta(hours=25),
            updated_at=now - timedelta(hours=25),
            person_media_ref={"key": photo_key},
            result_media_ref={"key": f"users/{USER_A}/tryon/{job_expired_photo}/result.webp"},
        )

        # 2. Failed job (>24h)
        job_failed = uuid4()
        job_repo._jobs[job_failed] = TryOnJobRecord(
            id=job_failed,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="failed",
            consent_version="tryon-v1",
            consent_accepted_at=now - timedelta(hours=25),
            created_at=now - timedelta(hours=25),
            updated_at=now - timedelta(hours=25),
        )

        # 3. Cancelled job (>12h)
        job_cancelled = uuid4()
        job_repo._jobs[job_cancelled] = TryOnJobRecord(
            id=job_cancelled,
            user_id=USER_A,
            garment_id=uuid4(),
            garment_ids=("g-1",),
            outfit_source="wardrobe",
            provider="mock",
            status="cancelled",
            consent_version="tryon-v1",
            consent_accepted_at=now - timedelta(hours=13),
            created_at=now - timedelta(hours=13),
            updated_at=now - timedelta(hours=13),
        )

        # Run retention cleanup
        summary = await cleanup_retention_data(job_repo=job_repo, storage=storage, now=now)

        assert summary.person_photos_purged == 1
        assert summary.failed_jobs_deleted == 1
        assert summary.cancelled_jobs_deleted == 1

        # Check storage: person photo was deleted
        assert await storage.object_exists(photo_key) is False

        # Check DB: person_media_ref is None, but result and metadata remain
        rec = job_repo.get_by_id(user_id=USER_A, job_id=job_expired_photo)
        assert rec is not None
        assert rec.person_media_ref is None
        assert rec.result_media_ref is not None


# ==============================================================================
# 6. Phase 5D API Endpoints Tests
# ==============================================================================
class TestTryOnPhase5dApiEndpoints:
    @pytest.fixture(autouse=True)
    def setup_api_env(self):
        tryon_app.reset_for_tests()
        fake_storage = FakeStorageAdapter()
        job_repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = InMemoryWardrobeRepo()

        app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
        app.dependency_overrides[get_tryon_repository] = lambda: job_repo
        app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
        app.dependency_overrides[get_current_user_id] = lambda: USER_A

        yield {"storage": fake_storage, "repo": job_repo}

        app.dependency_overrides.clear()
        tryon_app.reset_for_tests()

    def test_health_endpoint(self):
        client = TestClient(app)
        resp = client.get("/v1/tryon/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "provider" in data
        assert "storage" in data
        assert "retention_policies" in data
        assert "quotas" in data

    def test_retention_cleanup_endpoint(self):
        client = TestClient(app)
        resp = client.post("/v1/tryon/maintenance/retention-cleanup")
        assert resp.status_code == 200
        data = resp.json()
        assert "person_photos_purged" in data
        assert "failed_jobs_deleted" in data
        assert "cancelled_jobs_deleted" in data
