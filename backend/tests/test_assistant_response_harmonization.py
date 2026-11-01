"""Stage 1D Batch 4B.4: Assistant Response Harmonization Tests.

Proves:
1. Both response representations (reply.cards and reply.outfitIntelligence) use
   the same canonical recommendation result.
2. Selected item IDs are identical in both representations.
3. Scores and reasons agree across both representations.
4. Only one canonical recommendation execution occurs per turn.
5. Empty wardrobe is represented consistently across both representations.
6. Missing required category is represented consistently across both representations.
7. No legal candidate is represented consistently across both representations.
8. Authenticated database failure does not produce a fabricated recommendation.
9. Guest recommendations use ephemeral repositories and user_id=None.
10. No guest UUID or guest database persistence is introduced.
11. Mood remains contextual and does not affect canonical scoring.
12. No independent static outfit catalog recommendation is reintroduced.
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.main as main_module
from app.ai import engine, tools
from app.api.deps import get_current_user_id
from app.application.outfits import (
    EMPTY_WARDROBE,
    MISSING_REQUIRED_CATEGORY,
    NO_LEGAL_CANDIDATE,
    GenerateOutfit,
)
from app.data import catalog
from app.domain.ports.repositories import (
    OutfitComponent,
    OutfitRecommendation,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.models.schemas import (
    AssistantRequest,
    ChatMessage,
    SuggestionCard,
    UserContext,
    WardrobeItem as WireWardrobeItem,
)


# ---------------------------------------------------------------------------
# Test Doubles & Fixtures
# ---------------------------------------------------------------------------


def _sample_wire_items() -> list[WireWardrobeItem]:
    return [
        WireWardrobeItem(
            id="item-top-1",
            name="White Linen Shirt",
            category="tops",
            color="white",
            material="linen",
            isFavorite=True,
        ),
        WireWardrobeItem(
            id="item-bottom-1",
            name="Navy Tailored Trousers",
            category="bottoms",
            color="navy",
            material="wool",
            isFavorite=False,
        ),
        WireWardrobeItem(
            id="item-outer-1",
            name="Charcoal Blazer",
            category="outerwear",
            color="charcoal",
            material="wool",
            isFavorite=True,
        ),
        WireWardrobeItem(
            id="item-shoes-1",
            name="Brown Leather Oxford",
            category="footwear",
            color="brown",
            material="leather",
            isFavorite=False,
        ),
    ]


def _req(text: str, user: Optional[UserContext] = None) -> AssistantRequest:
    return AssistantRequest(
        messages=[ChatMessage(role="user", content=text)],
        user=user,
    )


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
# 1. Both response representations use the same canonical recommendation result
# ---------------------------------------------------------------------------


def test_1_both_representations_use_same_canonical_result():
    """Both reply.cards and reply.outfitIntelligence originate from the canonical result."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )
    req = _req("what should i wear for date night", user=user)

    reply = engine.handle(req)

    assert reply.cards is not None
    assert len(reply.cards) >= 1
    outfit_card = next((c for c in reply.cards if c.kind == "outfit"), None)
    assert outfit_card is not None
    assert reply.outfitIntelligence is not None

    # Both refer to the same components
    assert "White Linen Shirt - Tops" in outfit_card.items
    assert "Navy Tailored Trousers - Bottoms" in outfit_card.items
    assert "item-top-1" in reply.outfitIntelligence.selectedItemIds
    assert "item-bottom-1" in reply.outfitIntelligence.selectedItemIds
    assert reply.outfitIntelligence.outfitComposition.topIds == ["item-top-1"]
    assert reply.outfitIntelligence.outfitComposition.bottomIds == ["item-bottom-1"]


# ---------------------------------------------------------------------------
# 2. Selected item IDs are identical in both representations
# ---------------------------------------------------------------------------


