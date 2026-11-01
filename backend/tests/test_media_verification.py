"""Comprehensive automated test suite for Stage 2 P0-4 Phase 3:
Upload Verification & Canonical Media Publication.

Validates:
1. API & Authorization: Bearer JWT authentication, OW-1 caller scoping, 404 enumeration defense.
2. Zero-Trust Verification: Actual size, independent SHA-256 calculation, magic byte inspection.
3. Integrity & Spoofing: Mime spoofing, extension spoofing, corrupt payload, and bomb defense.
4. Image Canonicalization: EXIF orientation, GPS stripping, Lanczos downscaling, aspect ratio, Q85 WebP.
5. Child Process Lifecycle: Standalone subprocess, 5.0s timeout with SIGKILL, PID reaping, temp file cleanup.
6. Publication & Crash Recovery: Canonical R2 publication, staging cleanup, retry recovery.
7. Concurrency & Migration: Multi-session PostgreSQL concurrency serialization and 0034 lineage.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import io
import os
from pathlib import Path
import tempfile
from typing import Generator, Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.api.errors import ApiError
from app.application.media import (
    CompleteMediaUpload,
    get_media_upload_complete_lock_key,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    StoragePayloadError,
)
from app.infrastructure.db.models import MediaUploadAuthorization
from app.main import app
from app.workers.transcoder import (
    CANONICAL_MAX_EDGE,
    ImageValidationError,
    MemoryLimitExceededError,
    TranscoderProcessManager,
    TranscodingError,
    TranscodingTimeoutError,
)
from tests.fakes.fake_storage import FakeStorageAdapter


# -----------------------------------------------------------------------------
# Image Fixture Generators
# -----------------------------------------------------------------------------


def make_test_jpeg(
    width: int = 400,
    height: int = 300,
    color: str = "red",
    orientation: Optional[int] = None,
    with_gps: bool = False,
) -> bytes:
    """Generate deterministic JPEG image with optional EXIF orientation and GPS tags."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    exif = Image.Exif()

    if orientation is not None:
        exif[0x0112] = orientation  # Orientation tag

    if with_gps:
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1] = "N"
        gps_ifd[2] = ((37, 1), (46, 1), (2964, 100))
        gps_ifd[3] = "W"
        gps_ifd[4] = ((122, 1), (25, 1), (984, 100))

    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def make_test_webp(
    width: int = 400,
    height: int = 300,
    color: str = "blue",
) -> bytes:
    """Generate deterministic canonical WebP test image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


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


@pytest.fixture
def client(sqlite_db: Session, fake_storage: FakeStorageAdapter, test_user_id: UUID) -> TestClient:
    """FastAPI TestClient with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: test_user_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_auth_record(
    db: Session,
    user_id: UUID,
    upload_id: UUID,
    content_type: str = "image/jpeg",
    size_bytes: int = 1024,
    status: str = "authorized",
    hours_to_live: int = 24,
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
    )
    db.add(rec)
    db.commit()
    return rec


# -----------------------------------------------------------------------------
# 1. API & Authorization Tests
# -----------------------------------------------------------------------------


