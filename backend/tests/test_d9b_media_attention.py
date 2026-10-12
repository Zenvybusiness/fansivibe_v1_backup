"""D9B media-attention domain foundation and offline tests (Stage 1).

Covers pure Python domain entities, deterministic normalization, URL and outlet
identity extraction, headline canonicalization, 48-hour inception-anchored
Jaccard story clustering, status matrix enforcement, numeric integrity, count
hierarchy, and chaining prevention.

Zero database, zero network, zero LLM. Every test here is completely offline.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain.ports.source_adapter import RawSourceRecord
from app.domain.services.media_attention import (
    ALLOWED_STATUS_PAIRS,
    CLUSTER_INCEPTION_WINDOW,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_TRUNCATED,
    COMPLETENESS_UNAVAILABLE,
    DEFAULT_CLUSTERING_VERSION,
    DEFAULT_QUERY_CONFIG_VERSION,
    DEFAULT_VALUE_SCALE,
    GEO_TYPE_COUNTRY,
    JACCARD_SIMILARITY_THRESHOLD,
    METRIC_MEDIA_ATTENTION,
    QUERY_KIND_CONCEPT,
    SIGNAL_KIND,
    SOURCE_GDELT_DOC,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_PRESENT,
    STATUS_SUPPRESSED,
    ContributingRecordAssignment,
    MediaArticle,
    MediaAttentionEvidence,
    MediaAttentionObservation,
    MediaAttentionResult,
    StoryCluster,
    canonicalize_headline_tokens,
    cluster_stories,
    extract_outlet_domain,
    jaccard_similarity,
    normalize_article_url,
    normalize_media_attention,
    parse_media_article,
    parse_media_timestamp,
)
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE

_T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc)
_T_END = datetime(2026, 1, 12, 10, 0, 0, tzinfo=timezone.utc)


def _valid_obs_kwargs(**overrides) -> dict:
    base = {
        "source": SOURCE_GDELT_DOC,
        "metric": METRIC_MEDIA_ATTENTION,
        "query_kind": QUERY_KIND_CONCEPT,
        "query_key": "quiet_luxury",
        "query_display": "Quiet Luxury",
        "geo_scope": "IN",
        "geo_scope_type": GEO_TYPE_COUNTRY,
        "aggregation_interval": "rolling_7d",
        "period_start": _T0,
        "period_end": _T_END,
        "value_status": STATUS_PRESENT,
        "completeness_status": COMPLETENESS_COMPLETE,
        "value": 4.0,
        "value_scale": DEFAULT_VALUE_SCALE,
        "raw_article_count": 6,
        "distinct_outlet_count": 3,
        "estimated_deduplicated_story_count": 4,
        "query_config_version": DEFAULT_QUERY_CONFIG_VERSION,
        "clustering_version": DEFAULT_CLUSTERING_VERSION,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Status Matrix & Status Classification Tests
# ---------------------------------------------------------------------------


def test_approved_status_pairs():
    """All 4 approved status pairs construct valid observations."""
    # 1. present, complete (with valid metrics)
    obs_present = MediaAttentionObservation(**_valid_obs_kwargs())
    assert obs_present.value_status == "present"
    assert obs_present.completeness_status == "complete"
    assert obs_present.value == 4.0

    # 2. suppressed, truncated (with None metrics)
    obs_supp = MediaAttentionObservation(
        **_valid_obs_kwargs(
            value_status=STATUS_SUPPRESSED,
            completeness_status=COMPLETENESS_TRUNCATED,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
    )
    assert obs_supp.value_status == "suppressed"
    assert obs_supp.completeness_status == "truncated"
    assert obs_supp.value is None

    # 3. missing, unavailable (with None metrics)
    obs_missing = MediaAttentionObservation(
        **_valid_obs_kwargs(
            value_status=STATUS_MISSING,
            completeness_status=COMPLETENESS_UNAVAILABLE,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
    )
    assert obs_missing.value_status == "missing"
    assert obs_missing.completeness_status == "unavailable"

    # 4. invalid, unavailable (with None metrics)
    obs_invalid = MediaAttentionObservation(
        **_valid_obs_kwargs(
            value_status=STATUS_INVALID,
            completeness_status=COMPLETENESS_UNAVAILABLE,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
    )
    assert obs_invalid.value_status == "invalid"
    assert obs_invalid.completeness_status == "unavailable"


@pytest.mark.parametrize(
    ("val_status", "comp_status"),
    [
        (STATUS_PRESENT, COMPLETENESS_TRUNCATED),
        (STATUS_PRESENT, COMPLETENESS_UNAVAILABLE),
        (STATUS_SUPPRESSED, COMPLETENESS_COMPLETE),
        (STATUS_SUPPRESSED, COMPLETENESS_UNAVAILABLE),
        (STATUS_MISSING, COMPLETENESS_COMPLETE),
        (STATUS_MISSING, COMPLETENESS_TRUNCATED),
        (STATUS_INVALID, COMPLETENESS_COMPLETE),
        (STATUS_INVALID, COMPLETENESS_TRUNCATED),
        ("unknown", COMPLETENESS_COMPLETE),
        (STATUS_PRESENT, "unknown"),
    ],
)
def test_disallowed_status_pairs_rejected(val_status, comp_status):
    """Any status pair outside the 4 approved pairs is rejected deterministically."""
    with pytest.raises(ValueError, match="Invalid status pair"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value_status=val_status,
                completeness_status=comp_status,
                value=None,
                raw_article_count=None,
                distinct_outlet_count=None,
                estimated_deduplicated_story_count=None,
            )
        )


@pytest.mark.parametrize("status", [STATUS_SUPPRESSED, STATUS_MISSING, STATUS_INVALID])
def test_non_present_status_rejects_non_null_metrics(status):
    """Suppressed, missing, and invalid statuses require all metrics to be None."""
    comp_status = COMPLETENESS_TRUNCATED if status == STATUS_SUPPRESSED else COMPLETENESS_UNAVAILABLE

    # Non-null value
    with pytest.raises(ValueError, match="Value must be None when value_status is"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value_status=status,
                completeness_status=comp_status,
                value=2.0,
                raw_article_count=None,
                distinct_outlet_count=None,
                estimated_deduplicated_story_count=None,
            )
        )

    # Non-null raw_article_count
    with pytest.raises(ValueError, match="raw_article_count must be None when value_status is"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value_status=status,
                completeness_status=comp_status,
                value=None,
                raw_article_count=5,
                distinct_outlet_count=None,
                estimated_deduplicated_story_count=None,
            )
        )

    # Non-null distinct_outlet_count
    with pytest.raises(ValueError, match="distinct_outlet_count must be None when value_status is"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value_status=status,
                completeness_status=comp_status,
                value=None,
                raw_article_count=None,
                distinct_outlet_count=3,
                estimated_deduplicated_story_count=None,
            )
        )

    # Non-null estimated_deduplicated_story_count
    with pytest.raises(ValueError, match="estimated_deduplicated_story_count must be None when value_status is"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value_status=status,
                completeness_status=comp_status,
                value=None,
                raw_article_count=None,
                distinct_outlet_count=None,
                estimated_deduplicated_story_count=2,
            )
        )


def test_present_status_rejects_none_metric():
    """Present status rejects None for any metric or count column."""
    with pytest.raises(ValueError, match="Value cannot be None when value_status is 'present'"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=None))

    with pytest.raises(ValueError, match="raw_article_count cannot be None when value_status is 'present'"):
        MediaAttentionObservation(**_valid_obs_kwargs(raw_article_count=None))

    with pytest.raises(ValueError, match="distinct_outlet_count cannot be None when value_status is 'present'"):
        MediaAttentionObservation(**_valid_obs_kwargs(distinct_outlet_count=None))

    with pytest.raises(ValueError, match="estimated_deduplicated_story_count cannot be None when value_status is 'present'"):
        MediaAttentionObservation(**_valid_obs_kwargs(estimated_deduplicated_story_count=None))


# ---------------------------------------------------------------------------
# 2. Numeric Integrity & Edge Cases
# ---------------------------------------------------------------------------


def test_nan_metric_rejected():
    """NaN value is rejected with an explicit error."""
    with pytest.raises(ValueError, match="Metric value cannot be NaN"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=float("nan")))


def test_infinity_metric_rejected():
    """Positive and negative infinity are rejected."""
    with pytest.raises(ValueError, match="Metric value cannot be infinite"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=float("inf")))

    with pytest.raises(ValueError, match="Metric value cannot be infinite"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=float("-inf")))


def test_negative_metric_rejected():
    """Negative metric value is rejected."""
    with pytest.raises(ValueError, match="Metric value cannot be negative"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=-1.0, estimated_deduplicated_story_count=-1))

    with pytest.raises(ValueError, match="Metric value cannot be negative"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=-0.01))


def test_signed_negative_zero_rejected():
    """Signed negative zero (-0.0) is rejected."""
    with pytest.raises(ValueError, match="signed negative zero"):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                value=-0.0,
                raw_article_count=0,
                distinct_outlet_count=0,
                estimated_deduplicated_story_count=0,
            )
        )


def test_boolean_values_rejected_as_numeric():
    """Boolean True/False are rejected for value and count fields."""
    with pytest.raises(TypeError, match="Value must be a float or int"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=True))

    with pytest.raises(TypeError, match="raw_article_count must be an integer"):
        MediaAttentionObservation(**_valid_obs_kwargs(raw_article_count=True))

    with pytest.raises(TypeError, match="distinct_outlet_count must be an integer"):
        MediaAttentionObservation(**_valid_obs_kwargs(distinct_outlet_count=False))

    with pytest.raises(TypeError, match="estimated_deduplicated_story_count must be an integer"):
        MediaAttentionObservation(**_valid_obs_kwargs(estimated_deduplicated_story_count=True))


@pytest.mark.parametrize(
    ("count_name", "count_val"),
    [
        ("raw_article_count", -1),
        ("distinct_outlet_count", -1),
        ("estimated_deduplicated_story_count", -1),
    ],
)
def test_negative_counts_rejected(count_name, count_val):
    """Negative counts are rejected."""
    with pytest.raises(ValueError, match=f"{count_name} cannot be negative"):
        MediaAttentionObservation(**_valid_obs_kwargs(**{count_name: count_val}))


def test_value_must_equal_float_story_count():
    """value must exactly equal float(estimated_deduplicated_story_count)."""
    with pytest.raises(ValueError, match="must exactly equal float"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=3.5, estimated_deduplicated_story_count=4))

    with pytest.raises(ValueError, match="must exactly equal float"):
        MediaAttentionObservation(**_valid_obs_kwargs(value=5.0, estimated_deduplicated_story_count=4))


# ---------------------------------------------------------------------------
# 3. Count Hierarchy Tests (Zero vs Positive Branches)
# ---------------------------------------------------------------------------


def test_zero_branch_valid():
    """Empirical zero: raw=0, outlets=0, stories=0, value=0.0 constructs cleanly."""
    obs = MediaAttentionObservation(
        **_valid_obs_kwargs(
            value=0.0,
            raw_article_count=0,
            distinct_outlet_count=0,
            estimated_deduplicated_story_count=0,
        )
    )
    assert obs.value == 0.0
    assert obs.raw_article_count == 0
    assert obs.distinct_outlet_count == 0
    assert obs.estimated_deduplicated_story_count == 0


@pytest.mark.parametrize(
    ("outlets", "stories", "val"),
    [
        (1, 0, 0.0),
        (0, 1, 1.0),
        (0, 0, 1.0),
    ],
)
def test_zero_branch_violations_rejected(outlets, stories, val):
    """When raw_article_count is 0, outlets and stories must be 0 and value must be 0.0."""
    with pytest.raises(ValueError):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                raw_article_count=0,
                distinct_outlet_count=outlets,
                estimated_deduplicated_story_count=stories,
                value=val,
            )
        )


def test_positive_branch_valid():
    """Positive branch: raw=10, outlets=6, stories=8, value=8.0 is valid."""
    obs = MediaAttentionObservation(
        **_valid_obs_kwargs(
            raw_article_count=10,
            distinct_outlet_count=6,
            estimated_deduplicated_story_count=8,
            value=8.0,
        )
    )
    assert obs.raw_article_count == 10
    assert obs.distinct_outlet_count == 6
    assert obs.estimated_deduplicated_story_count == 8
    assert obs.value == 8.0


@pytest.mark.parametrize(
    ("raw", "outlets", "stories", "val", "match_str"),
    [
        (5, 6, 4, 4.0, "distinct_outlet_count (6) cannot exceed raw_article_count (5)"),
        (5, 3, 6, 6.0, "estimated_deduplicated_story_count (6) cannot exceed raw_article_count (5)"),
        (5, 0, 4, 4.0, "distinct_outlet_count must be >= 1 when raw_article_count >= 1"),
        (5, 3, 0, 0.0, "estimated_deduplicated_story_count must be >= 1 when raw_article_count >= 1"),
    ],
)
def test_positive_branch_hierarchy_violations_rejected(raw, outlets, stories, val, match_str):
    """Hierarchical constraints in the positive branch are strictly enforced."""
    with pytest.raises(ValueError, match=re.escape(match_str)):
        MediaAttentionObservation(
            **_valid_obs_kwargs(
                raw_article_count=raw,
                distinct_outlet_count=outlets,
                estimated_deduplicated_story_count=stories,
                value=val,
            )
        )


# ---------------------------------------------------------------------------
# 4. Outlet Domain Identity & URL Normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "fallback", "expected"),
    [
        ("https://www.vogue.in/fashion/trend-2026", None, "vogue.in"),
        ("http://m.timesofindia.indiatimes.com/city/mumbai/story", None, "timesofindia.indiatimes.com"),
        ("https://amp.ndtv.com/lifestyle/trend-update", None, "ndtv.com"),
        ("https://amp-indianexpress.com/lifestyle/fashion", None, "indianexpress.com"),
        ("https://hindustantimes.com:443/lifestyle/trends", None, "hindustantimes.com"),
        ("http://hindustantimes.com:80/lifestyle", None, "hindustantimes.com"),
        ("https://sub.domain.example.co.uk/page", None, "sub.domain.example.co.uk"),
        ("/relative/path/only", "www.vogue.in", "vogue.in"),
        ("", "m.femina.in", "femina.in"),
    ],
)
def test_extract_outlet_domain_success(url, fallback, expected):
    """Outlet domain extraction strips prefixes, ports, and handles fallbacks."""
    assert extract_outlet_domain(url, fallback_domain=fallback) == expected


def test_extract_outlet_domain_unresolvable_raises():
    """Unresolvable outlet domains raise ValueError."""
    with pytest.raises(ValueError, match="Unable to extract valid outlet domain"):
        extract_outlet_domain("", fallback_domain=None)

    with pytest.raises(ValueError, match="Unable to extract valid outlet domain"):
        extract_outlet_domain("/no/host/here", fallback_domain=None)


def test_normalize_article_url():
    """Article URL normalization strips tracking query parameters and standard ports."""
    raw_url = "https://www.vogue.in:443/fashion/quiet-luxury/?utm_source=twitter&utm_medium=social&page=1#section"
    normalized = normalize_article_url(raw_url)
    assert normalized == "https://vogue.in/fashion/quiet-luxury?page=1"
    assert "utm_source" not in normalized
    assert "utm_medium" not in normalized
    assert "#section" not in normalized


# ---------------------------------------------------------------------------
# 5. Timestamp Parsing & Period Validation
# ---------------------------------------------------------------------------


def test_parse_media_timestamp():
    """Supports ISO 8601 UTC and GDELT compact formats."""
    # ISO 8601 with Z
    dt1, err1 = parse_media_timestamp("2026-01-05T12:30:00Z")
    assert err1 is None
    assert dt1 == datetime(2026, 1, 5, 12, 30, 0, tzinfo=timezone.utc)

    # ISO 8601 with offset
    dt2, err2 = parse_media_timestamp("2026-01-05T18:00:00+05:30")
    assert err2 is None
    assert dt2 == datetime(2026, 1, 5, 12, 30, 0, tzinfo=timezone.utc)

    # GDELT compact format YYYYMMDDTHHMMSSZ
    dt3, err3 = parse_media_timestamp("20260105T123000Z")
    assert err3 is None
    assert dt3 == datetime(2026, 1, 5, 12, 30, 0, tzinfo=timezone.utc)

    # GDELT compact format YYYYMMDDHHMMSS
    dt4, err4 = parse_media_timestamp("20260105123000")
    assert err4 is None
    assert dt4 == datetime(2026, 1, 5, 12, 30, 0, tzinfo=timezone.utc)

    # Timezone-aware datetime passthrough
    dt5, err5 = parse_media_timestamp(_T0)
    assert err5 is None
    assert dt5 == _T0


def test_parse_media_timestamp_invalid():
    """Naive, missing, and malformed timestamps are cleanly rejected."""
    _, err_none = parse_media_timestamp(None)
    assert err_none == "missing"

    _, err_empty = parse_media_timestamp("   ")
    assert err_empty == "missing"

    naive_dt = datetime(2026, 1, 5, 10, 0, 0)
    _, err_naive = parse_media_timestamp(naive_dt)
    assert err_naive == "naive"

    _, err_invalid = parse_media_timestamp("not-a-timestamp")
    assert err_invalid == "invalid"


def test_period_ordering_validation():
    """Observations reject period_end <= period_start and naive datetimes."""
    # period_end == period_start
    with pytest.raises(ValueError, match="period_end must be strictly after period_start"):
        MediaAttentionObservation(**_valid_obs_kwargs(period_start=_T0, period_end=_T0))

    # period_end < period_start
    with pytest.raises(ValueError, match="period_end must be strictly after period_start"):
        MediaAttentionObservation(**_valid_obs_kwargs(period_start=_T_END, period_end=_T0))

    # Naive start
    naive_t = datetime(2026, 1, 5, 10, 0, 0)
    with pytest.raises(ValueError, match="period_start must be timezone-aware UTC datetime"):
        MediaAttentionObservation(**_valid_obs_kwargs(period_start=naive_t))


# ---------------------------------------------------------------------------
# 6. Headline Canonicalization & Wire Suffix Stripping
# ---------------------------------------------------------------------------


def test_canonicalize_headline_tokens():
    """HTML entities unescaped, wire suffixes stripped, stop words removed."""
    # Wire suffix stripping
    title1 = "India Fashion Week 2026: The Rise of Quiet Luxury - Times of India"
    tokens1 = canonicalize_headline_tokens(title1)
    assert "india" in tokens1
    assert "fashion" in tokens1
    assert "week" in tokens1
    assert "2026" in tokens1
    assert "rise" in tokens1
    assert "quiet" in tokens1
    assert "luxury" in tokens1
    # Wire suffix 'times of india' was stripped
    assert "times" not in tokens1

    # News agency wire suffix
    title2 = "Streetwear aesthetic surges in Mumbai &amp; Delhi | Reuters"
    tokens2 = canonicalize_headline_tokens(title2)
    assert "streetwear" in tokens2
    assert "aesthetic" in tokens2
    assert "surges" in tokens2
    assert "mumbai" in tokens2
    assert "delhi" in tokens2
    assert "reuters" not in tokens2
    assert "amp" not in tokens2  # &amp; was unescaped to & then stripped

    # PTI wire suffix
    title3 = "Sustainability in Indian textiles - PTI"
    tokens3 = canonicalize_headline_tokens(title3)
    assert "sustainability" in tokens3
    assert "indian" in tokens3
    assert "textiles" in tokens3
    assert "pti" not in tokens3


# ---------------------------------------------------------------------------
# 7. 48-Hour Inception-Anchored Clustering & Deduplication
# ---------------------------------------------------------------------------


def test_dedup_repeated_publisher_coverage():
    """Times of India publishes morning and evening articles on same story -> 1 cluster, 1 outlet."""
    art1 = MediaArticle(
        url="https://timesofindia.indiatimes.com/fashion/quiet-luxury-morning",
        normalized_url="https://timesofindia.indiatimes.com/fashion/quiet-luxury-morning",
        outlet_domain="timesofindia.indiatimes.com",
        title="Quiet Luxury Dominates India Fashion Week 2026",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week", "2026"}),
        published_at=_T0,
    )
    art2 = MediaArticle(
        url="https://timesofindia.indiatimes.com/fashion/quiet-luxury-evening-summary",
        normalized_url="https://timesofindia.indiatimes.com/fashion/quiet-luxury-evening-summary",
        outlet_domain="timesofindia.indiatimes.com",
        title="Quiet Luxury Dominates India Fashion Week 2026 - Times of India",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week", "2026"}),
        published_at=_T0 + timedelta(hours=6),
    )

    clusters, assignments = cluster_stories([art1, art2])
    assert len(clusters) == 1
    assert clusters[0].domains == frozenset({"timesofindia.indiatimes.com"})
    assert len(clusters[0].articles) == 2


def test_dedup_48h_boundary_just_within():
    """Story B published at t0 + 47h 59m merges into 1 cluster."""
    art1 = MediaArticle(
        url="https://vogue.in/story-a",
        normalized_url="https://vogue.in/story-a",
        outlet_domain="vogue.in",
        title="Quiet Luxury Dominates India Fashion Week",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week"}),
        published_at=_T0,
    )
    art2 = MediaArticle(
        url="https://hindustantimes.com/story-b",
        normalized_url="https://hindustantimes.com/story-b",
        outlet_domain="hindustantimes.com",
        title="Quiet Luxury Dominates India Fashion Week Recap",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week", "recap"}),
        published_at=_T0 + timedelta(hours=47, minutes=59),
    )

    clusters, _ = cluster_stories([art1, art2])
    assert len(clusters) == 1
    assert clusters[0].domains == frozenset({"vogue.in", "hindustantimes.com"})


def test_dedup_48h_boundary_just_outside():
    """Story B published at t0 + 48h 01m exceeds the window -> splits into 2 clusters."""
    art1 = MediaArticle(
        url="https://vogue.in/story-a",
        normalized_url="https://vogue.in/story-a",
        outlet_domain="vogue.in",
        title="Quiet Luxury Dominates India Fashion Week",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week"}),
        published_at=_T0,
    )
    art2 = MediaArticle(
        url="https://hindustantimes.com/story-b",
        normalized_url="https://hindustantimes.com/story-b",
        outlet_domain="hindustantimes.com",
        title="Quiet Luxury Dominates India Fashion Week",
        canonical_tokens=frozenset({"quiet", "luxury", "dominates", "india", "fashion", "week"}),
        published_at=_T0 + timedelta(hours=48, minutes=1),
    )

    clusters, _ = cluster_stories([art1, art2])
    assert len(clusters) == 2


def test_dedup_chaining_prevention():
    """Story A at t0, Story B at t0 + 40h, Story C at t0 + 60h.

    Story C is similar to B, but exceeds 48h from cluster inception (t0).
    Chaining is prevented: cluster splits into 2.
    """
    art_a = MediaArticle(
        url="https://vogue.in/story-a",
        normalized_url="https://vogue.in/story-a",
        outlet_domain="vogue.in",
        title="Quiet Luxury Fashion Trend",
        canonical_tokens=frozenset({"quiet", "luxury", "fashion", "trend"}),
        published_at=_T0,
    )
    art_b = MediaArticle(
        url="https://hindustantimes.com/story-b",
        normalized_url="https://hindustantimes.com/story-b",
        outlet_domain="hindustantimes.com",
        title="Quiet Luxury Fashion Trend In India",
        canonical_tokens=frozenset({"quiet", "luxury", "fashion", "trend", "india"}),
        published_at=_T0 + timedelta(hours=40),
    )
    art_c = MediaArticle(
        url="https://ndtv.com/story-c",
        normalized_url="https://ndtv.com/story-c",
        outlet_domain="ndtv.com",
        title="Quiet Luxury Fashion Trend In India",
        canonical_tokens=frozenset({"quiet", "luxury", "fashion", "trend", "india"}),
        published_at=_T0 + timedelta(hours=60),
    )

    clusters, _ = cluster_stories([art_a, art_b, art_c])
    assert len(clusters) == 2
    # Cluster 1 contains A and B (B merged at +40h <= 48h with Jaccard 4/5 = 0.80)
    assert set(clusters[0].articles) == {art_a, art_b}
    # Cluster 2 contains C (+60h > 48h from anchor t0, inception anchor prevents chaining)
    assert clusters[1].articles == (art_c,)


def test_jaccard_similarity_calculation():
    """Jaccard similarity meets mathematical definition."""
    set_a = frozenset({"quiet", "luxury", "fashion"})
    set_b = frozenset({"quiet", "luxury", "streetwear"})

    # Intersection: {"quiet", "luxury"} (2), Union: {"quiet", "luxury", "fashion", "streetwear"} (4) -> 0.5
    assert jaccard_similarity(set_a, set_b) == 0.5

    # Identical
    assert jaccard_similarity(set_a, set_a) == 1.0

    # Disjoint
    assert jaccard_similarity(set_a, frozenset({"vintage", "y2k"})) == 0.0

    # Both empty
    assert jaccard_similarity(frozenset(), frozenset()) == 1.0


# ---------------------------------------------------------------------------
# 8. normalize_media_attention High-Level Pipeline Tests
# ---------------------------------------------------------------------------


def test_normalize_media_attention_empirical_zero():
    """Empty article records produce valid empirical zero observation."""
    result = normalize_media_attention(
        records=[],
        period_start=_T0,
        period_end=_T_END,
        query_key="quiet_luxury",
        query_display="Quiet Luxury",
    )
    assert result.ok
    obs = result.observation
    assert obs is not None
    assert obs.value_status == "present"
    assert obs.completeness_status == "complete"
    assert obs.value == 0.0
    assert obs.raw_article_count == 0
    assert obs.distinct_outlet_count == 0
    assert obs.estimated_deduplicated_story_count == 0


def test_normalize_media_attention_with_raw_records():
    """Normalizes raw dictionary records into clusters and observation."""
    records = [
        {
            "url": "https://www.vogue.in/fashion/quiet-luxury-1",
            "title": "Quiet Luxury Trend Surges Across India - Vogue India",
            "seendate": "20260105T120000Z",
            "domain": "vogue.in",
        },
        {
            "url": "https://m.timesofindia.indiatimes.com/lifestyle/quiet-luxury-2",
            "title": "Quiet Luxury Trend Surges Across India - Times of India",
            "seendate": "20260105T150000Z",
            "domain": "timesofindia.indiatimes.com",
        },
        {
            "url": "https://ndtv.com/lifestyle/streetwear-boom",
            "title": "Streetwear Aesthetic Boom In Urban Centers",
            "seendate": "20260106T100000Z",
            "domain": "ndtv.com",
        },
    ]

    result = normalize_media_attention(
        records=records,
        period_start=_T0,
        period_end=_T_END,
        query_key="quiet_luxury",
    )
    assert result.ok
    obs = result.observation
    assert obs is not None
    assert obs.raw_article_count == 3
    assert obs.distinct_outlet_count == 3  # vogue.in, timesofindia.indiatimes.com, ndtv.com
    assert obs.estimated_deduplicated_story_count == 2  # 1 quiet luxury cluster, 1 streetwear cluster
    assert obs.value == 2.0


def test_normalize_media_attention_exact_url_deduplication():
    """Duplicate URLs in raw records are deduplicated before clustering."""
    records = [
        {
            "url": "https://vogue.in/fashion/quiet-luxury?utm_source=twitter",
            "title": "Quiet Luxury Trend Surges",
            "seendate": "20260105T120000Z",
        },
        {
            "url": "https://vogue.in/fashion/quiet-luxury?utm_source=facebook",
            "title": "Quiet Luxury Trend Surges",
            "seendate": "20260105T120000Z",
        },
    ]

    result = normalize_media_attention(
        records=records,
        period_start=_T0,
        period_end=_T_END,
        query_key="quiet_luxury",
    )
    assert result.ok
    obs = result.observation
    assert obs is not None
    # 2 duplicate URLs merged into 1 raw article
    assert obs.raw_article_count == 1
    assert obs.distinct_outlet_count == 1
    assert obs.estimated_deduplicated_story_count == 1
    assert obs.value == 1.0


def test_normalize_media_attention_suppressed_window():
    """Suppressed status produces truncated observation with None metrics."""
    result = normalize_media_attention(
        records=[],
        period_start=_T0,
        period_end=_T_END,
        query_key="quiet_luxury",
        value_status=STATUS_SUPPRESSED,
        completeness_status=COMPLETENESS_TRUNCATED,
    )
    assert result.ok
    obs = result.observation
    assert obs is not None
    assert obs.value_status == "suppressed"
    assert obs.completeness_status == "truncated"
    assert obs.value is None
    assert obs.raw_article_count is None


# ---------------------------------------------------------------------------
# 9. Query Configuration and Clustering Version Immutability
# ---------------------------------------------------------------------------


def test_version_string_bounds_enforced():
    """Versions must be non-empty and bounded to 60 characters."""
    # Empty string
    with pytest.raises(ValueError, match="query_config_version length"):
        MediaAttentionObservation(**_valid_obs_kwargs(query_config_version=""))

    with pytest.raises(ValueError, match="clustering_version length"):
        MediaAttentionObservation(**_valid_obs_kwargs(clustering_version=""))

    # Too long (> 60 chars)
    with pytest.raises(ValueError, match="query_config_version length"):
        MediaAttentionObservation(**_valid_obs_kwargs(query_config_version="x" * 61))

    with pytest.raises(ValueError, match="clustering_version length"):
        MediaAttentionObservation(**_valid_obs_kwargs(clustering_version="y" * 61))


# ---------------------------------------------------------------------------
# 10. Frozen Boundary Invariants
# ---------------------------------------------------------------------------


def test_demand_signal_remains_false():
    """Strict adherence to frozen boundary: DEMAND_SIGNAL_AVAILABLE is False."""
    assert DEMAND_SIGNAL_AVAILABLE is False


def test_media_attention_signal_kind_identity():
    """Media attention signal kind is 'media_attention' and never mixed with demand or catalog."""
    assert SIGNAL_KIND == METRIC_MEDIA_ATTENTION
    assert METRIC_MEDIA_ATTENTION == "media_attention"
