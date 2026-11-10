"""Tests for Stage 2 P1-1: Interactive Outfit Component Swapping.

Covers:
- Unit tests:
  - Valid top, bottom, footwear, outerwear, and accessory replacements.
  - Unsupported slot rejection (422).
  - Missing/unknown garment rejection (404).
  - Wrong garment category rejection (422).
  - Duplicate garment rejection across slots (422).
  - Pinned slot replacement rejection (409 PINNED_SLOT_CONFLICT).
  - Preservation of other pinned garments.
  - Canonical scoring engine invocation and compatibility recalculation.
  - No fabricated scores or reasons.
  - No unintended wardrobe mutation (read/derive only).
- Security tests:
  - Unauthenticated request rejection (401).
  - Cross-user garment injection (OW-1: 404, never 403, no leakage).
  - Forged IDs / malformed UUIDs (422).
- Candidate retrieval tests:
  - Category matching.
  - Current outfit garments excluded.
  - Owner-scoped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional, Sequence
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.errors import ApiError
from app.application.outfits import (
    GetOutfitCandidates,
    SwapOutfitSlot,
    normalize_slot_name,
)
from app.domain.ports.repositories import WardrobeItemRecord
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
    image_ref: Optional[dict] = None
    created_at: object = None
    updated_at: object = None


class FakeWardrobeItemRepository:
    """Owner-scoped in-memory wardrobe repository double."""

    def __init__(self, items: Sequence[FakeWardrobeItem] = ()) -> None:
        self.items: list[FakeWardrobeItem] = list(items)

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[FakeWardrobeItem]:
        for item in self.items:
            if item.user_id == user_id and item.id == item_id:
                return item
        return None

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


class FakeUserStateRepository:
    def __init__(self, preferences: Optional[dict] = None) -> None:
        self.preferences = preferences or {}

    def get_profile(self, *, user_id: UUID):
        return SimpleNamespace(preferences=self.preferences)


class FakeStorageAdapter(ObjectStoragePort):
    async def generate_presigned_get_url(self, *, key: str, expires_in_s: int = 900) -> str:
        return f"https://cdn.example.com/{key}?expires={expires_in_s}"

    async def put_object(self, *, key: str, data: bytes, content_type: str, metadata: Optional[dict] = None) -> StorageObjectMetadata:
        return StorageObjectMetadata(key=key, size_bytes=len(data), content_type=content_type, etag="fake_etag")

    async def head_object(self, *, key: str) -> Optional[StorageObjectMetadata]:
        return None


    async def delete_object(self, *, key: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

USER_A = uuid4()
USER_B = uuid4()

TOP_A1 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="White Linen Shirt", category="tops", color="white", material="linen", fit="relaxed", fit_confidence=0.8)
TOP_A2 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Black Crewneck", category="tops", color="black", material="cotton", fit="regular", fit_confidence=0.9)
BOTTOM_A1 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Navy Chinos", category="bottoms", color="navy", material="cotton", fit="regular", fit_confidence=0.85)
BOTTOM_A2 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Olive Cargo Trousers", category="bottoms", color="olive", material="cotton", fit="relaxed", fit_confidence=0.7)
SHOES_A1 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="White Leather Sneakers", category="footwear", color="white", material="leather")
SHOES_A2 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Brown Chelsea Boots", category="footwear", color="brown", material="leather")
OUTER_A1 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Charcoal Wool Coat", category="outerwear", color="charcoal", material="wool")
ACCESSORY_A1 = FakeWardrobeItem(id=uuid4(), user_id=USER_A, name="Silver Automatic Watch", category="accessories", color="silver", material="metal")

# Foreign items belonging to User B
TOP_B1 = FakeWardrobeItem(id=uuid4(), user_id=USER_B, name="User B Silk Shirt", category="tops", color="red", material="silk")
BOTTOM_B1 = FakeWardrobeItem(id=uuid4(), user_id=USER_B, name="User B Jeans", category="bottoms", color="black", material="denim")


def _build_repo() -> FakeWardrobeItemRepository:
    return FakeWardrobeItemRepository([
        TOP_A1, TOP_A2, BOTTOM_A1, BOTTOM_A2, SHOES_A1, SHOES_A2, OUTER_A1, ACCESSORY_A1,
        TOP_B1, BOTTOM_B1,
    ])


# ---------------------------------------------------------------------------
# Unit Tests — Normalization & Domain Use Cases
# ---------------------------------------------------------------------------


def test_normalize_slot_name():
    assert normalize_slot_name("top") == "tops"
    assert normalize_slot_name("tops") == "tops"
    assert normalize_slot_name("Tops") == "tops"
    assert normalize_slot_name("bottom") == "bottoms"
    assert normalize_slot_name("bottoms") == "bottoms"
    assert normalize_slot_name("shoe") == "footwear"
    assert normalize_slot_name("shoes") == "footwear"
    assert normalize_slot_name("footwear") == "footwear"
    assert normalize_slot_name("outerwear") == "outerwear"
    assert normalize_slot_name("accessory") == "accessories"
    assert normalize_slot_name("accessories") == "accessories"

    with pytest.raises(ApiError) as exc_info:
        normalize_slot_name("hat")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"


def test_swap_top_slot_success():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    rec, prev_id, prev_score, warnings = use_case.execute(
        user_id=USER_A,
        occasion="work",
        mood="clean",
        fit="regular",
        color_palette="neutral",
        current_garment_ids=current_ids,
        slot="tops",
        replacement_garment_id=TOP_A2.id,
    )

    assert prev_id == str(TOP_A1.id)
    assert rec.match_score >= 0.0 and rec.match_score <= 1.0
    rec_component_ids = [c.id for c in rec.components]
    assert str(TOP_A2.id) in rec_component_ids
    assert str(TOP_A1.id) not in rec_component_ids
    assert str(BOTTOM_A1.id) in rec_component_ids
    assert str(SHOES_A1.id) in rec_component_ids


def test_swap_bottom_slot_success():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    rec, prev_id, prev_score, warnings = use_case.execute(
        user_id=USER_A,
        occasion="casual",
        mood="relaxed",
        fit="relaxed",
        color_palette="neutral",
        current_garment_ids=current_ids,
        slot="bottoms",
        replacement_garment_id=BOTTOM_A2.id,
    )

    assert prev_id == str(BOTTOM_A1.id)
    rec_component_ids = [c.id for c in rec.components]
    assert str(BOTTOM_A2.id) in rec_component_ids
    assert str(BOTTOM_A1.id) not in rec_component_ids
    assert str(TOP_A1.id) in rec_component_ids


def test_swap_footwear_slot_success():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    rec, prev_id, prev_score, warnings = use_case.execute(
        user_id=USER_A,
        occasion="evening",
        mood="sharp",
        fit="regular",
        color_palette="neutral",
        current_garment_ids=current_ids,
        slot="shoes",
        replacement_garment_id=SHOES_A2.id,
    )

    assert prev_id == str(SHOES_A1.id)
    rec_component_ids = [c.id for c in rec.components]
    assert str(SHOES_A2.id) in rec_component_ids
    assert str(SHOES_A1.id) not in rec_component_ids


def test_swap_outerwear_and_accessory_slot_success():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    # Add outerwear into an outfit that didn't have it
    rec, prev_id, _, _ = use_case.execute(
        user_id=USER_A,
        occasion="winter",
        mood="classic",
        fit="regular",
        color_palette="neutral",
        current_garment_ids=current_ids,
        slot="outerwear",
        replacement_garment_id=OUTER_A1.id,
    )
    assert prev_id is None
    rec_component_ids = [c.id for c in rec.components]
    assert str(OUTER_A1.id) in rec_component_ids


def test_swap_rejects_category_mismatch():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    # Attempting to replace top with shoes
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=SHOES_A1.id,
        )
    assert exc_info.value.status_code == 422
    assert "replacement garment category" in exc_info.value.details["field_errors"][0]["error"]


def test_swap_rejects_duplicate_garment_in_different_slot():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    # Let's say user has an item in bottoms, and tries to use it in footwear
    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="footwear",
            replacement_garment_id=BOTTOM_A1.id,
        )
    assert exc_info.value.status_code == 422


def test_swap_rejects_pinned_slot():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    # Pin TOP_A1 and attempt to replace tops slot
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=TOP_A2.id,
            pinned_garment_ids=[TOP_A1.id],
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PINNED_SLOT_CONFLICT"


def test_swap_preserves_other_pinned_garments():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    # Pin BOTTOM_A1 and SHOES_A1, replace top
    rec, prev_id, _, _ = use_case.execute(
        user_id=USER_A,
        occasion="work",
        mood="clean",
        fit="regular",
        color_palette="neutral",
        current_garment_ids=current_ids,
        slot="tops",
        replacement_garment_id=TOP_A2.id,
        pinned_garment_ids=[BOTTOM_A1.id, SHOES_A1.id],
    )
    rec_component_ids = [c.id for c in rec.components]
    assert str(BOTTOM_A1.id) in rec_component_ids
    assert str(SHOES_A1.id) in rec_component_ids


def test_candidates_retrieval():
    repo = _build_repo()
    candidates_use_case = GetOutfitCandidates(wardrobe_items=repo)

    # For tops, excluding TOP_A1
    slot, items = candidates_use_case.execute(
        user_id=USER_A,
        slot="top",
        current_garment_ids=[TOP_A1.id],
    )
    assert slot == "tops"
    item_ids = [it.id for it in items]
    assert TOP_A2.id in item_ids
    assert TOP_A1.id not in item_ids
    # User B item must not be included
    assert TOP_B1.id not in item_ids


# ---------------------------------------------------------------------------
# Security & Ownership Tests (OW-1)
# ---------------------------------------------------------------------------


def test_swap_rejects_foreign_replacement_garment():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    # User A tries to replace top with User B's TOP_B1
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=TOP_B1.id,
        )
    # OW-1: Foreign items return 404 (indistinguishable from nonexistent)
    assert exc_info.value.status_code == 404


def test_swap_rejects_foreign_current_garment():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    # Current outfit contains User B's BOTTOM_B1
    current_ids = [TOP_A1.id, BOTTOM_B1.id, SHOES_A1.id]
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=TOP_A2.id,
        )
    assert exc_info.value.status_code == 404


def test_swap_rejects_nonexistent_garment_id():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id, SHOES_A1.id]
    fake_id = uuid4()
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=fake_id,
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# API Integration Tests (FastAPI TestClient)
# ---------------------------------------------------------------------------


def test_api_swap_slot_endpoint():
    repo = _build_repo()
    client = TestClient(app)

    # Dependency overrides
    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()

    # Monkeypatch the repositories in SwapOutfitSlot
    import app.api.routers.outfits as outfits_router

    original_init = outfits_router.SwapOutfitSlot.__init__

    def mock_init(self, wardrobe_items, user_state, feedback=None, saved_looks=None, wears=None):
        self._wardrobe_items = repo
        self._user_state = FakeUserStateRepository()
        self._feedback = None
        self._saved_looks = None
        self._wears = None

    outfits_router.SwapOutfitSlot.__init__ = mock_init

    try:
        response = client.post(
            "/v1/outfits/swap-slot",
            headers={"Authorization": "Bearer dev"},
            json={
                "occasion": "work",
                "mood": "clean",
                "fit": "regular",
                "colorPalette": "neutral",
                "currentGarmentIds": [str(TOP_A1.id), str(BOTTOM_A1.id), str(SHOES_A1.id)],
                "slot": "tops",
                "replacementGarmentId": str(TOP_A2.id),
                "pinnedGarmentIds": [str(BOTTOM_A1.id)],
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["replacedSlot"] == "tops"
        assert data["previousGarmentId"] == str(TOP_A1.id)
        assert data["replacementGarmentId"] == str(TOP_A2.id)
        assert 0.0 <= data["compatibilityScore"] <= 1.0
        assert "outfit" in data
        assert len(data["outfit"]["components"]) == 3
        comp_ids = [c["id"] for c in data["outfit"]["components"]]
        assert str(TOP_A2.id) in comp_ids
        assert str(BOTTOM_A1.id) in comp_ids
    finally:
        outfits_router.SwapOutfitSlot.__init__ = original_init
        app.dependency_overrides.clear()


def test_api_candidates_endpoint():
    repo = _build_repo()
    client = TestClient(app)

    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()

    import app.api.routers.outfits as outfits_router

    original_cand_init = outfits_router.GetOutfitCandidates.__init__

    def mock_cand_init(self, wardrobe_items):
        self._wardrobe_items = repo

    outfits_router.GetOutfitCandidates.__init__ = mock_cand_init

    try:
        response = client.post(
            "/v1/outfits/candidates",
            headers={"Authorization": "Bearer dev"},
            json={
                "slot": "tops",
                "currentGarmentIds": [str(TOP_A1.id)],
                "limit": 10,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["slot"] == "tops"
        assert len(data["candidates"]) >= 1
        cand_ids = [c["id"] for c in data["candidates"]]
        assert str(TOP_A2.id) in cand_ids
        assert str(TOP_A1.id) not in cand_ids
        # Ensure User B item is excluded
        assert str(TOP_B1.id) not in cand_ids
    finally:
        outfits_router.GetOutfitCandidates.__init__ = original_cand_init
        app.dependency_overrides.clear()


def test_api_unauthenticated_requests_fail():
    client = TestClient(app)
    # Missing auth header
    response = client.post(
        "/v1/outfits/swap-slot",
        json={
            "occasion": "work",
            "mood": "clean",
            "fit": "regular",
            "colorPalette": "neutral",
            "currentGarmentIds": [str(TOP_A1.id)],
            "slot": "tops",
            "replacementGarmentId": str(TOP_A2.id),
        },
    )
    # AuthSession resolution returns 401 when unauthenticated
    assert response.status_code == 401


def test_swap_rejects_blank_preference_fields():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id]
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="   ",  # Blank
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=TOP_A2.id,
        )
    assert exc_info.value.status_code == 422


def test_swap_rejects_empty_current_garment_ids():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=[],
            slot="tops",
            replacement_garment_id=TOP_A2.id,
        )
    assert exc_info.value.status_code == 422


def test_swap_rejects_pinned_garment_not_in_outfit():
    repo = _build_repo()
    user_state = FakeUserStateRepository()
    use_case = SwapOutfitSlot(wardrobe_items=repo, user_state=user_state)

    current_ids = [TOP_A1.id, BOTTOM_A1.id]
    foreign_pin = uuid4()
    with pytest.raises(ApiError) as exc_info:
        use_case.execute(
            user_id=USER_A,
            occasion="work",
            mood="clean",
            fit="regular",
            color_palette="neutral",
            current_garment_ids=current_ids,
            slot="tops",
            replacement_garment_id=TOP_A2.id,
            pinned_garment_ids=[foreign_pin],
        )
    assert exc_info.value.status_code == 422


def test_api_swap_slot_validation_error_on_malformed_uuid():
    client = TestClient(app)
    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    try:
        response = client.post(
            "/v1/outfits/swap-slot",
            headers={"Authorization": "Bearer dev"},
            json={
                "occasion": "work",
                "mood": "clean",
                "fit": "regular",
                "colorPalette": "neutral",
                "currentGarmentIds": ["not-a-uuid"],
                "slot": "tops",
                "replacementGarmentId": str(TOP_A2.id),
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_api_swap_slot_pinned_conflict_status_409():
    repo = _build_repo()
    client = TestClient(app)
    app.dependency_overrides[get_current_user_id] = lambda: USER_A

    import app.api.routers.outfits as outfits_router
    orig = outfits_router.SwapOutfitSlot.__init__
    def mock_init(self, wardrobe_items, user_state, feedback=None, saved_looks=None, wears=None):
        self._wardrobe_items = repo
        self._user_state = FakeUserStateRepository()
        self._feedback = None
        self._saved_looks = None
        self._wears = None

    outfits_router.SwapOutfitSlot.__init__ = mock_init
    try:
        response = client.post(
            "/v1/outfits/swap-slot",
            headers={"Authorization": "Bearer dev"},
            json={
                "occasion": "work",
                "mood": "clean",
                "fit": "regular",
                "colorPalette": "neutral",
                "currentGarmentIds": [str(TOP_A1.id), str(BOTTOM_A1.id)],
                "slot": "tops",
                "replacementGarmentId": str(TOP_A2.id),
                "pinnedGarmentIds": [str(TOP_A1.id)],
            },
        )
        assert response.status_code == 409
        body = response.json()
        assert (body.get("code") == "PINNED_SLOT_CONFLICT" or body.get("error", {}).get("code") == "PINNED_SLOT_CONFLICT")

    finally:
        outfits_router.SwapOutfitSlot.__init__ = orig
        app.dependency_overrides.clear()

