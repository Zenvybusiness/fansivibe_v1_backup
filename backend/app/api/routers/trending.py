"""M14 Trending API — `GET /v1/trending`, `GET /v1/trending/{trend_id}`.

Stateless in-memory reads over the deterministic test adapter (real
providers: NOT CONNECTED — CREDENTIAL/ACCESS REQUIRED). No database,
no migration. Auth via `get_current_user_id` (401 without Bearer).
Fail-closed: provider errors yield degraded-but-honest output, never
fabricated trends.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_current_user_id
from app.api.errors import not_found
from app.api.schemas.trending import TrendItemSchema, TrendProductSchema, TrendingFeed
from app.trending.domain import build_trends, load_test_adapter, matched_products

logger = logging.getLogger("fansivibe.trending")

router = APIRouter(prefix="/v1/trending", tags=["trending"])


def _snapshot(now: datetime) -> tuple:
    """Fetch each source independently so one failure never drops others."""
    try:
        signals, _ = load_test_adapter(now)
    except Exception as exc:  # pragma: no cover - adapter never raises
        logger.warning("trending signal source failed: %s", exc)
        signals = []
    try:
        _, products = load_test_adapter(now)
    except Exception as exc:  # pragma: no cover - adapter never raises
        logger.warning("trending product source failed: %s", exc)
        products = []
    return (signals, products)


def _to_schema(trend, products: list) -> TrendItemSchema:
    items = matched_products(products, trend.trend_id)
    return TrendItemSchema(
        trendId=trend.trend_id,
        displayName=trend.canonical_name,
        category=trend.category,
        region=trend.region,
        velocity=trend.velocity,
        confidence=trend.confidence,
        freshnessHours=trend.freshness_hours,
        supportingSignals=trend.supporting_signals,
        sources=sorted({p["source"] for p in trend.provenance}),
        provenance=list(trend.provenance),
        matchedProducts=[
            TrendProductSchema(
                provider=p.source,
                externalId=p.source_product_id,
                title=p.name,
                brand=p.brand,
                priceInr=p.price,
                imageUrl=p.image_url,
                productUrl=p.product_url or p.affiliate_url,
                inStock=p.availability,
            )
            for p in items
        ],
    )


@router.get("", response_model=TrendingFeed)
def get_trending(
    region: str = Query(default="IN", min_length=2, max_length=10),
    limit: int = Query(default=20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user_id),
) -> TrendingFeed:
    """Ranked trend feed (read-only, deterministic, stateless)."""
    now = datetime.now(timezone.utc)
    signals, products = _snapshot(now)
    signals = [s for s in signals if s.region == region]
    trends = build_trends(signals, products, now)[:limit]
    return TrendingFeed(
        region=region,
        generatedAt=now.isoformat(),
        isStale=False,
        items=[_to_schema(t, products) for t in trends],
    )


@router.get("/{trend_id}", response_model=TrendItemSchema)
def get_trend_detail(
    trend_id: str = Path(...),
    user_id: UUID = Depends(get_current_user_id),
) -> TrendItemSchema:
    """One normalized trend with provenance + matched products."""
    now = datetime.now(timezone.utc)
    signals, products = _snapshot(now)
    for trend in build_trends(signals, products, now):
        if trend.trend_id == trend_id:
            return _to_schema(trend, products)
    raise not_found()
