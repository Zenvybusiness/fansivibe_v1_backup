"""P5.3F PostgreSQL-backed tests for the Daily Try-On Quota Refund Policy.

Covers all 14 required policy & safety scenarios using disposable PostgreSQL,
FakeStorageAdapter, and MockGenlookServer / stubbed providers (zero live
Genlook or R2 calls).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update

from app.api.errors import ApiError
from app.application import tryon as tryon_app
from app.config.settings import Settings
from app.domain.ports.repositories import (
    REFUNDED_TRYON_ERROR_CODES,
    job_counts_toward_daily_quota,
)
from app.infrastructure.db.models import TryOnJobModel, UserState, Users, WardrobeItems
from app.infrastructure.db.repositories import TryOnJobRepositorySQL, WardrobeItemRepositorySQL
from app.infrastructure.external import genlook_tryon
from tests.fakes.fake_storage import FakeStorageAdapter
from tests.test_tryon_phase5f_genlook import (
    MockGenlookServer,
    TEST_API_KEY,
    VALID_JPEG,
    VALID_PNG,
    VALID_WEBP,
    _genlook_settings,
)


def _seed_user_with_garment(session, *, email: str) -> tuple[UUID, UUID]:
    user = Users(
        auth_provider="local",
        auth_subject=email,
        display_name=email.split("@")[0],
    )
    session.add(user)
    session.flush()
    session.add(UserState(user_id=user.id))
    garment_id = uuid4()
    session.add(
        WardrobeItems(
            id=garment_id,
            user_id=user.id,
            name="Quota Policy Jacket",
            category_id="tops",
            color_id="black",
            image_ref={"key": f"users/{user.id}/wardrobe/{garment_id}/canonical.webp"},
        )
    )
    session.commit()
    return user.id, garment_id


def _create_job(
    repo: TryOnJobRepositorySQL,
    *,
    user_id: UUID,
    garment_id: UUID,
    provider: str = "mock",
    status: str = "queued",
    person_media_ref: dict | None = None,
    idempotency_key: str | None = None,
) -> UUID:
    job_id = uuid4()
    repo.create(
        job_id=job_id,
        user_id=user_id,
        outfit_source="wardrobe",
        garment_id=garment_id,
        garment_ids=[str(garment_id)],
        provider=provider,
        status=status,
        consent_version="tryon-v1",
        consent_accepted_at=datetime.now(timezone.utc),
        person_media_ref=person_media_ref or {"key": f"users/{user_id}/tryon/{job_id}/person.jpg", "contentHash": "hash-1"},
        idempotency_key=idempotency_key or f"idem-{job_id}",
        request_fingerprint=f"fp-{job_id}",
    )
    return job_id


def test_completed_jobs_count_toward_daily_quota(db) -> None:
    """Scenario 1: Completed jobs count as 1 toward daily quota."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-completed@example.com")
        repo = TryOnJobRepositorySQL(s)
        for _ in range(3):
            jid = _create_job(repo, user_id=user_id, garment_id=garment_id, status="processing")
            repo.update_result(
                job_id=jid,
                result_media_ref={"key": f"users/{user_id}/tryon/{jid}/result.png"},
                completed_at=datetime.now(timezone.utc),
            )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 3


