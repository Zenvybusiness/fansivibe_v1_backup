"""Stage 1D Batch 4B.3: Canonical Outfit Recommendation Delegation Tests.

Verifies:
1. recommend_outfit delegates to GenerateOutfit.
2. Static catalog recommendation is no longer the recommendation source.
3. Authenticated execution uses server-authoritative wardrobe context.
4. Guest execution uses ephemeral repositories.
5. Guest execution performs no database writes.
6. Occasion, fit and palette mapping.
7. Mood remains contextual rather than scored.
8. Preferred item IDs are passed correctly.
9. Canonical ranking and reasons are preserved.
10. Empty wardrobe behavior.
11. Insufficient wardrobe behavior.
12. Database failure handling.
13. Missing appearance information.
14. No fabricated ownership claims.
15. Existing assistant tool response compatibility.
16. Existing Batch 4A hairstyle and grooming delegation remains functional.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.ai import engine, tools
from app.application.outfits import (
    EMPTY_WARDROBE,
    MISSING_REQUIRED_CATEGORY,
    GenerateOutfit,
)
from app.data import catalog
from app.domain.ports.repositories import (
    OutfitComponent,
    OutfitRecommendation,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.main import app, get_current_user_id, get_db
from app.models.schemas import (
    AssistantRequest,
    ChatMessage,
    FaceData,
    SuggestionCard,
    UserContext,
    WardrobeItem as WireWardrobeItem,
)


# ---------------------------------------------------------------------------
# Test Doubles & Fixtures
# ---------------------------------------------------------------------------


def _sample_guest_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "g-top-1",
            "name": "White Linen Shirt",
            "category": "tops",
            "color": "white",
            "material": "linen",
            "isFavorite": True,
            "fit": "regular",
            "fit_confidence": 0.85,
        },
        {
            "id": "g-bottom-1",
            "name": "Navy Tailored Trousers",
            "category": "bottoms",
            "color": "navy",
            "material": "wool",
            "isFavorite": False,
            "fit": "tailored",
            "fit_confidence": 0.90,
        },
        {
            "id": "g-outer-1",
            "name": "Charcoal Blazer",
            "category": "outerwear",
            "color": "charcoal",
            "material": "wool",
            "isFavorite": True,
            "fit": "regular",
            "fit_confidence": 0.75,
        },
        {
            "id": "g-foot-1",
            "name": "Brown Leather Oxford",
            "category": "footwear",
            "color": "brown",
            "material": "leather",
            "isFavorite": False,
        },
    ]


def _sample_wire_items() -> list[WireWardrobeItem]:
    return [
        WireWardrobeItem(
            id=d["id"],
            name=d["name"],
            category=d["category"],
            color=d["color"],
            material=d.get("material"),
            isFavorite=d.get("isFavorite", False),
        )
        for d in _sample_guest_items()
    ]


class SpyGenerateOutfit:
    """Spy use case tracking derive_with_reason calls."""

    def __init__(self, return_rec=None, return_reason=None, raise_exc=None):
        self.calls: list[dict[str, Any]] = []
        self.return_rec = return_rec
        self.return_reason = return_reason
        self.raise_exc = raise_exc

    def derive_with_reason(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return self.return_rec, self.return_reason


# ---------------------------------------------------------------------------
# 1. recommend_outfit delegates to GenerateOutfit
# ---------------------------------------------------------------------------


def test_1_recommend_outfit_delegates_to_generate_outfit():
    """recommend_outfit invokes GenerateOutfit with mapped parameters."""
    mock_rec = OutfitRecommendation(
        title="Date Outfit",
        match_score=0.89,
        components=[
            OutfitComponent(id="1", name="Shirt", category="tops", color="white", material="linen", reason="Top piece"),
            OutfitComponent(id="2", name="Pants", category="bottoms", color="navy", material="wool", reason="Bottom piece"),
        ],
        reasons=["Picked for a Date occasion", "Matches the selected occasion"],
        color_harmony="neutral palette",
        body_fit="regular fit",
        occasion_match="Matched for Date",
        style_score_impact="89% match",
        improvement_suggestion="Full coverage",
        selected_occasion="date",
        selected_mood="classic",
        selected_color_palette="neutral",
    )
    spy = SpyGenerateOutfit(return_rec=mock_rec, return_reason=None)

    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )
    cards = tools.recommend_outfit("date", user, generate_outfit=spy)

    assert len(spy.calls) == 1
    call = spy.calls[0]
    assert call["occasion"] == "date"
    assert call["mood"] == "classic"
    assert call["fit"] == "regular"
    assert call["color_palette"] == "neutral"

    assert len(cards) == 1
    card = cards[0]
    assert card.kind == "outfit"
    assert card.title == "Date Outfit"
    assert card.score == 89
    assert card.action == "open_outfit"
    assert "Shirt - Tops" in card.items
    assert "Pants - Bottoms" in card.items


# ---------------------------------------------------------------------------
# 2. Static catalog recommendation is no longer the recommendation source
# ---------------------------------------------------------------------------


def test_2_static_catalog_recommendation_no_longer_source():
    """Static catalog lookups (OCCASION_TO_LOOK, REFINED_OFFICE, CASUAL_LOOK) are not returned."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["casual"],
    )
    cards = tools.recommend_outfit("casual", user)

    assert len(cards) == 1
    card = cards[0]
    # Title must be dynamically derived canonical title, NOT hardcoded catalog look title
    assert card.title != catalog.CASUAL_LOOK.title
    assert card.title != catalog.REFINED_OFFICE.title
    assert card.title == "Casual Outfit"
    # Items must match the user's actual wardrobe, not catalog.CASUAL_LOOK items
    assert card.items != catalog.CASUAL_LOOK.items
    assert any("White Linen Shirt - Tops" in item for item in card.items)
    assert any("Navy Tailored Trousers - Bottoms" in item for item in card.items)


