"""M14 Trending domain contracts (provider-agnostic, in-memory).

Real provider integrations (YouTube Data API v3, Google Trends, Flipkart
Affiliate, Amazon PA-API) are NOT CONNECTED — CREDENTIAL/ACCESS REQUIRED.
See docs/architecture/TRENDING_PROVIDER_VALIDATION.md. The deterministic
test adapter below is the only bundled signal source; it carries fixed
provenance and never poses as live production connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re

# ponytail: alias table covers only demo vocabulary; expand from a
# provider-driven dictionary when a real source is connected.


@dataclass(frozen=True)
class TrendSignal:
    """One raw observation from a trend source."""

    source: str
    source_identifier: str
    observed_term: str
    category: str
    region: str
    observed_at: datetime
    growth: float | None = None
    volume: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Trend:
    """One normalized, scored trend entity."""

    trend_id: str
    canonical_name: str
    category: str
    attributes: dict
    region: str
    velocity: float
    confidence: float
    freshness_hours: float | None
    supporting_signals: int
    provenance: tuple


@dataclass(frozen=True)
class ProductCandidate:
    """One purchasable product matched to a trend. No fabricated fields:
    price/url/image/availability travel verbatim from the source or stay
    absent (None)."""

    source: str
    source_product_id: str
    name: str
    brand: str
    category: str
    price: float | None
    currency: str
    image_url: str | None
    availability: bool | None
    product_url: str | None
    affiliate_url: str | None
    attributes: dict
    provenance: dict
    observed_at: datetime


_ALIASES = {
    "baggy denim jacket": "oversized_denim_jacket",
    "loose denim outerwear": "oversized_denim_jacket",
    "oversized jean jacket": "oversized_denim_jacket",
    "oversized denim jacket": "oversized_denim_jacket",
    "baggy cargos": "wide_leg_cargo_pants",
    "parachute pants": "wide_leg_cargo_pants",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_term(term: str) -> str:
    """Deterministic term → canonical slug. Unknown terms slugify; never LLM."""
    key = " ".join(term.lower().split())
    if key in _ALIASES:
        return _ALIASES[key]
    slug = _SLUG_RE.sub("_", key).strip("_")
    return re.sub(r"_+", "_", slug) or "unknown"


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def score_trend(signals: list, now: datetime) -> tuple:
    """Deterministic (velocity, confidence) from legitimate signals only.

    Missing metrics stay missing (ignored, never synthesized). Freshness
    decays linearly over 48h; cross-source corroboration (≥2 distinct
    sources) adds confidence. Returns (0.0, 0.0) for empty input.
    """
    if not signals:
        return (0.0, 0.0)
    growths = [s.growth for s in signals if s.growth is not None]
    velocity = _clamp01(sum(growths) / len(growths)) if growths else 0.0
    sources = {s.source for s in signals}
    ages_h = [(now - s.observed_at).total_seconds() / 3600.0 for s in signals]
    freshest = min(ages_h)
    freshness = _clamp01(1.0 - freshest / 48.0)
    corroboration = 0.25 if len(sources) >= 2 else 0.0
    volume_boost = 0.1 if any(s.volume is not None for s in signals) else 0.0
    confidence = _clamp01(0.35 * velocity + 0.3 * freshness + corroboration + volume_boost)
    return (velocity, confidence)


def build_trends(
    signals: list,
    products: list,
    now: datetime,
    min_score: float = 0.55,
) -> list:
    """Normalize → group → score → rank. Provider failure isolation lives
    in the caller: fetch each source separately so one exception never
    drops the others (see tests). Dedup is by (source, source_product_id)
    only — never merged on similar names."""
    groups: dict = {}
    for signal in signals:
        groups.setdefault(normalize_term(signal.observed_term), []).append(signal)
    seen: set = set()
    unique_products = []
    for product in products:
        key = (product.source, product.source_product_id)
        if key not in seen:
            seen.add(key)
            unique_products.append(product)
    trends = []
    for slug, group in groups.items():
        velocity, confidence = score_trend(group, now)
        if confidence < min_score:
            continue
        sources = sorted({s.source for s in group})
        if len(sources) < 2:
            continue
        ages_h = [(now - s.observed_at).total_seconds() / 3600.0 for s in group]
        trends.append(
            Trend(
                trend_id=f"trend-{slug}",
                canonical_name=slug.replace("_", " "),
                category=group[0].category,
                attributes={},
                region=group[0].region,
                velocity=velocity,
                confidence=confidence,
                freshness_hours=min(ages_h),
                supporting_signals=len(group),
                provenance=tuple(
                    {
                        "source": s.source,
                        "source_identifier": s.source_identifier,
                        "observed_at": s.observed_at.isoformat(),
                    }
                    for s in group
                ),
            )
        )
    trends.sort(key=lambda t: (-t.confidence, t.trend_id))
    return trends


def matched_products(products: list, trend_id: str) -> list:
    """Products for one trend, preserving source provenance verbatim."""
    slug = trend_id.removeprefix("trend-")
    return [p for p in products if normalize_term(p.name) == slug]


# NOT CONNECTED test adapter — deterministic fixtures with fixed
# provenance. Real providers require credentials (see M14 report).
TEST_SIGNALS: list = []
TEST_PRODUCTS: list = []


def _utc(year: int, month: int, day: int, hour: int = 2) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def load_test_adapter(now: datetime) -> tuple:
    """Deterministic adapter signals. Raises nothing; a failing real
    provider must be caught by the caller so sibling sources survive."""
    signals = [
        TrendSignal(
            source="youtube_in",
            source_identifier="yt-test-1",
            observed_term="oversized denim jacket",
            category="outerwear",
            region="IN",
            observed_at=now,
            growth=0.48,
            volume=120.0,
        ),
        TrendSignal(
            source="google_trends_in",
            source_identifier="gt-test-1",
            observed_term="baggy denim jacket",
            category="outerwear",
            region="IN",
            observed_at=now,
            growth=0.52,
            volume=88.0,
        ),
    ]
    products = [
        ProductCandidate(
            source="test_commerce",
            source_product_id="TEST-001",
            name="oversized denim jacket",
            brand="Test Brand",
            category="outerwear",
            price=1299.0,
            currency="INR",
            image_url=None,
            availability=True,
            product_url=None,
            affiliate_url=None,
            attributes={},
            provenance={"source": "test_commerce", "note": "NOT CONNECTED fixture"},
            observed_at=now,
        ),
    ]
    return (signals, products)
