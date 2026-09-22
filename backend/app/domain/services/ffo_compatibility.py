"""FFO per-dimension outfit compatibility — additive projection, no new rules.

Projects the existing STEP-13 sub-signals (imported from analysis_rules,
never copied) and the FFO silhouette-heuristics file onto the FFO §31
dimension names as 0..1 scores. Linear rescales of the documented point
scales — deterministic, identical inputs → identical output.

Uncomputed dimensions are omitted (AI-0 honesty), never zero-filled.
No single fashion-correctness score is emitted. Proportion, aesthetic,
footwear, accessories, trend and budget dimensions are out of scope for
this slice (no engine signal exists for them yet).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.services.analysis_rules import (
    _candidate_members,
    _color_points,
    _coverage_points,
    _material_points,
    _occasion_points,
    _season_points,
    candidate_preference_points,
)

# ponytail: read the checked-in heuristics file directly; add caching only
# if profiling shows this on a hot path.
_HEURISTICS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "ffo"
    / "knowledge"
    / "rules"
    / "compatibility_heuristics.json"
)

# Native maxima of the reused point scales (analysis_rules constants).
_COLOR_RANGE = (-10.0, 10.0)
_MATERIAL_MAX = 5.0
_SEASON_RANGE = (-5.0, 5.0)
_OCCASION_MAX = 5.0
_COVERAGE_MAX = 40.0  # +8 x 5 generator categories
_PREFERENCE_MAX = 15.0

_ATTEMPTED_DIMS = (
    "color",
    "silhouette",
    "material",
    "occasion",
    "climate",
    "wardrobe",
    "user_preference",
)


def _rescale(points: float, low: float, high: float) -> float:
    return round((points - low) / (high - low), 2)


def _silhouette_score(members: list, items_by_id) -> tuple[float | None, str | None]:
    """Match the FFO volume heuristics on top/bottom silhouette attributes.

    Wardrobe rows carry no silhouette column, so this usually yields
    (None, None) — the dimension is then omitted, honestly.
    """
    lookup = items_by_id or {}
    top = next((m["id"] for m in members if m["category"] == "tops"), None)
    bottom = next((m["id"] for m in members if m["category"] == "bottoms"), None)
    if top is None or bottom is None:
        return None, None
    top_sil = getattr(lookup.get(top), "silhouette", None)
    bottom_sil = getattr(lookup.get(bottom), "silhouette", None)
    if not top_sil or not bottom_sil:
        return None, None
    heuristics = json.loads(_HEURISTICS_PATH.read_text(encoding="utf-8"))["heuristics"]
    for rule in heuristics:
        when = rule.get("when", {})
        if when.get("top") == top_sil and when.get("bottom") == bottom_sil:
            return rule["confidence"], f"silhouette: {rule['effect']} ({top_sil}+{bottom_sil})"
    return None, None


def ffo_compatibility(
    candidate,
    items_by_id=None,
    preferred_occasions=None,
    preferred_item_ids=None,
) -> dict:
    """Per-dimension FFO compatibility for one outfit candidate.

    Returns the FFO §37 shape: compatibility (0..1 per computed dimension),
    reasoning (which reused signal fired), confidence (fraction of attempted
    dimensions computed — a certainty measure, not a quality score) and
    uncertainties (omitted dimensions).
    """
    members = _candidate_members(candidate, items_by_id)
    ids = [m["id"] for m in members]
    compatibility: dict[str, float] = {}
    reasoning: list[str] = []

    color_pts = _color_points(members)
    compatibility["color"] = _rescale(color_pts, *_COLOR_RANGE)
    reasoning.append(f"color: {color_pts:+g} pts (neutral-vocabulary gate)")

    material_pts = _material_points(members)
    compatibility["material"] = round(material_pts / _MATERIAL_MAX, 2)
    reasoning.append(f"material: {material_pts:+g} pts (natural consistency)")

    season_pts = _season_points(members)
    compatibility["climate"] = _rescale(season_pts, *_SEASON_RANGE)
    reasoning.append(f"climate: {season_pts:+g} pts (season intersection)")

    coverage_pts = _coverage_points(members)
    compatibility["wardrobe"] = round(coverage_pts / _COVERAGE_MAX, 2)
    reasoning.append(f"wardrobe: {coverage_pts:+g} pts (category coverage)")

    sil_score, sil_reason = _silhouette_score(members, items_by_id)
    if sil_score is not None:
        compatibility["silhouette"] = sil_score
        reasoning.append(sil_reason or "")

    if preferred_occasions:
        occasion_pts = _occasion_points(members, preferred_occasions)
        compatibility["occasion"] = round(occasion_pts / _OCCASION_MAX, 2)
        reasoning.append(f"occasion: {occasion_pts:+g} pts (preferred-occasion match)")

    if preferred_item_ids is not None:
        preference_pts = candidate_preference_points(set(preferred_item_ids), ids)
        compatibility["user_preference"] = round(preference_pts / _PREFERENCE_MAX, 2)
        reasoning.append(f"user_preference: {preference_pts:+g} pts (saved-item overlap)")

    uncertainties = [dim for dim in _ATTEMPTED_DIMS if dim not in compatibility]
    confidence = round((len(_ATTEMPTED_DIMS) - len(uncertainties)) / len(_ATTEMPTED_DIMS), 2)
    return {
        "compatibility": compatibility,
        "reasoning": reasoning,
        "confidence": confidence,
        "uncertainties": uncertainties,
    }
