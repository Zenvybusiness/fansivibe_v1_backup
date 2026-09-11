"""Unit tests for the hairstyle decision engine (rules-first).

These never touch a database — they use the in-code catalog knowledge source.
"""

import pytest

from app.domain.services.analysis_rules import recommend_hairstyle
from app.domain.value_objects import AppearanceProfile
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

KNOWLEDGE = CatalogKnowledgeSource()


def _result(face_shape: str, **extra):
    return recommend_hairstyle(
        KNOWLEDGE,
        AppearanceProfile(faceShape=face_shape, **extra),
    )


def test_candidates_come_from_catalog():
    result = _result("Oval")
    all_ids = [result.top.id] + [a.id for a in result.alternatives]
    assert sorted(all_ids) == [
        "brushed_up_undercut",
        "classic_pompadour",
        "side_part",
        "textured_quiff",
    ]


def test_oval_ranks_quiff_first():
    result = _result("Oval")
    assert result.top.id == "textured_quiff"
    assert result.alternatives[0].id == "classic_pompadour"


def test_round_ranks_pompadour_first():
    result = _result("Round")
    assert result.top.id == "classic_pompadour"


def test_square_ranks_pompadour_first():
    result = _result("Square")
    assert result.top.id == "classic_pompadour"


def test_scores_are_bounded_and_descending():
    result = _result("Heart")
    scores = [result.top.matchScore] + [a.matchScore for a in result.alternatives]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_appearance_profile_is_carried_with_source_run():
    result = _result("Oval", skinTone="Warm Medium", styleType="Modern Classic", sourceRunId="abc-123")
    assert result.appearance.skinTone == "Warm Medium"
    assert result.appearance.styleType == "Modern Classic"
    assert result.appearance.sourceRunId == "abc-123"


def test_defaults_to_oval_when_shape_missing():
    result = recommend_hairstyle(KNOWLEDGE, AppearanceProfile(faceShape=""))
    assert result.top.id == "textured_quiff"


def test_reasons_are_grounded_in_catalog():
    result = _result("Oval")
    assert result.top.reasons  # never empty
    assert any("quiff" in r.lower() or "volume" in r.lower() for r in result.top.reasons)


def test_snapshot_shape_matches_wire():
    result = _result("Oval")
    snapshot = result.to_snapshot()
    assert set(snapshot.keys()) == {
        "appearance",
        "confidence",
        "needs_more_data",
        "recommendations",
    }
    assert set(snapshot["appearance"].keys()) == {
        "faceShape",
        "skinTone",
        "bodyType",
        "styleType",
        "sourceRunId",
    }
    assert 0.0 <= snapshot["confidence"] <= 1.0
    assert isinstance(snapshot["needs_more_data"], bool)
    recs = snapshot["recommendations"]
    assert set(recs.keys()) == {"top", "alternatives"}
    assert set(recs["top"].keys()) == {
        "id",
        "name",
        "description",
        "matchScore",
        "reasons",
        "stylingTips",
        "maintenance",
        "bestFor",
    }


def test_empty_knowledge_raises():
    class EmptySource:
        def retrieve_hairstyle_looks(self):
            return []

    with pytest.raises(ValueError):
        recommend_hairstyle(EmptySource(), AppearanceProfile(faceShape="Oval"))


# ============================================================================
# STEP 13.2 — outfit candidate contract (representation + score + ordering).
# Contract level only: no generation, no production wiring, no confidence or
# styleScore changes. engine.py behavior untouched (no test here touches it).
# ============================================================================

from uuid import uuid4 as _13_2_uuid4

from app.domain.services.analysis_rules import (
    CANDIDATE_SKELETONS,
    candidate_favorite_points,
    candidate_item_ids,
    candidate_preference_points,
    compose_candidate_score,
    rank_outfit_candidates,
)
from app.domain.value_objects import OutfitCandidate, OutfitComposition


def _13_2_candidate(top=(), bottom=(), score=0.0, **kw):
    return OutfitCandidate(top_ids=tuple(top), bottom_ids=tuple(bottom), score=score, **kw)


def test_13_2_candidate_representation_and_buckets():
    """1+2. Buckets preserve exact IDs; defaults are empty (sparse-ready)."""
    top, bottom = str(_13_2_uuid4()), str(_13_2_uuid4())
    c = _13_2_candidate(top=[top], bottom=[bottom], score=42.0)
    assert c.score == 42.0
    assert candidate_item_ids(c) == tuple(sorted([top, bottom]))
    empty = OutfitCandidate()
    assert candidate_item_ids(empty) == ()
    assert empty.score == 0.0


