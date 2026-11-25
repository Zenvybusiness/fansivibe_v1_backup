"""Comprehensive reliability, failure handling, and media security test suite (Phase 5C.1).

Covers Section 5 (Reliability & Failure Handling):
- Backend restart with queued jobs
- Backend restart with processing jobs
- Worker exception
- CatVTON subprocess failure
- GPU lease timeout
- Cancellation during processing
- Duplicate idempotency key
- Storage failure after inference
- Result persistence failure
- Deletion when one media deletion operation fails

Covers Section 6 (Media Security):
- User A cannot access User B's job
- User A cannot retrieve User B's result image
- User A cannot delete User B's media
- Raw object-storage paths are never exposed
- Signed access is scoped correctly
- Deletion handles partial storage failures without leaving inconsistent records
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
from typing import Any, Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
import app.application.tryon as tryon_app
from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import ApiError
from app.domain.ports.repositories import TryOnJobRecord, WardrobeItemRecord
from app.domain.ports.storage import ObjectStoragePort, StorageObjectMetadata
from tests.fakes.fake_storage import FakeStorageAdapter

USER_A = uuid4()
USER_B = uuid4()

def _make_valid_jpeg(size: tuple[int, int] = (128, 128), color: tuple[int, int, int] = (140, 120, 100)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


JPEG = ("person.jpg", _make_valid_jpeg(), "image/jpeg")


class FailingStorageAdapter(FakeStorageAdapter):
    """Storage adapter that simulates failures on specified operations or keys."""

    def __init__(self, fail_put: bool = False, fail_delete_keys: set[str] | None = None) -> None:
        super().__init__()
        self.fail_put = fail_put
        self.fail_delete_keys = fail_delete_keys or set()

    async def put_object(self, key: str, data: bytes, *, content_type: str = "image/webp", custom_metadata: Optional[dict[str, str]] = None) -> StorageObjectMetadata:
        if self.fail_put:
            raise RuntimeError("Simulated R2 storage outage")
        return await super().put_object(key, data, content_type=content_type, custom_metadata=custom_metadata)

    async def delete_object(self, key: str) -> bool:
        if key in self.fail_delete_keys:
            raise RuntimeError(f"Simulated storage deletion failure for {key}")
        return await super().delete_object(key)


class InMemoryWardrobeRepo:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add_item(self, user_id: UUID, item_id: UUID, category: str = "tops", name: str = "Test Shirt") -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        record = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name=name,
            category=category,
            color="navy",
            material="cotton",
            is_favorite=False,
            image_ref={"key": f"users/{user_id}/wardrobe/{item_id}/input.webp"},
            created_at=now,
            updated_at=now,
        )
        self.items[(user_id, item_id)] = record
        return record

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        return self.items.get((user_id, item_id))


@pytest.fixture
def fake_storage():
    return FakeStorageAdapter()


@pytest.fixture
def wardrobe_repo():
    repo = InMemoryWardrobeRepo()
    return repo


@pytest.fixture
def setup_overrides(fake_storage, wardrobe_repo):
    tryon_app.reset_for_tests()
    in_mem_job_repo = tryon_app._IN_MEMORY_REPO

    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_tryon_repository] = lambda: in_mem_job_repo
    app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo

    yield {
        "job_repo": in_mem_job_repo,
        "wardrobe_repo": wardrobe_repo,
        "storage": fake_storage,
    }

    app.dependency_overrides.pop(get_storage_adapter, None)
    app.dependency_overrides.pop(get_tryon_repository, None)
    app.dependency_overrides.pop(get_tryon_wardrobe_repository, None)
    app.dependency_overrides.pop(get_current_user_id, None)


def _set_user(user_id: UUID | None) -> TestClient:
    if user_id is None:
        app.dependency_overrides.pop(get_current_user_id, None)
    else:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


# === SECTION 5: RELIABILITY AND FAILURE HANDLING TESTS ===

def test_backend_restart_with_queued_jobs(setup_overrides):
    """Jobs in 'queued' state at server restart are safely marked failed with INTERRUPTED_BY_RESTART."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=["item-1"],
        provider="catvton",
        status="queued",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    recovered = tryon_app.recover_interrupted_jobs(repo)
    assert recovered == 1

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "INTERRUPTED_BY_RESTART"
    assert "server restart" in job.error_message
    assert job.completed_at is not None