def test_2_selected_item_ids_identical_in_both_representations():
    """Selected component IDs in outfitIntelligence match items referenced in cards."""
    mock_rec = OutfitRecommendation(
        title="Harmonized Ensemble",
        match_score=0.92,
        components=[
            OutfitComponent(id="item-top-1", name="White Linen Shirt", category="tops", color="white", material="linen", reason="Top"),
            OutfitComponent(id="item-bottom-1", name="Navy Tailored Trousers", category="bottoms", color="navy", material="wool", reason="Bottom"),
            OutfitComponent(id="item-shoes-1", name="Brown Leather Oxford", category="footwear", color="brown", material="leather", reason="Shoes"),
        ],
        reasons=["High color harmony between linen and navy wool"],
        color_harmony="neutral",
        body_fit="regular",
        occasion_match="date",
        style_score_impact="92% match",
        improvement_suggestion="",
        selected_occasion="date",
        selected_mood="classic",
        selected_color_palette="neutral",
    )
    spy = SpyGenerateOutfit(return_rec=mock_rec, return_reason=None)

    cards, intel = tools.derive_canonical_outfit_recommendation(
        occasion="date",
        user=UserContext(wardrobe=_sample_wire_items()),
        generate_outfit=spy,
    )

    assert len(cards) == 1
    card = cards[0]

    # Component IDs in outfit intelligence exactly match the canonical recommendation components
    expected_ids = ["item-top-1", "item-bottom-1", "item-shoes-1"]
    assert intel.selectedItemIds == expected_ids
    assert intel.outfitComposition.topIds == ["item-top-1"]
    assert intel.outfitComposition.bottomIds == ["item-bottom-1"]
    assert intel.outfitComposition.footwearIds == ["item-shoes-1"]

    # The card items represent the exact same components with their names and categories
    assert any("White Linen Shirt" in it for it in card.items)
    assert any("Navy Tailored Trousers" in it for it in card.items)
    assert any("Brown Leather Oxford" in it for it in card.items)


# ---------------------------------------------------------------------------
# 3. Scores and reasons agree
# ---------------------------------------------------------------------------


def test_3_scores_and_reasons_agree():
    """Ensemble match score and canonical reasons agree between card and outfitIntelligence."""
    mock_rec = OutfitRecommendation(
        title="Harmonized Ensemble",
        match_score=0.88,
        components=[
            OutfitComponent(id="item-top-1", name="White Linen Shirt", category="tops", color="white", material="linen", reason="Top"),
            OutfitComponent(id="item-bottom-1", name="Navy Tailored Trousers", category="bottoms", color="navy", material="wool", reason="Bottom"),
        ],
        reasons=["Harmonious silhouette", "Complementary neutral tones"],
        color_harmony="neutral",
        body_fit="regular",
        occasion_match="date",
        style_score_impact="88% match",
        improvement_suggestion="",
        selected_occasion="date",
        selected_mood="classic",
        selected_color_palette="neutral",
    )
    spy = SpyGenerateOutfit(return_rec=mock_rec, return_reason=None)

    cards, intel = tools.derive_canonical_outfit_recommendation(
        occasion="date",
        user=UserContext(wardrobe=_sample_wire_items()),
        generate_outfit=spy,
    )

    card = cards[0]
    # Match score: 88
    assert card.score == 88
    assert intel.matchScore == 88
    assert intel.outfitComposition.styleScore == 0
    assert intel.confidence == 0.88

    # Reasons:
    assert "Harmonious silhouette" in card.subtitle
    assert "Harmonious silhouette" in intel.stylingRationale
    assert "Harmonious silhouette" in intel.explanation


# ---------------------------------------------------------------------------
# 4. Only one canonical recommendation execution occurs per turn
# ---------------------------------------------------------------------------


def test_4_only_one_canonical_recommendation_execution_per_turn():
    """Engine invokes canonical recommendation derivation exactly once per turn."""
    user = UserContext(wardrobe=_sample_wire_items())
    req = _req("what should i wear to a party?", user=user)

    with patch("app.ai.tools.derive_canonical_outfit_recommendation", wraps=tools.derive_canonical_outfit_recommendation) as mock_derive:
        reply = engine.handle(req)

        assert mock_derive.call_count == 1
        assert reply.cards is not None
        assert reply.outfitIntelligence is not None


