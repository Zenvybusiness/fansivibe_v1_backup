"""Comprehensive offline test suite for YouTube fashion signal aggregation and catalog concept matching (TRENDING-02).

Validates:
1. Deterministic concept extraction and category compatibility across the 6 core concepts.
2. Word-boundary enforcement and prevention of substring false positives.
3. Insufficient evidence handling (returns empty tuple, zero hallucination).
4. Raw source record provenance and statistics preservation.
5. Deduplication of repeated video observations.
6. Time-window aggregation and equal-halves velocity/growth calculation.
7. Zero baseline historical requirement (never claims growth/acceleration without baseline).
8. Missing metrics versus genuine zero values.
9. Sparse and insufficient evidence handling.
10. Data-quality confidence heuristic and freshness decay.
11. Evidence boundaries preservation: DEMAND_SIGNAL_AVAILABLE = False, media_attention signal taxonomy.
12. Concept-to-catalog matching with category and attribute compatibility.
13. Strict fixture product exclusion (`attributes["fixture"] = True` excluded from live shopping recommendations).
14. Rejection of weak matches and separation of trend confidence from product match confidence.
15. Valid trend with zero matching products handled gracefully.
16. Non-fabrication of prices, stock, URLs, and retailer offers.
17. Backward compatibility of Discovery Trending APIs (`GET /v1/discovery/trending`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_trend_repository
from app.api.schemas.discovery import DiscoveryTrendItemSchema, DiscoveryTrendingResponse
from app.application.fashion_video_trends import (
    AggregateFashionVideoTrends,
    MEDIA_ATTENTION_KIND,
    enrich_candidate_with_video_signal,
)
from app.domain.ports.source_adapter import RawSourceRecord, SourceAuthError
from app.domain.services.catalog_concept_matcher import CatalogConceptMatcher
from app.domain.services.fashion_concept_extraction import (
    FashionConceptExtractor,
    normalize_text,
)
from app.domain.services.fashion_video_aggregation import (
    FashionVideoTrendSignal,
    REASON_LOW_CONFIDENCE,
    REASON_MEDIA_ATTENTION_ONLY,
    REASON_TOO_FEW_VIDEOS,
    REASON_ZERO_BASELINE,
    STAGE_DECLINING,
    STAGE_INSUFFICIENT,
    STAGE_RISING,
    aggregate_video_observations,
)
from app.domain.services.trends import (
    DEMAND_SIGNAL_AVAILABLE,
    ObservationEvidence,
    TrendCandidate,
    compute_trend_candidates,
)
from app.infrastructure.external.youtube_source import YouTubeSourceAdapter
from app.main import app

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
W_START = NOW - timedelta(days=14)
W_END = NOW
MIDPOINT = W_START + (W_END - W_START) / 2  # NOW - 7 days


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def _raw_video(
    video_id: str,
    title: str,
    *,
    description: str = "",
    tags: tuple[str, ...] = (),
    published_at: Optional[datetime] = None,
    channel_id: str = "UC12345",
    channel_title: str = "Fashion Trends India",
    view_count: Optional[int] = None,
    like_count: Optional[int] = None,
    comment_count: Optional[int] = None,
) -> RawSourceRecord:
    ts = published_at or NOW - timedelta(days=2)
    payload = {
        "videoId": video_id,
        "title": title,
        "description": description,
        "publishedAt": ts.isoformat(),
        "channelId": channel_id,
        "channelTitle": channel_title,
        "videoCategoryId": "26",
        "regionCode": "IN",
        "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnails": {"default": {"url": f"https://i.ytimg.com/vi/{video_id}/default.jpg"}},
        "tags": list(tags),
    }
    if view_count is not None or like_count is not None or comment_count is not None:
        payload["statistics"] = {
            "viewCount": view_count,
            "likeCount": like_count,
            "commentCount": comment_count,
        }
    return RawSourceRecord(
        source="youtube_in",
        payload=payload,
        source_record_id=video_id,
        source_timestamp=ts,
    )


# ---------------------------------------------------------------------------
# 1. Concept Extraction & Vocabulary Compatibility
# ---------------------------------------------------------------------------


def test_concept_extraction_exact_vocabulary() -> None:
    extractor = FashionConceptExtractor()

    cases = [
        ("Summer Lookbook: Oversized Shirts Styling", "oversized_shirts", "tops"),
        ("Baggy Denim Jacket Outfit Ideas", "denim_jackets", "outerwear"),
        ("How to Style Wide-leg Trousers for Men", "wide_leg_trousers", "bottoms"),
        ("Best Cargo Trousers for Streetwear", "cargo_trousers", "bottoms"),
        ("Pure Linen Shirts Summer Haul", "linen_shirts", "tops"),
        ("Top 5 Minimalist Sneakers Every Wardrobe Needs", "minimalist_sneakers", "footwear"),
    ]

    for title, expected_id, expected_category in cases:
        concepts = extractor.extract_from_text(title=title)
        assert len(concepts) == 1, f"Expected 1 concept for '{title}', got {len(concepts)}"
        assert concepts[0].concept_id == expected_id
        assert concepts[0].category == expected_category
        assert concepts[0].confidence == 1.0  # title match


def test_concept_extraction_avoids_substring_false_positives() -> None:
    extractor = FashionConceptExtractor()

    false_positive_titles = [
        "Condemning the fast fashion industry",             # contains 'denim' substring in 'condemning'
        "Rampant inflation in retail pricing",             # contains 'pant' in 'rampant'
        "Precargo logistics report and shipping",          # contains 'cargo' in 'precargo'
        "Table linen and dining room decor haul",          # 'table linen' should be suppressed
        "Linen tablecloth styling for dinner",             # negative pattern match
        "Bed linen and bedroom makeover ideas",            # negative pattern match
        "Tight skinny pants styling",                      # negative pattern for wide_leg
    ]

    for title in false_positive_titles:
        concepts = extractor.extract_from_text(title=title)
        assert len(concepts) == 0, f"Expected 0 concepts for '{title}', got {[c.concept_id for c in concepts]}"


def test_concept_extraction_insufficient_evidence_returns_empty() -> None:
    extractor = FashionConceptExtractor()

    non_fashion_titles = [
        "My Morning Routine & Coffee Vlog",
        "Best Gaming Laptops for 2026",
        "Exploring Mumbai Street Food",
        "General Fashion Trends Discussion",  # no specific concept mentioned
    ]

    for title in non_fashion_titles:
        concepts = extractor.extract_from_text(title=title)
        assert concepts == (), f"Expected empty extraction for '{title}', got {concepts}"


def test_concept_extraction_preserves_provenance() -> None:
    extractor = FashionConceptExtractor()
    pub_time = NOW - timedelta(days=3)
    record = _raw_video(
        video_id="yt_test_001",
        title="10 Linen Shirts Every Guy Needs",
        channel_id="ch_fashion_in",
        channel_title="Style India Hub",
        published_at=pub_time,
        view_count=45000,
        like_count=1800,
        comment_count=120,
    )

    extracted = extractor.extract_from_raw_record(record)
    assert len(extracted) == 1
    c = extracted[0]

    assert c.concept_id == "linen_shirts"
    assert c.canonical_name == "Linen Shirts"
    assert c.category == "tops"
    assert c.video_id == "yt_test_001"
    assert c.channel_id == "ch_fashion_in"
    assert c.channel_title == "Style India Hub"
    assert c.published_at == pub_time
    assert c.view_count == 45000
    assert c.like_count == 1800
    assert c.comment_count == 120
    assert c.video_url == "https://www.youtube.com/watch?v=yt_test_001"


# ---------------------------------------------------------------------------
# 2. Duplicate Video Handling & Time-Window Aggregation
# ---------------------------------------------------------------------------


def test_duplicate_video_handling_in_aggregation() -> None:
    extractor = FashionConceptExtractor()
    pub_time = NOW - timedelta(days=3)

    # Same video collected across 3 different runs
    records = [
        _raw_video("vid_1", "Oversized Shirts Lookbook", published_at=pub_time, view_count=1000),
        _raw_video("vid_1", "Oversized Shirts Lookbook", published_at=pub_time, view_count=1200),  # updated stats
        _raw_video("vid_1", "Oversized Shirts Lookbook", published_at=pub_time, view_count=1200),  # duplicate
    ]

    concepts = []
    for r in records:
        concepts.extend(extractor.extract_from_raw_record(r))

    signals = aggregate_video_observations(concepts, window_start=W_START, window_end=W_END)
    assert len(signals) == 1
    sig = signals[0]

    assert sig.distinct_videos == 1
    assert sig.contributing_video_ids == ("vid_1",)
    assert sig.total_views == 1200


def test_time_window_aggregation_and_equal_halves() -> None:
    extractor = FashionConceptExtractor()

    # 2 videos in earlier half (W_START to MIDPOINT)
    # 4 videos in later half (MIDPOINT to W_END)
    records = [
        _raw_video("v1", "Oversized Shirts Vol 1", published_at=W_START + timedelta(days=2), channel_id="ch1"),
        _raw_video("v2", "Oversized Shirts Vol 2", published_at=W_START + timedelta(days=4), channel_id="ch2"),
        _raw_video("v3", "Oversized Shirts Vol 3", published_at=MIDPOINT + timedelta(days=1), channel_id="ch1"),
        _raw_video("v4", "Oversized Shirts Vol 4", published_at=MIDPOINT + timedelta(days=2), channel_id="ch2"),
        _raw_video("v5", "Oversized Shirts Vol 5", published_at=MIDPOINT + timedelta(days=3), channel_id="ch3"),
        _raw_video("v6", "Oversized Shirts Vol 6", published_at=MIDPOINT + timedelta(days=4), channel_id="ch4"),
    ]

    concepts = []
    for r in records:
        concepts.extend(extractor.extract_from_raw_record(r))

    signals = aggregate_video_observations(concepts, window_start=W_START, window_end=W_END)
    assert len(signals) == 1
    sig = signals[0]

    assert sig.concept_id == "oversized_shirts"
    assert sig.distinct_videos == 6
    assert sig.distinct_channels == 4
    # Growth = (4 - 2) / 2 = 1.0 (+100%)
    assert sig.upload_growth == 1.0
    assert sig.stage == STAGE_RISING
    assert sig.upload_velocity_per_week == 3.0  # 6 videos over 14 days = 3 per week
    assert sig.confidence >= 0.6
    assert sig.publishable is True


def test_zero_baseline_historical_requirement() -> None:
    extractor = FashionConceptExtractor()

    # 4 videos in later half, 0 in earlier half
    records = [
        _raw_video("v1", "Cargo Trousers Vol 1", published_at=MIDPOINT + timedelta(days=1)),
        _raw_video("v2", "Cargo Trousers Vol 2", published_at=MIDPOINT + timedelta(days=2)),
        _raw_video("v3", "Cargo Trousers Vol 3", published_at=MIDPOINT + timedelta(days=3)),
        _raw_video("v4", "Cargo Trousers Vol 4", published_at=MIDPOINT + timedelta(days=4)),
    ]

    concepts = []
    for r in records:
        concepts.extend(extractor.extract_from_raw_record(r))

    signals = aggregate_video_observations(concepts, window_start=W_START, window_end=W_END)
    assert len(signals) == 1
    sig = signals[0]

    assert sig.distinct_videos == 4
    assert sig.upload_growth is None  # zero baseline prevents growth division
    assert sig.stage == STAGE_INSUFFICIENT
    assert REASON_ZERO_BASELINE in sig.reasons
    assert sig.publishable is False


def test_missing_metrics_vs_genuine_zero_values() -> None:
    extractor = FashionConceptExtractor()

    # Case A: Missing metrics (statistics omitted by provider)
    rec_missing = [
        _raw_video("v1", "Linen Shirts 1", published_at=W_START + timedelta(days=2)),
        _raw_video("v2", "Linen Shirts 2", published_at=MIDPOINT + timedelta(days=2)),
        _raw_video("v3", "Linen Shirts 3", published_at=MIDPOINT + timedelta(days=4)),
    ]
    concepts_missing = []
    for r in rec_missing:
        concepts_missing.extend(extractor.extract_from_raw_record(r))

    sig_missing = aggregate_video_observations(concepts_missing, window_start=W_START, window_end=W_END)[0]
    assert sig_missing.total_views is None
    assert sig_missing.total_likes is None
    assert sig_missing.total_comments is None

    # Case B: Genuine zero metrics (provider explicitly reported 0)
    rec_zeros = [
        _raw_video("v1", "Denim Jackets 1", published_at=W_START + timedelta(days=2), view_count=0, like_count=0, comment_count=0),
        _raw_video("v2", "Denim Jackets 2", published_at=MIDPOINT + timedelta(days=2), view_count=100, like_count=5, comment_count=0),
        _raw_video("v3", "Denim Jackets 3", published_at=MIDPOINT + timedelta(days=4), view_count=0, like_count=0, comment_count=0),
    ]
    concepts_zeros = []
    for r in rec_zeros:
        concepts_zeros.extend(extractor.extract_from_raw_record(r))

    sig_zeros = aggregate_video_observations(concepts_zeros, window_start=W_START, window_end=W_END)[0]
    assert sig_zeros.total_views == 100
    assert sig_zeros.total_likes == 5
    assert sig_zeros.total_comments == 0


def test_sparse_and_insufficient_evidence() -> None:
    extractor = FashionConceptExtractor()

    # Only 2 videos (< MIN_VIDEOS = 3)
    records = [
        _raw_video("v1", "Minimalist Sneakers 1", published_at=W_START + timedelta(days=2)),
        _raw_video("v2", "Minimalist Sneakers 2", published_at=MIDPOINT + timedelta(days=2)),
    ]
    concepts = []
    for r in records:
        concepts.extend(extractor.extract_from_raw_record(r))

    signals = aggregate_video_observations(concepts, window_start=W_START, window_end=W_END)
    assert len(signals) == 1
    sig = signals[0]

    assert sig.distinct_videos == 2
    assert sig.stage == STAGE_INSUFFICIENT
    assert REASON_TOO_FEW_VIDEOS in sig.reasons
    assert sig.publishable is False


def test_stale_data_decays_confidence() -> None:
    extractor = FashionConceptExtractor()

    # 4 videos published 10 days ago (240 hours stale)
    records = [
        _raw_video("v1", "Denim Jackets 1", published_at=W_START + timedelta(days=1)),
        _raw_video("v2", "Denim Jackets 2", published_at=W_START + timedelta(days=2)),
        _raw_video("v3", "Denim Jackets 3", published_at=W_START + timedelta(days=3)),
        _raw_video("v4", "Denim Jackets 4", published_at=W_START + timedelta(days=4)),
    ]
    concepts = []
    for r in records:
        concepts.extend(extractor.extract_from_raw_record(r))

    sig = aggregate_video_observations(concepts, window_start=W_START, window_end=W_END)[0]
    # Freshness is 0.0 because age > 168 hours
    assert sig.confidence < 0.6
    assert REASON_LOW_CONFIDENCE in sig.reasons
    assert sig.publishable is False


# ---------------------------------------------------------------------------
# 3. Evidence Boundaries & Non-Demand Invariants
# ---------------------------------------------------------------------------


def test_preserve_evidence_boundaries() -> None:
    # 1. DEMAND_SIGNAL_AVAILABLE is hardcoded False
    assert DEMAND_SIGNAL_AVAILABLE is False

    # 2. D6 Candidate enrichment classifies video signal as media_attention (never direct_demand)
    dummy_candidate = TrendCandidate(
        concept="oversized_shirts",
        canonical_name="Oversized Shirts",
        category="tops",
        window_start=W_START,
        window_end=W_END,
        observation_count=10,
        distinct_products=5,
        distinct_sources=2,
        first_observed_at=W_START,
        last_observed_at=W_END,
        catalog_growth=0.5,
        price_change_ratio=None,
        in_stock_ratio=1.0,
        demand_signal_available=DEMAND_SIGNAL_AVAILABLE,
        confidence=0.8,
        strength=0.5,
        stage="rising",
        is_fixture=False,
        publishable=False,  # False because demand is unavailable
        reasons=("catalog growth observed",),
        signals=(),
    )

    dummy_signal = FashionVideoTrendSignal(
        concept_id="oversized_shirts",
        canonical_name="Oversized Shirts",
        category="tops",
        window_start=W_START,
        window_end=W_END,
        distinct_videos=6,
        distinct_channels=3,
        upload_velocity_per_week=3.0,
        upload_growth=0.5,
        total_views=10000,
        total_likes=500,
        total_comments=50,
        first_published_at=W_START + timedelta(days=2),
        last_published_at=W_END - timedelta(hours=12),
        confidence=0.85,
        strength=0.5,
        stage="rising",
        publishable=True,
        reasons=(REASON_MEDIA_ATTENTION_ONLY,),
        contributing_video_ids=("v1", "v2"),
    )

    enriched = enrich_candidate_with_video_signal(dummy_candidate, dummy_signal)

    # Candidate confidence and stage remain unmutated
    assert enriched.confidence == dummy_candidate.confidence
    assert enriched.demand_signal_available is False

    # Enriched signals all have kind="media_attention"
    media_signals = [s for s in enriched.signals if s.kind == MEDIA_ATTENTION_KIND]
    assert len(media_signals) == 4
    for s in media_signals:
        assert s.kind == MEDIA_ATTENTION_KIND
        assert "demand" not in s.kind


# ---------------------------------------------------------------------------
# 4. Catalog Concept Matching & Fixture Product Exclusion
# ---------------------------------------------------------------------------


def test_catalog_matching_category_and_attribute_compatibility() -> None:
    matcher = CatalogConceptMatcher()

    genuine_products = [
        # Match for linen_shirts: tops, material linen
        {
            "id": "prod_linen_1",
            "title": "Classic Resort Linen Shirt",
            "brand": "Heritage India",
            "category": "tops",
            "subcategory": "shirt",
            "price": 2499.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://amazon.in/dp/B001",
            "attributes": {"material": "linen", "fit": "regular", "fixture": False},
        },
        # Match for oversized_shirts: tops, fit oversized
        {
            "id": "prod_oversized_1",
            "title": "Relaxed Drop-Shoulder Oversized Tee",
            "brand": "Urban Atelier",
            "category": "tops",
            "subcategory": "t-shirt",
            "price": 1299.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://amazon.in/dp/B002",
            "attributes": {"fit": "oversized", "silhouette": "relaxed", "fixture": False},
        },
        # Match for cargo_trousers: bottoms, cargo
        {
            "id": "prod_cargo_1",
            "title": "Multi-Pocket Utility Cargo Trousers",
            "brand": "Tactical Lab",
            "category": "bottoms",
            "subcategory": "cargo",
            "price": 3199.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://amazon.in/dp/B003",
            "attributes": {"style_tags": ["cargo", "utility"], "fixture": False},
        },
        # Non-matching: bottoms (chinos) should NOT match linen_shirts (tops)
        {
            "id": "prod_chinos_1",
            "title": "Slim Fit Casual Chinos",
            "brand": "Daily Wear",
            "category": "bottoms",
            "subcategory": "chinos",
            "price": 1899.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://amazon.in/dp/B004",
            "attributes": {"material": "cotton", "fit": "slim", "fixture": False},
        },
    ]

    # 1. Match linen_shirts
    linen_matches = matcher.match_products("linen_shirts", genuine_products)
    assert len(linen_matches) == 1
    assert linen_matches[0].product_id == "prod_linen_1"
    assert linen_matches[0].match_score >= 0.8
    assert "material matches 'linen'" in linen_matches[0].match_reasons

    # 2. Match oversized_shirts
    oversized_matches = matcher.match_products("oversized_shirts", genuine_products)
    assert len(oversized_matches) == 1
    assert oversized_matches[0].product_id == "prod_oversized_1"
    assert oversized_matches[0].match_score >= 0.8

    # 3. Match cargo_trousers
    cargo_matches = matcher.match_products("cargo_trousers", genuine_products)
    assert len(cargo_matches) == 1
    assert cargo_matches[0].product_id == "prod_cargo_1"


def test_fixture_product_exclusion_from_shopping_matches() -> None:
    matcher = CatalogConceptMatcher()

    catalog_with_fixtures = [
        # Fixture product (marked fixture=True)
        {
            "id": "SEED-TOP-001",
            "title": "Studio Linen Resort Shirt",
            "brand": "Studio Atelier",
            "category": "tops",
            "subcategory": "shirt",
            "price": 2499.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://catalog.fixture.test/products/SEED-TOP-001",
            "attributes": {"material": "linen", "fixture": True, "synthetic": True},
        },
        # Genuine product (marked fixture=False)
        {
            "id": "AMZ-TOP-001",
            "title": "Authentic Linen Summer Shirt",
            "brand": "Amazon Brand",
            "category": "tops",
            "subcategory": "shirt",
            "price": 2299.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://amazon.in/dp/B001",
            "attributes": {"material": "linen", "fixture": False},
        },
    ]

    # Live shopping match (exclude_fixtures=True)
    live_matches = matcher.match_products("linen_shirts", catalog_with_fixtures, exclude_fixtures=True)
    assert len(live_matches) == 1
    assert live_matches[0].product_id == "AMZ-TOP-001"
    assert live_matches[0].is_fixture is False

    # Debug / test inspection (exclude_fixtures=False) includes fixture
    debug_matches = matcher.match_products("linen_shirts", catalog_with_fixtures, exclude_fixtures=False)
    assert len(debug_matches) == 2


def test_valid_trend_with_zero_matching_products() -> None:
    matcher = CatalogConceptMatcher()
    products: list[dict] = []

    matches = matcher.match_products("minimalist_sneakers", products)
    assert matches == ()


def test_catalog_matching_preserves_provenance_and_no_fabrication() -> None:
    matcher = CatalogConceptMatcher()
    product = {
        "id": "GENUINE-001",
        "title": "Denim Overshirt Jacket",
        "brand": "Levi Strauss",
        "category": "outerwear",
        "subcategory": "jacket",
        "price": 4999.0,
        "currency": "INR",
        "availability": True,
        "product_url": "https://amazon.in/dp/B00XYZ",
        "image_urls": ["https://m.media-amazon.com/images/I/71xyz.jpg"],
        "attributes": {"material": "denim", "fixture": False},
        "source": "amazon_in",
    }

    matches = matcher.match_products("denim_jackets", [product])
    assert len(matches) == 1
    m = matches[0]

    assert m.product_id == "GENUINE-001"
    assert m.title == "Denim Overshirt Jacket"
    assert m.brand == "Levi Strauss"
    assert m.price == 4999.0
    assert m.currency == "INR"
    assert m.availability is True
    assert m.product_url == "https://amazon.in/dp/B00XYZ"
    assert m.image_url == "https://m.media-amazon.com/images/I/71xyz.jpg"
    assert m.retailer == "Amazon India"


# ---------------------------------------------------------------------------
# 5. Fail-Closed Credential Boundary
# ---------------------------------------------------------------------------


def test_fail_closed_credential_boundary_preserved() -> None:
    # Unset API key must raise SourceAuthError without making network calls
    adapter = YouTubeSourceAdapter(api_key="")
    with pytest.raises(SourceAuthError) as exc_info:
        adapter.fetch_batch()

    assert "YouTube Data API credentials not configured" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. Backward Compatibility of Discovery Trending API
# ---------------------------------------------------------------------------


class _StubTrendRepo:
    def observations_in_window(self, *, window_start, window_end):
        return (
            ObservationEvidence(
                product_id=uuid4(),
                category="outerwear",
                source="amazon_in",
                observed_at=NOW - timedelta(days=2),
                price=3499.0,
                availability=True,
                is_fixture=False,
            ),
        )


def test_discovery_trending_api_backward_compatibility() -> None:
    app.dependency_overrides[get_trend_repository] = lambda: _StubTrendRepo()
    app.dependency_overrides[get_current_user_id] = lambda: UUID(int=1)

    try:
        client = TestClient(app)
        res = client.get("/v1/discovery/trending", headers={"Authorization": "Bearer dev"})
        assert res.status_code == 200
        body = res.json()

        # Contract verification
        assert "windowStart" in body
        assert "windowEnd" in body
        assert "generatedAt" in body
        assert body["demandTrendStatus"] == "insufficient_evidence"
        assert body["evidenceType"] == "catalog_activity"
        assert body["directDemandAvailable"] is False
        assert "observationCount" in body
        assert "sourceCoverage" in body
        assert "items" in body

        # Item schema verification
        if body["items"]:
            item = body["items"][0]
            assert "concept" in item
            assert "canonicalName" in item
            assert "category" in item
            assert "signals" in item
            assert "matchedProducts" in item
            assert isinstance(item["matchedProducts"], list)

    finally:
        app.dependency_overrides.clear()
