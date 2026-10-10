"""D6 Trend Intelligence Engine — deterministic candidates computed from the
D5 observation history (``product_observations``).

What this engine can and cannot claim
-------------------------------------
The only evidence currently collected is *catalog / operational* (listing
counts, price, availability, source coverage, freshness) plus D5's historical
timestamps. **No authorized source currently provides a direct consumer-demand
signal** (search interest, sales/engagement velocity, review growth), so this
engine never manufactures a demand-based trend: it returns a typed
``insufficient_evidence`` outcome for demand and only reports catalog facts as
catalog facts. Catalog and operational signals are never presented as evidence
of consumer demand.

Signal taxonomy (every :class:`Signal` is tagged with exactly one kind):

- ``direct_demand``      — search interest / sales velocity / review growth.
  Available only when an authorized source supplies the metric with a
  documented meaning and a usable timestamp. **Not available today.**
- ``supporting``         — independent source coverage of a concept.
  Available from observations (count of distinct sources observing it).
- ``catalog_operational`` — listing counts, price change, availability,
  collection freshness. Catalog facts, never a demand claim.

Everything here is pure Python: deterministic, no database, no clock inside the
computation (windows and reference times are supplied by the caller), and never
Qwen / MediaPipe / an LLM. Equal inputs give equal output.

Reuse, not duplication: concept slugs come from
``app.trending.domain.normalize_term`` (the M14 canonical-term helper), and the
:func:`to_ffo_trend` projection aligns to the FFO v1.0 ``trend.schema.json``
field names (``trend_id``/``canonical_name``/``stage``/``confidence``/…) rather
than inventing a second trend entity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.trending.domain import normalize_term

# --- Signal taxonomy ---------------------------------------------------------

DIRECT_DEMAND = "direct_demand"
SUPPORTING = "supporting"
CATALOG_OPERATIONAL = "catalog_operational"

# Lifecycle stages. ``rising``/``plateau``/``declining`` reuse the FFO trend
# entity's advisory ``stage`` vocabulary; ``insufficient_evidence`` is our
# explicit typed outcome and must never be rendered as a trend claim.
STAGE_INSUFFICIENT = "insufficient_evidence"
STAGE_RISING = "rising"
STAGE_FLAT = "plateau"
STAGE_DECLINING = "declining"

# The single place that flips when an authorized demand provider is wired.
# Until then, demand is unavailable by design and no demand trend is produced.
DEMAND_SIGNAL_AVAILABLE = False

# --- Tunable heuristics (NOT empirically validated) --------------------------
# These shape *data-quality confidence* only. They never set the trend
# direction, which is a plain comparison of distinct products across two
# equal-length window halves. Documented choices, not science.
VOLUME_TARGET = 10          # observations for full volume credit
SOURCE_TARGET = 2           # distinct sources for full coverage credit
FRESH_HOURS = 24.0          # age at/below which data is fully fresh
STALE_HOURS = 168.0         # age at/above which freshness credit is zero
MIN_OBSERVATIONS = 3        # below this, a candidate is insufficient
GROWTH_RISING = 0.10        # catalog growth above this reads as rising
GROWTH_DECLINING = -0.10    # catalog growth below this reads as declining
MIN_PUBLISH_CONFIDENCE = 0.6

# Stable reason strings (audit + tests).
REASON_NO_DEMAND = "no authorized source provides a direct demand signal"
REASON_FIXTURE = "candidate includes fixture (synthetic) evidence"
REASON_ZERO_BASELINE = "no distinct products in the earlier window half (zero baseline)"
REASON_TOO_FEW = "fewer than the minimum observations for a stable comparison"
REASON_LOW_CONFIDENCE = "data-quality confidence below the publication threshold"


@dataclass(frozen=True)
class ObservationEvidence:
    """One D5 observation shaped for trend computation (DB → domain).

    ``category`` is the concept key taken from ``products.category``;
    observations without a category cannot be grouped and are ignored by the
    engine. Optional metrics stay ``None`` when the source did not provide
    them — never zero. ``is_fixture`` marks synthetic test evidence.
    """

    product_id: UUID
    category: Optional[str]
    source: str
    observed_at: datetime
    price: Optional[float] = None
    availability: Optional[bool] = None
    is_fixture: bool = False


@dataclass(frozen=True)
class Signal:
    """One audited component of a candidate: metric, kind, availability."""

    name: str
    kind: str
    available: bool
    value: Optional[float]
    unit: Optional[str]
    detail: str


@dataclass(frozen=True)
class TrendCandidate:
    """A concept's observation-history evidence for one window.

    ``confidence`` is confidence in the *data* (volume, source coverage,
    freshness); ``strength`` is the magnitude of the supported catalog signal.
    They are deliberately separate. ``stage`` reflects observed
    catalog/coverage activity and is **not** a consumer-demand statement.
    """

    concept: str
    canonical_name: str
    category: str
    window_start: datetime
    window_end: datetime
    observation_count: int
    distinct_products: int
    distinct_sources: int
    first_observed_at: datetime
    last_observed_at: datetime
    catalog_growth: Optional[float]
    price_change_ratio: Optional[float]
    in_stock_ratio: Optional[float]
    demand_signal_available: bool
    confidence: float
    strength: Optional[float]
    stage: str
    is_fixture: bool
    publishable: bool
    reasons: tuple[str, ...]
    signals: tuple[Signal, ...]


@dataclass(frozen=True)
class TrendAnalysis:
    """The full, auditable result for one window (candidates + demand status)."""

    window_start: datetime
    window_end: datetime
    candidates: tuple[TrendCandidate, ...]
    demand_trend_status: str
    demand_insufficient_reason: str
    # Window evidence coverage (D7): total observations loaded and the number
    # of distinct sources behind them. Additive counters, not a formula change.
    observation_count: int = 0
    source_coverage: int = 0


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _demand_signals() -> tuple[Signal, ...]:
    """The direct-demand signals we would report — all unavailable today."""
    return tuple(
        Signal(
            name=name,
            kind=DIRECT_DEMAND,
            available=False,
            value=None,
            unit=None,
            detail=REASON_NO_DEMAND,
        )
        for name in ("search_interest", "sales_velocity", "review_growth")
    )


def _build_candidate(
    slug: str, rows: list[ObservationEvidence], window_start: datetime, window_end: datetime
) -> TrendCandidate:
    rows = sorted(rows, key=lambda r: (r.observed_at, str(r.product_id), r.source))
    midpoint = window_start + (window_end - window_start) / 2
    first_half = [r for r in rows if r.observed_at < midpoint]
    second_half = [r for r in rows if r.observed_at >= midpoint]

    # Equal-length halves are compatible windows. Distinct product sets avoid
    # repeated identical observations inflating growth (D5 already prevents a
    # repeated identical payload from creating a new observation at all).
    products_first = {r.product_id for r in first_half}
    products_second = {r.product_id for r in second_half}
    catalog_growth: Optional[float] = None
    if products_first:  # zero baseline is not comparable — never divide
        catalog_growth = (len(products_second) - len(products_first)) / len(products_first)

    # Price change uses only observations that actually carried a price;
    # missing prices are skipped, never treated as zero.
    priced = [r for r in rows if r.price is not None]
    price_change_ratio: Optional[float] = None
    if len(priced) >= 2 and priced[0].price:  # guard divide-by-zero / None
        price_change_ratio = (priced[-1].price - priced[0].price) / priced[0].price

    with_avail = [r for r in rows if r.availability is not None]
    in_stock_ratio = (
        sum(1 for r in with_avail if r.availability) / len(with_avail)
        if with_avail
        else None
    )

    observation_count = len(rows)
    distinct_products = len({r.product_id for r in rows})
    distinct_sources = len({r.source for r in rows})
    first_observed_at = rows[0].observed_at
    last_observed_at = rows[-1].observed_at
    is_fixture = any(r.is_fixture for r in rows)

    age_hours = max(0.0, (window_end - last_observed_at).total_seconds() / 3600.0)
    volume = min(1.0, observation_count / VOLUME_TARGET)
    coverage = min(1.0, distinct_sources / SOURCE_TARGET)
    if age_hours <= FRESH_HOURS:
        freshness = 1.0
    elif age_hours >= STALE_HOURS:
        freshness = 0.0
    else:
        freshness = 1.0 - (age_hours - FRESH_HOURS) / (STALE_HOURS - FRESH_HOURS)
    confidence = round(0.4 * volume + 0.3 * coverage + 0.3 * freshness, 4)

    if observation_count < MIN_OBSERVATIONS or catalog_growth is None:
        stage = STAGE_INSUFFICIENT
    elif catalog_growth > GROWTH_RISING:
        stage = STAGE_RISING
    elif catalog_growth < GROWTH_DECLINING:
        stage = STAGE_DECLINING
    else:
        stage = STAGE_FLAT

    reasons: list[str] = []
    if is_fixture:
        reasons.append(REASON_FIXTURE)
    if not DEMAND_SIGNAL_AVAILABLE:
        reasons.append(REASON_NO_DEMAND)
    if catalog_growth is None:
        reasons.append(REASON_ZERO_BASELINE)
    if observation_count < MIN_OBSERVATIONS:
        reasons.append(REASON_TOO_FEW)
    if confidence < MIN_PUBLISH_CONFIDENCE:
        reasons.append(REASON_LOW_CONFIDENCE)

    publishable = (
        not is_fixture
        and DEMAND_SIGNAL_AVAILABLE
        and stage != STAGE_INSUFFICIENT
        and confidence >= MIN_PUBLISH_CONFIDENCE
    )

    signals: list[Signal] = [
        Signal(
            name="observation_count",
            kind=CATALOG_OPERATIONAL,
            available=True,
            value=float(observation_count),
            unit="count",
            detail="observations in the window (catalog fact)",
        ),
        Signal(
            name="distinct_products",
            kind=CATALOG_OPERATIONAL,
            available=True,
            value=float(distinct_products),
            unit="count",
            detail="distinct canonical products observed (catalog fact)",
        ),
        Signal(
            name="catalog_growth",
            kind=CATALOG_OPERATIONAL,
            available=catalog_growth is not None,
            value=catalog_growth,
            unit="ratio",
            detail="distinct products, later half vs earlier half (catalog fact)",
        ),
        Signal(
            name="price_change_ratio",
            kind=CATALOG_OPERATIONAL,
            available=price_change_ratio is not None,
            value=price_change_ratio,
            unit="ratio",
            detail="first vs last provided price in the window (catalog fact)",
        ),
        Signal(
            name="in_stock_ratio",
            kind=CATALOG_OPERATIONAL,
            available=in_stock_ratio is not None,
            value=in_stock_ratio,
            unit="ratio",
            detail="share of observations reported in stock",
        ),
        Signal(
            name="distinct_sources",
            kind=SUPPORTING,
            available=True,
            value=float(distinct_sources),
            unit="count",
            detail="independent sources observing the concept",
        ),
        *_demand_signals(),
    ]

    return TrendCandidate(
        concept=slug,
        canonical_name=slug.replace("_", " "),
        category=rows[0].category or slug,
        window_start=window_start,
        window_end=window_end,
        observation_count=observation_count,
        distinct_products=distinct_products,
        distinct_sources=distinct_sources,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        catalog_growth=catalog_growth,
        price_change_ratio=price_change_ratio,
        in_stock_ratio=in_stock_ratio,
        demand_signal_available=DEMAND_SIGNAL_AVAILABLE,
        confidence=confidence,
        strength=catalog_growth,
        stage=stage,
        is_fixture=is_fixture,
        publishable=publishable,
        reasons=tuple(reasons),
        signals=tuple(signals),
    )


def compute_trend_candidates(
    evidence: "tuple[ObservationEvidence, ...]",
    *,
    window_start: datetime,
    window_end: datetime,
) -> TrendAnalysis:
    """Compute deterministic trend candidates from observation evidence.

    Pure: the caller supplies the window and the already-loaded evidence, so
    there is no clock and no database access here. Candidates are grouped by
    canonical concept (``normalize_term(category)``) and returned sorted by
    concept, so the same evidence always yields the same result.
    """
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    groups: dict[str, list[ObservationEvidence]] = {}
    for row in evidence:
        if not row.category:
            continue  # cannot group an uncategorized observation
        groups.setdefault(normalize_term(row.category), []).append(row)

    candidates = tuple(
        _build_candidate(slug, groups[slug], window_start, window_end)
        for slug in sorted(groups)
    )
    return TrendAnalysis(
        window_start=window_start,
        window_end=window_end,
        candidates=candidates,
        demand_trend_status=STAGE_INSUFFICIENT,
        demand_insufficient_reason=REASON_NO_DEMAND,
        observation_count=len(evidence),
        source_coverage=len({row.source for row in evidence}),
    )


def to_ffo_trend(candidate: TrendCandidate) -> Optional[dict]:
    """Project a candidate onto the FFO v1.0 trend entity shape (reuse).

    Returns ``None`` unless the candidate is publishable, so fixture or
    insufficient-evidence candidates can never be emitted as a trend claim.
    ``growth`` here is the catalog/observation growth, never a demand claim,
    and ``source_type`` is ``INFERRED`` (derived from our own observations) —
    never ``MODEL_GENERATED``.
    """
    if not candidate.publishable:
        return None
    return {
        "trend_id": f"trend-{candidate.concept}",
        "canonical_name": candidate.canonical_name,
        "category": candidate.category,
        "stage": candidate.stage,
        "confidence": candidate.confidence,
        "growth": candidate.catalog_growth,
        "first_detected": candidate.first_observed_at.isoformat(),
        "last_updated": candidate.last_observed_at.isoformat(),
        "provenance": {
            "source": "discovery_observations",
            "source_type": "INFERRED",
            "created_at": candidate.first_observed_at.isoformat(),
            "updated_at": candidate.last_observed_at.isoformat(),
        },
        "signals": [
            {"source": "discovery_observations", "metric": s.name, "value": s.value}
            for s in candidate.signals
            if s.available and s.value is not None
        ],
    }