def test_13_2_preferred_ids_representable_with_exact_coefficients():
    """3. Step 11 mechanism reused: +5/item, 15 cap, no stacking."""
    first, second = str(_13_2_uuid4()), str(_13_2_uuid4())
    assert candidate_preference_points(frozenset([first]), [first]) == 5.0
    assert candidate_preference_points(frozenset([first]), [first, first]) == 5.0
    four = [str(_13_2_uuid4()) for _ in range(4)]
    assert candidate_preference_points(frozenset(four), four) == 15.0
    assert candidate_preference_points(frozenset(), [first]) == 0.0
    assert candidate_preference_points(None, [first]) == 0.0


def test_13_2_score_bounded_0_to_100():
    """4. Composition clamps each signal; total never leaves 0–100."""
    assert compose_candidate_score(70, 15, 15) == 100.0
    assert compose_candidate_score(0, 0, 0) == 0.0
    assert compose_candidate_score(999, -5, "nope") == 70.0
    assert compose_candidate_score(50, 10, 5) == 65.0
    assert candidate_favorite_points([True, False, True]) == 10.0
    assert candidate_favorite_points([True] * 9) == 15.0
    assert candidate_favorite_points([]) == 0.0


def test_13_2_ranking_deterministic():
    """5. Identical inputs → identical order regardless of input order."""
    ids = [str(_13_2_uuid4()) for _ in range(3)]
    made = [_13_2_candidate(top=[i], score=s) for i, s in zip(ids, (10.0, 90.0, 50.0))]
    first = rank_outfit_candidates(made)
    second = rank_outfit_candidates(list(reversed(made)))
    assert [c.score for c in first] == [90.0, 50.0, 10.0]
    assert first == second


def test_13_2_tie_break_more_items_then_lexical_ids():
    """6. Equal scores → more items first, then canonical ID order."""
    a, b, c = sorted(str(_13_2_uuid4()) for _ in range(3))
    fuller = _13_2_candidate(top=[a], bottom=[b], score=50.0)
    single = _13_2_candidate(top=[c], score=50.0)
    assert rank_outfit_candidates([single, fuller])[0] == fuller
    left = _13_2_candidate(top=[b], score=50.0)
    right = _13_2_candidate(top=[a], score=50.0)
    assert rank_outfit_candidates([left, right]) == [right, left]


def test_13_2_sparse_candidates_representable_no_fakes():
    """7+8. Empty buckets rank fine; no placeholder/null IDs introduced."""
    sparse = _13_2_candidate(bottom=[str(_13_2_uuid4())], score=5.0)
    assert rank_outfit_candidates([sparse]) == [sparse]
    assert rank_outfit_candidates([]) == []
    for cid in candidate_item_ids(sparse):
        assert isinstance(cid, str) and cid


def test_13_2_output_mapping_preserves_ids_without_schema_change():
    """M. Buckets map 1:1 onto the existing OutfitComposition (in-test proof;
    no production mapping added)."""
    top, bottom, shoe = (str(_13_2_uuid4()) for _ in range(3))
    c = OutfitCandidate(top_ids=(top,), bottom_ids=(bottom,), footwear_ids=(shoe,))
    comp = OutfitComposition(
        top_ids=list(c.top_ids),
        bottom_ids=list(c.bottom_ids),
        outerwear_ids=list(c.outerwear_ids),
        footwear_ids=list(c.footwear_ids),
        accessory_ids=list(c.accessory_ids),
    )
    assert comp.top_ids == [top]
    assert comp.footwear_ids == [shoe]
    assert comp.outerwear_ids == []
    assert sorted(comp.top_ids + comp.bottom_ids + comp.footwear_ids) == list(
        candidate_item_ids(c)
    )


def test_13_2_skeletons_cover_five_legal_structures():
    """F. Exactly the five audited skeletons over the five categories."""
    assert CANDIDATE_SKELETONS == (
        ("tops", "bottoms"),
        ("tops", "bottoms", "footwear"),
        ("tops", "bottoms", "outerwear", "footwear"),
        ("tops", "bottoms", "footwear", "accessories"),
        ("tops", "bottoms", "outerwear", "footwear", "accessories"),
    )


# ============================================================================
# STEP 13.3 — outfit candidate generation (legal skeletons only).
# Generation ONLY: no scoring (scores stay 0.0), no ranking, no preference or
# favorite points, no engine wiring. engine.py still evaluates wardrobe[0].
# ============================================================================

from app.domain.services.analysis_rules import generate_outfit_candidates
from app.models.schemas import WardrobeItem


def _13_3_item(item_id, category, **kw):
    return WardrobeItem(
        id=item_id, name=f"{category} {item_id[:4]}", category=category,
        color="black", material="cotton", isFavorite=False, **kw,
    )


_TOP = "aaaaaaaa-0000-4000-8000-000000000001"
_BOTTOM = "bbbbbbbb-0000-4000-8000-000000000002"
_SHOE = "cccccccc-0000-4000-8000-000000000003"
_OUTER = "dddddddd-0000-4000-8000-000000000004"
_ACC = "eeeeeeee-0000-4000-8000-000000000005"