def test_backend_restart_with_processing_jobs(setup_overrides):
    """Jobs in 'processing' state at server restart are safely marked failed with INTERRUPTED_BY_RESTART."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=["item-1"],
        provider="catvton",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    recovered = tryon_app.recover_interrupted_jobs(repo)
    assert recovered == 1

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "INTERRUPTED_BY_RESTART"
    assert job.completed_at is not None


def test_worker_exception_handling(setup_overrides, monkeypatch):
    """Worker unexpected exception marks job failed and prevents false completion."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="today",
        garment_id=None,
        garment_ids=["item-1"],
        provider="mock",
        status="queued",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    def failing_render(*args, **kwargs):
        raise RuntimeError("Worker kernel failure")

    monkeypatch.setattr(tryon_app.MockTryOnProvider, "render", failing_render)

    asyncio.run(tryon_app.execute_tryon_inference(
        job_id=job_id,
        user_id=USER_A,
        job_repo=repo,
        storage=setup_overrides["storage"],
    ))

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "AI_INFERENCE_FAILURE"
    assert job.completed_at is not None


def test_catvton_subprocess_failure(setup_overrides, monkeypatch):
    """CatVTON subprocess non-zero exit code marks job failed with AI_INFERENCE_FAILURE."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=["item-1"],
        provider="catvton",
        status="queued",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    monkeypatch.setattr(tryon_app.get_settings(), "tryon_provider", "catvton")

    def failing_render(*args, **kwargs):
        raise RuntimeError("CatVTON diffusion failed (exit code 1): CUDA out of memory")

    monkeypatch.setattr(tryon_app.CatVTONTryOnProvider, "render", failing_render)

    asyncio.run(tryon_app.execute_tryon_inference(
        job_id=job_id,
        user_id=USER_A,
        job_repo=repo,
        storage=setup_overrides["storage"],
    ))

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "AI_INFERENCE_FAILURE"


def test_gpu_lease_timeout(setup_overrides, monkeypatch):
    """GPU lease acquisition timeout marks job failed with AI_INFERENCE_FAILURE."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=["item-1"],
        provider="catvton",
        status="queued",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    monkeypatch.setattr(tryon_app.get_settings(), "tryon_provider", "catvton")

    def timeout_render(*args, **kwargs):
        raise TimeoutError("Timed out waiting for Priority 2 GPU lease")

    monkeypatch.setattr(tryon_app.CatVTONTryOnProvider, "render", timeout_render)

    asyncio.run(tryon_app.execute_tryon_inference(
        job_id=job_id,
        user_id=USER_A,
        job_repo=repo,
        storage=setup_overrides["storage"],
    ))

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "AI_INFERENCE_FAILURE"


def test_cancellation_during_processing(setup_overrides):
    """Job cancelled during processing discards result and remains cancelled."""
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="today",
        garment_id=None,
        garment_ids=["item-1"],
        provider="mock",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    # User cancels the job
    tryon_app.cancel_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
    cancelled_job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert cancelled_job.status == "cancelled"

    # Worker attempts to execute / persist
    asyncio.run(tryon_app.execute_tryon_inference(
        job_id=job_id,
        user_id=USER_A,
        job_repo=repo,
        storage=setup_overrides["storage"],
    ))

    # Job must remain cancelled and never become completed
    final_job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert final_job.status == "cancelled"
    assert final_job.result_media_ref is None


def test_duplicate_idempotency_key(setup_overrides):
    """Identical submission returns 202 duplicate-safe; modified payload returns 409 conflict."""
    client = _set_user(USER_A)
    key = "idem-test-sec5"

    resp1 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": key},
    )
    assert resp1.status_code == 202
    job_id = resp1.json()["job_id"]

    # Identical replay returns same job_id
    resp2 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": key},
    )
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id

    # Changed payload with same key returns 409 Conflict
    resp3 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-different"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": key},
    )
    assert resp3.status_code == 409


def test_storage_failure_after_inference(setup_overrides):
    """Storage failure during result save marks job failed with STORAGE_FAILURE."""
    failing_storage = FailingStorageAdapter(fail_put=True)
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="today",
        garment_id=None,
        garment_ids=["item-1"],
        provider="mock",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    asyncio.run(tryon_app.execute_tryon_inference(
        job_id=job_id,
        user_id=USER_A,
        job_repo=repo,
        storage=failing_storage,
    ))

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error_code == "STORAGE_FAILURE"
    assert job.completed_at is not None


def test_result_persistence_failure_leaves_not_completed(setup_overrides):
    """If database update_result fails, job must NEVER become falsely completed."""
    import unittest.mock as mock

    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="today",
        garment_id=None,
        garment_ids=["item-1"],
        provider="mock",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )

    with mock.patch.object(repo, "update_result", side_effect=RuntimeError("DB drop")):
        try:
            asyncio.run(tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=setup_overrides["storage"],
            ))
        except Exception:
            pass

    job = repo.get_by_id(user_id=USER_A, job_id=job_id)
    assert job.status != "completed", "Job must never become falsely completed"


