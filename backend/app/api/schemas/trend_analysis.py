"""Wire schemas for the D7 Trend Analysis API (`GET /v1/trends/analysis`).

CamelCase keys (API-19), matching the existing trend schemas. Only normalized
trend intelligence travels: window/coverage metadata, per-candidate metrics and
evidence, the FFO projection of *published* candidates, and explicit limitation
text. No internal database ids, no raw provider payloads, no credentials.

Catalog/operational activity is reported as ``catalogActivityStatus`` and
``evidenceType="catalog_activity"`` — never as consumer demand.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TrendSignalSchema(BaseModel):
    """One audited component: metric, taxonomy kind, availability, value."""

    metric: str
    kind: str
    available: bool
    value: Optional[float] = None
    unit: Optional[str] = None
    detail: str


class TrendCandidateSchema(BaseModel):
    """One concept's observation evidence for the analysis window.

    ``catalogActivityStatus`` is the advisory catalog classification from D6
    (rising/plateau/declining/insufficient_evidence); it is explicitly catalog
    activity, not a validated consumer-demand lifecycle stage. Missing metrics
    stay ``None`` (JSON null) — never zero.
    """

    concept: str
    canonicalName: str
    category: str
    evidenceType: str
    catalogActivityStatus: str
    observationCount: int
    distinctProducts: int
    distinctSources: int
    firstObservedAt: str
    lastObservedAt: str
    catalogGrowth: Optional[float] = None
    priceChangeRatio: Optional[float] = None
    inStockRatio: Optional[float] = None
    confidence: float
    strength: Optional[float] = None
    fixtureDerived: bool
    publishable: bool
    reasons: list[str]
    signals: list[TrendSignalSchema]
    ffoTrend: Optional[dict] = None


class TrendAnalysisResponse(BaseModel):
    """Read-only trend analysis for one window over the observation history."""

    windowStart: str
    windowEnd: str
    generatedAt: str
    demandTrendStatus: str
    evidenceType: str
    catalogActivityStatus: str
    directDemandAvailable: bool
    sourceCoverage: int
    observationCount: int
    insufficientEvidenceReason: Optional[str] = None
    confidenceInterpretation: str
    limitations: list[str]
    candidates: list[TrendCandidateSchema]
    publishedCandidates: list[TrendCandidateSchema]
