"""Tests for Stage 1D Batch 4B.2: Authenticated Wardrobe & Profile Data Authority.

Verifies:
1. Authenticated wardrobe comes from the server repository.
2. Client snapshot cannot override authenticated wardrobe.
3. Saved looks are loaded for the correct authenticated user.
4. Profile preferences come from authoritative user state.
5. User identity is derived from validated authentication.
6. Empty authenticated wardrobe is handled correctly.
7. Repository failure does not silently use stale client data.
8. Guest requests do not query authenticated wardrobe repositories.
9. Guest appearance information is not persisted.
10. Existing assistant endpoint contracts remain compatible.
11. Batch 4B.1 adapters remain unchanged and functional.
12. Garment ID and ownership preservation.
13. Pagination loads all pages for wardrobe.
14. Transient client face preserved when server unmeasured.
15. Server face overrides conflicting client face.
16. Saved looks error degrades safely.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user_id
from app.api.errors import ApiError
from app.domain.ports.repositories import (
    SavedLookRecord,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.infrastructure.db.session import get_db
from app.models.schemas import (
    AssistantReply,
    AssistantRequest,
    ChatMessage,
    FaceData,
    UserContext,
    WardrobeItem,
)


# --- Test Doubles / Spies ----------------------------------------------------


class SpyWardrobeRepo:
    def __init__(self, items: Optional[list[WardrobeItemRecord]] = None, fail: bool = False) -> None:
        self.items = items or []
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int = 1,
        page_size: int = 100,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list[WardrobeItemRecord], int]:
        self.calls.append(("get_for_user", {"user_id": user_id, "page": page, "page_size": page_size}))
        if self.fail:
            raise RuntimeError("Database connection lost during wardrobe read")
        total = len(self.items)
        start = (page - 1) * page_size
        end = start + page_size
        return self.items[start:end], total


class SpySavedLookRepo:
    def __init__(self, records: Optional[list[SavedLookRecord]] = None, fail: bool = False) -> None:
        self.records = records or []
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_for_user(
        self, *, user_id: UUID, page: int = 1, page_size: int = 100
    ) -> tuple[list[SavedLookRecord], int]:
        self.calls.append(("list_for_user", {"user_id": user_id, "page": page, "page_size": page_size}))
        if self.fail:
            raise RuntimeError("Database error during saved look read")
        total = len(self.records)
        start = (page - 1) * page_size
        end = start + page_size
        return self.records[start:end], total


class SpyUserStateRepo:
    def __init__(self, profile: Optional[UserProfileRecord] = None, fail: bool = False) -> None:
        self.profile = profile
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        self.calls.append(("get_profile", {"user_id": user_id}))
        if self.fail:
            raise RuntimeError("Database error during profile read")
        return self.profile

    def update_style_profile(self, *args, **kwargs) -> bool:
        self.calls.append(("update_style_profile", kwargs))
        return True


from datetime import datetime, timezone


def _make_wardrobe_record(
    item_id: str,
    name: str,
    category: str = "tops",
    color: str = "navy",
    material: Optional[str] = "cotton",
    is_favorite: bool = False,
    user_id: Optional[UUID] = None,
) -> WardrobeItemRecord:
    uid = user_id or uuid.uuid4()
    now = datetime.now(timezone.utc)
    return WardrobeItemRecord(
        id=UUID(item_id) if len(item_id) == 36 else uuid.uuid5(uuid.NAMESPACE_DNS, item_id),
        user_id=uid,
        name=name,
        category=category,
        color=color,
        material=material,
        is_favorite=is_favorite,
        image_ref=None,
        created_at=now,
        updated_at=now,
    )


# --- Test Fixtures & Harness --------------------------------------------------


@pytest.fixture
def test_setup(monkeypatch):
    """Sets up FastAPI test client with isolated repos and auth."""
    authenticated_user_id = uuid.uuid4()
    wardrobe_repo = SpyWardrobeRepo()
    saved_look_repo = SpySavedLookRepo()
    user_state_repo = SpyUserStateRepo()

    monkeypatch.setattr(main_module, "WardrobeItemRepositorySQL", lambda db: wardrobe_repo)
    monkeypatch.setattr(main_module, "SavedLookRepositorySQL", lambda db: saved_look_repo)
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db: user_state_repo)

    captured_handles: list[dict[str, Any]] = []

    def fake_handle(request, **kwargs):
        captured_handles.append({"request": request, "kwargs": kwargs})
        return AssistantReply(
            intent="wardrobe",
            text="Here is your wardrobe.",
            cards=[],
        )

    monkeypatch.setattr("app.ai.engine.handle", fake_handle)

    # Database dependency override: dummy session with dummy execute for testing
    dummy_session = type("DummySession", (), {"execute": lambda self, *a, **k: None})()
    main_module.app.dependency_overrides[get_db] = lambda: dummy_session

    def fake_get_current_user_id(authorization=None, db=None):
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            if token == "valid-auth-token":
                return authenticated_user_id
        raise ApiError(status_code=401, code="AUTHENTICATION_ERROR", message="Invalid token")

    monkeypatch.setattr(main_module, "get_current_user_id", fake_get_current_user_id)

    client = TestClient(main_module.app)

    yield {
        "client": client,
        "user_id": authenticated_user_id,
        "wardrobe_repo": wardrobe_repo,
        "saved_look_repo": saved_look_repo,
        "user_state_repo": user_state_repo,
        "captured_handles": captured_handles,
    }

    main_module.app.dependency_overrides.pop(get_db, None)


# --- Tests --------------------------------------------------------------------


def test_1_authenticated_wardrobe_from_server_repository(test_setup):
    """1. Authenticated wardrobe items are loaded from the server repository."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    captured = test_setup["captured_handles"]

    server_item = _make_wardrobe_record("00000000-0000-0000-0000-000000000001", "Silk Oxford", "tops", "white", user_id=uid)
    wardrobe_repo.items = [server_item]

    # Client sends an empty snapshot or different items
    body = {
        "messages": [{"role": "user", "content": "show my wardrobe"}],
        "user": {
            "wardrobe": [{"id": "client-item-1", "name": "Fake Tee", "category": "tops", "color": "red"}],
            "savedLooks": [],
            "preferredOccasions": ["casual"],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    assert len(wardrobe_repo.calls) >= 1
    assert wardrobe_repo.calls[0][1]["user_id"] == uid

    assert len(captured) == 1
    effective_request = captured[0]["request"]
    effective_wardrobe = effective_request.user.wardrobe

    assert len(effective_wardrobe) == 1
    assert effective_wardrobe[0].id == str(server_item.id)
    assert effective_wardrobe[0].name == "Silk Oxford"
    assert effective_wardrobe[0].color == "white"


def test_2_client_snapshot_cannot_override_authenticated_wardrobe(test_setup):
    """2. Client wardrobe snapshot cannot overwrite server records or inject unverified items."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    captured = test_setup["captured_handles"]

    server_item = _make_wardrobe_record("00000000-0000-0000-0000-000000000002", "Navy Wool Blazer", "outerwear", "navy", user_id=uid)
    wardrobe_repo.items = [server_item]

    # Client attempts to send 3 unverified garments
    body = {
        "messages": [{"role": "user", "content": "recommend outfit"}],
        "user": {
            "wardrobe": [
                {"id": "c-1", "name": "Unverified Top", "category": "tops", "color": "green"},
                {"id": "c-2", "name": "Unverified Chinos", "category": "bottoms", "color": "tan"},
                {"id": "c-3", "name": "Unverified Boots", "category": "footwear", "color": "brown"},
            ],
            "savedLooks": [],
            "preferredOccasions": ["date"],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_wardrobe = captured[0]["request"].user.wardrobe
    # Only the 1 server item exists; client garments were NOT merged or accepted
    assert len(effective_wardrobe) == 1
    assert effective_wardrobe[0].id == str(server_item.id)
    assert effective_wardrobe[0].name == "Navy Wool Blazer"
    assert not any(i.id in ("c-1", "c-2", "c-3") for i in effective_wardrobe)


def test_3_saved_looks_loaded_for_correct_authenticated_user(test_setup):
    """3. Saved looks and preferred item IDs are loaded for the authenticated user identity."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    saved_look_repo = test_setup["saved_look_repo"]
    captured = test_setup["captured_handles"]

    outfit_item_uuid = "00000000-0000-0000-0000-000000000099"
    saved_look_repo.records = [
        SavedLookRecord(
            id=uuid.uuid4(),
            look_id="textured_quiff",
            title="Textured Quiff",
            snapshot={"matchScore": 0.95},
            source_run_id=None,
            created_at=datetime.now(timezone.utc),
            source_context="hairstyle",
        ),
        SavedLookRecord(
            id=uuid.uuid4(),
            look_id=None,
            title="Date Night Favorite",
            snapshot={"selectedItemIds": [outfit_item_uuid]},
            source_run_id=None,
            created_at=datetime.now(timezone.utc),
            source_context="outfit",
        ),
    ]

    body = {
        "messages": [{"role": "user", "content": "show my saved looks"}],
        "user": {"wardrobe": [], "savedLooks": ["Stale Look"], "preferredOccasions": []},
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    assert len(saved_look_repo.calls) >= 1
    assert saved_look_repo.calls[0][1]["user_id"] == uid

    effective_user = captured[0]["request"].user
    assert "Textured Quiff" in effective_user.savedLooks or "textured_quiff" in effective_user.savedLooks
    assert "Date Night Favorite" in effective_user.savedLooks
    assert "Stale Look" not in effective_user.savedLooks

    # Preferred item IDs from the saved outfit are passed into engine
    passed_preferred_ids = captured[0]["kwargs"].get("preferred_item_ids")
    assert passed_preferred_ids == [outfit_item_uuid]


def test_4_profile_preferences_come_from_authoritative_user_state(test_setup):
    """4. Profile preferences and appearance profile come from authoritative user state."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    user_state_repo = test_setup["user_state_repo"]
    captured = test_setup["captured_handles"]

    user_state_repo.profile = UserProfileRecord(
        user_id=uid,
        display_name="Authenticated User",
        style_profile={
            "face_shape": "rectangular",
            "skin_tone": "deep",
            "body_type": "athletic",
            "style_type": "minimalist",
        },
        preferences={"preferred_occasions": ["business", "formal"]},
        settings={},
        flags={},
        version=1,
    )

    body = {
        "messages": [{"role": "user", "content": "what should I wear?"}],
        "user": {
            "wardrobe": [],
            "savedLooks": [],
            "preferredOccasions": ["casual"],
            "face": {
                "faceShape": "round",
                "skinTone": "fair",
                "bodyType": "slim",
                "styleType": "streetwear",
            },
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    assert len(user_state_repo.calls) >= 1
    assert user_state_repo.calls[0][1]["user_id"] == uid

    # Server occasions beat client occasions
    passed_occasions = captured[0]["kwargs"].get("preferred_occasions")
    assert passed_occasions == ["business", "formal"]

    # Server appearance profile beats client appearance
    effective_face = captured[0]["request"].user.face
    assert effective_face.faceShape == "rectangular"
    assert effective_face.skinTone == "deep"
    assert effective_face.bodyType == "athletic"
    assert effective_face.styleType == "minimalist"


def test_5_user_identity_derived_from_validated_authentication(test_setup):
    """5. User identity is derived strictly from validated auth, never from request fields."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    wardrobe_repo = test_setup["wardrobe_repo"]

    # Request has user context without token -> treated as guest
    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "user": {
            "wardrobe": [{"id": "g-1", "name": "Guest Tee", "category": "tops", "color": "black"}],
            "savedLooks": [],
            "preferredOccasions": ["casual"],
        },
    }

    resp_guest = client.post("/v1/assistant/chat", json=body)
    assert resp_guest.status_code == 200
    # Zero DB calls for guest
    assert len(wardrobe_repo.calls) == 0

    # Request with invalid token -> treated as guest (401 caught gracefully)
    resp_invalid = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer bad-token"})
    assert resp_invalid.status_code == 200
    assert len(wardrobe_repo.calls) == 0

    # Request with valid token -> uses authenticated uid
    resp_auth = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp_auth.status_code == 200
    assert len(wardrobe_repo.calls) >= 1
    assert wardrobe_repo.calls[0][1]["user_id"] == uid


def test_6_empty_authenticated_wardrobe_handled_correctly(test_setup):
    """6. Empty authenticated wardrobe is handled cleanly without fabricating garments."""
    client = test_setup["client"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    captured = test_setup["captured_handles"]

    # Server wardrobe is empty
    wardrobe_repo.items = []

    body = {
        "messages": [{"role": "user", "content": "recommend outfit"}],
        "user": {
            # Client claims to have items, but server has none
            "wardrobe": [{"id": "c-1", "name": "Fake Jeans", "category": "bottoms", "color": "blue"}],
            "savedLooks": [],
            "preferredOccasions": ["casual"],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_wardrobe = captured[0]["request"].user.wardrobe
    assert effective_wardrobe == []


def test_7_repository_failure_does_not_silently_use_stale_client_data(test_setup):
    """7. Server wardrobe repository failure does not silently fall back to stale client wardrobe."""
    client = test_setup["client"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    wardrobe_repo.fail = True

    body = {
        "messages": [{"role": "user", "content": "show wardrobe"}],
        "user": {
            "wardrobe": [{"id": "stale-1", "name": "Stale Shirt", "category": "tops", "color": "white"}],
            "savedLooks": [],
            "preferredOccasions": [],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    # Fails closed with 500 DATABASE_FAILURE instead of 200 with stale client data
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "DATABASE_FAILURE"


def test_8_guest_requests_do_not_query_authenticated_wardrobe_repositories(test_setup):
    """8. Guest requests do not query authenticated wardrobe, saved look, or user state repositories."""
    client = test_setup["client"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    saved_look_repo = test_setup["saved_look_repo"]
    user_state_repo = test_setup["user_state_repo"]
    captured = test_setup["captured_handles"]

    body = {
        "messages": [{"role": "user", "content": "what should I wear?"}],
        "user": {
            "wardrobe": [{"id": "guest-top", "name": "Guest Shirt", "category": "tops", "color": "black"}],
            "savedLooks": ["Guest Style"],
            "preferredOccasions": ["date"],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body)
    assert resp.status_code == 200

    # Verify zero database queries
    assert len(wardrobe_repo.calls) == 0
    assert len(saved_look_repo.calls) == 0
    assert len(user_state_repo.calls) == 0

    # Guest context was preserved in engine
    req = captured[0]["request"]
    assert len(req.user.wardrobe) == 1
    assert req.user.wardrobe[0].id == "guest-top"
    assert req.user.preferredOccasions == ["date"]


def test_9_guest_appearance_not_persisted(test_setup):
    """9. Guest appearance data is not persisted to the database."""
    client = test_setup["client"]
    user_state_repo = test_setup["user_state_repo"]

    body = {
        "messages": [{"role": "user", "content": "best hairstyle for me"}],
        "user": {
            "wardrobe": [],
            "savedLooks": [],
            "preferredOccasions": [],
            "face": {
                "faceShape": "oval",
                "skinTone": "olive",
                "bodyType": "athletic",
                "styleType": "classic",
            },
        },
    }

    resp = client.post("/v1/assistant/chat", json=body)
    assert resp.status_code == 200

    # Verify zero write calls
    assert not any(call[0] == "update_style_profile" for call in user_state_repo.calls)


def test_10_assistant_endpoint_contract_compatibility(test_setup, monkeypatch):
    """10. Endpoint response adheres to full AssistantReply contract."""
    client = test_setup["client"]

    # Re-enable real engine to verify response serialization
    monkeypatch.undo()

    # Reapply DB dependency override
    dummy_session = type("DummySession", (), {"execute": lambda self, *a, **k: None})()
    main_module.app.dependency_overrides[get_db] = lambda: dummy_session

    body = {
        "messages": [{"role": "user", "content": "what should I wear for date night"}],
        "user": {
            "wardrobe": [],
            "savedLooks": [],
            "preferredOccasions": ["date"],
        },
    }

    resp = client.post("/v1/assistant/chat", json=body)
    assert resp.status_code == 200
    data = resp.json()

    assert "intent" in data
    assert "text" in data
    assert "cards" in data
    assert "clarifications" in data
    assert "navigation" in data
    assert "outfitIntelligence" in data


def test_11_batch4b1_adapters_remain_unchanged_and_functional():
    """11. Batch 4B.1 ephemeral adapters remain functional and isolated."""
    from app.infrastructure.external.ephemeral_wardrobe import EphemeralWardrobeItemRepository
    from app.infrastructure.external.ephemeral_user_state import EphemeralUserStateRepository
    from app.application.outfits import GenerateOutfit

    guest_items = [
        {"id": "g-top", "name": "Linen Shirt", "category": "tops", "color": "white"},
        {"id": "g-bot", "name": "Chino Shorts", "category": "bottoms", "color": "khaki"},
    ]
    wardrobe_repo = EphemeralWardrobeItemRepository(guest_items)
    user_state_repo = EphemeralUserStateRepository(["casual"])

    generator = GenerateOutfit(
        wardrobe_items=wardrobe_repo,
        user_state=user_state_repo,
    )
    rec, reason = generator.derive_with_reason(
        user_id=uuid.UUID(int=0),
        occasion="casual",
        mood="relaxed",
        fit="regular",
        color_palette="neutral",
    )
    assert reason is None
    assert rec is not None
    assert len(rec.components) == 2
    comp_ids = {c.id for c in rec.components}
    assert comp_ids == {"g-top", "g-bot"}


def test_12_garment_id_and_ownership_preservation(test_setup):
    """12. Real garment UUIDs, ownership, and attributes are preserved."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    captured = test_setup["captured_handles"]

    real_item_uuid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    rec = _make_wardrobe_record(
        real_item_uuid,
        "Cashmere Sweater",
        category="tops",
        color="charcoal",
        material="cashmere",
        is_favorite=True,
        user_id=uid,
    )
    wardrobe_repo.items = [rec]

    body = {
        "messages": [{"role": "user", "content": "show my wardrobe"}],
        "user": None,  # Even when client passes user=None!
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_wardrobe = captured[0]["request"].user.wardrobe
    assert len(effective_wardrobe) == 1
    item = effective_wardrobe[0]
    assert item.id == real_item_uuid
    assert item.name == "Cashmere Sweater"
    assert item.category == "tops"
    assert item.color == "charcoal"
    assert item.material == "cashmere"
    assert item.isFavorite is True


def test_13_pagination_loads_all_pages_for_wardrobe(test_setup):
    """13. Authoritative wardrobe loading iterates all pages for large wardrobes."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    wardrobe_repo = test_setup["wardrobe_repo"]
    captured = test_setup["captured_handles"]

    # 150 items: page 1 = 100, page 2 = 50
    items = [
        _make_wardrobe_record(f"00000000-0000-0000-0000-{k:012d}", f"Item {k}", user_id=uid)
        for k in range(150)
    ]
    wardrobe_repo.items = items

    body = {"messages": [{"role": "user", "content": "show wardrobe"}]}
    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    # Verified 2 pages were queried
    assert len(wardrobe_repo.calls) == 2
    assert wardrobe_repo.calls[0][1]["page"] == 1
    assert wardrobe_repo.calls[1][1]["page"] == 2

    effective_wardrobe = captured[0]["request"].user.wardrobe
    assert len(effective_wardrobe) == 150


def test_14_transient_client_face_preserved_when_server_unmeasured(test_setup):
    """14. Transient client face data is preserved if server style_profile has no measured face data."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    user_state_repo = test_setup["user_state_repo"]
    captured = test_setup["captured_handles"]

    # Server profile has no face shape
    user_state_repo.profile = UserProfileRecord(
        user_id=uid,
        display_name="User",
        style_profile={},
        preferences={},
        settings={},
        flags={},
        version=1,
    )

    body = {
        "messages": [{"role": "user", "content": "best hairstyle"}],
        "user": {
            "wardrobe": [],
            "savedLooks": [],
            "preferredOccasions": [],
            "face": {"faceShape": "oval", "skinTone": "fair"},
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_face = captured[0]["request"].user.face
    assert effective_face is not None
    assert effective_face.faceShape == "oval"
    assert effective_face.skinTone == "fair"


def test_15_server_face_overrides_conflicting_client_face(test_setup):
    """15. Authoritative server appearance overrides conflicting client face attributes."""
    client = test_setup["client"]
    uid = test_setup["user_id"]
    user_state_repo = test_setup["user_state_repo"]
    captured = test_setup["captured_handles"]

    # Server has confirmed rectangular face shape
    user_state_repo.profile = UserProfileRecord(
        user_id=uid,
        display_name="User",
        style_profile={"face_shape": "rectangular", "skin_tone": "medium"},
        preferences={},
        settings={},
        flags={},
        version=1,
    )

    body = {
        "messages": [{"role": "user", "content": "best hairstyle"}],
        "user": {
            "wardrobe": [],
            "savedLooks": [],
            "preferredOccasions": [],
            "face": {"faceShape": "oval", "skinTone": "light"},
        },
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_face = captured[0]["request"].user.face
    assert effective_face.faceShape == "rectangular"
    assert effective_face.skinTone == "medium"


def test_16_saved_looks_error_degrades_safely(test_setup):
    """16. Saved look repository failure degrades safely to empty lists without crashing."""
    client = test_setup["client"]
    saved_look_repo = test_setup["saved_look_repo"]
    saved_look_repo.fail = True
    captured = test_setup["captured_handles"]

    body = {
        "messages": [{"role": "user", "content": "recommend outfit"}],
        "user": None,
    }

    resp = client.post("/v1/assistant/chat", json=body, headers={"Authorization": "Bearer valid-auth-token"})
    assert resp.status_code == 200

    effective_user = captured[0]["request"].user
    assert effective_user.savedLooks == []
    assert captured[0]["kwargs"].get("preferred_item_ids") == []
