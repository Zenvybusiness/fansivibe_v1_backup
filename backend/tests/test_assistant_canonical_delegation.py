"""Targeted regression test suite for AI Assistant canonical delegation (Batch 4A).

Validates that `backend/app/ai/tools.py` delegates hairstyle and grooming
recommendations to canonical domain recommendation engines:
- `analysis_rules.recommend_hairstyle`
- `grooming_rules.recommend_grooming`
and eliminates hardcoded catalog lookups, static scores, and unsupported
face-shape suitability claims.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ai import engine, tools
from app.data import catalog
from app.domain.ports.external import KnowledgeSource
from app.domain.services import analysis_rules, grooming_rules
from app.domain.value_objects import AppearanceProfile, HairstylePreferences
from app.infrastructure.external.knowledge import CatalogKnowledgeSource
from app.models.schemas import (
    AssistantRequest,
    ChatMessage,
    FaceData,
    SuggestionCard,
    UserContext,
)

# Disable external LLM calls during tests
import app.ai.llm_backend as llm_backend

llm_backend.is_available = lambda: False


# ===========================================================================
# 1. Verification of Canonical Delegation via Spies and Dependency Injection
# ===========================================================================


def test_hairstyle_delegates_to_canonical_analysis_rules():
    """`tools.recommend_hairstyle` calls `analysis_rules.recommend_hairstyle` with expected arguments."""
    user = UserContext(
        face=FaceData(
            faceShape="round",
            skinTone="warm",
            bodyType="athletic",
            styleType="classic",
        ),
        savedLooks=["classic_pompadour"],
    )

    with patch.object(
        analysis_rules,
        "recommend_hairstyle",
        wraps=analysis_rules.recommend_hairstyle,
    ) as spy_hair:
        cards = tools.recommend_hairstyle(user)

        assert spy_hair.called
        assert spy_hair.call_count == 1
        call_args, call_kwargs = spy_hair.call_args

        # Verify appearance profile passed to canonical engine
        passed_appearance = call_args[1]
        assert isinstance(passed_appearance, AppearanceProfile)
        assert passed_appearance.faceShape == "round"
        assert passed_appearance.skinTone == "warm"
        assert passed_appearance.bodyType == "athletic"
        assert passed_appearance.styleType == "classic"

        # Verify preferences passed to canonical engine
        passed_prefs = call_kwargs.get("preferences") or call_args[2]
        assert isinstance(passed_prefs, HairstylePreferences)
        assert "classic_pompadour" in passed_prefs.preferredLookIds

        # Verify output cards
        assert len(cards) >= 1
        assert cards[0].kind == "hairstyle"
        assert cards[0].action == "open_hairstyle"


def test_grooming_delegates_to_canonical_grooming_rules():
    """`tools.recommend_grooming` calls `grooming_rules.recommend_grooming` with expected arguments."""
    user = UserContext(
        face=FaceData(
            faceShape="oval",
            skinTone="medium",
            bodyType="average",
            styleType="minimalist",
        ),
        savedLooks=["structured_goatee"],
    )

    with patch.object(
        grooming_rules,
        "recommend_grooming",
        wraps=grooming_rules.recommend_grooming,
    ) as spy_groom:
        cards = tools.recommend_grooming(user)

        assert spy_groom.called
        assert spy_groom.call_count == 1
        call_args, call_kwargs = spy_groom.call_args

        # Verify appearance profile passed to canonical engine
        passed_appearance = call_args[1]
        assert isinstance(passed_appearance, AppearanceProfile)
        assert passed_appearance.faceShape == "oval"
        assert passed_appearance.skinTone == "medium"

        # Verify preferences passed to canonical engine
        passed_prefs = call_kwargs.get("preferences")
        assert isinstance(passed_prefs, HairstylePreferences)
        assert "structured_goatee" in passed_prefs.preferredLookIds

        # Verify output cards
        assert len(cards) >= 1
        assert cards[0].kind == "grooming"
        assert cards[0].action == "open_grooming"


def test_hairstyle_and_grooming_support_dependency_injection():
    """Both tools accept an explicit KnowledgeSource parameter."""
    custom_ks = MagicMock(spec=CatalogKnowledgeSource)
    custom_ks.knowledge_version = "test-1.0"
    
    # Use real CatalogKnowledgeSource to supply items for mock return
    real_ks = CatalogKnowledgeSource()
    custom_ks.retrieve_hairstyle_looks.side_effect = real_ks.retrieve_hairstyle_looks
    custom_ks.retrieve_grooming_looks.side_effect = real_ks.retrieve_grooming_looks

    cards_hair = tools.recommend_hairstyle(None, knowledge=custom_ks)
    assert len(cards_hair) >= 1
    assert custom_ks.retrieve_hairstyle_looks.called

    cards_groom = tools.recommend_grooming(None, knowledge=custom_ks)
    assert len(cards_groom) >= 1
    assert custom_ks.retrieve_grooming_looks.called


# ===========================================================================
# 2. Zero-Fabrication on Missing / Incomplete Face Shape
# ===========================================================================


@pytest.mark.parametrize(
    "user_input",
    [
        None,
        UserContext(),
        UserContext(face=None),
        UserContext(face=FaceData(faceShape=None)),
        UserContext(face=FaceData(faceShape="")),
        UserContext(face=FaceData(faceShape="   ")),
    ],
)
def test_unmeasured_face_shape_never_claims_oval(user_input):
    """Missing or empty face shape does NOT claim oval suitability in hairstyle or grooming."""
    hair_cards = tools.recommend_hairstyle(user_input)
    assert len(hair_cards) == 2
    for card in hair_cards:
        sub = card.subtitle.lower()
        assert "oval" not in sub
        assert "suits oval" not in sub
        assert "oval face" not in sub

    groom_cards = tools.recommend_grooming(user_input)
    assert len(groom_cards) == 2
    for card in groom_cards:
        sub = card.subtitle.lower()
        assert "oval" not in sub
        assert "frames the chin for oval" not in sub
        assert "oval face" not in sub


def test_unmeasured_face_shape_returns_honest_versatile_subtitles():
    """Unmeasured face shape returns honest versatile advisories indicating missing scan data."""
    hair_cards = tools.recommend_hairstyle(UserContext())
    assert "versatile" in hair_cards[0].subtitle.lower()
    assert "add a face scan" in hair_cards[0].subtitle.lower()

    groom_cards = tools.recommend_grooming(UserContext())
    assert "versatile" in groom_cards[0].subtitle.lower()
    assert "add a face scan" in groom_cards[0].subtitle.lower()


# ===========================================================================
# 3. Dynamic Canonical Scores (No Hardcoded 94% or 91%)
# ===========================================================================


def test_hairstyle_scores_are_dynamic_and_grounded():
    """Hairstyle scores are dynamically computed from canonical matchScore, not static constants."""
    # Round face gives Classic Pompadour 0.99 matchScore -> 99%
    cards_round = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="round")))
    assert cards_round[0].title == "Classic Pompadour"
    assert cards_round[0].score == 99

    # Rectangular face gives Textured Quiff 0.97 matchScore -> 97%
    cards_rec = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="rectangular")))
    assert cards_rec[0].title == "Textured Quiff"
    assert cards_rec[0].score == 97

    # Oval face gives Textured Quiff 1.00 matchScore -> 100%
    cards_oval = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="oval")))
    assert cards_oval[0].title == "Textured Quiff"
    assert cards_oval[0].score == 100

    # Unmeasured face gives Textured Quiff 0.94 matchScore -> 94%
    cards_none = tools.recommend_hairstyle(None)
    assert cards_none[0].title == "Textured Quiff"
    assert cards_none[0].score == 94


def test_grooming_scores_are_dynamic_and_grounded():
    """Grooming scores are dynamically computed from canonical matchScore, not static constants."""
    # Oval face gives Structured Goatee 0.98 matchScore -> 98%
    cards_oval = tools.recommend_grooming(UserContext(face=FaceData(faceShape="oval")))
    assert cards_oval[0].title == "Structured Goatee"
    assert cards_oval[0].score == 98
    assert cards_oval[1].score == 90  # Classic Stubble 0.85 + 0.05 -> 90%

    # Round face gives Classic Stubble alternative 89% (0.85 + 0.04)
    cards_round = tools.recommend_grooming(UserContext(face=FaceData(faceShape="round")))
    assert cards_round[1].title == "Classic Stubble"
    assert cards_round[1].score == 89


# ===========================================================================
# 4. Canonical Recommendation Reasons Preserved
# ===========================================================================


def test_hairstyle_preserves_canonical_face_match_reasons():
    """Measured face shapes include canonical face-match reason in subtitle."""
    cards_round = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="round")))
    assert "Strongest match for your round face shape (+0.12 face-shape fit)." in cards_round[0].subtitle

    cards_rec = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="rectangular")))
    assert "Strongest match for your rectangular face shape (+0.03 face-shape fit)." in cards_rec[0].subtitle

    cards_oval = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="oval")))
    assert "Strongest match for your oval face shape (+0.06 face-shape fit)." in cards_oval[0].subtitle


def test_grooming_preserves_canonical_face_match_reasons():
    """Grooming recommendations preserve canonical face-match reasons when applicable."""
    cards_oval = tools.recommend_grooming(UserContext(face=FaceData(faceShape="oval")))
    assert "Strongest match for your oval face shape (+0.06 face-shape fit)." in cards_oval[0].subtitle

    # For round face, Structured Goatee has 0 boost, so it uses the clean non-conflicting reason
    cards_round = tools.recommend_grooming(UserContext(face=FaceData(faceShape="round")))
    assert "Clean geometric shape reads intentional and polished" in cards_round[0].subtitle
    # Alternative Classic Stubble DOES have round face boost (+0.04)
    assert "Strongest match for your round face shape (+0.04 face-shape fit)." in cards_round[1].subtitle


# ===========================================================================
# 5. Canonical Ranking and Eligibility Respected
# ===========================================================================


def test_canonical_ranking_respected_across_face_shapes():
    """Ranking follows canonical analysis_rules and grooming_rules engine."""
    # Round face -> Pompadour > Quiff
    cards_round = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="round")))
    assert cards_round[0].title == "Classic Pompadour"
    assert cards_round[1].title == "Textured Quiff"

    # Square face -> Pompadour > Quiff
    cards_square = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="square")))
    assert cards_square[0].title == "Classic Pompadour"
    assert cards_square[1].title == "Textured Quiff"

    # Rectangular face -> Quiff > Pompadour (per canonical scoring 0.97 > 0.93)
    cards_rec = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="rectangular")))
    assert cards_rec[0].title == "Textured Quiff"
    assert cards_rec[1].title == "Classic Pompadour"

    # Oval face -> Quiff > Pompadour
    cards_oval = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="oval")))
    assert cards_oval[0].title == "Textured Quiff"
    assert cards_oval[1].title == "Classic Pompadour"


# ===========================================================================
# 6. Response Contract & Conversational Engine Compatibility
# ===========================================================================


def test_suggestion_card_contract_completeness():
    """Returned cards satisfy SuggestionCard contract with proper field types."""
    cards = tools.recommend_hairstyle(UserContext(face=FaceData(faceShape="round")))
    assert len(cards) == 2
    for card in cards:
        assert isinstance(card, SuggestionCard)
        assert card.kind == "hairstyle"
        assert isinstance(card.title, str) and card.title
        assert isinstance(card.subtitle, str) and card.subtitle
        assert isinstance(card.score, int) and 0 <= card.score <= 100
        assert isinstance(card.items, list) and len(card.items) >= 1
        assert card.action == "open_hairstyle"

    g_cards = tools.recommend_grooming(UserContext(face=FaceData(faceShape="oval")))
    assert len(g_cards) == 2
    for card in g_cards:
        assert isinstance(card, SuggestionCard)
        assert card.kind == "grooming"
        assert isinstance(card.title, str) and card.title
        assert isinstance(card.subtitle, str) and card.subtitle
        assert isinstance(card.score, int) and 0 <= card.score <= 100
        assert isinstance(card.items, list) and len(card.items) >= 1
        assert card.action == "open_grooming"


def test_conversational_engine_turn_hairstyle_uses_canonical_data():
    """`engine.handle` produces conversational text with dynamic canonical score and grounded reasons."""
    user = UserContext(face=FaceData(faceShape="round"))
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content="best hairstyle for me")],
        user=user,
    )
    reply = engine.handle(req)

    assert reply.intent == "hairstyle"
    assert len(reply.cards) == 2
    assert reply.cards[0].title == "Classic Pompadour"
    assert reply.cards[0].score == 99

    # Conversational text contains dynamic 99% match and grounded reason
    assert "Classic Pompadour (99% match)" in reply.text
    assert "Strongest match for your round face shape (+0.12 face-shape fit)." in reply.text


def test_conversational_engine_turn_grooming_uses_canonical_data():
    """`engine.handle` produces conversational text with dynamic canonical score and grounded reasons for grooming."""
    user = UserContext(face=FaceData(faceShape="oval"))
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content="which beard suits me")],
        user=user,
    )
    reply = engine.handle(req)

    assert reply.intent == "grooming"
    assert len(reply.cards) == 2
    assert reply.cards[0].title == "Structured Goatee"
    assert reply.cards[0].score == 98

    # Conversational text contains dynamic 98% match and grounded reason
    assert "Structured Goatee suits you best (98% match)" in reply.text
    assert "Strongest match for your oval face shape (+0.06 face-shape fit)." in reply.text


def test_conversational_engine_turn_unmeasured_face_honest():
    """`engine.handle` produces honest copy with no oval face claims when unmeasured."""
    req = AssistantRequest(
        messages=[ChatMessage(role="user", content="best hairstyle for me")],
        user=UserContext(),
    )
    reply = engine.handle(req)

    assert reply.intent == "hairstyle"
    assert "oval" not in reply.text.lower()
    assert "add a face scan" in reply.text.lower()
    assert reply.cards[0].title == "Textured Quiff"
    assert reply.cards[0].score == 94
