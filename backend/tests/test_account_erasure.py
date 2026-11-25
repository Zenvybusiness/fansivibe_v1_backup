"""Erasure tests — O-6 `DELETE /v1/users/me` (AUTH_API §5.6, TRX-8).

DB-backed API tests run when PostgreSQL is reachable, else skip
(see `tests/conftest.py`). Use-case unit tests run everywhere.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_storage_adapter
from app.application.auth import EraseAccount
from app.infrastructure.db.models import (
    LearningSignals,
    MediaUploadAuthorization,
    TryOnJobModel,
    UserSession,
    UserState,
    Users,
    WardrobeCategories,
    WardrobeItems,
)
from tests.conftest import make_session
from tests.fakes.fake_storage import FakeStorageAdapter

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)


def _register(email, password="Passw0rd1"):
    return client.post(
        "/v1/auth/register",
        json={"email": email, "password": password},
        headers={"Idempotency-Key": f"reg-{uuid.uuid4()}"},
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _rows(model, user_id):
    Session = make_session()
    with Session() as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(model)
                .where(model.user_id == user_id)
            ).scalar_one()
        )


def _seed_dependent(user_id):
    Session = make_session()
    with Session() as session:
        session.add(
            WardrobeItems(
                user_id=user_id,
                name="Doomed Top",
                category_id="tops",
                color_id="charcoal",
            )
        )
        session.add(
            LearningSignals(
                user_id=user_id,
                signal_type="item_added",
                label="added",
                context={},
            )
        )
        session.commit()


# --- API: authorized self-erasure -------------------------------------------


def test_delete_me_erases_account_and_dependents(db):
    email = f"erase-{uuid.uuid4()}@example.com"
    token = _register(email).json()["accessToken"]
    me = client.get("/v1/users/me", headers=_auth(token)).json()
    assert me["memorySummary"]["savedLooksCount"] == 0

    Session = make_session()
    with Session() as session:
        user_id = session.execute(
            select(Users.id).where(Users.auth_subject == email)
        ).scalar_one()
    _seed_dependent(user_id)
    assert _rows(WardrobeItems, user_id) == 1

    resp = client.delete("/v1/users/me", headers=_auth(token))
    assert resp.status_code == 204, resp.text

    with Session() as session:
        assert (
            session.execute(select(Users).where(Users.id == user_id)).scalar_one_or_none()
            is None
        )
        assert (
            session.execute(
                select(UserState).where(UserState.user_id == user_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            session.execute(
                select(UserSession).where(UserSession.user_id == user_id)
            ).scalar_one_or_none()
            is None
        )
    assert _rows(WardrobeItems, user_id) == 0
    assert _rows(LearningSignals, user_id) == 0
    # System-owned knowledge survives erasure (TRX-8).
    with Session() as session:
        assert (
            session.execute(
                select(func.count()).select_from(WardrobeCategories)
            ).scalar_one()
            > 0
        )


def test_delete_me_requires_auth(db):
    resp = client.delete("/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_delete_me_retry_with_dead_token_is_401_not_oracle(db):
    email = f"erase-{uuid.uuid4()}@example.com"
    token = _register(email).json()["accessToken"]
    assert client.delete("/v1/users/me", headers=_auth(token)).status_code == 204
    # Session died with the account: retry is 401 like any dead token —
    # never another user's data, never a 404 oracle on someone else.
    retry = client.delete("/v1/users/me", headers=_auth(token))
    assert retry.status_code == 401


def test_delete_me_cross_user_isolation(db):
    token_a = _register(f"a-{uuid.uuid4()}@example.com").json()["accessToken"]
    token_b = _register(f"b-{uuid.uuid4()}@example.com").json()["accessToken"]
    Session = make_session()
    with Session() as session:
        id_b = session.execute(
            select(Users.id).where(Users.auth_subject.like("b-%"))
        ).scalar_one()
    _seed_dependent(id_b)
    assert client.delete("/v1/users/me", headers=_auth(token_a)).status_code == 204
    assert _rows(WardrobeItems, id_b) == 1
    assert (
        client.get("/v1/users/me", headers=_auth(token_b)).status_code == 200
    )


def test_delete_me_erases_r2_wardrobe_staging_person_and_result_objects(db, monkeypatch):
    monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "mock")
    from app.config.settings import clear_settings_cache

    clear_settings_cache()
    storage = FakeStorageAdapter()
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    token_a = _register(f"media-a-{uuid.uuid4()}@example.com").json()["accessToken"]
    token_b = _register(f"media-b-{uuid.uuid4()}@example.com").json()["accessToken"]

    Session = make_session()
    with Session() as session:
        user_a = session.execute(
            select(Users.id).where(Users.auth_subject.like("media-a-%"))
        ).scalar_one()
        user_b = session.execute(
            select(Users.id).where(Users.auth_subject.like("media-b-%"))
        ).scalar_one()

        upload_a = uuid.uuid4()
        staging_key_a = f"staging/users/{user_a}/wardrobe/{upload_a}.webp"
        canonical_key_a = f"users/{user_a}/wardrobe/{upload_a}/attempts/1.webp"
        orphan_key_a = f"users/{user_a}/tryon/orphan-job/person.jpg"
        person_key_a = f"users/{user_a}/tryon/job-1/person.jpg"
        result_key_a = f"users/{user_a}/tryon/job-1/result.png"
        keep_key_b = f"users/{user_b}/wardrobe/item-b/canonical.webp"

        for k in (staging_key_a, canonical_key_a, orphan_key_a, person_key_a, result_key_a, keep_key_b):
            storage.put_object_bytes(k, b"img-bytes", content_type="image/webp")

        session.add(
            MediaUploadAuthorization(
                user_id=user_a,
                idempotency_key="u-a-1",
                upload_id=upload_a,
                key_version="kver_dev",
                request_fingerprint="fp-1",
                staging_key=staging_key_a,
                canonical_key=canonical_key_a,
                content_type="image/webp",
                size_bytes=9,
                expires_at=session.execute(select(func.now())).scalar_one(),
                status="published",
            )
        )
        session.add(
            WardrobeItems(
                user_id=user_a,
                name="User A Shirt",
                category_id="tops",
                color_id="black",
                image_ref={"key": canonical_key_a, "mediaType": "image/webp"},
            )
        )
        session.add(
            TryOnJobModel(
                user_id=user_a,
                outfit_source="wardrobe",
                garment_ids=[],
                provider="mock",
                status="completed",
                consent_version="tryon-v1",
                person_media_ref={"key": person_key_a},
                result_media_ref={"key": result_key_a},
            )
        )
        session.add(
            WardrobeItems(
                user_id=user_b,
                name="User B Shirt",
                category_id="tops",
                color_id="navy",
                image_ref={"key": keep_key_b, "mediaType": "image/webp"},
            )
        )
        session.commit()

    resp = client.delete("/v1/users/me", headers=_auth(token_a))
    assert resp.status_code == 204

    assert not storage.object_exists_sync(staging_key_a)
    assert not storage.object_exists_sync(canonical_key_a)
    assert not storage.object_exists_sync(orphan_key_a)
    assert not storage.object_exists_sync(person_key_a)
    assert not storage.object_exists_sync(result_key_a)
    assert storage.object_exists_sync(keep_key_b)
    assert _rows(TryOnJobModel, user_a) == 0
    assert _rows(MediaUploadAuthorization, user_a) == 0
    assert _rows(WardrobeItems, user_b) == 1
    assert client.get("/v1/users/me", headers=_auth(token_b)).status_code == 200
    clear_settings_cache()


def test_delete_me_storage_failure_preserves_account_for_idempotent_retry(db, monkeypatch):
    monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "mock")
    from app.config.settings import clear_settings_cache

    clear_settings_cache()
    storage = FakeStorageAdapter()
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    token = _register(f"retry-erase-{uuid.uuid4()}@example.com").json()["accessToken"]
    Session = make_session()
    with Session() as session:
        user_id = session.execute(
            select(Users.id).where(Users.auth_subject.like("retry-erase-%"))
        ).scalar_one()
        key = f"users/{user_id}/tryon/job-r/person.jpg"
        storage.put_object_bytes(key, b"person-bytes", content_type="image/jpeg")
        session.add(
            TryOnJobModel(
                user_id=user_id,
                outfit_source="wardrobe",
                garment_ids=[],
                provider="mock",
                status="completed",
                consent_version="tryon-v1",
                person_media_ref={"key": key},
            )
        )
        session.commit()

    # Simulate transient R2 deletion failure
    storage.simulate_failure = RuntimeError("R2 unavailable")
    fail_resp = client.delete("/v1/users/me", headers=_auth(token))
    assert fail_resp.status_code == 503
    assert fail_resp.json()["error"]["code"] == "ERASURE_STORAGE_FAILURE"

    # Account and session remain intact so user can retry safely
    assert client.get("/v1/users/me", headers=_auth(token)).status_code == 200
    assert storage.object_exists_sync(key)

    # Recover R2 and retry -> succeeds idempotently
    storage.simulate_failure = None
    ok_resp = client.delete("/v1/users/me", headers=_auth(token))
    assert ok_resp.status_code == 204
    assert not storage.object_exists_sync(key)
    assert client.delete("/v1/users/me", headers=_auth(token)).status_code == 401
    clear_settings_cache()


def test_erase_account_genlook_hook_failure_is_retryable_and_mock_makes_zero_calls():
    class _StubAuthRepo:
        def __init__(self, user_id: uuid.UUID) -> None:
            self.user_id = user_id
            self.deleted = False
            self.committed = False
            self.rolled_back = False

        def account_exists(self, *, user_id: uuid.UUID) -> bool:
            return not self.deleted and user_id == self.user_id

        def collect_user_media_keys(self, *, user_id: uuid.UUID):
            return [f"users/{user_id}/tryon/j1/person.jpg"], [uuid.uuid4()]

        def delete_account(self, *, user_id: uuid.UUID) -> bool:
            if self.deleted:
                return False
            self.deleted = True
            return True

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

    uid = uuid.uuid4()
    storage = FakeStorageAdapter()
    storage.put_object_bytes(f"users/{uid}/tryon/j1/person.jpg", b"p", content_type="image/jpeg")
    repo = _StubAuthRepo(uid)

    calls: list[uuid.UUID] = []

    def _failing_genlook(target_uid: uuid.UUID) -> bool:
        calls.append(target_uid)
        raise RuntimeError("Genlook transient outage")

    with pytest.raises(Exception) as exc_info:
        asyncio.run(EraseAccount(auth=repo, storage=storage, genlook_eraser=_failing_genlook)(user_id=uid))
    assert getattr(exc_info.value, "status_code", None) == 503
    assert repo.rolled_back
    assert not repo.deleted

    # Retry succeeds idempotently even though storage object was already purged
    calls2: list[uuid.UUID] = []
    res = asyncio.run(
        EraseAccount(
            auth=repo,
            storage=storage,
            genlook_eraser=lambda u: (calls2.append(u), True)[1],
        )(user_id=uid)
    )
    assert repo.deleted and repo.committed
    assert res["genlook_erased"] is True
    assert calls == [uid] and calls2 == [uid]
