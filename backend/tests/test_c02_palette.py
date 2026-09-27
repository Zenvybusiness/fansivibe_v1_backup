"""C-02-P palette implementation tests (STEP 2.8, owner-locked Option A).

Covers the 12 required proofs: per-palette +5 determinism; missing/unknown
evidence → 0; never a filter; +5 cap; conflict penalty intact; coverage max
35; color positive 5; compatibility ceiling exactly 70; preference/favorite
caps unchanged; tie-break unchanged. No Fit/Mood/preference/favorite
behavior asserted beyond their frozen caps.
"""

from types import SimpleNamespace

from app.domain.services.analysis_rules import (
    _CANDIDATE_COMPATIBILITY_MAX,
    _COLOR_CONFLICT_PENALTY,
    _COLOR_HARMONY_BONUS,
    _COVERAGE_PER_CATEGORY,
    _PALETTE_COLOR_SETS,
    _PALETTE_MAP_VERSION,
    _PALETTE_MATCH_BONUS,
    _color_points,
    _coverage_points,
    _palette_points,
    candidate_favorite_points,
    candidate_preference_points,
    compose_candidate_score,
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)
from app.domain.value_objects import OutfitCandidate


def _item(uid, category, color=None, material=None, fav=False):
    return SimpleNamespace(
        id=uid, category=category, color=color, material=material,
        is_favorite=fav,
    )


def _cand(**buckets):
    full = {"top": (), "bottom": (), "outer": (), "shoe": (), "acc": ()}
    full.update(buckets)
    return OutfitCandidate(
        top_ids=tuple(full["top"]), bottom_ids=tuple(full["bottom"]),
        outerwear_ids=tuple(full["outer"]), footwear_ids=tuple(full["shoe"]),
        accessory_ids=tuple(full["acc"]),
    )


def _members(*specs):
    """specs: (uid, category, color, material) → (candidate, items_by_id)."""
    items = {u: _item(u, c, color=co, material=m) for u, c, co, m in specs}
    by_cat = {}
    for u, c, _, _ in specs:
        by_cat.setdefault(c, []).append(u)
    cand = _cand(
        top=by_cat.get("tops", ()), bottom=by_cat.get("bottoms", ()),
        outer=by_cat.get("outerwear", ()), shoe=by_cat.get("footwear", ()),
        acc=by_cat.get("accessories", ()),
    )
    return cand, items


def _compat(cand, items, palette):
    from app.domain.services.analysis_rules import _candidate_members
    return _palette_points(_candidate_members(cand, items), palette)


# 1. Each locked palette mapping produces the expected deterministic +5.
def test_palette_each_mapping_scores_plus_five_deterministically():
    cases = [
        ("monochrome", [("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton")]),
        ("warm", [("t", "tops", "beige", "cotton"), ("b", "bottoms", "burgundy", "cotton")]),
        ("cool", [("t", "tops", "navy", "cotton"), ("b", "bottoms", "silver", "cotton")]),
    ]
    for palette, specs in cases:
        cand, items = _members(*specs)
        first = _compat(cand, items, palette)
        assert first == 5.0, palette
        assert _compat(cand, items, palette) == first  # deterministic repeat
    # Locked mapping content: only existing colors vocabulary codes.
    assert _PALETTE_COLOR_SETS["monochrome"] == frozenset({"black", "white", "charcoal", "grey"})
    assert _PALETTE_COLOR_SETS["warm"] == frozenset(
        {"beige", "burgundy", "olive", "khaki", "cream", "tan", "gold"})
    assert _PALETTE_COLOR_SETS["cool"] == frozenset({"navy", "light_blue", "indigo", "silver"})
    assert _PALETTE_MAP_VERSION == "c02-p/1"
    assert _PALETTE_MATCH_BONUS == 5.0


# 2/3. Missing / unknown palette evidence produces 0; unknown colors skipped.
def test_palette_missing_and_unknown_evidence_neutral():
    cand, items = _members(("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton"))
    assert _compat(cand, items, None) == 0.0
    assert _compat(cand, items, "spring") == 0.0  # invented palette → 0
    assert _compat(cand, items, "") == 0.0
    # All-unknown colors → 0 even for a valid palette.
    cand2, items2 = _members(("t", "tops", None, "cotton"), ("b", "bottoms", "", "cotton"))
    assert _compat(cand2, items2, "monochrome") == 0.0
    # Unknown member color skipped: known match still counts (missing stays missing).
    cand3, items3 = _members(("t", "tops", "black", "cotton"), ("b", "bottoms", None, "cotton"))
    assert _compat(cand3, items3, "monochrome") == 5.0
    # Unassigned codes (blush/stone) match no palette.
    cand4, items4 = _members(("t", "tops", "blush", "cotton"), ("b", "bottoms", "stone", "cotton"))
    for palette in ("monochrome", "warm", "cool"):
        assert _compat(cand4, items4, palette) == 0.0
    # Partial match (one member outside the set) → 0, never partial credit.
    cand5, items5 = _members(("t", "tops", "black", "cotton"), ("b", "bottoms", "navy", "cotton"))
    assert _compat(cand5, items5, "monochrome") == 0.0


