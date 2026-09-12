"""Wire schemas for the M14 Discover reads (UC-31, endpoints #43–44).

`GET /v1/looks` returns the cursor envelope
(`PAGINATION_FILTERING.md` §5.2: `{items, next_cursor, has_more}` — no
`total`, feed totals are unstable); `GET /v1/looks/{look_id}` returns a
bare `LookDetail`. JSON keys are camelCase (API-19).

Both DTOs carry verbatim catalog content only. The catalog rows have no
occasion/style/fit attributes, no image, no ensemble, and no wardrobe
linkage (DEC-014 P-3), so none of `imageUrl`/`occasion`/`styleTags`/
`fitTags`/`wardrobeMatchCount`/`matchScoreDetails`/`isTrending`/
`isOwned`/ensemble fields appear here (AI-0: uncomputed fields are
absent, never fabricated). `id` is the stable catalog code (PR-3 — a
string such as `textured_quiff`, never a UUID).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LookSummary(BaseModel):
    """One ranked feed row (#43 list item)."""

    id: str
    title: str
    description: str
    matchScore: int
    reasons: list[str]


class LookDetail(BaseModel):
    """One catalog look, full grounded content (#44 detail read)."""

    id: str
    title: str
    description: str
    matchScore: int
    reasons: list[str]
    stylingTips: str
    maintenance: str
    bestFor: str


class LookFeed(BaseModel):
    """Cursor envelope for `GET /v1/looks` (#43, UC-31)."""

    items: list[LookSummary]
    next_cursor: Optional[str] = None
    has_more: bool
