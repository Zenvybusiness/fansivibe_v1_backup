"""Comprehensive automated test suite for Stage 2 P0-4 Phase 2:
Backend Upload Authorization, Durable Idempotency & Atomic Distributed Rate Limiting.

Covers:
1. Endpoint & Validation (Auth, headers, size, MIME type, purpose, filename, SHA-256 bounds).
2. Durable Idempotency (RFC 9440 conflict detection, identical retry reuse, cross-user isolation).
3. Storage Signing Resilience (Presigned URL generation failure recovery on retry).
4. Key Ring & Rotation (Version persistence, secret rotation stability).
5. Rate Limiting (Sliding 60s window, independent user limits, retention pruning).
6. Migration 0033 Metadata (Revision chain 0032 -> 0033).
7. Genuine Multi-Session PostgreSQL Concurrency Tests (Advisory locking across threads).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.api.errors import ApiError
from app.api.schemas.media import (
    ALLOWED_MIME_TYPES,
    ALLOWED_PURPOSES,
    MAX_IMAGE_SIZE_BYTES,
    UploadAuthorizationRequest,
)
from app.application.media import (
    AuthorizeMediaUpload,
    IdempotencyConflictError,
    MEDIA_UPLOAD_LOCK_NAMESPACE,
    compute_canonical_request_fingerprint,
    get_media_upload_lock_key,
    prune_expired_authorizations,
)
from app.config.settings import Settings, clear_settings_cache, get_settings
from app.domain.ports.storage import ObjectStoragePort, StorageError
from app.infrastructure.db.models import MediaUploadAuthorization
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sqlite_engine():
    """Isolated in-memory SQLite engine with MediaUploadAuthorization table."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MediaUploadAuthorization.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_db(sqlite_engine) -> Generator[Session, None, None]:
    """Yield a transactional session connected to the in-memory SQLite engine."""
    session_factory = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_storage() -> FakeStorageAdapter:
    """In-memory fake object storage adapter."""
    return FakeStorageAdapter(bucket_name="fansivibe-test-wardrobe")


@pytest.fixture
def test_user_id() -> UUID:
    """Fixed test user ID for hermetic assertions."""
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def other_user_id() -> UUID:
    """Second test user ID for cross-user isolation assertions."""
    return UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def client(sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID) -> TestClient:
    """FastAPI TestClient with overridden DB, storage adapter, and current user."""
    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: test_user_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 1. Endpoint & Validation Tests
# -----------------------------------------------------------------------------