def _13_3_wardrobe(*pairs):
    return [_13_3_item(i, c) for i, c in pairs]


def test_13_3_empty_wardrobe_returns_empty():
    """1. Empty wardrobe → []."""
    assert generate_outfit_candidates([]) == []


def test_13_3_no_top_returns_empty():
    """2. No tops → [] (core mandatory)."""
    assert generate_outfit_candidates(_13_3_wardrobe((_BOTTOM, "bottoms"))) == []


def test_13_3_no_bottom_returns_empty():
    """3. No bottoms → []."""
    assert generate_outfit_candidates(_13_3_wardrobe((_TOP, "tops"))) == []


def test_13_3_top_bottom_yields_basic_candidate():
    """4. top + bottom → exactly one valid basic candidate."""
    (candidate,) = generate_outfit_candidates(
        _13_3_wardrobe((_TOP, "tops"), (_BOTTOM, "bottoms"))
    )
    assert candidate.top_ids == (_TOP,)
    assert candidate.bottom_ids == (_BOTTOM,)
    assert candidate.outerwear_ids == candidate.footwear_ids == candidate.accessory_ids == ()
    assert candidate.score == 0.0


def test_13_3_footwear_skeleton():
    """5. top + bottom + footwear → basic + footwear candidates."""
    out = generate_outfit_candidates(
        _13_3_wardrobe((_TOP, "tops"), (_BOTTOM, "bottoms"), (_SHOE, "footwear"))
    )
    assert len(out) == 2
    assert out[1].footwear_ids == (_SHOE,)
    assert out[0].footwear_ids == ()


def test_13_3_outerwear_skeleton():
    """6. + outerwear → the outerwear skeleton appears exactly once."""
    out = generate_outfit_candidates(
        _13_3_wardrobe(
            (_TOP, "tops"), (_BOTTOM, "bottoms"),
            (_OUTER, "outerwear"), (_SHOE, "footwear"),
        )
    )
    assert len(out) == 3
    assert [c for c in out if c.outerwear_ids == (_OUTER,)] != []


def test_13_3_accessory_skeleton():
    """7. + accessory (with footwear) → accessory skeleton appears."""
    out = generate_outfit_candidates(
        _13_3_wardrobe(
            (_TOP, "tops"), (_BOTTOM, "bottoms"),
            (_SHOE, "footwear"), (_ACC, "accessories"),
        )
    )
    assert len(out) == 3
    assert [c for c in out if c.accessory_ids == (_ACC,)] != []


def test_13_3_full_wardrobe_yields_full_candidate():
    """8. All five categories → five candidates incl. the full one."""
    out = generate_outfit_candidates(
        _13_3_wardrobe(
            (_TOP, "tops"), (_BOTTOM, "bottoms"), (_OUTER, "outerwear"),
            (_SHOE, "footwear"), (_ACC, "accessories"),
        )
    )
    assert len(out) == 5
    full = out[-1]
    assert (full.top_ids, full.bottom_ids, full.outerwear_ids,
            full.footwear_ids, full.accessory_ids) == (
        (_TOP,), (_BOTTOM,), (_OUTER,), (_SHOE,), (_ACC,))
    assert all(c.score == 0.0 for c in out)


def test_13_3_unknown_category_ignored_no_fabrication():
    """9+10. Unknown categories ignored; every emitted ID comes from input."""
    owned = {_TOP, _BOTTOM}
    out = generate_outfit_candidates(
        _13_3_wardrobe((_TOP, "tops"), (_BOTTOM, "bottoms"), ("x", "dresses"), ("", "tops"))
    )
    assert len(out) == 1
    emitted = {i for c in out for i in
               c.top_ids + c.bottom_ids + c.outerwear_ids + c.footwear_ids + c.accessory_ids}
    assert emitted <= owned and emitted == owned


def test_13_3_no_duplicate_candidates():
    """11. Same combination never emitted twice (incl. duplicated inputs)."""
    out = generate_outfit_candidates(
        _13_3_wardrobe((_TOP, "tops"), (_TOP, "tops"), (_BOTTOM, "bottoms"))
    )
    assert len(out) == 1


def test_13_3_exact_bucket_assignment():
    """12. IDs land in their own category buckets only."""
    out = generate_outfit_candidates(
        _13_3_wardrobe(
            (_TOP, "tops"), (_BOTTOM, "bottoms"),
            (_OUTER, "outerwear"), (_SHOE, "footwear"), (_ACC, "accessories"),
        )
    )
    for c in out:
        assert _TOP in c.top_ids and _BOTTOM in c.bottom_ids
        assert _OUTER not in c.top_ids + c.bottom_ids + c.footwear_ids + c.accessory_ids


