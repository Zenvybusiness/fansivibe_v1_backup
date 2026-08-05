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
    assert reply.cards and reply.cards[0].kind == "wardrobe"


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
