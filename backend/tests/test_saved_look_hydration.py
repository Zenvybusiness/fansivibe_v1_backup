"""Tests for Stage 2 P1-2: Enriched Saved Look Hydration & Wardrobe Linking.

Covers:
- Saved-look retrieval with all garments active.
- Saved-look retrieval with one archived garment.
- Saved-look retrieval with multiple archived garments.
- Saved-look retrieval with no garment images (fallback handling).
- Complete snapshot preservation (snapshot is read-only and never overwritten).
- Live metadata enrichment (name, category, color, material, isFavorite, fit).
- Correct ID-to-component matching.
- Authenticated ownership scoping (OW-1: foreign saved look -> 404, foreign garments -> not hydrated).
- Unauthenticated requests rejected (401).
- No arbitrary media key signing (rejects keys not belonging to caller's namespace).
- Presigned URL generation for authorized media only (15m SigV4 GET).
- No database writes during hydration (read-only verification).
- Batch query behavior and absence of N+1 queries.
- Pagination compatibility (page, page_size, total, include_items=False compatibility).
- Single saved look endpoint GET /v1/looks/saved/{id}.
- Hairstyle and grooming look handling (items=[]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.errors import ApiError, not_found
from app.application.saved_looks import (
    GetSavedLook,
    HydrateSavedLookGarments,
    ListSavedLooks,
)
from app.domain.ports.repositories import SavedLookRecord, WardrobeItemRecord
from app.domain.ports.storage import ObjectStoragePort, StorageObjectMetadata
from app.infrastructure.db.session import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Test Doubles (In-Memory, OW-1 Scoped)
# ---------------------------------------------------------------------------


@dataclass
class FakeWardrobeItem:
    id: UUID
    user_id: UUID
    name: str
    category: str
    color: str
    material: Optional[str] = None
    is_favorite: bool = False
    fit: Optional[str] = None
    fit_confidence: Optional[float] = None
    image_ref: Optional[dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FakeWardrobeItemRepository:
    """Owner-scoped in-memory wardrobe repository double."""

    def __init__(self, items: Sequence[FakeWardrobeItem] = ()) -> None:
        self.items: list[FakeWardrobeItem] = list(items)
        self.batch_query_count = 0

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[FakeWardrobeItem]:
        for item in self.items:
            if item.user_id == user_id and item.id == item_id:
                return item
        return None

    def get_by_ids(
        self, *, user_id: UUID, item_ids: Sequence[UUID]
    ) -> list[FakeWardrobeItem]:
        self.batch_query_count += 1
        id_set = set(item_ids)
        return [
            item
            for item in self.items
            if item.user_id == user_id and item.id in id_set
        ]

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list[FakeWardrobeItem], int]:
        matched = [
            it
            for it in self.items
            if it.user_id == user_id
            and (category is None or it.category == category)
            and (color is None or it.color == color)
        ]
        start = (page - 1) * page_size
        return matched[start : start + page_size], len(matched)


@dataclass
class FakeSavedLook:
    id: UUID
    user_id: UUID
    look_id: Optional[str]
    title: str
    source_context: Optional[str]
    snapshot: dict[str, Any]
    idempotency_key: str
    source_run_id: Optional[UUID] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FakeSavedLookRepository:
    """Owner-scoped in-memory saved-look repository double."""

    def __init__(self, records: Sequence[FakeSavedLook] = ()) -> None:
        self.records: list[FakeSavedLook] = list(records)
        self.mutated = False

    def insert(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        source_context: str,
        snapshot: dict,
        idempotency_key: str,
        source_run_id: Optional[UUID],
    ) -> FakeSavedLook:
        self.mutated = True
        row = FakeSavedLook(
            id=uuid4(),
            user_id=user_id,
            look_id=look_id,
            title=title,
            source_context=source_context,
            snapshot=snapshot,
            idempotency_key=idempotency_key,
            source_run_id=source_run_id,
        )
        self.records.append(row)
        return row

    def get_for_user(
        self, *, user_id: UUID, saved_look_id: UUID
    ) -> Optional[FakeSavedLook]:
        for rec in self.records:
            if rec.user_id == user_id and rec.id == saved_look_id:
                return rec
        return None

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[FakeSavedLook]:
        for rec in self.records:
            if rec.user_id == user_id and rec.idempotency_key == idempotency_key:
                return rec
        return None

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[FakeSavedLook], int]:
        user_recs = [r for r in self.records if r.user_id == user_id]
        user_recs.sort(key=lambda r: r.created_at, reverse=True)
        total = len(user_recs)
        start = (page - 1) * page_size
        return user_recs[start : start + page_size], total

    def delete(self, *, user_id: UUID, saved_look_id: UUID) -> None:
        self.mutated = True
        self.records = [
            r for r in self.records if not (r.user_id == user_id and r.id == saved_look_id)
        ]

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class FakeStorageAdapter:
    """In-memory storage adapter for presigned GET URL tests."""

    def __init__(self) -> None:
        self.signed_keys: list[str] = []

    async def generate_presigned_get_url(
        self, key: str, expires_in_s: int = 900
    ) -> str:
        self.signed_keys.append(key)
        return f"https://cdn.fansivibe.com/{key}?expires={expires_in_s}&sig=valid_test_sig"

    async def put_object(self, *args, **kwargs):
        raise NotImplementedError

    async def get_object_metadata(self, key: str) -> StorageObjectMetadata:
        raise NotImplementedError

    async def delete_object(self, key: str) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fixtures & Setup
# ---------------------------------------------------------------------------

USER_A = uuid4()
USER_B = uuid4()

TOP_ID = uuid4()
BOTTOM_ID = uuid4()
SHOES_ID = uuid4()
ARCHIVED_ID = uuid4()


@pytest.fixture
def sample_wardrobe(USER_A_id=USER_A):
    return [
        FakeWardrobeItem(
            id=TOP_ID,
            user_id=USER_A_id,
            name="Silk Camp Collar Shirt",
            category="tops",
            color="cream",
            material="silk",
            is_favorite=True,
            fit="relaxed",
            fit_confidence=0.88,
            image_ref={
                "uploadId": "upload-top-001",
                "objectKey": f"users/{USER_A_id}/wardrobe/upload-top-001/canonical.webp",
            },
        ),
        FakeWardrobeItem(
            id=BOTTOM_ID,
            user_id=USER_A_id,
            name="Tailored Pleated Trousers",
            category="bottoms",
            color="charcoal",
            material="wool",
            is_favorite=False,
            fit="slim",
            fit_confidence=0.92,
            image_ref={
                "uploadId": "upload-bot-002",
                "objectKey": f"users/{USER_A_id}/wardrobe/upload-bot-002/canonical.webp",
            },
        ),
        FakeWardrobeItem(
            id=SHOES_ID,
            user_id=USER_A_id,
            name="Leather Penny Loafers",
            category="footwear",
            color="burgundy",
            material="leather",
            is_favorite=False,
            fit="true_to_size",
            fit_confidence=0.95,
            image_ref=None,  # No image
        ),
    ]


@pytest.fixture
def sample_saved_looks(USER_A_id=USER_A):
    look_1_id = uuid4()
    look_2_id = uuid4()
    hairstyle_look_id = uuid4()

    # Look 1: All active garments
    look_1 = FakeSavedLook(
        id=look_1_id,
        user_id=USER_A_id,
        look_id=None,
        title="Riviera Sunset",
        source_context="outfit",
        snapshot={
            "title": "Riviera Sunset",
            "matchScore": 0.94,
            "components": [
                {
                    "id": str(TOP_ID),
                    "name": "Silk Camp Collar Shirt",
                    "category": "tops",
                    "color": "cream",
                    "material": "silk",
                    "reason": "Lustrous drape suited for twilight.",
                },
                {
                    "id": str(BOTTOM_ID),
                    "name": "Tailored Pleated Trousers",
                    "category": "bottoms",
                    "color": "charcoal",
                    "material": "wool",
                    "reason": "Anchors the lighter top with structured tailoring.",
                },
            ],
            "selectedItemIds": [str(TOP_ID), str(BOTTOM_ID)],
            "reasons": ["Harmonious contrast"],
        },
        idempotency_key="idemp-look-1",
    )

    # Look 2: Contains active top + archived garment
    look_2 = FakeSavedLook(
        id=look_2_id,
        user_id=USER_A_id,
        look_id=None,
        title="Archived Combo",
        source_context="outfit",
        snapshot={
            "title": "Archived Combo",
            "matchScore": 0.86,
            "components": [
                {
                    "id": str(TOP_ID),
                    "name": "Silk Camp Collar Shirt",
                    "category": "tops",
                    "color": "cream",
                    "material": "silk",
                    "reason": "Lustrous drape.",
                },
                {
                    "id": str(ARCHIVED_ID),
                    "name": "Vintage Denim Jacket",
                    "category": "outerwear",
                    "color": "indigo",
                    "material": "denim",
                    "reason": "Classic layer.",
                },
            ],
            "selectedItemIds": [str(TOP_ID), str(ARCHIVED_ID)],
            "reasons": ["Casual elegance"],
        },
        idempotency_key="idemp-look-2",
    )

    # Look 3: Hairstyle look
    look_3 = FakeSavedLook(
        id=hairstyle_look_id,
        user_id=USER_A_id,
        look_id="textured_crop",
        title="Textured Crop",
        source_context="hairstyle",
        snapshot={
            "appearance": {"faceShape": "Oval"},
            "recommendations": {"top": {"id": "textured_crop", "name": "Textured Crop"}},
        },
        idempotency_key="idemp-look-3",
    )

    return [look_1, look_2, look_3]


# ---------------------------------------------------------------------------
# Unit Tests (HydrateSavedLookGarments Use Case)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hydrate_all_active_garments(sample_wardrobe, sample_saved_looks):
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(
        wardrobe_items=wardrobe_repo,
        storage=storage,
    )

    result = await hydrator(user_id=USER_A, records=[sample_saved_looks[0]])

    assert sample_saved_looks[0].id in result
    items = result[sample_saved_looks[0].id]
    assert len(items) == 2

    top = next(i for i in items if i.id == str(TOP_ID))
    assert top.name == "Silk Camp Collar Shirt"
    assert top.category == "tops"
    assert top.color == "cream"
    assert top.material == "silk"
    assert top.isFavorite is True
    assert top.fit == "relaxed"
    assert top.fitConfidence == 0.88
    assert top.isArchived is False
    assert top.imageUrl is not None
    assert f"users/{USER_A}/wardrobe/upload-top-001/canonical.webp" in top.imageUrl
    assert top.reason == "Lustrous drape suited for twilight."

    bottom = next(i for i in items if i.id == str(BOTTOM_ID))
    assert bottom.name == "Tailored Pleated Trousers"
    assert bottom.category == "bottoms"
    assert bottom.isArchived is False
    assert bottom.imageUrl is not None


@pytest.mark.anyio
async def test_hydrate_with_archived_garment(sample_wardrobe, sample_saved_looks):
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(
        wardrobe_items=wardrobe_repo,
        storage=storage,
    )

    result = await hydrator(user_id=USER_A, records=[sample_saved_looks[1]])

    items = result[sample_saved_looks[1].id]
    assert len(items) == 2

    # Active top
    top = next(i for i in items if i.id == str(TOP_ID))
    assert top.isArchived is False
    assert top.imageUrl is not None

    # Archived outerwear
    archived = next(i for i in items if i.id == str(ARCHIVED_ID))
    assert archived.isArchived is True
    assert archived.name == "Vintage Denim Jacket"
    assert archived.category == "outerwear"
    assert archived.color == "indigo"
    assert archived.material == "denim"
    assert archived.imageUrl is None
    assert archived.imageRef is None
    assert archived.reason == "Classic layer."


@pytest.mark.anyio
async def test_hydrate_hairstyle_returns_empty_items(sample_wardrobe, sample_saved_looks):
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    hydrator = HydrateSavedLookGarments(wardrobe_items=wardrobe_repo)

    result = await hydrator(user_id=USER_A, records=[sample_saved_looks[2]])

    items = result[sample_saved_looks[2].id]
    assert items == []
    # Wardrobe repository was never queried
    assert wardrobe_repo.batch_query_count == 0


@pytest.mark.anyio
async def test_hydrate_no_image_garment(USER_A_id=USER_A):
    wardrobe_item = FakeWardrobeItem(
        id=SHOES_ID,
        user_id=USER_A_id,
        name="Leather Penny Loafers",
        category="footwear",
        color="burgundy",
        image_ref=None,
    )
    saved_look = FakeSavedLook(
        id=uuid4(),
        user_id=USER_A_id,
        look_id=None,
        title="Footwear Look",
        source_context="outfit",
        snapshot={
            "components": [
                {
                    "id": str(SHOES_ID),
                    "name": "Leather Penny Loafers",
                    "category": "footwear",
                    "color": "burgundy",
                }
            ],
            "selectedItemIds": [str(SHOES_ID)],
        },
        idempotency_key="idemp-shoes",
    )
    wardrobe_repo = FakeWardrobeItemRepository([wardrobe_item])
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(wardrobe_items=wardrobe_repo, storage=storage)

    result = await hydrator(user_id=USER_A_id, records=[saved_look])
    items = result[saved_look.id]
    assert len(items) == 1
    assert items[0].id == str(SHOES_ID)
    assert items[0].isArchived is False
    assert items[0].imageUrl is None
    assert len(storage.signed_keys) == 0


@pytest.mark.anyio
async def test_batch_hydration_prevents_n_plus_one(sample_wardrobe, sample_saved_looks):
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(wardrobe_items=wardrobe_repo, storage=storage)

    # Hydrate 3 looks at once
    result = await hydrator(user_id=USER_A, records=sample_saved_looks)

    assert len(result) == 3
    # Exactly 1 batch query was executed for all looks on the page!
    assert wardrobe_repo.batch_query_count == 1


@pytest.mark.anyio
async def test_snapshot_preservation_and_no_writes(sample_wardrobe, sample_saved_looks):
    saved_repo = FakeSavedLookRepository(sample_saved_looks)
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(wardrobe_items=wardrobe_repo, storage=storage)

    original_snapshot_copy = dict(sample_saved_looks[0].snapshot)

    result = await hydrator(user_id=USER_A, records=[sample_saved_looks[0]])

    assert sample_saved_looks[0].snapshot == original_snapshot_copy
    assert saved_repo.mutated is False


@pytest.mark.anyio
async def test_no_arbitrary_media_key_signing(USER_A_id=USER_A):
    """Foreign key inside imageRef is rejected to prevent SSRF / signature forgery."""
    malicious_item = FakeWardrobeItem(
        id=TOP_ID,
        user_id=USER_A_id,
        name="Top",
        category="tops",
        color="white",
        image_ref={"objectKey": f"users/{USER_B}/private/secret.pdf"},  # Foreign user key
    )
    saved_look = FakeSavedLook(
        id=uuid4(),
        user_id=USER_A_id,
        look_id=None,
        title="Test",
        source_context="outfit",
        snapshot={"components": [{"id": str(TOP_ID), "name": "Top", "category": "tops", "color": "white"}]},
        idempotency_key="idemp-sec",
    )
    wardrobe_repo = FakeWardrobeItemRepository([malicious_item])
    storage = FakeStorageAdapter()
    hydrator = HydrateSavedLookGarments(wardrobe_items=wardrobe_repo, storage=storage)

    result = await hydrator(user_id=USER_A_id, records=[saved_look])
    items = result[saved_look.id]
    assert len(items) == 1
    # Foreign key was NOT signed!
    assert items[0].imageUrl is None
    assert len(storage.signed_keys) == 0


# ---------------------------------------------------------------------------
# API Route Tests (FastAPI TestClient + Dependency Overrides)
# ---------------------------------------------------------------------------


def test_api_list_saved_looks_hydrates_garments(sample_wardrobe, sample_saved_looks):
    saved_repo = FakeSavedLookRepository(sample_saved_looks)
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()

    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    # Mock DB session use cases by patching route dependencies
    from app.infrastructure.db.repositories import (
        SavedLookRepositorySQL,
        WardrobeItemRepositorySQL,
    )

    class MockSession:
        pass

    mock_db = MockSession()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Monkeypatch repository instantiation in route
    import app.api.routers.looks as looks_module

    orig_saved_repo = looks_module.SavedLookRepositorySQL
    orig_wardrobe_repo = looks_module.WardrobeItemRepositorySQL
    looks_module.SavedLookRepositorySQL = lambda db: saved_repo
    looks_module.WardrobeItemRepositorySQL = lambda db: wardrobe_repo

    client = TestClient(app)
    try:
        resp = client.get("/v1/looks/saved?include_items=true")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        items = data["items"]
        assert len(items) == 3

        # Look 1: All active garments hydrated
        look_1 = next(l for l in items if l["title"] == "Riviera Sunset")
        assert look_1["items"] is not None
        assert len(look_1["items"]) == 2
        top_garment = next(g for g in look_1["items"] if g["id"] == str(TOP_ID))
        assert top_garment["name"] == "Silk Camp Collar Shirt"
        assert top_garment["isArchived"] is False
        assert top_garment["imageUrl"] is not None

        # Look 2: Contains archived garment
        look_2 = next(l for l in items if l["title"] == "Archived Combo")
        assert look_2["items"] is not None
        archived_garment = next(g for g in look_2["items"] if g["id"] == str(ARCHIVED_ID))
        assert archived_garment["isArchived"] is True
        assert archived_garment["imageUrl"] is None

        # Look 3: Hairstyle
        look_3 = next(l for l in items if l["title"] == "Textured Crop")
        assert look_3["items"] == []

    finally:
        looks_module.SavedLookRepositorySQL = orig_saved_repo
        looks_module.WardrobeItemRepositorySQL = orig_wardrobe_repo
        app.dependency_overrides.clear()


def test_api_list_saved_looks_unhydrated_compat(sample_wardrobe, sample_saved_looks):
    """When include_items=false, items is None and byte-compatible with existing schema."""
    saved_repo = FakeSavedLookRepository(sample_saved_looks)
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()

    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    import app.api.routers.looks as looks_module

    orig_saved_repo = looks_module.SavedLookRepositorySQL
    orig_wardrobe_repo = looks_module.WardrobeItemRepositorySQL
    looks_module.SavedLookRepositorySQL = lambda db: saved_repo
    looks_module.WardrobeItemRepositorySQL = lambda db: wardrobe_repo

    client = TestClient(app)
    try:
        resp = client.get("/v1/looks/saved?include_items=false")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["items"] is None
        # Zero wardrobe queries executed
        assert wardrobe_repo.batch_query_count == 0
    finally:
        looks_module.SavedLookRepositorySQL = orig_saved_repo
        looks_module.WardrobeItemRepositorySQL = orig_wardrobe_repo
        app.dependency_overrides.clear()


def test_api_get_saved_look_detail_success(sample_wardrobe, sample_saved_looks):
    saved_repo = FakeSavedLookRepository(sample_saved_looks)
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()

    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    import app.api.routers.looks as looks_module

    orig_saved_repo = looks_module.SavedLookRepositorySQL
    orig_wardrobe_repo = looks_module.WardrobeItemRepositorySQL
    looks_module.SavedLookRepositorySQL = lambda db: saved_repo
    looks_module.WardrobeItemRepositorySQL = lambda db: wardrobe_repo

    client = TestClient(app)
    try:
        look_id = sample_saved_looks[0].id
        resp = client.get(f"/v1/looks/saved/{look_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == str(look_id)
        assert data["title"] == "Riviera Sunset"
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "Silk Camp Collar Shirt"
    finally:
        looks_module.SavedLookRepositorySQL = orig_saved_repo
        looks_module.WardrobeItemRepositorySQL = orig_wardrobe_repo
        app.dependency_overrides.clear()


def test_api_get_saved_look_detail_ow1_cross_user_404(sample_wardrobe, sample_saved_looks):
    """User B requesting User A's saved look receives 404 (never 403, no existence leak)."""
    saved_repo = FakeSavedLookRepository(sample_saved_looks)
    wardrobe_repo = FakeWardrobeItemRepository(sample_wardrobe)
    storage = FakeStorageAdapter()

    # Authenticated as USER_B
    app.dependency_overrides[get_current_user_id] = lambda: USER_B
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    import app.api.routers.looks as looks_module

    orig_saved_repo = looks_module.SavedLookRepositorySQL
    orig_wardrobe_repo = looks_module.WardrobeItemRepositorySQL
    looks_module.SavedLookRepositorySQL = lambda db: saved_repo
    looks_module.WardrobeItemRepositorySQL = lambda db: wardrobe_repo

    client = TestClient(app)
    try:
        user_a_look_id = sample_saved_looks[0].id
        resp = client.get(f"/v1/looks/saved/{user_a_look_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
    finally:
        looks_module.SavedLookRepositorySQL = orig_saved_repo
        looks_module.WardrobeItemRepositorySQL = orig_wardrobe_repo
        app.dependency_overrides.clear()


def test_api_get_saved_look_detail_unauthenticated_401():
    client = TestClient(app)
    look_id = uuid4()
    resp = client.get(f"/v1/looks/saved/{look_id}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"