def test_13_3_deterministic_output_and_reversed_input():
    """13+14. Same input twice → same; reversed input → same candidates."""
    pairs = [(_TOP, "tops"), (_BOTTOM, "bottoms"), (_OUTER, "outerwear"),
             (_SHOE, "footwear"), (_ACC, "accessories")]
    first = generate_outfit_candidates(_13_3_wardrobe(*pairs))
    again = generate_outfit_candidates(_13_3_wardrobe(*pairs))
    assert first == again
    rev = generate_outfit_candidates(_13_3_wardrobe(*reversed(pairs)))
    assert rev == first


def test_13_3_no_combinatorial_explosion():
    """15 (STEP 13.11 update). 3 tops × 3 bottoms × 2 footwear + outerwear +
    accessory → global cap 25, not 5 (one-per-skeleton superseded) and not
    90+ (bounded reps + cap). First 9 are (tops, bottoms) shapes in lexical
    order — skeleton ordering preserved under the cap."""
    tops = [f"aaaaaaaa-0000-4000-8000-00000000010{i}" for i in range(3)]
    bottoms = [f"bbbbbbbb-0000-4000-8000-00000000020{i}" for i in range(3)]
    shoes = [f"cccccccc-0000-4000-8000-00000000030{i}" for i in range(2)]
    pairs = ([(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms]
             + [(s, "footwear") for s in shoes]
             + [(_OUTER, "outerwear"), (_ACC, "accessories")])
    out = generate_outfit_candidates(_13_3_wardrobe(*pairs))
    assert len(out) == 25
    assert all(not c.footwear_ids for c in out[:9])
    assert out[0].top_ids == (min(tops),)


def test_13_3_only_audited_skeletons_generated():
    """16. Every candidate shape is one of the five CANDIDATE_SKELETONS."""
    from app.domain.services.analysis_rules import CANDIDATE_SKELETONS

    out = generate_outfit_candidates(
        _13_3_wardrobe(
            (_TOP, "tops"), (_BOTTOM, "bottoms"), (_OUTER, "outerwear"),
            (_SHOE, "footwear"), (_ACC, "accessories"),
        )
    )
    cats = ("tops", "bottoms", "outerwear", "footwear", "accessories")
    for c in out:
        shape = tuple(
            cat for cat, bucket in zip(
                cats, (c.top_ids, c.bottom_ids, c.outerwear_ids, c.footwear_ids, c.accessory_ids))
            if bucket
        )
        assert shape in CANDIDATE_SKELETONS


# ============================================================================
# STEP 13.4 — outfit candidate scoring (evaluation only).
# Scoring ONLY: no ranking, no winner, no engine wiring (wardrobe[0] intact),
# no confidence/styleScore/API/schema/DB change. Score 0–100, disjoint from
# 0–1 confidence by construction.
# ============================================================================

from types import SimpleNamespace as _13_4_NS

from app.domain.services.analysis_rules import score_outfit_candidate
from app.domain.value_objects import OutfitCandidate as _13_4_Candidate


def _13_4_attr(item_id, category, color="black", material="cotton", fav=False):
    return _13_4_NS(id=item_id, category=category, color=color,
                    material=material, isFavorite=fav)


_A = "aaaaaaaa-0000-4000-8000-000000000011"
_B = "bbbbbbbb-0000-4000-8000-000000000022"
_C = "cccccccc-0000-4000-8000-000000000033"
_D = "dddddddd-0000-4000-8000-000000000044"


def _13_4_items(**over):
    base = {
        _A: ("tops", "black", "cotton", False),
        _B: ("bottoms", "white", "denim", False),
        _C: ("footwear", "black", "leather", False),
        _D: ("outerwear", "navy", "wool", False),
    }
    base.update(over)
    return {i: _13_4_attr(i, c, color=co, material=m, fav=f) for i, (c, co, m, f) in base.items()}


def _13_4_cand(top=(), bottom=(), outer=(), shoe=(), acc=()):
    return _13_4_Candidate(top_ids=tuple(top), bottom_ids=tuple(bottom),
                           outerwear_ids=tuple(outer), footwear_ids=tuple(shoe),
                           accessory_ids=tuple(acc))


def test_13_4_score_range_and_neutral_base():
    """1+2. Range 0–100; empty candidate scores 0 without crashing."""
    empty = score_outfit_candidate(_13_4_cand(), {})
    assert empty.score == 0.0
    assert (empty.compatibility, empty.preference, empty.favorite) == (0.0, 0.0, 0.0)
    full = score_outfit_candidate(
        _13_4_cand((_A,), (_B,), (_D,), (_C,)), _13_4_items(),
        preferred_item_ids=frozenset([_A, _B, _C, _D]))
    assert 0.0 <= full.score <= 100.0


def test_13_4_top_bottom_exact_score():
    """3+17. Hand-computed: coverage 16 + harmony 10 + season 5 + formality 5."""
    out = score_outfit_candidate(_13_4_cand((_A,), (_B,)), _13_4_items())
    assert out.compatibility == 36.0
    assert out.preference == 0.0 and out.favorite == 0.0
    assert out.score == 36.0


def test_13_4_color_harmony_improves_conflict_reduces():
    """4+5+9. Neutral pair +10; bright–bright pair −10 (delta 20)."""
    bright = score_outfit_candidate(_13_4_cand((_A,), (_B,)),
                                    _13_4_items(**{_A: ("tops", "red", "cotton", False),
                                                   _B: ("bottoms", "olive", "denim", False)}))
    assert bright.compatibility == 16.0  # 16 − 10 + 0 + 5 + 5
    assert bright.score == 16.0


def test_13_4_season_and_formality_terms():
    """6+7. Consistency bonuses present; mixed formality loses its +5."""
    two = score_outfit_candidate(_13_4_cand((_A,), (_B,)), _13_4_items())
    three = score_outfit_candidate(_13_4_cand((_A,), (_B,), shoe=(_C,)), _13_4_items())
    # three: coverage 24 + harmony 10 + season 5 + formality 0 (casual+formal mix)
    assert three.compatibility == 39.0
    assert two.compatibility == 36.0


def test_13_4_preference_points_and_cap():
    """8+9+11. +5/item, +15 cap, set semantics."""
    c = _13_4_cand((_A,), (_B,), (_D,), (_C,))
    one = score_outfit_candidate(c, _13_4_items(), preferred_item_ids=frozenset([_A]))
    assert one.preference == 5.0
    allp = score_outfit_candidate(
        c, _13_4_items(),
        preferred_item_ids=frozenset([_A, _B, _C, _D, "ffffffff-0000-4000-8000-000000000099"]))
    assert allp.preference == 15.0
    assert allp.score <= 100.0


def test_13_4_favorite_points_and_cap():
    """10. +5/favorite member, cap 15; candidate score only."""
    c = _13_4_cand((_A,), (_B,), (_D,), (_C,))
    items = {k: _13_4_attr(k, cat, color=co, material=m, fav=True)
             for k, (cat, co, m, _) in
             {_A: ("tops", "black", "cotton", False), _B: ("bottoms", "white", "denim", False),
              _D: ("outerwear", "navy", "wool", False), _C: ("footwear", "black", "leather", False)}.items()}
    out = score_outfit_candidate(c, items)
    assert out.favorite == 15.0
    two = score_outfit_candidate(_13_4_cand((_A,), (_B,)), _13_4_items(
        **{_A: ("tops", "black", "cotton", True)}))
    assert two.favorite == 5.0


def test_13_4_preference_plus_favorite_compose_no_double_count():
    """12+13. One preferred+favorite item: preference counted once."""
    c = _13_4_cand((_A,), (_B,))
    items = _13_4_items(**{_A: ("tops", "black", "cotton", True)})
    out = score_outfit_candidate(c, items, preferred_item_ids=frozenset([_A]))
    assert out.preference == 5.0
    assert out.favorite == 5.0
    assert out.score == out.compatibility + 5.0 + 5.0
    assert "signal" not in score_outfit_candidate.__code__.co_varnames
    assert "saved" not in "".join(score_outfit_candidate.__code__.co_varnames)


def test_13_4_unknown_attributes_degrade_safely():
    """6+7+14. Unknown material/color and missing items → neutral, no crash.
    Category-derived seasons/formality still apply (real data, not invented)."""
    items = {_A: _13_4_NS(id=_A, category="tops"),
             _B: _13_4_NS(id=_B, category="bottoms", color="", material=None, isFavorite=False)}
    out = score_outfit_candidate(_13_4_cand((_A,), (_B,)), items)
    assert out.compatibility == 26.0  # 16 coverage + 0 + 0 + 5 season + 5 formality
    ghost = score_outfit_candidate(_13_4_cand(("missing-id",), (_B,)), _13_4_items())
    assert ghost.score >= 0.0


def test_13_4_deterministic_repeated_scoring():
    """15. Identical inputs → identical scored replacement; input untouched."""
    c = _13_4_cand((_A,), (_B,), (_D,), (_C,))
    items = _13_4_items()
    first = score_outfit_candidate(c, items, preferred_item_ids=frozenset([_A]))
    second = score_outfit_candidate(c, items, preferred_item_ids=frozenset([_A]))
    assert first == second
    assert c.score == 0.0 and c.preference == 0.0  # frozen input unmutated


def test_13_4_sparse_and_single_category_safety():
    """16. Sparse/single-category candidates never crash, stay bounded."""
    assert score_outfit_candidate(_13_4_cand(), {}).score == 0.0
    single = score_outfit_candidate(_13_4_cand(bottom=(_B,)), _13_4_items())
    assert 0.0 <= single.score <= 100.0


def test_13_4_final_confidence_untouched():
    """18+R. Candidate scoring does not move OI confidence or thresholds."""
    from app.domain.services.analysis_rules import (
        compute_clothing_intelligence, compute_outfit_intelligence)
    from app.domain.value_objects import WardrobeContext

    ctx = WardrobeContext(total_items=24, favorite_count=8,
                          items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4,
                                              "footwear": 4, "accessories": 3},
                          style_score=87)
    ci = compute_clothing_intelligence(
        item_category="tops", item_color="charcoal", item_material="wool",
        item_is_favorite=True, wardrobe_context=ctx,
        preferred_occasions=["casual", "office", "date"])
    before = compute_outfit_intelligence(
        ci, item_color="charcoal", item_material="wool", item_is_favorite=True,
        wardrobe_context=ctx, preferred_occasions=["casual", "office", "date"])
    score_outfit_candidate(_13_4_cand((_A,), (_B,)), _13_4_items(),
                           preferred_item_ids=frozenset([_A, _B]))
    after = compute_outfit_intelligence(
        ci, item_color="charcoal", item_material="wool", item_is_favorite=True,
        wardrobe_context=ctx, preferred_occasions=["casual", "office", "date"])
    assert (before.confidence, after.confidence) == (1.0, 1.0)
    assert before.confidence_level.level == after.confidence_level.level == "strong"


