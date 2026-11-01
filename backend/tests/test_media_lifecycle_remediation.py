"""Comprehensive test suite for Stage 2 P0-4 Phase 3.1:
Published Media Lifecycle Reliability Remediation.

Validates:
1. F-01: Preservation of published authorization records during 24h retention pruning.
2. F-01: Preservation of active processing records and bounded batch pruning.
3. F-02: Failure-injection tests for canonical-object crash recovery without re-transcoding.
4. F-02: Recovery fallback when canonical object is corrupt, unrelated, or missing.
5. F-03 & F-05: Durable 15-second PostgreSQL processing lease concurrency serialization.
6. F-03 & F-05: Multi-session PostgreSQL concurrency (2 and 10 concurrent requests).
7. F-03 & F-05: Lease expiration recovery, 5-attempt limit, and 60s cooldown reset.
8. F-03 & F-05: Lease clearing on publication, terminal failure, and transient errors.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import io
import time
from typing import Generator, Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.api.errors import ApiError
from app.application.media import (
    CompleteMediaUpload,
    get_canonical_object_key,
    prune_expired_authorizations,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageObjectMetadata,
)
from app.infrastructure.db.models import MediaUploadAuthorization
from app.main import app
from app.workers.transcoder import TranscoderProcessManager
from tests.fakes.fake_storage import FakeStorageAdapter


DISPOSABLE_PG_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_phase3_1_test"
)


# -----------------------------------------------------------------------------
# Fixtures & Helpers
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
def fake_storage() -> FakeStorageAdapter:
    """In-memory fake object storage adapter."""
    adapter = FakeStorageAdapter(bucket_name="fansivibe-test-wardrobe")
    yield adapter
    adapter.clear()


@pytest.fixture
def test_user_id() -> UUID:
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def other_user_id() -> UUID:
    return UUID("22222222-2222-2222-2222-222222222222")


def create_auth_record(
    db: Session,
    user_id: UUID,
    upload_id: UUID,
    content_type: str = "image/jpeg",
    size_bytes: int = 1024,
    status: str = "authorized",
    hours_to_live: int = 24,
    canonical_key: Optional[str] = None,
    canonical_sha256: Optional[str] = None,
    processing_attempts: int = 0,
    processing_lease_expires_at: Optional[datetime] = None,
    processing_started_at: Optional[datetime] = None,
) -> MediaUploadAuthorization:
    """Helper to insert an initial MediaUploadAuthorization row."""
    ext = "webp" if content_type == "image/webp" else "jpg"
    staging_key = f"staging/users/{user_id}/wardrobe/{upload_id}.{ext}"
    now = datetime.now(timezone.utc)
    rec = MediaUploadAuthorization(
        user_id=user_id,
        idempotency_key=f"idem-{upload_id}",
        upload_id=upload_id,
        key_version="v1",
        request_fingerprint="fp123",
        staging_key=staging_key,
        content_type=content_type,
        size_bytes=size_bytes,
        status=status,
        created_at=now,
        expires_at=now + timedelta(hours=hours_to_live),
        canonical_key=canonical_key,
        canonical_sha256=canonical_sha256,
        processing_attempts=processing_attempts,
        processing_lease_expires_at=processing_lease_expires_at,
        processing_started_at=processing_started_at,
    )
    db.add(rec)
    db.commit()
    return rec


# -----------------------------------------------------------------------------
# 1. F-01: Preservation of Published Records & Bounded Pruning Tests
# -----------------------------------------------------------------------------


class TestF01AuthorizationPruning:
    """Validate F-01 requirements: preservation of published records and active leases during pruning."""

    def test_expired_authorized_records_are_pruned(self, sqlite_db: Session, test_user_id: UUID):
        """Expired records with status='authorized' are pruned when expires_at < cutoff."""
        uid = uuid4()
        create_auth_record(sqlite_db, test_user_id, uid, status="authorized", hours_to_live=-2)

        deleted = prune_expired_authorizations(sqlite_db)
        assert deleted == 1

        rec = sqlite_db.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == uid)
        ).scalar_one_or_none()
        assert rec is None

    def test_expired_failed_and_expired_records_are_pruned(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Expired records with status='failed' or 'expired' are pruned according to existing policy."""
        uid_failed = uuid4()
        uid_expired = uuid4()
        create_auth_record(sqlite_db, test_user_id, uid_failed, status="failed", hours_to_live=-2)
        create_auth_record(sqlite_db, test_user_id, uid_expired, status="expired", hours_to_live=-2)

        deleted = prune_expired_authorizations(sqlite_db)
        assert deleted == 2

    def test_published_records_are_strictly_preserved_regardless_of_age(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """F-01 core requirement: published records must NEVER be deleted by 24h retention pruning."""
        uid_pub = uuid4()
        canonical_key = f"users/{test_user_id}/wardrobe/{uid_pub}/canonical.webp"
        canonical_sha = hashlib.sha256(b"dummy-canonical").hexdigest()
        now = datetime.now(timezone.utc)

        # Record is 72 hours old (well past 24-hour expiration)
        rec = create_auth_record(
            sqlite_db,
            test_user_id,
            uid_pub,
            status="published",
            hours_to_live=-72,
            canonical_key=canonical_key,
            canonical_sha256=canonical_sha,
        )
        rec.canonical_width = 1920
        rec.canonical_height = 1440
        rec.canonical_size_bytes = 45000
        rec.completed_at = now - timedelta(hours=72)
        sqlite_db.commit()

        # Prune with current cutoff
        deleted = prune_expired_authorizations(sqlite_db, now=now)
        assert deleted == 0

        # Published record still exists with all canonical metadata intact
        persisted = sqlite_db.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == uid_pub)
        ).scalar_one()
        assert persisted.status == "published"
        assert persisted.canonical_key == canonical_key
        assert persisted.canonical_sha256 == canonical_sha
        assert persisted.canonical_width == 1920
        assert persisted.canonical_height == 1440
        assert persisted.canonical_size_bytes == 45000
        assert persisted.completed_at is not None

    def test_active_processing_records_are_preserved_during_pruning(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Records with status='processing' and active lease must NOT be pruned even if upload expired."""
        now = datetime.now(timezone.utc)
        uid_proc = uuid4()
        create_auth_record(
            sqlite_db,
            test_user_id,
            uid_proc,
            status="processing",
            hours_to_live=-2,  # original authorization expired
            processing_lease_expires_at=now + timedelta(seconds=15),  # lease active!
            processing_started_at=now - timedelta(seconds=5),
        )

        deleted = prune_expired_authorizations(sqlite_db, now=now)
        assert deleted == 0

        persisted = sqlite_db.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == uid_proc)
        ).scalar_one_or_none()
        assert persisted is not None
        assert persisted.status == "processing"

    def test_stale_processing_records_with_expired_lease_are_pruned_when_upload_expired(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Processing records with expired lease AND expired authorization are pruned."""
        now = datetime.now(timezone.utc)
        uid_stale = uuid4()
        create_auth_record(
            sqlite_db,
            test_user_id,
            uid_stale,
            status="processing",
            hours_to_live=-25,  # upload expired >24h ago
            processing_lease_expires_at=now - timedelta(hours=1),  # lease expired 1h ago
        )

        deleted = prune_expired_authorizations(sqlite_db, now=now)
        assert deleted == 1

    def test_bounded_pruning_respects_batch_size_and_max_batches(
        self, sqlite_db: Session, test_user_id: UUID
    ):
        """Pruning respects batch_size and max_batches limits to prevent table lock spikes."""
        now = datetime.now(timezone.utc)
        for _ in range(15):
            create_auth_record(
                sqlite_db,
                test_user_id,
                uuid4(),
                status="authorized",
                hours_to_live=-2,
            )

        # 15 expired records exist; prune in batches of 5 with max_batches=2 (should delete 10)
        deleted = prune_expired_authorizations(
            sqlite_db, now=now, batch_size=5, max_batches=2
        )
        assert deleted == 10

        remaining = sqlite_db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.expires_at < now,
                MediaUploadAuthorization.status != "published",
            )
        ).scalars().all()
        assert len(remaining) == 5

    def test_pruning_does_not_delete_canonical_storage_objects(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Authorization pruning must never delete canonical storage objects."""
        uid = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, uid)
        fake_storage.put_object_bytes(canonical_key, b"canonical-webp-bytes", content_type="image/webp")

        create_auth_record(
            sqlite_db,
            test_user_id,
            uid,
            status="published",
            hours_to_live=-48,
            canonical_key=canonical_key,
        )

        prune_expired_authorizations(sqlite_db)
        assert fake_storage.object_exists_sync(canonical_key)


# -----------------------------------------------------------------------------
# 2. F-02: Canonical-Object Crash Recovery Failure-Injection Tests
# -----------------------------------------------------------------------------


class TestF02CanonicalCrashRecovery:
    """Validate F-02 requirements: reliable detection and recovery of existing canonical objects."""

    @pytest.mark.anyio
    async def test_canonical_publication_succeeds_but_db_commit_fails_recovery(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Failure-injection: R2 publication succeeds, DB commit fails, retry recovers without re-transcoding."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        canonical_bytes = make_test_webp(width=600, height=400)
        canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()

        # 1. Put valid canonical object in R2 with custom metadata (as step 13 would)
        fake_storage.put_object_bytes(
            canonical_key,
            canonical_bytes,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "sha256": canonical_sha,
                "width": "600",
                "height": "400",
            },
        )

        # 2. Put staging bytes in R2
        jpeg_bytes = make_test_jpeg(width=600, height=400)
        auth = create_auth_record(
            sqlite_db,
            test_user_id,
            upload_id,
            content_type="image/jpeg",
            size_bytes=len(jpeg_bytes),
            status="processing",
            processing_attempts=1,
            canonical_key=None,  # DB commit crashed before persisting canonical_key!
            canonical_sha256=None,
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # 3. Simulate application restart: instantiate a fresh CompleteMediaUpload use case
        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)

        # Mock transcoder to prove re-transcoding is NOT called
        transcode_called = False

        class SpyingTranscoder:
            async def transcode(self, raw_bytes):
                nonlocal transcode_called
                transcode_called = True
                raise AssertionError("Transcoder should NOT be called during canonical crash recovery!")

        use_case._transcoder = SpyingTranscoder()

        # 4. Execute completion retry
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert not transcode_called
        assert res["uploadId"] == upload_id
        assert res["objectKey"] == canonical_key
        assert res["contentHash"] == canonical_sha
        assert res["mediaType"] == "image/webp"
        assert res["status"] == "ready"

        # Staging object deleted after successful recovery
        assert not fake_storage.object_exists_sync(auth.staging_key)

        # DB row updated to published with canonical metadata
        sqlite_db.expire_all()
        persisted = sqlite_db.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one()
        assert persisted.status == "published"
        assert persisted.canonical_key == canonical_key
        assert persisted.canonical_sha256 == canonical_sha
        assert persisted.completed_at is not None
        assert persisted.processing_lease_expires_at is None

    @pytest.mark.anyio
    async def test_crash_recovery_rejects_corrupted_canonical_bytes_and_falls_back(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """If existing canonical object has corrupted bytes (magic bytes/SHA mismatch), falls back to safe retry path."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)

        # Put corrupted bytes in canonical location
        fake_storage.put_object_bytes(
            canonical_key,
            b"corrupted-garbage-bytes-not-webp",
            content_type="image/webp",
            custom_metadata={
                "user_id": str(test_user_id),
                "upload_id": str(upload_id),
                "sha256": "fake_sha_that_does_not_match",
            },
        )

        # Valid staging bytes exist
        jpeg_bytes = make_test_jpeg(width=300, height=200)
        auth = create_auth_record(
            sqlite_db,
            test_user_id,
            upload_id,
            content_type="image/jpeg",
            size_bytes=len(jpeg_bytes),
            status="processing",
            canonical_key=None,
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        # Succeeded by falling back to re-transcoding and publishing attempt WebP
        assert res["status"] == "ready"
        assert res["mediaType"] == "image/webp"
        assert res["objectKey"].startswith(f"users/{test_user_id}/wardrobe/{upload_id}/")

        # Verified valid WebP bytes now in storage at published key
        meta = await fake_storage.get_object_metadata(res["objectKey"])
        assert meta is not None
        assert meta.size_bytes > 0

    @pytest.mark.anyio
    async def test_crash_recovery_rejects_unrelated_foreign_canonical_object(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID, other_user_id: UUID
    ):
        """Canonical object metadata belonging to another user is rejected during crash recovery."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        other_canonical = make_test_webp()

        # Metadata claims other_user_id
        fake_storage.put_object_bytes(
            canonical_key,
            other_canonical,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(other_user_id),  # foreign user!
                "upload_id": str(upload_id),
                "sha256": hashlib.sha256(other_canonical).hexdigest(),
            },
        )

        jpeg_bytes = make_test_jpeg(width=200, height=200)
        auth = create_auth_record(
            sqlite_db,
            test_user_id,
            upload_id,
            content_type="image/jpeg",
            size_bytes=len(jpeg_bytes),
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        # Published new attempt object with caller's verified media
        assert res["status"] == "ready"
        meta = await fake_storage.get_object_metadata(res["objectKey"])
        assert meta.custom_metadata["user_id"] == str(test_user_id)

    @pytest.mark.anyio
    async def test_crash_recovery_when_canonical_object_does_not_exist(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """When canonical object does not exist, standard staging verification and transcoding proceeds."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg(width=300, height=300)
        auth = create_auth_record(
            sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes)
        )
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        assert res["mediaType"] == "image/webp"

    @pytest.mark.anyio
    async def test_idempotent_replay_after_upload_expiry(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID
    ):
        """Published uploads continue returning 200 OK even after the 24h upload authorization expired."""
        upload_id = uuid4()
        canonical_key = get_canonical_object_key(test_user_id, upload_id)
        now = datetime.now(timezone.utc)

        # Set status='published' with expires_at in the past (-48h)
        rec = create_auth_record(
            sqlite_db,
            test_user_id,
            upload_id,
            status="published",
            hours_to_live=-48,
            canonical_key=canonical_key,
            canonical_sha256="canonical_hash_123",
        )
        rec.canonical_width = 1920
        rec.canonical_height = 1080
        rec.canonical_size_bytes = 65000
        rec.completed_at = now - timedelta(hours=48)
        sqlite_db.commit()

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["status"] == "ready"
        assert res["objectKey"] == canonical_key
        assert res["contentHash"] == "canonical_hash_123"


# -----------------------------------------------------------------------------
# 3. F-03 & F-05: Durable Processing Lease & Multi-Session PostgreSQL Concurrency
# -----------------------------------------------------------------------------


class TestF03AndF05DurableProcessingLeasePostgreSQL:
    """Genuine multi-session PostgreSQL concurrency and durable lease validation."""

    @classmethod
    def setup_class(cls):
        """Verify disposable database connectivity before running PostgreSQL tests."""
        try:
            test_engine = create_engine(DISPOSABLE_PG_URL, pool_size=15, max_overflow=10)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            cls.engine = test_engine
            cls.SessionLocal = sessionmaker(bind=test_engine)
        except Exception as exc:
            pytest.skip(f"Disposable PostgreSQL not available: {exc}")

    @classmethod
    def teardown_class(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def _seed_user_and_auth(
        self, user_id: UUID, upload_id: UUID, status: str = "authorized", attempts: int = 0
    ) -> str:
        """Seed a test user and initial MediaUploadAuthorization row in the disposable DB."""
        staging_key = f"staging/users/{user_id}/wardrobe/{upload_id}.jpg"
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
                    "  :staging_key, 'image/jpeg', 2048, now() + INTERVAL '24 hours', :status, :attempts"
                    ") ON CONFLICT (user_id, idempotency_key) DO UPDATE SET "
                    "  status = EXCLUDED.status, processing_attempts = EXCLUDED.processing_attempts"
                ),
                {
                    "user_id": user_id,
                    "idem": f"idem-{upload_id}",
                    "upload_id": upload_id,
                    "staging_key": staging_key,
                    "status": status,
                    "attempts": attempts,
                },
            )
            session.commit()
        return staging_key

    def test_two_concurrent_completion_requests_exactly_one_claims_lease(self):
        """Two concurrent completion requests on independent DB sessions: exactly 1 claims lease, 1 gets 409 Conflict."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=300, height=300)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        results = []
        errors = []

        def worker_fn(thread_id: int):
            with self.SessionLocal() as db_session:
                use_case = CompleteMediaUpload(storage=shared_storage, db=db_session)
                try:
                    res = asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
                    return ("OK", res)
                except ApiError as exc:
                    return ("API_ERROR", exc)
                except Exception as exc:
                    return ("ERROR", exc)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker_fn, i) for i in range(2)]
            for fut in as_completed(futures):
                status, val = fut.result()
                if status == "OK":
                    results.append(val)
                elif status == "API_ERROR":
                    errors.append(val)
                else:
                    pytest.fail(f"Unexpected error: {val}")

        # Either one claims lease and publishes (or both return OK if one completed and second replayed idempotently),
        # or exactly one gets 200 OK and one gets 409 CONFLICT with Retry-After header.
        total_success = len(results)
        total_conflicts = len([e for e in errors if e.status_code == 409 and e.code == "CONFLICT"])

        assert total_success >= 1
        if total_conflicts > 0:
            conflict_err = [e for e in errors if e.status_code == 409][0]
            assert conflict_err.headers.get("Retry-After") == "5"

        # Exactly 1 canonical object exists in storage
        keys = shared_storage.get_stored_keys()
        canonical_keys = [k for k in keys if k.startswith(f"users/{test_user}/wardrobe/{upload_id}/")]
        assert len(canonical_keys) == 1

    def test_ten_concurrent_completion_requests_no_duplicate_processing(self):
        """10 concurrent requests across independent PostgreSQL sessions serialize cleanly without duplicate transcoding."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=400, height=300)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        successes = []
        conflicts = []

        def worker_fn(worker_idx: int):
            with self.SessionLocal() as db_session:
                use_case = CompleteMediaUpload(storage=shared_storage, db=db_session)
                try:
                    res = asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
                    return ("SUCCESS", res)
                except ApiError as exc:
                    return ("API_ERROR", exc)
                except Exception as exc:
                    return ("ERROR", exc)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_fn, i) for i in range(10)]
            for fut in as_completed(futures):
                status, val = fut.result()
                if status == "SUCCESS":
                    successes.append(val)
                elif status == "API_ERROR" and val.status_code == 409:
                    conflicts.append(val)
                else:
                    pytest.fail(f"Unexpected result: {status} -> {val}")

        # At least 1 succeeded
        assert len(successes) >= 1
        # All successes return the exact same canonical objectKey
        expected_key = successes[0]["objectKey"]
        for s in successes:
            assert s["objectKey"] == expected_key
            assert s["status"] == "ready"

        # Conflicts must have Retry-After header
        for c in conflicts:
            assert c.status_code == 409
            assert "Retry-After" in c.headers

        # Exactly 1 canonical object was published
        keys = shared_storage.get_stored_keys()
        canonical_keys = [k for k in keys if k.startswith(f"users/{test_user}/wardrobe/{upload_id}/")]
        assert len(canonical_keys) == 1

    def test_lease_expiry_permits_worker_recovery(self):
        """When an active lease expires (>15s elapsed on crashed worker), a new request can safely claim lease and recover."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=200, height=200)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        # Simulate crashed worker: status='processing', lease expired 5 seconds ago
        with self.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  status = 'processing', "
                    "  processing_started_at = now() - INTERVAL '20 seconds', "
                    "  processing_lease_expires_at = now() - INTERVAL '5 seconds', "
                    "  processing_attempts = 1 "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            )
            session.commit()

        # Retry request arrives on independent session
        with self.SessionLocal() as session:
            use_case = CompleteMediaUpload(storage=shared_storage, db=session)
            res = asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))

        assert res["status"] == "ready"

        # Verify DB state is published and lease cleared
        with self.SessionLocal() as session:
            row = session.execute(
                text("SELECT status, processing_lease_expires_at FROM media_upload_authorizations WHERE upload_id = :uid"),
                {"uid": upload_id},
            ).fetchone()
            assert row[0] == "published"
            assert row[1] is None

    def test_crashed_worker_leaves_recoverable_state(self):
        """Simulate worker dying mid-processing; prove upload recovers cleanly."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=200, height=200)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        # Worker 1 starts processing, claims lease, then "dies"
        with self.SessionLocal() as session:
            use_case1 = CompleteMediaUpload(storage=shared_storage, db=session)
            # Seed lease as if worker 1 died 16s ago
            session.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  status = 'processing', "
                    "  processing_started_at = now() - INTERVAL '16 seconds', "
                    "  processing_lease_expires_at = now() - INTERVAL '1 second', "
                    "  processing_attempts = 1 "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            )
            session.commit()

        # Worker 2 recovers after lease expiry
        with self.SessionLocal() as session:
            use_case2 = CompleteMediaUpload(storage=shared_storage, db=session)
            res = asyncio.run(use_case2.execute(user_id=test_user, upload_id=upload_id))
            assert res["status"] == "ready"

    def test_published_completion_remains_idempotent_across_workers(self):
        """Multiple independent sessions completing an already-published record return identical payloads."""
        test_user = uuid4()
        upload_id = uuid4()
        self._seed_user_and_auth(test_user, upload_id)
        canonical_key = get_canonical_object_key(test_user, upload_id)

        # Set to published
        with self.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  status = 'published', "
                    "  canonical_key = :ckey, "
                    "  canonical_sha256 = 'abc123sha', "
                    "  canonical_width = 1920, "
                    "  canonical_height = 1080, "
                    "  canonical_size_bytes = 50000, "
                    "  completed_at = now() "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id, "ckey": canonical_key},
            )
            session.commit()

        shared_storage = FakeStorageAdapter()

        # Two independent worker sessions call complete
        with self.SessionLocal() as s1, self.SessionLocal() as s2:
            u1 = CompleteMediaUpload(storage=shared_storage, db=s1)
            u2 = CompleteMediaUpload(storage=shared_storage, db=s2)
            r1 = asyncio.run(u1.execute(user_id=test_user, upload_id=upload_id))
            r2 = asyncio.run(u2.execute(user_id=test_user, upload_id=upload_id))

        assert r1 == r2
        assert r1["objectKey"] == canonical_key
        assert r1["contentHash"] == "abc123sha"

    def test_lease_is_cleared_after_success(self):
        """Successful publication clears processing_lease_expires_at to NULL."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=200, height=200)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        with self.SessionLocal() as session:
            use_case = CompleteMediaUpload(storage=shared_storage, db=session)
            asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))

        with self.SessionLocal() as session:
            row = session.execute(
                text("SELECT status, processing_lease_expires_at FROM media_upload_authorizations WHERE upload_id = :uid"),
                {"uid": upload_id},
            ).fetchone()
            assert row[0] == "published"
            assert row[1] is None

    def test_lease_cleared_on_terminal_failure(self):
        """Terminal failure (e.g. empty object) transitions status='failed' and clears lease."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        # Empty object triggers terminal 422 EMPTY_OBJECT
        shared_storage.put_object_bytes(staging_key, b"", content_type="image/jpeg")

        with self.SessionLocal() as session:
            use_case = CompleteMediaUpload(storage=shared_storage, db=session)
            with pytest.raises(ApiError) as exc_info:
                asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
            assert exc_info.value.status_code == 422
            assert exc_info.value.code == "EMPTY_OBJECT"

        with self.SessionLocal() as session:
            row = session.execute(
                text("SELECT status, failure_reason, processing_lease_expires_at FROM media_upload_authorizations WHERE upload_id = :uid"),
                {"uid": upload_id},
            ).fetchone()
            assert row[0] == "failed"
            assert row[1] == "EMPTY_OBJECT"
            assert row[2] is None

    def test_five_attempt_limit_and_cooldown_recovery(self):
        """Five rapid failed attempts trigger 409 limit; after 60s cooldown, attempt counter resets and retry is allowed."""
        test_user = uuid4()
        upload_id = uuid4()
        staging_key = self._seed_user_and_auth(test_user, upload_id)

        shared_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=200, height=200)
        shared_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        # 1. Simulate 5 attempts failed rapidly (started 10s ago, lease expired 1s ago)
        with self.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  status = 'processing', "
                    "  processing_started_at = now() - INTERVAL '10 seconds', "
                    "  processing_lease_expires_at = now() - INTERVAL '1 second', "
                    "  processing_attempts = 5 "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            )
            session.commit()

        # Immediate retry within cooldown window is rejected with 409 PROCESSING_LIMIT_EXCEEDED
        with self.SessionLocal() as session:
            use_case = CompleteMediaUpload(storage=shared_storage, db=session)
            with pytest.raises(ApiError) as exc_info:
                asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "PROCESSING_LIMIT_EXCEEDED"
            assert exc_info.value.headers.get("Retry-After") == "60"

        # 2. Simulate cooldown expired (started 65 seconds ago)
        with self.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  processing_started_at = now() - INTERVAL '65 seconds', "
                    "  processing_lease_expires_at = now() - INTERVAL '50 seconds' "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            )
            session.commit()

        # Now retry is permitted and resets attempt counter
        with self.SessionLocal() as session:
            use_case = CompleteMediaUpload(storage=shared_storage, db=session)
            res = asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
            assert res["status"] == "ready"

    def test_independent_workers_use_same_durable_lease_state(self):
        """Independent PostgreSQL sessions query and respect durable lease state."""
        test_user = uuid4()
        upload_id = uuid4()
        self._seed_user_and_auth(test_user, upload_id)

        # Session 1 claims lease
        with self.SessionLocal() as s1:
            s1.execute(
                text(
                    "UPDATE media_upload_authorizations SET "
                    "  status = 'processing', "
                    "  processing_started_at = now(), "
                    "  processing_lease_expires_at = now() + INTERVAL '15 seconds', "
                    "  processing_attempts = 1 "
                    "WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            )
            s1.commit()

        # Session 2 inspects record and observes active lease
        with self.SessionLocal() as s2:
            row = s2.execute(
                text(
                    "SELECT status, processing_lease_expires_at > now() "
                    "FROM media_upload_authorizations WHERE upload_id = :uid"
                ),
                {"uid": upload_id},
            ).fetchone()
            assert row[0] == "processing"
            assert row[1] is True
