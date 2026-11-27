"""Regression tests for P5.2C: Backend Wardrobe Media Lifecycle.

Uses disposable PostgreSQL (`db` fixture) and `FakeStorageAdapter`.
Asserts actual database rows (`WardrobeItems`, `MediaUploadAuthorization`)
and fake storage object state.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.application.media import (
    cleanup_pending_media_deletions,
    prune_expired_authorizations,
)
from app.domain.ports.storage import StorageError
from app.infrastructure.db.models import (
    Colors,
    Materials,
    MediaUploadAuthorization,
    Users,
    UserState,
    WardrobeCategories,
    WardrobeItems,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

pytestmark = pytest.mark.usefixtures("db")

VALID_SHA256_A = "a" * 64
VALID_SHA256_B = "b" * 64


def _seed_vocab(SessionLocal) -> None:
    with SessionLocal() as session:
        for code, label in (
            ("tops", "Tops"),
            ("bottoms", "Bottoms"),
            ("outerwear", "Outerwear"),
        ):
            if session.get(WardrobeCategories, code) is None:
                session.add(WardrobeCategories(code=code, label=label, sort_order=1, active=True))
        for code, label in (("charcoal", "Charcoal"), ("navy", "Navy"), ("white", "White")):
            if session.get(Colors, code) is None:
                session.add(Colors(code=code, label=label, sort_order=1, active=True))
        for code, label in (("cotton", "Cotton"), ("wool", "Wool")):
            if session.get(Materials, code) is None:
                session.add(Materials(code=code, label=label, sort_order=1, active=True))
        session.commit()


def _create_user(SessionLocal, subject: str) -> UUID:
    with SessionLocal() as session:
        user = Users(auth_provider="dev", auth_subject=subject, display_name=subject)
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
        session.commit()
        return user.id


def _create_published_media(
    SessionLocal,
    storage: FakeStorageAdapter,
    user_id: UUID,
    *,
    sha256: str = VALID_SHA256_A,
    payload: bytes = b"RIFF\x00\x00\x00\x00WEBPfake-image",
    expired: bool = False,
) -> tuple[UUID, str]:
    upload_id = uuid4()
    lease_token = uuid4()
    canonical_key = f"users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp"
    staging_key = f"staging/users/{user_id}/wardrobe/{upload_id}.webp"
    now = datetime.now(timezone.utc)
    expires_at = now - timedelta(hours=1) if expired else now + timedelta(hours=24)

    storage.put_object_bytes(canonical_key, payload, content_type="image/webp")

    with SessionLocal() as session:
        auth = MediaUploadAuthorization(
            user_id=user_id,
            idempotency_key=f"idemp-{upload_id}",
            upload_id=upload_id,
            key_version="v1",
            request_fingerprint=f"fp-{upload_id}",
            staging_key=staging_key,
            content_type="image/webp",
            size_bytes=len(payload),
            created_at=now - timedelta(hours=2),
            expires_at=expires_at,
            status="published",
            canonical_key=canonical_key,
            canonical_sha256=sha256,
            canonical_size_bytes=len(payload),
            canonical_width=512,
            canonical_height=512,
            completed_at=now,
        )
        session.add(auth)
        session.commit()

    return upload_id, canonical_key


def _create_wardrobe_item(
    SessionLocal,
    user_id: UUID,
    *,
    name: str = "Classic Tee",
    image_ref: dict | None = None,
) -> UUID:
    with SessionLocal() as session:
        item = WardrobeItems(
            user_id=user_id,
            name=name,
            category_id="tops",
            color_id="navy",
            material_id="cotton",
            image_ref=image_ref,
        )
        session.add(item)
        session.commit()
        return item.id


def _make_image_ref(upload_id: UUID, key: str, *, sha256: str = VALID_SHA256_A, **extra) -> dict:
    ref = {
        "uploadId": str(upload_id),
        "objectKey": key,
        "mediaType": "image/webp",
        "width": 512,
        "height": 512,
        "sizeBytes": 21,
        "contentHash": sha256,
        "status": "ready",
    }
    ref.update(extra)
    return ref


def _override_client(SessionLocal, storage: FakeStorageAdapter, user_id: UUID) -> TestClient:
    def _get_db_override():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_storage_adapter] = lambda: storage
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def test_1_delete_owned_item_deletes_unreferenced_image_and_auth(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-1")
    upload_id, key = _create_published_media(db, storage, user_a)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(upload_id, key))

    client = _override_client(db, storage, user_a)
    resp = client.delete(f"/v1/wardrobe/items/{item_id}")
    assert resp.status_code == 204

    with db() as session:
        assert session.get(WardrobeItems, item_id) is None
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one_or_none()
        assert auth is None

    assert not storage.object_exists_sync(key)


def test_2_delete_item_preserves_image_referenced_by_another_item(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-2")
    upload_id, key = _create_published_media(db, storage, user_a)
    ref = _make_image_ref(upload_id, key)
    item_1 = _create_wardrobe_item(db, user_a, name="Item 1", image_ref=ref)
    item_2 = _create_wardrobe_item(db, user_a, name="Item 2", image_ref=dict(ref))

    client = _override_client(db, storage, user_a)
    resp = client.delete(f"/v1/wardrobe/items/{item_1}")
    assert resp.status_code == 204

    with db() as session:
        assert session.get(WardrobeItems, item_1) is None
        assert session.get(WardrobeItems, item_2) is not None
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one_or_none()
        assert auth is not None
        assert auth.status == "published"

    assert storage.object_exists_sync(key)


def test_3_foreign_user_delete_returns_404_and_deletes_no_media(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-3a")
    user_b = _create_user(db, "p52c-user-3b")
    upload_id, key = _create_published_media(db, storage, user_a)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(upload_id, key))

    client = _override_client(db, storage, user_b)
    resp = client.delete(f"/v1/wardrobe/items/{item_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    with db() as session:
        assert session.get(WardrobeItems, item_id) is not None
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one_or_none()
        assert auth is not None
        assert auth.status == "published"

    assert storage.object_exists_sync(key)


def test_4_and_5_replace_image_attaches_new_cleans_old_and_preserves_new(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-4")
    old_upload_id, old_key = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_A)
    new_upload_id, new_key = _create_published_media(
        db, storage, user_a, sha256=VALID_SHA256_B, payload=b"RIFF\x00\x00\x00\x00WEBPnew-image"
    )
    item_id = _create_wardrobe_item(
        db, user_a, image_ref=_make_image_ref(old_upload_id, old_key)
    )

    client = _override_client(db, storage, user_a)
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"imageRef": {"uploadId": str(new_upload_id)}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imageRef"]["uploadId"] == str(new_upload_id)
    assert body["imageRef"]["objectKey"] == new_key

    with db() as session:
        item = session.get(WardrobeItems, item_id)
        assert item is not None
        assert item.image_ref["uploadId"] == str(new_upload_id)
        assert item.image_ref["objectKey"] == new_key

        old_auth = session.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.upload_id == old_upload_id
            )
        ).scalar_one_or_none()
        new_auth = session.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.upload_id == new_upload_id
            )
        ).scalar_one_or_none()
        assert old_auth is None
        assert new_auth is not None
        assert new_auth.status == "published"

    assert not storage.object_exists_sync(old_key)
    assert storage.object_exists_sync(new_key)

    # Replacing with the same image must NOT delete it
    resp_same = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"imageRef": {"uploadId": str(new_upload_id)}},
    )
    assert resp_same.status_code == 200
    assert storage.object_exists_sync(new_key)


def test_6_clear_image_removes_only_old_unreferenced_object(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-6")
    upload_1, key_1 = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_A)
    upload_2, key_2 = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_B)
    item_1 = _create_wardrobe_item(db, user_a, name="Cleared", image_ref=_make_image_ref(upload_1, key_1))
    item_2 = _create_wardrobe_item(db, user_a, name="Kept", image_ref=_make_image_ref(upload_2, key_2))

    client = _override_client(db, storage, user_a)
    resp = client.patch(f"/v1/wardrobe/items/{item_1}", json={"clearImageRef": True})
    assert resp.status_code == 200
    assert resp.json()["imageRef"] is None

    with db() as session:
        assert session.get(WardrobeItems, item_1).image_ref is None
        assert session.get(WardrobeItems, item_2).image_ref["objectKey"] == key_2
        auth_1 = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_1)
        ).scalar_one_or_none()
        auth_2 = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_2)
        ).scalar_one_or_none()
        assert auth_1 is None
        assert auth_2 is not None and auth_2.status == "published"

    assert not storage.object_exists_sync(key_1)
    assert storage.object_exists_sync(key_2)


def test_7_omitted_image_fields_preserve_existing_image(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-7")
    upload_id, key = _create_published_media(db, storage, user_a)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(upload_id, key))

    client = _override_client(db, storage, user_a)
    resp = client.patch(f"/v1/wardrobe/items/{item_id}", json={"name": "Renamed Tee"})
    assert resp.status_code == 200
    assert resp.json()["imageRef"]["objectKey"] == key

    with db() as session:
        item = session.get(WardrobeItems, item_id)
        assert item.name == "Renamed Tee"
        assert item.image_ref["objectKey"] == key
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one_or_none()
        assert auth is not None and auth.status == "published"

    assert storage.object_exists_sync(key)


def test_8_failed_db_update_does_not_delete_old_image(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-8")
    old_upload, old_key = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_A)
    new_upload, new_key = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_B)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(old_upload, old_key))

    client = _override_client(db, storage, user_a)
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"category": "nonexistent_category", "imageRef": {"uploadId": str(new_upload)}},
    )
    assert resp.status_code == 422

    with db() as session:
        item = session.get(WardrobeItems, item_id)
        assert item.image_ref["objectKey"] == old_key
        old_auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == old_upload)
        ).scalar_one_or_none()
        assert old_auth is not None and old_auth.status == "published"

    assert storage.object_exists_sync(old_key)
    assert storage.object_exists_sync(new_key)


def test_9_and_10_storage_failure_leaves_retryable_state_and_consistent_auth(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-9")
    upload_id, key = _create_published_media(db, storage, user_a, expired=True)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(upload_id, key))

    storage.simulate_failure = StorageError("Simulated R2 outage", key=key)
    client = _override_client(db, storage, user_a)
    resp = client.delete(f"/v1/wardrobe/items/{item_id}")
    assert resp.status_code == 204

    # Item is deleted in DB; storage object still exists; auth is delete_pending (not published)
    with db() as session:
        assert session.get(WardrobeItems, item_id) is None
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one()
        assert auth.status == "delete_pending"
        assert auth.failure_reason == "STORAGE_DELETE_FAILED"

        # Prune must NOT remove delete_pending rows even when expired
        pruned = prune_expired_authorizations(session)
        assert pruned == 0
        assert (
            session.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.upload_id == upload_id
                )
            ).scalar_one_or_none()
            is not None
        )

    assert storage.object_exists_sync(key)

    # delete_pending authorization cannot be re-associated or fetched via /v1/media/url
    other_item = _create_wardrobe_item(db, user_a, name="Other", image_ref=None)
    assoc_resp = client.patch(
        f"/v1/wardrobe/items/{other_item}",
        json={"imageRef": {"uploadId": str(upload_id)}},
    )
    assert assoc_resp.status_code == 422
    assert assoc_resp.json()["error"]["code"] == "UNPUBLISHED_MEDIA"

    url_resp = client.get(f"/v1/media/url?upload_id={upload_id}")
    assert url_resp.status_code == 404

    # Recover storage and run durable retry cleanup
    storage.simulate_failure = None
    with db() as session:
        summary = asyncio.run(cleanup_pending_media_deletions(storage, session))
        assert summary.checked == 1
        assert summary.deleted == 1
        assert summary.failed == 0
        assert (
            session.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.upload_id == upload_id
                )
            ).scalar_one_or_none()
            is None
        )
    assert not storage.object_exists_sync(key)


def test_11_extraction_provenance_intact_on_image_replace(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-11")
    old_upload, old_key = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_A)
    new_upload, new_key = _create_published_media(db, storage, user_a, sha256=VALID_SHA256_B)
    run_id = str(uuid4())
    item_id = _create_wardrobe_item(
        db,
        user_a,
        image_ref=_make_image_ref(
            old_upload,
            old_key,
            sourceRunId=run_id,
            candidateId="cand_1",
            extractionConfidence=0.91,
        ),
    )

    client = _override_client(db, storage, user_a)
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"imageRef": {"uploadId": str(new_upload)}},
    )
    assert resp.status_code == 200
    body_ref = resp.json()["imageRef"]
    assert body_ref["uploadId"] == str(new_upload)
    assert body_ref["objectKey"] == new_key
    assert body_ref["sourceRunId"] == run_id
    assert body_ref["candidateId"] == "cand_1"
    assert body_ref["extractionConfidence"] == pytest.approx(0.91)

    with db() as session:
        item = session.get(WardrobeItems, item_id)
        assert item.image_ref["sourceRunId"] == run_id
        assert item.image_ref["candidateId"] == "cand_1"
        assert item.image_ref["extractionConfidence"] == pytest.approx(0.91)


def test_12_repeated_delete_and_cleanup_operations_are_idempotent(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_a = _create_user(db, "p52c-user-12")
    upload_id, key = _create_published_media(db, storage, user_a)
    item_id = _create_wardrobe_item(db, user_a, image_ref=_make_image_ref(upload_id, key))

    client = _override_client(db, storage, user_a)
    assert client.delete(f"/v1/wardrobe/items/{item_id}").status_code == 204
    assert client.delete(f"/v1/wardrobe/items/{item_id}").status_code == 404

    with db() as session:
        s1 = asyncio.run(cleanup_pending_media_deletions(storage, session))
        s2 = asyncio.run(cleanup_pending_media_deletions(storage, session))
        assert s1.checked == 0 and s1.deleted == 0
        assert s2.checked == 0 and s2.deleted == 0

    assert not storage.object_exists_sync(key)

