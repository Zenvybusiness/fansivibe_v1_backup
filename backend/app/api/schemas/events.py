"""Wire schemas for the event calendar surface (#26–29, M8-B).

Shapes mirror `DAILY_OUTFIT_EVENTS_API.md` §§4.5/5.4–5.7: `EventCreate` /
`EventUpdate` carry the same required/optional markers (full replace on
PUT); `UserEvent` is the bare detail DTO; `EventSummary` is the list
card; `UserEventList` is the offset envelope (`{items,page,page_size,
total}`, API-18). All keys are camelCase (C-4).

Length bounds ride on the schema as the wire guard (`min_length=1`
rejects supplied-empty text); the use case re-validates the same bounds
so direct callers see identical 422s, and the DB CHECKs are the final
safety layer. `time` stays a plain string here — strict `HH:mm`
validation lives in the use case (a `datetime.time` field would accept
seconds, which the contract forbids).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    eventType: str = Field(min_length=1)
    eventDate: date
    time: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, min_length=1, max_length=2000)


class EventUpdate(EventCreate):
    """Full-replacement update body — same shape as `EventCreate` (E-4)."""


class UserEvent(BaseModel):
    id: UUID
    title: str
    eventType: str
    eventDate: date
    time: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class EventSummary(BaseModel):
    """List card for `GET /v1/events` (no location/notes/timestamps)."""

    id: UUID
    title: str
    eventType: str
    eventDate: date
    time: Optional[str] = None


class UserEventList(BaseModel):
    """Offset envelope for `GET /v1/events` (endpoint #27)."""

    items: list[EventSummary]
    page: int
    page_size: int
    total: int


class OutfitComponent(BaseModel):
    """One owned wardrobe item in an event outfit (endpoint #30).

    Honest ensemble subset: `colorHex` has no server source and is
    omitted (DEC-015, AI-0 — hence `exclude_none` on the route).
    `category`/`color`/`material` are stored vocab codes (K9.1).
    """

    id: str
    name: str
    category: str
    color: str
    colorHex: Optional[str] = None
    material: Optional[str] = None
    reason: str


class OutfitRecommendation(BaseModel):
    """Derived event outfit (endpoint #30, UC-21) — ensemble family.

    `matchScore` is the family 0..1 float scale; `selectedOccasion` is
    the event TYPE CODE. Fields with no engine source
    (`colorHarmony`, `bodyFit`, `occasionMatch`, `styleScoreImpact`,
    `improvementSuggestion`, `selectedMood`, `selectedColorPalette`)
    stay `None` and are excluded from the wire (`exclude_none` on the
    route) — never fabricated. No alternatives: the canonical DTO
    carries none (DAILY §4.4, V1, builder mock).
    """

    title: str
    matchScore: float
    components: list[OutfitComponent]
    reasons: list[str]
    colorHarmony: Optional[str] = None
    bodyFit: Optional[str] = None
    occasionMatch: Optional[str] = None
    styleScoreImpact: Optional[str] = None
    improvementSuggestion: Optional[str] = None
    selectedOccasion: str
    selectedMood: Optional[str] = None
    selectedColorPalette: Optional[str] = None
