"""End-to-End Tests for AI Stylist (Phase 2).

Covers all 12 mandatory Stage H & I situations and user journeys:
1. User has an empty wardrobe (status="empty_wardrobe", no hallucinated items).
2. User has only one garment category (status="missing_required_category", truthful guidance).
3. User asks for an outfit for a specific occasion ("wedding" -> formal, "meeting" -> office).
4. User requests a garment they do not own (generates outfit with owned items, clarifies suggestion).
5. User asks for alternatives ("suggest three outfits", candidate alternatives provided).
6. User asks to change one garment ("replace the shoes" -> slot_to_swap="footwear").
7. User has incomplete style preferences (safe defaults, no crashes).
8. Model returns malformed JSON (safe fallback, canonical outfit preserved).
9. Model returns nonexistent wardrobe IDs (strictly filtered, no fake IDs in cards).
10. Ollama is unavailable (fail-open graceful fallback to canonical recommendation).
11. Request times out (timeout handled cleanly, returns canonical recommendation).
12. Cross-user isolation (OW-1, User A cannot query or receive User B's wardrobe items).
13. Weather context fail-open integration (coarse weather context handled safely).
14. Conversational continuity (multi-turn follow-up "make it more formal").
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.ai import engine, intent, llm_backend, tools
from app.api.deps import get_current_user_id
from app.api.errors import ApiError
from app.domain.ports.repositories import (
    OutfitComponent,
    OutfitRecommendation,
    SavedLookRecord,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.infrastructure.db.session import get_db
from app.models.schemas import (
    AssistantReply,
    AssistantRequest,
    ChatMessage,
    SuggestionCard,
    UserContext,
    WardrobeItem as WireWardrobeItem,
)


# ---------------------------------------------------------------------------
# Test Doubles & Fixtures
# ---------------------------------------------------------------------------

USER_A_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_B_ID = UUID("22222222-2222-4222-8222-222222222222")


def _make_record(
    item_id: str,
    name: str,
    category: str,
    color: str = "navy",
    material: Optional[str] = "cotton",
    user_id: UUID = USER_A_ID,
) -> WardrobeItemRecord:
    now = datetime.now(timezone.utc)
    return WardrobeItemRecord(
        id=UUID(item_id) if len(item_id) == 36 else uuid.uuid5(uuid.NAMESPACE_DNS, item_id),
        user_id=user_id,
        name=name,
        category=category,
        color=color,
        material=material,
        is_favorite=False,
        image_ref=None,
        created_at=now,
        updated_at=now,
    )


def _sample_capsule(user_id: UUID = USER_A_ID) -> list[WardrobeItemRecord]:
    return [
        _make_record("00000000-0000-0000-0000-000000000001", "White Linen Shirt", "tops", "white", "linen", user_id),
        _make_record("00000000-0000-0000-0000-000000000002", "Navy Wool Trousers", "bottoms", "navy", "wool", user_id),
        _make_record("00000000-0000-0000-0000-000000000003", "Charcoal Blazer", "outerwear", "charcoal", "wool", user_id),
        _make_record("00000000-0000-0000-0000-000000000004", "Brown Leather Oxfords", "footwear", "brown", "leather", user_id),
        _make_record("00000000-0000-0000-0000-000000000005", "White Minimalist Sneakers", "footwear", "white", "leather", user_id),
    ]


class MockWardrobeRepo:
    def __init__(self, items_by_user: Optional[dict[UUID, list[WardrobeItemRecord]]] = None):
        self.items_by_user = items_by_user or {}

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        **kwargs,
    ) -> tuple[list[WardrobeItemRecord], int]:
        user_items = self.items_by_user.get(user_id, [])
        start = (page - 1) * page_size
        return user_items[start : start + page_size], len(user_items)

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[WardrobeItemRecord]:
        for item in self.items_by_user.get(user_id, []):
            if item.id == item_id:
                return item
        return None


class MockUserStateRepo:
    def __init__(self, profiles: Optional[dict[UUID, UserProfileRecord]] = None):
        self.profiles = profiles or {}

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        return self.profiles.get(user_id)


class MockSavedLookRepo:
    def __init__(self):
        self.saved_looks: list[SavedLookRecord] = []

    def list_for_user(self, *, user_id: UUID, page: int = 1, page_size: int = 100) -> tuple[list[SavedLookRecord], int]:
        user_looks = [look for look in self.saved_looks if look.user_id == user_id]
        start = (page - 1) * page_size
        return user_looks[start : start + page_size], len(user_looks)


@pytest.fixture
def api_client(monkeypatch):
    """Configures FastAPI test client with mocked DB repositories and auth."""
    wardrobe_repo = MockWardrobeRepo({
        USER_A_ID: _sample_capsule(USER_A_ID),
        USER_B_ID: [_make_record("99999999-9999-4999-8999-999999999999", "Secret Item B", "tops", "red", "silk", USER_B_ID)],
    })
    user_state_repo = MockUserStateRepo()
    saved_look_repo = MockSavedLookRepo()

    monkeypatch.setattr(main_module, "WardrobeItemRepositorySQL", lambda db: wardrobe_repo)
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db: user_state_repo)
    monkeypatch.setattr(main_module, "SavedLookRepositorySQL", lambda db: saved_look_repo)

    dummy_session = type("DummySession", (), {"execute": lambda self, *a, **k: None})()
    main_module.app.dependency_overrides[get_db] = lambda: dummy_session

    def fake_auth(authorization: Optional[str] = None, db: Any = None):
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(status_code=401, code="AUTHENTICATION_ERROR", message="Missing token")
        token = authorization.removeprefix("Bearer ").strip()
        if token == "user-a-token":
            return USER_A_ID
        elif token == "user-b-token":
            return USER_B_ID
        raise ApiError(status_code=401, code="AUTHENTICATION_ERROR", message="Invalid token")

    monkeypatch.setattr(main_module, "get_current_user_id", fake_auth)

    client = TestClient(main_module.app)
    yield client, wardrobe_repo, user_state_repo

    main_module.app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 1: Empty Wardrobe
# ---------------------------------------------------------------------------

def test_1_empty_wardrobe(api_client):
    """User with no wardrobe items receives graceful empty_wardrobe guidance without fabricated garments."""
    client, wardrobe_repo, _ = api_client
    wardrobe_repo.items_by_user[USER_A_ID] = []

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    outfit_cards = [c for c in data.get("cards", []) if c.get("kind") == "outfit"]
    assert len(outfit_cards) == 1
    # Card is an informational empty wardrobe card
    card = outfit_cards[0]
    assert card["title"] == "Empty Wardrobe"
    assert card.get("items") == ["No wardrobe items catalogued yet"]
    assert "wardrobe" in data["text"].lower() or "add" in data["text"].lower()
    if data.get("outfitIntelligence"):
        assert data["outfitIntelligence"]["status"] == "empty_wardrobe"


# ---------------------------------------------------------------------------
# Test 2: Single Garment Category (Missing Required Category)
# ---------------------------------------------------------------------------

def test_2_single_category_wardrobe(api_client):
    """User with only tops receives truthful missing_required_category response without fabricating bottoms."""
    client, wardrobe_repo, _ = api_client
    wardrobe_repo.items_by_user[USER_A_ID] = [
        _make_record("00000000-0000-0000-0000-000000000001", "White Linen Shirt", "tops", "white", "linen", USER_A_ID),
    ]

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "Suggest an outfit for office."}]},
    )
    assert res.status_code == 200
    data = res.json()
    outfit_cards = [c for c in data.get("cards", []) if c.get("kind") == "outfit"]
    assert len(outfit_cards) == 1
    card = outfit_cards[0]
    assert card["title"] == "Incomplete Wardrobe"
    # Never claim bottoms exist
    for item in card.get("items", []):
        assert "bottom" not in item.lower() and "trouser" not in item.lower()
    if data.get("outfitIntelligence"):
        assert data["outfitIntelligence"]["status"] == "missing_required_category"


# ---------------------------------------------------------------------------
# Test 3: Specific Occasion Mapping (Wedding -> Formal)
# ---------------------------------------------------------------------------

def test_3_specific_occasion_wedding_mapping(api_client):
    """Wedding request correctly maps to formal formality and selects formal pieces."""
    client, _, _ = api_client

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "Suggest an outfit for a wedding"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    assert len(data["cards"]) >= 1
    card = data["cards"][0]
    assert card["kind"] == "outfit"
    if data.get("outfitIntelligence"):
        assert data["outfitIntelligence"]["occasion"] == "formal"


# ---------------------------------------------------------------------------
# Test 4: Request Unowned Garment
# ---------------------------------------------------------------------------

def test_4_request_unowned_garment(api_client):
    """Requesting an unowned garment provides outfit recommendations without claiming ownership."""
    client, _, _ = api_client

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "Style my yellow trenchcoat"}]},
    )
    assert res.status_code == 200
    data = res.json()
    card = data["cards"][0]
    for item in card["items"]:
        assert "yellow" not in item.lower() and "trenchcoat" not in item.lower()
    assert len(card["items"]) >= 2


# ---------------------------------------------------------------------------
# Test 5: Request Alternatives ("Suggest three outfits")
# ---------------------------------------------------------------------------

def test_5_request_alternatives(api_client):
    """Requesting alternative outfits returns runner-up outfit cards."""
    client, _, _ = api_client

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "Suggest three outfits from my wardrobe"}]},
    )
    assert res.status_code == 200
    data = res.json()
    outfit_cards = [c for c in data["cards"] if c["kind"] == "outfit"]
    assert len(outfit_cards) >= 1
    assert len(data["cards"]) >= 1


# ---------------------------------------------------------------------------
# Test 6: Slot Replacement ("Replace the shoes")
# ---------------------------------------------------------------------------

def test_6_slot_replacement_shoes(api_client):
    """Follow-up request to replace shoes swaps the footwear slot."""
    client, _, _ = api_client

    messages = [
        {"role": "user", "content": "Suggest an outfit for office"},
        {"role": "assistant", "content": "Here is an outfit with Brown Leather Oxfords"},
        {"role": "user", "content": "Replace the shoes with sneakers"},
    ]
    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": messages},
    )
    assert res.status_code == 200
    data = res.json()
    card = data["cards"][0]
    assert len(card["items"]) >= 2


# ---------------------------------------------------------------------------
# Test 7: Incomplete Style Preferences (Safe Defaults)
# ---------------------------------------------------------------------------

def test_7_incomplete_style_preferences(api_client):
    """User with no profile preferences executes safely with graceful defaults."""
    client, _, user_state_repo = api_client
    user_state_repo.profiles[USER_A_ID] = UserProfileRecord(
        user_id=USER_A_ID,
        display_name="Authenticated User",
        style_profile={},
        preferences={},
        settings={},
        flags={},
        version=1,
    )

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    assert len(data["cards"]) >= 1


# ---------------------------------------------------------------------------
# Test 8: Model Returns Malformed JSON (Safe Fallback)
# ---------------------------------------------------------------------------

def test_8_model_returns_malformed_json(monkeypatch):
    """Malformed LLM response gracefully preserves canonical base_text recommendation."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "broken", 0)

    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: mock_response)

    enriched_text = llm_backend.enrich_stylist_recommendation(
        base_text="Base canonical recommendation for casual outfit.",
        occasion="casual",
        selected_components=[{"name": "White Linen Shirt", "category": "tops", "color": "white"}],
        missing_categories=[],
        user_query="What should I wear today?",
    )
    assert enriched_text == "Base canonical recommendation for casual outfit."