# ============================================================================
# STEP 13.5 — ranking + winner selection (ordering only).
# The rank function predates this step (13.2 contract); these tests pin its
# specified behavior plus the new select_best_outfit_candidate() helper. No
# scoring, no engine wiring, no confidence/styleScore involvement.
# ============================================================================

from app.domain.services.analysis_rules import (
    rank_outfit_candidates,
    select_best_outfit_candidate,
)
from app.domain.value_objects import OutfitCandidate as _13_5_Candidate


def _13_5_ranked(top=(), score=0.0, bottom=()):
    return _13_5_Candidate(top_ids=tuple(top), bottom_ids=tuple(bottom), score=score)


_LOW = "aaaaaaaa-0000-4000-8000-0000000000aa"
_MID = "bbbbbbbb-0000-4000-8000-0000000000bb"
_HIGH = "cccccccc-0000-4000-8000-0000000000cc"


def test_13_5_higher_score_ranks_first():
    """Q1+Q2. Score DESC, nothing else consulted."""
    out = rank_outfit_candidates([
        _13_5_ranked((_LOW,), 10.0),
        _13_5_ranked((_HIGH,), 90.0),
        _13_5_ranked((_MID,), 50.0),
    ])
    assert [c.score for c in out] == [90.0, 50.0, 10.0]


