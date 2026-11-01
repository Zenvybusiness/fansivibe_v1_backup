"""Comprehensive automated test suite for Stage 2 P0-4 Phase 4:
Secure Wardrobe Media Association, Cloud Retrieval & Flutter Integration.

Covers all 18 security and architectural requirements from Gate 7:
1. User A associates User A's published media (201, presigned GET generated).
2. User A attempts to associate User B's published media (non-revealing 404).
3. User A attempts to associate an unpublished upload (409 Conflict).
4. User A attempts to associate a staging key (422 Unprocessable Entity).
5. User A submits an arbitrary R2 key (422 Unprocessable Entity).
6. User A submits a fabricated canonical reference (rejected / overwritten with trusted DB values).
7. User A attempts to modify an item using another user's media (non-revealing 404).
8. User A attempts to replace an image with an invalid reference (fails, preserves existing).
9. Update without image field preserves the existing image.
10. Explicit image removal (clearImageRef) behaves correctly.
11. Wardrobe item can be created without an image.
12. Association failure does not partially modify the wardrobe (transactional consistency).
13. Published replay remains valid.
14. Temporary GET URL is generated only for authorized published media via GET /v1/media/url.
15. Presigned GET URLs are never stored in PostgreSQL (PR-8 verification).
16. Expired or corrupt media references fail safely.
17. Staging objects remain inaccessible through GET /v1/media/url.
18. Existing legacy canonical records (pre-attempt-id) remain retrievable and associable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

from app.api.deps import get_current_user_id, get_db, get_storage_adapter
from app.infrastructure.db.models import (
    Base,
    Colors,
    Materials,
    MediaUploadAuthorization,
    Users,
    WardrobeCategories,
    WardrobeItems,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sqlite_engine():
    """Isolated in-memory SQLite engine with all required tables."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_custom_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "char_length", 1, lambda s: len(s) if s is not None else 0
        )
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

    # Create required tables in in-memory SQLite
    Users.__table__.create(engine)
    WardrobeCategories.__table__.create(engine)
    Colors.__table__.create(engine)
    Materials.__table__.create(engine)
    MediaUploadAuthorization.__table__.create(engine)
    WardrobeItems.__table__.create(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_db(sqlite_engine):
    """Yield a transactional session connected to the in-memory SQLite engine."""
    SessionLocal = sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    # Seed vocabulary tables
    for code, label in (
        ("tops", "Tops"),
        ("bottoms", "Bottoms"),
        ("outerwear", "Outerwear"),
        ("footwear", "Footwear"),
        ("accessories", "Accessories"),
    ):
        session.add(WardrobeCategories(code=code, label=label, sort_order=1, active=True))

    for code, label in (
        ("charcoal", "Charcoal"),
        ("white", "White"),
        ("navy", "Navy"),
        ("black", "Black"),
    ):
        session.add(Colors(code=code, label=label, sort_order=1, active=True))

    for code, label in (
        ("wool", "Wool"),
        ("cotton", "Cotton"),
        ("silk", "Silk"),
    ):
        session.add(Materials(code=code, label=label, sort_order=1, active=True))

    session.commit()
    yield session
    session.close()


@pytest.fixture
def fake_storage():
    """In-memory fake object storage adapter."""
    return FakeStorageAdapter()


@pytest.fixture
def test_users(sqlite_db):
    """Seed User A and User B."""
    user_a = Users(
        id=uuid4(),
        auth_provider="test",
        auth_subject="user-a",
        display_name="User A",
    )
    user_b = Users(
        id=uuid4(),
        auth_provider="test",
        auth_subject="user-b",
        display_name="User B",
    )
    sqlite_db.add_all([user_a, user_b])
    sqlite_db.commit()
    return {"user_a": user_a.id, "user_b": user_b.id}


def create_published_upload(
    db: Session,
    user_id: UUID,
    *,
    upload_id: UUID | None = None,
    canonical_key: str | None = None,
    status: str = "published",
    width: int = 800,
    height: int = 1200,
    sha256: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
) -> MediaUploadAuthorization:
    uid = upload_id or uuid4()
    attempt_id = uuid4()
    c_key = canonical_key or f"users/{user_id}/wardrobe/{uid}/{attempt_id}.webp"
    now = datetime.now(timezone.utc)
    record = MediaUploadAuthorization(
        upload_id=uid,
        user_id=user_id,
        idempotency_key=f"idemp_{uid}",
        key_version="v1",
        request_fingerprint="fingerprint",
        staging_key=f"staging/users/{user_id}/wardrobe/{uid}/source.webp",
        content_type="image/webp",
        size_bytes=1024,
        status=status,
        canonical_key=c_key if status == "published" else None,
        canonical_sha256=sha256 if status == "published" else None,
        canonical_size_bytes=1024 if status == "published" else None,
        canonical_width=width if status == "published" else None,
        canonical_height=height if status == "published" else None,
        completed_at=now if status == "published" else None,
        expires_at=now + timedelta(hours=24),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# -----------------------------------------------------------------------------
# Test Cases
# -----------------------------------------------------------------------------

def test_user_a_associates_published_media(sqlite_db, fake_storage, test_users):
    """1. User A associates User A's published media (201, presigned GET generated)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Classic Wool Coat",
                "category": "outerwear",
                "color": "charcoal",
                "material": "wool",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": upload.canonical_key,
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Classic Wool Coat"
        assert data["imageUrl"] is not None
        assert "action=get" in data["imageUrl"]
        assert data["imageRef"] is not None
        assert data["imageRef"]["uploadId"] == str(upload.upload_id)
        assert data["imageRef"]["objectKey"] == upload.canonical_key
        assert data["imageRef"]["downloadUrl"] is not None
        assert "action=get" in data["imageRef"]["downloadUrl"]
        assert data["imageRef"]["width"] == 800
        assert data["imageRef"]["height"] == 1200
    finally:
        app.dependency_overrides.clear()


def test_user_a_associates_user_b_published_media_rejected(sqlite_db, fake_storage, test_users):
    """2. User A attempts to associate User B's published media (non-revealing 404)."""
    user_a_id = test_users["user_a"]
    user_b_id = test_users["user_b"]
    upload_b = create_published_upload(sqlite_db, user_b_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Sneaky Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload_b.upload_id),
                    "objectKey": upload_b.canonical_key,
                },
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] in ("NOT_FOUND", "MEDIA_NOT_FOUND")
    finally:
        app.dependency_overrides.clear()