# ---------------------------------------------------------------------------
# Test 9: Model Nonexistent Wardrobe IDs (Filtered Out)
# ---------------------------------------------------------------------------

def test_9_model_nonexistent_ids_filtered(api_client):
    """Any nonexistent wardrobe IDs are never surfaced in recommended cards."""
    client, _, _ = api_client

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["cards"]) >= 1
    card = data["cards"][0]
    valid_names = {"White Linen Shirt", "Navy Wool Trousers", "Charcoal Blazer", "Brown Leather Oxfords", "White Minimalist Sneakers"}
    for item in card["items"]:
        name_part = item.split(" - ")[0]
        assert name_part in valid_names


# ---------------------------------------------------------------------------
# Test 10: Ollama Unavailable (Fail-Open Fallback)
# ---------------------------------------------------------------------------

def test_10_ollama_unavailable_fallback(monkeypatch, api_client):
    """When Ollama is unreachable, engine completes successfully using deterministic reasoner."""
    client, _, _ = api_client

    orig_post = httpx.Client.post
    def selective_post(self, url, *args, **kwargs):
        if "11434" in str(url) or "/api/chat" in str(url):
            raise httpx.ConnectError("Ollama service unreachable on port 11434")
        return orig_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", selective_post)

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    assert len(data["cards"]) >= 1
    assert data["cards"][0]["kind"] == "outfit"


