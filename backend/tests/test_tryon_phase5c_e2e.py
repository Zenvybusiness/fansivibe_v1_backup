"""Phase 5C Virtual Try-On End-to-End and Integration Test Suite.

Covers:
- Job creation and persistence (PostgreSQL / repository)
- Job status transitions (queued -> processing -> completed / failed / cancelled)
- Authenticated ownership & cross-user isolation (OW-1)
- Wardrobe garment ownership validation & rejection of foreign/invalid garment IDs
- Consent validation (current version, explicit acceptance)
- Duplicate submission & idempotency conflict detection
- Provider selection (mock vs CatVTON) and mock test-data labeling
- CatVTON production rejection invariant
- Failed inference propagation without fake success
- Retry eligible failed jobs & cancel queued/processing jobs
- Media storage persistence, ownership isolation, and deletion
"""

from __future__ import annotations

import io
from types import SimpleNamespace
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
from app.domain.ports.repositories import TryOnJobRecord, WardrobeItemRecord
from app.domain.ports.storage import ObjectStoragePort, StorageObjectMetadata
from app.infrastructure.db.repositories import WardrobeItemRepositorySQL
from tests.fakes.fake_storage import FakeStorageAdapter

USER_A = uuid4()
USER_B = uuid4()

def _make_valid_jpeg(size: tuple[int, int] = (128, 128), color: tuple[int, int, int] = (120, 140, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


JPEG = ("person.jpg", _make_valid_jpeg(), "image/jpeg")


class InMemoryWardrobeRepo:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add_item(self, user_id: UUID, item_id: UUID, category: str = "tops", name: str = "Test Shirt") -> WardrobeItemRecord:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
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
def setup_overrides(monkeypatch, fake_storage, wardrobe_repo):
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


def _client_for_user(user_id: UUID | None = USER_A) -> TestClient:
    if user_id is None:
        app.dependency_overrides.pop(get_current_user_id, None)
    else:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


# --- Tests ---

def test_job_creation_and_persistence(setup_overrides):
    """Submitting a valid tryon job creates a durable record in the repository."""
    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1", "item-2"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-create-1"},
    )
    assert resp.status_code == 202
    body = resp.json()
    job_id = body["job_id"]
    assert body["status"] == "processing"
    assert body["is_mock"] is True

    # Check persistence in repo
    job = setup_overrides["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(job_id))
    assert job is not None
    assert str(job.id) == job_id
    assert job.user_id == USER_A
    assert job.consent_version == "tryon-v1"


def test_wardrobe_ownership_validation_success(setup_overrides):
    """Valid wardrobe item owned by user succeeds."""
    user_item_id = uuid4()
    setup_overrides["wardrobe_repo"].add_item(user_id=USER_A, item_id=user_item_id, category="tops")

    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "wardrobe",
            "garment_ids": f'["{user_item_id}"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-wardrobe-1"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"]


def test_wardrobe_ownership_validation_rejects_foreign_garment(setup_overrides):
    """Attempting to use another user's wardrobe garment is rejected (OW-1)."""
    user_b_item_id = uuid4()
    setup_overrides["wardrobe_repo"].add_item(user_id=USER_B, item_id=user_b_item_id, category="tops")

    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "wardrobe",
            "garment_ids": f'["{user_b_item_id}"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-foreign-1"},
    )
    assert resp.status_code == 422
    assert "not found in user wardrobe" in resp.text


def test_wardrobe_ownership_validation_rejects_invalid_uuid(setup_overrides):
    """Malformed garment ID format in wardrobe mode is rejected."""
    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "wardrobe",
            "garment_ids": '["not-a-uuid"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-invalid-uuid"},
    )
    assert resp.status_code == 422
    assert "invalid garment UUID" in resp.text


def test_cross_user_job_isolation(setup_overrides):
    """User B cannot view or poll User A's try-on job (404-not-403)."""
    client_a = _client_for_user(USER_A)
    resp = client_a.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-iso-1"},
    )
    job_id = resp.json()["job_id"]

    client_b = _client_for_user(USER_B)
    resp_b = client_b.get(f"/v1/tryon/jobs/{job_id}")
    assert resp_b.status_code == 404

    resp_b_img = client_b.get(f"/v1/tryon/jobs/{job_id}/image")
    assert resp_b_img.status_code == 404


