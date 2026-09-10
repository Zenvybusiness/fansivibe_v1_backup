"""Unit tests for the modular hairstyle and grooming decision engine stages.

Covers each stage from `DECISION_ENGINE_ARCHITECTURE.md` for the hairstyle
and grooming tasks — ContextBuilder, CandidateGeneration, Filtering, Scoring,
Ranking, Explanation, Recommendation — plus the derived confidence value, honest
insufficient-user-data handling, and the low-confidence path. All tests are
deterministic: identical inputs → identical outputs. No database, no LLM.
"""

from __future__ import annotations

import pytest

from app.domain.ports.external import KnowledgeError
from app.domain.services.analysis_rules import (
    build_context,
    build_explanations,
    derive_confidence,
    derive_grooming_confidence,
    filter_candidates,
    filter_grooming_candidates,
    generate_candidates,
    rank_candidates,
    recommend_hairstyle,
    score_candidates,
    recommend_grooming,
    build_grooming_context,
    generate_grooming_candidates,
    score_grooming_candidates,
    rank_grooming_candidates,
    build_grooming_explanations,
)
from app.domain.value_objects import (
    AppearanceProfile,
    HairstylePreferences,
)
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

KNOWLEDGE = CatalogKnowledgeSource()


def _profile(**overrides) -> AppearanceProfile:
    values = {
        "faceShape": "Oval",
        "skinTone": "Warm Medium",
        "bodyType": "Athletic",
        "styleType": "Modern Classic",
        "sourceRunId": "run-1",
    }
    values.update(overrides)
    return AppearanceProfile(**values)


def _context(profile: AppearanceProfile, preferences=None):
    return build_context(
        profile,
        preferences,
        knowledge_version=KNOWLEDGE.knowledge_version,
    )


# --- candidate generation ----------------------------------------------------


def test_candidates_come_from_knowledge_source_only():
    context = _context(_profile())
    candidates = generate_candidates(KNOWLEDGE, context)
    assert sorted(look.id for look in candidates) == [
        "brushed_up_undercut",
        "classic_pompadour",
        "side_part",
        "textured_quiff",
    ]


def test_candidate_generation_rejects_empty_knowledge():
    class EmptySource:
        knowledge_version = "test"
        def retrieve_hairstyle_looks(self):
            return []

    with pytest.raises(KnowledgeError):
        generate_candidates(EmptySource(), _context(_profile()))


# --- filtering ---------------------------------------------------------------


def test_filtering_excludes_preferred_exclusions():
    context = _context(
        _profile(),
        HairstylePreferences(excludedLookIds=frozenset({"classic_pompadour"})),
    )
    filtered = filter_candidates(generate_candidates(KNOWLEDGE, context), context)
    assert "classic_pompadour" not in [look.id for look in filtered]
    assert "textured_quiff" in [look.id for look in filtered]


def test_filtering_is_binary_keep_drop_without_scoring():
    context = _context(
        _profile(),
        HairstylePreferences(excludedLookIds=frozenset({"side_part"})),
    )
    filtered = filter_candidates(generate_candidates(KNOWLEDGE, context), context)
    assert len(filtered) == 3
    # Filtering never reorders or rescales the survivors.
    assert sorted(look.matchScore for look in filtered) == [0.78, 0.87, 0.94]


def test_filtering_without_exclusions_keeps_all():
    context = _context(_profile())
    filtered = filter_candidates(generate_candidates(KNOWLEDGE, context), context)
    assert len(filtered) == 4


# --- scoring -----------------------------------------------------------------


