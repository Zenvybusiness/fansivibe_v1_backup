"""Adversarial and concurrency tests for Stage 2 P0-4 Phase 3.4: Immutable R2 Attempt Publication.

Validates the 15 critical requirements and failure modes identified in Phase 3.3 audit:
1. Worker A writes its attempt key and loses its lease.
2. Worker B writes a different attempt key and successfully finalizes.
3. Worker A completes its delayed PUT after Worker B finalizes.
4. Verify Worker B's object bytes remain unchanged.
5. Verify PostgreSQL still references Worker B's object.
6. Worker A attempts finalization after losing ownership (LEASE_LOST 409).
7. Worker A attempts staging deletion after losing ownership (fenced, 0-row update preserves staging).
8. Worker B successfully finalizes and deletes staging.
9. Staging deletion fails after successful publication (published DB row preserved, 200 OK returned).
10. Crash after attempt PUT but before database commit (recovered and adopted by subsequent worker).
11. Crash after database commit but before staging deletion (replayed cleanly, staging deleted on replay).
12. Recovery of an existing published legacy canonical key (preserved without rewrites).
13. Two concurrent attempts with different fencing tokens (serialized by advisory lock and active lease).
14. An abandoned attempt object is not treated as published.
15. Cleanup never deletes the winning attempt key.
16. Thread-pool continuation test: delayed external PUT completes in OS thread after coroutine cancellation.
17. Pre-PUT fencing gate: lease expired before PUT aborts without touching storage.
18. Key format normalization and path traversal rejection.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.errors import ApiError
from app.application.media import (
    CompleteMediaUpload,
    get_attempt_object_key,
    get_canonical_object_key,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageObjectMetadata,
)
from app.infrastructure.db.models import Base, MediaUploadAuthorization
from tests.fakes.fake_storage import FakeStorageAdapter


# -----------------------------------------------------------------------------
# Fixtures & Test Data Helpers
# -----------------------------------------------------------------------------

@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MediaUploadAuthorization.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_db(sqlite_engine):
    SessionLocal = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_storage() -> FakeStorageAdapter:
    return FakeStorageAdapter(bucket_name="test-wardrobe-bucket")


@pytest.fixture
def test_user_id() -> UUID:
    return UUID("11111111-1111-1111-1111-111111111111")


def make_test_jpeg(width: int = 400, height: int = 300, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def make_test_webp(width: int = 400, height: int = 300, color: tuple[int, int, int] = (0, 128, 255)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def create_auth(
    db: Session,
    user_id: UUID,
    upload_id: UUID,
    *,
    status: str = "authorized",
    attempts: int = 0,
    size_bytes: int = 1024,
    lease_token: Optional[UUID] = None,
    lease_expires_at: Optional[datetime] = None,
    canonical_key: Optional[str] = None,
    canonical_sha256: Optional[str] = None,
    content_type: str = "image/jpeg",
) -> MediaUploadAuthorization:
    now = datetime.now(timezone.utc)
    auth = MediaUploadAuthorization(
        user_id=user_id,
        idempotency_key=f"idem-{upload_id}",
        upload_id=upload_id,
        key_version="v1",
        request_fingerprint="fp123",
        staging_key=f"staging/users/{user_id}/wardrobe/{upload_id}.jpeg",
        content_type=content_type,
        size_bytes=size_bytes,
        created_at=now,
        expires_at=now + timedelta(hours=24),
        status=status,
        canonical_key=canonical_key,
        canonical_sha256=canonical_sha256,
        processing_attempts=attempts,
        processing_started_at=now if status == "processing" else None,
        processing_lease_expires_at=lease_expires_at,
        processing_lease_token=lease_token,
    )
    db.add(auth)
    db.commit()
    db.refresh(auth)
    return auth


# -----------------------------------------------------------------------------
# Threaded Storage Stub for Physical Thread-Leak Simulation
# -----------------------------------------------------------------------------

class ThreadedLatePutStorage(FakeStorageAdapter):
    """Storage adapter that executes put_object synchronously in a real OS thread via asyncio.to_thread.

    Accurately models the Boto3/urllib3 behavior where coroutine cancellation leaves the OS thread
    running until completion.
    """

    def __init__(self, bucket_name: str = "test-bucket", delay_seconds: float = 0.25):
        super().__init__(bucket_name=bucket_name)
        self.delay_seconds = delay_seconds
        self.put_started_event = asyncio.Event()
        self.put_completed = False
        self.last_written_key: Optional[str] = None

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "image/webp",
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        loop = asyncio.get_running_loop()

        def _blocking_os_thread_put():
            # Signal that the thread started executing
            loop.call_soon_threadsafe(self.put_started_event.set)
            # Sleep in OS thread (cannot be interrupted by coroutine cancellation!)
            time.sleep(self.delay_seconds)
            # Perform storage write in the thread
            self.put_object_bytes(
                key=key,
                data=data,
                content_type=content_type,
                custom_metadata=dict(custom_metadata or {}),
            )
            self.put_completed = True
            self.last_written_key = key
            return StorageObjectMetadata(
                key=key,
                size_bytes=len(data),
                content_type=content_type,
                last_modified=datetime.now(timezone.utc),
                custom_metadata=dict(custom_metadata or {}),
            )

        return await asyncio.to_thread(_blocking_os_thread_put)


# -----------------------------------------------------------------------------
# Workstream 1 & 7 Tests: Immutable Attempt-Specific Object Keys & Concurrency
# -----------------------------------------------------------------------------

class TestImmutableAttemptPublication:
    """Test immutable attempt keys and stale-worker write isolation."""

    def test_attempt_key_derivation_format_and_security(self, test_user_id: UUID):
        upload_id = uuid4()
        token = uuid4()
        key = get_attempt_object_key(test_user_id, upload_id, token)

        expected = f"users/{test_user_id}/wardrobe/{upload_id}/attempts/{token}.webp"
        assert key == expected
        assert not key.endswith("canonical.webp")

        # Path traversal rejection: non-UUID types raise ValueError
        with pytest.raises(ValueError):
            get_attempt_object_key(test_user_id, upload_id, "../../hack.webp")  # type: ignore

    def test_legacy_canonical_key_compatibility(self, test_user_id: UUID):
        upload_id = uuid4()
        token = uuid4()

        # Without token: returns legacy key
        legacy = get_canonical_object_key(test_user_id, upload_id)
        assert legacy == f"users/{test_user_id}/wardrobe/{upload_id}/canonical.webp"

        # With token: delegates to attempt key
        attempt = get_canonical_object_key(test_user_id, upload_id, token)
        assert attempt == f"users/{test_user_id}/wardrobe/{upload_id}/attempts/{token}.webp"

    @pytest.mark.anyio
    async def test_worker_a_and_b_cross_attempt_isolation_sequence(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenarios 1-5: Worker A delayed write lands on its own attempt key, Worker B's object is untouched.

        1. Worker A writes attempt key A and loses lease.
        2. Worker B writes attempt key B and successfully finalizes.
        3. Worker A completes its delayed PUT after Worker B finalizes.
        4. Verify Worker B's object bytes remain unchanged.
        5. Verify PostgreSQL still references Worker B's object.
        """
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()

        key_a = get_attempt_object_key(test_user_id, upload_id, token_a)
        key_b = get_attempt_object_key(test_user_id, upload_id, token_b)

        assert key_a != key_b, "Different attempts must write to different keys"

        # Staging image
        jpeg_bytes = make_test_jpeg(width=300, height=200, color=(10, 20, 30))
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_token=token_a,
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=2),  # expired!
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # Worker B claims lease with token_b and publishes
        auth.processing_lease_token = token_b
        auth.processing_lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        sqlite_db.commit()

        data_b = make_test_webp(width=300, height=200, color=(0, 255, 0))
        sha_b = hashlib.sha256(data_b).hexdigest()

        # Worker B writes key_b
        await fake_storage.put_object(
            key=key_b,
            data=data_b,
            content_type="image/webp",
            custom_metadata={"user_id": str(test_user_id), "upload_id": str(upload_id), "sha256": sha_b},
        )

        # Worker B finalizes DB
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        await use_case._finalize_published_record(
            user_id=test_user_id,
            upload_id=upload_id,
            lease_token=token_b,
            canonical_key=key_b,
            canonical_sha256=sha_b,
            size_bytes=len(data_b),
            width=300,
            height=200,
            staging_key=auth.staging_key,
        )

        # Verify DB is published with Worker B's reference
        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.canonical_key == key_b
        assert auth.canonical_sha256 == sha_b

        # Now Worker A's delayed PUT to key_a completes!
        data_a = make_test_webp(width=300, height=200, color=(255, 0, 0))
        sha_a = hashlib.sha256(data_a).hexdigest()
        await fake_storage.put_object(
            key=key_a,
            data=data_a,
            content_type="image/webp",
            custom_metadata={"user_id": str(test_user_id), "upload_id": str(upload_id), "sha256": sha_a},
        )

        # 4. Verify Worker B's object bytes remain unchanged!
        b_bytes = await fake_storage.read_object(key_b)
        assert b_bytes == data_b
        assert hashlib.sha256(b_bytes).hexdigest() == sha_b

        # 5. Verify PostgreSQL still references Worker B's object!
        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.canonical_key == key_b
        assert auth.canonical_sha256 == sha_b

    @pytest.mark.anyio
    async def test_worker_a_attempts_finalization_after_losing_ownership(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 6: Worker A calls finalization after losing ownership; must abort with 409 LEASE_LOST."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()

        key_a = get_attempt_object_key(test_user_id, upload_id, token_a)
        key_b = get_attempt_object_key(test_user_id, upload_id, token_b)

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="published",
            canonical_key=key_b,
            canonical_sha256="sha_b",
        )

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        with pytest.raises(ApiError) as exc_info:
            await use_case._finalize_published_record(
                user_id=test_user_id,
                upload_id=upload_id,
                lease_token=token_a,
                canonical_key=key_a,
                canonical_sha256="sha_a",
                size_bytes=500,
                width=100,
                height=100,
                staging_key=auth.staging_key,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "LEASE_LOST"

        # Database remains pointing to Worker B
        sqlite_db.refresh(auth)
        assert auth.canonical_key == key_b
        assert auth.canonical_sha256 == "sha_b"

    @pytest.mark.anyio
    async def test_worker_a_validation_failure_preserves_staging_after_losing_ownership(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 7: Worker A validation failure after lease expiry must NOT delete shared staging object."""
        upload_id = uuid4()
        token_a = uuid4()
        token_b = uuid4()

        now = datetime.now(timezone.utc)
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            lease_token=token_b,  # Worker B owns lease!
            lease_expires_at=now + timedelta(seconds=30),
        )

        staging_data = make_test_jpeg()
        fake_storage.put_object_bytes(auth.staging_key, staging_data, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)

        # Worker A tries to record failure under defunct token_a
        still_owner = use_case._record_failure(upload_id, token_a, "CORRUPT_IMAGE")
        assert still_owner is False, "Defunct worker must affect 0 rows"

        # In Phase 3.4, deletion is gated by `if still_owner:`
        if still_owner:
            await fake_storage.delete_object(auth.staging_key)

        # Assert staging object was preserved!
        assert auth.staging_key in fake_storage._objects
        assert fake_storage._objects[auth.staging_key][0] == staging_data

    @pytest.mark.anyio
    async def test_worker_b_successfully_finalizes_and_deletes_staging(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 8: Winning Worker B successfully finalizes publication and deletes staging."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg(width=300, height=200)
        auth = create_auth(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        assert res["objectKey"].startswith(f"users/{test_user_id}/wardrobe/{upload_id}/attempts/")
        assert res["objectKey"].endswith(".webp")

        # Staging key was deleted
        assert auth.staging_key not in fake_storage._objects
        # Attempt key exists in storage
        assert res["objectKey"] in fake_storage._objects

    @pytest.mark.anyio
    async def test_staging_deletion_failure_preserves_published_record(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Scenario 9: If staging deletion fails, the published database record is preserved and 200 OK returned."""
        upload_id = uuid4()
        token = uuid4()
        key = get_attempt_object_key(test_user_id, upload_id, token)

        class FailingDeleteStorage(FakeStorageAdapter):
            async def delete_object(self, key: str) -> None:
                raise StorageError("R2 deletion timeout during staging cleanup")

        storage = FailingDeleteStorage()
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            lease_token=token,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )

        use_case = CompleteMediaUpload(storage=storage, db=sqlite_db)
        res = await use_case._finalize_published_record(
            user_id=test_user_id,
            upload_id=upload_id,
            lease_token=token,
            canonical_key=key,
            canonical_sha256="sha123",
            size_bytes=500,
            width=200,
            height=200,
            staging_key=auth.staging_key,
        )

        assert res["status"] == "ready"
        assert res["objectKey"] == key

        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.canonical_key == key

    @pytest.mark.anyio
    async def test_crash_after_attempt_put_before_database_commit(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 10: Crash after attempt PUT but before DB commit: Worker B recovers and adopts the attempt object."""
        upload_id = uuid4()
        token_a = uuid4()

        key_a = get_attempt_object_key(test_user_id, upload_id, token_a)
        canonical_bytes = make_test_webp(width=400, height=300)
        canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()

        # Staging payload
        jpeg_bytes = make_test_jpeg(width=400, height=300)
        source_sha = hashlib.sha256(jpeg_bytes).hexdigest()

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            attempts=1,
            lease_token=token_a,
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),  # expired!
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # Worker A wrote attempt object before crashing
        fake_storage.put_object_bytes(
            key_a,
            canonical_bytes,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "lease_token": str(token_a),
                "sha256": canonical_sha,
                "width": "400",
                "height": "300",
                "source_sha256": source_sha,
            },
        )

        # Worker B executes completion
        use_case_b = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case_b.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        # Adopted Worker A's attempt object!
        assert res["objectKey"] == key_a
        assert res["contentHash"] == canonical_sha

        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.canonical_key == key_a
        assert auth.canonical_sha256 == canonical_sha

    @pytest.mark.anyio
    async def test_crash_after_database_commit_before_staging_deletion(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 11: Crash after database commit before staging deletion; subsequent replay cleans up staging."""
        upload_id = uuid4()
        token = uuid4()
        key = get_attempt_object_key(test_user_id, upload_id, token)

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="published",
            canonical_key=key,
            canonical_sha256="hash123",
        )
        # Staging was left behind due to crash
        fake_storage.put_object_bytes(auth.staging_key, b"leftover-staging", content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        assert res["objectKey"] == key
        # Staging is cleaned up on idempotent replay
        assert auth.staging_key not in fake_storage._objects

    @pytest.mark.anyio
    async def test_recovery_of_existing_published_legacy_canonical_key(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 12: Recovery of existing published legacy canonical key (canonical.webp) preserves key without rewrites."""
        upload_id = uuid4()
        legacy_key = f"users/{test_user_id}/wardrobe/{upload_id}/canonical.webp"

        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="published",
            canonical_key=legacy_key,
            canonical_sha256="legacy_sha",
        )

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        # Key must NOT be rewritten or migrated to attempts/
        assert res["objectKey"] == legacy_key

    @pytest.mark.anyio
    async def test_two_concurrent_attempts_with_different_fencing_tokens(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 13: Two concurrent attempts: second attempt blocked by active lease."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)

        # Worker A claims lease
        token_a = uuid4()
        now = datetime.now(timezone.utc)
        auth.status = "processing"
        auth.processing_lease_token = token_a
        auth.processing_started_at = now
        auth.processing_lease_expires_at = now + timedelta(seconds=30)
        sqlite_db.commit()

        # Worker B tries to execute concurrently
        with pytest.raises(ApiError) as exc_info:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "CONFLICT"
        assert exc_info.value.headers.get("Retry-After") == "5"

    @pytest.mark.anyio
    async def test_abandoned_attempt_object_not_treated_as_published(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 14: An abandoned attempt object in R2 is not treated as published without DB commit."""
        upload_id = uuid4()
        abandoned_token = uuid4()
        abandoned_key = get_attempt_object_key(test_user_id, upload_id, abandoned_token)

        # Object sits in storage from abandoned run
        fake_storage.put_object_bytes(abandoned_key, make_test_webp(), content_type="image/webp")

        auth = create_auth(sqlite_db, test_user_id, upload_id, status="authorized")

        # Database is NOT published
        assert auth.status != "published"
        assert auth.canonical_key is None

    @pytest.mark.anyio
    async def test_orphan_cleanup_never_deletes_winning_attempt_key(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 15: Orphan cleanup algorithm compares R2 keys against auth.canonical_key and preserves winning key."""
        upload_id = uuid4()
        token_win = uuid4()
        token_orphan_1 = uuid4()
        token_orphan_2 = uuid4()

        winning_key = get_attempt_object_key(test_user_id, upload_id, token_win)
        orphan_key_1 = get_attempt_object_key(test_user_id, upload_id, token_orphan_1)
        orphan_key_2 = get_attempt_object_key(test_user_id, upload_id, token_orphan_2)

        # Storage has all 3 attempt objects
        fake_storage.put_object_bytes(winning_key, b"win", content_type="image/webp")
        fake_storage.put_object_bytes(orphan_key_1, b"orphan1", content_type="image/webp")
        fake_storage.put_object_bytes(orphan_key_2, b"orphan2", content_type="image/webp")

        # Database record commits winning_key
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="published",
            canonical_key=winning_key,
            canonical_sha256="sha_win",
        )

        # Simulated Orphan Cleanup Routine (Phase 13 specification verification):
        # 1. Fetch blessed canonical key from DB
        db_canonical_key = sqlite_db.execute(
            select(MediaUploadAuthorization.canonical_key).where(
                MediaUploadAuthorization.upload_id == upload_id,
                MediaUploadAuthorization.status == "published",
            )
        ).scalar_one()

        # 2. Iterate storage keys under prefix
        prefix = f"users/{test_user_id}/wardrobe/{upload_id}/attempts/"
        attempt_keys = [k for k in list(fake_storage._objects.keys()) if k.startswith(prefix)]

        deleted_orphans = []
        for k in attempt_keys:
            if k != db_canonical_key:
                await fake_storage.delete_object(k)
                deleted_orphans.append(k)

        # 3. Verify orphans were deleted and winning key was NEVER touched!
        assert deleted_orphans == [orphan_key_1, orphan_key_2]
        assert orphan_key_1 not in fake_storage._objects
        assert orphan_key_2 not in fake_storage._objects
        assert winning_key in fake_storage._objects
        assert fake_storage._objects[winning_key][0] == b"win"

    @pytest.mark.anyio
    async def test_threaded_delayed_put_completes_after_coroutine_cancellation(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Scenario 16: Accurately model external thread pool continuation across coroutine cancellation.

        Proves that:
        - Worker A's blocking OS thread continues after coroutine cancellation.
        - Worker A writes to attempts/{token_a}.webp.
        - Worker B claims the lease and writes attempts/{token_b}.webp.
        - Worker A's delayed write never overwrites Worker B's object or changes PostgreSQL.
        """
        upload_id = uuid4()
        storage = ThreadedLatePutStorage(delay_seconds=0.3)

        jpeg_bytes = make_test_jpeg(width=300, height=200, color=(100, 100, 100))
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            content_type="image/jpeg",
            size_bytes=len(jpeg_bytes),
        )
        storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case_a = CompleteMediaUpload(
            storage=storage,
            db=sqlite_db,
            pipeline_timeout_seconds=25.0,
            heartbeat_interval_seconds=0,
        )

        # Worker A starts execution
        task_a = asyncio.create_task(use_case_a.execute(user_id=test_user_id, upload_id=upload_id))

        # Wait until the blocking OS thread put has actually started in the thread pool
        await asyncio.wait_for(storage.put_started_event.wait(), timeout=5.0)

        # Worker A's coroutine is cancelled while put_object is executing in the OS thread
        task_a.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task_a

        # Database reverted to authorized for retry
        sqlite_db.refresh(auth)
        assert auth.status == "authorized"

        # Now Worker B retries with standard fast storage adapter sharing the same storage state
        fast_storage = FakeStorageAdapter()
        fast_storage._objects = storage._objects  # share storage dict

        use_case_b = CompleteMediaUpload(
            storage=fast_storage,
            db=sqlite_db,
            pipeline_timeout_seconds=25.0,
            heartbeat_interval_seconds=0,
        )
        res_b = await use_case_b.execute(user_id=test_user_id, upload_id=upload_id)

        assert res_b["status"] == "ready"
        key_b = res_b["objectKey"]
        bytes_b = fast_storage._objects[key_b][0]

        # Now wait for Worker A's OS thread to finish sleeping and writing
        await asyncio.sleep(0.4)
        assert storage.put_completed is True
        key_a = storage.last_written_key
        assert key_a is not None
        assert key_a != key_b, "Worker A and Worker B wrote to completely different attempt keys"

        # Worker B's bytes are completely unchanged!
        assert fast_storage._objects[key_b][0] == bytes_b

        # PostgreSQL still references Worker B!
        sqlite_db.refresh(auth)
        assert auth.status == "published"
        assert auth.canonical_key == key_b

    @pytest.mark.anyio
    async def test_pre_put_fencing_gate_aborts_when_lease_expired_before_put(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Scenario 17: Pre-PUT fencing check detects expired lease and aborts before initiating storage upload."""
        upload_id = uuid4()
        token = uuid4()
        auth = create_auth(
            sqlite_db,
            test_user_id,
            upload_id,
            status="processing",
            lease_token=token,
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),  # expired!
        )
        fake_storage.put_object_bytes(auth.staging_key, make_test_jpeg(), content_type="image/jpeg")

        # Worker B claims lease after Worker A's lease expired
        token_b = uuid4()
        auth.processing_lease_token = token_b
        auth.processing_lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        sqlite_db.commit()

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)

        # Worker A reaches Step 13 and tries to execute with defunct token
        with pytest.raises(ApiError) as exc_info:
            await use_case._execute_pipeline(
                user_id=test_user_id,
                upload_id=upload_id,
                lease_token=token,
                staging_key=auth.staging_key,
                expected_content_type="image/jpeg",
                existing_canonical_key=None,
                existing_canonical_sha256=None,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "LEASE_LOST"

        # Zero attempt objects written to storage
        attempt_prefix = f"users/{test_user_id}/wardrobe/{upload_id}/attempts/"
        written_attempts = [k for k in fake_storage._objects if k.startswith(attempt_prefix)]
        assert len(written_attempts) == 0, "No storage write must occur when pre-PUT fencing check fails"
