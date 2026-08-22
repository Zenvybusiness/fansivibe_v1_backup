"""Wire schemas for the save surface (#23, `POST /v1/looks/saved`).

Shapes mirror `HAIRSTYLE_RECOMMENDATION_API.md` §5.5 (`SaveLookRequest`,
`SavedLook`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SaveLookRequest(BaseModel):
    lookId: Optional[str] = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    sourceContext: str
    snapshot: dict[str, Any]


class SavedLook(BaseModel):
    id: UUID
    lookId: Optional[str] = None
    title: str
    snapshot: dict[str, Any]
    sourceRunId: Optional[UUID] = None
    createdAt: datetime


class SavedLookList(BaseModel):
    """Offset envelope for `GET /v1/looks/saved` (endpoint #24)."""

    items: list[SavedLook]
    page: int
    page_size: int
    total: int