def test_13_5_equal_score_prefers_more_items():
    """Q3. Equal scores → fuller candidate first (duplicates not counted)."""
    fuller = _13_5_ranked((_LOW,), 50.0, bottom=(_MID,))
    single = _13_5_ranked((_HIGH,), 50.0)
    assert rank_outfit_candidates([single, fuller])[0] == fuller


def test_13_5_equal_score_and_count_uses_canonical_ids():
    """Q4. Full tie → ascending canonical ID representation."""
    first = _13_5_ranked((_MID,), 50.0)
    second = _13_5_ranked((_LOW,), 50.0)
    assert rank_outfit_candidates([first, second]) == [second, first]


def test_13_5_reversed_and_repeated_ranking_identical():
    """Q5+Q6. Input order irrelevant; repeated calls identical."""
    made = [_13_5_ranked((_LOW,), 10.0), _13_5_ranked((_HIGH,), 90.0),
            _13_5_ranked((_MID,), 90.0, bottom=(_LOW,))]
    assert rank_outfit_candidates(made) == rank_outfit_candidates(list(reversed(made)))
    assert rank_outfit_candidates(made) == rank_outfit_candidates(made)


def test_13_5_empty_and_single_input():
    """Q7+Q8+R edges. [] → []; one → itself."""
    assert rank_outfit_candidates([]) == []
    only = _13_5_ranked((_LOW,), 0.0)
    assert rank_outfit_candidates([only]) == [only]
    assert select_best_outfit_candidate([]) is None


def test_13_5_winner_is_ranked_first_unmutated():
    """Q9+Q10+Q12. Winner == ranked[0], same object, scores untouched."""
    best = _13_5_ranked((_HIGH,), 100.0)
    rest = [_13_5_ranked((_LOW,), 0.0), _13_5_ranked((_MID,), 50.0)]
    winner = select_best_outfit_candidate(rest + [best])
    assert winner is best
    assert winner.score == 100.0


def test_13_5_input_list_and_objects_not_mutated():
    """Q11+Q12. New ordered list; inputs and objects unchanged."""
    made = [_13_5_ranked((_LOW,), 10.0), _13_5_ranked((_HIGH,), 90.0)]
    snapshot = list(made)
    out = rank_outfit_candidates(made)
    assert made == snapshot and out is not made
    assert [c.score for c in made] == [10.0, 90.0]