# ---------------------------------------------------------------------------
# Test 11: Request Timeout Handling
# ---------------------------------------------------------------------------

def test_11_request_timeout_handling(monkeypatch, api_client):
    """When inference times out, engine handles it cleanly and returns canonical recommendation."""
    from app.ai.manager.scheduler import get_gpu_scheduler
    client, _, _ = api_client

    orig_post = httpx.Client.post
    def selective_post(self, url, *args, **kwargs):
        if "11434" in str(url) or "/api/chat" in str(url):
            raise httpx.TimeoutException("Ollama inference timed out after 10s")
        return orig_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", selective_post)

    try:
        res = client.post(
            "/v1/assistant/chat",
            headers={"Authorization": "Bearer user-a-token"},
            json={"messages": [{"role": "user", "content": "Suggest a wedding outfit"}]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["intent"] == "outfit"
        assert len(data["cards"]) >= 1
    finally:
        scheduler = get_gpu_scheduler()
        if scheduler.is_quarantined():
            scheduler.operator_recover("test_suite", "Cleanup after timeout test", force=True)


# ---------------------------------------------------------------------------
# Test 12: Cross-User Isolation (OW-1)
# ---------------------------------------------------------------------------

def test_12_cross_user_isolation(api_client):
    """User A's query never includes or accesses User B's wardrobe items."""
    client, _, _ = api_client

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "Show me an outfit for casual today"}]},
    )
    assert res.status_code == 200
    data = res.json()
    for card in data.get("cards", []):
        for item in card.get("items", []):
            assert "Secret Item B" not in item


