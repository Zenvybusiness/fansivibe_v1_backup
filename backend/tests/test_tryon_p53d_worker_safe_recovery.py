"""P5.3D PostgreSQL integration tests for worker-safe Try-On recovery.

Covers:
1. Worker A claims a job with unique worker_id, lease_token, and bounded lease_expires_at.
2. Worker B starts recovery while Worker A's lease is valid.
3. Worker B does NOT interrupt Worker A's active job (or freshly queued job).
4. Worker A's lease expires (or Worker A dies).
5. Worker B safely recovers the abandoned job as INTERRUPTED_BY_RESTART.
6. Concurrent workers cannot claim the same queued job.
7. A recovered Genlook job resumes its existing generationId rather than creating another.
8. A late result (and late failure / metadata write) from an old worker cannot overwrite a newer execution.
9. Lease renewal and recovery races are handled atomically in PostgreSQL.
10. Deployment startup validation rejects unsafe multi-worker/lease configurations.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.application import tryon as tryon_app
from app.config.settings import Settings, clear_settings_cache, validate_production_startup
from app.infrastructure.db.models import UserState, Users, WardrobeItems
from app.infrastructure.db.repositories import TryOnJobRepositorySQL, WardrobeItemRepositorySQL
from app.infrastructure.external import genlook_tryon
from tests.fakes.fake_storage import FakeStorageAdapter
from tests.test_tryon_phase5f_genlook import (
    MockGenlookServer,
    VALID_JPEG,
    VALID_PNG,
    VALID_WEBP,
    _genlook_settings,
)


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


class _SingleWardrobeRepo:
    def __init__(self, user_id: UUID, item_id: UUID):
        self._user_id = user_id
        self._item_id = item_id

    def get_by_id(self, *, user_id: UUID, item_id: UUID):
        from types import SimpleNamespace

        if user_id != self._user_id or item_id != self._item_id:
            return None
        return SimpleNamespace(
            id=self._item_id,
            user_id=self._user_id,
            name="Studio Jacket",
            category="outerwear",
            color="black",
            material="wool",
            fit="regular",
            image_ref={"key": f"users/{self._user_id}/wardrobe/{self._item_id}/item.webp"},
        )


def test_worker_b_does_not_interrupt_worker_a_active_or_freshly_queued_job_on_postgres(db):
    """Scenarios 1, 2, 3: Worker A claims a job; Worker B recovery leaves it untouched."""
    Session = db
    with Session() as s_seed:
        user_id = _seed_user(s_seed, email="p53d-live@example.com")
        repo_a = TryOnJobRepositorySQL(s_seed)

        active_job_id = uuid4()
        repo_a.create(
            job_id=active_job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-1"],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            worker_id="worker-a",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        token_a = uuid4()
        assert repo_a.claim_queued_job(
            job_id=active_job_id,
            processing_started_at=datetime.now(timezone.utc),
            worker_id="worker-a",
            lease_token=token_a,
            lease_seconds=60,
        )

        # Also create a freshly queued job owned by Worker A (not yet claimed by BackgroundTasks)
        queued_job_id = uuid4()
        repo_a.create(
            job_id=queued_job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-2"],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            worker_id="worker-a",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )

    # Worker B starts up in a separate session and runs startup recovery
    with Session() as s_b:
        repo_b = TryOnJobRepositorySQL(s_b)
        recovered = tryon_app.recover_interrupted_jobs(repo_b, worker_id="worker-b")
        assert recovered == 0

        stale_recovered = tryon_app.recover_stale_jobs(
            job_repo=repo_b,
            stale_after_s=30,
            now=datetime.now(timezone.utc) + timedelta(seconds=5),
            worker_id="worker-b",
        )
        assert stale_recovered == 0

    with Session() as s_chk:
        repo_chk = TryOnJobRepositorySQL(s_chk)
        active_job = repo_chk.get_by_id(user_id=user_id, job_id=active_job_id)
        assert active_job is not None
        assert active_job.status == "processing"
        assert active_job.worker_id == "worker-a"
        assert active_job.lease_token == token_a

        queued_job = repo_chk.get_by_id(user_id=user_id, job_id=queued_job_id)
        assert queued_job is not None
        assert queued_job.status == "queued"
        assert queued_job.worker_id == "worker-a"


def test_worker_b_recovers_expired_abandoned_job_on_postgres(db):
    """Scenarios 4, 5: When Worker A's lease expires, Worker B safely recovers the abandoned job."""
    Session = db
    with Session() as s_a:
        user_id = _seed_user(s_a, email="p53d-expired@example.com")
        repo_a = TryOnJobRepositorySQL(s_a)
        job_id = uuid4()
        repo_a.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-1"],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        token_a = uuid4()
        assert repo_a.claim_queued_job(
            job_id=job_id,
            processing_started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            worker_id="worker-a-dead",
            lease_token=token_a,
            lease_seconds=30,
        )
        # Simulate lease expiration in PostgreSQL (Worker A died without heartbeating)
        s_a.execute(
            text("UPDATE tryon_jobs SET lease_expires_at = clock_timestamp() - interval '5 seconds' WHERE id = :jid"),
            {"jid": job_id},
        )
        s_a.commit()

    with Session() as s_b:
        repo_b = TryOnJobRepositorySQL(s_b)
        recovered = tryon_app.recover_interrupted_jobs(repo_b, worker_id="worker-b")
        assert recovered == 1

    with Session() as s_chk:
        repo_chk = TryOnJobRepositorySQL(s_chk)
        job = repo_chk.get_by_id(user_id=user_id, job_id=job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "INTERRUPTED_BY_RESTART"
        assert job.worker_id is None
        assert job.lease_token is None
        assert job.lease_expires_at is None


def test_concurrent_workers_cannot_claim_same_queued_job_on_postgres(db):
    """Scenario 6: Two concurrent workers racing to claim the same queued job — only one wins."""
    Session = db
    with Session() as s_seed:
        user_id = _seed_user(s_seed, email="p53d-race-claim@example.com")
        repo = TryOnJobRepositorySQL(s_seed)
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-1"],
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )

    def _try_claim(worker_name: str) -> tuple[bool, UUID]:
        tok = uuid4()
        with Session() as s:
            r = TryOnJobRepositorySQL(s)
            won = r.claim_queued_job(
                job_id=job_id,
                processing_started_at=datetime.now(timezone.utc),
                worker_id=worker_name,
                lease_token=tok,
                lease_seconds=60,
            )
            return won, tok

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_try_claim, ["worker-1", "worker-2", "worker-3", "worker-4"]))

    winners = [res for res in results if res[0]]
    assert len(winners) == 1

    with Session() as s_chk:
        job = TryOnJobRepositorySQL(s_chk).get_by_id(user_id=user_id, job_id=job_id)
        assert job is not None
        assert job.status == "processing"
        assert job.lease_token == winners[0][1]