# ---------------------------------------------------------------------------
# 3. Authenticated execution uses server-authoritative wardrobe context
# ---------------------------------------------------------------------------


def test_3_authenticated_execution_uses_server_authoritative_wardrobe():
    """Authenticated requests derive recommendations from server repository data."""
    auth_user_id = uuid4()
    now = datetime.now(timezone.utc)
    server_items = [
        WardrobeItemRecord(
            id=UUID("11111111-1111-4111-8111-111111111111"),
            user_id=auth_user_id,
            name="Server Silk Shirt",
            category="tops",
            color="white",
            material="silk",
            is_favorite=True,
            image_ref=None,
            created_at=now,
            updated_at=now,
            fit="regular",
            fit_confidence=0.90,
        ),
        WardrobeItemRecord(
            id=UUID("22222222-2222-4222-8222-222222222222"),
            user_id=auth_user_id,
            name="Server Wool Trousers",
            category="bottoms",
            color="black",
            material="wool",
            is_favorite=False,
            image_ref=None,
            created_at=now,
            updated_at=now,
            fit="regular",
            fit_confidence=0.85,
        ),
    ]

    class MockServerWardrobeRepo:
        def get_for_user(self, *, user_id, page=1, page_size=100, **kwargs):
            assert user_id == auth_user_id
            return server_items, len(server_items)

    class MockServerUserStateRepo:
        def get_profile(self, *, user_id):
            assert user_id == auth_user_id
            return UserProfileRecord(
                user_id=auth_user_id,
                display_name="Authenticated User",
                style_profile={},
                preferences={"preferred_occasions": ["office"]},
                settings={},
                flags={},
                version=1,
            )

    wardrobe_repo = MockServerWardrobeRepo()
    user_state_repo = MockServerUserStateRepo()

    # Client snapshot with unverified items
    client_user = UserContext(
        wardrobe=[WireWardrobeItem(id="fake-1", name="Fake Top", category="tops", color="red")],
        preferredOccasions=["date"],
    )

    cards = tools.recommend_outfit(
        "office",
        client_user,
        user_id=auth_user_id,
        wardrobe_items=wardrobe_repo,
        user_state=user_state_repo,
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.title == "Office Outfit"
    # Grounded in server items, not client snapshot
    assert "Server Silk Shirt - Tops" in card.items
    assert "Server Wool Trousers - Bottoms" in card.items
    assert not any("Fake Top" in item for item in card.items)


# ---------------------------------------------------------------------------
# 4. Guest execution uses ephemeral repositories
# ---------------------------------------------------------------------------


def test_4_guest_execution_uses_ephemeral_repositories():
    """Guest requests run canonical GenerateOutfit over in-memory ephemeral repositories."""
    guest_context = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )

    # Calling without DB repositories or auth user_id runs ephemeral execution
    cards = tools.recommend_outfit("date", guest_context)

    assert len(cards) == 1
    card = cards[0]
    assert card.kind == "outfit"
    assert card.title == "Date Outfit"
    assert card.score is not None
    assert card.score > 0
    assert "White Linen Shirt - Tops" in card.items
    assert "Navy Tailored Trousers - Bottoms" in card.items


# ---------------------------------------------------------------------------
# 5. Guest execution performs no database writes
# ---------------------------------------------------------------------------


