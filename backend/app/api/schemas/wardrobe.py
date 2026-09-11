"""Wire schemas for the wardrobe surface (Step 4D).

Shapes mirror `WARDROBE_API.md` §4.7 and §5.1–§5.4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WardrobeItem(BaseModel):
    id: UUID
    name: str
    category: str
    color: str
    material: Optional[str] = None
    isFavorite: bool = False
    imageRef: Optional[dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime


class WardrobeItemCreate(BaseModel):
    """Request body for `POST /v1/wardrobe/items` (W-3)."""

    name: str = Field(min_length=1, max_length=100)
    category: str
    color: str
    material: Optional[str] = None
    isFavorite: bool = False
    imageRef: Optional[dict[str, Any]] = None


class WardrobeItemPatch(BaseModel):
    """Request body for `PATCH /v1/wardrobe/items/{item_id}` (W-4).

    PATCH partial merge — only present fields change. `null` material clears it.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    category: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    isFavorite: Optional[bool] = None


class ListEnvelope(BaseModel):
    """Offset envelope for `GET /v1/wardrobe/items` (W-1)."""

    items: list[WardrobeItem]
    page: int
    page_size: int
    total: int


class WardrobeInsight(BaseModel):
    """Response for `GET /v1/wardrobe/insight` (W-7)."""

    title: str
    insight: str
    action: Optional[str] = None
    route: Optional[str] = None


class WearEventLogRequest(BaseModel):
    """Request body for `POST /v1/wardrobe/wears` (STEP 15.4).

    `wornAt` omitted → server now. At most 10 *canonical* item IDs is
    enforced in the use case (raw duplicates canonicalize first).
    """

    itemIds: list[UUID] = Field(min_length=1)
    wornAt: Optional[datetime] = None


class WearEvent(BaseModel):
    """One persisted wear-event row (`GET /v1/wardrobe/wears` item)."""

    id: UUID
    wardrobeItemId: UUID
    wornAt: datetime
    wearGroupId: UUID
    createdAt: datetime


class WearEventLogResponse(BaseModel):
    """Response for `POST /v1/wardrobe/wears` (STEP 15.4).

    `created=False` on idempotent replay (still HTTP 201, save precedent).
    """

    wears: list[WearEvent]
    wearGroupId: UUID
    wornAt: datetime
    created: bool


class WearEventList(BaseModel):
    """Offset envelope for `GET /v1/wardrobe/wears` (STEP 15.4)."""

    items: list[WearEvent]
    page: int
    page_size: int
    total: int


class WearSummary(BaseModel):
    """Response for `GET /v1/wardrobe/wear-summary` (W-9, STEP 17.3).

    Accepted wire contract: DEC-012 + `WARDROBE_API.md` §10.3. Maps the
    domain `WearSummary` 1:1 at the API boundary (no recomputation):
    keys are canonical backend wardrobe UUID strings, category keys are
    canonical vocabulary codes, instants are ISO-8601 UTC (`null` =
    never worn). Counts only — no names, judgments, or recommendations.
    """

    totalWears: int
    wearCounts: dict[str, int]
    lastWorn: dict[str, Optional[datetime]]
    mostWornItemIds: list[str]
    leastWornItemIds: list[str]
    unwornItemIds: list[str]
    recentlyWornItemIds: list[str]
    wearsByCategory: dict[str, int]