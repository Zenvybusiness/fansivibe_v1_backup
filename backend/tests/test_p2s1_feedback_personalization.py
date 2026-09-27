"""Tests for Phase 2 Step 1 — Feedback-Driven AI Stylist Personalization.

Validates the bounded deterministic personalization term consuming existing
user feedback (likes/dislikes) and wear history:
  1. no feedback → neutral
  2. like → positive bounded effect
  3. dislike → negative bounded effect
  4. repeated like → does not exceed cap
  5. repeated dislike → does not become unlimited
  6. contradictory like/dislike → deterministic result
  7. wear → only if safely supported
  8. preferredItemIds remains independent
  9. existing palette scoring unchanged
  10. existing fit scoring unchanged
  11. final score remains <= 100
  12. deterministic tie-break remains unchanged
  13. explanation reason only appears when evidence exists
  14. build_feedback_context correctly extracts and orders evidence
  15. GenerateOutfit end-to-end integration with feedback/wear
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.application.outfits import GenerateOutfit, _derive_outfit, _to_recommendation
from app.domain.ports.repositories import (
    FeedbackEventRecord,
    OutfitComponent,
    SavedLookRecord,
    WearEventRecord,
)
from app.domain.services.analysis_rules import (
    _FEEDBACK_DISLIKE_EXACT_PENALTY,
    _FEEDBACK_DISLIKE_SIMILAR_PENALTY,
    _FEEDBACK_LIKE_EXACT_BONUS,
    _FEEDBACK_LIKE_SIMILAR_BONUS,
    _FEEDBACK_NEGATIVE_CAP,
    _FEEDBACK_POSITIVE_CAP,
    _WEAR_BONUS_CAP,
    _WEAR_COMBINATION_BONUS,
    _WEAR_SIMILAR_BONUS,
    build_feedback_context,
    candidate_feedback_points,
    candidate_wear_points,
    compose_candidate_score,
    rank_outfit_candidates,
    score_outfit_candidate,
)
from app.domain.value_objects import FeedbackContext, OutfitCandidate

USER = uuid4()
T1 = uuid4()
T2 = uuid4()
B1 = uuid4()
B2 = uuid4()
S1 = uuid4()
A1 = uuid4()


def _item(item_id, category, color="black", material="cotton", is_favorite=False, fit="slim", fit_confidence=0.8, name="Test Item"):
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


def _cand(top, bottom, footwear=None, accessory=None):
    return OutfitCandidate(
        top_ids=(str(top),),
        bottom_ids=(str(bottom),),
        footwear_ids=((str(footwear),) if footwear else ()),
        accessory_ids=((str(accessory),) if accessory else ()),
    )


# ---------------------------------------------------------------------------
# Requirement 1: no feedback → neutral
# ---------------------------------------------------------------------------


def test_1_no_feedback_neutral():
    cand = _cand(T1, B1)
    items = {str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")}

    base = score_outfit_candidate(cand, items)
    with_none = score_outfit_candidate(cand, items, feedback_context=None)
    with_empty = score_outfit_candidate(cand, items, feedback_context=FeedbackContext())

    assert base.score == with_none.score == with_empty.score
    assert with_none.feedback == 0.0
    assert with_none.wear == 0.0
    assert with_empty.feedback == 0.0
    assert with_empty.wear == 0.0

    # No feedback or wear explanation reasons
    rec = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=with_none,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert not any("liked" in r.lower() for r in rec.reasons)
    assert not any("negative" in r.lower() for r in rec.reasons)
    assert not any("worn" in r.lower() for r in rec.reasons)


# ---------------------------------------------------------------------------
# Requirement 2: like → positive bounded effect
# ---------------------------------------------------------------------------


def test_2_like_positive_bounded_effect():
    cand = _cand(T1, B1, S1)
    items = {
        str(T1): _item(T1, "tops"),
        str(B1): _item(B1, "bottoms"),
        str(S1): _item(S1, "footwear"),
    }
    base = score_outfit_candidate(cand, items)

    # Exact match like
    ctx_exact = FeedbackContext(liked_outfits=(frozenset([str(T1), str(B1), str(S1)]),))
    exact_scored = score_outfit_candidate(cand, items, feedback_context=ctx_exact)

    assert exact_scored.feedback == _FEEDBACK_LIKE_EXACT_BONUS
    assert exact_scored.score == base.score + _FEEDBACK_LIKE_EXACT_BONUS

    # Partial/similar match like (shares T1 and B1 >= 2 items)
    ctx_similar = FeedbackContext(liked_outfits=(frozenset([str(T1), str(B1)]),))
    similar_scored = score_outfit_candidate(cand, items, feedback_context=ctx_similar)

    assert similar_scored.feedback == _FEEDBACK_LIKE_SIMILAR_BONUS
    assert similar_scored.score == base.score + _FEEDBACK_LIKE_SIMILAR_BONUS

    # Explanation reason includes positive like statement
    rec = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=exact_scored,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms"), str(S1): _item(S1, "footwear")},
    )
    assert "Similar to outfits you've liked" in rec.reasons


# ---------------------------------------------------------------------------
# Requirement 3: dislike → negative bounded effect
# ---------------------------------------------------------------------------


def test_3_dislike_negative_bounded_effect():
    cand = _cand(T1, B1, S1)
    items = {
        str(T1): _item(T1, "tops"),
        str(B1): _item(B1, "bottoms"),
        str(S1): _item(S1, "footwear"),
    }
    base = score_outfit_candidate(cand, items)

    # Exact match dislike
    ctx_exact = FeedbackContext(disliked_outfits=(frozenset([str(T1), str(B1), str(S1)]),))
    disliked_scored = score_outfit_candidate(cand, items, feedback_context=ctx_exact)

    assert disliked_scored.feedback == _FEEDBACK_DISLIKE_EXACT_PENALTY
    assert disliked_scored.score == base.score + _FEEDBACK_DISLIKE_EXACT_PENALTY
    assert disliked_scored.score > 0  # NOT blacklisted, score remains positive

    # Explanation reason includes negative feedback reduction statement
    rec = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=disliked_scored,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms"), str(S1): _item(S1, "footwear")},
    )
    assert "Reduced because of previous negative feedback" in rec.reasons


# ---------------------------------------------------------------------------
# Requirement 4: repeated like → does not exceed cap
# ---------------------------------------------------------------------------


def test_4_repeated_like_does_not_exceed_cap():
    cand = _cand(T1, B1, S1)
    items = {
        str(T1): _item(T1, "tops"),
        str(B1): _item(B1, "bottoms"),
        str(S1): _item(S1, "footwear"),
    }
    # 5 liked outfits matching candidate pieces
    liked = tuple(
        frozenset([str(T1), str(B1), str(uuid4())]) for _ in range(5)
    )
    ctx = FeedbackContext(liked_outfits=liked)
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)

    assert scored.feedback == _FEEDBACK_POSITIVE_CAP
    assert scored.feedback == 6.0


# ---------------------------------------------------------------------------
# Requirement 5: repeated dislike → does not become unlimited
# ---------------------------------------------------------------------------


def test_5_repeated_dislike_does_not_become_unlimited():
    cand = _cand(T1, B1, S1)
    items = {
        str(T1): _item(T1, "tops"),
        str(B1): _item(B1, "bottoms"),
        str(S1): _item(S1, "footwear"),
    }
    # 5 disliked outfits matching candidate pieces
    disliked = tuple(
        frozenset([str(T1), str(B1), str(uuid4())]) for _ in range(5)
    )
    ctx = FeedbackContext(disliked_outfits=disliked)
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)

    assert scored.feedback == _FEEDBACK_NEGATIVE_CAP
    assert scored.feedback == -6.0


# ---------------------------------------------------------------------------
# Requirement 6: contradictory like/dislike → deterministic result
# ---------------------------------------------------------------------------


def test_6_contradictory_like_dislike_deterministic_result():
    cand = _cand(T1, B1)
    items = {str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")}
    base = score_outfit_candidate(cand, items)

    # One liked outfit (+4) and one disliked outfit (-4) for the same combination
    ctx = FeedbackContext(
        liked_outfits=(frozenset([str(T1), str(B1)]),),
        disliked_outfits=(frozenset([str(T1), str(B1)]),),
    )
    scored = score_outfit_candidate(cand, items, feedback_context=ctx)

    assert scored.feedback == 0.0
    assert scored.score == base.score

    rec = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=scored,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert not any("liked" in r.lower() for r in rec.reasons)
    assert not any("negative" in r.lower() for r in rec.reasons)


# ---------------------------------------------------------------------------
# Requirement 7: wear → only if safely supported
# ---------------------------------------------------------------------------


def test_7_wear_safely_supported():
    cand = _cand(T1, B1, S1)
    items = {
        str(T1): _item(T1, "tops"),
        str(B1): _item(B1, "bottoms"),
        str(S1): _item(S1, "footwear"),
    }
    base = score_outfit_candidate(cand, items)

    # Exact worn combination
    ctx_exact = FeedbackContext(worn_combinations=(frozenset([str(T1), str(B1), str(S1)]),))
    exact_scored = score_outfit_candidate(cand, items, feedback_context=ctx_exact)

    assert exact_scored.wear == _WEAR_COMBINATION_BONUS
    assert exact_scored.score == base.score + _WEAR_COMBINATION_BONUS

    # Partial worn combination (>=2 items worn together)
    ctx_partial = FeedbackContext(worn_combinations=(frozenset([str(T1), str(B1)]),))
    partial_scored = score_outfit_candidate(cand, items, feedback_context=ctx_partial)

    assert partial_scored.wear == _WEAR_SIMILAR_BONUS
    assert partial_scored.score == base.score + _WEAR_SIMILAR_BONUS

    # Cap holds
    ctx_multi = FeedbackContext(
        worn_combinations=(
            frozenset([str(T1), str(B1), str(S1)]),
            frozenset([str(T1), str(B1)]),
        )
    )
    multi_scored = score_outfit_candidate(cand, items, feedback_context=ctx_multi)
    assert multi_scored.wear == _WEAR_BONUS_CAP

    # Reason rendered
    rec = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=exact_scored,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms"), str(S1): _item(S1, "footwear")},
    )
    assert "Previously worn combination" in rec.reasons


# ---------------------------------------------------------------------------
# Requirement 8: preferredItemIds remains independent
# ---------------------------------------------------------------------------


def test_8_preferred_item_ids_remains_independent():
    cand = _cand(T1, B1)
    items = {str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")}

    # Base preference with explicit user-selected preferred_item_ids
    pref_scored = score_outfit_candidate(cand, items, preferred_item_ids=frozenset([str(T1)]))
    assert pref_scored.preference == 5.0
    assert pref_scored.feedback == 0.0

    # With like added: preference sub-score remains exactly 5.0
    ctx_like = FeedbackContext(liked_outfits=(frozenset([str(T1), str(B1)]),))
    both_scored = score_outfit_candidate(
        cand, items, preferred_item_ids=frozenset([str(T1)]), feedback_context=ctx_like
    )
    assert both_scored.preference == 5.0
    assert both_scored.feedback == _FEEDBACK_LIKE_EXACT_BONUS
    assert both_scored.score == pref_scored.score + _FEEDBACK_LIKE_EXACT_BONUS


# ---------------------------------------------------------------------------
# Requirement 9: existing palette scoring unchanged
# ---------------------------------------------------------------------------


def test_9_existing_palette_scoring_unchanged():
    cand = _cand(T1, B1)
    # Both items black -> monochrome palette match (+5)
    items = {
        str(T1): _item(T1, "tops", color="black"),
        str(B1): _item(B1, "bottoms", color="black"),
    }
    palette_base = score_outfit_candidate(cand, items, preferred_palette="monochrome")
    plain = score_outfit_candidate(cand, items)
    assert palette_base.compatibility == plain.compatibility + 5.0

    ctx_like = FeedbackContext(liked_outfits=(frozenset([str(T1), str(B1)]),))
    palette_with_like = score_outfit_candidate(
        cand, items, preferred_palette="monochrome", feedback_context=ctx_like
    )
    assert palette_with_like.compatibility == palette_base.compatibility
    assert palette_with_like.feedback == _FEEDBACK_LIKE_EXACT_BONUS


# ---------------------------------------------------------------------------
# Requirement 10: existing fit scoring unchanged
# ---------------------------------------------------------------------------


def test_10_existing_fit_scoring_unchanged():
    cand = _cand(T1, B1)
    # Both items have usable fit evidence matching slim (+5)
    items = {
        str(T1): _item(T1, "tops", fit="slim", fit_confidence=0.8),
        str(B1): _item(B1, "bottoms", fit="slim", fit_confidence=0.8),
    }
    fit_base = score_outfit_candidate(cand, items, preferred_fit="slim")
    plain = score_outfit_candidate(cand, items)
    assert fit_base.compatibility == plain.compatibility + 5.0

    ctx_dislike = FeedbackContext(disliked_outfits=(frozenset([str(T1), str(B1)]),))
    fit_with_dislike = score_outfit_candidate(
        cand, items, preferred_fit="slim", feedback_context=ctx_dislike
    )
    assert fit_with_dislike.compatibility == fit_base.compatibility
    assert fit_with_dislike.feedback == _FEEDBACK_DISLIKE_EXACT_PENALTY


# ---------------------------------------------------------------------------
# Requirement 11: final score remains <= 100 and >= 0
# ---------------------------------------------------------------------------


def test_11_final_score_remains_le_100_and_ge_0():
    # Maximum budget test: 70 comp + 15 pref + 15 fav + 6 feedback + 2 wear = 108
    capped = compose_candidate_score(
        compatibility=70.0,
        preference=15.0,
        favorite=15.0,
        feedback=6.0,
        wear=2.0,
    )
    assert capped == 100.0

    # Low score with heavy dislike does not drop below 0
    floored = compose_candidate_score(
        compatibility=2.0,
        preference=0.0,
        favorite=0.0,
        feedback=-6.0,
        wear=0.0,
    )
    assert floored == 0.0


# ---------------------------------------------------------------------------
# Requirement 12: deterministic tie-break remains unchanged
# ---------------------------------------------------------------------------


def test_12_deterministic_tie_break_remains_unchanged():
    c1 = OutfitCandidate(
        top_ids=("a",), bottom_ids=("b",), compatibility=50.0, score=50.0
    )
    c2 = OutfitCandidate(
        top_ids=("c",), bottom_ids=("d",), compatibility=50.0, score=50.0
    )

    ranked1 = rank_outfit_candidates([c1, c2])
    ranked2 = rank_outfit_candidates([c2, c1])

    assert [c.top_ids for c in ranked1] == [c.top_ids for c in ranked2]
    assert ranked1[0].top_ids == ("a",)  # Lexical tie-break: 'a' < 'c'


# ---------------------------------------------------------------------------
# Requirement 13: explanation reason only appears when evidence exists
# ---------------------------------------------------------------------------


def test_13_explanation_reason_truthfulness():
    # Neutral candidate
    neutral = OutfitCandidate(top_ids=(str(T1),), bottom_ids=(str(B1),), score=50.0)
    rec_neutral = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=neutral,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert "Similar to outfits you've liked" not in rec_neutral.reasons
    assert "Reduced because of previous negative feedback" not in rec_neutral.reasons
    assert "Previously worn combination" not in rec_neutral.reasons

    # Like only
    liked_cand = OutfitCandidate(
        top_ids=(str(T1),), bottom_ids=(str(B1),), feedback=4.0, score=54.0
    )
    rec_liked = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=liked_cand,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert "Similar to outfits you've liked" in rec_liked.reasons
    assert "Reduced because of previous negative feedback" not in rec_liked.reasons
    assert "Previously worn combination" not in rec_liked.reasons

    # Dislike only
    disliked_cand = OutfitCandidate(
        top_ids=(str(T1),), bottom_ids=(str(B1),), feedback=-4.0, score=46.0
    )
    rec_disliked = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=disliked_cand,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert "Similar to outfits you've liked" not in rec_disliked.reasons
    assert "Reduced because of previous negative feedback" in rec_disliked.reasons
    assert "Previously worn combination" not in rec_disliked.reasons

    # Wear only
    worn_cand = OutfitCandidate(
        top_ids=(str(T1),), bottom_ids=(str(B1),), wear=2.0, score=52.0
    )
    rec_worn = _to_recommendation(
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
        winner=worn_cand,
        by_record={str(T1): _item(T1, "tops"), str(B1): _item(B1, "bottoms")},
    )
    assert "Similar to outfits you've liked" not in rec_worn.reasons
    assert "Reduced because of previous negative feedback" not in rec_worn.reasons
    assert "Previously worn combination" in rec_worn.reasons


# ---------------------------------------------------------------------------
# Test 14: build_feedback_context unit tests with fake repositories
# ---------------------------------------------------------------------------


class _FakeFeedbackRepo:
    def __init__(self, events):
        self.events = events

    def list_for_user(self, *, user_id, limit=100):
        return self.events


class _FakeSavedLooksRepo:
    def __init__(self, looks):
        self.looks = {l.id: l for l in looks}

    def get_for_user(self, *, user_id, saved_look_id):
        return self.looks.get(saved_look_id)


class _FakeWearRepo:
    def __init__(self, wears):
        self.wears = wears

    def list_for_user(self, *, user_id, page=1, page_size=100):
        return self.wears, len(self.wears)


def test_14_build_feedback_context():
    look_1 = uuid4()
    look_2 = uuid4()

    saved_look_1 = SavedLookRecord(
        id=look_1,
        look_id=None,
        title="Outfit 1",
        snapshot={"selectedItemIds": [str(T1), str(B1)]},
        source_run_id=None,
        created_at=datetime.now(timezone.utc),
        source_context="outfit",
    )
    saved_look_2 = SavedLookRecord(
        id=look_2,
        look_id=None,
        title="Outfit 2",
        snapshot={"components": [{"id": str(T2)}, {"id": str(B2)}]},
        source_run_id=None,
        created_at=datetime.now(timezone.utc),
        source_context="outfit",
    )

    t1 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc)

    # Event 1: earlier like on look 1
    # Event 2: later dislike on look 1 (overrides like)
    # Event 3: like on look 2
    events = [
        FeedbackEventRecord(
            id=uuid4(),
            user_id=USER,
            target_look_id=None,
            target_saved_look_id=look_1,
            rating="like",
            reason=None,
            idempotency_key="k1",
            occurred_at=t1,
        ),
        FeedbackEventRecord(
            id=uuid4(),
            user_id=USER,
            target_look_id=None,
            target_saved_look_id=look_1,
            rating="dislike",
            reason=None,
            idempotency_key="k2",
            occurred_at=t2,
        ),
        FeedbackEventRecord(
            id=uuid4(),
            user_id=USER,
            target_look_id=None,
            target_saved_look_id=look_2,
            rating="like",
            reason=None,
            idempotency_key="k3",
            occurred_at=t1,
        ),
    ]

    group_id = uuid4()
    wear_events = [
        WearEventRecord(
            id=uuid4(),
            user_id=USER,
            wardrobe_item_id=T1,
            worn_at=t1,
            wear_group_id=group_id,
            idempotency_key="w1",
            created_at=t1,
        ),
        WearEventRecord(
            id=uuid4(),
            user_id=USER,
            wardrobe_item_id=B1,
            worn_at=t1,
            wear_group_id=group_id,
            idempotency_key="w1",
            created_at=t1,
        ),
    ]

    ctx = build_feedback_context(
        user_id=USER,
        feedback=_FakeFeedbackRepo(events),
        saved_looks=_FakeSavedLooksRepo([saved_look_1, saved_look_2]),
        wears=_FakeWearRepo(wear_events),
    )

    # look_1 had later dislike -> in disliked_outfits
    assert frozenset([str(T1), str(B1)]) in ctx.disliked_outfits
    assert frozenset([str(T1), str(B1)]) not in ctx.liked_outfits

    # look_2 had like -> in liked_outfits
    assert frozenset([str(T2), str(B2)]) in ctx.liked_outfits

    # T1 and B1 worn together in group_id -> in worn_combinations
    assert frozenset([str(T1), str(B1)]) in ctx.worn_combinations


# ---------------------------------------------------------------------------
# Test 15: GenerateOutfit end-to-end integration
# ---------------------------------------------------------------------------


class _FakeWardrobeRepo:
    def __init__(self, items):
        self._items = items

    def get_for_user(self, *, user_id, page=1, page_size=100):
        return self._items, len(self._items)


class _FakeUserStateRepo:
    def get(self, *, user_id):
        return None


def test_15_generate_outfit_end_to_end():
    # Wardrobe with 2 tops, 2 bottoms
    # Combination (T1, B1) is disliked
    # Combination (T2, B2) is liked
    top_1 = _item(T1, "tops", "black")
    top_2 = _item(T2, "tops", "black")
    bot_1 = _item(B1, "bottoms", "black")
    bot_2 = _item(B2, "bottoms", "black")

    look_1 = uuid4()
    look_2 = uuid4()

    saved_look_1 = SavedLookRecord(
        id=look_1,
        look_id=None,
        title="Outfit 1",
        snapshot={"selectedItemIds": [str(T1), str(B1)]},
        source_run_id=None,
        created_at=datetime.now(timezone.utc),
        source_context="outfit",
    )
    saved_look_2 = SavedLookRecord(
        id=look_2,
        look_id=None,
        title="Outfit 2",
        snapshot={"selectedItemIds": [str(T2), str(B2)]},
        source_run_id=None,
        created_at=datetime.now(timezone.utc),
        source_context="outfit",
    )

    t = datetime.now(timezone.utc)
    events = [
        FeedbackEventRecord(
            id=uuid4(),
            user_id=USER,
            target_look_id=None,
            target_saved_look_id=look_1,
            rating="dislike",
            reason=None,
            idempotency_key="k1",
            occurred_at=t,
        ),
        FeedbackEventRecord(
            id=uuid4(),
            user_id=USER,
            target_look_id=None,
            target_saved_look_id=look_2,
            rating="like",
            reason=None,
            idempotency_key="k2",
            occurred_at=t,
        ),
    ]

    use_case = GenerateOutfit(
        wardrobe_items=_FakeWardrobeRepo([top_1, top_2, bot_1, bot_2]),
        user_state=_FakeUserStateRepo(),
        feedback=_FakeFeedbackRepo(events),
        saved_looks=_FakeSavedLooksRepo([saved_look_1, saved_look_2]),
    )

    recom, reason = use_case.derive_with_reason(
        user_id=USER,
        occasion="casual",
        mood="classic",
        fit="slim",
        color_palette="monochrome",
    )

    assert recom is not None
    assert reason is None
    # Winner must be (T2, B2) because it was liked (+4.0) while (T1, B1) was disliked (-4.0)
    winner_ids = {c.id for c in recom.components}
    assert str(T2) in winner_ids
    assert str(B2) in winner_ids
    assert "Similar to outfits you've liked" in recom.reasons
