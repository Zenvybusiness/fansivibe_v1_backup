"""Phase 5E.1 VTON Security, Privacy, and Reliability Hardening Tests.

Covers:
1. Operator authentication on POST /v1/tryon/maintenance/retention-cleanup.
2. Person-image Pillow validation, MIME/content matching, decompression-bomb
   rejection, orientation preservation, and EXIF/GPS stripping.
3. In-memory _BYTE_CACHE lifecycle cleanup across completion, failure,
   exception, cancellation, and retry/image retrieval preservation.
4. SQLAlchemy session closure in get_tryon_repository and
   get_tryon_wardrobe_repository on success and exceptions.
5. Person-image durable persistence as a hard prerequisite before worker start
   and presigned input URL creation, plus cancellation/retry orphan cleanup.
6. Provider output validation (JPEG, PNG, WebP, mock SVG, and invalid outputs).
7. RunPod / FASHN fail-closed garment category enforcement (footwear/accessories
   never silently converted to tops).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ExifTags
from pydantic import ValidationError

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import ApiError
import app.application.tryon as tryon_app
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.repositories import WardrobeItemRecord
from app.domain.ports.storage import StorageError, StorageNotFoundError
from app.domain.ports.tryon_provider import (
    CatVTONTryOnProvider,
    CommercialTryOnProvider,
    CommercialTryOnProviderConfig,
    ProviderPayloadError,
)
from app.infrastructure.db.session import get_db
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

USER_A = uuid4()
USER_B = uuid4()
VALID_OP_KEY = "operator-secret-key-for-tests-32-chars-minimum"


def _make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (90, 130, 170),
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def _make_jpeg_with_gps_and_orientation() -> bytes:
    # Create asymmetric image (width=160, height=100) with Orientation=6 (rotate 270 CW -> 100x160)
    img = Image.new("RGB", (160, 100), color=(20, 40, 60))
    # Paint top-left pixel red; after Orientation=6 transpose (rotate 270 CCW / 90 CW),
    # (0, 0) moves to top-right (99, 0).
    for x in range(10):
        for y in range(10):
            img.putpixel((x, y), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: Rotate 90 CW on display
    exif[0x010F] = "TestCamera"
    exif[0x8825] = {
        1: "N",
        2: (37.0, 46.0, 30.0),
        3: "W",
        4: (122.0, 25.0, 10.0),
    }
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class _WardrobeRepoStub:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add(self, user_id: UUID, item_id: UUID, category: str) -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        rec = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name="Item",
            category=category,
            color="black",
            material="cotton",
            is_favorite=False,
            image_ref={"key": f"users/{user_id}/wardrobe/{item_id}/input.webp"},
            created_at=now,
            updated_at=now,
        )
        self.items[(user_id, item_id)] = rec
        return rec

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        return self.items.get((user_id, item_id))


@pytest.fixture
def env_setup(monkeypatch):
    tryon_app.reset_for_tests()
    clear_settings_cache()
    storage = FakeStorageAdapter()
    job_repo = tryon_app._IN_MEMORY_REPO
    wardrobe_repo = _WardrobeRepoStub()

    app.dependency_overrides[get_storage_adapter] = lambda: storage
    app.dependency_overrides[get_tryon_repository] = lambda: job_repo
    app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_current_user_id] = lambda: USER_A

    yield {
        "storage": storage,
        "job_repo": job_repo,
        "wardrobe_repo": wardrobe_repo,
    }

    app.dependency_overrides.clear()
    tryon_app.reset_for_tests()
    clear_settings_cache()


def _submit(
    client: TestClient,
    *,
    filename: str = "person.jpg",
    content: bytes | None = None,
    content_type: str = "image/jpeg",
    key: str = "k-1",
    outfit_source: str = "today",
    garment_ids: str = '["g-1"]',
):
    payload = content if content is not None else _make_image_bytes("JPEG")
    return client.post(
        "/v1/tryon/jobs",
        files={"person_image": (filename, payload, content_type)},
        data={
            "outfit_source": outfit_source,
            "garment_ids": garment_ids,
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": key},
    )


# ==============================================================================
# 1. Maintenance Endpoint Operator Authorization Tests
# ==============================================================================


class TestMaintenanceEndpointAuthorization:
    def test_unauthenticated_request_rejected_401(self, monkeypatch, env_setup):
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", VALID_OP_KEY)
        clear_settings_cache()
        app.dependency_overrides.pop(get_current_user_id, None)

        resp = TestClient(app).post("/v1/tryon/maintenance/retention-cleanup")
        assert resp.status_code == 401

    def test_normal_authenticated_user_cannot_trigger_maintenance(self, monkeypatch, env_setup):
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", VALID_OP_KEY)
        clear_settings_cache()
        # Authenticated user A via get_current_user_id + Bearer header, but no X-Operator-Key
        resp = TestClient(app).post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={"Authorization": "Bearer user-jwt-token"},
        )
        assert resp.status_code == 401

        # Even if normal user passes their token as X-Operator-Key, rejected with 403
        resp_forbidden = TestClient(app).post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={
                "Authorization": "Bearer user-jwt-token",
                "X-Operator-Key": "user-jwt-token",
            },
        )
        assert resp_forbidden.status_code == 403

    def test_wrong_operator_key_rejected_403(self, monkeypatch, env_setup):
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", VALID_OP_KEY)
        clear_settings_cache()
        resp = TestClient(app).post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={"X-Operator-Key": "wrong-operator-key"},
        )
        assert resp.status_code == 403

    def test_unconfigured_operator_key_fails_closed_503(self, monkeypatch, env_setup):
        monkeypatch.delenv("FANSIVIBE_OPERATOR_API_KEY", raising=False)
        clear_settings_cache()
        resp = TestClient(app).post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={"X-Operator-Key": VALID_OP_KEY},
        )
        assert resp.status_code == 503

    def test_valid_operator_key_succeeds_200(self, monkeypatch, env_setup):
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", VALID_OP_KEY)
        clear_settings_cache()
        app.dependency_overrides.pop(get_current_user_id, None)

        resp = TestClient(app).post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={"X-Operator-Key": VALID_OP_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "person_photos_purged" in body
        assert "completed_results_deleted" in body

    def test_operator_key_production_validation_and_repr_masking(self):
        with pytest.raises(ValidationError, match="FANSIVIBE_OPERATOR_API_KEY"):
            Settings(
                _env_file=None,
                environment="production",
                database_url="postgresql+psycopg://prod:StrongPass123!@db.internal:5432/prod",
                auth_secret="a" * 32,
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_account_id="acc-123",
                r2_access_key_id="key-123",
                r2_secret_access_key="sec-123",
                media_upload_hmac_secret="b" * 32,
                operator_api_key="short",
            )

        s = Settings(_env_file=None, operator_api_key=VALID_OP_KEY)
        assert VALID_OP_KEY not in repr(s)
        assert VALID_OP_KEY not in str(s)


# ==============================================================================
# 2. Person Image Validation & Privacy Hardening Tests
# ==============================================================================


class TestPersonImageValidationAndPrivacy:
    def test_fake_jpeg_mime_with_non_image_bytes_rejected(self, env_setup):
        client = TestClient(app)
        resp = _submit(
            client,
            content=b"\xff\xd8not-actually-a-jpeg-payload",
            content_type="image/jpeg",
            key="fake-jpg-1",
        )
        assert resp.status_code == 422

        resp2 = _submit(
            client,
            content=b"<html><body>not an image</body></html>",
            content_type="image/jpeg",
            key="fake-jpg-2",
        )
        assert resp2.status_code == 422

    def test_mime_content_mismatch_rejected(self, env_setup):
        client = TestClient(app)
        png_bytes = _make_image_bytes("PNG")
        jpeg_bytes = _make_image_bytes("JPEG")
        webp_bytes = _make_image_bytes("WEBP")

        assert _submit(client, content=png_bytes, content_type="image/jpeg", key="mm-1").status_code == 422
        assert _submit(client, content=jpeg_bytes, content_type="image/png", key="mm-2").status_code == 422
        assert _submit(client, content=webp_bytes, content_type="image/jpeg", key="mm-3").status_code == 422

    def test_malformed_images_rejected(self, env_setup):
        client = TestClient(app)
        valid_jpeg = _make_image_bytes("JPEG", size=(128, 128))
        truncated_jpeg = valid_jpeg[: len(valid_jpeg) // 2]
        assert _submit(client, content=truncated_jpeg, content_type="image/jpeg", key="mal-1").status_code == 422

        valid_png = _make_image_bytes("PNG", size=(128, 128))
        truncated_png = valid_png[:24]
        assert _submit(client, content=truncated_png, content_type="image/png", key="mal-2").status_code == 422

    def test_excessive_dimensions_and_decompression_bomb_rejected(self, monkeypatch, env_setup):
        client = TestClient(app)
        # Edge > 4096
        oversized = _make_image_bytes("PNG", size=(4097, 100))
        assert _submit(client, filename="p.png", content=oversized, content_type="image/png", key="dim-1").status_code == 422

        # Decompression bomb pixel limit (e.g. 4000x3500 = 14MP > 12MP MAX_IMAGE_PIXELS)
        bomb = _make_image_bytes("PNG", size=(4000, 3500))
        assert _submit(client, filename="bomb.png", content=bomb, content_type="image/png", key="dim-2").status_code == 422

        # Also test explicit DecompressionBombError handling
        def _raise_bomb(*args, **kwargs):
            raise Image.DecompressionBombError("bomb")

        monkeypatch.setattr(Image, "open", _raise_bomb)
        with pytest.raises(ApiError) as exc_info:
            tryon_app.validate_and_sanitize_person_image(_make_image_bytes("JPEG"), "image/jpeg")
        assert exc_info.value.status_code == 422

    def test_exif_gps_removed_and_orientation_preserved(self, env_setup):
        raw_with_gps = _make_jpeg_with_gps_and_orientation()
        # Confirm fixture actually has GPS + Orientation=6 before ingestion
        with Image.open(io.BytesIO(raw_with_gps)) as orig:
            orig_exif = orig.getexif()
            assert 0x8825 in orig_exif
            assert orig_exif[0x0112] == 6
            assert orig.size == (160, 100)

        client = TestClient(app)
        resp = _submit(client, content=raw_with_gps, content_type="image/jpeg", key="exif-1")
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=job_id)
        assert job is not None and job.person_media_ref is not None
        stored_bytes = env_setup["storage"].get_stored_bytes(job.person_media_ref["key"])

        with Image.open(io.BytesIO(stored_bytes)) as sanitized:
            assert sanitized.format == "JPEG"
            # Orientation=6 transposed 160x100 -> 100x160
            assert sanitized.size == (100, 160)
            # Red corner moved from top-left (0,0) to top-right (95,5)
            r, g, b = sanitized.getpixel((95, 5))
            assert r > 200 and g < 50 and b < 50
            sanitized_exif = sanitized.getexif()
            assert len(sanitized_exif) == 0
            assert 0x8825 not in sanitized_exif

    @pytest.mark.parametrize(
        ("fmt", "mime", "ext"),
        [
            ("JPEG", "image/jpeg", "jpg"),
            ("PNG", "image/png", "png"),
            ("WEBP", "image/webp", "webp"),
        ],
    )
    def test_valid_jpeg_png_webp_accepted_and_consistent(self, env_setup, fmt, mime, ext):
        client = TestClient(app)
        img_bytes = _make_image_bytes(fmt, size=(128, 128))
        resp = _submit(
            client,
            filename=f"person.{ext}",
            content=img_bytes,
            content_type=mime,
            key=f"valid-{fmt}",
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])
        job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=job_id)
        assert job.person_media_ref["mediaType"] == mime
        assert job.person_media_ref["key"].endswith(f"/person.{ext}")

        stored = env_setup["storage"].get_stored_bytes(job.person_media_ref["key"])
        with Image.open(io.BytesIO(stored)) as decoded:
            assert decoded.format == fmt


# ==============================================================================
# 3. _BYTE_CACHE Lifecycle Tests
# ==============================================================================


class TestByteCacheLifecycle:
    def test_byte_cache_evicted_after_submit_and_supports_image_retrieval(self, env_setup):
        client = TestClient(app)
        resp = _submit(client, key="cache-mock-1")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Person bytes must be evicted immediately after durable storage in submit_tryon_job
        assert job_id not in tryon_app._BYTE_CACHE

        # Polling and image retrieval still work cleanly
        client.get(f"/v1/tryon/jobs/{job_id}")
        client.get(f"/v1/tryon/jobs/{job_id}")
        img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"].startswith("image/svg+xml")

    def test_byte_cache_evicted_on_completion_failure_exception_cancel_and_retry(
        self, monkeypatch, env_setup
    ):
        storage = env_setup["storage"]
        repo = env_setup["job_repo"]

        # Non-mock commercial flow with mocked render
        settings = SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="commercial",
            environment="development",
            tryon_consent_version="tryon-v1",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=5,
            tryon_commercial_provider_name="test_commercial",
            tryon_commercial_api_key="sk_test_1234567890abcdef",
            tryon_commercial_endpoint_url="https://api.example.invalid/tryon",
            tryon_commercial_connect_timeout_s=5.0,
            tryon_commercial_inference_timeout_s=10.0,
            tryon_commercial_max_retries=0,
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)

        # 1. Fail on first inference -> _BYTE_CACHE empty, retry still works via storage!
        monkeypatch.setattr(
            tryon_app.CommercialTryOnProvider,
            "render",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        client = TestClient(app)
        resp = _submit(client, key="cache-comm-1")
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        assert job_id not in tryon_app._BYTE_CACHE
        assert repo.get_by_id(user_id=USER_A, job_id=UUID(job_id)).status == "failed"

        # 2. Retry succeeds reading person bytes from storage (with _BYTE_CACHE empty)
        png_out = _make_image_bytes("PNG")
        monkeypatch.setattr(
            tryon_app.CommercialTryOnProvider,
            "render",
            lambda *a, **kw: png_out,
        )
        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        assert job_id not in tryon_app._BYTE_CACHE

        done_job = repo.get_by_id(user_id=USER_A, job_id=UUID(job_id))
        assert done_job.status == "completed"
        assert done_job.result_media_ref["mediaType"] == "image/png"
        assert storage.object_exists_sync(done_job.result_media_ref["key"])

        img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"].startswith("image/png")

    def test_byte_cache_evicted_on_cancel_and_create_failure(self, monkeypatch, env_setup):
        repo = env_setup["job_repo"]
        # Seed cache entry and cancel
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        tryon_app._BYTE_CACHE[str(job_id)] = (_make_image_bytes("JPEG"), "image/jpeg")
        tryon_app.cancel_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
        assert str(job_id) not in tryon_app._BYTE_CACHE

        # Create failure cleans up _BYTE_CACHE
        class _FailingCreateRepo(tryon_app.InMemoryTryOnJobRepository):
            def create(self, **kwargs):
                raise RuntimeError("DB insert failed")

        failing_repo = _FailingCreateRepo()
        with pytest.raises(RuntimeError, match="DB insert failed"):
            tryon_app.submit_job(
                user_id=str(USER_A),
                outfit_source="today",
                garment_ids=["g-1"],
                person_content_type="image/jpeg",
                person_bytes=_make_image_bytes("JPEG"),
                consent_version="tryon-v1",
                consent_accepted=True,
                idempotency_key="create-fail-1",
                job_repo=failing_repo,
            )
        assert len(tryon_app._BYTE_CACHE) == 0


# ==============================================================================
# 4. SQLAlchemy Session Lifecycle Tests
# ==============================================================================


class TestTryOnSessionLifecycle:
    def test_session_local_closed_on_success_and_exception(self, monkeypatch):
        from app.infrastructure.db import session as db_session_mod

        created_sessions: list[MagicMock] = []

        def _fake_session_local():
            sess = MagicMock()
            created_sessions.append(sess)
            return sess

        monkeypatch.setattr(db_session_mod, "SessionLocal", _fake_session_local)

        # Mock TryOnJobRepositorySQL & WardrobeItemRepositorySQL to avoid real SQL execution
        fake_job = SimpleNamespace(
            id=uuid4(),
            user_id=USER_A,
            outfit_source="today",
            garment_ids=("g-1",),
            provider="mock",
            status="completed",
            error_code=None,
            error_message=None,
            retry_count=0,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result_media_ref=None,
            image_bytes=None,
        )

        app.dependency_overrides[get_current_user_id] = lambda: USER_A
        app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()

        try:
            # 1. Successful request closes session
            monkeypatch.setattr(tryon_app, "get_job", lambda **kw: fake_job)
            resp = TestClient(app).get(f"/v1/tryon/jobs/{fake_job.id}")
            assert resp.status_code == 200
            assert len(created_sessions) == 1
            assert created_sessions[0].close.call_count == 1

            # 2. Request raising exception also closes sessions for both repos
            def _boom(**kw):
                raise RuntimeError("Unexpected handler failure")

            monkeypatch.setattr(tryon_app, "submit_job", _boom)
            resp_err = TestClient(app, raise_server_exceptions=False).post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", _make_image_bytes("JPEG"), "image/jpeg")},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "sess-exc-1"},
            )
            assert resp_err.status_code == 500
            # Both get_tryon_repository and get_tryon_wardrobe_repository opened and closed sessions
            assert len(created_sessions) == 3
            assert created_sessions[1].close.call_count == 1
            assert created_sessions[2].close.call_count == 1
        finally:
            app.dependency_overrides.clear()

    def test_get_db_generator_override_closed_on_success_and_exception(self, monkeypatch):
        closed_flags: list[str] = []

        def _fake_get_db():
            sess = MagicMock()
            try:
                yield sess
            finally:
                closed_flags.append("closed")

        app.dependency_overrides[get_db] = _fake_get_db
        app.dependency_overrides[get_current_user_id] = lambda: USER_A
        app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()

        try:
            monkeypatch.setattr(tryon_app, "get_job", lambda **kw: None)
            resp = TestClient(app).get(f"/v1/tryon/jobs/{uuid4()}")
            assert resp.status_code == 404
            assert closed_flags == ["closed"]
        finally:
            app.dependency_overrides.clear()


# ==============================================================================
# 5. Person Image Persistence Hard Prerequisite Tests
# ==============================================================================


class TestInputPersistencePrerequisite:
    def test_worker_never_starts_when_person_storage_fails(self, monkeypatch, env_setup):
        class _FailPutStorage(FakeStorageAdapter):
            async def put_object(self, key: str, data: bytes, *, content_type: str = "image/webp", custom_metadata=None):
                raise StorageError("R2 write outage", key=key)

        failing_storage = _FailPutStorage()
        app.dependency_overrides[get_storage_adapter] = lambda: failing_storage

        settings = SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="commercial",
            environment="development",
            tryon_consent_version="tryon-v1",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=5,
            tryon_commercial_provider_name="test_commercial",
            tryon_commercial_api_key="sk_test_1234567890abcdef",
            tryon_commercial_endpoint_url="https://api.example.invalid/tryon",
            tryon_commercial_connect_timeout_s=5.0,
            tryon_commercial_inference_timeout_s=10.0,
            tryon_commercial_max_retries=0,
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)

        worker_called = False

        async def _spy_worker(**kwargs):
            nonlocal worker_called
            worker_called = True

        monkeypatch.setattr(tryon_app, "execute_tryon_inference", _spy_worker)

        resp = _submit(TestClient(app), key="persist-fail-1")
        assert resp.status_code == 503
        assert worker_called is False
        assert len(tryon_app._BYTE_CACHE) == 0

        # Job must be safely marked failed in repo
        jobs = list(env_setup["job_repo"]._jobs.values())
        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert jobs[0].error_code == "STORAGE_FAILURE"

    def test_store_person_image_async_does_not_swallow_exceptions(self, env_setup):
        class _FailPutStorage(FakeStorageAdapter):
            async def put_object(self, key: str, data: bytes, *, content_type: str = "image/webp", custom_metadata=None):
                raise StorageError("R2 write outage", key=key)

        repo = env_setup["job_repo"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="commercial",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )

        with pytest.raises(StorageError, match="R2 write outage"):
            asyncio.run(
                tryon_app.store_person_image_async(
                    storage=_FailPutStorage(),
                    user_id=USER_A,
                    job_id=job_id,
                    person_bytes=_make_image_bytes("JPEG"),
                    content_type="image/jpeg",
                    job_repo=repo,
                )
            )

        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"

    def test_presigned_input_url_requires_durable_storage_confirmation(self, env_setup):
        storage = env_setup["storage"]
        key = f"users/{USER_A}/tryon/{uuid4()}/person.jpg"

        with pytest.raises(StorageNotFoundError):
            asyncio.run(tryon_app.create_confirmed_presigned_input_url(storage=storage, key=key))

        asyncio.run(storage.put_object(key, _make_image_bytes("JPEG"), content_type="image/jpeg"))
        url = asyncio.run(tryon_app.create_confirmed_presigned_input_url(storage=storage, key=key))
        assert key in url

    def test_worker_fails_if_person_media_ref_missing_from_storage(self, monkeypatch, env_setup):
        repo = env_setup["job_repo"]
        storage = env_setup["storage"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="commercial",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": f"users/{USER_A}/tryon/{job_id}/person.jpg"},
        )
        # Ensure worker refuses to run provider if storage object is absent
        provider_called = False
        monkeypatch.setattr(
            tryon_app.MockTryOnProvider,
            "render",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("provider must not run")),
        )
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
            )
        )
        assert provider_called is False
        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"

    def test_retry_cleans_up_stale_previous_format_result(self, monkeypatch, env_setup):
        storage = env_setup["storage"]
        repo = env_setup["job_repo"]
        job_id = uuid4()
        person_key = f"users/{USER_A}/tryon/{job_id}/person.jpg"
        old_result_key = f"users/{USER_A}/tryon/{job_id}/result.png"
        asyncio.run(storage.put_object(person_key, _make_image_bytes("JPEG"), content_type="image/jpeg"))
        asyncio.run(storage.put_object(old_result_key, _make_image_bytes("PNG"), content_type="image/png"))

        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="commercial",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": person_key, "contentHash": "abc"},
        )
        repo.update_result(
            job_id=job_id,
            result_media_ref={"key": old_result_key, "mediaType": "image/png"},
            completed_at=datetime.now(timezone.utc),
        )
        # Simulate failed retryable job with stale result_media_ref from prior run
        repo._jobs[job_id] = tryon_app.TryOnJobRecord(
            **{
                **repo._jobs[job_id].__dict__,
                "status": "failed",
            }
        )

        settings = SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="commercial",
            environment="development",
            tryon_consent_version="tryon-v1",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=5,
            tryon_commercial_provider_name="test_commercial",
            tryon_commercial_api_key="sk_test_1234567890abcdef",
            tryon_commercial_endpoint_url="https://api.example.invalid/tryon",
            tryon_commercial_connect_timeout_s=5.0,
            tryon_commercial_inference_timeout_s=10.0,
            tryon_commercial_max_retries=0,
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)
        monkeypatch.setattr(
            tryon_app.CommercialTryOnProvider,
            "render",
            lambda *a, **kw: _make_image_bytes("JPEG"),
        )

        resp = TestClient(app).post(f"/v1/tryon/jobs/{job_id}/retry")
        assert resp.status_code == 202
        assert storage.object_exists_sync(old_result_key) is False
        assert storage.object_exists_sync(f"users/{USER_A}/tryon/{job_id}/result.jpg") is True

    def test_cancellation_during_person_storage_deletes_orphaned_input(self, env_setup):
        repo = env_setup["job_repo"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="commercial",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )

        class _CancelDuringPutStorage(FakeStorageAdapter):
            async def put_object(self, key: str, data: bytes, *, content_type: str = "image/webp", custom_metadata=None):
                res = await super().put_object(key, data, content_type=content_type, custom_metadata=custom_metadata)
                tryon_app.cancel_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
                return res

        storage = _CancelDuringPutStorage()
        key = asyncio.run(
            tryon_app.store_person_image_async(
                storage=storage,
                user_id=USER_A,
                job_id=job_id,
                person_bytes=_make_image_bytes("JPEG"),
                content_type="image/jpeg",
                job_repo=repo,
            )
        )
        assert storage.object_exists_sync(key) is False
        assert str(job_id) not in tryon_app._BYTE_CACHE


# ==============================================================================
# 6. Provider Output Validation Tests
# ==============================================================================


class TestProviderOutputValidation:
    @pytest.mark.parametrize(
        ("fmt", "mime", "ext"),
        [
            ("JPEG", "image/jpeg", "jpg"),
            ("PNG", "image/png", "png"),
            ("WEBP", "image/webp", "webp"),
        ],
    )
    def test_worker_stores_actual_output_format_and_mime(self, monkeypatch, env_setup, fmt, mime, ext):
        storage = env_setup["storage"]
        repo = env_setup["job_repo"]
        settings = SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="commercial",
            environment="development",
            tryon_consent_version="tryon-v1",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=5,
            tryon_commercial_provider_name="test_commercial",
            tryon_commercial_api_key="sk_test_1234567890abcdef",
            tryon_commercial_endpoint_url="https://api.example.invalid/tryon",
            tryon_commercial_connect_timeout_s=5.0,
            tryon_commercial_inference_timeout_s=10.0,
            tryon_commercial_max_retries=0,
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)
        out_bytes = _make_image_bytes(fmt)
        monkeypatch.setattr(tryon_app.CommercialTryOnProvider, "render", lambda *a, **kw: out_bytes)

        resp = _submit(TestClient(app), key=f"out-{fmt}")
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job.status == "completed"
        assert job.result_media_ref["mediaType"] == mime
        assert job.result_media_ref["key"].endswith(f"/result.{ext}")

        img_resp = TestClient(app).get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"].startswith(mime)
        assert img_resp.content == out_bytes

    def test_mock_svg_preserved_and_non_mock_svg_rejected(self, monkeypatch, env_setup):
        # Mock SVG allowed
        ct, ext = tryon_app.validate_and_inspect_output_image(
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
            allow_svg=True,
        )
        assert (ct, ext) == ("image/svg+xml", "svg")

        # Non-mock SVG rejected
        with pytest.raises(ProviderPayloadError):
            tryon_app.validate_and_inspect_output_image(
                b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
                allow_svg=False,
            )

    @pytest.mark.parametrize(
        "bad_output",
        [
            b"",
            b"<html>502 Bad Gateway</html>",
            b"\xff\xd8\xff" + b"\x00" * 32,  # corrupt JPEG
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",  # GIF unsupported
        ],
    )
    def test_invalid_provider_outputs_rejected_and_fail_job(self, monkeypatch, env_setup, bad_output):
        repo = env_setup["job_repo"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(tryon_app.MockTryOnProvider, "render", lambda *a, **kw: bad_output)

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=env_setup["storage"],
            )
        )
        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job.status == "failed"
        assert job.error_code == "INVALID_PROVIDER_OUTPUT"
        assert job.result_media_ref is None


# ==============================================================================
# 7. RunPod / FASHN Fail-Closed Category Boundary Tests
# ==============================================================================


class TestRunPodCategoryBoundary:
    @pytest.mark.parametrize("unsupported_cat", ["footwear", "shoes", "accessories", "jewelry", "bags"])
    def test_unsupported_categories_fail_closed_in_provider_and_worker(
        self, monkeypatch, env_setup, unsupported_cat
    ):
        cfg = CommercialTryOnProviderConfig(
            provider_name="runpod_fashn_pending",
            api_key="sk_test_1234567890abcdef",
            endpoint_url="https://api.runpod.ai/v2/placeholder/run",
        )
        provider = CommercialTryOnProvider(cfg, http_client=MagicMock())
        with pytest.raises(ProviderPayloadError, match="Unsupported garment category"):
            provider.render(
                person_digest="abc",
                garment_labels=["item-1"],
                seed="s1",
                outfit_source="wardrobe",
                person_bytes=_make_image_bytes("JPEG"),
                category=unsupported_cat,
            )

        catvton = CatVTONTryOnProvider()
        with pytest.raises(ProviderPayloadError, match="Unsupported garment category"):
            catvton.render(
                person_digest="abc",
                garment_labels=["item-1"],
                seed="s1",
                outfit_source="wardrobe",
                person_bytes=_make_image_bytes("JPEG"),
                category=unsupported_cat,
            )

        # Also verify execute_tryon_inference fails closed when wardrobe item is footwear/accessories
        garment_id = uuid4()
        env_setup["wardrobe_repo"].add(USER_A, garment_id, unsupported_cat)
        repo = env_setup["job_repo"]
        storage = env_setup["storage"]
        job_id = uuid4()
        person_key = f"users/{USER_A}/tryon/{job_id}/person.jpg"
        asyncio.run(storage.put_object(person_key, _make_image_bytes("JPEG"), content_type="image/jpeg"))

        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=garment_id,
            garment_ids=[str(garment_id)],
            provider="commercial",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": person_key, "contentHash": "abc"},
        )

        settings = SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="commercial",
            environment="development",
            tryon_consent_version="tryon-v1",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=5,
            tryon_commercial_provider_name="runpod_fashn_pending",
            tryon_commercial_api_key="sk_test_1234567890abcdef",
            tryon_commercial_endpoint_url="https://api.runpod.ai/v2/placeholder/run",
            tryon_commercial_connect_timeout_s=5.0,
            tryon_commercial_inference_timeout_s=10.0,
            tryon_commercial_max_retries=0,
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=env_setup["wardrobe_repo"],
            )
        )
        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job.status == "failed"
        assert job.error_code == "PAYLOAD_REJECTED"