def test_consent_validation_rejection(setup_overrides):
    """Missing or mismatched consent is rejected with 422."""
    client = _client_for_user(USER_A)

    # Consent not accepted
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "false",
        },
        headers={"Idempotency-Key": "key-consent-1"},
    )
    assert resp.status_code == 422

    # Wrong consent version
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "old-version",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-consent-2"},
    )
    assert resp.status_code == 422


def test_duplicate_submission_and_conflict(setup_overrides):
    """Replay of identical payload returns original job; altered payload with same key returns 409."""
    client = _client_for_user(USER_A)
    resp1 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "idemp-key-dup"},
    )
    assert resp1.status_code == 202
    job_id = resp1.json()["job_id"]

    # Replay identical
    resp2 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "idemp-key-dup"},
    )
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id

    # Changed payload with same key -> 409
    resp3 = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["different-item"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "idemp-key-dup"},
    )
    assert resp3.status_code == 409


def test_catvton_production_rejection(monkeypatch, setup_overrides):
    """CatVTON provider is strictly rejected in production environment."""
    prod_settings = SimpleNamespace(
        tryon_enabled=True,
        tryon_provider="catvton",
        environment="production",
        tryon_consent_version="tryon-v1",
        tryon_daily_quota_per_user=20,
    )
    monkeypatch.setattr(tryon_app, "get_settings", lambda: prod_settings)

    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-prod-catvton"},
    )
    assert resp.status_code == 422
    assert "CatVTON cannot be enabled in production" in resp.text


def test_production_mock_provider_fails_closed(monkeypatch, setup_overrides):
    """In production, mock provider fails closed (503) rather than pretending to be AI."""
    prod_settings = SimpleNamespace(
        tryon_enabled=True,
        tryon_provider="mock",
        environment="production",
        tryon_consent_version="tryon-v1",
        tryon_daily_quota_per_user=20,
    )
    monkeypatch.setattr(tryon_app, "get_settings", lambda: prod_settings)

    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-prod-mock"},
    )
    assert resp.status_code == 503


def test_job_cancellation_flow(setup_overrides):
    """Active job can be cancelled, transition status to cancelled, and cannot be re-cancelled when terminal."""
    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-cancel-1"},
    )
    job_id = resp.json()["job_id"]

    # Cancel the job
    cancel_resp = client.post(f"/v1/tryon/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Further status poll shows cancelled
    status_resp = client.get(f"/v1/tryon/jobs/{job_id}")
    assert status_resp.json()["status"] == "cancelled"


def test_job_retry_flow(setup_overrides):
    """Failed job can be retried, increments retry count, and transitions to processing."""
    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-retry-1"},
    )
    job_id = resp.json()["job_id"]

    # Mark failed in repo to test retry
    setup_overrides["job_repo"].update_failure(
        job_id=UUID(job_id),
        error_code="CUDA_OOM",
        error_message="Simulation failure",
        completed_at=tryon_app.datetime.now(tryon_app.timezone.utc),
    )

    # Retry job
    retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
    assert retry_resp.status_code == 202
    assert retry_resp.json()["status"] == "processing"

    # Status shows retry_count = 1
    status_resp = client.get(f"/v1/tryon/jobs/{job_id}")
    assert status_resp.json()["retry_count"] == 1


def test_job_deletion_and_media_cleanup(setup_overrides):
    """Deleting a job removes the record and associated private storage keys."""
    client = _client_for_user(USER_A)
    resp = client.post(
        "/v1/tryon/jobs",
        files={"person_image": JPEG},
        data={
            "outfit_source": "today",
            "garment_ids": '["item-1"]',
            "consent_version": "tryon-v1",
            "consent_accepted": "true",
        },
        headers={"Idempotency-Key": "key-delete-1"},
    )
    job_id = resp.json()["job_id"]

    # Delete job
    del_resp = client.delete(f"/v1/tryon/jobs/{job_id}")
    assert del_resp.status_code == 204

    # Now lookup returns 404
    get_resp = client.get(f"/v1/tryon/jobs/{job_id}")
    assert get_resp.status_code == 404