def test_recovered_genlook_job_resumes_existing_generation_without_duplicate_charge(db, monkeypatch):
    """Scenario 7: A recovered Genlook job resumes existing generationId without creating another."""
    Session = db
    server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
    cfg = _genlook_settings(genlook_poll_timeout_s=0.1, genlook_poll_interval_s=0.01)

    orig_init = genlook_tryon.GenlookTryOnProvider.__init__

    def _patched_init(self_p, config, **kw):
        kw.setdefault("http_client", server)
        orig_init(self_p, config, **kw)

    monkeypatch.setattr(genlook_tryon.GenlookTryOnProvider, "__init__", _patched_init)
    monkeypatch.setattr(tryon_app, "get_settings", lambda: cfg)

    storage = FakeStorageAdapter()
    with Session() as s_seed:
        user_id = _seed_user(s_seed, email="p53d-genlook@example.com")
        garment_id = uuid4()
        s_seed.add(
            WardrobeItems(
                id=garment_id,
                user_id=user_id,
                name="Studio Jacket",
                category_id="outerwear",
                color_id="black",
                image_ref={"key": f"users/{user_id}/wardrobe/{garment_id}/item.webp"},
            )
        )
        s_seed.commit()
        wardrobe_repo = WardrobeItemRepositorySQL(s_seed)
        asyncio.run(
            storage.put_object(
                f"users/{user_id}/wardrobe/{garment_id}/item.webp",
                VALID_WEBP,
                content_type="image/webp",
            )
        )
        job_id = uuid4()
        person_key = f"users/{user_id}/tryon/{job_id}/person.jpg"
        asyncio.run(storage.put_object(person_key, VALID_JPEG, content_type="image/jpeg"))

        # Keep cm8gen_1 pending so initial execution times out after saving generationId
        server.poll_sequences["cm8gen_1"] = [{"status": "PENDING"}]
        repo = TryOnJobRepositorySQL(s_seed)
        repo.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=garment_id,
            garment_ids=[str(garment_id)],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={
                "key": person_key,
                "contentHash": tryon_app.sha256_hex(VALID_JPEG),
            },
        )
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=user_id,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )
        # Simulate that Worker A crashed mid-processing with cm8gen_1 saved and lease expired
        s_seed.execute(
            text(
                "UPDATE tryon_jobs SET status='processing', worker_id='worker-a-dead', "
                "lease_token=:tok, lease_expires_at = clock_timestamp() - interval '10 seconds', "
                "error_code=NULL, error_message=NULL, completed_at=NULL WHERE id = :jid"
            ),
            {"tok": uuid4(), "jid": job_id},
        )
        s_seed.commit()

    # Worker B recovers the abandoned job
    with Session() as s_rec:
        repo_b = TryOnJobRepositorySQL(s_rec)
        assert tryon_app.recover_interrupted_jobs(repo_b, worker_id="worker-b") == 1
        rec_job = repo_b.get_by_id(user_id=user_id, job_id=job_id)
        assert rec_job is not None
        assert rec_job.status == "failed"
        assert rec_job.error_code == "INTERRUPTED_BY_RESTART"
        assert rec_job.person_media_ref["genlook"]["generationId"] == "cm8gen_1"
        assert rec_job.person_media_ref["genlook"]["imageId"].startswith("ephemeral/customer/")
        assert rec_job.person_media_ref["genlook"]["attemptSeq"] == 0

    # Now Genlook completes cm8gen_1; retry on Worker B resumes GET /generations/cm8gen_1
    server.poll_sequences["cm8gen_1"] = [
        {"status": "COMPLETED", "resultImageUrl": "https://cdn.genlook-results.example/cm8gen_1/out.png"}
    ]
    normal_cfg = _genlook_settings(genlook_poll_timeout_s=2.0, genlook_poll_interval_s=0.01)
    monkeypatch.setattr(tryon_app, "get_settings", lambda: normal_cfg)

    with Session() as s_retry:
        repo_retry = TryOnJobRepositorySQL(s_retry)
        wardrobe_repo_retry = WardrobeItemRepositorySQL(s_retry)
        retried = tryon_app.retry_job(user_id=str(user_id), job_id=str(job_id), job_repo=repo_retry)
        assert retried.status == "processing"
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=user_id,
                job_repo=repo_retry,
                storage=storage,
                wardrobe_repo=wardrobe_repo_retry,
            )
        )
        done = repo_retry.get_by_id(user_id=user_id, job_id=job_id)
        assert done is not None
        assert done.status == "completed"
        assert done.result_media_ref["generationId"] == "cm8gen_1"

    assert server.credits == 9  # Only 1 credit charged across crash + recovery + retry
    tryon_posts = [c for c in server.calls if c["url"].endswith("/try-on")]
    assert len(tryon_posts) == 1