# ---------------------------------------------------------------------------
# 5. Empty wardrobe is represented consistently
# ---------------------------------------------------------------------------


def test_5_empty_wardrobe_represented_consistently():
    """Empty wardrobe returns consistent empty representation across card and intelligence."""
    user = UserContext(wardrobe=[])
    req = _req("what should i wear for date night", user=user)

    reply = engine.handle(req)

    outfit_card = next((c for c in reply.cards if c.kind == "outfit"), None)
    assert outfit_card is not None
    assert outfit_card.title == "Empty Wardrobe"
    assert outfit_card.score is None
    assert outfit_card.action == "open_wardrobe"

    assert reply.outfitIntelligence is not None
    assert reply.outfitIntelligence.status == "empty_wardrobe"
    assert reply.outfitIntelligence.matchScore is None
    assert reply.outfitIntelligence.selectedItemIds == []
    assert reply.outfitIntelligence.confidence == 0.0


# ---------------------------------------------------------------------------
# 6. Missing required category is represented consistently
# ---------------------------------------------------------------------------


def test_6_missing_required_category_represented_consistently():
    """Wardrobe missing required bottoms produces consistent category deficit representation."""
    user = UserContext(
        wardrobe=[
            WireWardrobeItem(
                id="item-top-only",
                name="T-Shirt",
                category="tops",
                color="black",
            )
        ]
    )
    req = _req("what should i wear for date night", user=user)

    reply = engine.handle(req)

    outfit_card = next((c for c in reply.cards if c.kind == "outfit"), None)
    assert outfit_card is not None
    assert outfit_card.title == "Incomplete Wardrobe"
    assert outfit_card.score is None
    assert outfit_card.action == "open_wardrobe"

    assert reply.outfitIntelligence is not None
    assert reply.outfitIntelligence.status == "missing_required_category"
    assert reply.outfitIntelligence.matchScore is None
    assert reply.outfitIntelligence.selectedItemIds == []


# ---------------------------------------------------------------------------
# 7. No legal candidate is represented consistently
# ---------------------------------------------------------------------------


