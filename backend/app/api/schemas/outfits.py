"""Wire schemas for the M13 outfit builder surface (#41–42, UC-28/29/30).

Shapes mirror the ensemble `OutfitRecommendation` family frozen in
REC_API §4.3 and V1 §6.7: `title*`, `matchScore*` (family 0..1 float
scale — no rescale, no unification), `components*`, `reasons*`, the five
metric-prose fields, and the `selected*` request echoes. All keys are
camelCase (C-4).

Honesty subset (AI-0, M8-C/M9 precedent): per-component `colorHex` has
no server source and is always absent; the route serves the DTO with
`exclude_none`, so absent optionals never reach the wire. No
alternatives: the canonical DTO carries none. Save reuses M7's
`SaveLookRequest` (the router enforces `sourceContext == "outfit"`).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class OutfitGenerateRequest(BaseModel):
    """Preference selections for one outfit derivation (#41, UC-28/29).

    `occasion`/`mood`/`fit`/`colorPalette` are validated as non-empty
    1..200 strings (no frozen backend vocab table exists for these
    selections — structural validation only, invalid values → 422).
    `seed` is the opaque UC-29 variety selector (absent → the winner;
    same seed repeats the backend result).
    """

    occasion: str = Field(min_length=1, max_length=200)
    mood: str = Field(min_length=1, max_length=200)
    fit: str = Field(min_length=1, max_length=200)
    colorPalette: str = Field(min_length=1, max_length=200)
    seed: Optional[str] = Field(default=None, min_length=1, max_length=200)


class OutfitComponent(BaseModel):
    """One owned wardrobe item in an outfit (no hex — no server source)."""

    id: str
    name: str
    category: str
    color: str
    material: Optional[str] = None
    reason: str


class OutfitRecommendation(BaseModel):
    """Derived outfit value object (endpoint #41, UC-28/UC-29)."""

    title: str
    matchScore: float = Field(ge=0, le=1)
    components: list[OutfitComponent]
    reasons: list[str]
    colorHarmony: str
    bodyFit: str
    occasionMatch: str
    styleScoreImpact: str
    improvementSuggestion: str
    selectedOccasion: str
    selectedMood: str
    selectedColorPalette: str
