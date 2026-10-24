"""Application use case for fashion video signal aggregation and catalog concept matching (TRENDING-02).

Orchestrates:
1. Concept extraction from raw video records using ``FashionConceptExtractor``.
2. Time-window media attention aggregation using ``aggregate_video_observations``.
3. Grounded catalog matching using ``CatalogConceptMatcher`` (strictly excluding fixtures).
4. Backward-compatible signal bridge for D6/D7 trend candidates.

Preserves all frozen boundaries:
- DEMAND_SIGNAL_AVAILABLE = False is strictly maintained.
- Creator attention metrics are classified as media_attention (never direct_demand).
- Genuine catalog product matching excludes fixture products.
- No parallel product databases or migrations are created.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.domain.ports.source_adapter import RawSourceRecord
from app.domain.services.catalog_concept_matcher import (
    CatalogConceptMatcher,
    MatchedCatalogProduct,
)
from app.domain.services.fashion_concept_extraction import (
    ExtractedVideoConcept,
    FashionConceptExtractor,
)
from app.domain.services.fashion_video_aggregation import (
    FashionVideoTrendSignal,
    aggregate_video_observations,
)
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE, Signal, TrendCandidate

MEDIA_ATTENTION_KIND = "media_attention"


@dataclass(frozen=True)
class AggregatedVideoTrend:
    """One aggregated video trend concept with its media signal and matched products."""

    concept_id: str
    canonical_name: str
    category: str
    signal: FashionVideoTrendSignal
    matched_products: tuple[MatchedCatalogProduct, ...] = field(default_factory=tuple)


class AggregateFashionVideoTrends:
    """Orchestrates concept extraction, aggregation, and catalog matching."""

    def __init__(
        self,
        *,
        extractor: Optional[FashionConceptExtractor] = None,
        matcher: Optional[CatalogConceptMatcher] = None,
    ) -> None:
        self._extractor = extractor or FashionConceptExtractor()
        self._matcher = matcher or CatalogConceptMatcher()

    def process_records(
        self,
        raw_records: Sequence[RawSourceRecord],
        *,
        window_start: datetime,
        window_end: datetime,
        catalog_products: Sequence[Any] = (),
        exclude_fixtures: bool = True,
        max_products_per_trend: int = 10,
    ) -> tuple[AggregatedVideoTrend, ...]:
        """Process raw YouTube records into aggregated fashion video trends."""
        # 1. Extract concepts from each raw record
        all_concepts: list[ExtractedVideoConcept] = []
        for record in raw_records:
            extracted = self._extractor.extract_from_raw_record(record)
            all_concepts.extend(extracted)

        # 2. Aggregate observations over time window
        signals = aggregate_video_observations(
            all_concepts,
            window_start=window_start,
            window_end=window_end,
        )

        # 3. Match concepts to catalog products
        trends: list[AggregatedVideoTrend] = []
        for sig in signals:
            matched: tuple[MatchedCatalogProduct, ...] = ()
            if catalog_products:
                matched = self._matcher.match_products(
                    sig.concept_id,
                    catalog_products,
                    exclude_fixtures=exclude_fixtures,
                    limit=max_products_per_trend,
                )

            trends.append(
                AggregatedVideoTrend(
                    concept_id=sig.concept_id,
                    canonical_name=sig.canonical_name,
                    category=sig.category,
                    signal=sig,
                    matched_products=matched,
                )
            )

        return tuple(trends)


def enrich_candidate_with_video_signal(
    candidate: TrendCandidate,
    video_signal: Optional[FashionVideoTrendSignal],
) -> TrendCandidate:
    """Enrich a D6 TrendCandidate with non-invasive media attention signals.

    Preserves D6 confidence, stage, and DEMAND_SIGNAL_AVAILABLE = False.
    """
    if not video_signal:
        # Append unavailable media attention signal
        unavailable_signal = Signal(
            name="youtube_video_attention",
            kind=MEDIA_ATTENTION_KIND,
            available=False,
            value=None,
            unit="videos",
            detail="no YouTube creator video observations in window",
        )
        return replace(candidate, signals=(*candidate.signals, unavailable_signal))

    # Append available media attention signals
    media_signals: list[Signal] = [
        Signal(
            name="youtube_video_count",
            kind=MEDIA_ATTENTION_KIND,
            available=True,
            value=float(video_signal.distinct_videos),
            unit="videos",
            detail=(
                f"{video_signal.distinct_videos} distinct YouTube fashion videos from "
                f"{video_signal.distinct_channels} channels (media attention, not demand)"
            ),
        ),
        Signal(
            name="youtube_channel_count",
            kind=MEDIA_ATTENTION_KIND,
            available=True,
            value=float(video_signal.distinct_channels),
            unit="channels",
            detail="distinct creator channels publishing content for this concept",
        ),
        Signal(
            name="youtube_upload_growth",
            kind=MEDIA_ATTENTION_KIND,
            available=video_signal.upload_growth is not None,
            value=video_signal.upload_growth,
            unit="ratio",
            detail=(
                "video upload growth, later half vs earlier half (creator attention)"
                if video_signal.upload_growth is not None
                else "no distinct videos in earlier window half (zero baseline)"
            ),
        ),
    ]

    if video_signal.total_views is not None:
        media_signals.append(
            Signal(
                name="youtube_total_views",
                kind=MEDIA_ATTENTION_KIND,
                available=True,
                value=float(video_signal.total_views),
                unit="views",
                detail="total verified video views across observed content",
            )
        )

    return replace(
        candidate,
        signals=(*candidate.signals, *media_signals),
    )