@pytest.mark.parametrize(
    "error_code",
    [
        "PROVIDER_TRANSIENT_FAILURE",  # Scenario 2
        "PROVIDER_AUTH_ERROR",         # Scenario 3
        "PROVIDER_CONFIG_ERROR",       # Scenario 3
        "PROVIDER_QUOTA_EXCEEDED",     # Scenario 3
        "STORAGE_FAILURE",             # Scenario 4
        "INTERRUPTED_BY_RESTART",      # Scenario 5
        "STALE_JOB_TIMEOUT",           # Scenario 6
    ],
)
def test_infrastructure_failures_are_refunded(db, error_code: str) -> None:
    """Scenarios 2-6: All approved infrastructure failure codes are refunded."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(
            s, email=f"p53f-infra-{error_code.lower()}@example.com"
        )
        repo = TryOnJobRepositorySQL(s)
        jid = _create_job(repo, user_id=user_id, garment_id=garment_id, status="processing")
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        repo.update_failure(
            job_id=jid,
            error_code=error_code,
            error_message="infra failure",
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 0
        rec = repo.get_by_id(user_id=user_id, job_id=jid)
        assert rec is not None
        assert job_counts_toward_daily_quota(rec) is False


def test_cancellation_before_dispatch_refunded_and_after_genlook_acceptance_counts(
    db, monkeypatch
) -> None:
    """Scenarios 7 & 8: Pre-dispatch cancellation is refunded; post-acceptance Genlook cancellation counts."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-cancel@example.com")
        repo = TryOnJobRepositorySQL(s)

        # 7a. Queued job cancelled before dispatch -> refunded (0)
        pre_job = _create_job(repo, user_id=user_id, garment_id=garment_id, provider="genlook", status="queued")
        tryon_app.cancel_job(user_id=str(user_id), job_id=str(pre_job), job_repo=repo)
        assert repo.count_today_jobs(user_id=user_id, day=today) == 0

        # 7b. Image uploaded to Genlook, cancelled before POST /try-on -> refunded (0)
        img_only_job = _create_job(
            repo,
            user_id=user_id,
            garment_id=garment_id,
            provider="genlook",
            status="processing",
            person_media_ref={
                "key": f"users/{user_id}/tryon/img-only/person.jpg",
                "contentHash": "h-img",
                "genlook": {"imageId": "img_123"},
            },
        )
        tryon_app.cancel_job(user_id=str(user_id), job_id=str(img_only_job), job_repo=repo)
        assert repo.count_today_jobs(user_id=user_id, day=today) == 0

        # 8a. Cancelled after Genlook accepted generation (generationId present) -> counts as 1
        accepted_job = _create_job(
            repo,
            user_id=user_id,
            garment_id=garment_id,
            provider="genlook",
            status="processing",
            person_media_ref={
                "key": f"users/{user_id}/tryon/accepted/person.jpg",
                "contentHash": "h-acc",
                "genlook": {"generationId": "cm8gen_accepted", "generationStatus": "PENDING"},
            },
        )
        tryon_app.cancel_job(user_id=str(user_id), job_id=str(accepted_job), job_repo=repo)
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        # 8b. Cancelled while POST /try-on dispatch was ambiguous (pendingIdempotencyKey present) -> counts as 1
        ambiguous_job = _create_job(
            repo,
            user_id=user_id,
            garment_id=garment_id,
            provider="genlook",
            status="processing",
            person_media_ref={
                "key": f"users/{user_id}/tryon/ambig/person.jpg",
                "contentHash": "h-amb",
                "genlook": {"pendingIdempotencyKey": "fv-tryon-ambig-a0"},
            },
        )
        tryon_app.cancel_job(user_id=str(user_id), job_id=str(ambiguous_job), job_repo=repo)
        assert repo.count_today_jobs(user_id=user_id, day=today) == 2

        # 8c. Explicitly refunded Genlook state -> does not count
        refunded_cancel = _create_job(
            repo,
            user_id=user_id,
            garment_id=garment_id,
            provider="genlook",
            status="processing",
            person_media_ref={
                "key": f"users/{user_id}/tryon/ref/person.jpg",
                "contentHash": "h-ref",
                "genlook": {"generationId": "cm8gen_ref", "refunded": True},
            },
        )
        tryon_app.cancel_job(user_id=str(user_id), job_id=str(refunded_cancel), job_repo=repo)
        assert repo.count_today_jobs(user_id=user_id, day=today) == 2