# 4. Palette never hard-filters a candidate.
def test_palette_never_filters_candidates():
    import inspect
    # Generation takes no palette input at all (signal-only by construction).
    assert "palette" not in inspect.signature(generate_outfit_candidates).parameters
    assert "palette" not in inspect.signature(rank_outfit_candidates).parameters
    wardrobe = [
        _item("t", "tops", color="navy", material="cotton"),
        _item("b", "bottoms", color="white", material="cotton"),
    ]
    cands = generate_outfit_candidates(wardrobe)
    assert len(cands) == 1
    by_id = {i.id: i for i in wardrobe}
    ranked = rank_outfit_candidates(
        [score_outfit_candidate(c, by_id, frozenset(), ["casual"], preferred_palette="warm")
         for c in cands])
    assert len(ranked) == 1  # non-matching palette still ranks
    assert select_best_outfit_candidate(ranked) is not None


# 5. Palette contribution cannot exceed +5.
def test_palette_contribution_capped_at_five():
    cand, items = _members(
        ("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton"),
        ("o", "outerwear", "charcoal", "wool"), ("f", "footwear", "grey", "leather"),
        ("a", "accessories", "black", "silk"),
    )
    for palette in ("monochrome", "warm", "cool", None, "nope"):
        assert 0.0 <= _compat(cand, items, palette) <= 5.0
    assert _compat(cand, items, "monochrome") == 5.0


# 6. Existing color conflict/penalty behavior remains intact.
def test_color_conflict_penalty_intact():
    assert _COLOR_CONFLICT_PENALTY == -10.0
    assert _COLOR_HARMONY_BONUS == 5.0
    cand, items = _members(("t", "tops", "red", "cotton"), ("b", "bottoms", "olive", "denim"))
    from app.domain.services.analysis_rules import _candidate_members, _color_points
    members = _candidate_members(cand, items)
    assert _color_points(members) == -10.0
    out = score_outfit_candidate(cand, items)
    assert out.compatibility == 14.0  # 14 − 10 + 0 + 5 + 5
    # Neutral pair earns the reduced +5 harmony bonus.
    cand2, items2 = _members(("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton"))
    assert _color_points(_candidate_members(cand2, items2)) == 5.0


# 7. Coverage maximum is now 35.
def test_coverage_maximum_is_35():
    from app.domain.services.analysis_rules import _candidate_members, _coverage_points
    cand, items = _members(
        ("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton"),
        ("o", "outerwear", "charcoal", "wool"), ("f", "footwear", "grey", "leather"),
        ("a", "accessories", "black", "silk"),
    )
    assert _COVERAGE_PER_CATEGORY == 7.0
    assert _coverage_points(_candidate_members(cand, items)) == 35.0


# 8/9. Compatibility ceiling exactly 70; realistic maxed candidate == 60.
def test_compatibility_ceiling_exactly_70():
    assert _CANDIDATE_COMPATIBILITY_MAX == 70.0
    # Maxed realistic fixture: 35 coverage + 5 harmony + 5 material + 5 season
    # + 0 formality (footwear/accessories force mixed registers) + 5 occasion + 5 palette.
    cand, items = _members(
        ("t", "tops", "black", "cotton"), ("b", "bottoms", "white", "cotton"),
        ("o", "outerwear", "charcoal", "cotton"), ("f", "footwear", "grey", "cotton"),
        ("a", "accessories", "black", "cotton"),
    )
    out = score_outfit_candidate(cand, items, frozenset(), ["casual"], preferred_palette="monochrome")
    assert out.compatibility == 60.0
    assert out.score == 60.0
    # Ceiling enforced at compose: nothing can exceed 100 total.
    assert compose_candidate_score(70.0, 15.0, 15.0) == 100.0
    assert compose_candidate_score(999.0, 999.0, 999.0) == 100.0
    # End-to-end through the wired derive path: palette moves the winner, never breaks it.
    plain = score_outfit_candidate(cand, items, frozenset(), ["casual"])
    assert out.score == plain.score + 5.0


# 10. Preference +15 and Favorite +15 remain unchanged.
def test_preference_and_favorite_caps_unchanged():
    ids = [f"aaaaaaaa-0000-4000-8000-{i:012d}" for i in range(4)]
    assert candidate_preference_points(frozenset(ids), ids) == 15.0
    assert candidate_preference_points(frozenset(ids[:1]), ids[:1]) == 5.0
    assert candidate_favorite_points([True, True, True, True]) == 15.0
    assert candidate_favorite_points([True, False]) == 5.0


# 11. Deterministic tie-break unchanged (score → count → canonical IDs).
def test_tie_break_unchanged():
    low = OutfitCandidate(top_ids=("b",), bottom_ids=("b",), score=50.0)
    fuller = OutfitCandidate(top_ids=("a",), bottom_ids=("b", "c"), score=50.0)
    assert rank_outfit_candidates([low, fuller])[0] is fuller  # fuller first on tie
    a = OutfitCandidate(top_ids=("a",), bottom_ids=("c",), score=50.0)
    b = OutfitCandidate(top_ids=("b",), bottom_ids=("c",), score=50.0)
    assert rank_outfit_candidates([b, a]) == [a, b]  # lexical IDs break remaining ties
    hi = OutfitCandidate(top_ids=("z",), score=90.0)
    assert rank_outfit_candidates([low, hi]) == [hi, low]  # score still primary
