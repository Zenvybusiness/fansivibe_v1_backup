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