def test_user_a_associates_unpublished_media_rejected(sqlite_db, fake_storage, test_users):
    """3. User A attempts to associate an unpublished upload (409 Conflict)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id, status="authorized")

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Pending Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": f"staging/users/{user_a_id}/wardrobe/{upload.upload_id}/source.webp",
                },
            },
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] in ("MEDIA_NOT_PUBLISHED", "UNPUBLISHED_MEDIA")
    finally:
        app.dependency_overrides.clear()


def test_user_a_associates_staging_key_rejected(sqlite_db, fake_storage, test_users):
    """4. User A attempts to associate a staging key (422 Unprocessable Entity)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Staging Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": f"staging/users/{user_a_id}/wardrobe/{upload.upload_id}/source.webp",
                },
            },
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_user_a_submits_arbitrary_r2_key_rejected(sqlite_db, fake_storage, test_users):
    """5. User A submits an arbitrary R2 key (422 Unprocessable Entity)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Hacked Key Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": "buckets/other_bucket/malicious.jpg",
                },
            },
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_user_a_submits_fabricated_canonical_ref_rejected(sqlite_db, fake_storage, test_users):
    """6. User A submits a fabricated canonical reference (rejected / mismatch)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)
    fake_key = f"users/{user_a_id}/wardrobe/{upload.upload_id}/{uuid4()}.webp"

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Fabricated Attempt Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": fake_key,
                },
            },
        )
        # Key mismatch between client payload and trusted DB record is rejected
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_user_a_modifies_item_with_foreign_media_rejected(sqlite_db, fake_storage, test_users):
    """7. User A attempts to modify an item using another user's media (non-revealing 404)."""
    user_a_id = test_users["user_a"]
    user_b_id = test_users["user_b"]
    upload_b = create_published_upload(sqlite_db, user_b_id)

    # Seed an existing item for user A
    item = WardrobeItems(
        user_id=user_a_id,
        name="Existing Top",
        category_id="tops",
        color_id="white",
    )
    sqlite_db.add(item)
    sqlite_db.commit()
    sqlite_db.refresh(item)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.patch(
            f"/v1/wardrobe/items/{item.id}",
            json={
                "imageRef": {
                    "uploadId": str(upload_b.upload_id),
                    "objectKey": upload_b.canonical_key,
                },
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] in ("NOT_FOUND", "MEDIA_NOT_FOUND")
    finally:
        app.dependency_overrides.clear()


def test_user_a_replaces_image_with_invalid_ref_fails_and_preserves(sqlite_db, fake_storage, test_users):
    """8. User A attempts to replace an image with an invalid reference (fails, preserves existing)."""
    user_a_id = test_users["user_a"]
    upload_1 = create_published_upload(sqlite_db, user_a_id)

    # Seed item with valid image_ref
    original_ref = {
        "upload_id": str(upload_1.upload_id),
        "object_key": upload_1.canonical_key,
        "media_type": "image/webp",
        "sha256": upload_1.canonical_sha256,
    }
    item = WardrobeItems(
        user_id=user_a_id,
        name="Tee",
        category_id="tops",
        color_id="black",
        image_ref=original_ref,
    )
    sqlite_db.add(item)
    sqlite_db.commit()
    sqlite_db.refresh(item)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        # Submit invalid nonexistent uploadId
        resp = client.patch(
            f"/v1/wardrobe/items/{item.id}",
            json={
                "imageRef": {
                    "uploadId": str(uuid4()),
                    "objectKey": f"users/{user_a_id}/wardrobe/nonexistent/key.webp",
                },
            },
        )
        assert resp.status_code == 404

        # Verify DB item still has original image_ref
        sqlite_db.refresh(item)
        assert item.image_ref["upload_id"] == str(upload_1.upload_id)
        assert item.image_ref["object_key"] == upload_1.canonical_key
    finally:
        app.dependency_overrides.clear()


def test_update_without_image_field_preserves_existing_image(sqlite_db, fake_storage, test_users):
    """9. Update without image field preserves the existing image."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    original_ref = {
        "upload_id": str(upload.upload_id),
        "object_key": upload.canonical_key,
        "media_type": "image/webp",
        "sha256": upload.canonical_sha256,
    }
    item = WardrobeItems(
        user_id=user_a_id,
        name="Old Name",
        category_id="tops",
        color_id="black",
        image_ref=original_ref,
    )
    sqlite_db.add(item)
    sqlite_db.commit()

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.patch(
            f"/v1/wardrobe/items/{item.id}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["imageUrl"] is not None
        assert (data["imageRef"].get("uploadId") or data["imageRef"].get("upload_id")) == str(upload.upload_id)

        sqlite_db.refresh(item)
        assert item.name == "New Name"
        assert item.image_ref["upload_id"] == str(upload.upload_id)
    finally:
        app.dependency_overrides.clear()


def test_explicit_image_removal(sqlite_db, fake_storage, test_users):
    """10. Explicit image removal (clearImageRef) behaves correctly."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    original_ref = {
        "upload_id": str(upload.upload_id),
        "object_key": upload.canonical_key,
        "media_type": "image/webp",
        "sha256": upload.canonical_sha256,
    }
    item = WardrobeItems(
        user_id=user_a_id,
        name="Shirt",
        category_id="tops",
        color_id="navy",
        image_ref=original_ref,
    )
    sqlite_db.add(item)
    sqlite_db.commit()

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.patch(
            f"/v1/wardrobe/items/{item.id}",
            json={"clearImageRef": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imageUrl"] is None
        assert data["imageRef"] is None

        sqlite_db.refresh(item)
        assert item.image_ref is None
    finally:
        app.dependency_overrides.clear()


def test_wardrobe_item_can_be_created_without_image(sqlite_db, fake_storage, test_users):
    """11. A wardrobe item can be created without an image."""
    user_a_id = test_users["user_a"]

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Imageless Chinos",
                "category": "bottoms",
                "color": "navy",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Imageless Chinos"
        assert data["imageUrl"] is None
        assert data["imageRef"] is None
    finally:
        app.dependency_overrides.clear()


def test_association_failure_is_transactional(sqlite_db, fake_storage, test_users):
    """12. Association failure does not partially modify the wardrobe (transactional consistency)."""
    user_a_id = test_users["user_a"]

    item = WardrobeItems(
        user_id=user_a_id,
        name="Original Shirt Name",
        category_id="tops",
        color_id="white",
        material_id="cotton",
    )
    sqlite_db.add(item)
    sqlite_db.commit()

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        # Attempt PATCH with invalid image reference AND a name change
        resp = client.patch(
            f"/v1/wardrobe/items/{item.id}",
            json={
                "name": "Altered Name",
                "imageRef": {
                    "uploadId": str(uuid4()),
                    "objectKey": "invalid_key",
                },
            },
        )
        assert resp.status_code in (404, 422)

        # Database record must NOT have been modified to "Altered Name"
        sqlite_db.refresh(item)
        assert item.name == "Original Shirt Name"
    finally:
        app.dependency_overrides.clear()


def test_published_replay_remains_valid(sqlite_db, fake_storage, test_users):
    """13. Published replay remains valid (multiple associations to same media succeed)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        ref_payload = {
            "uploadId": str(upload.upload_id),
            "objectKey": upload.canonical_key,
        }
        resp1 = client.post(
            "/v1/wardrobe/items",
            json={"name": "Item 1", "category": "tops", "color": "white", "imageRef": ref_payload},
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/v1/wardrobe/items",
            json={"name": "Item 2", "category": "bottoms", "color": "navy", "imageRef": ref_payload},
        )
        assert resp2.status_code == 201
        assert resp1.json()["imageRef"]["uploadId"] == resp2.json()["imageRef"]["uploadId"]
    finally:
        app.dependency_overrides.clear()


def test_temporary_get_url_endpoint(sqlite_db, fake_storage, test_users):
    """14. Temporary GET URL is generated only for authorized published media via GET /v1/media/url."""
    user_a_id = test_users["user_a"]
    user_b_id = test_users["user_b"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage

    try:
        # User A requests their own upload URL -> 200
        app.dependency_overrides[get_current_user_id] = lambda: user_a_id
        client_a = TestClient(app)
        resp_a = client_a.get(
            "/v1/media/url",
            params={"uploadId": str(upload.upload_id), "objectKey": upload.canonical_key},
        )
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert data_a["uploadId"] == str(upload.upload_id)
        assert "action=get" in data_a["downloadUrl"]
        assert data_a["expiresInSeconds"] == 900

        # User B requests User A's upload URL -> non-revealing 404
        app.dependency_overrides[get_current_user_id] = lambda: user_b_id
        client_b = TestClient(app)
        resp_b = client_b.get(
            "/v1/media/url",
            params={"uploadId": str(upload.upload_id), "objectKey": upload.canonical_key},
        )
        assert resp_b.status_code == 404
        assert resp_b.json()["error"]["code"] in ("NOT_FOUND", "MEDIA_NOT_FOUND")
    finally:
        app.dependency_overrides.clear()


def test_presigned_urls_never_stored_in_postgres(sqlite_db, fake_storage, test_users):
    """15. Presigned GET URLs are never stored in PostgreSQL (PR-8 verification)."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Audit Coat",
                "category": "outerwear",
                "color": "charcoal",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": upload.canonical_key,
                },
            },
        )
        assert resp.status_code == 201
        item_id = resp.json()["id"]

        # Inspect raw database row directly
        raw_item = sqlite_db.execute(
            select(WardrobeItems).where(WardrobeItems.id == UUID(item_id))
        ).scalar_one()

        assert raw_item.image_ref is not None
        # Assert invariant PR-8: downloadUrl and signed query credentials are NEVER persisted
        assert "downloadUrl" not in raw_item.image_ref
        assert "download_url" not in raw_item.image_ref
        assert "action=get" not in str(raw_item.image_ref)
        assert "X-Amz-" not in str(raw_item.image_ref)
        assert "https://" not in str(raw_item.image_ref)
    finally:
        app.dependency_overrides.clear()


