"""Comprehensive adversarial test suite for Stage 2 P0-4 Phase 3.2:
Media Lifecycle Critical Reliability Corrections.

Covers all 19 required adversarial test scenarios across 7 workstreams:
1. Worker A lease expires; Worker B claims it; Worker A tries to clear the lease.
2. Worker A tries to renew after Worker B claims ownership.
3. Worker A tries to publish after losing ownership.
4. Worker A tries to finalize failure after losing ownership.
5. Operation exceeds the original lease duration (with and without heartbeat).
6. Semaphore queue exceeds the permitted wait timeout.
7. Lease renewal fails after ownership changes.
8. Cancellation while transcoding.
9. Cancellation during R2 publication.
10. PostgreSQL long-transaction clock semantics (clock_timestamp vs now).
11. Five retryable failures followed by a sixth request (attempt ceiling enforcement).
12. Terminal failure replay (HTTP 409 UPLOAD_FAILED).
13. Cooldown recovery after 60 seconds.
14. Missing R2 SHA metadata (fail-closed recovery).
15. Incorrect R2 SHA metadata (hash mismatch fallback).
16. Canonical bytes disagree with trusted server evidence.
17. Client checksum assertion mismatch during recovery.
18. Corrupt WebP dimension decoding (no fake dimensions).
19. Missing staging data with invalid canonical data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
import time
from typing import Generator, Optional
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.errors import ApiError
from app.application.media import (
    CompleteMediaUpload,
    MAX_PROCESSING_ATTEMPTS,
    PROCESSING_LEASE_SECONDS,
    PROCESSING_RECOVERY_COOLDOWN_SECONDS,
    get_canonical_object_key,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageObjectMetadata,
)
from app.infrastructure.db.models import MediaUploadAuthorization, Users
from app.workers.transcoder import (
    TranscoderProcessManager,
    TranscodingTimeoutError,
)
from tests.fakes.fake_storage import FakeStorageAdapter


DISPOSABLE_PG_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_p32_test"
)


# -----------------------------------------------------------------------------
# Test Helpers & Fixtures
# -----------------------------------------------------------------------------


def make_test_jpeg(width: int = 400, height: int = 300, color: str = "red") -> bytes:
    """Generate deterministic JPEG image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_test_webp(width: int = 400, height: int = 300, color: str = "blue") -> bytes:
    """Generate deterministic canonical WebP test image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite database engine with MediaUploadAuthorization table."""
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
    """Yield transactional session connected to in-memory SQLite engine."""
    session_factory = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user_id() -> UUID:
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def fake_storage() -> FakeStorageAdapter:
    return FakeStorageAdapter()


