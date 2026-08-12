"""Unit tests for the modular hairstyle decision engine stages.

Covers each stage from `DECISION_ENGINE_ARCHITECTURE.md` for the hairstyle
task — ContextBuilder, CandidateGeneration, Filtering, Scoring, Ranking,
Explanation, Recommendation — plus the derived confidence value, honest
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
    filter_candidates,
    generate_candidates,
    rank_candidates,
    recommend_hairstyle,
    score_candidates,
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