def test_corrupt_media_reference_fails_safely(sqlite_db, fake_storage, test_users):
    """16. Expired or corrupt media references fail safely."""
    user_a_id = test_users["user_a"]
    # Create upload marked as published but with empty canonical_key
    upload = create_published_upload(sqlite_db, user_a_id)
    upload.canonical_key = None
    sqlite_db.commit()

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Corrupt Media Item",
                "category": "tops",
                "color": "black",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": "users/invalid/key.webp",
                },
            },
        )
        assert resp.status_code in (409, 422)
    finally:
        app.dependency_overrides.clear()


def test_staging_objects_inaccessible_via_get_url(sqlite_db, fake_storage, test_users):
    """17. Staging objects remain inaccessible through GET /v1/media/url."""
    user_a_id = test_users["user_a"]
    upload = create_published_upload(sqlite_db, user_a_id, status="authorized")

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        resp = client.get(
            "/v1/media/url",
            params={
                "uploadId": str(upload.upload_id),
                "objectKey": f"staging/users/{user_a_id}/wardrobe/{upload.upload_id}/source.webp",
            },
        )
        assert resp.status_code in (404, 422)
    finally:
        app.dependency_overrides.clear()


def test_legacy_canonical_records_retrievable_and_associable(sqlite_db, fake_storage, test_users):
    """18. Existing legacy canonical records (pre-attempt-id) remain retrievable and associable."""
    user_a_id = test_users["user_a"]
    uid = uuid4()
    # Legacy key format without attempt UUID
    legacy_key = f"users/{user_a_id}/wardrobe/{uid}/original.webp"
    upload = create_published_upload(sqlite_db, user_a_id, upload_id=uid, canonical_key=legacy_key)

    app.dependency_overrides[get_db] = lambda: sqlite_db
    app.dependency_overrides[get_storage_adapter] = lambda: fake_storage
    app.dependency_overrides[get_current_user_id] = lambda: user_a_id

    client = TestClient(app)
    try:
        # Association succeeds
        resp = client.post(
            "/v1/wardrobe/items",
            json={
                "name": "Legacy Coat",
                "category": "outerwear",
                "color": "navy",
                "imageRef": {
                    "uploadId": str(upload.upload_id),
                    "objectKey": legacy_key,
                },
            },
        )
        assert resp.status_code == 201
        assert resp.json()["imageRef"]["objectKey"] == legacy_key

        # Retrieval URL succeeds
        get_resp = client.get(
            "/v1/media/url",
            params={"uploadId": str(upload.upload_id), "objectKey": legacy_key},
        )
        assert get_resp.status_code == 200
        assert "action=get" in get_resp.json()["downloadUrl"]
    finally:
        app.dependency_overrides.clear()
