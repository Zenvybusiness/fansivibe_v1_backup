"""Regression tests for P5.2D: Extraction Save Atomicity & Media Authorization Consistency.

Uses disposable PostgreSQL (`db` fixture) and `FakeStorageAdapter`.
Asserts actual database rows (`WardrobeItems`, `MediaUploadAuthorization`, `AnalysisRuns`)
and fake storage object state.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import threading
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.application.garment_extraction import (
    SaveExtractedGarments,
    candidate_crop_object_key,
)
from app.application.media import (
    cleanup_pending_media_deletions,
    prune_expired_authorizations,
)
from app.application.wardrobe import AddWardrobeItem, DeleteWardrobeItem
from app.domain.ports.storage import StorageError
from app.infrastructure.db.models import (
    AnalysisRuns,
    Colors,
    Materials,
    MediaUploadAuthorization,
    Users,
    UserState,
    WardrobeCategories,
    WardrobeItems,
)
from app.infrastructure.db.repositories import (
    AnalysisRunRepositorySQL,
    LearningSignalRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

pytestmark = pytest.mark.usefixtures("db")


def _make_webp_bytes(color: tuple[int, int, int] = (30, 60, 120)) -> bytes:
    img = Image.new("RGB", (120, 160), color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def _seed_vocab(SessionLocal) -> None:
    with SessionLocal() as session:
        for code, label in (
            ("tops", "Tops"),
            ("bottoms", "Bottoms"),
            ("outerwear", "Outerwear"),
        ):
            if session.get(WardrobeCategories, code) is None:
                session.add(WardrobeCategories(code=code, label=label, sort_order=1, active=True))
        for code, label in (
            ("navy", "Navy"),
            ("charcoal", "Charcoal"),
            ("beige", "Beige"),
            ("white", "White"),
        ):
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


def _create_completed_garment_run(
    SessionLocal,
    storage: FakeStorageAdapter,
    user_id: UUID,
    *,
    candidates: list[dict] | None = None,
) -> UUID:
    run_id = uuid4()
    if candidates is None:
        candidates = [
            {
                "id": "cand_1",
                "category": "tops",
                "color": "navy",
                "material": "cotton",
                "confidence": 0.93,
                "crop_width": 120,
                "crop_height": 160,
            },
            {
                "id": "cand_2",
                "category": "bottoms",
                "color": "beige",
                "material": "cotton",
                "confidence": 0.88,
                "crop_width": 120,
                "crop_height": 160,
            },
        ]

    enriched_candidates = []
    for idx, c in enumerate(candidates):
        cand = dict(c)
        cid = str(cand["id"])
        ckey = candidate_crop_object_key(user_id, run_id, cid)
        webp = _make_webp_bytes((30 + idx * 40, 60, 120))
        storage.put_object_bytes(ckey, webp, content_type="image/webp")
        cand["crop_key"] = ckey
        cand["has_crop"] = True
        enriched_candidates.append(cand)

    with SessionLocal() as session:
        run = AnalysisRuns(
            id=run_id,
            user_id=user_id,
            run_type="garment",
            status="completed",
            engine_version="v1",
            knowledge_version="v1",
            completed_at=datetime.now(timezone.utc),
            result={
                "candidates": enriched_candidates,
                "partial_failures": [],
                "has_segmentation_mask": False,
            },
        )
        session.add(run)
        session.commit()
    return run_id


def _override_client(SessionLocal, storage: FakeStorageAdapter, user_id: UUID) -> TestClient:
    def _get_db_override():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_storage_adapter] = lambda: storage
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def test_1_wardrobe_item_and_provenance_commit_atomically(db, monkeypatch):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-1")
    run_id = _create_completed_garment_run(db, storage, user_id)

    create_calls: list[dict] = []
    update_calls: list[dict] = []
    orig_create = WardrobeItemRepositorySQL.create
    orig_update = WardrobeItemRepositorySQL.update

    def spy_create(self, **kwargs):
        create_calls.append(kwargs)
        return orig_create(self, **kwargs)

    def spy_update(self, **kwargs):
        update_calls.append(kwargs)
        return orig_update(self, **kwargs)

    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", spy_create)
    monkeypatch.setattr(WardrobeItemRepositorySQL, "update", spy_update)

    client = _override_client(db, storage, user_id)
    resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-atomic-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                    "material": "cotton",
                    "extractionConfidence": 0.93,
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["savedItems"]) == 1
    assert body["failedItems"] == []

    # Provenance was supplied on initial create; NO second WardrobeItems.update commit!
    assert len(create_calls) == 1
    assert len(update_calls) == 0
    created_ref = create_calls[0]["image_ref"]
    assert created_ref["sourceRunId"] == str(run_id)
    assert created_ref["candidateId"] == "cand_1"
    assert created_ref["extractionConfidence"] == pytest.approx(0.93)

    with db() as session:
        items = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        assert len(items) == 1
        item = items[0]
        assert item.image_ref["sourceRunId"] == str(run_id)
        assert item.image_ref["candidateId"] == "cand_1"
        assert item.image_ref["extractionConfidence"] == pytest.approx(0.93)

        auths = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.user_id == user_id)
        ).scalars().all()
        assert len(auths) == 1
        assert auths[0].status == "published"
        assert auths[0].canonical_key == item.image_ref["objectKey"]
        assert storage.object_exists_sync(auths[0].canonical_key)


def test_2_and_7_db_failure_rolls_back_item_and_auth_and_never_leaves_published_auth_for_deleted_obj(
    db, monkeypatch
):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-2")
    run_id = _create_completed_garment_run(db, storage, user_id)

    def fail_create(self, **kwargs):
        raise RuntimeError("Simulated DB item insert failure")

    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", fail_create)

    client = _override_client(db, storage, user_id)
    resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-db-fail-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["savedItems"] == []
    assert len(body["failedItems"]) == 1

    # DB has zero WardrobeItems AND zero MediaUploadAuthorization rows (both rolled back)
    with db() as session:
        assert (
            session.execute(
                select(WardrobeItems).where(WardrobeItems.user_id == user_id)
            ).scalars().all()
            == []
        )
        assert (
            session.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.user_id == user_id
                )
            ).scalars().all()
            == []
        )

    # Zero canonical wardrobe objects in storage; temporary extraction crop preserved for retry
    wardrobe_keys = asyncio.run(storage.list_keys(f"users/{user_id}/wardrobe/"))
    assert wardrobe_keys == []
    assert storage.object_exists_sync(candidate_crop_object_key(user_id, run_id, "cand_1"))


def test_3_and_4_storage_promotion_then_db_and_delete_failure_queues_durable_cleanup_and_retry_no_duplicates(
    db, monkeypatch
):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-3")
    run_id = _create_completed_garment_run(db, storage, user_id)

    orig_create = WardrobeItemRepositorySQL.create

    def fail_create(self, **kwargs):
        raise RuntimeError("Simulated DB commit failure")

    orig_delete = storage.delete_object

    async def fail_wardrobe_delete(key: str) -> None:
        if "/wardrobe/" in key:
            raise StorageError("Simulated R2 delete outage", key=key)
        await orig_delete(key)

    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", fail_create)
    monkeypatch.setattr(storage, "delete_object", fail_wardrobe_delete)

    client = _override_client(db, storage, user_id)
    resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-fail-queue-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["failedItems"]) == 1

    wardrobe_keys_before = asyncio.run(storage.list_keys(f"users/{user_id}/wardrobe/"))
    assert len(wardrobe_keys_before) == 1
    promoted_key = wardrobe_keys_before[0]

    # Durable delete_pending record created; NOT published!
    with db() as session:
        assert (
            session.execute(
                select(WardrobeItems).where(WardrobeItems.user_id == user_id)
            ).scalars().all()
            == []
        )
        auths = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.user_id == user_id)
        ).scalars().all()
        assert len(auths) == 1
        assert auths[0].status == "delete_pending"
        assert auths[0].failure_reason == "STORAGE_DELETE_FAILED"
        assert auths[0].canonical_key == promoted_key
        prior_upload_id = auths[0].upload_id

    # Recover DB and storage, then retry save: must reuse upload_id/key and NOT duplicate!
    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", orig_create)
    monkeypatch.setattr(storage, "delete_object", orig_delete)

    retry_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-fail-queue-2"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert retry_resp.status_code == 200
    retry_body = retry_resp.json()
    assert len(retry_body["savedItems"]) == 1
    assert retry_body["failedItems"] == []

    wardrobe_keys_after = asyncio.run(storage.list_keys(f"users/{user_id}/wardrobe/"))
    assert wardrobe_keys_after == [promoted_key]

    with db() as session:
        items = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        assert len(items) == 1
        assert items[0].image_ref["uploadId"] == str(prior_upload_id)
        assert items[0].image_ref["objectKey"] == promoted_key
        assert items[0].image_ref["sourceRunId"] == str(run_id)
        assert items[0].image_ref["candidateId"] == "cand_1"

        auths = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.user_id == user_id)
        ).scalars().all()
        assert len(auths) == 1
        assert auths[0].status == "published"


def test_5_concurrent_candidate_save_produces_one_wardrobe_item(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-5")
    run_id = _create_completed_garment_run(db, storage, user_id)

    payload = [
        {
            "candidateId": "cand_1",
            "name": "Concurrent Tee",
            "category": "tops",
            "color": "navy",
            "material": "cotton",
        }
    ]

    def _run_save(idemp_key: str) -> dict:
        with db() as session:
            uc = SaveExtractedGarments(
                runs=AnalysisRunRepositorySQL(session),
                wardrobe=WardrobeItemRepositorySQL(session),
                storage=storage,
                signals=LearningSignalRepositorySQL(session),
                db=session,
            )
            return asyncio.run(
                uc.execute(
                    user_id=user_id,
                    run_id=run_id,
                    items=payload,
                    idempotency_key=idemp_key,
                )
            )

    async def _concurrent():
        res1, res2 = await asyncio.gather(
            asyncio.to_thread(_run_save, "p52d-conc-key-1"),
            asyncio.to_thread(_run_save, "p52d-conc-key-2"),
        )
        return res1, res2

    r1, r2 = asyncio.run(_concurrent())
    assert len(r1["saved_records"]) == 1
    assert len(r2["saved_records"]) == 1
    assert r1["saved_records"][0].id == r2["saved_records"][0].id

    with db() as session:
        items = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        assert len(items) == 1
        auths = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.user_id == user_id)
        ).scalars().all()
        assert len(auths) == 1


def test_6_partial_batch_retry_preserves_successful_candidates(db, monkeypatch):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-6")
    run_id = _create_completed_garment_run(db, storage, user_id)

    orig_create = WardrobeItemRepositorySQL.create

    def fail_cand_1_only(self, **kwargs):
        if kwargs.get("name") == "Item One":
            raise RuntimeError("Transient failure on cand_1")
        return orig_create(self, **kwargs)

    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", fail_cand_1_only)

    client = _override_client(db, storage, user_id)
    resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-partial-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Item One",
                    "category": "tops",
                    "color": "navy",
                },
                {
                    "candidateId": "cand_2",
                    "name": "Item Two",
                    "category": "bottoms",
                    "color": "beige",
                },
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["savedItems"]) == 1
    assert body["savedItems"][0]["candidateId"] == "cand_2"
    assert len(body["failedItems"]) == 1
    assert body["failedItems"][0]["candidateId"] == "cand_1"

    # Recover and retry full batch: cand_2 is preserved without duplicate, cand_1 is saved
    monkeypatch.setattr(WardrobeItemRepositorySQL, "create", orig_create)
    retry_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-partial-2"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Item One",
                    "category": "tops",
                    "color": "navy",
                },
                {
                    "candidateId": "cand_2",
                    "name": "Item Two",
                    "category": "bottoms",
                    "color": "beige",
                },
            ]
        },
    )
    assert retry_resp.status_code == 200
    retry_body = retry_resp.json()
    assert len(retry_body["savedItems"]) == 2
    assert retry_body["failedItems"] == []

    with db() as session:
        items = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        assert len(items) == 2
        cids = {it.image_ref["candidateId"] for it in items}
        assert cids == {"cand_1", "cand_2"}


def test_8_existing_p52c_delete_pending_retry_remains_intact(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-8")
    run_id = _create_completed_garment_run(db, storage, user_id)

    client = _override_client(db, storage, user_id)
    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-p52c-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Navy Crewneck",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    saved = save_resp.json()["savedItems"][0]
    item_id = UUID(saved["id"])
    upload_id = UUID(saved["imageRef"]["uploadId"])
    canonical_key = saved["imageRef"]["objectKey"]

    storage.simulate_failure = StorageError("Simulated R2 outage", key=canonical_key)
    del_resp = client.delete(f"/v1/wardrobe/items/{item_id}")
    assert del_resp.status_code == 204

    with db() as session:
        assert session.get(WardrobeItems, item_id) is None
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one()
        assert auth.status == "delete_pending"
        assert auth.failure_reason == "STORAGE_DELETE_FAILED"
        assert prune_expired_authorizations(session, now=datetime.now(timezone.utc) + timedelta(days=2)) == 0

    assert client.get(f"/v1/media/url?upload_id={upload_id}").status_code == 404

    storage.simulate_failure = None
    with db() as session:
        summary = asyncio.run(cleanup_pending_media_deletions(storage, session))
        assert summary.deleted == 1
        assert (
            session.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.upload_id == upload_id
                )
            ).scalar_one_or_none()
            is None
        )
    assert not storage.object_exists_sync(canonical_key)


def test_9_extraction_provenance_remains_correct_after_save_and_metadata_update(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-9")
    run_id = _create_completed_garment_run(db, storage, user_id)

    client = _override_client(db, storage, user_id)
    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-prov-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Initial Tee",
                    "category": "tops",
                    "color": "navy",
                    "extractionConfidence": 0.91,
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    item_id = save_resp.json()["savedItems"][0]["id"]

    patch_resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"name": "Updated Tee", "color": "charcoal", "isFavorite": True},
    )
    assert patch_resp.status_code == 200
    patched_ref = patch_resp.json()["imageRef"]
    assert patched_ref["sourceRunId"] == str(run_id)
    assert patched_ref["candidateId"] == "cand_1"
    assert patched_ref["extractionConfidence"] == pytest.approx(0.91)

    get_resp = client.get(f"/v1/wardrobe/items/{item_id}")
    assert get_resp.status_code == 200
    get_ref = get_resp.json()["imageRef"]
    assert get_ref["sourceRunId"] == str(run_id)
    assert get_ref["candidateId"] == "cand_1"
    assert get_ref["extractionConfidence"] == pytest.approx(0.91)


def test_10_attach_versus_delete_concurrency_cannot_remove_newly_referenced_media(db):
    _seed_vocab(db)
    storage = FakeStorageAdapter()
    user_id = _create_user(db, "p52d-user-10")
    run_id = _create_completed_garment_run(db, storage, user_id)

    client = _override_client(db, storage, user_id)
    save_resp = client.post(
        f"/v1/analysis/garment/runs/{run_id}/save",
        headers={"Idempotency-Key": "p52d-race-1"},
        json={
            "items": [
                {
                    "candidateId": "cand_1",
                    "name": "Original Item",
                    "category": "tops",
                    "color": "navy",
                }
            ]
        },
    )
    assert save_resp.status_code == 200
    saved = save_resp.json()["savedItems"][0]
    original_item_id = UUID(saved["id"])
    upload_id = UUID(saved["imageRef"]["uploadId"])
    canonical_key = saved["imageRef"]["objectKey"]

    barrier = threading.Barrier(2, timeout=10)
    attach_outcome: dict[str, object] = {}
    delete_outcome: dict[str, object] = {}

    def _delete_worker() -> None:
        with db() as session:
            barrier.wait()
            uc = DeleteWardrobeItem(
                wardrobe=WardrobeItemRepositorySQL(session),
                db=session,
            )
            try:
                asyncio.run(uc.execute(user_id=user_id, item_id=original_item_id, storage=storage))
                delete_outcome["ok"] = True
            except Exception as exc:
                delete_outcome["error"] = exc

    def _attach_worker() -> None:
        with db() as session:
            barrier.wait()
            uc = AddWardrobeItem(
                wardrobe=WardrobeItemRepositorySQL(session),
                db=session,
            )
            try:
                created = uc(
                    user_id=user_id,
                    name="Newly Attached Item",
                    category="tops",
                    color="navy",
                    material="cotton",
                    isFavorite=False,
                    image_ref={"uploadId": str(upload_id)},
                )
                attach_outcome["item_id"] = created.id
            except Exception as exc:
                attach_outcome["error"] = exc

    t_del = threading.Thread(target=_delete_worker)
    t_att = threading.Thread(target=_attach_worker)
    t_del.start()
    t_att.start()
    t_del.join(timeout=15)
    t_att.join(timeout=15)

    assert "ok" in delete_outcome, f"Delete worker failed unexpectedly: {delete_outcome}"

    with db() as session:
        live_items = session.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        auth = session.execute(
            select(MediaUploadAuthorization).where(MediaUploadAuthorization.upload_id == upload_id)
        ).scalar_one_or_none()

        if "item_id" in attach_outcome:
            # Attach succeeded: media MUST NOT have been deleted and auth MUST remain published!
            assert len(live_items) == 1
            assert live_items[0].id == attach_outcome["item_id"]
            assert auth is not None and auth.status == "published"
            assert storage.object_exists_sync(canonical_key)
        else:
            # Delete won first and fenced the media as delete_pending: attach MUST have been rejected!
            assert len(live_items) == 0
            assert "error" in attach_outcome
            assert auth is None
            assert not storage.object_exists_sync(canonical_key)

