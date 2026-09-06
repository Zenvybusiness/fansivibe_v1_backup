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