"""Wire schemas for the M9 Today's Look surface (#31–33).

Shapes mirror the derived-look `TodayLook` family frozen in
`DAILY_OUTFIT_EVENTS_API.md` §§4.4/5.1–5.3 and DEC-017/018: `title*`,
`occasion*`, `weather?`, `description*`, `matchScore*`/`styleScore*`
(native 0–100 int scale, STEP-13 budget — no rescale), `components*`,
`reasons*`, `styleDna*`, `wardrobeContext*`, `alternatives[]`, plus the
additive top-level `selectedItemIds` (API-2) that reuses M7 validation
verbatim at save time. All keys are camelCase (C-4).

Honesty subset (AI-0, DEC-018 C12): `weather` has no provider in v1 and
is always absent; per-component `colorHex` has no server source;
`aiSelectionReason` / `confidenceBoost` / `aiInsights` / `dailyStyleTip`
/ `wardrobeContext.insight` are omitted unless grounded (never
fabricated). The route serves these with `exclude_none`, so absent
optionals never reach the wire. Alternatives carry the minimal mapping
(stable member-derived id + candidate score) only.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TodayLookComponent(BaseModel):
    """One owned wardrobe item in a TodayLook (no reason/hex — the
    derived-look component shape)."""

    id: str
    name: str
    category: str
    color: str
    material: Optional[str] = None


class TodayLookStyleDna(BaseModel):
    """StyleProfile projection — only present subfields travel (absent
    profile gaps never 404, DEC-018 C12)."""

    styleType: Optional[str] = None
    bodyType: Optional[str] = None
    skinTone: Optional[str] = None
    faceShape: Optional[str] = None


class TodayLookWardrobeContext(BaseModel):
    """Grounded wardrobe counts (`insight` omitted — no grounded prose)."""

    totalItems: int
    matchingItems: int


class TodayLookAlternative(BaseModel):
    """One ranked runner-up (`ranked[1:3]`, minimal mapping)."""

    id: str
    matchScore: int = Field(ge=0, le=100)


class TodayLook(BaseModel):
    """Derived today's look (endpoints #31–32, UC-16/UC-17)."""

    title: str
    occasion: Optional[str] = None
    description: str
    matchScore: int = Field(ge=0, le=100)
    styleScore: int = Field(ge=0, le=100)
    components: list[TodayLookComponent]
    reasons: list[str]
    styleDna: Optional[TodayLookStyleDna] = None
    wardrobeContext: TodayLookWardrobeContext
    alternatives: list[TodayLookAlternative] = Field(default_factory=list)
    selectedItemIds: list[str]