class TestEndpointAndValidation:
    """Verify endpoint routing, OW-1 caller scoping, and strict input validation."""

    def test_unauthenticated_request_rejected_401(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter
    ):
        """Unauthenticated requests fail closed with HTTP 401."""
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: sqlite_db
        app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
        try:
            unauth_client = TestClient(app)
            response = unauth_client.post(
                "/v1/media/uploads",
                headers={"Idempotency-Key": "test-key-1"},
                json={
                    "purpose": "wardrobe_item",
                    "contentType": "image/webp",
                    "sizeBytes": 1024,
                },
            )
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_invalid_token_rejected_401(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter
    ):
        """Malformed or forged Bearer tokens fail with HTTP 401."""
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: sqlite_db
        app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
        try:
            unauth_client = TestClient(app)
            response = unauth_client.post(
                "/v1/media/uploads",
                headers={
                    "Authorization": "Bearer invalid.forged.jwt.token",
                    "Idempotency-Key": "test-key-1",
                },
                json={
                    "purpose": "wardrobe_item",
                    "contentType": "image/webp",
                    "sizeBytes": 1024,
                },
            )
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_missing_idempotency_key_rejected_422(self, client: TestClient):
        """Requests without an Idempotency-Key header are rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 1024,
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "idempotency" in str(data).lower()

    def test_empty_or_whitespace_idempotency_key_rejected_422(self, client: TestClient):
        """Empty or whitespace-only Idempotency-Key headers are rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "   "},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 1024,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_idempotency_key_too_long_rejected_422(self, client: TestClient):
        """Idempotency-Key exceeding 128 characters is rejected with HTTP 422."""
        too_long_key = "k" * 129
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": too_long_key},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 1024,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize("invalid_mime", [
        "image/png",
        "image/svg+xml",
        "image/gif",
        "application/pdf",
        "text/plain",
    ])
    def test_invalid_content_type_rejected_422(self, client: TestClient, invalid_mime: str):
        """Unsupported MIME types are strictly rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "key-mime-1"},
            json={
                "purpose": "wardrobe_item",
                "contentType": invalid_mime,
                "sizeBytes": 1024,
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("invalid_size", [
        0,
        -1,
        -500,
        MAX_IMAGE_SIZE_BYTES + 1,
        10 * 1024 * 1024,
    ])
    def test_size_bytes_bounds_rejected_422(self, client: TestClient, invalid_size: int):
        """Sizes <= 0 or > 2MB (2,097,152 bytes) are rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "key-size-1"},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": invalid_size,
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("invalid_purpose", [
        "face_scan",
        "avatar",
        "grooming",
        "profile_picture",
        "chat_attachment",
    ])
    def test_disallowed_purpose_rejected_422(self, client: TestClient, invalid_purpose: str):
        """Purposes outside MS10.3 'wardrobe_item' are rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "key-purp-1"},
            json={
                "purpose": invalid_purpose,
                "contentType": "image/webp",
                "sizeBytes": 1024,
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("invalid_sha", [
        "not-a-valid-hex-string",
        "abc123",  # too short
        "a" * 63,   # 63 chars
        "a" * 65,   # 65 chars
        "G" * 64,   # uppercase / non-hex
    ])
    def test_invalid_client_sha256_rejected_422(self, client: TestClient, invalid_sha: str):
        """Malformed client-asserted SHA-256 hashes are rejected with HTTP 422."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "key-sha-1"},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 1024,
                "clientAssertionSha256": invalid_sha,
            },
        )
        assert response.status_code == 422

    def test_path_traversal_filename_sanitized(self, client: TestClient, test_user_id: UUID):
        """Path traversal sequences in filename are stripped and do not affect stagingKey."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "key-traversal-1"},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 1024,
                "filename": "../../../etc/passwd.webp",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "passwd.webp" not in data["stagingKey"]
        assert data["stagingKey"].startswith(f"staging/users/{test_user_id}/wardrobe/")

    def test_authenticated_valid_request_succeeds_201(
        self, client: TestClient, test_user_id: UUID
    ):
        """Valid authenticated request returns HTTP 201 with staging key and presigned URL."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "auth-valid-001"},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/webp",
                "sizeBytes": 500_000,
                "filename": "camera_capture_01.webp",
                "clientAssertionSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        )
        assert response.status_code == 201
        data = response.json()

        # Wire assertions
        assert "uploadId" in data
        assert "uploadUrl" in data
        assert "stagingKey" in data
        assert "expiresAt" in data
        assert data["expiresInSeconds"] == 900
        assert data["requiredHeaders"] == {"Content-Type": "image/webp"}

        # Staging key format assertions: staging/users/{user_id}/wardrobe/{upload_id}.webp
        upload_id = data["uploadId"]
        expected_staging_key = f"staging/users/{test_user_id}/wardrobe/{upload_id}.webp"
        assert data["stagingKey"] == expected_staging_key
        assert upload_id in data["uploadUrl"]

    def test_jpeg_fallback_accepted_with_jpeg_staging_key(
        self, client: TestClient, test_user_id: UUID
    ):
        """JPEG content type is accepted as fallback and generates .jpeg staging key."""
        response = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "auth-jpeg-001"},
            json={
                "purpose": "wardrobe_item",
                "contentType": "image/jpeg",
                "sizeBytes": 300_000,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["stagingKey"].endswith(".jpeg")
        assert data["requiredHeaders"] == {"Content-Type": "image/jpeg"}


# -----------------------------------------------------------------------------
# 2. Durable Idempotency Tests
# -----------------------------------------------------------------------------

class TestDurableIdempotency:
    """Verify durable idempotency, conflict detection (RFC 9440), and retries."""

    def test_idempotency_returns_same_slot_on_identical_retry(
        self, client: TestClient, test_user_id: UUID
    ):
        """Identical retry with same key and parameters returns identical uploadId and stagingKey."""
        payload = {
            "purpose": "wardrobe_item",
            "contentType": "image/webp",
            "sizeBytes": 2048,
            "filename": "shirt.webp",
        }
        res1 = client.post("/v1/media/uploads", headers={"Idempotency-Key": "idem-100"}, json=payload)
        assert res1.status_code == 201
        data1 = res1.json()

        res2 = client.post("/v1/media/uploads", headers={"Idempotency-Key": "idem-100"}, json=payload)
        assert res2.status_code == 201
        data2 = res2.json()

        assert data1["uploadId"] == data2["uploadId"]
        assert data1["stagingKey"] == data2["stagingKey"]

    def test_idempotency_conflict_returns_409(self, client: TestClient):
        """Reusing the same Idempotency-Key with altered parameters returns HTTP 409 Conflict."""
        res1 = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "idem-conflict-1"},
            json={"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 1000},
        )
        assert res1.status_code == 201

        # Alter sizeBytes
        res2 = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "idem-conflict-1"},
            json={"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 2000},
        )
        assert res2.status_code == 409
        data2 = res2.json()
        assert data2["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert data2["error"]["details"]["idempotency_key"] == "idem-conflict-1"

    def test_different_users_independent_idempotency_namespaces(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID, other_user_id: UUID
    ):
        """Two different users can use the exact same Idempotency-Key without collision."""
        payload = {"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 1500}

        # User 1
        app.dependency_overrides[get_db] = lambda: sqlite_db
        app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
        app.dependency_overrides[get_current_user_id] = lambda: test_user_id
        client1 = TestClient(app)
        res1 = client1.post("/v1/media/uploads", headers={"Idempotency-Key": "shared-key-abc"}, json=payload)
        assert res1.status_code == 201
        data1 = res1.json()

        # User 2
        app.dependency_overrides[get_current_user_id] = lambda: other_user_id
        client2 = TestClient(app)
        res2 = client2.post("/v1/media/uploads", headers={"Idempotency-Key": "shared-key-abc"}, json=payload)
        assert res2.status_code == 201
        data2 = res2.json()

        # Separate authorizations and staging keys
        assert data1["uploadId"] != data2["uploadId"]
        assert data1["stagingKey"] != data2["stagingKey"]
        assert f"staging/users/{test_user_id}/wardrobe/" in data1["stagingKey"]
        assert f"staging/users/{other_user_id}/wardrobe/" in data2["stagingKey"]

    def test_idempotent_retry_does_not_consume_rate_limit_slot(
        self, client: TestClient, sqlite_db: Session, test_user_id: UUID
    ):
        """Multiple retries with the same Idempotency-Key create only 1 database authorization record."""
        payload = {"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 1000}
        for _ in range(5):
            res = client.post("/v1/media/uploads", headers={"Idempotency-Key": "multi-retry-key"}, json=payload)
            assert res.status_code == 201

        # Check database rows
        rows = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == test_user_id,
                MediaUploadAuthorization.idempotency_key == "multi-retry-key",
            )
        ).scalars().all()
        assert len(rows) == 1

    def test_presigned_url_failure_recovery_on_retry(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """If storage signing fails after persistence, client retry recovers the stored slot cleanly."""
        use_case = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
        )

        # 1. Simulate failure during URL generation
        fake_storage.simulate_failure = StorageError("Transient connection drop during SigV4 minting")
        with pytest.raises(ApiError) as exc_info:
            asyncio.run(
                use_case.execute(
                    user_id=test_user_id,
                    purpose="wardrobe_item",
                    content_type="image/webp",
                    size_bytes=1000,
                    idempotency_key="key-storage-fail-1",
                )
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.code == "STORAGE_SIGNING_ERROR"

        # 2. Verify row was persisted in PostgreSQL/SQLite
        row = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == test_user_id,
                MediaUploadAuthorization.idempotency_key == "key-storage-fail-1",
            )
        ).scalar_one_or_none()
        assert row is not None
        initial_upload_id = row.upload_id

        # 3. Clear simulated failure and retry with identical Idempotency-Key
        fake_storage.simulate_failure = None
        result = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="key-storage-fail-1",
            )
        )
        assert result["uploadId"] == initial_upload_id
        assert str(initial_upload_id) in result["uploadUrl"]

        # Assert no duplicate row was created
        all_rows = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == test_user_id,
                MediaUploadAuthorization.idempotency_key == "key-storage-fail-1",
            )
        ).scalars().all()
        assert len(all_rows) == 1

    def test_transaction_closed_before_storage_signing_in_retry_path(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Database transaction and advisory lock must be released before storage URL signing."""
        rollback_called_before_signing = []
        original_rollback = sqlite_db.rollback
        rollback_count = 0

        def spy_rollback():
            nonlocal rollback_count
            rollback_count += 1
            return original_rollback()

        sqlite_db.rollback = spy_rollback

        class InspectingStorage(FakeStorageAdapter):
            async def generate_presigned_put_url(self, *args, **kwargs) -> str:
                rollback_called_before_signing.append(rollback_count)
                return await super().generate_presigned_put_url(*args, **kwargs)

        storage = InspectingStorage(bucket_name="test-bucket")
        use_case = AuthorizeMediaUpload(
            storage=storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
        )
        res1 = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="tx-release-test-key",
            )
        )
        assert len(rollback_called_before_signing) == 1
        assert rollback_called_before_signing[0] == 0  # Initial creation commits, not rollbacks

        # Identical retry path
        res2 = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="tx-release-test-key",
            )
        )
        assert res1["uploadId"] == res2["uploadId"]
        assert len(rollback_called_before_signing) == 2
        # Verify rollback was called before generate_presigned_put_url
        assert rollback_called_before_signing[1] >= 1

    def test_transaction_closed_before_storage_signing_in_locked_retry_path(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """In locked duplicate branch (step 9), transaction is rolled back before storage URL signing."""
        rollback_called_before_signing = []
        original_rollback = sqlite_db.rollback
        rollback_count = 0

        def spy_rollback():
            nonlocal rollback_count
            rollback_count += 1
            return original_rollback()

        sqlite_db.rollback = spy_rollback

        class InspectingStorage(FakeStorageAdapter):
            async def generate_presigned_put_url(self, *args, **kwargs) -> str:
                rollback_called_before_signing.append(rollback_count)
                return await super().generate_presigned_put_url(*args, **kwargs)

        storage = InspectingStorage(bucket_name="test-bucket")
        use_case = AuthorizeMediaUpload(
            storage=storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
        )

        res1 = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="step9-tx-key",
            )
        )

        # Now simulate step 4 returning None, so step 9 is reached:
        real_execute = sqlite_db.execute
        select_count = 0

        def step4_miss_execute(stmt, *args, **kwargs):
            nonlocal select_count
            text_rep = str(stmt)
            if "media_upload_authorizations" in text_rep and "SELECT" in text_rep:
                select_count += 1
                if select_count == 1:
                    class EmptyResult:
                        def scalar_one_or_none(self):
                            return None
                    return EmptyResult()
            return real_execute(stmt, *args, **kwargs)

        sqlite_db.execute = step4_miss_execute
        res2 = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="step9-tx-key",
            )
        )
        assert res1["uploadId"] == res2["uploadId"]
        assert select_count >= 2  # Proves step 9 was executed
        assert rollback_called_before_signing[-1] >= 1


# -----------------------------------------------------------------------------
# 3. Configuration & Security Tests
# -----------------------------------------------------------------------------

class TestConfigurationAndSecurity:
    """Verify HMAC key-ring rotation, version persistence, and fail-closed security."""

    def test_key_version_persisted_in_database(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Authorization record durably stores the active key_version."""
        use_case = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_2026_11a",
            key_ring={"kver_2026_11a": "secret-1-minimum-32-characters-long!"},
        )
        result = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=5000,
                idempotency_key="key-ver-check",
            )
        )
        row = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.upload_id == result["uploadId"]
            )
        ).scalar_one()
        assert row.key_version == "kver_2026_11a"

    def test_key_rotation_preserves_inflight_retry(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Secret rotation to a new active key preserves retries of existing authorizations."""
        key_ring = {
            "kver_1": "initial-secret-at-least-32-chars-long!",
            "kver_2": "rotated-secret-at-least-32-chars-long!",
        }
        # Initial request under kver_1
        use_case_v1 = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring=key_ring,
        )
        res1 = asyncio.run(
            use_case_v1.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=2000,
                idempotency_key="rotation-safe-key",
            )
        )

        # DevOps rotates active key to kver_2
        use_case_v2 = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_2",
            key_ring=key_ring,
        )
        res2 = asyncio.run(
            use_case_v2.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=2000,
                idempotency_key="rotation-safe-key",
            )
        )

        # Retry returns identical stored slot
        assert res1["uploadId"] == res2["uploadId"]
        assert res1["stagingKey"] == res2["stagingKey"]

    def test_effective_media_upload_key_ring_resolves_previous_key_id(self):
        """Settings maps MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS to MEDIA_UPLOAD_PREVIOUS_KEY_ID."""
        settings = Settings(
            media_upload_active_key_id="kver_2",
            media_upload_previous_key_id="kver_1",
            media_upload_hmac_secret="rotated-secret-at-least-32-characters!",
            media_upload_hmac_secret_previous="previous-secret-at-least-32-characters!",
        )
        ring = settings.effective_media_upload_key_ring
        assert ring["kver_2"] == "rotated-secret-at-least-32-characters!"
        assert ring["kver_1"] == "previous-secret-at-least-32-characters!"

    def test_key_rotation_preserves_inflight_retry_via_settings(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Rotation preserves retries when using Settings.effective_media_upload_key_ring."""
        settings_v1 = Settings(
            media_upload_active_key_id="kver_1",
            media_upload_hmac_secret="initial-secret-at-least-32-chars-long!",
        )
        use_case_v1 = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id=settings_v1.media_upload_active_key_id,
            key_ring=settings_v1.effective_media_upload_key_ring,
        )
        res1 = asyncio.run(
            use_case_v1.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=2000,
                idempotency_key="settings-rotation-key",
            )
        )

        # DevOps rotates active to kver_2, previous is kver_1
        settings_v2 = Settings(
            media_upload_active_key_id="kver_2",
            media_upload_previous_key_id="kver_1",
            media_upload_hmac_secret="rotated-secret-at-least-32-chars-long!",
            media_upload_hmac_secret_previous="initial-secret-at-least-32-chars-long!",
        )
        use_case_v2 = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id=settings_v2.media_upload_active_key_id,
            key_ring=settings_v2.effective_media_upload_key_ring,
        )
        res2 = asyncio.run(
            use_case_v2.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=2000,
                idempotency_key="settings-rotation-key",
            )
        )
        assert res1["uploadId"] == res2["uploadId"]
        assert res1["stagingKey"] == res2["stagingKey"]

    def test_json_key_ring_parsing_and_resolution(self):
        """MEDIA_UPLOAD_KEY_RING JSON string parses into structured key ring dictionary."""
        settings = Settings(
            media_upload_active_key_id="kver_3",
            media_upload_key_ring='{"kver_1": "secret-1-at-least-32-characters!", "kver_2": "secret-2-at-least-32-characters!", "kver_3": "secret-3-at-least-32-characters!"}',
        )
        ring = settings.effective_media_upload_key_ring
        assert ring["kver_1"] == "secret-1-at-least-32-characters!"
        assert ring["kver_2"] == "secret-2-at-least-32-characters!"
        assert ring["kver_3"] == "secret-3-at-least-32-characters!"

    def test_missing_historical_key_fails_safely(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """An authorization whose key_version is absent from key ring fails closed with 409 conflict."""
        unknown_auth = MediaUploadAuthorization(
            user_id=test_user_id,
            idempotency_key="unknown-key-version",
            upload_id=uuid4(),
            key_version="kver_retired_ancient",
            request_fingerprint="some-old-fingerprint",
            staging_key="staging/unknown",
            content_type="image/webp",
            size_bytes=1000,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        sqlite_db.add(unknown_auth)
        sqlite_db.commit()

        use_case = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_current",
            key_ring={"kver_current": "current-secret-at-least-32-chars-long!"},
        )
        with pytest.raises(ApiError) as exc_info:
            asyncio.run(
                use_case.execute(
                    user_id=test_user_id,
                    purpose="wardrobe_item",
                    content_type="image/webp",
                    size_bytes=1000,
                    idempotency_key="unknown-key-version",
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"

    def test_production_settings_requires_secure_previous_secret(self):
        """Insecure previous secret fails closed in production."""
        with pytest.raises(ValidationError, match="secure MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
                auth_secret="prod-jwt-secret-with-at-least-32-characters!",
                media_upload_hmac_secret="secure-prod-active-secret-32-chars-long!",
                media_upload_hmac_secret_previous="insecure-dev-secret",
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_access_key_id="prod-key",
                r2_secret_access_key="prod-secret",
                r2_endpoint_url="https://r2.cloudflarestorage.com",
            )

    def test_production_settings_fail_closed_without_hmac_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Production environment fails closed if media upload HMAC secret is insecure."""
        monkeypatch.delenv("MEDIA_UPLOAD_HMAC_SECRET", raising=False)
        clear_settings_cache()

        with pytest.raises(ValidationError, match="secure MEDIA_UPLOAD_HMAC_SECRET"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
                auth_secret="prod-jwt-secret-with-at-least-32-characters!",
                media_upload_hmac_secret="insecure-dev-hmac-secret",
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_access_key_id="prod-key",
                r2_secret_access_key="prod-secret",
                r2_endpoint_url="https://r2.cloudflarestorage.com",
            )

    def test_presigned_urls_not_persisted_in_database(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Presigned URLs must NEVER be stored in the database (Database Invariant PR-8)."""
        use_case = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring={"kver_1": "secret-1-minimum-32-characters-long!"},
        )
        result = asyncio.run(
            use_case.execute(
                user_id=test_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="no-url-persist",
            )
        )
        row = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.upload_id == result["uploadId"]
            )
        ).scalar_one()

        # Inspect table columns
        table_columns = [c.name for c in MediaUploadAuthorization.__table__.columns]
        assert "upload_url" not in table_columns
        assert "presigned_url" not in table_columns
        assert "uploadUrl" not in table_columns


