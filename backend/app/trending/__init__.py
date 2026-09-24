"""M14 Trending package — provider-agnostic domain only (no DB, no keys)."""

from app.trending.domain import (
    ProductCandidate,
    Trend,
    TrendSignal,
    build_trends,
    load_test_adapter,
    matched_products,
    normalize_term,
    score_trend,
)

__all__ = [
    "ProductCandidate",
    "Trend",
    "TrendSignal",
    "build_trends",
    "load_test_adapter",
    "matched_products",
    "normalize_term",
    "score_trend",
]
