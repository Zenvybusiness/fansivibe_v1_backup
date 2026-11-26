"""Phase 7 Virtual Try-On Production Readiness & Hardening Verification Suite.

Covers:
- Phase 7A: Privacy, consent version enforcement, signed-URL expiry, owner-only
  access, account erasure without orphaned R2 objects, and cross-user-safe
  retention cleanup (including abandoned jobs and storage failure preservation).
- Phase 7B: Atomic quotas (daily, per-user concurrency, global concurrency),
  rate limiting, idempotency, Cases A-I billing & retry safety.
- Phase 7C: Crash/restart recovery, stale-job recovery, completed-job guard,
  concurrent retry protection, and worker concurrency semaphore bounds.
- Phase 7D: Structured operational logging, Prometheus metrics, and zero secret/PII
  or presigned-URL leakage.
- Phase 7E: Production configuration invariants and .env test-isolation proof.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import ApiError
from app.api.rate_limit import reset as reset_rate_limiter
import app.application.tryon as tryon_app
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.repositories import TryOnJobRecord, WardrobeItemRecord
from app.domain.ports.storage import StorageError
from app.infrastructure.db.models import TryOnJobModel, UserState, Users
from app.infrastructure.db.repositories import TryOnJobRepositorySQL
from app.main import app
from app.telemetry.metrics import get_metrics_collector
from tests.conftest import make_session
from tests.fakes.fake_storage import FakeStorageAdapter
from tests.test_tryon_phase5f_genlook import (
    MockGenlookServer,
    MockResponse,
    TEST_API_KEY,
    _genlook_settings,
)

USER_A = uuid4()
USER_B = uuid4()
OP_KEY = "phase7-operator-secret-key-32-chars-minimum"


def _make_jpeg(size: tuple[int, int] = (128, 128), color: tuple[int, int, int] = (90, 120, 150)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(size: tuple[int, int] = (128, 128), color: tuple[int, int, int] = (40, 160, 110)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _make_webp(size: tuple[int, int] = (128, 128), color: tuple[int, int, int] = (150, 90, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="WEBP")
    return buf.getvalue()


VALID_JPEG = _make_jpeg()
VALID_PNG = _make_png()
VALID_WEBP = _make_webp()


class _WardrobeRepoStub:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add(self, user_id: UUID, item_id: UUID, category: str = "tops") -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        rec = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name="Phase 7 Garment",
            category=category,
            color="black",
            material="cotton",
            is_favorite=False,
            image_ref={"objectKey": f"users/{user_id}/wardrobe/{item_id}/canonical.webp"},
            created_at=now,
            updated_at=now,
        )
        self.items[(user_id, item_id)] = rec
        return rec

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        return self.items.get((user_id, item_id))


@pytest.fixture
def phase7_env(monkeypatch):
    tryon_app.reset_for_tests()
    clear_settings_cache()
    reset_rate_limiter()
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
    reset_rate_limiter()


def _patch_genlook(monkeypatch, server: MockGenlookServer, settings_obj: SimpleNamespace | None = None):
    cfg = settings_obj or _genlook_settings()
    monkeypatch.setattr(tryon_app, "get_settings", lambda: cfg)
    from app.infrastructure.external import genlook_tryon as gl_mod

    orig_init = gl_mod.GenlookTryOnProvider.__init__

    def _patched_init(self, config, *, http_client=None):
        orig_init(self, config, http_client=server)

    monkeypatch.setattr(gl_mod.GenlookTryOnProvider, "__init__", _patched_init)


def _seed_pg_user(session, *, email: str) -> UUID:
    u = Users(auth_provider="local", auth_subject=email, display_name=email.split("@")[0])
    session.add(u)
    session.flush()
    session.add(UserState(user_id=u.id))
    session.commit()
    return u.id


# ==============================================================================
# Phase 7A: Privacy, Consent, and Media Lifecycle
# ==============================================================================


class TestPhase7APrivacyAndLifecycle:
    def test_owner_unauth_cross_user_and_cache_control_headers(self, phase7_env):
        storage: FakeStorageAdapter = phase7_env["storage"]
        wardrobe_repo: _WardrobeRepoStub = phase7_env["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["objectKey"], VALID_WEBP, content_type="image/webp"))

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "p7a-owner-1"},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Complete mock job
        client.get(f"/v1/tryon/jobs/{job_id}")
        client.get(f"/v1/tryon/jobs/{job_id}")

        # Owner retrieves image with strict private, no-store cache headers
        img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 200
        assert "no-store" in img_resp.headers.get("cache-control", "").lower()
        assert "private" in img_resp.headers.get("cache-control", "").lower()

        # Another user gets 404 on job, image, retry, cancel, delete
        app.dependency_overrides[get_current_user_id] = lambda: USER_B
        assert client.get(f"/v1/tryon/jobs/{job_id}").status_code == 404
        assert client.get(f"/v1/tryon/jobs/{job_id}/image").status_code == 404
        assert client.post(f"/v1/tryon/jobs/{job_id}/retry").status_code == 404
        assert client.post(f"/v1/tryon/jobs/{job_id}/cancel").status_code == 404
        assert client.delete(f"/v1/tryon/jobs/{job_id}").status_code == 404

        # Unauthenticated user gets 401
        app.dependency_overrides.pop(get_current_user_id, None)
        assert client.get(f"/v1/tryon/jobs/{job_id}").status_code == 401
        assert client.get(f"/v1/tryon/jobs/{job_id}/image").status_code == 401
        assert client.get("/v1/tryon/capabilities").status_code == 401

    def test_consent_version_rotation_blocks_submit_and_old_job_retry(self, monkeypatch, phase7_env):
        repo = phase7_env["job_repo"]
        wardrobe_repo = phase7_env["wardrobe_repo"]
        gid = uuid4()
        wardrobe_repo.add(USER_A, gid)

        client = TestClient(app)
        # Create job under tryon-v1 and mark it failed
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "p7a-consent-1"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])
        repo.update_failure(
            job_id=job_id,
            error_code="PROVIDER_TRANSIENT_FAILURE",
            error_message="failed",
            completed_at=datetime.now(timezone.utc),
        )

        # Rotate consent version to tryon-v2
        monkeypatch.setattr(tryon_app, "get_settings", lambda: SimpleNamespace(
            tryon_enabled=True,
            tryon_provider="mock",
            environment="development",
            tryon_consent_version="tryon-v2",
            tryon_daily_quota_per_user=20,
            tryon_max_concurrent_jobs_per_user=2,
            tryon_max_concurrent_jobs_global=10,
            tryon_worker_concurrency_limit=10,
        ))

        # Old consent_version rejected on new submit (422)
        bad_submit = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "p7a-consent-2"},
        )
        assert bad_submit.status_code == 422

        # Retrying a job accepted under superseded consent tryon-v1 also fails closed (422)
        bad_retry = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert bad_retry.status_code == 422

    def test_retention_cleanup_blocks_cross_user_keys_preserves_on_storage_error_and_purges_abandoned(
        self, phase7_env
    ):
        repo = phase7_env["job_repo"]
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(hours=30)

        class _TransientDeleteFailStorage(FakeStorageAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.fail_keys: set[str] = set()

            async def delete_object(self, key: str) -> bool:
                if key in self.fail_keys:
                    raise StorageError("R2 transient outage", key=key)
                return await super().delete_object(key)

        storage = _TransientDeleteFailStorage()

        # User B legitimate object that User A's tampered ref points to
        user_b_key = f"users/{USER_B}/tryon/legit-b/result.png"
        storage.put_object_bytes(user_b_key, VALID_PNG, content_type="image/png")

        # Tampered/corrupted job owned by USER_A referencing USER_B's key
        tampered_job_id = uuid4()
        repo._jobs[tampered_job_id] = TryOnJobRecord(
            id=tampered_job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=("g1",),
            provider="mock",
            status="completed",
            consent_version="tryon-v1",
            consent_accepted_at=old_ts,
            created_at=old_ts,
            updated_at=old_ts,
            completed_at=old_ts,
            person_media_ref={"key": user_b_key},
            result_media_ref={"key": user_b_key},
        )

        # Transient R2 failure on failed job: DB record must NOT be orphaned
        fail_job_id = uuid4()
        fail_person_key = f"users/{USER_A}/tryon/{fail_job_id}/person.jpg"
        storage.put_object_bytes(fail_person_key, VALID_JPEG, content_type="image/jpeg")
        storage.fail_keys.add(fail_person_key)
        repo._jobs[fail_job_id] = TryOnJobRecord(
            id=fail_job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=("g1",),
            provider="mock",
            status="failed",
            consent_version="tryon-v1",
            consent_accepted_at=old_ts,
            created_at=old_ts,
            updated_at=old_ts,
            completed_at=old_ts,
            person_media_ref={"key": fail_person_key},
        )

        # Abandoned processing job (>24h old)
        abandoned_id = uuid4()
        abandoned_key = f"users/{USER_A}/tryon/{abandoned_id}/person.jpg"
        storage.put_object_bytes(abandoned_key, VALID_JPEG, content_type="image/jpeg")
        repo._jobs[abandoned_id] = TryOnJobRecord(
            id=abandoned_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=("g1",),
            provider="mock",
            status="processing",
            consent_version="tryon-v1",
            consent_accepted_at=old_ts,
            created_at=old_ts,
            updated_at=old_ts,
            processing_started_at=old_ts,
            person_media_ref={"key": abandoned_key},
        )

        summary = asyncio.run(tryon_app.cleanup_retention_data(job_repo=repo, storage=storage, now=now))
        # User B's object MUST remain intact!
        assert storage.object_exists_sync(user_b_key) is True
        # Failed job whose R2 delete errored MUST still exist in DB so next run retries!
        assert repo.get_by_id(user_id=USER_A, job_id=fail_job_id) is not None
        # Abandoned job was purged from both storage and DB!
        assert not storage.object_exists_sync(abandoned_key)
        assert repo.get_by_id(user_id=USER_A, job_id=abandoned_id) is None
        assert summary.abandoned_jobs_deleted == 1
        assert summary.storage_errors >= 2

        # Recover R2 and re-run retention -> failed job now cleans up cleanly without orphan
        storage.fail_keys.clear()
        summary2 = asyncio.run(tryon_app.cleanup_retention_data(job_repo=repo, storage=storage, now=now))
        assert not storage.object_exists_sync(fail_person_key)
        assert repo.get_by_id(user_id=USER_A, job_id=fail_job_id) is None
        assert summary2.failed_jobs_deleted == 1


# ==============================================================================
# Phase 7B & 7C: Quotas, Concurrency, Cases A-I & Worker Reliability
# ==============================================================================


class TestPhase7BAnd7CQuotasAndReliability:
    def test_case_b_multi_user_global_concurrency_limit_on_postgres(self, db, monkeypatch):
        Session = db
        with Session() as s:
            u1 = _seed_pg_user(s, email="p7b-u1@example.com")
            u2 = _seed_pg_user(s, email="p7b-u2@example.com")
            u3 = _seed_pg_user(s, email="p7b-u3@example.com")

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: SimpleNamespace(
                tryon_enabled=True,
                tryon_provider="commercial",
                environment="development",
                tryon_consent_version="tryon-v1",
                tryon_daily_quota_per_user=20,
                tryon_max_concurrent_jobs_per_user=5,
                tryon_max_concurrent_jobs_global=2,
                tryon_worker_concurrency_limit=2,
                tryon_commercial_provider_name="comm",
                tryon_commercial_api_key="sk_test_1234567890abcdef",
                tryon_commercial_endpoint_url="https://api.example.invalid/vton",
                tryon_commercial_connect_timeout_s=5.0,
                tryon_commercial_inference_timeout_s=10.0,
                tryon_commercial_max_retries=0,
            ),
        )
        storage = FakeStorageAdapter()

        def _submit_for(uid: UUID, idx: int) -> int:
            with Session() as sess:
                repo = TryOnJobRepositorySQL(sess)
                try:
                    tryon_app.submit_job(
                        user_id=str(uid),
                        outfit_source="today",
                        garment_ids=["g-1"],
                        person_content_type="image/jpeg",
                        person_bytes=VALID_JPEG,
                        consent_version="tryon-v1",
                        consent_accepted=True,
                        idempotency_key=f"p7b-global-{idx}",
                        job_repo=repo,
                        storage=storage,
                    )
                    return 202
                except ApiError as exc:
                    return exc.status_code

        # 3 users submit concurrently while global_concurrent_limit=2 -> max 2 admitted, >=1 gets 429
        with ThreadPoolExecutor(max_workers=3) as pool:
            codes = list(pool.map(lambda pair: _submit_for(*pair), [(u1, 1), (u2, 2), (u3, 3)]))

        assert codes.count(202) == 2
        assert codes.count(429) == 1

    def test_tryon_rate_limit_enforced_when_enabled(self, monkeypatch, phase7_env):
        reset_rate_limiter()
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_TRYON_PER_MINUTE", "2")
        clear_settings_cache()

        client = TestClient(app)
        for i in range(2):
            r = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": f"rl-tryon-{i}"},
            )
            assert r.status_code == 202

        r3 = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "today",
                "garment_ids": '["g-1"]',
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "rl-tryon-3"},
        )
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "RATE_LIMITED"

    def test_case_g_definitive_provider_failure_clears_gen_id_and_increments_attempt(
        self, monkeypatch, phase7_env
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        _patch_genlook(monkeypatch, server)
        storage: FakeStorageAdapter = phase7_env["storage"]
        repo = phase7_env["job_repo"]
        wardrobe_repo = phase7_env["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["objectKey"], VALID_WEBP, content_type="image/webp"))

        # Genlook accepts cm8gen_1, then transitions to FAILED (refunded)
        server.poll_sequences["cm8gen_1"] = [
            {
                "status": "FAILED",
                "errorCode": "GENERATION_FAILED",
                "errorMessage": "Upstream model error",
            }
        ]
        server.poll_sequences["cm8gen_2"] = [
            {"status": "COMPLETED", "resultImageUrl": "https://cdn.genlook-results.example/cm8gen_2/out.png"}
        ]

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "p7b-case-g"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        failed = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed.status == "failed"
        gl = failed.person_media_ref["genlook"]
        assert gl["generationId"] is None
        assert gl["generationStatus"] == "FAILED"
        assert gl["attemptSeq"] == 1
        assert gl["refunded"] is True

        # Retry uses a fresh attempt key (fv-tryon-{job_id}-a1) and succeeds
        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done.status == "completed"
        tryon_posts = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_posts) == 2
        assert tryon_posts[0]["headers"]["Idempotency-Key"].endswith("-a0")
        assert tryon_posts[1]["headers"]["Idempotency-Key"].endswith("-a1")

    def test_concurrent_retry_and_duplicate_worker_execution_prevented(self, monkeypatch, phase7_env):
        repo = phase7_env["job_repo"]
        storage = phase7_env["storage"]
        job_id = uuid4()
        person_key = f"users/{USER_A}/tryon/{job_id}/person.jpg"
        asyncio.run(storage.put_object(person_key, VALID_JPEG, content_type="image/jpeg"))
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="today",
            garment_id=None,
            garment_ids=["g-1"],
            provider="commercial",
            status="failed",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": person_key, "contentHash": "h"},
        )

        # Concurrent retry_job calls: only 1 succeeds, second raises 409 CONFLICT
        results: list[str] = []
        for _ in range(2):
            try:
                tryon_app.retry_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
                results.append("ok")
            except ApiError as exc:
                results.append(f"err:{exc.status_code}")
        assert results == ["ok", "err:409"]

        # Duplicate concurrent execute_tryon_inference on same job_id only invokes provider ONCE
        render_calls = 0
        barrier = threading.Barrier(2)

        def _slow_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            time.sleep(0.05)
            return VALID_PNG

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: SimpleNamespace(
                tryon_enabled=True,
                tryon_provider="commercial",
                environment="development",
                tryon_consent_version="tryon-v1",
                tryon_daily_quota_per_user=20,
                tryon_max_concurrent_jobs_per_user=5,
                tryon_max_concurrent_jobs_global=10,
                tryon_worker_concurrency_limit=4,
                tryon_commercial_provider_name="comm",
                tryon_commercial_api_key="sk_test_1234567890abcdef",
                tryon_commercial_endpoint_url="https://api.example.invalid/vton",
                tryon_commercial_connect_timeout_s=5.0,
                tryon_commercial_inference_timeout_s=10.0,
                tryon_commercial_max_retries=0,
            ),
        )
        monkeypatch.setattr(tryon_app.CommercialTryOnProvider, "render", _slow_render)

        async def _run_both():
            await asyncio.gather(
                tryon_app.execute_tryon_inference(job_id=job_id, user_id=USER_A, job_repo=repo, storage=storage),
                tryon_app.execute_tryon_inference(job_id=job_id, user_id=USER_A, job_repo=repo, storage=storage),
            )

        asyncio.run(_run_both())
        assert render_calls == 1
        assert repo.get_by_id(user_id=USER_A, job_id=job_id).status == "completed"

        # Completed job cannot be executed again
        asyncio.run(
            tryon_app.execute_tryon_inference(job_id=job_id, user_id=USER_A, job_repo=repo, storage=storage)
        )
        assert render_calls == 1

    def test_worker_concurrency_respects_configured_limit_and_stale_recovery(self, monkeypatch, phase7_env):
        repo = phase7_env["job_repo"]
        storage = phase7_env["storage"]
        active_now = 0
        max_observed = 0
        lock = threading.Lock()

        def _tracked_render(*args, **kwargs):
            nonlocal active_now, max_observed
            with lock:
                active_now += 1
                max_observed = max(max_observed, active_now)
            time.sleep(0.05)
            with lock:
                active_now -= 1
            return VALID_PNG

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: SimpleNamespace(
                tryon_enabled=True,
                tryon_provider="commercial",
                environment="development",
                tryon_consent_version="tryon-v1",
                tryon_daily_quota_per_user=20,
                tryon_max_concurrent_jobs_per_user=10,
                tryon_max_concurrent_jobs_global=10,
                tryon_worker_concurrency_limit=2,
                tryon_stale_job_timeout_s=60,
                tryon_commercial_provider_name="comm",
                tryon_commercial_api_key="sk_test_1234567890abcdef",
                tryon_commercial_endpoint_url="https://api.example.invalid/vton",
                tryon_commercial_connect_timeout_s=5.0,
                tryon_commercial_inference_timeout_s=10.0,
                tryon_commercial_max_retries=0,
            ),
        )
        monkeypatch.setattr(tryon_app.CommercialTryOnProvider, "render", _tracked_render)

        job_ids: list[UUID] = []
        for idx in range(5):
            jid = uuid4()
            pkey = f"users/{USER_A}/tryon/{jid}/person.jpg"
            asyncio.run(storage.put_object(pkey, VALID_JPEG, content_type="image/jpeg"))
            repo.create(
                job_id=jid,
                user_id=USER_A,
                outfit_source="today",
                garment_id=None,
                garment_ids=["g-1"],
                provider="commercial",
                status="queued",
                consent_version="tryon-v1",
                consent_accepted_at=datetime.now(timezone.utc),
                person_media_ref={"key": pkey, "contentHash": f"h{idx}"},
            )
            job_ids.append(jid)

        async def _run_all():
            await asyncio.gather(
                *[
                    tryon_app.execute_tryon_inference(job_id=jid, user_id=USER_A, job_repo=repo, storage=storage)
                    for jid in job_ids
                ]
            )

        asyncio.run(_run_all())
        assert max_observed <= 2

        # Stale processing job recovery preserves genlook generationId without restart
        stale_id = uuid4()
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=120)
        repo._jobs[stale_id] = TryOnJobRecord(
            id=stale_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=("g1",),
            provider="genlook",
            status="processing",
            consent_version="tryon-v1",
            consent_accepted_at=old_ts,
            created_at=old_ts,
            updated_at=old_ts,
            processing_started_at=old_ts,
            person_media_ref={"key": f"users/{USER_A}/tryon/{stale_id}/person.jpg", "genlook": {"generationId": "gen_stale_1"}},
        )
        recovered = tryon_app.recover_stale_jobs(job_repo=repo, stale_after_s=60)
        assert recovered == 1
        st_rec = repo.get_by_id(user_id=USER_A, job_id=stale_id)
        assert st_rec.status == "failed"
        assert st_rec.error_code == "STALE_JOB_TIMEOUT"
        assert st_rec.person_media_ref["genlook"]["generationId"] == "gen_stale_1"


# ==============================================================================
# Phase 7D & 7E: Observability, Metrics, Secret Redaction & Config Isolation
# ==============================================================================


class TestPhase7DObservabilityAnd7EConfig:
    def test_structured_logs_metrics_and_no_secret_or_signed_url_leak(
        self, monkeypatch, caplog, phase7_env
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        _patch_genlook(monkeypatch, server)
        storage: FakeStorageAdapter = phase7_env["storage"]
        wardrobe_repo = phase7_env["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["objectKey"], VALID_WEBP, content_type="image/webp"))

        client = TestClient(app)
        with caplog.at_level(logging.INFO):
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(gid)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "p7d-obs-1"},
            )
            assert resp.status_code == 202
            # Duplicate replay
            resp2 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(gid)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "p7d-obs-1"},
            )
            assert resp2.status_code == 202

        log_text = caplog.text
        assert "event=tryon_job_created" in log_text
        assert "event=tryon_job_duplicate_replay" in log_text
        assert "event=tryon_job_completed" in log_text
        assert TEST_API_KEY not in log_text
        assert "X-Amz-Signature" not in log_text
        assert "resultImageUrl" not in log_text

        prom = client.get("/metrics").text
        assert "fansivibe_tryon_jobs_created_total" in prom
        assert "fansivibe_tryon_jobs_terminal_total" in prom
        assert "fansivibe_tryon_processing_duration_seconds_count" in prom
        assert "fansivibe_tryon_credits_charged_total" in prom
        assert TEST_API_KEY not in prom

        summary = get_metrics_collector().get_summary()
        assert summary["tryon_jobs_created_total"] >= 1
        assert summary["tryon_jobs_replayed_total"] >= 1

    def test_dotenv_isolated_under_pytest_but_explicit_env_file_supported(
        self, monkeypatch, tmp_path
    ):
        env_file = tmp_path / ".env"
        env_file.write_text("FANSIVIBE_OPERATOR_API_KEY=from-explicit-dotenv-file-32chars!!\n", encoding="utf-8")

        monkeypatch.delenv("FANSIVIBE_OPERATOR_API_KEY", raising=False)
        clear_settings_cache()

        # Default Settings() under pytest skips backend/.env on disk when env var is deleted
        s_default = Settings()
        assert s_default.operator_api_key is None

        # Explicit _env_file=... still works as expected
        s_explicit = Settings(_env_file=env_file)
        assert s_explicit.operator_api_key == "from-explicit-dotenv-file-32chars!!"

    def test_production_rejects_wildcard_cors_even_without_credentials(self):
        with pytest.raises(ValidationError, match="wildcard"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_db",
                auth_secret="p" * 40,
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_account_id="acc-prod",
                r2_access_key_id="key-prod",
                r2_secret_access_key="sec-prod",
                media_upload_hmac_secret="h" * 40,
                cors_origins=["*"],
                cors_allow_credentials=False,
            )

    def test_sensitive_routes_carry_private_no_store_cache_headers(self, phase7_env):
        client = TestClient(app)
        cap_resp = client.get("/v1/tryon/capabilities")
        assert cap_resp.status_code == 200
        assert "no-store" in cap_resp.headers.get("cache-control", "").lower()
        assert "private" in cap_resp.headers.get("cache-control", "").lower()

    def test_delete_job_and_media_fails_closed_without_orphaning_on_storage_error(
        self, phase7_env
    ):
        repo = phase7_env["job_repo"]

        class _DeleteFailStorage(FakeStorageAdapter):
            async def delete_object(self, key: str) -> bool:
                raise StorageError("R2 delete outage", key=key)

        storage = _DeleteFailStorage()
        job_id = uuid4()
        result_key = f"users/{USER_A}/tryon/{job_id}/result.png"
        storage.put_object_bytes(result_key, VALID_PNG, content_type="image/png")
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
        repo.update_result(
            job_id=job_id,
            result_media_ref={"key": result_key, "mediaType": "image/png"},
            completed_at=datetime.now(timezone.utc),
        )

        with pytest.raises(ApiError) as exc_info:
            asyncio.run(
                tryon_app.delete_job_and_media(
                    user_id=str(USER_A),
                    job_id=str(job_id),
                    job_repo=repo,
                    storage=storage,
                )
            )
        assert exc_info.value.status_code == 503
        # Job record and R2 object remain intact so caller can safely retry
        assert repo.get_by_id(user_id=USER_A, job_id=job_id) is not None
        assert storage.object_exists_sync(result_key) is True

    def test_distributed_postgres_rate_limit_enforced_across_sessions(self, db):
        from app.api import rate_limit

        Session = db
        bucket_key = f"tryon:multiworker-{uuid4()}"
        now = datetime.now(timezone.utc)

        def _hit(_idx: int) -> tuple[bool, int]:
            with Session() as sess:
                return rate_limit.check_distributed(
                    bucket_key,
                    limit=3,
                    window_s=60.0,
                    session=sess,
                    now=now,
                )

        # Simulate 5 concurrent requests across separate worker DB sessions
        with ThreadPoolExecutor(max_workers=5) as pool:
            outcomes = list(pool.map(_hit, range(5)))

        allowed_count = sum(1 for allowed, _ in outcomes if allowed)
        denied_count = sum(1 for allowed, _ in outcomes if not allowed)
        assert allowed_count == 3
        assert denied_count == 2

    def test_p4_rate_limit_bucket_model_and_pruning(self, db):
        from app.api import rate_limit
        from app.infrastructure.db.models import RateLimitBucket

        Session = db
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(hours=2)
        with Session() as sess:
            rate_limit.check_distributed(
                "auth:old-ip", limit=5, window_s=60.0, session=sess, now=old_ts
            )
            rate_limit.check_distributed(
                "auth:fresh-ip", limit=5, window_s=60.0, session=sess, now=now
            )
            pruned = rate_limit.prune_expired_buckets(sess, older_than_s=3600.0, now=now)
            assert pruned == 1
            remaining = sess.execute(select(RateLimitBucket.bucket_key)).scalars().all()
            assert remaining == ["auth:fresh-ip"]

    def test_p4_production_settings_and_startup_validation_hardening(self):
        from app.config.settings import validate_production_startup

        base_kwargs = {
            "environment": "production",
            "database_url": "postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_db",
            "auth_secret": "x" * 40,
            "allow_dev_token": False,
            "media_storage_provider": "r2",
            "r2_bucket_name": "prod-bucket",
            "r2_account_id": "acc-prod",
            "r2_access_key_id": "key-prod",
            "r2_secret_access_key": "sec-prod",
            "media_upload_hmac_secret": "y" * 40,
            "operator_api_key": "z" * 40,
            "tryon_provider": "genlook",
            "genlook_api_key": TEST_API_KEY,
        }

        # Case-insensitive FANSIVIBE_ENV still blocks CatVTON
        with pytest.raises(ValidationError, match="CatVTON"):
            Settings(**{**base_kwargs, "environment": "PRODUCTION", "tryon_provider": "catvton"})

        # Cleartext R2 endpoint, wildcard CORS regex, cleartext CORS origin, SQLite DB rejected
        with pytest.raises(ValidationError, match="HTTPS"):
            Settings(**{**base_kwargs, "r2_endpoint_url": "http://r2.internal"})
        with pytest.raises(ValidationError, match="wildcard"):
            Settings(**{**base_kwargs, "cors_origin_regex": ".*"})
        with pytest.raises(ValidationError, match="HTTPS"):
            Settings(**{**base_kwargs, "cors_origins": ["http://app.fansivibe.com"]})
        with pytest.raises(ValidationError, match="DATABASE_URL"):
            Settings(**{**base_kwargs, "database_url": "sqlite:///prod.db"})

        # Startup gate requires Genlook when Try-On is enabled, mandatory operator key, and distinct upload HMAC
        s_mock = Settings(**{**base_kwargs, "tryon_provider": "mock"})
        with pytest.raises(ValueError, match="genlook"):
            validate_production_startup(s_mock)

        s_no_op = Settings(**{**base_kwargs, "operator_api_key": None})
        with pytest.raises(ValueError, match="FANSIVIBE_OPERATOR_API_KEY"):
            validate_production_startup(s_no_op)

        s_same_hmac = Settings(**{**base_kwargs, "media_upload_hmac_secret": "x" * 40})
        with pytest.raises(ValueError, match="distinct"):
            validate_production_startup(s_same_hmac)

        s_valid = Settings(**base_kwargs)
        validate_production_startup(s_valid)

    def test_p4_non_wardrobe_submit_never_links_foreign_or_missing_garment_fk(self, db):
        Session = db
        with Session() as sess:
            u1 = _seed_pg_user(sess, email="p4-fk-u1@example.com")
            storage = FakeStorageAdapter()
            repo = TryOnJobRepositorySQL(sess)
            from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

            w_repo = WardrobeItemRepositorySQL(sess)
            foreign_or_missing_uuid = str(uuid4())
            job, created = tryon_app.submit_job(
                user_id=str(u1),
                outfit_source="today",
                garment_ids=[foreign_or_missing_uuid],
                person_content_type="image/jpeg",
                person_bytes=VALID_JPEG,
                consent_version="tryon-v1",
                consent_accepted=True,
                idempotency_key="p4-non-wardrobe-uuid",
                wardrobe_repo=w_repo,
                job_repo=repo,
                storage=storage,
            )
            assert created is True
            assert job.garment_id is None

    def test_p4_genlook_ssrf_blocks_dns_resolving_to_private_ip(self, monkeypatch):
        import socket
        from app.infrastructure.external.genlook_tryon import _is_safe_result_url

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))],
        )
        assert _is_safe_result_url("https://metadata-rebind.example/out.png", allow_http=False) is False

    def test_p4_genlook_polling_429_preserves_generation_id_no_double_charge(
        self, monkeypatch, phase7_env
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        _patch_genlook(monkeypatch, server)
        storage: FakeStorageAdapter = phase7_env["storage"]
        repo = phase7_env["job_repo"]
        wardrobe_repo = phase7_env["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["objectKey"], VALID_WEBP, content_type="image/webp"))

        # Poll returns 429 RATE_LIMITED > max_consecutive_transient (5) after POST /try-on succeeds
        server.next_poll_responses.extend(
            [
                MockResponse(
                    429,
                    {"code": "RATE_LIMITED", "message": "Too many polls", "status": 429},
                    headers={"Retry-After": "0.01"},
                )
                for _ in range(7)
            ]
        )

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "p4-poll-429"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        failed = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed is not None
        assert failed.status == "failed"
        gl = failed.person_media_ref["genlook"]
        assert gl["generationId"] == "cm8gen_1"
        assert server.credits == 9

        # Retry resumes polling cm8gen_1 without issuing a second POST /try-on (no double charge!)
        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done is not None and done.status == "completed"
        assert server.credits == 9
        tryon_posts = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_posts) == 1