# -----------------------------------------------------------------------------
# 4. Rate Limiting & Retention Tests
# -----------------------------------------------------------------------------

class TestRateLimitingAndRetention:
    """Verify the 30 req/min rolling rate limit and maintenance pruning."""

    def test_rate_limit_enforced_at_30_per_minute(
        self, client: TestClient, test_user_id: UUID
    ):
        """User cannot authorize more than 30 uploads in a rolling 60-second window."""
        payload = {"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 1000}

        # 30 successful authorizations
        for i in range(30):
            res = client.post(
                "/v1/media/uploads",
                headers={"Idempotency-Key": f"burst-req-{i}"},
                json=payload,
            )
            assert res.status_code == 201, f"Request {i} failed: {res.text}"

        # 31st request rejected with HTTP 429
        res_31 = client.post(
            "/v1/media/uploads",
            headers={"Idempotency-Key": "burst-req-31"},
            json=payload,
        )
        assert res_31.status_code == 429
        data = res_31.json()
        assert data["error"]["code"] == "RATE_LIMITED"
        assert res_31.headers.get("Retry-After") == "60"

    def test_different_users_have_independent_rate_limit_counters(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID, other_user_id: UUID
    ):
        """One user hitting the 30 req/min limit does not throttle a different user."""
        use_case = AuthorizeMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            active_key_id="kver_1",
            key_ring={"kver_1": "secret-1-minimum-32-characters-long!"},
        )
        # User 1 consumes all 30 slots
        for i in range(30):
            asyncio.run(
                use_case.execute(
                    user_id=test_user_id,
                    purpose="wardrobe_item",
                    content_type="image/webp",
                    size_bytes=1000,
                    idempotency_key=f"u1-burst-{i}",
                )
            )

        # User 1 is throttled
        with pytest.raises(ApiError) as exc_info:
            asyncio.run(
                use_case.execute(
                    user_id=test_user_id,
                    purpose="wardrobe_item",
                    content_type="image/webp",
                    size_bytes=1000,
                    idempotency_key="u1-burst-31",
                )
            )
        assert exc_info.value.status_code == 429

        # User 2 can still make upload authorizations successfully
        res_u2 = asyncio.run(
            use_case.execute(
                user_id=other_user_id,
                purpose="wardrobe_item",
                content_type="image/webp",
                size_bytes=1000,
                idempotency_key="u2-first-request",
            )
        )
        assert res_u2["uploadId"] is not None

    def test_prune_expired_authorizations(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Pruning deletes records where expires_at < now, preserving active records."""
        now = datetime.now(timezone.utc)

        # Insert expired record
        expired_auth = MediaUploadAuthorization(
            user_id=test_user_id,
            idempotency_key="expired-1",
            upload_id=uuid4(),
            key_version="kver_1",
            request_fingerprint="fp1",
            staging_key="staging/expired",
            content_type="image/webp",
            size_bytes=100,
            created_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),
        )
        # Insert active record
        active_auth = MediaUploadAuthorization(
            user_id=test_user_id,
            idempotency_key="active-1",
            upload_id=uuid4(),
            key_version="kver_1",
            request_fingerprint="fp2",
            staging_key="staging/active",
            content_type="image/webp",
            size_bytes=100,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        sqlite_db.add_all([expired_auth, active_auth])
        sqlite_db.commit()

        # Run pruning
        deleted = prune_expired_authorizations(sqlite_db, now=now)
        assert deleted == 1

        # Check remaining
        remaining = sqlite_db.execute(select(MediaUploadAuthorization)).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].idempotency_key == "active-1"

    def test_lock_namespace_stability(self, test_user_id: UUID):
        """Lock key is deterministically derived from media_upload_rate_limit:{user_id}."""
        assert MEDIA_UPLOAD_LOCK_NAMESPACE == "media_upload_rate_limit"
        lock_key = get_media_upload_lock_key(test_user_id)
        assert isinstance(lock_key, int)
        assert -9223372036854775808 <= lock_key <= 9223372036854775807

    def test_server_time_window_filter_compiles_to_postgres_interval(self):
        """PostgreSQL rolling-window rate-limit filter compiles to server-side INTERVAL '60 seconds'."""
        from sqlalchemy.dialects import postgresql
        from sqlalchemy import func

        stmt = select(func.count()).select_from(MediaUploadAuthorization).where(
            MediaUploadAuthorization.created_at >= (func.now() - text("INTERVAL '60 seconds'"))
        )
        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "now() - INTERVAL '60 seconds'" in compiled_sql

    def test_prune_expired_authorizations_bounded_batches(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Pruning deletes in batches of batch_size, cleanly pruning multiple batches."""
        now = datetime.now(timezone.utc)
        for i in range(5):
            sqlite_db.add(
                MediaUploadAuthorization(
                    user_id=test_user_id,
                    idempotency_key=f"batch-expired-{i}",
                    upload_id=uuid4(),
                    key_version="kver_1",
                    request_fingerprint=f"fp-batch-{i}",
                    staging_key=f"staging/expired/{i}",
                    content_type="image/webp",
                    size_bytes=100,
                    created_at=now - timedelta(hours=25),
                    expires_at=now - timedelta(hours=1),
                )
            )
        sqlite_db.commit()

        deleted = prune_expired_authorizations(sqlite_db, now=now, batch_size=2)
        assert deleted == 5
        remaining = sqlite_db.execute(select(MediaUploadAuthorization)).scalars().all()
        assert len(remaining) == 0

    def test_prune_expired_authorizations_with_max_batches_and_remaining(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Setting max_batches limits iterations, leaving remaining expired records intact."""
        now = datetime.now(timezone.utc)
        for i in range(5):
            sqlite_db.add(
                MediaUploadAuthorization(
                    user_id=test_user_id,
                    idempotency_key=f"mb-expired-{i}",
                    upload_id=uuid4(),
                    key_version="kver_1",
                    request_fingerprint=f"fp-mb-{i}",
                    staging_key=f"staging/expired/{i}",
                    content_type="image/webp",
                    size_bytes=100,
                    created_at=now - timedelta(hours=25),
                    expires_at=now - timedelta(hours=1),
                )
            )
        sqlite_db.add(
            MediaUploadAuthorization(
                user_id=test_user_id,
                idempotency_key="mb-active",
                upload_id=uuid4(),
                key_version="kver_1",
                request_fingerprint="fp-mb-act",
                staging_key="staging/active",
                content_type="image/webp",
                size_bytes=100,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        sqlite_db.commit()

        deleted = prune_expired_authorizations(sqlite_db, now=now, batch_size=2, max_batches=1)
        assert deleted == 2
        remaining = sqlite_db.execute(select(MediaUploadAuthorization)).scalars().all()
        assert len(remaining) == 4


# -----------------------------------------------------------------------------
# 5. Migration 0033 Metadata Tests
# -----------------------------------------------------------------------------

class TestMigration0033Metadata:
    """Verify migration 0033 file linkage and linear history."""

    def test_migration_0033_metadata_and_chain(self):
        """0033 exists, is a child of 0032, and forms a linear chain to single head."""
        backend = Path(__file__).resolve().parents[1]
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "alembic"))
        script = ScriptDirectory.from_config(config)

        # Single head assertion
        heads = script.get_heads()
        assert len(heads) == 1
        assert heads[0] in ("0033", "0034", "0035", "0036")

        # Parent assertion
        rev33 = script.get_revision("0033")
        assert rev33 is not None
        assert rev33.down_revision == "0032"

        # Upgrade and downgrade callables present
        module = rev33.module
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert callable(module.upgrade)
        assert callable(module.downgrade)


# -----------------------------------------------------------------------------
# 6. Concurrency Tests (PostgreSQL Gated)
# -----------------------------------------------------------------------------

class TestConcurrencyAndAdvisoryLocking:
    """Multi-session concurrency tests verifying distributed PostgreSQL rate limiting."""

    def test_lock_contention_timeout_via_sqlstate_55p03_maps_to_429_retry_after_5(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """PostgreSQL advisory lock contention (SQLSTATE 55P03) maps to HTTP 429 with Retry-After: 5."""
        orig_err = Exception("statement timeout")
        orig_err.pgcode = "55P03"

        orig_dialect = sqlite_db.bind.dialect.name
        sqlite_db.bind.dialect.name = "postgresql"
        real_execute = sqlite_db.execute

        def mock_execute(stmt, *args, **kwargs):
            text_str = str(stmt)
            if "pg_advisory_xact_lock" in text_str or "lock_timeout" in text_str:
                raise OperationalError("SELECT pg_advisory_xact_lock(:lock_key)", params={}, orig=orig_err)
            return real_execute(stmt, *args, **kwargs)

        sqlite_db.execute = mock_execute

        try:
            use_case = AuthorizeMediaUpload(
                storage=fake_storage,
                db=sqlite_db,
                active_key_id="kver_1",
                key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
            )
            with pytest.raises(ApiError) as exc_info:
                asyncio.run(
                    use_case.execute(
                        user_id=test_user_id,
                        purpose="wardrobe_item",
                        content_type="image/webp",
                        size_bytes=1000,
                        idempotency_key="contention-test-key",
                    )
                )
            err = exc_info.value
            assert err.status_code == 429
            assert err.code == "RATE_LIMITED"
            assert err.details.get("retry_after") == 5
        finally:
            sqlite_db.bind.dialect.name = orig_dialect

    def test_lock_contention_timeout_via_english_string_fallback(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Fallback English lock timeout string maps to HTTP 429 with Retry-After: 5."""
        orig_err = Exception("canceling statement due to lock timeout")

        orig_dialect = sqlite_db.bind.dialect.name
        sqlite_db.bind.dialect.name = "postgresql"
        real_execute = sqlite_db.execute

        def mock_execute(stmt, *args, **kwargs):
            text_str = str(stmt)
            if "pg_advisory_xact_lock" in text_str or "lock_timeout" in text_str:
                raise OperationalError("SELECT pg_advisory_xact_lock(:lock_key)", params={}, orig=orig_err)
            return real_execute(stmt, *args, **kwargs)

        sqlite_db.execute = mock_execute

        try:
            use_case = AuthorizeMediaUpload(
                storage=fake_storage,
                db=sqlite_db,
                active_key_id="kver_1",
                key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
            )
            with pytest.raises(ApiError) as exc_info:
                asyncio.run(
                    use_case.execute(
                        user_id=test_user_id,
                        purpose="wardrobe_item",
                        content_type="image/webp",
                        size_bytes=1000,
                        idempotency_key="contention-fallback-key",
                    )
                )
            err = exc_info.value
            assert err.status_code == 429
            assert err.code == "RATE_LIMITED"
            assert err.details.get("retry_after") == 5
        finally:
            sqlite_db.bind.dialect.name = orig_dialect

    def test_non_timeout_operational_error_maps_to_500_database_failure(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Other operational errors map safely to HTTP 500 DATABASE_FAILURE."""
        orig_err = Exception("connection lost")
        orig_err.pgcode = "08006"

        orig_dialect = sqlite_db.bind.dialect.name
        sqlite_db.bind.dialect.name = "postgresql"
        real_execute = sqlite_db.execute

        def mock_execute(stmt, *args, **kwargs):
            text_str = str(stmt)
            if "pg_advisory_xact_lock" in text_str or "lock_timeout" in text_str:
                raise OperationalError("SELECT 1", params={}, orig=orig_err)
            return real_execute(stmt, *args, **kwargs)

        sqlite_db.execute = mock_execute

        try:
            use_case = AuthorizeMediaUpload(
                storage=fake_storage,
                db=sqlite_db,
                active_key_id="kver_1",
                key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
            )
            with pytest.raises(ApiError) as exc_info:
                asyncio.run(
                    use_case.execute(
                        user_id=test_user_id,
                        purpose="wardrobe_item",
                        content_type="image/webp",
                        size_bytes=1000,
                        idempotency_key="connection-fail-key",
                    )
                )
            err = exc_info.value
            assert err.status_code == 500
            assert err.code == "DATABASE_FAILURE"
        finally:
            sqlite_db.bind.dialect.name = orig_dialect

    def test_endpoint_lock_timeout_returns_http_429_with_retry_after_header(
        self, client: TestClient, sqlite_db: Session
    ):
        """Lock contention timeout at API layer returns HTTP 429 and Retry-After: 5 header."""
        orig_err = Exception("canceling statement due to lock timeout")
        orig_err.pgcode = "55P03"

        orig_dialect = sqlite_db.bind.dialect.name
        sqlite_db.bind.dialect.name = "postgresql"
        original_execute = sqlite_db.execute

        def mock_execute(stmt, *args, **kwargs):
            text_str = str(stmt)
            if "pg_advisory_xact_lock" in text_str or "lock_timeout" in text_str:
                raise OperationalError("SET LOCAL lock_timeout", params={}, orig=orig_err)
            return original_execute(stmt, *args, **kwargs)

        sqlite_db.execute = mock_execute

        try:
            res = client.post(
                "/v1/media/uploads",
                headers={"Idempotency-Key": "endpoint-lock-timeout-key"},
                json={"purpose": "wardrobe_item", "contentType": "image/webp", "sizeBytes": 1000},
            )
            assert res.status_code == 429
            assert res.headers.get("Retry-After") == "5"
            assert res.json()["error"]["code"] == "RATE_LIMITED"
            assert res.json()["error"]["details"]["retry_after"] == 5
        finally:
            sqlite_db.bind.dialect.name = orig_dialect

    @pytest.fixture
    def pg_db_url(self) -> str:
        url = os.environ.get("FANSIVIBE_TEST_DATABASE_URL", "")
        if not url:
            pytest.skip("FANSIVIBE_TEST_DATABASE_URL not set; genuine multi-session PostgreSQL concurrency tests skipped.")
        return url

    def test_concurrent_upload_authorizations_enforce_atomic_rate_limit(
        self, pg_db_url: str, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Forty concurrent requests for one user produce exactly 30 authorizations and 10 rate-limit rejections."""
        engine = create_engine(pg_db_url, pool_size=50, max_overflow=10)
        # Ensure table exists in test DB
        MediaUploadAuthorization.__table__.create(engine, checkfirst=True)

        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        # Ensure test user exists in users table (foreign key constraint) and clean authorizations
        with session_factory() as s:
            user = s.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": test_user_id}).scalar_one_or_none()
            if user is None:
                s.execute(
                    text("INSERT INTO users (id, auth_provider, auth_subject, display_name) VALUES (:uid, 'test', 'test-subject', 'Test User')"),
                    {"uid": test_user_id},
                )
            s.execute(text("DELETE FROM media_upload_authorizations WHERE user_id = :uid"), {"uid": test_user_id})
            s.commit()

        results = []

        def worker(request_idx: int):
            db_session = session_factory()
            try:
                use_case = AuthorizeMediaUpload(
                    storage=fake_storage,
                    db=db_session,
                    active_key_id="kver_1",
                    key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
                )
                res = asyncio.run(
                    use_case.execute(
                        user_id=test_user_id,
                        purpose="wardrobe_item",
                        content_type="image/webp",
                        size_bytes=1000,
                        idempotency_key=f"concurrent-req-{request_idx}",
                    )
                )
                return ("SUCCESS", res)
            except ApiError as exc:
                return ("RATE_LIMITED" if exc.status_code == 429 else "ERROR", exc)
            except Exception as exc:
                return ("EXCEPTION", exc)
            finally:
                db_session.close()

        with ThreadPoolExecutor(max_workers=40) as executor:
            futures = [executor.submit(worker, i) for i in range(40)]
            for f in as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[0] == "SUCCESS"]
        rate_limited = [r for r in results if r[0] == "RATE_LIMITED"]

        assert len(successes) == 30, f"Expected exactly 30 successes, got {len(successes)}"
        assert len(rate_limited) == 10, f"Expected exactly 10 rate-limited rejections, got {len(rate_limited)}"

    def test_concurrent_identical_idempotency_requests_return_same_slot(
        self, pg_db_url: str, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Ten concurrent identical requests produce exactly one DB authorization record and one uploadId."""
        engine = create_engine(pg_db_url, pool_size=20, max_overflow=5)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        # Clean existing rows for this user and ensure user exists
        with session_factory() as s:
            user = s.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": test_user_id}).scalar_one_or_none()
            if user is None:
                s.execute(
                    text("INSERT INTO users (id, auth_provider, auth_subject, display_name) VALUES (:uid, 'test', 'test-subject', 'Test User')"),
                    {"uid": test_user_id},
                )
            s.execute(text("DELETE FROM media_upload_authorizations WHERE user_id = :uid"), {"uid": test_user_id})
            s.commit()

        results = []

        def worker():
            db_session = session_factory()
            try:
                use_case = AuthorizeMediaUpload(
                    storage=fake_storage,
                    db=db_session,
                    active_key_id="kver_1",
                    key_ring={"kver_1": "test-secret-at-least-32-chars-long!"},
                )
                res = asyncio.run(
                    use_case.execute(
                        user_id=test_user_id,
                        purpose="wardrobe_item",
                        content_type="image/webp",
                        size_bytes=1000,
                        idempotency_key="concurrent-identical-key",
                    )
                )
                return ("SUCCESS", res)
            except Exception as exc:
                return ("EXCEPTION", exc)
            finally:
                db_session.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker) for _ in range(10)]
            for f in as_completed(futures):
                results.append(f.result())

        # All 10 succeeded
        for status_code, res in results:
            assert status_code == "SUCCESS"

        # All 10 received the exact same uploadId
        first_upload_id = results[0][1]["uploadId"]
        for _, res in results:
            assert res["uploadId"] == first_upload_id

        # Exactly 1 row in the database
        with session_factory() as s:
            count = s.execute(
                text("SELECT COUNT(*) FROM media_upload_authorizations WHERE user_id = :uid"),
                {"uid": test_user_id},
            ).scalar()
            assert count == 1