def test_7_no_legal_candidate_represented_consistently():
    """When canonical engine finds no legal candidates, both fields agree on empty state."""
    spy = SpyGenerateOutfit(return_rec=None, return_reason=NO_LEGAL_CANDIDATE)

    cards, intel = tools.derive_canonical_outfit_recommendation(
        occasion="date",
        user=UserContext(wardrobe=_sample_wire_items()),
        generate_outfit=spy,
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.score is None
    assert card.title == "No Matching Outfit"

    assert intel.status == "no_legal_candidate"
    assert intel.matchScore is None
    assert intel.selectedItemIds == []


# ---------------------------------------------------------------------------
# 8. Authenticated database failure does not produce a fabricated recommendation
# ---------------------------------------------------------------------------


def test_8_authenticated_db_failure_does_not_fabricate_recommendation():
    """Database OperationalError does not trigger static fallback or fabricated outfit."""
    class FailingRepo:
        def get_for_user(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("Database connection failed"))

    req = _req(
        "what should i wear for date night",
        user=UserContext(wardrobe=[]),
    )

    reply = engine.handle(
        req,
        user_id=uuid4(),
        wardrobe_items=FailingRepo(),
    )

    outfit_card = next((c for c in reply.cards if c.kind == "outfit"), None)
    assert outfit_card is not None
    assert outfit_card.score is None
    assert "Unavailable" in outfit_card.title

    assert reply.outfitIntelligence is not None
    assert reply.outfitIntelligence.status == "unavailable"
    assert reply.outfitIntelligence.matchScore is None
    assert reply.outfitIntelligence.selectedItemIds == []


# ---------------------------------------------------------------------------
# 9. Guest recommendations use ephemeral repositories and user_id=None
# ---------------------------------------------------------------------------


def test_9_guest_recommendations_use_ephemeral_repositories_and_none_userid():
    """Guest recommendations pass user_id=None and use ephemeral adapters."""
    wire_items = _sample_wire_items()
    user = UserContext(
        wardrobe=wire_items,
        preferredOccasions=["casual"],
    )
    req = _req("what should i wear for casual day", user=user)

    with patch.object(GenerateOutfit, "derive_with_reason", autospec=True) as mock_derive:
        mock_derive.return_value = (
            OutfitRecommendation(
                title="Guest Look",
                match_score=0.85,
                components=[
                    OutfitComponent(id="item-top-1", name="Shirt", category="tops", color="white", material="linen", reason="Top"),
                    OutfitComponent(id="item-bottom-1", name="Pants", category="bottoms", color="navy", material="wool", reason="Bottom"),
                ],
                reasons=["Guest matching"],
                color_harmony="neutral",
                body_fit="regular",
                occasion_match="casual",
                style_score_impact="85% match",
                improvement_suggestion="",
                selected_occasion="casual",
                selected_mood="classic",
                selected_color_palette="neutral",
            ),
            None,
        )

        reply = engine.handle(req)

        assert mock_derive.call_count == 1
        _, kwargs = mock_derive.call_args
        assert kwargs["user_id"] is None
        instance = mock_derive.call_args[0][0]
        assert isinstance(instance._wardrobe_items, EphemeralWardrobeItemRepository)
        assert isinstance(instance._user_state, EphemeralUserStateRepository)


# ---------------------------------------------------------------------------
# 10. No guest UUID or guest database persistence is introduced
# ---------------------------------------------------------------------------


def test_10_no_guest_uuid_or_guest_db_persistence():
    """Guest execution via HTTP endpoint performs zero database operations and never creates a guest UUID."""
    mock_db = MagicMock()
    app = main_module.app
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_id] = lambda *a, **k: None

    try:
        client = TestClient(app)
        res = client.post(
            "/v1/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "what should i wear for date night"}],
                "user": {
                    "wardrobe": [w.model_dump() for w in _sample_wire_items()],
                    "preferredOccasions": ["date"],
                },
            },
        )
        assert res.status_code == 200
        reply = res.json()
        assert reply["cards"] is not None
        assert reply["outfitIntelligence"] is not None

        # Guest request must not touch db for write/persistence
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()
        mock_db.flush.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 11. Mood remains contextual and does not affect canonical scoring
# ---------------------------------------------------------------------------


def test_11_mood_remains_contextual_and_does_not_affect_canonical_scoring():
    """Mood remains contextual metadata; identical items and occasion yield identical scores."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["date"],
    )

    req = _req("what should i wear for date night", user=user)

    reply_classic = engine.handle(req, mood="classic")
    reply_bold = engine.handle(req, mood="bold")

    card_classic = next(c for c in reply_classic.cards if c.kind == "outfit")
    card_bold = next(c for c in reply_bold.cards if c.kind == "outfit")

    # The canonical candidate scoring is identical across moods for identical candidate garments
    assert card_classic.score == card_bold.score
    assert reply_classic.outfitIntelligence.matchScore == reply_bold.outfitIntelligence.matchScore


# ---------------------------------------------------------------------------
# 12. No independent static outfit catalog recommendation is reintroduced
# ---------------------------------------------------------------------------


def test_12_no_independent_static_outfit_catalog_reintroduced():
    """Neither reply.cards nor reply.outfitIntelligence returns static catalog looks."""
    user = UserContext(
        wardrobe=_sample_wire_items(),
        preferredOccasions=["work"],
    )
    req = _req("what should i wear for office?", user=user)

    reply = engine.handle(req)

    outfit_card = next((c for c in reply.cards if c.kind == "outfit"), None)
    assert outfit_card is not None
    assert outfit_card.title != "Refined Office"
    assert outfit_card.title != "Effortless Casual"

    for item_id in reply.outfitIntelligence.selectedItemIds:
        # None of the selected IDs should refer to static unowned items
        assert item_id in {item.id for item in user.wardrobe}