def test_retry_does_not_consume_additional_daily_slot(db, monkeypatch) -> None:
    """Scenario 9: Retrying an existing job never consumes another daily quota slot."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-retry@example.com")
        repo = TryOnJobRepositorySQL(s)
        # Create 1 completed job (fills quota=1) and 1 non-refunded failed job?
        # Even simpler: create 1 failed PAYLOAD_REJECTED job (counts as 1, filling quota=1)
        jid = _create_job(repo, user_id=user_id, garment_id=garment_id, status="processing")
        repo.update_failure(
            job_id=jid,
            error_code="PAYLOAD_REJECTED",
            error_message="bad input",
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="mock",
                tryon_enabled=True,
                tryon_daily_quota_per_user=1,
            ),
        )

        # New submission is blocked at quota=1
        with pytest.raises(ApiError) as exc:
            tryon_app.submit_job(
                user_id=str(user_id),
                outfit_source="wardrobe",
                garment_ids=[str(garment_id)],
                person_content_type="image/jpeg",
                person_bytes=VALID_JPEG,
                consent_version="tryon-v1",
                consent_accepted=True,
                idempotency_key="new-job-blocked",
                wardrobe_repo=WardrobeItemRepositorySQL(s),
                job_repo=repo,
            )
        assert exc.value.status_code == 429

        # Retry of the existing job succeeds without consuming a second slot
        retried = tryon_app.retry_job(user_id=str(user_id), job_id=str(jid), job_repo=repo)
        assert retried.status == "processing"
        assert retried.retry_count == 1
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        repo.update_result(
            job_id=jid,
            result_media_ref={"key": f"users/{user_id}/tryon/{jid}/result.png"},
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1


def test_infra_failure_followed_by_successful_new_job_consumes_one_slot(
    db, monkeypatch
) -> None:
    """Scenario 10: A refunded infrastructure failure followed by a new successful job consumes 1 slot."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-seq@example.com")
        repo = TryOnJobRepositorySQL(s)
        wardrobe_repo = WardrobeItemRepositorySQL(s)

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="mock",
                tryon_enabled=True,
                tryon_daily_quota_per_user=1,
            ),
        )

        j1, created1 = tryon_app.submit_job(
            user_id=str(user_id),
            outfit_source="wardrobe",
            garment_ids=[str(garment_id)],
            person_content_type="image/jpeg",
            person_bytes=VALID_JPEG,
            consent_version="tryon-v1",
            consent_accepted=True,
            idempotency_key="seq-1",
            wardrobe_repo=wardrobe_repo,
            job_repo=repo,
        )
        assert created1 is True
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        # Fails with infrastructure error -> refunded
        repo.update_failure(
            job_id=j1.id,
            error_code="PROVIDER_TRANSIENT_FAILURE",
            error_message="upstream 503",
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 0

        # New submission now succeeds and completes -> total daily quota used = 1
        j2, created2 = tryon_app.submit_job(
            user_id=str(user_id),
            outfit_source="wardrobe",
            garment_ids=[str(garment_id)],
            person_content_type="image/jpeg",
            person_bytes=VALID_JPEG,
            consent_version="tryon-v1",
            consent_accepted=True,
            idempotency_key="seq-2",
            wardrobe_repo=wardrobe_repo,
            job_repo=repo,
        )
        assert created2 is True
        repo.update_result(
            job_id=j2.id,
            result_media_ref={"key": f"users/{user_id}/tryon/{j2.id}/result.png"},
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1


def test_concurrent_submissions_respect_quota_with_refunded_jobs_on_postgres(
    db, monkeypatch
) -> None:
    """Scenario 11: Concurrent submissions under PG advisory lock cannot exceed daily quota."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-race@example.com")
        repo = TryOnJobRepositorySQL(s)
        # Seed 2 refunded jobs that must NOT consume slots
        for code in ("STORAGE_FAILURE", "INTERRUPTED_BY_RESTART"):
            jid = _create_job(repo, user_id=user_id, garment_id=garment_id, status="processing")
            repo.update_failure(
                job_id=jid,
                error_code=code,
                error_message="refunded",
                completed_at=datetime.now(timezone.utc),
            )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 0

    monkeypatch.setattr(
        tryon_app,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            tryon_provider="mock",
            tryon_enabled=True,
            tryon_daily_quota_per_user=3,
            tryon_max_concurrent_jobs_per_user=10,
            tryon_max_concurrent_jobs_global=10,
        ),
    )

    def _submit(idx: int) -> tuple[str, bool]:
        with Session() as s:
            try:
                job, created = tryon_app.submit_job(
                    user_id=str(user_id),
                    outfit_source="wardrobe",
                    garment_ids=[str(garment_id)],
                    person_content_type="image/jpeg",
                    person_bytes=VALID_JPEG,
                    consent_version="tryon-v1",
                    consent_accepted=True,
                    idempotency_key=f"p53f-race-{idx}",
                    wardrobe_repo=WardrobeItemRepositorySQL(s),
                    job_repo=TryOnJobRepositorySQL(s),
                )
                return str(job.id), created
            except ApiError as exc:
                return f"ERR:{exc.status_code}", False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_submit, range(8)))

    assert sum(1 for _, created in results if created) == 3, results
    assert sum(1 for val, _ in results if val == "ERR:429") == 5, results
    with Session() as s:
        assert TryOnJobRepositorySQL(s).count_today_jobs(user_id=user_id, day=today) == 3


def test_utc_midnight_boundary_accounting(db) -> None:
    """Scenario 12: UTC midnight boundaries isolate day D from day D+1."""
    Session = db
    day_d = date(2026, 11, 26)
    day_d1 = date(2026, 11, 27)
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-utc@example.com")
        repo = TryOnJobRepositorySQL(s)

        j_end_d = _create_job(repo, user_id=user_id, garment_id=garment_id, status="completed")
        j_start_d1 = _create_job(repo, user_id=user_id, garment_id=garment_id, status="completed")

        s.execute(
            update(TryOnJobModel)
            .where(TryOnJobModel.id == j_end_d)
            .values(created_at=datetime(2026, 11, 26, 23, 59, 59, 999999, tzinfo=timezone.utc))
        )
        s.execute(
            update(TryOnJobModel)
            .where(TryOnJobModel.id == j_start_d1)
            .values(created_at=datetime(2026, 11, 27, 0, 0, 0, 0, tzinfo=timezone.utc))
        )
        s.commit()

        assert repo.count_today_jobs(user_id=user_id, day=day_d) == 1
        assert repo.count_today_jobs(user_id=user_id, day=day_d1) == 1


def test_concurrency_limits_retry_cap_and_non_infra_failures_remain_enforced(
    db, monkeypatch
) -> None:
    """Scenario 13: Per-user concurrency, retry cap (_MAX_TRYON_RETRIES=3), and non-infra failures remain enforced."""
    Session = db
    today = datetime.now(timezone.utc).date()
    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-abuse@example.com")
        repo = TryOnJobRepositorySQL(s)
        wardrobe_repo = WardrobeItemRepositorySQL(s)

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="mock",
                tryon_enabled=True,
                tryon_daily_quota_per_user=20,
                tryon_max_concurrent_jobs_per_user=2,
                tryon_max_concurrent_jobs_global=10,
            ),
        )

        # 2 active jobs hit per-user concurrency limit
        active_ids: list[UUID] = []
        for i in range(2):
            job, _ = tryon_app.submit_job(
                user_id=str(user_id),
                outfit_source="wardrobe",
                garment_ids=[str(garment_id)],
                person_content_type="image/jpeg",
                person_bytes=VALID_JPEG,
                consent_version="tryon-v1",
                consent_accepted=True,
                idempotency_key=f"conc-{i}",
                wardrobe_repo=wardrobe_repo,
                job_repo=repo,
            )
            active_ids.append(job.id)
        with pytest.raises(ApiError) as exc_conc:
            tryon_app.submit_job(
                user_id=str(user_id),
                outfit_source="wardrobe",
                garment_ids=[str(garment_id)],
                person_content_type="image/jpeg",
                person_bytes=VALID_JPEG,
                consent_version="tryon-v1",
                consent_accepted=True,
                idempotency_key="conc-3",
                wardrobe_repo=wardrobe_repo,
                job_repo=repo,
            )
        assert exc_conc.value.status_code == 429

        # Complete the active jobs so retry cap can be exercised
        for aid in active_ids:
            repo.update_result(
                job_id=aid,
                result_media_ref={"key": f"users/{user_id}/tryon/{aid}/result.png"},
                completed_at=datetime.now(timezone.utc),
            )

        # Non-infrastructure failure (AI_INFERENCE_FAILURE / PAYLOAD_REJECTED) still counts
        j_non_infra = _create_job(repo, user_id=user_id, garment_id=garment_id, status="processing")
        repo.update_failure(
            job_id=j_non_infra,
            error_code="AI_INFERENCE_FAILURE",
            error_message="model error",
            completed_at=datetime.now(timezone.utc),
        )
        assert repo.count_today_jobs(user_id=user_id, day=today) == 3

        # Retry cap (_MAX_TRYON_RETRIES = 3) remains enforced
        for attempt in range(3):
            retried = tryon_app.retry_job(user_id=str(user_id), job_id=str(j_non_infra), job_repo=repo)
            assert retried.retry_count == attempt + 1
            repo.update_failure(
                job_id=j_non_infra,
                error_code="PROVIDER_TRANSIENT_FAILURE",
                error_message="transient",
                completed_at=datetime.now(timezone.utc),
            )
        with pytest.raises(ApiError) as exc_retry:
            tryon_app.retry_job(user_id=str(user_id), job_id=str(j_non_infra), job_repo=repo)
        assert exc_retry.value.status_code == 409


def test_genlook_credit_and_idempotency_safeguards_intact(
    db, monkeypatch
) -> None:
    """Scenario 14: Cancelled-after-acceptance Genlook job counts toward quota and reuses generationId on retry."""
    server = MockGenlookServer(initial_credits=10)
    monkeypatch.setattr(
        tryon_app,
        "get_settings",
        lambda: _genlook_settings(tryon_daily_quota_per_user=20),
    )
    orig_init = genlook_tryon.GenlookTryOnProvider.__init__

    def _patched_init(self_p, config, **kw):
        kw.setdefault("http_client", server)
        orig_init(self_p, config, **kw)

    monkeypatch.setattr(genlook_tryon.GenlookTryOnProvider, "__init__", _patched_init)

    storage = FakeStorageAdapter()
    Session = db
    today = datetime.now(timezone.utc).date()

    with Session() as s:
        user_id, garment_id = _seed_user_with_garment(s, email="p53f-genlook@example.com")
        repo = TryOnJobRepositorySQL(s)
        wardrobe_repo = WardrobeItemRepositorySQL(s)

        asyncio.run(
            storage.put_object(
                f"users/{user_id}/wardrobe/{garment_id}/canonical.webp",
                VALID_WEBP,
                content_type="image/webp",
            )
        )
        job_id = _create_job(repo, user_id=user_id, garment_id=garment_id, provider="genlook", status="queued")
        person_key = f"users/{user_id}/tryon/{job_id}/person.jpg"
        asyncio.run(storage.put_object(person_key, VALID_JPEG, content_type="image/jpeg"))

        # Cancel during Genlook polling (after POST /try-on accepted and charged 1 credit)
        orig_get = server.get

        def _cancel_on_poll(url, **kw):
            if "/generations/" in url:
                with Session() as s_cancel:
                    tryon_app.cancel_job(
                        user_id=str(user_id),
                        job_id=str(job_id),
                        job_repo=TryOnJobRepositorySQL(s_cancel),
                    )
            return orig_get(url, **kw)

        server.get = _cancel_on_poll  # type: ignore[method-assign]
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=user_id,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )
        server.get = orig_get  # type: ignore[method-assign]

        # 1 Genlook credit consumed, and daily quota counts as 1
        assert server.credits == 9
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1

        # Retry resumes existing generationId without consuming a second Genlook credit or second daily slot
        tryon_app.retry_job(user_id=str(user_id), job_id=str(job_id), job_repo=repo)
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=user_id,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )
        assert server.credits == 9
        assert repo.count_today_jobs(user_id=user_id, day=today) == 1
        done = repo.get_by_id(user_id=user_id, job_id=job_id)
        assert done is not None
        assert done.status == "completed"