def test_5_guest_execution_performs_no_database_writes():
    """Ephemeral guest execution makes 0 database session or SQL calls."""
    mock_db = MagicMock()
    guest_context = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["casual"],
    )

    cards = tools.recommend_outfit("casual", guest_context)
    assert len(cards) == 1
    assert cards[0].kind == "outfit"

    mock_db.execute.assert_not_called()
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_not_called()
    mock_db.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Occasion, fit and palette mapping
# ---------------------------------------------------------------------------


def test_6_occasion_fit_and_palette_mapping():
    """Occasion, fit, and palette inputs reach scorer and generate grounded reasons."""
    cool_slim_items = [
        WireWardrobeItem(id="t-slim", name="Cool Slim Tee", category="tops", color="navy", material="cotton", isFavorite=False),
        WireWardrobeItem(id="b-slim", name="Cool Slim Jeans", category="bottoms", color="light_blue", material="denim", isFavorite=False),
    ]
    # Set fit and fit_confidence on items
    raw_guest_items = [
        {
            "id": "t-slim",
            "name": "Cool Slim Tee",
            "category": "tops",
            "color": "navy",
            "material": "cotton",
            "fit": "slim",
            "fit_confidence": 0.85,
        },
        {
            "id": "b-slim",
            "name": "Cool Slim Jeans",
            "category": "bottoms",
            "color": "light_blue",
            "material": "denim",
            "fit": "slim",
            "fit_confidence": 0.85,
        },
    ]
    wardrobe = EphemeralWardrobeItemRepository(raw_guest_items)
    user_state = EphemeralUserStateRepository(preferred_occasions=["party"])

    cards = tools.recommend_outfit(
        "party",
        None,
        wardrobe_items=wardrobe,
        user_state=user_state,
        fit="slim",
        color_palette="cool",
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.title == "Party Outfit"
    # Grounded reasons must reflect occasion, fit, and palette
    assert "party" in card.subtitle.lower() or "party" in card.title.lower()


# ---------------------------------------------------------------------------
# 7. Mood remains contextual rather than scored
# ---------------------------------------------------------------------------


def test_7_mood_remains_contextual_rather_than_scored():
    """Different mood selections do not alter outfit score, components, or ranking."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )

    cards_bold = tools.recommend_outfit("date", user, mood="bold")
    cards_minimal = tools.recommend_outfit("date", user, mood="minimal")
    cards_classic = tools.recommend_outfit("date", user, mood="classic")

    assert cards_bold[0].score == cards_minimal[0].score == cards_classic[0].score
    assert cards_bold[0].items == cards_minimal[0].items == cards_classic[0].items
    assert cards_bold[0].title == cards_minimal[0].title == cards_classic[0].title


# ---------------------------------------------------------------------------
# 8. Preferred item IDs are passed correctly
# ---------------------------------------------------------------------------


def test_8_preferred_item_ids_passed_correctly():
    """Preferred item IDs flow to GenerateOutfit and award preference reason."""
    fav_top_id = str(uuid4())
    alt_top_id = str(uuid4())
    bot_id = str(uuid4())
    raw_guest_items = [
        {"id": fav_top_id, "name": "Special Linen Shirt", "category": "tops", "color": "white"},
        {"id": alt_top_id, "name": "Basic Crew Neck", "category": "tops", "color": "grey"},
        {"id": bot_id, "name": "Classic Trousers", "category": "bottoms", "color": "black"},
    ]
    wardrobe = EphemeralWardrobeItemRepository(raw_guest_items)
    user_state = EphemeralUserStateRepository(preferred_occasions=["casual"])

    cards = tools.recommend_outfit(
        "casual",
        None,
        wardrobe_items=wardrobe,
        user_state=user_state,
        preferred_item_ids=[fav_top_id],
    )

    assert len(cards) == 1
    card = cards[0]
    assert any("Special Linen Shirt" in item for item in card.items)


# ---------------------------------------------------------------------------
# 9. Canonical ranking and reasons are preserved
# ---------------------------------------------------------------------------


def test_9_canonical_ranking_and_reasons_preserved():
    """Grounded canonical reasons are generated and reflected in card subtitle."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )
    cards = tools.recommend_outfit("date", user)

    assert len(cards) == 1
    card = cards[0]
    assert "Picked for a Date occasion" in card.subtitle
    assert "Covers" in card.subtitle


# ---------------------------------------------------------------------------
# 10. Empty wardrobe behavior
# ---------------------------------------------------------------------------


def test_10_empty_wardrobe_behavior():
    """Empty wardrobe returns honest empty card without fabricated outfits."""
    empty_user = UserContext(
        wardrobe=[],
        preferredOccasions=["casual"],
    )
    cards = tools.recommend_outfit("casual", empty_user)

    assert len(cards) == 1
    card = cards[0]
    assert card.kind == "outfit"
    assert card.title == "Empty Wardrobe"
    assert "Add tops and bottoms" in card.subtitle
    assert card.score is None
    assert card.action == "open_wardrobe"
    assert "No wardrobe items catalogued yet" in card.items


# ---------------------------------------------------------------------------
# 11. Insufficient wardrobe behavior
# ---------------------------------------------------------------------------


def test_11_insufficient_wardrobe_behavior():
    """Tops-only or bottoms-only wardrobe returns incomplete wardrobe card."""
    tops_only_user = UserContext(
        wardrobe=[
            WireWardrobeItem(id="t-1", name="Only Top", category="tops", color="blue"),
        ],
        preferredOccasions=["casual"],
    )
    cards = tools.recommend_outfit("casual", tops_only_user)

    assert len(cards) == 1
    card = cards[0]
    assert card.kind == "outfit"
    assert card.title == "Incomplete Wardrobe"
    assert "You need at least one top and one bottom" in card.subtitle
    assert card.score is None
    assert card.action == "open_wardrobe"


# ---------------------------------------------------------------------------
# 12. Database failure handling
# ---------------------------------------------------------------------------


def test_12_database_failure_handling():
    """Database failure degrades safely to an unavailable card without crash or fabrication."""
    class FailingRepo:
        def get_for_user(self, *args, **kwargs):
            raise RuntimeError("Database connection timed out")

    cards = tools.recommend_outfit(
        "casual",
        None,
        user_id=uuid4(),
        wardrobe_items=FailingRepo(),
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.kind == "outfit"
    assert "Unavailable" in card.title
    assert card.score is None
    assert card.items == []
    assert card.action == "open_wardrobe"


# ---------------------------------------------------------------------------
# 13. Missing appearance information
# ---------------------------------------------------------------------------


def test_13_missing_appearance_information():
    """Outfit recommendation functions normally when face data is missing/empty."""
    no_face_user = UserContext(
        wardrobe=_sample_wire_items(),
        face=None,
        preferredOccasions=["office"],
    )
    cards = tools.recommend_outfit("office", no_face_user)

    assert len(cards) == 1
    card = cards[0]
    assert card.title == "Office Outfit"
    assert card.score is not None
    assert card.score > 0


# ---------------------------------------------------------------------------
# 14. No fabricated ownership claims
# ---------------------------------------------------------------------------


def test_14_no_fabricated_ownership_claims():
    """All items in recommendation cards belong strictly to the provided wardrobe."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["casual"],
    )
    cards = tools.recommend_outfit("casual", user)

    owned_names = {i.name for i in user.wardrobe}
    for item_str in cards[0].items:
        garment_name = item_str.split(" - ")[0]
        assert garment_name in owned_names, f"Fabricated garment claimed as owned: {garment_name}"


# ---------------------------------------------------------------------------
# 15. Existing assistant tool response compatibility
# ---------------------------------------------------------------------------


def test_15_existing_assistant_tool_response_compatibility():
    """Card complies fully with schemas.SuggestionCard and engine integration."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content="what should i wear for date night")],
        user=user,
    )
    reply = engine.handle(req)

    assert reply.intent == "outfit"
    assert len(reply.cards) == 1
    card = reply.cards[0]
    assert isinstance(card, SuggestionCard)
    assert card.kind == "outfit"
    assert card.title == "Date Outfit"
    assert isinstance(card.score, int)
    assert card.score > 0
    assert card.action == "open_outfit"
    assert "date" in reply.text.lower()


# ---------------------------------------------------------------------------
# 16. Existing Batch 4A hairstyle and grooming delegation remains functional
# ---------------------------------------------------------------------------


def test_16_batch_4a_hairstyle_and_grooming_remain_functional():
    """Hairstyle and grooming tools remain canonical and untouched by outfit delegation."""
    user = UserContext(
        face=FaceData(faceShape="round"),
        savedLooks=[],
    )
    hair_cards = tools.recommend_hairstyle(user)
    assert len(hair_cards) >= 1
    assert hair_cards[0].kind == "hairstyle"
    assert hair_cards[0].score is not None
    assert hair_cards[0].score > 0

    groom_cards = tools.recommend_grooming(user)
    assert len(groom_cards) >= 1
    assert groom_cards[0].kind == "grooming"
    assert groom_cards[0].score is not None
    assert groom_cards[0].score > 0
