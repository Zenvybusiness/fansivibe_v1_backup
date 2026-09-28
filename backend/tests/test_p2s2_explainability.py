"""Tests for Phase 2 Step 2 — explainable + actionable AI Stylist reasons.

Every reason must be grounded in a real score contribution from the
existing (unchanged) recommendation engine:

 1. palette reason only with palette contribution
 2. fit reason only with fit contribution
 3. preferred-item reason only when preferred item contributes
 4. favorite reason only when favorite contributes
 5. positive feedback reason only with positive feedback
 6. negative feedback reason only with negative feedback
 7. wear reason only with wear contribution
 8. no evidence -> no fabricated reason
 9. duplicate reasons are removed
10. reason ordering is deterministic
11. existing score is unchanged
12. API serialization works
13. (Flutter rendering — covered in Dart `outfit_recommendation_reasons_test.dart`)
14. empty reasons do not crash (backend: empty list serializes; Flutter: fallback copy)
15. existing C-02/C-03/C-05 suites remain green (run separately)
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.application.outfits import (
    FIT_REASON,
    OCCASION_MATCH_REASON,
    PALETTE_REASON,
    PREFERRED_ITEM_REASON,
    _to_recommendation,
)
from app.api.routers.outfits import _record_to_outfit_schema
from app.domain.services.analysis_rules import (
    compose_candidate_score,
    score_outfit_candidate,
)
from app.domain.value_objects import FeedbackContext, OutfitCandidate

T1 = uuid4()
T2 = uuid4()
B1 = uuid4()
B2 = uuid4()


def _item(item_id, category, color="black", material="cotton",
          is_favorite=False, fit="slim", fit_confidence=0.8, name="Test Item"):
    return SimpleNamespace(
        id=str(item_id),
        name=name,
        category=category,
        color=color,
        material=material,
        is_favorite=is_favorite,
        fit=fit,
        fit_confidence=fit_confidence,
    )


def _cand(top, bottom):
    return OutfitCandidate(top_ids=(str(top),), bottom_ids=(str(bottom),))


def _rec(winner, records, **kwargs):
    params = dict(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=winner,
        by_record=records,
    )
    params.update(kwargs)
    return _to_recommendation(**params)


def _records(t_color="black", b_color="black", fav=False,
             fit="slim", conf=0.8):
    return {
        str(T1): _item(T1, "tops", color=t_color, fit=fit, fit_confidence=conf,
                       is_favorite=fav, name="Top"),
        str(B1): _item(B1, "bottoms", color=b_color, fit=fit, fit_confidence=conf,
                       is_favorite=fav, name="Bottom"),
    }


# 1. palette reason appears only with palette contribution
def test_1_palette_reason_only_with_contribution():
    cand = _cand(T1, B1)
    items = _records(t_color="black", b_color="white")  # monochrome set
    scored = score_outfit_candidate(cand, items, preferred_palette="monochrome")
    rec = _rec(scored, items)
    assert PALETTE_REASON in rec.reasons

    miss = score_outfit_candidate(cand, items, preferred_palette="warm")
    rec_miss = _rec(miss, items, color_palette="warm")
    assert PALETTE_REASON not in rec_miss.reasons


# 2. fit reason appears only with fit contribution
def test_2_fit_reason_only_with_contribution():
    cand = _cand(T1, B1)
    items = _records(fit="slim", conf=0.8)
    scored = score_outfit_candidate(cand, items, preferred_fit="slim")
    rec = _rec(scored, items)
    assert FIT_REASON in rec.reasons

    # `tailored` request is unsupported -> neutral -> no reason
    miss = score_outfit_candidate(cand, items, preferred_fit="tailored")
    rec_miss = _rec(miss, items, fit="tailored")
    assert FIT_REASON not in rec_miss.reasons

    # low confidence evidence -> neutral -> no reason
    low = _records(fit="slim", conf=0.2)
    low_scored = score_outfit_candidate(cand, low, preferred_fit="slim")
    rec_low = _rec(low_scored, low)
    assert FIT_REASON not in rec_low.reasons


# 3. preferred-item reason appears only when preferred item contributes
def test_3_preferred_item_reason_only_when_contributing():
    cand = _cand(T1, B1)
    items = _records()
    scored = score_outfit_candidate(
        cand, items, preferred_item_ids=frozenset([str(T1)]))
    assert scored.preference > 0
    assert PREFERRED_ITEM_REASON in _rec(scored, items).reasons

    plain = score_outfit_candidate(cand, items)
    assert plain.preference == 0.0
    assert PREFERRED_ITEM_REASON not in _rec(plain, items).reasons


# 4. favorite reason appears only when favorite contributes
def test_4_favorite_reason_only_when_contributing():
    cand = _cand(T1, B1)
    items = _records(fav=True)
    scored = score_outfit_candidate(cand, items)
    assert scored.favorite > 0
    rec = _rec(scored, items)
    assert any("favorite" in r.lower() for r in rec.reasons)

    plain_items = _records(fav=False)
    plain = score_outfit_candidate(cand, plain_items)
    assert plain.favorite == 0.0
    rec_plain = _rec(plain, plain_items)
    assert not any("favorite" in r.lower() for r in rec_plain.reasons)

    # gate: favorited names but zero favorite sub-score -> no reason
    zero_fav = OutfitCandidate(
        top_ids=(str(T1),), bottom_ids=(str(B1),),
        favorite=0.0, score=50.0,
    )
    rec_gate = _rec(zero_fav, items)
    assert not any("favorite" in r.lower() for r in rec_gate.reasons)


# 5. positive feedback reason appears only with positive feedback
def test_5_positive_feedback_only_with_positive():
    cand = _cand(T1, B1)
    items = _records()
    ctx = FeedbackContext(
        liked_outfits=(frozenset([str(T1), str(B1)]),))
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)
    assert scored.feedback > 0
    rec = _rec(scored, items)
    assert "Similar to outfits you've liked" in rec.reasons
    assert "Reduced because of previous negative feedback" not in rec.reasons

    neutral = score_outfit_candidate(cand, items)
    rec_neutral = _rec(neutral, items)
    assert "Similar to outfits you've liked" not in rec_neutral.reasons


# 6. negative feedback reason appears only with negative feedback
def test_6_negative_feedback_only_with_negative():
    cand = _cand(T1, B1)
    items = _records()
    ctx = FeedbackContext(
        disliked_outfits=(frozenset([str(T1), str(B1)]),))
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)
    assert scored.feedback < 0
    rec = _rec(scored, items)
    assert "Reduced because of previous negative feedback" in rec.reasons
    assert "Similar to outfits you've liked" not in rec.reasons


# 7. wear reason appears only with wear contribution
def test_7_wear_reason_only_with_wear():
    cand = _cand(T1, B1)
    items = _records()
    ctx = FeedbackContext(
        worn_combinations=(frozenset([str(T1), str(B1)]),))
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)
    assert scored.wear > 0
    assert "Previously worn combination" in _rec(scored, items).reasons

    neutral = score_outfit_candidate(cand, items)
    assert "Previously worn combination" not in _rec(neutral, items).reasons


# 8. no evidence -> no fabricated reason
def test_8_no_evidence_no_fabricated_reason():
    cand = _cand(T1, B1)
    items = {
        str(T1): _item(T1, "tops", color="blush", fit="tailored",
                       fit_confidence=0.9),
        str(B1): _item(B1, "bottoms", color="stone", fit="tailored",
                       fit_confidence=0.9),
    }
    scored = score_outfit_candidate(
        cand, items, preferred_palette="warm", preferred_fit="tailored",
        preferred_occasions=["gala-night-xyz"],
    )
    assert scored.preference == 0.0
    assert scored.favorite == 0.0
    assert scored.feedback == 0.0
    assert scored.wear == 0.0
    rec = _rec(scored, items, color_palette="warm", fit="tailored",
               occasion="gala-night-xyz",
               occasions=["gala-night-xyz"])
    assert len(rec.reasons) == 2  # only the always-true base lines
    assert rec.reasons[0].startswith("Picked for a ")
    assert rec.reasons[1].startswith("Covers ")
    for banned in (PALETTE_REASON, FIT_REASON, PREFERRED_ITEM_REASON,
                   OCCASION_MATCH_REASON, "Similar to outfits you've liked",
                   "Reduced because of previous negative feedback",
                   "Previously worn combination"):
        assert banned not in rec.reasons


# 9. duplicate reasons are removed
def test_9_duplicate_reasons_removed():
    cand = _cand(T1, B1)
    dup_items = {
        str(T1): _item(T1, "tops", is_favorite=True, name="Same Name"),
        str(B1): _item(B1, "bottoms", is_favorite=True, name="Same Name"),
    }
    scored = score_outfit_candidate(cand, dup_items)
    rec = _rec(scored, dup_items)
    assert len(rec.reasons) == len(set(rec.reasons))


# 10. reason ordering is deterministic
def test_10_reason_ordering_deterministic():
    cand = _cand(T1, B1)
    items = _records(t_color="black", b_color="white", fav=True)
    ctx = FeedbackContext(
        liked_outfits=(frozenset([str(T1), str(B1)]),),
        worn_combinations=(frozenset([str(T1), str(B1)]),),
    )
    scored = score_outfit_candidate(
        cand, items, preferred_item_ids=frozenset([str(T1)]),
        preferred_occasions=["casual"], preferred_palette="monochrome",
        preferred_fit="slim", feedback_context=ctx,
    )
    first = _rec(scored, items, occasions=["casual"]).reasons
    second = _rec(scored, items, occasions=["casual"]).reasons
    assert first == second
    idx = {r: i for i, r in enumerate(first)}
    ordered = [PALETTE_REASON, FIT_REASON, PREFERRED_ITEM_REASON,
               OCCASION_MATCH_REASON, "Similar to outfits you've liked",
               "Previously worn combination"]
    present = [r for r in ordered if r in idx]
    assert [idx[r] for r in present] == sorted(idx[r] for r in present)
    # base context lines stay first
    assert first[0].startswith("Picked for a ")
    assert first[1].startswith("Covers ")


# 11. existing score is unchanged
def test_11_existing_score_unchanged():
    cand = _cand(T1, B1)
    items = _records(t_color="black", b_color="black")
    before = score_outfit_candidate(
        cand, items, preferred_item_ids=frozenset([str(T1)]),
        preferred_palette="monochrome", preferred_fit="slim",
    )
    # palette +5 / fit +5 / preferred +5/item: spot-check locked weights
    plain = score_outfit_candidate(cand, items)
    pal = score_outfit_candidate(cand, items, preferred_palette="monochrome")
    assert pal.compatibility == plain.compatibility + 5.0
    fit = score_outfit_candidate(cand, items, preferred_fit="slim")
    assert fit.compatibility == plain.compatibility + 5.0
    assert before.preference == 5.0
    # explanation must not mutate the winner's score
    snapshot = before.score
    _rec(before, items)
    assert before.score == snapshot
    # budget clamps hold
    assert compose_candidate_score(70.0, 15.0, 15.0, feedback=6.0,
                                   wear=2.0) == 100.0


# 12. API serialization works
def test_12_api_serialization():
    cand = _cand(T1, B1)
    items = _records(t_color="black", b_color="white", fav=True)
    scored = score_outfit_candidate(
        cand, items, preferred_palette="monochrome",
        preferred_occasions=["casual"],
    )
    rec = _rec(scored, items, occasions=["casual"])
    schema = _record_to_outfit_schema(rec)
    assert isinstance(schema.reasons, list)
    assert all(isinstance(r, str) for r in schema.reasons)
    assert PALETTE_REASON in schema.reasons
    assert 0 <= schema.matchScore <= 1
    dumped = schema.model_dump()
    assert dumped["reasons"] == rec.reasons


# 14. empty reasons do not crash (backend serializes []; Flutter covers UI)
def test_14_empty_reasons_serialize():
    cand = OutfitCandidate(top_ids=(str(T1),), bottom_ids=(str(B1),),
                           score=50.0)
    rec = _rec(cand, _records())
    rec_empty = rec  # reasons never None; explicit empty also serializes
    assert isinstance(rec_empty.reasons, list)
    from app.domain.ports.repositories import OutfitRecommendation
    from dataclasses import replace
    as_empty = replace(rec, reasons=[])
    schema = _record_to_outfit_schema(as_empty)
    assert schema.reasons == []
    assert isinstance(OutfitRecommendation, type)
