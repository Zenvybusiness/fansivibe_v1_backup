"""D7 Trend Analysis API — `GET /v1/trends/analysis` (read-only).

Exposes the existing D6 Trend Intelligence Engine over the D5 observation
history. It adds no engine, no formula and no migration: it orchestrates
``AnalyzeTrends`` and maps its auditable result to a typed, versioned contract.

Honesty rules enforced here:

- Catalog/operational activity is labelled ``catalog_activity`` and never
  rendered as consumer demand. ``DEMAND_SIGNAL_AVAILABLE`` is False today, so
  ``demandTrendStatus`` is ``insufficient_evidence`` and nothing is published.
- Fixture-derived evidence is never published (D6 already excludes it).
- A candidate whose FFO projection fails the authoritative ``trend.schema.json``
  is fail-closed: excluded from ``publishedCandidates`` with an explicit reason.
- Missing metrics stay ``null``; they are never turned into zero.
- No internal database ids, raw provider payloads or credentials are returned.
- Read-only: no writes, no provider calls, no rate-limit changes (the limiter
  only guards credential endpoints).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_current_user_id, get_trend_repository
from app.api.errors import database_failure, validation
from app.api.schemas.trend_analysis import (
    TrendAnalysisResponse,
    TrendCandidateSchema,
    TrendSignalSchema,
)
from app.application.trends import AnalyzeTrends, TrendConfig
from app.data.ffo.validation import trend_errors
from app.domain.services.trends import (
    DEMAND_SIGNAL_AVAILABLE,
    STAGE_INSUFFICIENT,
    TrendCandidate,
    to_ffo_trend,
)

logger = logging.getLogger("fansivibe.trends")

router = APIRouter(prefix="/v1/trends", tags=["trends"])

# Documented window policy: a default of the last 30 days, and a hard cap so a
# single request can never scan an unbounded history.
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90

# Catalog/operational evidence is the only kind available today. This constant
# and ``DEMAND_SIGNAL_AVAILABLE`` are the two places that change when a demand
# provider is authorized.
EVIDENCE_TYPE_CATALOG = "catalog_activity"
REASON_SCHEMA_INVALID = "projection failed FFO trend schema validation"

_CONFIDENCE_INTERPRETATION = (
    "confidence is a documented 0..1 data-quality heuristic (observation "
    "volume, source coverage, freshness); it is NOT the probability that a "
    "trend is correct"
)
_LIMITATIONS = (
    "no authorized direct-demand provider is connected, so consumer-demand "
    "trends cannot be validated yet",
    "catalog growth, price changes and availability describe catalog "
    "activity, never consumer demand",
    "catalog activity stages are advisory catalog classification, not "
    "validated consumer-demand lifecycle stages",
    "fixture-derived observations are never published as trends",
    "missing metrics are omitted (null), never treated as zero",
    "confidence is a documented heuristic, not a probability",
)


def _resolve_window(
    window_start: Optional[datetime],
    window_end: Optional[datetime],
    *,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return a validated ``[start, end)`` window or a truthful 422."""
    if window_start is None and window_end is None:
        return now - timedelta(days=DEFAULT_WINDOW_DAYS), now
    if window_start is None or window_end is None:
        raise validation(
            [
                {
                    "field": "window",
                    "error": "provide both window_start and window_end, or neither",
                }
            ]
        )
    for field, value in (("window_start", window_start), ("window_end", window_end)):
        if value.tzinfo is None:
            raise validation(
                [{"field": field, "error": f"{field} must include a timezone offset"}]
            )
    if window_end <= window_start:
        raise validation(
            [{"field": "window_end", "error": "window_end must be after window_start"}]
        )
    if window_end - window_start > timedelta(days=MAX_WINDOW_DAYS):
        raise validation(
            [
                {
                    "field": "window",
                    "error": f"window must not exceed {MAX_WINDOW_DAYS} days",
                }
            ]
        )
    return window_start, window_end


def _candidate_schema(candidate: TrendCandidate) -> tuple[TrendCandidateSchema, bool]:
    """Map a D6 candidate to the wire contract; fail closed on schema failure."""
    projection = to_ffo_trend(candidate)  # None unless the candidate is publishable
    ffo_trend: Optional[dict] = None
    published = False
    reasons = list(candidate.reasons)
    if projection is not None:
        errors = trend_errors(projection)
        if errors:
            # The projection is internal, so only a stable reason string is
            # exposed; details stay in logs (never the raw payload).
            reasons.append(REASON_SCHEMA_INVALID)
            logger.warning("trend projection failed FFO schema: %s", "; ".join(errors))
        else:
            ffo_trend = projection
            published = True

    schema = TrendCandidateSchema(
        concept=candidate.concept,
        canonicalName=candidate.canonical_name,
        category=candidate.category,
        evidenceType=EVIDENCE_TYPE_CATALOG,
        catalogActivityStatus=candidate.stage,
        observationCount=candidate.observation_count,
        distinctProducts=candidate.distinct_products,
        distinctSources=candidate.distinct_sources,
        firstObservedAt=candidate.first_observed_at.isoformat(),
        lastObservedAt=candidate.last_observed_at.isoformat(),
        catalogGrowth=candidate.catalog_growth,
        priceChangeRatio=candidate.price_change_ratio,
        inStockRatio=candidate.in_stock_ratio,
        confidence=candidate.confidence,
        strength=candidate.strength,
        fixtureDerived=candidate.is_fixture,
        publishable=published,
        reasons=reasons,
        signals=[
            TrendSignalSchema(
                metric=s.name,
                kind=s.kind,
                available=s.available,
                value=s.value,
                unit=s.unit,
                detail=s.detail,
            )
            for s in candidate.signals
        ],
        ffoTrend=ffo_trend,
    )
    return schema, published


@router.get("/analysis", response_model=TrendAnalysisResponse)
def get_trend_analysis(
    window_start: Optional[datetime] = Query(default=None),
    window_end: Optional[datetime] = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    repository=Depends(get_trend_repository),
) -> TrendAnalysisResponse:
    """Analyze catalog-observation evidence for one window (read-only)."""
    del user_id  # authentication is required; the evidence is system-wide
    now = datetime.now(timezone.utc)
    start, end = _resolve_window(window_start, window_end, now=now)

    try:
        analysis = AnalyzeTrends(repository=repository)(
            TrendConfig(window_start=start, window_end=end)
        )
    except SQLAlchemyError:
        raise database_failure()

    candidates: list[TrendCandidateSchema] = []
    published_candidates: list[TrendCandidateSchema] = []
    for candidate in analysis.candidates:
        schema, published = _candidate_schema(candidate)
        candidates.append(schema)
        if published:
            published_candidates.append(schema)

    return TrendAnalysisResponse(
        windowStart=start.isoformat(),
        windowEnd=end.isoformat(),
        generatedAt=now.isoformat(),
        demandTrendStatus=analysis.demand_trend_status,
        evidenceType=EVIDENCE_TYPE_CATALOG,
        catalogActivityStatus="observed" if analysis.candidates else "no_observations",
        directDemandAvailable=DEMAND_SIGNAL_AVAILABLE,
        sourceCoverage=analysis.source_coverage,
        observationCount=analysis.observation_count,
        insufficientEvidenceReason=(
            analysis.demand_insufficient_reason
            if analysis.demand_trend_status == STAGE_INSUFFICIENT
            else None
        ),
        confidenceInterpretation=_CONFIDENCE_INTERPRETATION,
        limitations=list(_LIMITATIONS),
        candidates=candidates,
        publishedCandidates=published_candidates,
    )