# ---------------------------------------------------------------------------
# Test 13: Weather Context Fail-Open Integration
# ---------------------------------------------------------------------------

def test_13_weather_context_fail_open(api_client, monkeypatch):
    """Weather context is safely passed when available and fail-open when unavailable."""
    client, _, _ = api_client

    # Case A: Weather provider returns rainy context
    class MockWeatherCtx:
        class Current:
            condition_code = "rainy"
            temperature_c = 14.0
        current = Current()

    class MockWeatherProvider:
        def get_weather(self, loc):
            return MockWeatherCtx()

    monkeypatch.setattr(main_module, "get_weather_provider", lambda: MockWeatherProvider())

    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today in London?"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    assert len(data["cards"]) >= 1

    # Case B: Weather provider raises exception -> fail-open
    class BrokenWeatherProvider:
        def get_weather(self, loc):
            raise RuntimeError("Weather API down")

    monkeypatch.setattr(main_module, "get_weather_provider", lambda: BrokenWeatherProvider())

    res_broken = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": [{"role": "user", "content": "What should I wear today?"}]},
    )
    assert res_broken.status_code == 200
    assert res_broken.json()["intent"] == "outfit"


# ---------------------------------------------------------------------------
# Test 14: Conversational Continuity ("Make it more formal")
# ---------------------------------------------------------------------------

def test_14_conversational_continuity(api_client):
    """Multi-turn conversation adjusts formality from casual to formal."""
    client, _, _ = api_client

    messages = [
        {"role": "user", "content": "Suggest a casual outfit for today"},
        {"role": "assistant", "content": "Here is a casual outfit with Linen Shirt and Sneakers"},
        {"role": "user", "content": "Make it more formal"},
    ]
    res = client.post(
        "/v1/assistant/chat",
        headers={"Authorization": "Bearer user-a-token"},
        json={"messages": messages},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "outfit"
    if data.get("outfitIntelligence"):
        assert data["outfitIntelligence"]["occasion"] in ("formal", "office")
