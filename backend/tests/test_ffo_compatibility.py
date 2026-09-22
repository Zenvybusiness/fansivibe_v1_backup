"""FFO compatibility scorer — per-dimension projection of existing signals.

Additive only: exercises `ffo_compatibility` over the reused STEP-13
sub-signals. No database, no user data, no prod behavior change.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.services.ffo_compatibility import ffo_compatibility
from app.domain.value_objects import OutfitCandidate


def _item(item_id: str, category: str, color=None, material=None, **extra):
    return SimpleNamespace(
        id=item_id, category=category, color=color,
        material=material, is_favorite=False, **extra,
    )


def _wardrobe():
    return {
        "a": _item("a", "tops", color="white", material="cotton"),
        "b": _item("b", "bottoms", color="black", material="wool"),
        "c": _item("c", "footwear", color="grey", material="leather"),
    }


def _candidate():
    return OutfitCandidate(top_ids=("a",), bottom_ids=("b",), footwear_ids=("c",))


def test_emits_computed_dimensions_bounded_no_single_score():
    result = ffo_compatibility(_candidate(), _wardrobe())
    dims = result["compatibility"]
    assert set(dims) == {"color", "material", "climate", "wardrobe"}
    for score in dims.values():
        assert 0.0 <= score <= 1.0
    assert dims["color"] == 1.0  # neutral-vocabulary harmony (+10)
    assert dims["material"] == 1.0  # all natural (+5)
    assert "score" not in result and "matchScore" not in result
    assert set(result["uncertainties"]) == {"silhouette", "occasion", "user_preference"}
    assert result["confidence"] == round(4 / 7, 2)


def test_deterministic_repeat_call():
    first = ffo_compatibility(_candidate(), _wardrobe(), preferred_occasions=["casual"])
    second = ffo_compatibility(_candidate(), _wardrobe(), preferred_occasions=["casual"])
    assert first == second


def test_occasion_emitted_only_with_preferences():
    assert "occasion" in ffo_compatibility(
        _candidate(), _wardrobe(), preferred_occasions=["casual"]
    )["compatibility"]
    assert "occasion" not in ffo_compatibility(_candidate(), _wardrobe())["compatibility"]


def test_silhouette_heuristic_when_attrs_present():
    items = {
        "a": _item("a", "tops", color="white", material="cotton", silhouette="oversized"),
        "b": _item("b", "bottoms", color="black", material="wool", silhouette="wide_leg"),
    }
    result = ffo_compatibility(OutfitCandidate(top_ids=("a",), bottom_ids=("b",)), items)
    assert result["compatibility"]["silhouette"] == 0.7
    assert any("high_volume_outfit" in reason for reason in result["reasoning"])


def test_user_preference_overlap_and_omission():
    uid = "65fd6999-b55c-4d27-98dc-0fcc7c770c18"  # UUID-form: engine matches canonical UUIDs only
    items = {"u": _item(uid, "tops", color="white", material="cotton")}
    candidate = OutfitCandidate(top_ids=(uid,), bottom_ids=("b",))
    overlap = ffo_compatibility(candidate, {**_wardrobe(), **items}, preferred_item_ids={uid})
    assert overlap["compatibility"]["user_preference"] == round(5 / 15, 2)
    assert "user_preference" not in ffo_compatibility(_candidate(), _wardrobe())["compatibility"]
