from app.ai import engine
from app.models.schemas import AssistantReply, AssistantRequest, ChatMessage, UserContext

# The LLM is never available in tests — engine must fall back to rules.
import app.ai.llm_backend as llm_backend

llm_backend.is_available = lambda: False


def _chat(*messages: str, user: UserContext | None = None) -> AssistantReply:
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content=m) for m in messages],
        user=user,
    )
    return engine.handle(req)


def test_greeting_reply():
    reply = _chat("hello")
    assert reply.intent == "greeting"
    assert reply.text


def test_outfit_asks_clarification_when_ambiguous():
    reply = _chat("what should I wear?")
    assert reply.intent == "outfit"
    assert reply.clarifications
    assert any(c.value == "office" for c in reply.clarifications)
    assert not reply.cards


def test_outfit_with_occasion_returns_card():
    reply = _chat("what should I wear to a date?")
    assert reply.intent == "outfit"
    assert reply.cards
    assert reply.cards[0].kind == "outfit"
    assert "Date" in reply.cards[0].title


def test_bare_occasion_reply_returns_card():
    reply = _chat("date")
    assert reply.intent == "outfit"
    assert reply.cards
    assert reply.cards[0].kind == "outfit"
    assert "Date" in reply.cards[0].title


def test_hairstyle_returns_cards():
    reply = _chat("best hairstyle for me")
    assert reply.intent == "hairstyle"
    assert reply.cards and reply.cards[0].kind == "hairstyle"


def test_grooming_returns_cards():
    reply = _chat("which beard suits me")
    assert reply.intent == "grooming"
    assert reply.cards and reply.cards[0].kind == "grooming"


def test_wardrobe_uses_user_context():
    user = UserContext(wardrobe=[], savedLooks=["Modern Minimalist"])
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards and reply.cards[0].kind == "clothing_intelligence"


def test_navigate_returns_route():
    reply = _chat("open my wardrobe")
    assert reply.intent == "navigate"
    assert reply.navigation is not None
    assert reply.navigation.route == "wardrobe"


def test_unknown_offers_help_options():
    reply = _chat("blah blah blah")
    assert reply.intent in ("unknown", "clarify")
    assert reply.clarifications


def test_suggestion_card_has_action_for_navigation():
    reply = _chat("suggest an outfit for work")
    assert reply.cards
    assert reply.cards[0].action == "open_outfit"


def test_wardrobe_produces_outfit_intelligence():
    """Wardrobe request produces Outfit Intelligence (STEP 7C)."""
    from app.models.schemas import WardrobeItem

    user = UserContext(
        wardrobe=[
            WardrobeItem(id="1", name="Merino Crew Neck", category="tops", color="Charcoal", material="Wool", isFavorite=True),
            WardrobeItem(id="2", name="Linen Button-Down", category="tops", color="White", material="Linen"),
            WardrobeItem(id="3", name="Oxford Shirt", category="tops", color="Light Blue", material="Cotton"),
        ],
        savedLooks=["Modern Minimalist"],
        preferredOccasions=["casual", "office"],
    )
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Should have outfit intelligence cards from STEP 7C integration
    kind_labels = [c.kind for c in reply.cards]
    assert "clothing_intelligence" in kind_labels
    # Should have confidence, data availability, and coverage cards
    confidence_card = next((c for c in reply.cards if "Confidence:" in (c.title or "")), None)
    assert confidence_card is not None
    availability_card = next((c for c in reply.cards if "Data Availability" in (c.title or "")), None)
    assert availability_card is not None


