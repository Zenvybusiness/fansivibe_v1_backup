"""Wire schemas for M14 Trending (`GET /v1/trending`, detail).

CamelCase keys (API-19). Only normalized trend intelligence travels:
trend score/confidence, freshness, supporting source info, matched
products, provenance. No provider credentials, no raw provider payloads.
Unprovided product fields (price/url/image/availability) are null —
never fabricated.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TrendProductSchema(BaseModel):
    provider: str
    externalId: str
    title: str
    brand: str
    priceInr: Optional[float] = None
    imageUrl: Optional[str] = None
    productUrl: Optional[str] = None
    inStock: Optional[bool] = None


class TrendItemSchema(BaseModel):
    trendId: str
    displayName: str
    category: str
    region: str
    velocity: float
    confidence: float
    freshnessHours: Optional[float] = None
    supportingSignals: int
    sources: list[str]
    provenance: list[dict]
    matchedProducts: list[TrendProductSchema]


class TrendingFeed(BaseModel):
    region: str
    generatedAt: str
    isStale: bool = False
    items: list[TrendItemSchema]