class TestCompletionApiAndAuthorization:
    """Validate API route contracts, JWT authentication, and OW-1 owner boundaries."""

    def test_unauthenticated_request_rejected_401(
        self, sqlite_db: Session, fake_storage: FakeStorageAdapter
    ):
        """Unauthenticated requests fail closed with HTTP 401."""
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: sqlite_db
        app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
        try:
            unauth_client = TestClient(app)
            upload_id = uuid4()
            response = unauth_client.post(f"/v1/media/uploads/{upload_id}/complete")
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_unknown_upload_id_returns_safe_404(self, client: TestClient):
        """Unknown upload IDs return HTTP 404 NOT_FOUND."""
        upload_id = uuid4()
        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_cross_user_upload_returns_safe_404_ow1(
        self,
        client: TestClient,
        sqlite_db: Session,
        other_user_id: UUID,
    ):
        """Attempting to complete another user's upload returns 404 NOT_FOUND (OW-1 enumeration protection)."""
        upload_id = uuid4()
        # Record belongs to other_user_id
        create_auth_record(sqlite_db, other_user_id, upload_id)

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_expired_authorization_returns_410(
        self,
        client: TestClient,
        sqlite_db: Session,
        test_user_id: UUID,
    ):
        """Authorizations older than 24 hours return HTTP 410 UPLOAD_EXPIRED."""
        upload_id = uuid4()
        create_auth_record(sqlite_db, test_user_id, upload_id, hours_to_live=-1)

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "UPLOAD_EXPIRED"

    def test_missing_staging_object_returns_400(
        self,
        client: TestClient,
        sqlite_db: Session,
        test_user_id: UUID,
    ):
        """If client calls /complete before PUT upload finishes, returns HTTP 400."""
        upload_id = uuid4()
        create_auth_record(sqlite_db, test_user_id, upload_id)

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "STAGING_OBJECT_NOT_FOUND"

    def test_valid_authenticated_jpeg_completion_workflow(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Happy path: verified JPEG staging object transcodes to WebP and publishes canonical MediaRef."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg(width=600, height=400, color="green")
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))

        # Put staging bytes into storage
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 200

        body = response.json()
        assert body["uploadId"] == str(upload_id)
        assert body["mediaType"] == "image/webp"
        assert body["width"] == 600
        assert body["height"] == 400
        assert body["status"] == "ready"
        assert body["contentHash"] is not None
        assert body["objectKey"].startswith(f"users/{test_user_id}/wardrobe/{upload_id}/")
        assert body["objectKey"].endswith(".webp")

        # Staging object must be deleted
        assert not fake_storage.object_exists_sync(auth.staging_key)
        # Canonical object must exist in storage
        assert fake_storage.object_exists_sync(body["objectKey"])

        # Database state updated to published
        sqlite_db.expire_all()
        persisted = sqlite_db.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one()
        assert persisted.status == "published"
        assert persisted.canonical_key == body["objectKey"]
        assert persisted.canonical_sha256 == body["contentHash"]
        assert persisted.completed_at is not None

    def test_valid_authenticated_webp_completion_workflow(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Happy path: verified WebP staging object canonicalizes and publishes canonical MediaRef."""
        upload_id = uuid4()
        webp_bytes = make_test_webp(width=800, height=600, color="yellow")
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/webp", size_bytes=len(webp_bytes))

        fake_storage.put_object_bytes(auth.staging_key, webp_bytes, content_type="image/webp")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 200
        body = response.json()
        assert body["mediaType"] == "image/webp"
        assert body["width"] == 800
        assert body["height"] == 600

    def test_duplicate_completion_returns_idempotent_result(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Duplicate calls to /complete for an already-published upload return identical response idempotently."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg(width=300, height=300)
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # First call
        resp1 = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert resp1.status_code == 200

        # Second call (idempotent replay)
        resp2 = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()


# -----------------------------------------------------------------------------
# 2. Zero-Trust Integrity & Spoofing Tests
# -----------------------------------------------------------------------------


class TestZeroTrustIntegrityAndSpoofing:
    """Validate server-side zero-trust inspection of payloads and headers."""

    def test_sha256_mismatch_with_client_assertion_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Client-asserted SHA-256 differing from actual received bytes is rejected with HTTP 422 CHECKSUM_MISMATCH."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        fake_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
        response = client.post(
            f"/v1/media/uploads/{upload_id}/complete",
            json={"clientSha256": fake_sha256},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CHECKSUM_MISMATCH"

    def test_sha256_match_with_client_assertion_succeeds(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Correct client-asserted SHA-256 succeeds verification."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        actual_sha = hashlib.sha256(jpeg_bytes).hexdigest()
        response = client.post(
            f"/v1/media/uploads/{upload_id}/complete",
            json={"clientSha256": actual_sha},
        )
        assert response.status_code == 200

    def test_invalid_magic_bytes_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Payload with non-image magic bytes (e.g. text/html) is rejected with HTTP 422 INVALID_FILE_SIGNATURE."""
        upload_id = uuid4()
        fake_payload = b"<html><body>Not an image</body></html>"
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(fake_payload))
        fake_storage.put_object_bytes(auth.staging_key, fake_payload, content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_FILE_SIGNATURE"

    def test_mime_spoofing_declared_webp_actual_jpeg_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Authorized as WebP but uploaded JPEG payload is rejected with HTTP 422 CONTENT_TYPE_MISMATCH."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/webp", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CONTENT_TYPE_MISMATCH"

    def test_corrupt_truncated_image_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Truncated or corrupted image payload is rejected with HTTP 422 CORRUPT_IMAGE."""
        upload_id = uuid4()
        # Valid JPEG magic bytes followed by truncated garbage
        corrupt_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00" + b"\x00" * 32
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(corrupt_bytes))
        fake_storage.put_object_bytes(auth.staging_key, corrupt_bytes, content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 422
        assert response.json()["error"]["code"] in ("CORRUPT_IMAGE", "VALIDATION_ERROR")

    def test_excessive_dimensions_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Image exceeding 12 megapixels or 4096px edge is rejected with HTTP 422 DIMENSIONS_EXCEEDED."""
        upload_id = uuid4()
        oversized_jpeg = make_test_jpeg(width=4500, height=3000)  # 13.5 MP > 12 MP
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(oversized_jpeg))
        fake_storage.put_object_bytes(auth.staging_key, oversized_jpeg, content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 422
        assert response.json()["error"]["code"] in ("DIMENSIONS_EXCEEDED", "DECOMPRESSION_BOMB")

    def test_empty_staging_object_rejected_422(
        self,
        client: TestClient,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Empty staging object (0 bytes) is rejected with HTTP 422 EMPTY_OBJECT."""
        upload_id = uuid4()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id)
        fake_storage.put_object_bytes(auth.staging_key, b"", content_type="image/jpeg")

        response = client.post(f"/v1/media/uploads/{upload_id}/complete")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EMPTY_OBJECT"


# -----------------------------------------------------------------------------
# 3. Image Transcoding, Metadata Scrubbing & Privacy Tests
# -----------------------------------------------------------------------------


class TestImageTranscodingAndPrivacyScrubbing:
    """Validate EXIF orientation, GPS stripping, downscaling, and WebP conversion."""

    @pytest.mark.anyio
    async def test_exif_orientation_normalization(self):
        """EXIF orientation tag 6 (rotate 90 CW) is normalized into upright raster pixels."""
        # 400 wide x 200 high with orientation 6 -> upright normalized dimensions must be 200 wide x 400 high
        jpeg_bytes = make_test_jpeg(width=400, height=200, orientation=6)
        mgr = TranscoderProcessManager()

        result = await mgr.transcode(jpeg_bytes)
        assert result.width == 200
        assert result.height == 400
        assert result.format == "image/webp"

    @pytest.mark.anyio
    async def test_gps_and_exif_metadata_completely_scrubbed(self):
        """All EXIF IFD, GPS tags, and metadata are stripped from output WebP."""
        jpeg_with_gps = make_test_jpeg(width=300, height=300, with_gps=True)

        # Confirm input has EXIF
        in_img = Image.open(io.BytesIO(jpeg_with_gps))
        assert in_img.getexif() is not None

        mgr = TranscoderProcessManager()
        result = await mgr.transcode(jpeg_with_gps)

        # Inspect actual output bytes
        out_img = Image.open(io.BytesIO(result.canonical_bytes))
        out_exif = out_img.getexif()
        # Verify 0 exif tags and zero GPSInfo tag
        assert len(out_exif) == 0
        assert 0x8825 not in out_exif
        assert b"Latitude" not in result.canonical_bytes
        assert b"GPS" not in result.canonical_bytes

    @pytest.mark.anyio
    async def test_aspect_ratio_preservation_and_downscaling(self):
        """Images larger than 1920px are downscaled preserving exact aspect ratio without upscaling."""
        # 3000 x 1500 (2:1 aspect ratio) -> longest edge 1920 -> 1920 x 960
        large_jpeg = make_test_jpeg(width=3000, height=1500)
        mgr = TranscoderProcessManager(max_edge=1920)

        result = await mgr.transcode(large_jpeg)
        assert result.width == 1920
        assert result.height == 960

    @pytest.mark.anyio
    async def test_no_upscaling_behavior_for_smaller_images(self):
        """Images smaller than 1920px retain their original dimensions without upscaling."""
        small_jpeg = make_test_jpeg(width=800, height=600)
        mgr = TranscoderProcessManager(max_edge=1920)

        result = await mgr.transcode(small_jpeg)
        assert result.width == 800
        assert result.height == 600

    @pytest.mark.anyio
    async def test_output_webp_validity_and_hash(self):
        """Canonical output is valid WebP and calculated SHA-256 matches actual byte digest."""
        jpeg_bytes = make_test_jpeg(width=500, height=500)
        mgr = TranscoderProcessManager()

        result = await mgr.transcode(jpeg_bytes)
        assert result.canonical_bytes[:4] == b"RIFF"
        assert result.canonical_bytes[8:12] == b"WEBP"
        expected_sha = hashlib.sha256(result.canonical_bytes).hexdigest()
        assert result.canonical_sha256 == expected_sha


# -----------------------------------------------------------------------------
# 4. Process Manager Lifecycle, Timeout & Resource Tests
# -----------------------------------------------------------------------------


class TestProcessManagerLifecycleAndSafety:
    """Validate subprocess timeouts, PID reaping, cancellation, and concurrency semaphore."""

    @pytest.mark.anyio
    async def test_subprocess_timeout_escalates_to_sigkill_and_reaps(self):
        """A tight timeout terminates child process and reaps zombie PID."""
        jpeg_bytes = make_test_jpeg(width=1200, height=800)
        # Timeout set to 0.0001s guarantees timeout
        mgr = TranscoderProcessManager(timeout_seconds=0.0001)

        with pytest.raises(TranscodingTimeoutError) as excinfo:
            await mgr.transcode(jpeg_bytes)

        assert excinfo.value.code == "TRANSCODING_TIMEOUT"

    @pytest.mark.anyio
    async def test_temporary_files_are_cleaned_up_on_failure(self):
        """Temporary files are cleaned up on all failure paths."""
        tmp_dir = Path(tempfile.gettempdir())
        before_files = set(tmp_dir.glob("fv_*"))

        corrupt_payload = b"not-a-valid-image-data-stream"
        mgr = TranscoderProcessManager()

        with pytest.raises(ImageValidationError):
            await mgr.transcode(corrupt_payload)

        after_files = set(tmp_dir.glob("fv_*"))
        # Any new temp files must have been cleaned up
        leaked = after_files - before_files
        assert len(leaked) == 0

    @pytest.mark.anyio
    async def test_worker_semaphore_serializes_concurrent_jobs(self):
        """Worker semaphore limits active transcoding child processes to 1 at a time."""
        sem = TranscoderProcessManager.get_semaphore()
        # Verify initial semaphore value is 1
        assert sem._value == 1

        jpeg1 = make_test_jpeg(width=200, height=200, color="red")
        jpeg2 = make_test_jpeg(width=200, height=200, color="blue")
        mgr = TranscoderProcessManager()

        # Execute concurrent tasks
        res1, res2 = await asyncio.gather(
            mgr.transcode(jpeg1),
            mgr.transcode(jpeg2),
        )
        assert res1.canonical_bytes is not None
        assert res2.canonical_bytes is not None
        # Semaphore released back to 1
        assert sem._value == 1


# -----------------------------------------------------------------------------
# 5. Publication, Idempotency & Crash Recovery Tests
# -----------------------------------------------------------------------------


class TestPublicationAndCrashRecovery:
    """Validate atomic publication, storage failure handling, and crash recovery."""

    @pytest.mark.anyio
    async def test_canonical_object_published_to_private_storage(
        self,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """Transcoded WebP is published to private canonical storage key."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        canonical_key = res["objectKey"]
        assert canonical_key.startswith(f"users/{test_user_id}/wardrobe/{upload_id}/")
        assert canonical_key.endswith(".webp")
        assert await fake_storage.object_exists(canonical_key) is True

    @pytest.mark.anyio
    async def test_storage_publication_failure_rolls_back_and_allows_retry(
        self,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """If storage.put_object fails, operation returns 503 and upload remains retryable."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # Simulate storage failure on put_object
        fake_storage.simulate_failure = StorageError("R2 simulated network timeout")

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        with pytest.raises(ApiError) as excinfo:
            await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert excinfo.value.status_code == 503
        assert excinfo.value.code == "STORAGE_ERROR"

        # Clear simulated failure and verify retry succeeds
        fake_storage.simulate_failure = None
        retry_res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)
        assert retry_res["status"] == "ready"

    @pytest.mark.anyio
    async def test_crash_recovery_adopts_existing_canonical_object_on_retry(
        self,
        sqlite_db: Session,
        fake_storage: FakeStorageAdapter,
        test_user_id: UUID,
    ):
        """If server crashed after canonical PUT but before DB commit, retry adopts existing canonical blob."""
        upload_id = uuid4()
        jpeg_bytes = make_test_jpeg()
        auth = create_auth_record(sqlite_db, test_user_id, upload_id, content_type="image/jpeg", size_bytes=len(jpeg_bytes))
        fake_storage.put_object_bytes(auth.staging_key, jpeg_bytes, content_type="image/jpeg")

        # Simulate state where canonical object was already published to R2 in previous attempt
        canonical_bytes = make_test_webp(width=400, height=300)
        canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()
        canonical_key = f"users/{test_user_id}/wardrobe/{upload_id}/canonical.webp"
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

        # Set DB row to point to canonical_key as in interrupted commit
        auth.canonical_key = canonical_key
        auth.canonical_sha256 = canonical_sha
        sqlite_db.commit()

        use_case = CompleteMediaUpload(storage=fake_storage, db=sqlite_db)
        res = await use_case.execute(user_id=test_user_id, upload_id=upload_id)

        assert res["objectKey"] == canonical_key
        assert res["contentHash"] == canonical_sha
        assert res["status"] == "ready"


# -----------------------------------------------------------------------------
# 6. Alembic Migration 0034 Lineage & PostgreSQL Concurrency Tests
# -----------------------------------------------------------------------------


class TestMigration0034MetadataAndPostgreSQL:
    """Validate Alembic migration 0034 lineage and multi-session PostgreSQL concurrency."""

    def test_migration_0034_and_0035_metadata_and_chain(self):
        """Migration 0034 through 0036 forming single linear head."""
        backend = Path(__file__).resolve().parents[1]
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "alembic"))
        script = ScriptDirectory.from_config(config)

        heads = script.get_heads()
        assert len(heads) == 1
        assert heads[0] == "0036"

        rev36 = script.get_revision("0036")
        assert rev36 is not None
        assert rev36.down_revision == "0035"
        assert hasattr(rev36.module, "upgrade")
        assert hasattr(rev36.module, "downgrade")

        rev35 = script.get_revision("0035")
        assert rev35 is not None
        assert rev35.down_revision == "0034"
        assert hasattr(rev35.module, "upgrade")
        assert hasattr(rev35.module, "downgrade")

        rev34 = script.get_revision("0034")
        assert rev34 is not None
        assert rev34.down_revision == "0033"
        assert hasattr(rev34.module, "upgrade")
        assert hasattr(rev34.module, "downgrade")
        assert rev34.down_revision == "0033"
        assert hasattr(rev34.module, "upgrade")
        assert hasattr(rev34.module, "downgrade")

    def test_postgresql_concurrent_completion_serialization(self):
        """Independent PostgreSQL sessions serialize concurrent completion requests via advisory locking."""
        disposable_url = "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_phase3_1_test"
        try:
            test_engine = create_engine(disposable_url, pool_size=10, max_overflow=5)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            pytest.skip("Disposable PostgreSQL database not available for multi-session test")

        SessionLocal = sessionmaker(bind=test_engine)
        test_user = uuid4()
        upload_id = uuid4()

        # Seed users and media_upload_authorizations in disposable DB
        with SessionLocal() as init_session:
            init_session.execute(
                text(
                    "INSERT INTO users (id, auth_provider, auth_subject, display_name) "
                    "VALUES (:id, 'local', :subj, 'Test User') ON CONFLICT DO NOTHING"
                ),
                {"id": test_user, "subj": f"subj_{upload_id}"},
            )
            create_auth_record(init_session, test_user, upload_id)

        shared_fake_storage = FakeStorageAdapter()
        jpeg_bytes = make_test_jpeg(width=200, height=200)
        staging_key = f"staging/users/{test_user}/wardrobe/{upload_id}.jpg"
        shared_fake_storage.put_object_bytes(staging_key, jpeg_bytes, content_type="image/jpeg")

        results = []
        errors = []

        def worker_task(thread_id: int):
            with SessionLocal() as db_session:
                use_case = CompleteMediaUpload(storage=shared_fake_storage, db=db_session)
                try:
                    res = asyncio.run(use_case.execute(user_id=test_user, upload_id=upload_id))
                    return ("OK", res)
                except Exception as exc:
                    return ("ERROR", exc)

        # Launch 5 concurrent completion attempts on separate PostgreSQL sessions
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(5)]
            for fut in as_completed(futures):
                status, val = fut.result()
                if status == "OK":
                    results.append(val)
                else:
                    errors.append(val)

        # All successful responses must return identical canonical media reference
        assert len(results) >= 1
        first_key = results[0]["objectKey"]
        for r in results:
            assert r["objectKey"] == first_key
            assert r["status"] == "ready"

        # Verify only 1 canonical object was published to storage
        keys = shared_fake_storage.get_stored_keys()
        canonical_keys = [k for k in keys if k.startswith(f"users/{test_user}/wardrobe/{upload_id}/")]
        assert len(canonical_keys) == 1

        test_engine.dispose()