def test_deletion_when_one_media_fails(setup_overrides):
    """Deletion succeeds and removes DB record even when one storage deletion raises an error."""
    person_key = f"users/{USER_A}/tryon/job-del-test/person.jpg"
    result_key = f"users/{USER_A}/tryon/job-del-test/result.jpg"

    storage = FailingStorageAdapter(fail_delete_keys={person_key})
    repo = setup_overrides["job_repo"]
    job_id = uuid4()
    now = datetime.now(timezone.utc)
    repo.create(
        job_id=job_id,
        user_id=USER_A,
        outfit_source="today",
        garment_id=None,
        garment_ids=["item-1"],
        provider="mock",
        status="queued",
        consent_version="tryon-v1",
        consent_accepted_at=now,
        person_media_ref={"key": person_key},
    )
    repo.update_result(
        job_id=job_id,
        result_media_ref={"key": result_key},
        completed_at=now,
    )

    # Call delete
    success = asyncio.run(tryon_app.delete_job_and_media(
        user_id=str(USER_A),
        job_id=str(job_id),
        job_repo=repo,
        storage=storage,
    ))
    assert success is True

    # Database row is deleted
    assert repo.get_by_id(user_id=USER_A, job_id=job_id) is None


# === SECTION 6: MEDIA SECURITY TESTS ===

def test_user_a_cannot_access_user_b_job(setup_overrides):
    """User B cannot view or poll User A's tryon job (OW-1, returns 404 Not Found)."""
    client_a = _set_user(USER_A)
    resp_a = client_a.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "sec-job-iso-1"},
    )
    job_id = resp_a.json()["job_id"]

    client_b = _set_user(USER_B)
    resp_b = client_b.get(f"/v1/tryon/jobs/{job_id}")
    assert resp_b.status_code == 404


def test_user_a_cannot_retrieve_user_b_result_image(setup_overrides):
    """User B cannot retrieve User A's composite result image (OW-1, returns 404 Not Found)."""
    client_a = _set_user(USER_A)
    resp_a = client_a.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "sec-img-iso-1"},
    )
    job_id = resp_a.json()["job_id"]

    # Poll twice as User A to complete mock job
    client_a.get(f"/v1/tryon/jobs/{job_id}")
    client_a.get(f"/v1/tryon/jobs/{job_id}")

    # User A can retrieve image
    assert client_a.get(f"/v1/tryon/jobs/{job_id}/image").status_code == 200

    # User B gets 404
    client_b = _set_user(USER_B)
    assert client_b.get(f"/v1/tryon/jobs/{job_id}/image").status_code == 404


def test_user_a_cannot_delete_user_b_media(setup_overrides):
    """User B cannot delete User A's try-on job or media (OW-1, returns 404 Not Found)."""
    client_a = _set_user(USER_A)
    resp_a = client_a.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "sec-del-iso-1"},
    )
    job_id = resp_a.json()["job_id"]

    client_b = _set_user(USER_B)
    resp_b = client_b.delete(f"/v1/tryon/jobs/{job_id}")
    assert resp_b.status_code == 404

    # User A's job still exists
    client_a_again = _set_user(USER_A)
    assert client_a_again.get(f"/v1/tryon/jobs/{job_id}").status_code == 200


def test_raw_storage_paths_never_exposed(setup_overrides):
    """Public wire schemas never expose raw bucket names, object storage URLs, or secret credentials."""
    client = _set_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "sec-path-1"},
    )
    body = resp.json()
    assert "bucket" not in body
    assert "r2.cloudflarestorage.com" not in str(body)
    assert "s3://" not in str(body)

    job_id = body["job_id"]
    client.get(f"/v1/tryon/jobs/{job_id}")
    status_body = client.get(f"/v1/tryon/jobs/{job_id}").json()

    assert "bucket" not in status_body
    assert "r2.cloudflarestorage.com" not in str(status_body)
    assert "s3://" not in str(status_body)


def test_signed_access_scoped_correctly(setup_overrides):
    """Media keys are strictly scoped under users/{user_id}/tryon/{job_id}/..."""
    client = _set_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "sec-scope-1"},
    )
    job_id = resp.json()["job_id"]
    client.get(f"/v1/tryon/jobs/{job_id}")
    status_body = client.get(f"/v1/tryon/jobs/{job_id}").json()

    result_ref = status_body.get("result_media_ref")
    assert result_ref is not None
    key = result_ref["key"]
    expected_prefix = f"users/{USER_A}/tryon/{job_id}/"
    assert key.startswith(expected_prefix), f"Key {key} must start with {expected_prefix}"