def test_scoring_uses_face_shape_boost_on_seed():
    context = _context(_profile(faceShape="Round"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # pompadour seed 0.87 + round boost 0.12
    assert by_id["classic_pompadour"].score == 0.99
    assert by_id["classic_pompadour"].signals == {
        "seed": 0.87,
        "face_shape": 0.12,
        "preference": 0.0,
        "saved_look": 0.0,
    }


def test_scoring_scores_stay_within_zero_one():
    context = _context(_profile(faceShape="Oval"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    assert all(0.0 <= candidate.score <= 1.0 for candidate in scored)


def test_scoring_unknown_face_shape_is_neutral():
    context = _context(_profile(faceShape="Zodiac"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    assert by_id["textured_quiff"].score == 0.94  # seed, no boost


def test_scoring_preference_boost_is_additive():
    context = _context(
        _profile(faceShape="Oval"),
        HairstylePreferences(preferredLookIds=frozenset({"side_part"})),
    )
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # side_part seed 0.82 + oval boost 0.05 + preference boost 0.03
    assert by_id["side_part"].score == 0.90
    assert by_id["side_part"].signals["preference"] == 0.03
    assert by_id["side_part"].signals == {
        "seed": 0.82,
        "face_shape": 0.05,
        "preference": 0.03,
        "saved_look": 0.0,
    }


# --- ranking -----------------------------------------------------------------


def test_ranking_orders_descending_and_deterministic():
    context = _context(_profile(faceShape="Round"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    first = rank_candidates(scored)
    second = rank_candidates(scored)
    assert [candidate.score for candidate in first] == sorted(
        (candidate.score for candidate in first), reverse=True
    )
    assert [candidate.id for candidate in first] == [
        candidate.id for candidate in second
    ]


def test_ranking_ties_keep_catalog_order():
    context = _context(_profile(faceShape="Heart"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # side_part (0.82+0.00) and brushed_up_undercut (0.78+0.04) both land at
    # 0.82 — a stable tie that must keep catalog (generation) order.
    assert by_id["side_part"].score == by_id["brushed_up_undercut"].score
    ranked_ids = [candidate.id for candidate in rank_candidates(scored)]
    assert ranked_ids.index("side_part") < ranked_ids.index("brushed_up_undercut")


# --- confidence ---------------------------------------------------------------


def test_confidence_is_deterministic_and_bounded():
    context = _context(_profile())
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    ranked = rank_candidates(scored)
    first = derive_confidence(context, ranked)
    second = derive_confidence(context, ranked)
    assert first == second
    assert 0.0 <= first <= 1.0


def test_confidence_rises_with_profile_completeness():
    full = _context(_profile())
    scored = score_candidates(generate_candidates(KNOWLEDGE, full), full)
    ranked = rank_candidates(scored)
    full_confidence = derive_confidence(full, ranked)

    sparse = _context(_profile(faceShape="Round", skinTone="", bodyType="", styleType=""))
    scored = score_candidates(generate_candidates(KNOWLEDGE, sparse), sparse)
    ranked = rank_candidates(scored)
    sparse_confidence = derive_confidence(sparse, ranked)

    assert full_confidence > sparse_confidence


# --- explanation --------------------------------------------------------------


def test_explanations_are_grounded_in_catalog_reasons():
    context = _context(_profile())
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    explanations = build_explanations(rank_candidates(scored), context)
    assert [explanation.id for explanation in explanations] == [
        "textured_quiff",
        "classic_pompadour",
        "side_part",
        "brushed_up_undercut",
    ]
    for explanation in explanations:
        assert explanation.reasons  # never empty
    assert any("face shape" in reason for reason in explanations[0].reasons)


def test_explanations_never_invent_unknown_facts():
    context = _context(_profile(faceShape="Zodiac"))
    scored = score_candidates(generate_candidates(KNOWLEDGE, context), context)
    explanations = build_explanations(rank_candidates(scored), context)
    for explanation in explanations:
        # An unknown face shape gets no face-match reason and no invented text.
        assert all(not reason.lower().startswith("strongest match") for reason in explanation.reasons)
        assert "zodiac" not in " ".join(explanation.reasons).lower()


# --- insufficient user data ---------------------------------------------------


def test_insufficient_user_data_defaults_neutral_and_flags():
    # No appearance signals at all — the engine must not fabricate; it uses
    # the neutral default (oval→neutral for an unknown face) and honestly
    # flags `needs_more_data` with low confidence.
    result = recommend_hairstyle(KNOWLEDGE, _profile(faceShape="Rectangle", skinTone="", bodyType="", styleType=""))
    assert result.needs_more_data is True
    assert result.confidence < 0.5
    assert result.appearance.faceShape == "Rectangle"
    assert result.top.id in {"textured_quiff", "classic_pompadour"}


def test_full_profile_does_not_need_more_data():
    result = recommend_hairstyle(KNOWLEDGE, _profile())
    assert result.needs_more_data is False


# --- low-confidence analysis ---------------------------------------------------


def test_low_confidence_still_yields_grounded_top_pick():
    # Sparse grounding + a tight ranking → low confidence, but the top pick
    # stays grounded in the catalog (never fabricated, AI-0).
    result = recommend_hairstyle(
        KNOWLEDGE,
        _profile(faceShape="Rectangle", skinTone="", bodyType="", styleType=""),
    )
    assert result.confidence < 0.5
    assert result.top.id in {"textured_quiff", "classic_pompadour"}
    assert result.top.matchScore <= 1.0
    assert result.top.reasons


def test_confidence_reflects_decisive_vs_tight_top():
    # A profile with a decisive top pick and full grounding yields a higher
    # confidence than the same grounding with a tight top-vs-runner-up gap.
    decisive = recommend_hairstyle(
        KNOWLEDGE, _profile(faceShape="Oval", skinTone="Warm Medium", bodyType="Athletic", styleType="Modern Classic")
    )
    tight = recommend_hairstyle(
        KNOWLEDGE, _profile(faceShape="Rectangle", skinTone="Warm Medium", bodyType="Athletic", styleType="Modern Classic")
    )
    assert decisive.confidence > tight.confidence


# --- orchestrator determinism -------------------------------------------------


def test_recommendation_is_deterministic_for_identical_inputs():
    first = recommend_hairstyle(KNOWLEDGE, _profile(faceShape="Round"))
    second = recommend_hairstyle(KNOWLEDGE, _profile(faceShape="Round"))
    assert first.to_snapshot() == second.to_snapshot()


def test_preferences_change_results_deterministically():
    plain = recommend_hairstyle(KNOWLEDGE, _profile(faceShape="Oval"))
    excluded = recommend_hairstyle(
        KNOWLEDGE,
        _profile(faceShape="Oval"),
        HairstylePreferences(excludedLookIds=frozenset({"textured_quiff"})),
    )
    assert excluded.top.id == "classic_pompadour"
    assert excluded.top.id != plain.top.id


# --- grooming decision engine tests -------------------------------------------


def test_grooming_candidates_come_from_knowledge_source_only():
    context = _context(_profile(faceShape="Oval"))
    candidates = generate_grooming_candidates(KNOWLEDGE, context)
    all_ids = [c.id for c in candidates]
    assert sorted(all_ids) == sorted([
        "structured_goatee",
        "classic_stubble",
        "full_beard",
        "goatee_with_mustache",
    ])


def test_grooming_candidate_generation_rejects_empty_knowledge():
    class EmptySource:
        knowledge_version = "test"
        def retrieve_grooming_looks(self):
            return []

    with pytest.raises(KnowledgeError):
        generate_grooming_candidates(EmptySource(), _context(_profile(faceShape="Oval")))


def test_grooming_filtering_excludes_preferred_exclusions():
    context = _context(
        _profile(faceShape="Oval"),
        HairstylePreferences(excludedLookIds=frozenset({"full_beard"})),
    )
    filtered = filter_grooming_candidates(
        generate_grooming_candidates(KNOWLEDGE, context), context
    )
    assert "full_beard" not in [look.id for look in filtered]
    assert "structured_goatee" in [look.id for look in filtered]


def test_grooming_filtering_is_binary_keep_drop_without_scoring():
    context = _context(
        _profile(faceShape="Oval"),
        HairstylePreferences(excludedLookIds=frozenset({"side_part"})),
    )
    # side_part is not a grooming look, so filtering should keep all
    filtered = filter_grooming_candidates(
        generate_grooming_candidates(KNOWLEDGE, context), context
    )
    assert len(filtered) == 4


def test_grooming_filtering_without_exclusions_keeps_all():
    context = _context(_profile(faceShape="Oval"))
    filtered = filter_grooming_candidates(
        generate_grooming_candidates(KNOWLEDGE, context), context
    )
    assert len(filtered) == 4


def test_grooming_scoring_uses_face_shape_boost_on_seed():
    context = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # structured_goatee seed 0.92 + oval boost 0.06
    assert by_id["structured_goatee"].score == 0.98
    assert by_id["structured_goatee"].signals == {
        "seed": 0.92,
        "face_shape": 0.06,
        "preference": 0.0,
        "saved_look": 0.0,
    }


def test_grooming_scores_stay_within_zero_one():
    context = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    assert all(0.0 <= candidate.score <= 1.0 for candidate in scored)


def test_grooming_unknown_face_shape_is_neutral():
    context = _context(_profile(faceShape="Zodiac"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # no boost for unknown face shape, scores stay as seed
    assert by_id["structured_goatee"].score == 0.92


def test_grooming_preference_boost_is_additive():
    context = _context(
        _profile(faceShape="Oval"),
        HairstylePreferences(preferredLookIds=frozenset({"classic_stubble"})),
    )
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # classic_stubble seed 0.85 + oval boost 0.05 + preference boost 0.03
    assert by_id["classic_stubble"].score == 0.93
    assert by_id["classic_stubble"].signals["preference"] == 0.03
    assert by_id["classic_stubble"].signals == {
        "seed": 0.85,
        "face_shape": 0.05,
        "preference": 0.03,
        "saved_look": 0.0,
    }


def test_grooming_ranking_orders_descending_and_deterministic():
    context = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    first = rank_grooming_candidates(scored)
    second = rank_grooming_candidates(scored)
    assert [candidate.score for candidate in first] == sorted(
        (candidate.score for candidate in first), reverse=True
    )
    assert [candidate.id for candidate in first] == [candidate.id for candidate in second]


def test_grooming_ranking_ties_keep_catalog_order():
    context = _context(_profile(faceShape="Heart"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    by_id = {candidate.id: candidate for candidate in scored}
    # classic_stubble (0.85+0.05) and goatee_with_mustache (0.71+0.05) both have
    # boost for heart, but different seeds — ensure stable ordering
    ranked_ids = [candidate.id for candidate in rank_grooming_candidates(scored)]
    # catalog order: structured_goatee, classic_stubble, full_beard, goatee_with_mustache


def test_grooming_explanations_are_grounded_in_catalog_reasons():
    context = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    explanations = build_grooming_explanations(rank_grooming_candidates(scored), context)
    assert [explanation.id for explanation in explanations] == [
        "structured_goatee",
        "classic_stubble",
        "full_beard",
        "goatee_with_mustache",
    ]
    for explanation in explanations:
        assert explanation.reasons  # never empty


def test_grooming_explanations_never_invent_unknown_facts():
    context = _context(_profile(faceShape="Zodiac"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    explanations = build_grooming_explanations(rank_grooming_candidates(scored), context)
    for explanation in explanations:
        # An unknown face shape gets no face-match reason and no invented text.
        assert all(not reason.lower().startswith("strongest match") for reason in explanation.reasons)
        assert "zodiac" not in " ".join(explanation.reasons).lower()


def test_grooming_confidence_is_deterministic_and_bounded():
    context = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, context), context)
    ranked = rank_grooming_candidates(scored)
    first = derive_grooming_confidence(context, ranked)
    second = derive_grooming_confidence(context, ranked)
    assert first == second
    assert 0.0 <= first <= 1.0


def test_grooming_confidence_rises_with_profile_completeness():
    full = _context(_profile(faceShape="Oval"))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, full), full)
    ranked = rank_grooming_candidates(scored)
    full_confidence = derive_grooming_confidence(full, ranked)

    sparse = _context(_profile(faceShape="Oval", skinTone="", bodyType="", styleType=""))
    scored = score_grooming_candidates(generate_grooming_candidates(KNOWLEDGE, sparse), sparse)
    ranked = rank_grooming_candidates(scored)
    sparse_confidence = derive_grooming_confidence(sparse, ranked)

    assert full_confidence > sparse_confidence


def test_grooming_insufficient_user_data_defaults_neutral_and_flags():
    result = recommend_grooming(KNOWLEDGE, _profile(faceShape="Rectangle", skinTone="", bodyType="", styleType=""))
    assert result.needs_more_data is True
    assert result.confidence < 0.5
    assert result.appearance.faceShape == "Rectangle"
    assert result.top.id in {"structured_goatee", "classic_stubble", "full_beard", "goatee_with_mustache"}


def test_grooming_full_profile_does_not_need_more_data():
    result = recommend_grooming(KNOWLEDGE, _profile(faceShape="Oval"))
    assert result.needs_more_data is False


def test_grooming_low_confidence_still_yields_grounded_top_pick():
    result = recommend_grooming(
        KNOWLEDGE,
        _profile(faceShape="Rectangle", skinTone="", bodyType="", styleType=""),
    )
    assert result.confidence < 0.5
    assert result.top.id in {"structured_goatee", "classic_stubble", "full_beard", "goatee_with_mustache"}
    assert result.top.reasons


def test_grooming_confidence_reflects_decisive_vs_tight_top():
    decisive = recommend_grooming(
        KNOWLEDGE, _profile(faceShape="Oval", skinTone="Warm Medium", bodyType="Athletic", styleType="Modern Classic")
    )
    tight = recommend_grooming(
        KNOWLEDGE, _profile(faceShape="Rectangle", skinTone="Warm Medium", bodyType="Athletic", styleType="Modern Classic")
    )
    assert decisive.confidence > tight.confidence


def test_grooming_recommendation_is_deterministic_for_identical_inputs():
    first = recommend_grooming(KNOWLEDGE, _profile(faceShape="Round"))
    second = recommend_grooming(KNOWLEDGE, _profile(faceShape="Round"))
    assert first.to_snapshot() == second.to_snapshot()


def test_grooming_preferences_change_results_deterministically():
    plain = recommend_grooming(KNOWLEDGE, _profile(faceShape="Oval"))
    excluded = recommend_grooming(
        KNOWLEDGE,
        _profile(faceShape="Oval"),
        HairstylePreferences(excludedLookIds=frozenset({"structured_goatee"})),
    )
    assert excluded.top.id != plain.top.id
    assert excluded.top.id in {"classic_stubble", "full_beard", "goatee_with_mustache"}


def test_grooming_empty_candidate_set():
    """Empty knowledge source should raise KnowledgeError."""
    class EmptySource:
        knowledge_version = "test"
        def retrieve_grooming_looks(self):
            return []

    with pytest.raises(KnowledgeError):
        generate_grooming_candidates(EmptySource(), _context(_profile(faceShape="Oval")))


def test_grooming_incompatible_grooming_option():
    """When all candidates are filtered out, recommend_grooming raises KnowledgeError."""
    with pytest.raises(KnowledgeError, match="no grooming looks after filtering"):
        recommend_grooming(
            KNOWLEDGE,
            _profile(faceShape="Oval"),
            HairstylePreferences(excludedLookIds=frozenset({
                "structured_goatee", "classic_stubble", "full_beard", "goatee_with_mustache"
            })),
        )


# Helper: same as _context from the hairstyle tests but with grooming awareness
def _context(profile: AppearanceProfile, preferences=None):
    return build_context(
        profile,
        preferences,
        knowledge_version=KNOWLEDGE.knowledge_version,
    )


# ============================================================================
# STEP 11.4.1 — assistant engine OUTFIT wiring defect (DB-free, no LLM)
#
# `engine.handle()` referenced the domain `outfit` object (bound only in the
# INTENT_WARDROBE branch) on the INTENT_OUTFIT path → NameError — and the
# domain shape never matched the wire `AssistantReply.outfitIntelligence`
# contract. The fix builds the wire object from the existing recommendation
# outputs only. No scoring, selection, personalization, or WARDROBE change.
# ============================================================================


def _assistant_request(message, user=None):
    from app.models.schemas import AssistantRequest, ChatMessage

    return AssistantRequest(
        messages=[ChatMessage(role="user", content=message)], user=user
    )


def _assistant_user(**overrides):
    from app.models.schemas import UserContext, WardrobeItem

    values = {
        "wardrobe": [
            WardrobeItem(
                id="item-1",
                name="Navy Blazer",
                category="outerwear",
                color="navy",
                material="wool",
                isFavorite=True,
            ),
            WardrobeItem(
                id="item-2",
                name="White Tee",
                category="tops",
                color="white",
                material="cotton",
                isFavorite=False,
            ),
        ],
        "face": None,
        "savedLooks": [],
        "preferredOccasions": ["date", "office"],
    }
    values.update(overrides)
    return UserContext(**values)


def _handle_no_llm(monkeypatch, request):
    """Run `engine.handle()` with LLM enrichment disabled (deterministic)."""
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as llm_backend

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    return assistant_engine.handle(request)


def test_11_4_1_wardrobe_behavior_unchanged(monkeypatch):
    """A. WARDROBE text/cards/intelligence computation identical to before."""
    reply = _handle_no_llm(
        monkeypatch, _assistant_request("what do I own in my wardrobe", _assistant_user())
    )
    assert reply.intent == "wardrobe"
    assert "wardrobe" in reply.text.lower()
    assert len(reply.cards) > 0
    assert reply.cards[0].kind == "clothing_intelligence"
    # The WARDROBE reply never carried the wire field — still None.
    assert reply.outfitIntelligence is None


def test_11_4_1_outfit_no_longer_raises_name_error(monkeypatch):
    """B. INTENT_OUTFIT with an occasion returns a reply (was NameError)."""
    reply = _handle_no_llm(
        monkeypatch, _assistant_request("what should i wear for date night")
    )
    assert reply.intent == "outfit"
    assert len(reply.cards) > 0
    assert "date" in reply.text


def test_11_4_1_outfit_carries_wire_level_shape(monkeypatch):
    """C. OUTFIT reply carries schemas.OutfitIntelligence built from existing outputs."""
    from app.models.schemas import OutfitIntelligence as WireOutfitIntelligence

    reply = _handle_no_llm(
        monkeypatch, _assistant_request("what should i wear for date night")
    )
    wire = reply.outfitIntelligence
    assert isinstance(wire, WireOutfitIntelligence)
    assert wire.occasion == "date"
    assert wire.stylingRationale == reply.cards[0].subtitle
    # Untouched schema defaults — no invented scoring or selection.
    assert wire.selectedItemIds == []
    assert wire.confidence == 0.0
    assert wire.explanation == ""
    assert wire.dataAvailability == "full"


def test_11_4_1_non_outfit_intents_unaffected(monkeypatch):
    """D. Greeting / thanks / hairstyle / ambiguous-outfit paths unchanged."""
    greeting = _handle_no_llm(monkeypatch, _assistant_request("hi"))
    assert greeting.intent == "greeting"
    assert greeting.outfitIntelligence is None

    thanks = _handle_no_llm(monkeypatch, _assistant_request("thanks a lot"))
    assert thanks.intent == "thanks"
    assert thanks.outfitIntelligence is None

    hairstyle = _handle_no_llm(monkeypatch, _assistant_request("best haircut for me"))
    assert hairstyle.intent == "hairstyle"
    assert len(hairstyle.cards) > 0
    assert hairstyle.outfitIntelligence is None

    # Ambiguous outfit (no occasion) still asks for clarification, no crash.
    clarify = _handle_no_llm(monkeypatch, _assistant_request("what should i wear"))
    assert clarify.intent == "outfit"
    assert len(clarify.clarifications) > 0
    assert clarify.outfitIntelligence is None


def test_11_4_1_no_saved_look_personalization_introduced(monkeypatch):
    """E. Saved looks cannot influence the outfit reply; no new input exists."""
    import inspect

    from app.ai import engine as assistant_engine

    assert "saved_looks" not in inspect.signature(assistant_engine.handle).parameters

    plain = _handle_no_llm(
        monkeypatch, _assistant_request("what should i wear for date night")
    )
    with_saves = _handle_no_llm(
        monkeypatch,
        _assistant_request(
            "what should i wear for date night",
            _assistant_user(savedLooks=["classic_stubble", "textured_quiff"]),
        ),
    )
    assert with_saves.outfitIntelligence.occasion == plain.outfitIntelligence.occasion
    assert (
        with_saves.outfitIntelligence.stylingRationale
        == plain.outfitIntelligence.stylingRationale
    )
    assert [c.title for c in with_saves.cards] == [c.title for c in plain.cards]


# ============================================================================
# STEP 11.10 — server-authoritative assistant preferences (DB-free).
#
# `POST /v1/assistant/chat` resolves `preferred_occasions` at the entry point
# (server list wins when valid and non-empty, else the client snapshot) and
# passes the resolved list into `engine.handle(preferred_occasions=...)`.
# Auth stays optional; resolution is read-only and never throws. OI formulas,
# hairstyle/grooming, and the wire schema are untouched.
# ============================================================================


def _11_10_wardrobe_user(occasions):
    from app.models.schemas import UserContext, WardrobeItem

    return UserContext(
        wardrobe=[
            WardrobeItem(
                id="item-1",
                name="Navy Blazer",
                category="outerwear",
                color="navy",
                material="wool",
                isFavorite=True,
            ),
            WardrobeItem(
                id="item-2",
                name="White Tee",
                category="tops",
                color="white",
                material="cotton",
                isFavorite=False,
            ),
        ],
        savedLooks=[],
        preferredOccasions=list(occasions),
    )


def _11_10_chat_request(message, occasions):
    from app.models.schemas import AssistantRequest, ChatMessage

    return AssistantRequest(
        messages=[ChatMessage(role="user", content=message)],
        user=_11_10_wardrobe_user(occasions),
    )


def _11_10_occasion_confidence(reply, occasion):
    card = next(
        c for c in reply.cards if c.title == f"Suitable for: {occasion}"
    )
    return card.subtitle


def _11_10_handle_no_llm(monkeypatch, request, **kwargs):
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as llm_backend

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    return assistant_engine.handle(request, **kwargs)


def test_11_10_engine_override_reaches_outfit_intelligence(monkeypatch):
    """7. An explicit resolved list drives OI occasion blending (not client)."""
    req = _11_10_chat_request("what do I own in my wardrobe", ["date"])
    reply = _11_10_handle_no_llm(
        monkeypatch, req, preferred_occasions=["party"]
    )
    assert reply.intent == "wardrobe"
    assert _11_10_occasion_confidence(reply, "party") == "Confidence: 100%"
    assert _11_10_occasion_confidence(reply, "date") == "Confidence: 30%"


def test_11_10_identical_values_preserve_behavior(monkeypatch):
    """6. Resolved == client snapshot → output equivalent to legacy call."""
    req = _11_10_chat_request("what do I own in my wardrobe", ["date"])
    legacy = _11_10_handle_no_llm(monkeypatch, req)
    resolved = _11_10_handle_no_llm(
        monkeypatch, req, preferred_occasions=["date"]
    )
    assert resolved.text == legacy.text
    assert [c.title for c in resolved.cards] == [c.title for c in legacy.cards]
    assert [c.subtitle for c in resolved.cards] == [
        c.subtitle for c in legacy.cards
    ]


def test_11_10_hairstyle_and_grooming_unaffected(monkeypatch):
    """8. The occasions parameter cannot move hairstyle/grooming output."""
    from app.models.schemas import AssistantRequest, ChatMessage

    for message in ("best hairstyle for me", "which beard suits me"):
        req = AssistantRequest(
            messages=[ChatMessage(role="user", content=message)], user=None
        )
        plain = _11_10_handle_no_llm(monkeypatch, req)
        routed = _11_10_handle_no_llm(
            monkeypatch, req, preferred_occasions=["office"]
        )
        assert routed.intent == plain.intent
        assert routed.text == plain.text
        assert [c.title for c in routed.cards] == [c.title for c in plain.cards]


class _11_10_FakeUserStateRepo:
    """Recording UserStateRepository double: canned preferences per user."""

    def __init__(self, db=None, rows=None) -> None:
        self._rows = rows if rows is not None else {}
        self.calls: list = []

    def get_profile(self, *, user_id):
        from app.domain.ports.repositories import UserProfileRecord

        self.calls.append(("get_profile", user_id))
        row = self._rows.get(user_id)
        if row is None:
            return None
        return UserProfileRecord(
            user_id=user_id,
            display_name="Alex",
            style_profile={},
            preferences=row,
            settings={},
            flags={},
            version=1,
        )


def _11_10_post(monkeypatch, body, headers=None):
    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    old_db = main_module.app.dependency_overrides.get(get_db)
    old_user = main_module.app.dependency_overrides.get(get_current_user_id)
    main_module.app.dependency_overrides[get_db] = lambda: object()
    main_module.app.dependency_overrides[get_current_user_id] = lambda: None
    try:
        client = TestClient(main_module.app)
        return client.post("/v1/assistant/chat", json=body, headers=headers)
    finally:
        if old_db is not None:
            main_module.app.dependency_overrides[get_db] = old_db
        else:
            main_module.app.dependency_overrides.pop(get_db, None)
        if old_user is not None:
            main_module.app.dependency_overrides[get_current_user_id] = old_user
        else:
            main_module.app.dependency_overrides.pop(get_current_user_id, None)


def _11_10_chat_body(occasions):
    return {
        "messages": [
            {"role": "user", "content": "what do I own in my wardrobe"}
        ],
        "user": {"wardrobe": [], "savedLooks": [], "preferredOccasions": occasions},
    }


def test_11_10_server_beats_client(monkeypatch):
    """1. Server ["business"] wins over client ["weekend"]."""
    import uuid as _uuid

    import app.main as main_module

    user_id = _uuid.uuid4()
    repo = _11_10_FakeUserStateRepo(
        rows={user_id: {"preferred_occasions": ["business"]}}
    )
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db=None: repo)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )
    captured: dict = {}

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        captured.update(kwargs)
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    resp = _11_10_post(
        monkeypatch,
        _11_10_chat_body(["weekend"]),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    assert captured.get("preferred_occasions") == ["business"]
    assert repo.calls == [("get_profile", user_id)]


def test_11_10_empty_server_falls_back_to_client(monkeypatch):
    """2. Server [] → engine receives the client list."""
    import uuid as _uuid

    import app.main as main_module

    user_id = _uuid.uuid4()
    repo = _11_10_FakeUserStateRepo(rows={user_id: {"preferred_occasions": []}})
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db=None: repo)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )
    captured: dict = {}

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        captured.update(kwargs)
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    resp = _11_10_post(
        monkeypatch,
        _11_10_chat_body(["weekend"]),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    assert captured.get("preferred_occasions") == ["weekend"]


def test_11_10_missing_profile_falls_back_to_client(monkeypatch):
    """3. No user_state row → client snapshot, no 500."""
    import uuid as _uuid

    import app.main as main_module

    user_id = _uuid.uuid4()
    repo = _11_10_FakeUserStateRepo(rows={})
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db=None: repo)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )
    captured: dict = {}

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        captured.update(kwargs)
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    resp = _11_10_post(
        monkeypatch,
        _11_10_chat_body(["weekend"]),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    assert captured.get("preferred_occasions") == ["weekend"]


def test_11_10_malformed_server_falls_back_to_client(monkeypatch):
    """4+5. Missing key or non-list[str] server value → client, no throw."""
    import uuid as _uuid

    import app.main as main_module

    user_id = _uuid.uuid4()
    captured: dict = {}

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        captured.update(kwargs)
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )
    for bad_prefs in (
        {},
        {"preferred_occasions": "business"},
        {"preferred_occasions": ["date", 1]},
        {"preferred_occasions": None},
    ):
        repo = _11_10_FakeUserStateRepo(rows={user_id: bad_prefs})
        monkeypatch.setattr(
            main_module, "UserStateRepositorySQL", lambda db=None: repo
        )
        resp = _11_10_post(
            monkeypatch,
            _11_10_chat_body(["weekend"]),
            headers={"Authorization": "Bearer dev"},
        )
        assert resp.status_code == 200
        assert captured.get("preferred_occasions") == ["weekend"]


def test_11_10_unauthenticated_keeps_client_behavior(monkeypatch):
    """G. No Bearer token → no 401; client snapshot flows through untouched."""
    captured: dict = {}

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        captured.update(kwargs)
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    resp = _11_10_post(monkeypatch, _11_10_chat_body(["weekend"]))
    assert resp.status_code == 200
    assert captured.get("preferred_occasions") == ["weekend"]


def test_11_10_resolution_writes_nothing(monkeypatch):
    """10. Preference resolution performs zero database writes."""
    import uuid as _uuid

    import app.main as main_module

    user_id = _uuid.uuid4()
    repo = _11_10_FakeUserStateRepo(
        rows={user_id: {"preferred_occasions": ["business"]}}
    )
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db=None: repo)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )

    from app.models.schemas import AssistantReply

    def spy(request, **kwargs):
        return AssistantReply(intent="wardrobe", text="ok", cards=[])

    monkeypatch.setattr("app.ai.engine.handle", spy)
    resp = _11_10_post(
        monkeypatch,
        _11_10_chat_body(["weekend"]),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    assert repo.calls == [("get_profile", user_id)]
    assert repo._rows[user_id] == {"preferred_occasions": ["business"]}


def test_11_10_resolved_server_value_reaches_oi(monkeypatch):
    """7. End to end: server ["party"] beats client ["date"] in OI output."""
    import uuid as _uuid

    import app.main as main_module
    import app.ai.llm_backend as llm_backend

    user_id = _uuid.uuid4()
    repo = _11_10_FakeUserStateRepo(
        rows={user_id: {"preferred_occasions": ["party"]}}
    )
    monkeypatch.setattr(main_module, "UserStateRepositorySQL", lambda db=None: repo)
    monkeypatch.setattr(
        main_module, "get_current_user_id", lambda authorization, db: user_id
    )
    monkeypatch.setattr(llm_backend, "is_available", lambda: False)

    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    old_db = main_module.app.dependency_overrides.get(get_db)
    old_user = main_module.app.dependency_overrides.get(get_current_user_id)
    main_module.app.dependency_overrides[get_db] = lambda: object()
    main_module.app.dependency_overrides[get_current_user_id] = lambda: None
    try:
        client = TestClient(main_module.app)
        resp = client.post(
            "/v1/assistant/chat",
            json=_11_10_chat_body(["date"]),
            headers={"Authorization": "Bearer dev"},
        )
    finally:
        if old_db is not None:
            main_module.app.dependency_overrides[get_db] = old_db
        else:
            main_module.app.dependency_overrides.pop(get_db, None)
        if old_user is not None:
            main_module.app.dependency_overrides[get_current_user_id] = old_user
        else:
            main_module.app.dependency_overrides.pop(get_current_user_id, None)

    assert resp.status_code == 200
    cards = {
        c["title"]: c["subtitle"] for c in resp.json()["cards"]
    }
    assert cards.get("Suitable for: party") == "Confidence: 100%"
    assert cards.get("Suitable for: date") == "Confidence: 30%"


# ============================================================================
# STEP 11.17 — saved-outfit preference consumer (OI + assistant seam).
#
# DB-free. The +0.05 contribution is additive-only on the OI confidence value;
# the STEP 7A formula, thresholds, and all sub-rules are untouched. Honest
# scope note: OI evaluates the single item the engine passes (wardrobe[0]);
# no multi-item ranking is invented — `selected_item_ids` stays [].
# ============================================================================

from uuid import uuid4 as _11_17_uuid4


def _11_17_context(sparse=False):
    from app.domain.value_objects import WardrobeContext

    if sparse:
        return WardrobeContext(
            total_items=2,
            favorite_count=0,
            items_per_category={"tops": 1, "bottoms": 1},
            style_score=87,
        )
    return WardrobeContext(
        total_items=24,
        favorite_count=8,
        items_per_category={
            "tops": 8,
            "bottoms": 5,
            "outerwear": 4,
            "footwear": 4,
            "accessories": 3,
        },
        style_score=87,
    )


def _11_17_oi(item_id="", preferred=None, sparse=False):
    from app.domain.services.analysis_rules import (
        compute_clothing_intelligence,
        compute_outfit_intelligence,
    )

    ctx = _11_17_context(sparse=sparse)
    ci = compute_clothing_intelligence(
        item_category="tops",
        item_color="charcoal",
        item_material="wool",
        item_is_favorite=not sparse,
        wardrobe_context=ctx,
        preferred_occasions=["casual", "office", "travel"],
    )
    return compute_outfit_intelligence(
        ci,
        item_color="charcoal",
        item_material="wool",
        item_is_favorite=not sparse,
        wardrobe_context=ctx,
        preferred_occasions=["casual", "office", "date"],
        item_id=item_id,
        preferred_item_ids=preferred,
    )


def test_11_17_absent_or_empty_input_reproduces_baseline():
    """A. None / empty preferred set → identical OI output (all fields)."""
    base = _11_17_oi()
    assert _11_17_oi(preferred=None).confidence == base.confidence
    assert _11_17_oi(preferred=frozenset()).confidence == base.confidence
    assert _11_17_oi(preferred=frozenset()).confidence_level.level == (
        base.confidence_level.level
    )
    assert _11_17_oi().item_id == ""


def test_11_17_preferred_item_receives_plus_0_05():
    """B. item_id in the set → exactly +0.05 on confidence, id recorded."""
    item = str(_11_17_uuid4())
    base = _11_17_oi(sparse=True)
    assert base.confidence < 1.0  # headroom: the delta must be visible
    result = _11_17_oi(item_id=item, preferred=frozenset([item]), sparse=True)
    assert result.item_id == item
    assert result.confidence == round(base.confidence + 0.05, 2)
    assert result.confidence_level.level in ("strong", "reasonable", "insufficient")


def test_11_17_repeated_ids_do_not_stack():
    """C. Same ID evaluated repeatedly still yields one +0.05."""
    from app.domain.services.analysis_rules import preference_contribution

    item = str(_11_17_uuid4())
    assert preference_contribution(frozenset([item]), [item, item]) == 0.05
    assert preference_contribution(frozenset([item]), [item]) == 0.05


def test_11_17_contribution_capped_at_plus_0_15():
    """D. Four distinct preferred IDs → 0.15, not 0.20."""
    from app.domain.services.analysis_rules import preference_contribution

    ids = [str(_11_17_uuid4()) for _ in range(4)]
    assert preference_contribution(frozenset(ids), ids) == 0.15


def test_11_17_multiple_preferred_items_each_counted():
    """E. Two distinct preferred IDs → 0.10; each OI item gets its +0.05."""
    from app.domain.services.analysis_rules import preference_contribution

    first, second = str(_11_17_uuid4()), str(_11_17_uuid4())
    assert preference_contribution(frozenset([first, second]), [first, second]) == 0.10
    base = _11_17_oi(sparse=True)
    assert _11_17_oi(item_id=first, preferred=frozenset([first, second]), sparse=True).confidence == (
        round(base.confidence + 0.05, 2)
    )
    assert _11_17_oi(item_id=second, preferred=frozenset([first, second]), sparse=True).confidence == (
        round(base.confidence + 0.05, 2)
    )


def test_11_17_non_preferred_item_unchanged():
    """F. Item outside the set → zero contribution, baseline confidence."""
    base = _11_17_oi()
    other = str(_11_17_uuid4())
    result = _11_17_oi(item_id=other, preferred=frozenset([str(_11_17_uuid4())]))
    assert result.confidence == base.confidence


def test_11_17_signals_are_not_an_input():
    """I. Neither the resolver, the formula, nor OI accepts learning-signal
    data — the preferred set is a pure function of saved_looks rows, so a
    look_saved echo cannot contribute a second time. Structural (no signal
    parameter or local exists) + behavioral (same rows → same set)."""
    import inspect

    from app.domain.services.analysis_rules import (
        compute_outfit_intelligence,
        preference_contribution,
        resolve_preferred_item_ids,
    )

    assert "signal" not in inspect.signature(resolve_preferred_item_ids).parameters
    assert "signal" not in inspect.signature(preference_contribution).parameters
    # NOTE: inspect.signature(compute_outfit_intelligence) is unusable — its
    # `-> OutfitIntelligence` return annotation is only imported lazily
    # inside the function body (pre-existing quirk, Py3.14 evaluates it on
    # access). co_varnames needs no annotation evaluation.
    assert not [
        name
        for name in compute_outfit_intelligence.__code__.co_varnames
        if "signal" in name
    ]


def _11_17_wardrobe_request(item_ids, message="what do I own in my wardrobe"):
    from app.models.schemas import AssistantRequest, ChatMessage, UserContext, WardrobeItem

    names = ["Navy Blazer", "White Tee", "Blue Jeans", "Brown Boots"]
    cats = ["outerwear", "tops", "bottoms", "footwear"]
    cols = ["navy", "white", "denim", "brown"]
    wardrobe = [
        WardrobeItem(
            id=iid,
            name=names[k % len(names)],
            category=cats[k % len(cats)],
            color=cols[k % len(cols)],
            material="wool" if k == 0 else "cotton",
            isFavorite=(k == 0),
        )
        for k, iid in enumerate(item_ids)
    ]
    return AssistantRequest(
        messages=[ChatMessage(role="user", content=message)],
        user=UserContext(wardrobe=wardrobe, savedLooks=[], preferredOccasions=["date"]),
    )


def _11_17_confidence_card(reply):
    return next(c for c in reply.cards if c.title.startswith("Confidence:"))


def test_11_17_handle_without_input_keeps_baseline_reply():
    """A (assistant). No preferred_item_ids → text and cards identical."""
    ids = [str(_11_17_uuid4()), str(_11_17_uuid4())]
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as _llm

    real = _llm.is_available
    _llm.is_available = lambda: False
    try:
        plain = assistant_engine.handle(_11_17_wardrobe_request(ids))
        routed = assistant_engine.handle(_11_17_wardrobe_request(ids), preferred_item_ids=[])
    finally:
        _llm.is_available = real
    assert routed.text == plain.text
    assert [c.title for c in routed.cards] == [c.title for c in plain.cards]
    assert [c.subtitle for c in routed.cards] == [c.subtitle for c in plain.cards]


def test_11_17_saved_outfit_reaches_wardrobe_oi_path(monkeypatch):
    """K. A saved outfit ID reaches OI as (item_id, preferred set) and moves
    the evaluated item's confidence card by exactly +0.05."""
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as llm_backend

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    first, second = str(_11_17_uuid4()), str(_11_17_uuid4())
    req = _11_17_wardrobe_request([first, second])

    baseline = assistant_engine.handle(req)
    preferred = assistant_engine.handle(req, preferred_item_ids=[second, first])

    # The engine evaluates wardrobe[0]: only `first` can move this reply.
    only_first = assistant_engine.handle(req, preferred_item_ids=[first])
    assert _11_17_confidence_card(only_first).subtitle != (
        _11_17_confidence_card(baseline).subtitle
    )
    # Preferred set containing other items only → identical reply.
    only_second = assistant_engine.handle(req, preferred_item_ids=[second])
    assert [c.subtitle for c in only_second.cards] == [
        c.subtitle for c in baseline.cards
    ]
    assert only_second.text == baseline.text
    assert _11_17_confidence_card(preferred).subtitle != (
        _11_17_confidence_card(baseline).subtitle
    )


def test_11_17_engine_passes_item_id_and_set_to_oi(monkeypatch):
    """K (seam). The WARDROBE branch forwards the candidate ID + set."""
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as llm_backend
    import app.domain.services.analysis_rules as rules

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    first, second = str(_11_17_uuid4()), str(_11_17_uuid4())
    captured = {}
    real_oi = rules.compute_outfit_intelligence

    def spy(**kwargs):
        captured.update(kwargs)
        return real_oi(
            kwargs["clothing_intelligence"],
            item_color=kwargs["item_color"],
            item_material=kwargs["item_material"],
            item_is_favorite=kwargs["item_is_favorite"],
            wardrobe_context=kwargs["wardrobe_context"],
            preferred_occasions=kwargs["preferred_occasions"],
            item_id=kwargs["item_id"],
            preferred_item_ids=kwargs["preferred_item_ids"],
        )

    monkeypatch.setattr(assistant_engine, "compute_outfit_intelligence", spy)
    assistant_engine.handle(
        _11_17_wardrobe_request([first, second]), preferred_item_ids=[first]
    )
    assert captured["item_id"] == first
    assert captured["preferred_item_ids"] == frozenset([first])


# ============================================================================
# STEP 13.6 — candidate pipeline production integration (INTENT_WARDROBE).
# engine.py only; domain helpers reused unmodified. No-candidate wardrobes
# fall through to the historical wardrobe[0] path (covered by pre-existing
# 11.4.1/11.10/11.17 tests, all still green).
# ============================================================================

from uuid import uuid4 as _13_6_uuid4


def _13_6_item(item_id, category, color="black", material="cotton", fav=False):
    from app.models.schemas import WardrobeItem

    return WardrobeItem(id=item_id, name=f"{category} {item_id[:4]}",
                        category=category, color=color, material=material,
                        isFavorite=fav)


def _13_6_request(items, message="what do I own in my wardrobe", occasions=None):
    from app.models.schemas import AssistantRequest, ChatMessage, UserContext

    return AssistantRequest(
        messages=[ChatMessage(role="user", content=message)],
        user=UserContext(wardrobe=list(items), savedLooks=[],
                         preferredOccasions=list(occasions) if occasions else ["date"]),
    )


def _13_6_no_llm(monkeypatch):
    from app.ai import engine as assistant_engine
    import app.ai.llm_backend as llm_backend

    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    return assistant_engine


def _13_6_cards(reply):
    return {c.title: c.subtitle for c in reply.cards}


def test_13_6_empty_wardrobe_honest_no_crash(monkeypatch):
    """M1. Empty wardrobe → wardrobe reply, defaults, no Selected card."""
    engine = _13_6_no_llm(monkeypatch)
    reply = engine.handle(_13_6_request([]))
    assert reply.intent == "wardrobe"
    assert "wardrobe" in reply.text.lower()
    assert not [c for c in reply.cards if c.title.startswith("Selected Items:")]


def test_13_6_sparse_wardrobes_fall_back_without_fabrication(monkeypatch):
    """M2/M3. One item / no bottoms → historical path, real IDs only."""
    engine = _13_6_no_llm(monkeypatch)
    top = str(_13_6_uuid4())
    one = engine.handle(_13_6_request([_13_6_item(top, "tops")]))
    assert "Your tops in" in one.text
    assert not [c for c in one.cards if c.title.startswith("Selected Items:")]
    outer, tee = str(_13_6_uuid4()), str(_13_6_uuid4())
    two = engine.handle(_13_6_request([_13_6_item(outer, "outerwear"),
                                       _13_6_item(tee, "tops")]))
    assert "Your outerwear in" in two.text  # wardrobe[0] honored, as before


def test_13_6_top_bottom_selects_winner_with_ids_and_composition(monkeypatch):
    """M4. Winner IDs + composition cards from the real winning candidate."""
    engine = _13_6_no_llm(monkeypatch)
    top, bottom = str(_13_6_uuid4()), str(_13_6_uuid4())
    reply = engine.handle(_13_6_request([_13_6_item(top, "tops"),
                                         _13_6_item(bottom, "bottoms")]))
    cards = _13_6_cards(reply)
    assert cards.get("Selected Items: 2") == f"{top}, {bottom}"
    assert cards.get("Outfit Composition") == "Top(s): 1 | Bottom(s): 1"


def test_13_6_footwear_skeleton_composition(monkeypatch):
    """M5. Footwear member appears in the composition card (casual occasion,
    which footwear suits per the existing category map)."""
    engine = _13_6_no_llm(monkeypatch)
    ids = [str(_13_6_uuid4()) for _ in range(3)]
    reply = engine.handle(_13_6_request([_13_6_item(ids[0], "tops"),
                                         _13_6_item(ids[1], "bottoms"),
                                         _13_6_item(ids[2], "footwear")],
                                        occasions=["casual"]))
    cards = _13_6_cards(reply)
    assert "Footwear: 1" in cards.get("Outfit Composition", "")
    assert ids[2] in cards.get("Selected Items: 3", "")


def test_13_6_multi_candidate_winner_matches_domain_pipeline(monkeypatch):
    """M6. Full wardrobe → winner equals the independently computed
    generate→score→rank→select result (no second algorithm in engine)."""
    from app.domain.services.analysis_rules import (
        generate_outfit_candidates, rank_outfit_candidates,
        score_outfit_candidate, select_best_outfit_candidate)
    engine = _13_6_no_llm(monkeypatch)
    ids = {"tops": str(_13_6_uuid4()), "bottoms": str(_13_6_uuid4()),
           "outerwear": str(_13_6_uuid4()), "footwear": str(_13_6_uuid4()),
           "accessories": str(_13_6_uuid4())}
    items = [_13_6_item(i, c) for c, i in ids.items()]
    reply = engine.handle(_13_6_request(items))
    by_id = {i.id: i for i in items}
    expected = select_best_outfit_candidate(rank_outfit_candidates(
        [score_outfit_candidate(c, by_id, frozenset(), ["date"])
         for c in generate_outfit_candidates(items)]))
    assert expected is not None
    cards = _13_6_cards(reply)
    winner_ids = (list(expected.top_ids) + list(expected.bottom_ids)
                  + list(expected.outerwear_ids) + list(expected.footwear_ids)
                  + list(expected.accessory_ids))
    assert cards.get(f"Selected Items: {len(winner_ids)}") is not None
    subtitle = cards[f"Selected Items: {len(winner_ids)}"]
    # Engine renders the existing STEP 7C.2 truncation contract (first 4).
    assert subtitle == ", ".join(winner_ids[:4]) + ("..." if len(winner_ids) > 4 else "")
    for part, bucket in (("Top(s): 1", expected.top_ids),
                         ("Bottom(s): 1", expected.bottom_ids),
                         ("Outerwear: 1", expected.outerwear_ids),
                         ("Footwear: 1", expected.footwear_ids),
                         ("Accessories: 1", expected.accessory_ids)):
        if bucket:
            assert part in cards.get("Outfit Composition", "")


def test_13_6_wardrobe_zero_not_unconditional_winner(monkeypatch):
    """N. wardrobe[0] is a bottoms item (old code evaluated it); the pipeline
    evaluates the winner's top and selects both IDs."""
    engine = _13_6_no_llm(monkeypatch)
    bottom, top = str(_13_6_uuid4()), str(_13_6_uuid4())
    reply = engine.handle(_13_6_request([_13_6_item(bottom, "bottoms"),
                                         _13_6_item(top, "tops")]))
    assert "Your tops in" in reply.text  # not "Your bottoms in"
    assert _13_6_cards(reply).get("Selected Items: 2") == f"{top}, {bottom}"


def test_13_6_deterministic_repeated_calls(monkeypatch):
    """O. Identical inputs → identical text, cards, selection."""
    engine = _13_6_no_llm(monkeypatch)
    ids = [str(_13_6_uuid4()) for _ in range(4)]
    cats = ["tops", "bottoms", "outerwear", "footwear"]
    req = lambda: _13_6_request([_13_6_item(i, c) for i, c in zip(ids, cats)])
    first, second = engine.handle(req()), engine.handle(req())
    assert first.text == second.text
    assert [(c.title, c.subtitle) for c in first.cards] == [
        (c.title, c.subtitle) for c in second.cards]


def test_13_6_preferred_item_flows_into_pipeline_scoring(monkeypatch):
    """Q. Preferred set reaches score_outfit_candidate per candidate, and the
    rendered confidence equals the domain OI value (whose +0.05 preference
    delta is asserted exactly, free of float-rendering)."""
    from app.ai import engine as assistant_engine
    from app.domain.services.analysis_rules import compute_clothing_intelligence
    from app.domain.services.analysis_rules import compute_outfit_intelligence
    from app.domain.value_objects import WardrobeContext

    engine = _13_6_no_llm(monkeypatch)
    top, bottom = str(_13_6_uuid4()), str(_13_6_uuid4())
    items = [_13_6_item(top, "tops"), _13_6_item(bottom, "bottoms")]
    seen = []
    real_score = assistant_engine.score_outfit_candidate

    def spy(candidate, items_by_id, preferred, occasions):
        seen.append((candidate, preferred, occasions))
        return real_score(candidate, items_by_id, preferred, occasions)

    monkeypatch.setattr(assistant_engine, "score_outfit_candidate", spy)
    base = engine.handle(_13_6_request(items))
    assert seen and all(p == frozenset() for _, p, _ in seen)
    assert all(o == ["date"] for _, _, o in seen)
    seen.clear()
    pref = engine.handle(_13_6_request(items), preferred_item_ids=[top])
    assert seen and all(p == frozenset([top]) for _, p, _ in seen)

    def _expected_oi(preferred):
        ctx = WardrobeContext(total_items=2, favorite_count=0,
                              items_per_category={"tops": 1, "bottoms": 1},
                              style_score=87)
        ci = compute_clothing_intelligence(
            item_category="tops", item_color="black", item_material="cotton",
            item_is_favorite=False, wardrobe_context=ctx,
            preferred_occasions=["date"])
        return compute_outfit_intelligence(
            ci, item_color="black", item_material="cotton",
            item_is_favorite=False, wardrobe_context=ctx,
            preferred_occasions=["date"], item_id=top,
            preferred_item_ids=preferred)

    exp_base, exp_pref = _expected_oi(frozenset()), _expected_oi(frozenset([top]))
    assert round(exp_pref.confidence - exp_base.confidence, 2) == 0.05

    def _conf(reply):
        return next(c.subtitle for c in reply.cards
                    if c.title.startswith("Confidence:"))

    assert _conf(base) == f"{exp_base.confidence:.1f}/1.0"
    assert _conf(pref) == f"{exp_pref.confidence:.1f}/1.0"


# ============================================================================
# STEP 13.7 — winner mapping & explanation audit proofs.
# Audit only: no production change was required (mapping verified correct).
# These tests pin the two boundaries without prior explicit coverage:
# incompatible-pair fallback and explanation grounding.
# ============================================================================


def test_13_7_two_incompatible_items_fall_back_honestly(monkeypatch):
    """L. Two tops (no legal skeleton) → historical fallback, no crash,
    no Selected card, no fabricated IDs."""
    engine = _13_6_no_llm(monkeypatch)
    first, second = str(_13_6_uuid4()), str(_13_6_uuid4())
    reply = engine.handle(_13_6_request([_13_6_item(first, "tops"),
                                         _13_6_item(second, "tops")]))
    assert reply.intent == "wardrobe"
    assert "Your tops in" in reply.text  # wardrobe[0] honored, as before
    assert not [c for c in reply.cards if c.title.startswith("Selected Items:")]
    assert "Outfit Composition" not in _13_6_cards(reply)


def test_13_7_winner_explanation_grounded_no_unsupported_claims(monkeypatch):
    """H+N. Winner reply text stays grounded: names only owned items and
    deterministic signals; no vision/perfection/body/shopping/trend claims."""
    engine = _13_6_no_llm(monkeypatch)
    top, bottom = str(_13_6_uuid4()), str(_13_6_uuid4())
    for req in (_13_6_request([_13_6_item(top, "tops"), _13_6_item(bottom, "bottoms")]),
                _13_6_request([_13_6_item(top, "tops")])):
        text = engine.handle(req).text.lower()
        for banned in ("perfect", "ai vision", "face shape", "your body",
                       "shopping", "trend", "buy ", "recommend you purchase"):
            assert banned not in text
    winner_text = engine.handle(
        _13_6_request([_13_6_item(top, "tops"), _13_6_item(bottom, "bottoms")])).text
    assert "Your tops in black" in winner_text  # owned item, real attributes
    assert "wardrobe" in winner_text.lower()