def test_13_5_ranking_ignores_scores_only():
    """Q13+Q14. Ranking reads score/count/IDs — never confidence/styleScore;
    winner delegates to the single ranking contract (no second algorithm)."""
    import inspect

    rank_names = set(rank_outfit_candidates.__code__.co_names)
    assert not ({"confidence", "styleScore", "style_score"} & rank_names)
    # Winner references only the single ranking contract (no second
    # algorithm, no score/confidence computation of its own).
    select_names = set(select_best_outfit_candidate.__code__.co_names)
    assert "rank_outfit_candidates" in select_names
    assert not ({"confidence", "styleScore", "style_score", "sorted"} & select_names)


def test_13_5_duplicate_inputs_preserved_deterministically():
    """E+R. Supplied duplicates are neither merged nor invented-around."""
    dup = _13_5_ranked((_LOW,), 40.0)
    out = rank_outfit_candidates([dup, _13_5_ranked((_HIGH,), 40.0), dup])
    assert len(out) == 3
    assert rank_outfit_candidates([dup, dup]) == [dup, dup]


def test_13_5_score_boundaries_and_sparse_shapes():
    """R. 0/100, empty buckets, and full candidates order sanely."""
    full = _13_5_Candidate(
        top_ids=(_LOW,), bottom_ids=(_MID,), outerwear_ids=(_HIGH,),
        footwear_ids=(_LOW,), accessory_ids=(_MID,), score=100.0)
    none = _13_5_Candidate(score=0.0)
    out = rank_outfit_candidates([none, full])
    assert out == [full, none]
    assert select_best_outfit_candidate([none, full]) is full


# ============================================================================
# STEP 13.11 — bounded multi-item generation (≤3 reps/category, ≤25 total).
# Generation ONLY: no scoring (scores stay 0.0), no ranking, no engine change.
# The 13.3 one-per-skeleton contract is superseded by the approved bounded
# contract (only the count test above changed shape; all other 13.3 tests
# hold verbatim for single-representative wardrobes).
# ============================================================================

from app.domain.services.analysis_rules import (
    generate_outfit_candidates as _13_11_generate,
)


def _13_11_ids(prefix, n):
    return [f"{prefix}-0000-4000-8000-{i:012d}" for i in range(n)]


def test_13_11_same_category_competition():
    """H. Top A and Top B both appear across candidates with Bottom A."""
    tops = _13_11_ids("aaaaaaaa", 2)
    bottom = _13_11_ids("bbbbbbbb", 1)[0]
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(bottom, "bottoms")])))
    by_top = {c.top_ids[0] for c in out}
    assert by_top == set(tops)
    assert all(c.bottom_ids == (bottom,) for c in out)


def test_13_11_representative_limit_three():
    """B. 10 tops → only the 3 lexically smallest participate (scoring-blind)."""
    tops = _13_11_ids("aaaaaaaa", 10)
    bottom = _13_11_ids("bbbbbbbb", 1)[0]
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(bottom, "bottoms")])))
    assert len(out) == 3
    assert [c.top_ids[0] for c in out] == sorted(tops)[:3]


def test_13_11_multi_category_combinations():
    """I. 3×3×3 across tops/bottoms/footwear → multiple distinct combos."""
    tops = _13_11_ids("aaaaaaaa", 3)
    bottoms = _13_11_ids("bbbbbbbb", 3)
    shoes = _13_11_ids("cccccccc", 3)
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms]
          + [(s, "footwear") for s in shoes])))
    triples = [c for c in out if c.footwear_ids]
    assert len(triples) > 1
    assert len({(c.top_ids, c.bottom_ids, c.footwear_ids) for c in triples}) == len(triples)
    assert len(out) <= 25


def test_13_11_global_cap_exactly_25():
    """J. Oversupply (4×4×3+outerwear+accessory) stops at exactly 25."""
    pairs = ([(t, "tops") for t in _13_11_ids("aaaaaaaa", 4)]
             + [(b, "bottoms") for b in _13_11_ids("bbbbbbbb", 4)]
             + [(s, "footwear") for s in _13_11_ids("cccccccc", 3)]
             + [(_OUTER, "outerwear"), (_ACC, "accessories")])
    assert len(_13_11_generate(_13_3_wardrobe(*pairs))) == 25


def test_13_11_sparse_single_items():
    """L. Single top → []; single bottom → []."""
    assert _13_11_generate(_13_3_wardrobe((_TOP, "tops"))) == []
    assert _13_11_generate(_13_3_wardrobe((_BOTTOM, "bottoms"))) == []


