"""C-03 preferred_item_ids implementation tests (STEP 3, owner-locked).

Explicit user-selected preferred wardrobe items: optional
`preferredItemIds?: UUID[]` on #41, threaded request → derive → score.
Absent/null/[] ≡ empty baseline; malformed → 422; unknown/foreign →
ignored to 0 (never 404); +5/item cap 15 soft ranking only; OI
+0.05/cap 0.15 independent; C-02 untouched; no filtering/generation/
tie-break/budget changes. DB-free.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas.outfits import OutfitGenerateRequest
from app.application.outfits import (
    GenerateOutfit,
    _normalize_preferred_item_ids,
)
from app.domain.services.analysis_rules import (
    candidate_preference_points,
    compose_candidate_score,
    generate_outfit_candidates,
    preference_contribution,
    rank_outfit_candidates,
    score_outfit_candidate,
)
from app.domain.value_objects import OutfitCandidate

USER = uuid4()
T1 = uuid4()
T2 = uuid4()
B1 = uuid4()
B2 = uuid4()

PREFS = {
    "occasion": "office",
    "mood": "classic",
    "fit": "nope",
    "colorPalette": "nope",
}


def _item(uid, category, color="black", material="cotton", fav=False, fit=None, conf=None):
    return SimpleNamespace(
        id=uid, category=category, color=color, material=material,
        is_favorite=fav, fit=fit, fit_confidence=conf,
    )


def _cand(**buckets):
    full = {"top": (), "bottom": (), "outer": (), "shoe": (), "acc": ()}
    full.update(buckets)
    return OutfitCandidate(
        top_ids=tuple(full["top"]), bottom_ids=tuple(full["bottom"]),
        outerwear_ids=tuple(full["outer"]), footwear_ids=tuple(full["shoe"]),
        accessory_ids=tuple(full["acc"]),
    )


def _pair():
    """One tops+bottoms candidate over UUID-string IDs."""
    top, bottom = str(T1), str(B1)
    cand = _cand(top=(top,), bottom=(bottom,))
    items = {
        top: _item(top, "tops"),
        bottom: _item(bottom, "bottoms"),
    }
    return cand, items


# --- wire schema -----------------------------------------------------------

def test_schema_absent_is_none():
    assert OutfitGenerateRequest(**PREFS).preferredItemIds is None


def test_schema_null_is_none():
    assert OutfitGenerateRequest(**{**PREFS, "preferredItemIds": None}).preferredItemIds is None


def test_schema_empty_list_is_empty():
    assert OutfitGenerateRequest(**{**PREFS, "preferredItemIds": []}).preferredItemIds == []


def test_schema_valid_uuids():
    req = OutfitGenerateRequest(**{**PREFS, "preferredItemIds": [str(T1), str(B1)]})
    assert req.preferredItemIds == [T1, B1]


def test_schema_malformed_uuid_rejected_422():
    with pytest.raises(ValidationError):
        OutfitGenerateRequest(**{**PREFS, "preferredItemIds": ["not-a-uuid"]})


# --- normalizer ------------------------------------------------------------

def test_normalize_none_and_empty():
    assert _normalize_preferred_item_ids(None) == frozenset()
    assert _normalize_preferred_item_ids([]) == frozenset()


def test_normalize_uuid_objects_and_dedup():
    out = _normalize_preferred_item_ids([T1, T1, str(B1)])
    assert out == frozenset([str(T1), str(B1)])


def test_normalize_non_list_degrades_empty():
    assert _normalize_preferred_item_ids("nope") == frozenset()


# --- ranking ---------------------------------------------------------------

def test_plus_five_per_match_cap_15():
    cand, items = _pair()
    one = score_outfit_candidate(cand, items, frozenset([str(T1)]))
    assert one.preference == 5.0
    two = score_outfit_candidate(cand, items, frozenset([str(T1), str(B1)]))
    assert two.preference == 10.0
    ids = [str(uuid4()) for _ in range(4)]
    cand4 = _cand(top=(ids[0],), bottom=tuple(ids[1:]))
    items4 = {i: _item(i, "tops" if n == 0 else "bottoms") for n, i in enumerate(ids)}
    assert score_outfit_candidate(cand4, items4, frozenset(ids)).preference == 15.0


def test_duplicates_do_not_stack():
    cand, items = _pair()
    single = score_outfit_candidate(cand, items, frozenset([str(T1)]))
    # Set semantics: the same ID twice is still one match (+5).
    assert candidate_preference_points(frozenset([str(T1)]), [str(T1), str(T1)]) == 5.0
    assert single.preference == 5.0


def test_nonexistent_and_foreign_ids_contribute_zero():
    cand, items = _pair()
    ghost = str(uuid4())
    assert score_outfit_candidate(cand, items, frozenset([ghost])).preference == 0.0
    # Foreign-user ID can never match owner-scoped candidates → 0.
    assert score_outfit_candidate(cand, items, frozenset([str(uuid4())])).preference == 0.0


def test_empty_input_identical_to_baseline():
    cand, items = _pair()
    base = score_outfit_candidate(cand, items)
    assert score_outfit_candidate(cand, items, None) == base
    assert score_outfit_candidate(cand, items, frozenset()) == base


def test_no_filtering_or_generation_effect():
    wardrobe = [
        _item(str(T1), "tops"), _item(str(T2), "tops"),
        _item(str(B1), "bottoms"), _item(str(B2), "bottoms"),
    ]
    cands = generate_outfit_candidates(wardrobe)
    assert "preferred" not in inspect.signature(generate_outfit_candidates).parameters
    by_id = {i.id: i for i in wardrobe}
    plain = rank_outfit_candidates(
        [score_outfit_candidate(c, by_id, frozenset(), ["office"]) for c in cands]
    )
    boosted = rank_outfit_candidates(
        [score_outfit_candidate(c, by_id, frozenset([str(T1)]), ["office"]) for c in cands]
    )
    assert len(boosted) == len(plain) > 0  # boost reorders, never removes


def test_preferred_boost_is_soft_ranking_delta():
    wardrobe = [
        _item(str(T1), "tops"), _item(str(T2), "tops"),
        _item(str(B1), "bottoms"), _item(str(B2), "bottoms"),
    ]
    by_id = {i.id: i for i in wardrobe}
    cands = generate_outfit_candidates(wardrobe)
    for cand in cands:
        base = score_outfit_candidate(cand, by_id, frozenset(), ["office"])
        boosted = score_outfit_candidate(
            cand, by_id, frozenset([str(T1)]), ["office"]
        )
        delta = round(boosted.score - base.score, 2)
        assert delta in (0.0, 5.0)
        assert boosted.score <= 100.0


# --- C-02 regression --------------------------------------------------------

def test_c02_palette_plus_five_intact():
    cand, items = _pair()  # black/white → monochrome
    out = score_outfit_candidate(cand, items, frozenset(), ["office"], preferred_palette="monochrome")
    plain = score_outfit_candidate(cand, items, frozenset(), ["office"])
    assert out.compatibility == plain.compatibility + 5.0


def test_c02_fit_plus_five_intact():
    top, bottom = str(T1), str(B1)
    cand = _cand(top=(top,), bottom=(bottom,))
    items = {
        top: _item(top, "tops", fit="slim", conf=None),
        bottom: _item(bottom, "bottoms", fit="slim", conf=None),
    }
    items[top].fit_confidence = 0.9
    items[bottom].fit_confidence = 0.9
    out = score_outfit_candidate(cand, items, frozenset(), [], preferred_fit="slim")
    plain = score_outfit_candidate(cand, items, frozenset(), [])
    assert out.compatibility == plain.compatibility + 5.0


def test_total_ceiling_100_and_tie_break():
    assert compose_candidate_score(70.0, 15.0, 15.0) == 100.0
    assert compose_candidate_score(999.0, 999.0, 999.0) == 100.0
    low = OutfitCandidate(top_ids=("b",), bottom_ids=("b",), score=50.0)
    fuller = OutfitCandidate(top_ids=("a",), bottom_ids=("b", "c"), score=50.0)
    assert rank_outfit_candidates([low, fuller])[0] is fuller


# --- OI lane independent ----------------------------------------------------

def test_oi_lane_scales_separately():
    ids = [str(uuid4()) for _ in range(4)]
    assert preference_contribution(frozenset(ids), ids) == 0.15
    assert candidate_preference_points(frozenset(ids), ids) == 15.0
    one = str(uuid4())
    assert preference_contribution(frozenset([one]), [one]) == 0.05
    assert candidate_preference_points(frozenset([one]), [one]) == 5.0


# --- derive path ------------------------------------------------------------

class _FakeWardrobe:
    def __init__(self, records):
        self._records = records

    def get_for_user(self, *, user_id, page, page_size, **kwargs):
        return list(self._records), len(self._records)


class _FakeUserState:
    def get_profile(self, *, user_id):
        return None


def _record(uid, category, name):
    return SimpleNamespace(
        id=uid, category=category, name=name, color="black",
        material="cotton", is_favorite=False, fit=None, fit_confidence=None,
    )


def _use_case():
    records = [
        _record(T1, "tops", "Tee A"),
        _record(T2, "tops", "Tee B"),
        _record(B1, "bottoms", "Jeans"),
        _record(B2, "bottoms", "Chinos"),
    ]
    return GenerateOutfit(
        wardrobe_items=_FakeWardrobe(records), user_state=_FakeUserState()
    )


def _derive(use_case, preferred):
    return use_case.derive_with_reason(
        user_id=USER,
        occasion="office",
        mood="classic",
        fit="nope",
        color_palette="nope",
        preferred_item_ids=preferred,
    )


def test_derive_empty_identical_to_baseline():
    use_case = _use_case()
    base, _ = _derive(use_case, None)
    empty, _ = _derive(use_case, [])
    assert base is not None and empty is not None
    assert base.match_score == empty.match_score
    assert [c.id for c in base.components] == [c.id for c in empty.components]


def test_derive_foreign_id_matches_baseline():
    use_case = _use_case()
    base, _ = _derive(use_case, None)
    foreign, _ = _derive(use_case, [uuid4()])
    assert base is not None and foreign is not None
    assert foreign.match_score == base.match_score
    assert [c.id for c in foreign.components] == [c.id for c in base.components]


def test_derive_duplicates_do_not_stack():
    use_case = _use_case()
    single, _ = _derive(use_case, [T1])
    double, _ = _derive(use_case, [T1, T1, T1])
    assert single is not None and double is not None
    assert double.match_score == single.match_score


def test_derive_signature_backward_compatible():
    assert "preferred_item_ids" in inspect.signature(
        GenerateOutfit.derive_with_reason
    ).parameters
    default = inspect.signature(GenerateOutfit.derive_with_reason).parameters[
        "preferred_item_ids"
    ].default
    assert default is None  # existing callers without the kwarg keep baseline


def test_non_outfit_callers_intentionally_left_empty():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    events = (root / "application" / "events.py").read_text()
    today = (root / "application" / "today.py").read_text()
    main = (root / "main.py").read_text()
    # No explicit preference source on these paths: still literal empty,
    # assistant entry still omits the kwarg (baseline preserved).
    assert "preferredItemIds" not in events
    assert "preferredItemIds" not in today
    assert "score_outfit_candidate(candidate, items_by_id, frozenset(), occasions)" in events
    assert "score_outfit_candidate(candidate, items_by_id, frozenset(), occasions)" in today
    assert "preferred_item_ids" not in main
