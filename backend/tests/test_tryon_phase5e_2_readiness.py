"""Phase 5E.2 VTON Integration Readiness, Pillow Configuration, and PostgreSQL Tests.

Covers:
1. Centralized Pillow configuration at application startup (no per-request global
   mutation of Image.MAX_IMAGE_PIXELS or ImageFile.LOAD_TRUNCATED_IMAGES),
   concurrent validation thread safety, decompression-bomb rejection, JPEG/PNG/WebP
   validation, and EXIF/GPS stripping + orientation correction.
2. Operator authentication enforcement and secret non-leakage in logs/errors/settings.
3. Real PostgreSQL integration tests (via `db` fixture on isolated test database):
   - VTON job persistence, cross-session survival, OW-1 isolation, idempotency
     unique constraint, and startup recovery.
   - Job cancellation, stale-worker protection, and retry count/status transitions.
   - Repository SQLAlchemy session lifecycle and zero connection leaks.
   - Background inference fresh-session lifecycle (_execute_inference_with_fresh_session)
     on both success and inference failure.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import logging
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFile
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
)
from app.api.errors import ApiError
import app.application.tryon as tryon_app
from app.config.image import (
    MAX_OUTPUT_IMAGE_PIXELS,
    MAX_PERSON_IMAGE_PIXELS,
    MAX_PILLOW_IMAGE_PIXELS,
    configure_pillow_limits,
)
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.tryon_provider import (
    ProviderPayloadError,
    validate_raster_image_bytes,
)
from app.infrastructure.db import session as db_session_mod
from app.infrastructure.db.models import UserState, Users
from app.infrastructure.db.repositories import TryOnJobRepositorySQL
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter


def _make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (90, 130, 170),
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def _make_jpeg_with_gps_and_orientation() -> bytes:
    img = Image.new("RGB", (160, 100), color=(20, 40, 60))
    for x in range(10):
        for y in range(10):
            img.putpixel((x, y), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6
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


def _seed_user(session, *, email: str) -> UUID:
    user = Users(
        auth_provider="local",
        auth_subject=email,
        display_name=email.split("@")[0],
    )
    session.add(user)
    session.flush()
    session.add(UserState(user_id=user.id))
    session.commit()
    return user.id


# ==============================================================================
# 1. Centralized Pillow Configuration & Concurrency Regression Tests
# ==============================================================================


class TestCentralizedPillowConfiguration:
    def test_startup_configures_pillow_limits_centrally(self) -> None:
        configure_pillow_limits()
        assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS
        assert Image.MAX_IMAGE_PIXELS == MAX_OUTPUT_IMAGE_PIXELS
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False

    def test_validations_do_not_mutate_global_pillow_settings(
        self, monkeypatch
    ) -> None:
        configure_pillow_limits()
        observed_limits: list[int | None] = []
        observed_truncated: list[bool] = []
        original_open = Image.open

        def _spy_open(*args, **kwargs):
            observed_limits.append(Image.MAX_IMAGE_PIXELS)
            observed_truncated.append(ImageFile.LOAD_TRUNCATED_IMAGES)
            return original_open(*args, **kwargs)

        monkeypatch.setattr(Image, "open", _spy_open)

        for fmt, mime in (
            ("JPEG", "image/jpeg"),
            ("PNG", "image/png"),
            ("WEBP", "image/webp"),
        ):
            raw = _make_image_bytes(fmt, size=(128, 128))
            sanitized, out_mime = tryon_app.validate_and_sanitize_person_image(raw, mime)
            assert out_mime == mime
            ct, _ext = tryon_app.validate_and_inspect_output_image(
                sanitized, allow_svg=False, provider_id="commercial"
            )
            assert ct == mime
            assert (
                validate_raster_image_bytes(
                    sanitized, "Test", provider_id="commercial"
                )
                == mime
            )

        assert observed_limits
        assert all(limit == MAX_PILLOW_IMAGE_PIXELS for limit in observed_limits)
        assert all(flag is False for flag in observed_truncated)
        assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False

    def test_concurrent_person_and_large_output_validation_thread_safe(self) -> None:
        configure_pillow_limits()
        person_jpeg = _make_jpeg_with_gps_and_orientation()
        # 4096x4096 = 16,777,216 pixels (valid output ceiling > 12MP person ceiling)
        large_output_png = _make_image_bytes("PNG", size=(4096, 4096), color=(10, 20, 30))

        def _run_person() -> tuple[int, int]:
            sanitized, mime = tryon_app.validate_and_sanitize_person_image(
                person_jpeg, "image/jpeg"
            )
            assert mime == "image/jpeg"
            assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS
            with Image.open(io.BytesIO(sanitized)) as img:
                assert len(img.getexif()) == 0
                return img.size

        def _run_output() -> tuple[str, str]:
            res = tryon_app.validate_and_inspect_output_image(
                large_output_png, allow_svg=False, provider_id="commercial"
            )
            assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS
            return res

        with ThreadPoolExecutor(max_workers=8) as pool:
            person_futures = [pool.submit(_run_person) for _ in range(8)]
            output_futures = [pool.submit(_run_output) for _ in range(4)]

            for fut in person_futures:
                assert fut.result() == (100, 160)
            for fut in output_futures:
                assert fut.result() == ("image/png", "png")

        assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS
        assert ImageFile.LOAD_TRUNCATED_IMAGES is False

    def test_decompression_bombs_rejected_above_person_and_output_limits(self) -> None:
        configure_pillow_limits()
        # 4000x3500 = 14MP > 12MP person limit
        person_14mp = _make_image_bytes("PNG", size=(4000, 3500))
        with pytest.raises(ApiError) as exc_info:
            tryon_app.validate_and_sanitize_person_image(person_14mp, "image/png")
        assert exc_info.value.status_code == 422

        # 5000x4000 = 20MP > 16.77MP central MAX_IMAGE_PIXELS (triggers DecompressionBombWarning -> error)
        bomb_20mp = _make_image_bytes("PNG", size=(5000, 4000))
        with pytest.raises(ApiError) as exc_bomb:
            tryon_app.validate_and_sanitize_person_image(bomb_20mp, "image/png")
        assert exc_bomb.value.status_code == 422

        with pytest.raises(ProviderPayloadError):
            tryon_app.validate_and_inspect_output_image(
                bomb_20mp, allow_svg=False, provider_id="commercial"
            )

        assert MAX_PERSON_IMAGE_PIXELS == 12_000_000
        assert Image.MAX_IMAGE_PIXELS == MAX_PILLOW_IMAGE_PIXELS


# ==============================================================================
# 2. Operator Auth Production Fail-Closed & Secret Non-Leakage Tests
# ==============================================================================


class TestOperatorAuthAndSecretNonLeakage:
    def test_missing_production_operator_credentials_fail_closed_without_secret_leak(
        self, monkeypatch, caplog
    ) -> None:
        monkeypatch.setenv("FANSIVIBE_ENV", "production")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://prod:ProdPass123!@db.internal:5432/prod",
        )
        monkeypatch.setenv("FANSIVIBE_AUTH_SECRET", "p" * 40)
        monkeypatch.setenv("FANSIVIBE_ALLOW_DEV_TOKEN", "false")
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_BUCKET_NAME", "prod-bucket")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acc-prod")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-prod")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sec-prod")
        monkeypatch.setenv("MEDIA_UPLOAD_HMAC_SECRET", "h" * 40)
        monkeypatch.delenv("FANSIVIBE_OPERATOR_API_KEY", raising=False)
        clear_settings_cache()

        supplied_secret = "caller-supplied-operator-secret-value-xyz"
        try:
            with caplog.at_level(logging.DEBUG):
                client = TestClient(app)
                resp_no_header = client.post("/v1/tryon/maintenance/retention-cleanup")
                assert resp_no_header.status_code == 401

                resp_with_header = client.post(
                    "/v1/tryon/maintenance/retention-cleanup",
                    headers={"X-Operator-Key": supplied_secret},
                )
                assert resp_with_header.status_code == 503
                assert resp_with_header.json()["error"]["code"] == "OPERATOR_AUTH_NOT_CONFIGURED"
                assert supplied_secret not in resp_with_header.text
                assert supplied_secret not in caplog.text
        finally:
            clear_settings_cache()

    def test_operator_secret_never_leaks_in_logs_or_errors(
        self, monkeypatch, caplog
    ) -> None:
        op_secret = "super-secret-operator-key-at-least-32-bytes"
        wrong_secret = "wrong-secret-attempt-that-must-not-be-logged"
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", op_secret)
        clear_settings_cache()
        app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()
        app.dependency_overrides[get_tryon_repository] = lambda: tryon_app._IN_MEMORY_REPO
        try:
            with caplog.at_level(logging.DEBUG):
                client = TestClient(app)
                r403 = client.post(
                    "/v1/tryon/maintenance/retention-cleanup",
                    headers={"X-Operator-Key": wrong_secret},
                )
                assert r403.status_code == 403
                assert op_secret not in r403.text
                assert wrong_secret not in r403.text

                r200 = client.post(
                    "/v1/tryon/maintenance/retention-cleanup",
                    headers={"X-Operator-Key": op_secret},
                )
                assert r200.status_code == 200
                assert op_secret not in r200.text
                assert op_secret not in caplog.text
                assert wrong_secret not in caplog.text
        finally:
            app.dependency_overrides.clear()
            clear_settings_cache()

    def test_real_minted_user_jwt_rejected_on_maintenance_endpoint(
        self, monkeypatch
    ) -> None:
        from app.application.auth import mint_access_token

        op_secret = "super-secret-operator-key-at-least-32-bytes"
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", op_secret)
        clear_settings_cache()
        user_jwt = mint_access_token(
            user_id=uuid4(),
            session_id=uuid4(),
            secret="test-only-auth-secret",
            expires_in_s=3600,
        )
        try:
            client = TestClient(app)
            r401 = client.post(
                "/v1/tryon/maintenance/retention-cleanup",
                headers={"Authorization": f"Bearer {user_jwt}"},
            )
            assert r401.status_code == 401

            r403 = client.post(
                "/v1/tryon/maintenance/retention-cleanup",
                headers={
                    "Authorization": f"Bearer {user_jwt}",
                    "X-Operator-Key": user_jwt,
                },
            )
            assert r403.status_code == 403
        finally:
            clear_settings_cache()


# ==============================================================================
# 3. Real PostgreSQL Integration Verification
# ==============================================================================


class TestPostgresTryOnIntegration:
    def _assert_disposable_db(self) -> None:
        db_name = db_session_mod.engine.url.database or ""
        assert db_name != "fansivibe", "Refusing to run integration tests against dev DB"

    def test_tryon_job_persistence_isolation_idempotency_and_recovery(self, db) -> None:
        self._assert_disposable_db()
        Session = db

        with Session() as s1:
            user_a = _seed_user(s1, email="pg-tryon-a@example.com")
            user_b = _seed_user(s1, email="pg-tryon-b@example.com")
            repo1 = TryOnJobRepositorySQL(s1)
            job_id = uuid4()
            created = repo1.create(
                job_id=job_id,
                user_id=user_a,
                outfit_source="today",
                garment_id=None,
                garment_ids=["g-1"],
                provider="commercial",
                status="queued",
                consent_version="tryon-v1",
                consent_accepted_at=datetime.now(timezone.utc),
                person_media_ref={"key": f"users/{user_a}/tryon/{job_id}/person.jpg"},
                idempotency_key="pg-idem-1",
                request_fingerprint="fp-1",
            )
            assert created.status == "queued"

            # Unique constraint (user_id, idempotency_key) from migration 0038 enforced in PG
            with pytest.raises(IntegrityError):
                repo1.create(
                    job_id=uuid4(),
                    user_id=user_a,
                    outfit_source="today",
                    garment_id=None,
                    garment_ids=["g-1"],
                    provider="commercial",
                    status="queued",
                    consent_version="tryon-v1",
                    consent_accepted_at=datetime.now(timezone.utc),
                    idempotency_key="pg-idem-1",
                    request_fingerprint="fp-2",
                )
            s1.rollback()

        # Verify survival in a completely separate SQLAlchemy session + OW-1 isolation
        with Session() as s2:
            repo2 = TryOnJobRepositorySQL(s2)
            loaded_a = repo2.get_by_id(user_id=user_a, job_id=job_id)
            assert loaded_a is not None
            assert loaded_a.id == job_id
            assert loaded_a.status == "queued"
            assert repo2.get_by_id(user_id=user_b, job_id=job_id) is None

            recovered = tryon_app.recover_interrupted_jobs(repo2)
            assert recovered == 1

        with Session() as s3:
            repo3 = TryOnJobRepositorySQL(s3)
            after_recover = repo3.get_by_id(user_id=user_a, job_id=job_id)
            assert after_recover is not None
            assert after_recover.status == "failed"
            assert after_recover.error_code == "INTERRUPTED_BY_RESTART"

    def test_job_cancellation_stale_worker_guard_and_retry_on_postgres(
        self, db, monkeypatch
    ) -> None:
        self._assert_disposable_db()
        Session = db
        with Session() as s:
            user_a = _seed_user(s, email="pg-cancel-a@example.com")
            repo = TryOnJobRepositorySQL(s)
            job_id = uuid4()
            repo.create(
                job_id=job_id,
                user_id=user_a,
                outfit_source="today",
                garment_id=None,
                garment_ids=["g-1"],
                provider="commercial",
                status="processing",
                consent_version="tryon-v1",
                consent_accepted_at=datetime.now(timezone.utc),
                person_media_ref={"key": f"users/{user_a}/tryon/{job_id}/person.jpg"},
                idempotency_key="pg-cancel-1",
                request_fingerprint="fp-cancel",
            )

        storage = FakeStorageAdapter()
        app.dependency_overrides[get_current_user_id] = lambda: user_a
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        monkeypatch.setattr(tryon_app, "execute_tryon_inference", lambda **kw: None)
        try:
            client = TestClient(app)
            cancel_resp = client.post(f"/v1/tryon/jobs/{job_id}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["status"] == "cancelled"

            # Stale worker attempt cannot overwrite cancelled job in PostgreSQL
            with Session() as s2:
                repo2 = TryOnJobRepositorySQL(s2)
                stale = repo2.update_result(
                    job_id=job_id,
                    result_media_ref={"key": f"users/{user_a}/tryon/{job_id}/result.png"},
                    completed_at=datetime.now(timezone.utc),
                )
                assert stale is not None
                assert stale.status == "cancelled"

            # Retry cancelled job increments retry_count in PostgreSQL
            async def _noop_async(**kw):
                return None

            monkeypatch.setattr(tryon_app, "execute_tryon_inference", _noop_async)
            retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
            assert retry_resp.status_code == 202

            with Session() as s3:
                repo3 = TryOnJobRepositorySQL(s3)
                retried = repo3.get_by_id(user_id=user_a, job_id=job_id)
                assert retried is not None
                assert retried.retry_count == 1
                assert retried.error_code is None
                assert retried.status == "processing"
        finally:
            app.dependency_overrides.clear()

    def test_repository_session_lifecycle_no_pool_leaks_on_postgres(
        self, db, monkeypatch
    ) -> None:
        self._assert_disposable_db()
        Session = db
        with Session() as s:
            user_a = _seed_user(s, email="pg-sess-a@example.com")

        pool = db_session_mod.engine.pool
        baseline_checkedout = pool.checkedout()

        app.dependency_overrides[get_current_user_id] = lambda: user_a
        app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # 1. Normal 404 lookup through real get_tryon_repository -> SessionLocal
            r404 = client.get(f"/v1/tryon/jobs/{uuid4()}")
            assert r404.status_code == 404
            assert pool.checkedout() == baseline_checkedout

            # 2. Exception path closes both get_tryon_repository and get_tryon_wardrobe_repository sessions
            def _boom(**kw):
                raise RuntimeError("forced-session-lifecycle-error")

            monkeypatch.setattr(tryon_app, "submit_job", _boom)
            r500 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", _make_image_bytes("JPEG"), "image/jpeg")},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-sess-exc-1"},
            )
            assert r500.status_code == 500
            assert pool.checkedout() == baseline_checkedout
        finally:
            app.dependency_overrides.clear()

    def test_background_inference_fresh_session_success_and_failure_on_postgres(
        self, db, monkeypatch
    ) -> None:
        self._assert_disposable_db()
        tryon_app.reset_for_tests()
        Session = db
        with Session() as s:
            user_a = _seed_user(s, email="pg-bg-a@example.com")

        storage = FakeStorageAdapter()
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

        png_result = _make_image_bytes("PNG", size=(128, 128), color=(40, 120, 200))
        monkeypatch.setattr(
            tryon_app.CommercialTryOnProvider,
            "render",
            lambda *a, **kw: png_result,
        )

        pool = db_session_mod.engine.pool
        baseline_checkedout = pool.checkedout()

        app.dependency_overrides[get_current_user_id] = lambda: user_a
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        try:
            client = TestClient(app)
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", _make_image_bytes("JPEG"), "image/jpeg")},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-bg-ok-1"},
            )
            assert resp.status_code == 202
            job_id = UUID(resp.json()["job_id"])
            assert str(job_id) not in tryon_app._BYTE_CACHE
            assert pool.checkedout() == baseline_checkedout

            with Session() as s_verify:
                row = TryOnJobRepositorySQL(s_verify).get_by_id(
                    user_id=user_a, job_id=job_id
                )
                assert row is not None
                assert row.status == "completed"
                assert row.result_media_ref is not None
                assert row.result_media_ref["mediaType"] == "image/png"
                assert storage.object_exists_sync(row.result_media_ref["key"])

            img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
            assert img_resp.status_code == 200
            assert img_resp.content == png_result
            assert pool.checkedout() == baseline_checkedout

            # Failure path: inference exception must mark failed in PG without false success or leaked session
            monkeypatch.setattr(
                tryon_app.CommercialTryOnProvider,
                "render",
                lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("gpu-worker-crash")),
            )
            resp_fail = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", _make_image_bytes("JPEG"), "image/jpeg")},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-bg-fail-1"},
            )
            assert resp_fail.status_code == 202
            fail_job_id = UUID(resp_fail.json()["job_id"])
            assert str(fail_job_id) not in tryon_app._BYTE_CACHE
            assert pool.checkedout() == baseline_checkedout

            with Session() as s_verify2:
                fail_row = TryOnJobRepositorySQL(s_verify2).get_by_id(
                    user_id=user_a, job_id=fail_job_id
                )
                assert fail_row is not None
                assert fail_row.status == "failed"
                assert fail_row.error_code == "AI_INFERENCE_FAILURE"
                assert fail_row.result_media_ref is None
        finally:
            app.dependency_overrides.clear()
            tryon_app.reset_for_tests()