def test_13_11_multi_item_input_order_independence():
    """M. Shuffled multi-item wardrobe → identical candidates in order."""
    tops = _13_11_ids("aaaaaaaa", 3)
    bottoms = _13_11_ids("bbbbbbbb", 2)
    pairs = [(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms]
    assert (_13_11_generate(_13_3_wardrobe(*pairs))
            == _13_11_generate(_13_3_wardrobe(*reversed(pairs))))


def test_13_11_generated_ids_exist_in_wardrobe():
    """N. Every emitted ID comes from the input; five-category ceiling holds."""
    tops = _13_11_ids("aaaaaaaa", 4)
    bottoms = _13_11_ids("bbbbbbbb", 4)
    owned = set(tops + bottoms)
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms])))
    for c in out:
        ids = (c.top_ids + c.bottom_ids + c.outerwear_ids + c.footwear_ids
               + c.accessory_ids)
        assert set(ids) <= owned and len(ids) == len(set(ids))


def test_13_11_downstream_score_rank_select_compatible():
    """P. Generated candidates flow through scoring→ranking→selection."""
    from app.domain.services.analysis_rules import (
        rank_outfit_candidates, score_outfit_candidate,
        select_best_outfit_candidate)
    top, bottom = _13_11_ids("aaaaaaaa", 1)[0], _13_11_ids("bbbbbbbb", 1)[0]
    items = {top: _13_3_item(top, "tops"), bottom: _13_3_item(bottom, "bottoms")}
    out = _13_11_generate([items[top], items[bottom]])
    scored = [score_outfit_candidate(c, items, frozenset(), []) for c in out]
    winner = select_best_outfit_candidate(rank_outfit_candidates(scored))
    assert winner is not None
    assert set(winner.top_ids + winner.bottom_ids) == {top, bottom}


def test_13_11_exact_generation_bounds():
    """B+E. Per-category representatives capped at exactly 3; global cap 25."""
    from app.domain.services.analysis_rules import (
        _MAX_CANDIDATES, _MAX_REPRESENTATIVES_PER_CATEGORY)

    assert _MAX_REPRESENTATIVES_PER_CATEGORY == 3
    assert _MAX_CANDIDATES == 25


def test_13_11_generation_never_scores():
    """O. Generation must not call score_outfit_candidate(); every emitted
    candidate keeps neutral/default score values (multi-item wardrobe)."""
    tops = _13_11_ids("aaaaaaaa", 2)
    bottoms = _13_11_ids("bbbbbbbb", 2)
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms])))
    assert "score_outfit_candidate" not in _13_11_generate.__code__.co_names
    assert out
    for c in out:
        assert c.score == 0.0
        assert (c.compatibility, c.preference, c.favorite) == (0.0, 0.0, 0.0)


def test_13_11_sparse_single_non_core_item():
    """L. A lone item that cannot form tops+bottoms → [] (any category)."""
    assert _13_11_generate(_13_3_wardrobe((_SHOE, "footwear"))) == []
    assert _13_11_generate(_13_3_wardrobe((_OUTER, "outerwear"))) == []
    assert _13_11_generate(_13_3_wardrobe((_ACC, "accessories"))) == []


def test_13_11_top_bottom_footwear_multiple_with_reps():
    """L.6. top + bottom + footwear with several tops → multiple candidates."""
    tops = _13_11_ids("aaaaaaaa", 2)
    bottom = _13_11_ids("bbbbbbbb", 1)[0]
    shoe = _13_11_ids("cccccccc", 1)[0]
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(bottom, "bottoms"), (shoe, "footwear")])))
    assert len(out) == 4
    assert [c for c in out if not c.footwear_ids] != []
    assert [c for c in out if c.footwear_ids == (shoe,)] != []


def test_13_11_skeleton_major_prefix_order():
    """K. Earlier skeletons enumerate fully before later ones (2×2×1)."""
    tops = _13_11_ids("aaaaaaaa", 2)
    bottoms = _13_11_ids("bbbbbbbb", 2)
    shoe = _13_11_ids("cccccccc", 1)[0]
    out = _13_11_generate(_13_3_wardrobe(
        *([(t, "tops") for t in tops] + [(b, "bottoms") for b in bottoms]
          + [(shoe, "footwear")])))
    assert len(out) == 8
    assert [(c.top_ids, c.bottom_ids, c.footwear_ids) for c in out[:4]] == [
        ((tops[0],), (bottoms[0],), ()),
        ((tops[0],), (bottoms[1],), ()),
        ((tops[1],), (bottoms[0],), ()),
        ((tops[1],), (bottoms[1],), ()),
    ]
    assert all(c.footwear_ids == (shoe,) for c in out[4:])


def test_13_11_duplicate_inputs_deduped_multi_item():
    """G. Duplicated multi-item inputs emit each combination exactly once."""
    tops = _13_11_ids("aaaaaaaa", 2)
    bottom = _13_11_ids("bbbbbbbb", 1)[0]
    pairs = [(tops[0], "tops"), (tops[1], "tops"), (bottom, "bottoms")]
    assert (_13_11_generate(_13_3_wardrobe(*pairs))
            == _13_11_generate(_13_3_wardrobe(*(pairs + pairs))))