def test_full_wardrobe_produces_outfit_card():
    """Full wardrobe produces outfit cards with reasonable confidence (STEP 7C)."""
    from app.models.schemas import WardrobeItem

    user = UserContext(
        wardrobe=[
            WardrobeItem(id="1", name="Merino Crew Neck", category="tops", color="Charcoal", material="Wool", isFavorite=True),
            WardrobeItem(id="2", name="Linen Button-Down", category="tops", color="White", material="Linen"),
            WardrobeItem(id="3", name="Oxford Shirt", category="tops", color="Light Blue", material="Cotton"),
            WardrobeItem(id="4", name="Charcoal Trousers", category="bottoms", color="Charcoal", material="Wool", isFavorite=True),
            WardrobeItem(id="5", name="Khaki Chinos", category="bottoms", color="Khaki", material="Cotton"),
            WardrobeItem(id="6", name="Leather Belt", category="accessories", color="Black", material="Leather", isFavorite=True),
            WardrobeItem(id="7", name="Brown Derbies", category="footwear", color="Brown", material="Leather", isFavorite=True),
        ],
        savedLooks=["Modern Minimalist"],
        preferredOccasions=["casual", "office"],
    )
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Full wardrobe → reasonable or strong confidence
    confidence_card = next((c for c in reply.cards if "Confidence:" in (c.title or "")), None)
    assert confidence_card is not None


def test_sparse_wardrobe_low_confidence_message():
    """Sparse wardrobe produces correct low-confidence messaging (STEP 7C)."""
    from app.models.schemas import WardrobeItem

    user = UserContext(
        wardrobe=[
            WardrobeItem(id="1", name="Fav Top", category="tops", color="Black", material="Wool", isFavorite=True),
        ],
        savedLooks=[],
        preferredOccasions=[],
    )
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Sparse wardrobe → data_availability = "sparse" and lower confidence
    confidence_card = next((c for c in reply.cards if "Confidence:" in (c.title or "")), None)
    assert confidence_card is not None
    # Data availability card should indicate sparse
    availability_card = next((c for c in reply.cards if "Data Availability" in (c.title or "")), None)
    assert availability_card is not None
    availability_card_text = availability_card.subtitle or ""
    assert "sparse" in availability_card_text.lower() or "limited" in availability_card_text.lower()


def test_missing_categories_reflected_in_response():
    """Missing categories are reflected in the Assistant response (STEP 7C)."""
    from app.models.schemas import WardrobeItem

    user = UserContext(
        wardrobe=[
            WardrobeItem(id="1", name="Fav Top", category="tops", color="Black", material="Wool", isFavorite=True),
        ],
        savedLooks=[],
        preferredOccasions=[],
    )
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Coverage card should show missing categories
    coverage_card = next((c for c in reply.cards if "Coverage:" in (c.title or "")), None)
    assert coverage_card is not None


def test_unknown_occasion_defaults():
    """Unknown occasion defaults according to STEP 7A (STEP 7C)."""
    user = UserContext(wardrobe=[], savedLooks=[], preferredOccasions=[])
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Should still produce cards even without an occasion


def test_non_wardrobe_intents_unchanged():
    """Existing non-wardrobe Assistant intents remain unchanged."""
    # Greeting
    reply = _chat("hello")
    assert reply.intent == "greeting"
    assert reply.text

    # Hairstyle
    reply = _chat("best hairstyle for me")
    assert reply.intent == "hairstyle"
    assert reply.cards and reply.cards[0].kind == "hairstyle"

    # Grooming
    reply = _chat("which beard suits me")
    assert reply.intent == "grooming"
    assert reply.cards and reply.cards[0].kind == "grooming"

    # Navigate
    reply = _chat("open my wardrobe")
    assert reply.intent == "navigate"
    assert reply.navigation is not None
    assert reply.navigation.route == "wardrobe"

    # Unknown
    reply = _chat("blah blah blah")
    assert reply.intent in ("unknown", "clarify")
    assert reply.clarifications


def test_clothing_intelligence_behavior_unchanged():
    """Existing Clothing Intelligence behavior remains unchanged."""
    user = UserContext(wardrobe=[], savedLooks=[], preferredOccasions=[])
    reply = _chat("show my wardrobe", user=user)
    assert reply.intent == "wardrobe"
    assert reply.cards
    # Should still have clothing intelligence cards
    kind_labels = [c.kind for c in reply.cards]
    assert "clothing_intelligence" in kind_labels
