"""M14 Trending contract tests (DB-free, deterministic test adapter).

Covers: normalization equivalents/distinct, scoring (fresh/stale/
single/multi/missing), provenance, product dedup without name-merging,
single-provider failure isolation, API shape/auth/404. No DB, no keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.trending.domain import (
    ProductCandidate,
    TrendSignal,
    build_trends,
    matched_products,
    normalize_term,
    score_trend,
)

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}
NOW = datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)


def _signal(term, source="youtube_in", growth=0.5, at=None, volume=10.0):
    return TrendSignal(
        source=source,
        source_identifier=f"{source}-1",
        observed_term=term,
        category="outerwear",
        region="IN",
        observed_at=at or NOW,
        growth=growth,
        volume=volume,
    )


def _product(name, source="test_commerce", pid="TEST-001"):
    return ProductCandidate(
        source=source,
        source_product_id=pid,
        name=name,
        brand="Test Brand",
        category="outerwear",
        price=1299.0,
        currency="INR",
        image_url=None,
        availability=True,
        product_url=None,
        affiliate_url=None,
        attributes={},
        provenance={"source": source},
        observed_at=NOW,
    )


def test_normalize_equivalent_terms():
    assert normalize_term("oversized denim jacket") == normalize_term("baggy denim jacket")
    assert normalize_term("oversized denim jacket") == normalize_term("loose denim outerwear")
    assert normalize_term("oversized denim jacket") == normalize_term("oversized jean jacket")


def test_normalize_distinct_terms():
    assert normalize_term("oversized denim jacket") != normalize_term("wide leg cargo pants")
    assert normalize_term("cobalt blue") != normalize_term("mocha brown")


def test_scoring_fresh_beats_stale():
    fresh = [_signal("oversized denim jacket", at=NOW), _signal("baggy denim jacket", source="google_trends_in", at=NOW)]
    stale_at = NOW - timedelta(hours=72)
    stale = [_signal("oversized denim jacket", at=stale_at), _signal("baggy denim jacket", source="google_trends_in", at=stale_at)]
    assert score_trend(fresh, NOW)[1] > score_trend(stale, NOW)[1]


def test_scoring_multi_source_beats_single():
    single = [_signal("oversized denim jacket"), _signal("oversized denim jacket")]
    multi = [_signal("oversized denim jacket"), _signal("baggy denim jacket", source="google_trends_in")]
    assert score_trend(multi, NOW)[1] > score_trend(single, NOW)[1]


def test_scoring_missing_metrics_not_fabricated():
    signals = [
        TrendSignal("youtube_in", "y1", "oversized denim jacket", "outerwear", "IN", NOW),
        TrendSignal("google_trends_in", "g1", "baggy denim jacket", "outerwear", "IN", NOW),
    ]
    velocity, _ = score_trend(signals, NOW)
    assert velocity == 0.0


def test_provenance_preserved():
    trends = build_trends(
        [_signal("oversized denim jacket"), _signal("baggy denim jacket", source="google_trends_in")],
        [_product("oversized denim jacket")],
        NOW,
        min_score=0.0,
    )
    assert len(trends) == 1
    sources = {p["source"] for p in trends[0].provenance}
    assert sources == {"youtube_in", "google_trends_in"}
    assert all("observed_at" in p and "source_identifier" in p for p in trends[0].provenance)


def test_products_dedup_without_name_merge():
    products = [
        _product("oversized denim jacket", pid="TEST-001"),
        _product("oversized denim jacket", pid="TEST-001"),  # exact duplicate
        _product("oversized denim jacket", source="other_shop", pid="TEST-001"),  # same id, other source
    ]
    trends = build_trends(
        [_signal("oversized denim jacket"), _signal("baggy denim jacket", source="google_trends_in")],
        products,
        NOW,
        min_score=0.0,
    )
    matched = matched_products(products, trends[0].trend_id)
    keys = {(p.source, p.source_product_id) for p in matched}
    assert len(keys) == 2  # cross-source rows never merged on similar names


def test_single_source_never_ranks():
    trends = build_trends([_signal("oversized denim jacket")], [], NOW, min_score=0.0)
    assert trends == []


def test_api_requires_auth():
    assert client.get("/v1/trending").status_code == 401


def test_api_feed_shape_and_no_fabrication():
    response = client.get("/v1/trending", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["region"] == "IN"
    assert body["isStale"] is False
    assert len(body["items"]) >= 1
    item = body["items"][0]
    assert item["trendId"].startswith("trend-")
    assert item["confidence"] >= 0.55
    assert len(item["provenance"]) >= 2
    assert len(item["matchedProducts"]) >= 1
    product = item["matchedProducts"][0]
    assert product["priceInr"] == 1299.0
    assert product["imageUrl"] is None  # unprovided stays null, never faked
    assert product["productUrl"] is None


def test_api_detail_and_404():
    feed = client.get("/v1/trending", headers=HEADERS).json()
    trend_id = feed["items"][0]["trendId"]
    detail = client.get(f"/v1/trending/{trend_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["trendId"] == trend_id
    assert client.get("/v1/trending/trend-nope", headers=HEADERS).status_code == 404