def test_late_result_from_old_worker_cannot_overwrite_newer_execution_on_postgres(db):
    """Scenario 8: Fencing token rejects late result/failure/metadata writes from superseded worker."""
    Session = db
    with Session() as s:
        user_id = _seed_user(s, email="p53d-fencing@example.com")
        repo = TryOnJobRepositorySQL(s)
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-1"],
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        old_token = uuid4()
        assert repo.claim_queued_job(
            job_id=job_id,
            processing_started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            worker_id="worker-old",
            lease_token=old_token,
            lease_seconds=30,
        )
        # Expire old lease and recover
        s.execute(
            text("UPDATE tryon_jobs SET lease_expires_at = clock_timestamp() - interval '5 seconds' WHERE id = :jid"),
            {"jid": job_id},
        )
        s.commit()
        assert repo.recover_abandoned_jobs(worker_id="worker-new") != []

        # Retry and claim by new worker with new_token
        assert repo.update_retry(
            job_id=job_id,
            retry_count=1,
            status="queued",
            worker_id="worker-new",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        ) is not None
        new_token = uuid4()
        assert repo.claim_queued_job(
            job_id=job_id,
            processing_started_at=datetime.now(timezone.utc),
            worker_id="worker-new",
            lease_token=new_token,
            lease_seconds=60,
        )

        # Old worker wakes up and attempts late writes with old_token — ALL MUST BE REJECTED
        assert (
            repo.update_person_media_ref(
                job_id=job_id,
                person_media_ref={"stale": True},
                expected_lease_token=old_token,
            )
            is None
        )
        assert (
            repo.update_failure(
                job_id=job_id,
                error_code="STALE_ERROR",
                error_message="old worker failed",
                completed_at=datetime.now(timezone.utc),
                expected_lease_token=old_token,
            )
            is None
        )
        assert (
            repo.update_result(
                job_id=job_id,
                result_media_ref={"key": "stale/result.png"},
                completed_at=datetime.now(timezone.utc),
                expected_lease_token=old_token,
            )
            is None
        )

        # New worker's write with new_token succeeds
        completed = repo.update_result(
            job_id=job_id,
            result_media_ref={"key": f"users/{user_id}/tryon/{job_id}/result.png"},
            completed_at=datetime.now(timezone.utc),
            expected_lease_token=new_token,
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.result_media_ref["key"] == f"users/{user_id}/tryon/{job_id}/result.png"

        # Even after completion, old worker's late result/failure is rejected
        assert (
            repo.update_result(
                job_id=job_id,
                result_media_ref={"key": "stale/overwrite.png"},
                completed_at=datetime.now(timezone.utc),
                expected_lease_token=old_token,
            )
            is None
        )
        final = repo.get_by_id(user_id=user_id, job_id=job_id)
        assert final is not None
        assert final.result_media_ref["key"] == f"users/{user_id}/tryon/{job_id}/result.png"


def test_lease_renewal_and_recovery_race_are_atomic_on_postgres(db):
    """Scenario 9: Concurrent lease renewal vs recovery never produces split-brain state."""
    Session = db
    with Session() as s_seed:
        user_id = _seed_user(s_seed, email="p53d-renew-race@example.com")
        repo = TryOnJobRepositorySQL(s_seed)
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=["g-1"],
            provider="mock",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        tok = uuid4()
        assert repo.claim_queued_job(
            job_id=job_id,
            processing_started_at=datetime.now(timezone.utc),
            worker_id="worker-a",
            lease_token=tok,
            lease_seconds=2,
        )

    def _renew() -> bool:
        with Session() as s:
            return TryOnJobRepositorySQL(s).renew_lease(
                job_id=job_id,
                worker_id="worker-a",
                lease_token=tok,
                lease_seconds=60,
            )

    def _recover() -> int:
        with Session() as s:
            return len(
                TryOnJobRepositorySQL(s).recover_abandoned_jobs(
                    worker_id="worker-b",
                    error_code="INTERRUPTED_BY_RESTART",
                )
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_renew = pool.submit(_renew)
        f_recover = pool.submit(_recover)
        renewed = f_renew.result()
        recovered_count = f_recover.result()

    # Exactly one outcome: either renewal won (recovered==0, job still processing with worker-a)
    # or recovery won if lease had already lapsed (renewed==False, recovered==1, job failed).
    with Session() as s_chk:
        job = TryOnJobRepositorySQL(s_chk).get_by_id(user_id=user_id, job_id=job_id)
        assert job is not None
        if renewed:
            assert recovered_count == 0
            assert job.status == "processing"
            assert job.worker_id == "worker-a"
            assert job.lease_token == tok
        else:
            assert recovered_count == 1
            assert job.status == "failed"
            assert job.worker_id is None
            assert job.lease_token is None


def test_deployment_startup_validation_for_multi_worker_and_lease_bounds(monkeypatch):
    """Deployment safety: reject invalid lease/heartbeat bounds and multi-worker without PostgreSQL."""
    with pytest.raises(ValueError, match="HEARTBEAT_INTERVAL_SECONDS"):
        Settings(
            _env_file=None,
            tryon_worker_lease_seconds=15,
            tryon_worker_heartbeat_interval_seconds=15,
        )

    monkeypatch.setenv("UVICORN_WORKERS", "2")
    prod_non_pg = Settings.model_construct(
        environment="production",
        database_url="sqlite:///./local_unsafe.db",
        allow_dev_token=False,
        tryon_enabled=True,
        tryon_provider="genlook",
        genlook_api_key="gk_prod_valid_key_1234567890",
        operator_api_key="op_prod_valid_key_1234567890_abcdef",
        auth_secret="auth_secret_distinct_1234567890_abcdef",
        media_upload_hmac_secret="upload_secret_distinct_1234567890_abcdef",
        media_upload_key_ring={},
        media_upload_active_key_id="v1",
    )
    with pytest.raises(ValueError, match="PostgreSQL"):
        validate_production_startup(prod_non_pg)

    # With PostgreSQL + R2, multi-worker startup validation passes
    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
    prod_pg = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://user:pass@localhost:5432/fansivibe_prod",
        media_storage_provider="r2",
        r2_bucket_name="fansivibe-prod-media",
        r2_endpoint_url="https://example.r2.cloudflarestorage.com",
        r2_access_key_id="prod_access_key_1234",
        r2_secret_access_key="prod_secret_key_1234567890",
        allow_dev_token=False,
        tryon_enabled=True,
        tryon_provider="genlook",
        genlook_api_key="gk_prod_valid_key_1234567890",
        operator_api_key="op_prod_valid_key_1234567890_abcdef",
        auth_secret="auth_secret_distinct_1234567890_abcdef",
        media_upload_hmac_secret="upload_secret_distinct_1234567890_abcdef",
    )
    validate_production_startup(prod_pg)