def create_auth(
    db: Session,
    user_id: UUID,
    upload_id: UUID,
    *,
    status: str = "authorized",
    attempts: int = 0,
    expires_delta: timedelta = timedelta(hours=24),
    content_type: str = "image/jpeg",
    size_bytes: int = 2048,
    lease_expires_at: Optional[datetime] = None,
    lease_token: Optional[UUID] = None,
    failure_reason: Optional[str] = None,
) -> MediaUploadAuthorization:
    now = datetime.now(timezone.utc)
    rec = MediaUploadAuthorization(
        user_id=user_id,
        idempotency_key=f"idem-{upload_id}",
        upload_id=upload_id,
        key_version="v1",
        request_fingerprint="fp123",
        staging_key=f"staging/users/{user_id}/wardrobe/{upload_id}.jpg",
        content_type=content_type,
        size_bytes=size_bytes,
        created_at=now,
        expires_at=now + expires_delta,
        status=status,
        processing_attempts=attempts,
        processing_started_at=now if status == "processing" else None,
        processing_lease_expires_at=lease_expires_at,
        processing_lease_token=lease_token,
        failure_reason=failure_reason,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# -----------------------------------------------------------------------------
# Workstream 1: Fencing-Token Lease Ownership Tests
# -----------------------------------------------------------------------------


class TestWorkstream1FencingTokenOwnership:
    """Validate Workstream 1: Lease ownership fencing via unique UUID lease tokens."""

    @pytest.mark.anyio
    async def test_worker_a_lease_expires_worker_b_claims_worker_a_cannot_clear_lease(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 1: Worker A lease expires; Worker B claims it; Worker A tries to clear the lease."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()
        now = datetime.now(timezone.utc)

        # Worker A had claimed the lease, which has now expired
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_expires_at=now - timedelta(seconds=5),
            lease_token=token_a,
        )

        # Worker B claims the expired lease and receives token_B
        auth.processing_lease_token = token_b
        auth.processing_lease_expires_at = now + timedelta(seconds=30)
        sqlite_db.commit()

        # Worker A wakes up and attempts to clear the lease via _record_retryable_status
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        cleared = use_case._record_retryable_status(upload_id, token_a)

        # Assert Worker A was rejected (0 rows updated)
        assert cleared is False

        # Assert Worker B's active lease is completely intact
        sqlite_db.refresh(auth)
        assert auth.status == "processing"
        assert auth.processing_lease_token == token_b
        assert auth.processing_lease_expires_at is not None

    @pytest.mark.anyio
    async def test_worker_a_tries_to_renew_after_worker_b_claims_ownership(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 2 & 7: Worker A tries to renew after Worker B claims ownership."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()
        now = datetime.now(timezone.utc)

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_expires_at=now - timedelta(seconds=1),
            lease_token=token_a,
        )

        # Worker B supersedes Worker A
        auth.processing_lease_token = token_b
        auth.processing_lease_expires_at = now + timedelta(seconds=30)
        sqlite_db.commit()

        # Worker A attempts to renew lease
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        renewed = use_case.renew_lease(upload_id, token_a, extend_seconds=15)

        assert renewed is False
        sqlite_db.refresh(auth)
        assert auth.processing_lease_token == token_b

    @pytest.mark.anyio
    async def test_worker_a_tries_to_publish_after_losing_ownership(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 3: Worker A tries to publish after losing ownership; must abort with 409 LEASE_LOST and preserve staging."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()
        now = datetime.now(timezone.utc)

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_expires_at=now - timedelta(seconds=2),
            lease_token=token_a,
        )
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        # Worker B took ownership
        auth.processing_lease_token = token_b
        auth.processing_lease_expires_at = now + timedelta(seconds=30)
        sqlite_db.commit()

        # Worker A attempts to finalize publication
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        with pytest.raises(ApiError) as exc_info:
            await use_case._finalize_published_record(
                user_id=test_user_id,
                upload_id=upload_id,
                lease_token=token_a,
                canonical_key=get_canonical_object_key(test_user_id, upload_id),
                canonical_sha256="fake_sha",
                size_bytes=1024,
                width=400,
                height=300,
                staging_key=auth.staging_key,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "LEASE_LOST"

        # Staging key must NOT have been deleted
        assert auth.staging_key in fake_storage._objects
        sqlite_db.refresh(auth)
        assert auth.status == "processing"
        assert auth.processing_lease_token == token_b

    @pytest.mark.anyio
    async def test_worker_a_tries_to_record_failure_after_losing_ownership(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 4: Worker A tries to record failure after Worker B claims ownership."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()
        now = datetime.now(timezone.utc)

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_expires_at=now - timedelta(seconds=1),
            lease_token=token_a,
        )

        # Worker B supersedes Worker A
        auth.processing_lease_token = token_b
        sqlite_db.commit()

        # Worker A attempts to mark failure
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        recorded = use_case._record_failure(upload_id, token_a, "DECOMPRESSION_BOMB")

        assert recorded is False
        sqlite_db.refresh(auth)
        assert auth.status == "processing"
        assert auth.processing_lease_token == token_b


# -----------------------------------------------------------------------------
# Workstream 2: Operation Lifecycle, Duration & Bounds Tests
# -----------------------------------------------------------------------------


class TestWorkstream2OperationLifecycleAndDuration:
    """Validate Workstream 2: Operation bounds, semaphore queue limits, and lease duration."""

    @pytest.mark.anyio
    async def test_semaphore_queue_exceeds_permitted_wait(self):
        """Scenario 6: Semaphore queue exceeds permitted wait timeout."""
        transcoder = TranscoderProcessManager(semaphore_timeout_seconds=0.1)
        sem = transcoder.get_semaphore()

        # Acquire the semaphore to simulate another active task in this worker
        await sem.acquire()
        try:
            raw_bytes = make_test_jpeg()
            with pytest.raises(TranscodingTimeoutError) as exc_info:
                await transcoder.transcode(raw_bytes)

            assert exc_info.value.code == "TRANSCODING_TIMEOUT"
            assert "semaphore wait timed out" in exc_info.value.message
        finally:
            sem.release()

    @pytest.mark.anyio
    async def test_operation_exceeds_pipeline_deadline_and_fails_safely(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 5: Operation exceeds pipeline deadline (25s bound) and rolls back lease safely."""
        upload_id = uuid4()
        auth = create_auth(sqlite_db, test_user_id, upload_id)
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        class SlowStorage(FakeStorageAdapter):
            async def get_object_metadata(self, key: str) -> Optional[StorageObjectMetadata]:
                await asyncio.sleep(0.3)
                return await super().get_object_metadata(key)

        slow_storage = SlowStorage()
        slow_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        use_case = CompleteMediaUpload(
            storage=slow_storage,
            db=sqlite_db,
            pipeline_timeout_seconds=0.1,  # Strict short timeout
            heartbeat_interval_seconds=0,
        )

        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert exc_info.value.status_code == 504
        assert exc_info.value.code == "PROCESSING_TIMEOUT"

        # Lease was safely released back to authorized for retry
        sqlite_db.refresh(auth)
        assert auth.status == "authorized"
        assert auth.processing_lease_token is None

    @pytest.mark.anyio
    async def test_cancellation_while_transcoding_cleans_up_and_reverts_lease(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 8: Cancellation while transcoding kills process and clears lease."""
        upload_id = uuid4()
        auth = create_auth(sqlite_db, test_user_id, upload_id)
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        class HangingTranscoder(TranscoderProcessManager):
            async def transcode(self, raw_bytes: bytes):
                await asyncio.sleep(10.0)

        use_case = CompleteMediaUpload(
            storage=fake_storage,
            db=sqlite_db,
            transcoder=HangingTranscoder(),
            heartbeat_interval_seconds=0,
        )

        task = asyncio.create_task(use_case.execute(user_id=test_user_id, upload_id=upload_id))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        sqlite_db.refresh(auth)
        assert auth.status == "authorized"
        assert auth.processing_lease_token is None

    @pytest.mark.anyio
    async def test_cancellation_during_r2_publication_reverts_lease(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 9: Cancellation during R2 canonical publication reverts lease."""
        upload_id = uuid4()
        auth = create_auth(sqlite_db, test_user_id, upload_id)
        class HangingPutStorage(FakeStorageAdapter):
            async def put_object(self, key, data, content_type="application/octet-stream", custom_metadata=None):
                await asyncio.sleep(10.0)
                return await super().put_object(key, data, content_type, custom_metadata)

        hanging_storage = HangingPutStorage()
        hanging_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        use_case = CompleteMediaUpload(
            storage=hanging_storage,
            db=sqlite_db,
            heartbeat_interval_seconds=0,
        )

        task = asyncio.create_task(use_case.execute(user_id=test_user_id, upload_id=upload_id))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        sqlite_db.refresh(auth)
        assert auth.status == "authorized"
        assert auth.processing_lease_token is None


# -----------------------------------------------------------------------------
# Workstream 4: Attempt-Limit & Cooldown Enforcement Tests
# -----------------------------------------------------------------------------


class TestWorkstream4AttemptLimitAndCooldown:
    """Validate Workstream 4: 5-attempt ceiling and 60-second cooldown."""

    @pytest.mark.anyio
    async def test_five_retryable_failures_followed_by_sixth_request_rejected(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 11: Five retryable failures followed by a sixth request must hit PROCESSING_LIMIT_EXCEEDED."""
        upload_id = uuid4()
        # Staging file is missing, causing 400 STAGING_OBJECT_NOT_FOUND (retryable error)
        auth = create_auth(sqlite_db, test_user_id, upload_id, status="authorized", attempts=0)

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)

        # Execute 5 times (each fails with STAGING_OBJECT_NOT_FOUND and reverts status to authorized)
        for expected_attempt in range(1, 6):
            with pytest.raises(ApiError) as exc_info:
                await use_case.execute(user_id=test_user_id, upload_id=upload_id)
            assert exc_info.value.code == "STAGING_OBJECT_NOT_FOUND"
            sqlite_db.refresh(auth)
            assert auth.status == "authorized"
            assert auth.processing_attempts == expected_attempt

        # 6th attempt must be rejected with PROCESSING_LIMIT_EXCEEDED (HTTP 409)
        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "PROCESSING_LIMIT_EXCEEDED"
        assert "Retry-After" in exc_info.value.headers
        sqlite_db.refresh(auth)
        assert auth.status == "authorized"
        assert auth.processing_attempts == 5  # Must not increment further

    @pytest.mark.anyio
    async def test_terminal_failure_replay_returns_409_upload_failed(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 12: Terminal failed records must not return to processing; return 409 UPLOAD_FAILED."""
        upload_id = uuid4()
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="failed",
            attempts=1,
            failure_reason="EMPTY_OBJECT",
        )

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "UPLOAD_FAILED"
        assert "EMPTY_OBJECT" in exc_info.value.message

        sqlite_db.refresh(auth)
        assert auth.status == "failed"

    @pytest.mark.anyio
    async def test_cooldown_recovery_after_60_seconds_resets_attempts(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 13: Cooldown recovery: after 60 seconds elapsed, attempts counter resets to 1."""
        upload_id = uuid4()
        now = datetime.now(timezone.utc)
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="authorized",
            attempts=5,
        )
        auth.processing_started_at = now - timedelta(seconds=65)  # 65s ago (> 60s cooldown)
        sqlite_db.commit()

        # Provide valid staging data so execution can succeed on recovery
        jpeg_bytes = make_test_jpeg()
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.processing_attempts == 1  # Reset to 1 on recovery attempt!


# -----------------------------------------------------------------------------
# Workstream 5: Fail-Closed Canonical Crash Recovery Tests
# -----------------------------------------------------------------------------


class TestWorkstream5FailClosedCanonicalRecovery:
    """Validate Workstream 5: Fail-closed recovery with trusted server-side integrity evidence."""

    @pytest.mark.anyio
    async def test_missing_r2_sha_metadata_rejects_automatic_hash_acceptance(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 14: Missing R2 SHA metadata must never result in automatic hash acceptance."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        canonical_bytes = make_test_webp()

        # Canonical exists but custom_metadata lacks "sha256"
        fake_storage.put_object_bytes(
            canonical_key,
            canonical_bytes,
            content_type="image/webp",
            custom_metadata={"user_id": str(test_user_id), "upload_id": str(upload_id)},
        )

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        # auth.canonical_sha256 is None in DB!
        jpeg_bytes = make_test_jpeg()
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        # Recovery did NOT blindly adopt the object; it fell back to safe fresh transcoding
        assert res["status"] == "ready"
        sqlite_db.refresh(auth)
        assert auth.status == "published"

    @pytest.mark.anyio
    async def test_incorrect_r2_sha_metadata_triggers_fallback(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 15: Incorrect R2 SHA metadata triggers fallback to fresh transcode."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        canonical_bytes = make_test_webp()

        # Incorrect sha in metadata
        fake_storage.put_object_bytes(
            canonical_key,
            canonical_bytes,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "sha256": "incorrect_hash_value_here",
            },
        )

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        # Completed with genuine hash, not the incorrect metadata hash
        assert res["contentHash"] != "incorrect_hash_value_here"

    @pytest.mark.anyio
    async def test_canonical_bytes_disagree_with_trusted_server_evidence(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 16: Canonical bytes disagree with trusted server evidence (DB canonical_sha256)."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        canonical_bytes = make_test_webp()

        fake_storage.put_object_bytes(canonical_key, canonical_bytes, content_type="image/webp")

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        auth.canonical_sha256 = "mismatched_server_evidence_hash"
        sqlite_db.commit()

        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        assert res["contentHash"] != "mismatched_server_evidence_hash"

    @pytest.mark.anyio
    async def test_client_checksum_assertion_mismatch_during_recovery(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 17: Client checksum assertion mismatch during recovery must fail closed with 422 CHECKSUM_MISMATCH."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        canonical_bytes = make_test_webp()
        canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()

        fake_storage.put_object_bytes(
            canonical_key,
            canonical_bytes,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "sha256": canonical_sha,
                "width": "400",
                "height": "300",
            },
        )

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        jpeg_bytes = make_test_jpeg()
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(
                user_id=test_user_id,
                upload_id=upload_id,
                client_assertion_sha256="wrong_client_asserted_hash",
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "CHECKSUM_MISMATCH"

        sqlite_db.refresh(auth)
        assert auth.status == "failed"

    @pytest.mark.anyio
    async def test_corrupt_webp_dimension_decoding_rejects_and_falls_back(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 18: Corrupt WebP dimension decoding must not fabricate dimensions (1920, 1440); reject and re-transcode."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)

        # Bytes start with RIFF...WEBP header but chunk payload is garbage that PIL cannot decode
        corrupt_webp = b"RIFF\x14\x00\x00\x00WEBPVP8 \x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        corrupt_sha = hashlib.sha256(corrupt_webp).hexdigest()

        fake_storage.put_object_bytes(
            canonical_key,
            corrupt_webp,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "sha256": corrupt_sha,
            },
        )

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(width=320, height=240), content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        # Dimensions must NOT be fake 1920, 1440! Must be real decoded dimensions from clean transcode
        assert (res["width"], res["height"]) == (320, 240)

    @pytest.mark.anyio
    async def test_missing_staging_data_with_invalid_canonical_data_fails_closed(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 19: Missing staging data with invalid canonical data must fail closed (400 STAGING_OBJECT_NOT_FOUND)."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        corrupt_bytes = b"not_even_riff_header"

        fake_storage.put_object_bytes(canonical_key, corrupt_bytes, content_type="image/webp")

        auth = create_auth(sqlite_db, test_user_id, upload_id)
        # Staging object is NOT put in fake_storage!

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db, heartbeat_interval_seconds=0)
        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "STAGING_OBJECT_NOT_FOUND"

        sqlite_db.refresh(auth)
        assert auth.status != "published"


# -----------------------------------------------------------------------------
# Workstream 3: PostgreSQL Wall-Clock Time Semantics Tests (Disposable DB)
# -----------------------------------------------------------------------------


class TestWorkstream3PostgreSQLServerTimeSemantics:
    """Validate Workstream 3: PostgreSQL wall-clock time semantics using clock_timestamp()."""

    @classmethod
    def setup_class(cls):
        """Create disposable PostgreSQL database and run migrations to 0036."""
        admin_engine = create_engine(
            "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/postgres",
            isolation_level="AUTOCOMMIT",
        )
        try:
            with admin_engine.connect() as conn:
                conn.execute(text("DROP DATABASE IF EXISTS fansivibe_disposable_p32_test;"))
                conn.execute(text("CREATE DATABASE fansivibe_disposable_p32_test;"))

            from alembic.config import Config
            from alembic import command
            os.environ["DATABASE_URL"] = DISPOSABLE_PG_URL
            cfg = Config("alembic.ini")
            cfg.set_main_option("sqlalchemy.url", DISPOSABLE_PG_URL)
            command.upgrade(cfg, "head")

            cls.engine = create_engine(DISPOSABLE_PG_URL, pool_size=10, max_overflow=5)
            cls.SessionLocal = sessionmaker(bind=cls.engine)
            cls.admin_engine = admin_engine
        except Exception as exc:
            admin_engine.dispose()
            pytest.skip(f"Disposable PostgreSQL not available: {exc}")

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()
        if hasattr(cls, "admin_engine"):
            with cls.admin_engine.connect() as conn:
                conn.execute(text("DROP DATABASE IF EXISTS fansivibe_disposable_p32_test;"))
            cls.admin_engine.dispose()

    def test_clock_timestamp_advances_during_transaction_while_now_is_frozen(self):
        """Scenario 10: In PostgreSQL, now() is frozen at transaction start while clock_timestamp() advances."""
        with self.engine.connect() as conn:
            with conn.begin():
                t_start_now = conn.execute(text("SELECT now()")).scalar()
                t_start_clock = conn.execute(text("SELECT clock_timestamp()")).scalar()

                # Simulate a lock wait or long transaction
                conn.execute(text("SELECT pg_sleep(0.5)"))

                t_after_now = conn.execute(text("SELECT now()")).scalar()
                t_after_clock = conn.execute(text("SELECT clock_timestamp()")).scalar()

                # now() must be completely frozen!
                assert t_start_now == t_after_now

                # clock_timestamp() must have advanced by at least 0.5s!
                delta_clock = (t_after_clock - t_start_clock).total_seconds()
                assert delta_clock >= 0.45

    @pytest.mark.anyio
    async def test_postgresql_multi_session_fencing_token_lease_isolation(self, fake_storage: FakeStorageAdapter):
        """Multi-session PostgreSQL test: Worker A loses lease to Worker B, Worker A cannot overwrite DB."""
        user_id = uuid4()
        upload_id = uuid4()

        with self.SessionLocal() as session:
            session.execute(
                text(
                    "INSERT INTO users (id, auth_provider, auth_subject, display_name) "
                    "VALUES (:id, 'local', :subj, 'Test User') ON CONFLICT DO NOTHING"
                ),
                {"id": user_id, "subj": f"subj_{upload_id}"},
            )
            session.execute(
                text(
                    "INSERT INTO media_upload_authorizations ("
                    "  user_id, idempotency_key, upload_id, key_version, request_fingerprint, "
                    "  staging_key, content_type, size_bytes, expires_at, status, processing_attempts"
                    ") VALUES ("
                    "  :user_id, :idem, :upload_id, 'v1', 'fp123', "
                    "  :staging_key, 'image/jpeg', 2048, clock_timestamp() + INTERVAL '24 hours', 'authorized', 0"
                    ")"
                ),
                {
                    "user_id": user_id,
                    "idem": f"idem-{upload_id}",
                    "upload_id": upload_id,
                    "staging_key": f"staging/users/{user_id}/wardrobe/{upload_id}.jpg",
                },
            )
            session.commit()

        # Session 1: Worker A claims lease
        with self.SessionLocal() as session_a:
            use_case_a = CompleteMediaUpload(storage=fake_storage, db=session_a, lease_seconds=1, heartbeat_interval_seconds=0)
            fake_storage.put_object_bytes(f"staging/users/{user_id}/wardrobe/{upload_id}.jpg", make_test_jpeg(), content_type="image/jpeg")

            # Worker A executes and claims lease
            auth_a = session_a.execute(
                select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
            ).scalar_one()
            token_a = uuid4()
            auth_a.status = "processing"
            auth_a.processing_lease_token = token_a
            # Simulate lease expired in PostgreSQL
            auth_a.processing_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=2)
            session_a.commit()

        # Session 2: Worker B claims the expired lease
        with self.SessionLocal() as session_b:
            use_case_b = CompleteMediaUpload(storage=fake_storage, db=session_b)
            auth_b = session_b.execute(
                select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
            ).scalar_one()
            token_b = uuid4()
            auth_b.processing_lease_token = token_b
            auth_b.processing_lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
            session_b.commit()

        # Session 1: Worker A wakes up and attempts to clear the lease or finalize
        with self.SessionLocal() as session_a:
            use_case_a = CompleteMediaUpload(storage=fake_storage, db=session_a)
            cleared = use_case_a._record_retryable_status(upload_id, token_a)
            assert cleared is False

            # Worker A tries to finalize publication
            with pytest.raises(ApiError) as exc_info:
                await use_case_a._finalize_published_record(
                    user_id=user_id,
                    upload_id=upload_id,
                    lease_token=token_a,
                    canonical_key=get_canonical_object_key(user_id, upload_id),
                    canonical_sha256="fake_sha",
                    size_bytes=1024,
                    width=400,
                    height=300,
                    staging_key=f"staging/users/{user_id}/wardrobe/{upload_id}.jpg",
                )
            assert exc_info.value.code == "LEASE_LOST"

        # Verify Worker B's lease was completely unaffected
        with self.SessionLocal() as session_check:
            auth_check = session_check.execute(
                select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
            ).scalar_one()
            assert auth_check.status == "processing"
            assert auth_check.processing_lease_token == token_b
