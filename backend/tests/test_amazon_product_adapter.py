"""Tests for Amazon India Product Ingestion Adapter (DISCOVERY-10B-4).

Validates:
1. Safety boundary: unconfigured credentials cleanly fail closed with SourceAuthError.
2. Error translation: 401/403 -> SourceAuthError, 429 -> SourceRateLimitError, 5xx -> SourceTransientError.
3. Payload validation: malformed JSON translates to SourcePayloadError.
4. Response parsing: authentic Amazon PA-API 5.0 and Rainforest API schemas map to RawSourceRecord.
5. Normalization boundary: raw records normalize cleanly without errors.
6. DB persistence: CollectSource inserts raw records, canonical product, retailer, variant, and retailer_offers.
7. Idempotency: re-ingesting identical payload is skipped without duplicating rows.
8. Price history: price change updates retailer_offers and appends to offer_price_history.
9. Cross-retailer isolation: second retailer does not overwrite Amazon offer.
10. Synthetic fixture isolation: fixtures stay isolated with zero retailer offers.
11. Offer API & redirect flow: GET /products/{id}/offers returns offer, redirect validates domain and records offer_click.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import (
    get_candidate_repository,
    get_discovery_event_repository,
    get_optional_user_id,
)
from app.application.collection import CollectSource, CollectionConfig
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAuthError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.normalization import normalize_product
from app.infrastructure.db.models import (
    DiscoveryEvent,
    OfferPriceHistory,
    Product,
    ProductSourceMap,
    ProductVariant,
    RawSourceRecord as RawSourceRecordModel,
    Retailer,
    RetailerOffer,
)
from app.infrastructure.db.repositories import (
    DiscoveryEventRepositorySQL,
    DiscoveryRepositorySQL,
)
from app.infrastructure.external.amazon_source import (
    AmazonProductAdapter,
    SOURCE_AMAZON_IN,
    _append_affiliate_tag,
)
from app.infrastructure.external.fashion_catalog_seed import compute_test_gtin14
from app.main import app

pytestmark = pytest.mark.usefixtures("db")


def _sample_paapi_item(asin: str = "B09L7X9M12", price: float = 1999.0) -> dict:
    """Authentic Amazon PA-API 5.0 item payload."""
    return {
        "ASIN": asin,
        "DetailPageURL": f"https://www.amazon.in/dp/{asin}?tag=fansivibe-21",
        "ItemInfo": {
            "Title": {"DisplayValue": "Men's Relaxed Fit Cotton Shirt"},
            "ByLineInfo": {"Brand": {"DisplayValue": "Studio Atelier"}},
            "Classifications": {
                "Binding": {"DisplayValue": "Apparel"},
                "ProductGroup": {"DisplayValue": "Apparel"},
            },
            "Features": {
                "DisplayValues": ["100% Breathable Cotton", "Spread Collar"]
            },
            "ManufactureInfo": {
                "ItemPartNumber": {"DisplayValue": "ATELIER-SHIRT-M"}
            },
        },
        "Images": {
            "Primary": {
                "Large": {
                    "URL": "https://m.media-amazon.com/images/I/71example.jpg"
                }
            }
        },
        "Offers": {
            "Listings": [
                {
                    "Price": {
                        "Amount": price,
                        "Currency": "INR",
                        "DisplayAmount": f"₹{price:,.2f}",
                    },
                    "SavingBasis": {
                        "Amount": price + 500.0,
                        "Currency": "INR",
                    },
                    "Availability": {
                        "Message": "In Stock.",
                        "Type": "NOW",
                    },
                }
            ]
        },
    }


def _sample_rainforest_item(asin: str = "B09L7X9M12", price: float = 1999.0) -> dict:
    """Authentic Rainforest API Amazon.in item payload."""
    return {
        "asin": asin,
        "title": "Men's Relaxed Fit Cotton Shirt",
        "link": f"https://www.amazon.in/dp/{asin}",
        "brand": "Studio Atelier",
        "image": "https://m.media-amazon.com/images/I/71example.jpg",
        "price": {
            "value": price,
            "currency": "INR",
            "raw": f"₹{price:,.0f}",
        },
        "availability": {
            "raw": "In stock",
        },
        "variants": [
            {"size": "L", "color": "Navy"}
        ],
    }


def _make_mock_client(
    status_code: int = 200,
    json_data: Optional[dict] = None,
    headers: Optional[dict[str, str]] = None,
) -> httpx.Client:
    body = json.dumps(json_data or {}).encode("utf-8")
    resp_headers = headers or {}
    resp = httpx.Response(
        status_code=status_code,
        content=body,
        headers=resp_headers,
        request=httpx.Request("POST", "https://webservices.amazon.in/paapi5/searchitems"),
    )
    return httpx.Client(transport=httpx.MockTransport(lambda req: resp))


# 1. Safety boundary: unconfigured credentials
def test_unconfigured_credentials_fails_closed():
    adapter = AmazonProductAdapter(
        associate_tag=None,
        access_key=None,
        secret_key=None,
        rainforest_api_key=None,
        records=None,
    )
    with pytest.raises(SourceAuthError) as exc_info:
        adapter.fetch_batch()
    assert "credentials are not configured" in str(exc_info.value)


# 2. HTTP error translation
def test_http_auth_error_translation():
    client = _make_mock_client(status_code=403)
    adapter = AmazonProductAdapter(
        http_client=client,
        access_key="dummy_key",
        secret_key="dummy_secret",
        associate_tag="dummy-21",
        pace_interval_s=0.0,
    )
    with pytest.raises(SourceAuthError):
        adapter.fetch_batch()


def test_http_rate_limit_translation():
    client = _make_mock_client(status_code=429, headers={"Retry-After": "4.5"})
    adapter = AmazonProductAdapter(
        http_client=client,
        access_key="dummy_key",
        secret_key="dummy_secret",
        associate_tag="dummy-21",
        pace_interval_s=0.0,
    )
    with pytest.raises(SourceRateLimitError) as exc_info:
        adapter.fetch_batch()
    assert exc_info.value.retry_after_s == 4.5


def test_http_transient_error_translation():
    client = _make_mock_client(status_code=503)
    adapter = AmazonProductAdapter(
        http_client=client,
        access_key="dummy_key",
        secret_key="dummy_secret",
        associate_tag="dummy-21",
        pace_interval_s=0.0,
        max_retries=1,
        backoff_base_s=0.01,
    )
    with pytest.raises(SourceTransientError):
        adapter.fetch_batch()


def test_payload_error_translation():
    resp = httpx.Response(
        status_code=200,
        content=b"not json",
        request=httpx.Request("POST", "https://webservices.amazon.in/paapi5/searchitems"),
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda req: resp))
    adapter = AmazonProductAdapter(
        http_client=client,
        access_key="dummy_key",
        secret_key="dummy_secret",
        associate_tag="dummy-21",
        pace_interval_s=0.0,
    )
    with pytest.raises(SourcePayloadError):
        adapter.fetch_batch()


# 3. Response parsing into RawSourceRecord and normalization
def test_paapi_real_response_parsing():
    raw_item = _sample_paapi_item()
    client = _make_mock_client(
        status_code=200,
        json_data={"SearchResult": {"Items": [raw_item], "TotalResultCount": 1}},
    )
    adapter = AmazonProductAdapter(
        http_client=client,
        access_key="dummy_key",
        secret_key="dummy_secret",
        associate_tag="fansivibe-21",
        pace_interval_s=0.0,
    )
    batch = adapter.fetch_batch()
    assert batch.source == SOURCE_AMAZON_IN
    assert len(batch.records) == 1
    raw = batch.records[0]
    assert raw.source_record_id == "B09L7X9M12"
    assert raw.payload["price"] == 1999.0
    assert raw.payload["currency"] == "INR"
    assert raw.payload["availability"] is True
    assert raw.payload["attributes"]["fixture"] is False
    assert "fansivibe-21" in raw.payload["product_url"]

    norm = normalize_product(raw)
    assert norm.ok is True
    assert norm.product is not None
    assert norm.product.title == "Men's Relaxed Fit Cotton Shirt"
    assert norm.product.price == 1999.0


def test_rainforest_real_response_parsing():
    raw_item = _sample_rainforest_item()
    client = _make_mock_client(
        status_code=200,
        json_data={"search_results": [raw_item], "pagination": {"total_pages": 1}},
    )
    adapter = AmazonProductAdapter(
        http_client=client,
        rainforest_api_key="rf_dummy_key",
        associate_tag="fansivibe-21",
        pace_interval_s=0.0,
    )
    batch = adapter.fetch_batch()
    assert batch.source == SOURCE_AMAZON_IN
    assert len(batch.records) == 1
    raw = batch.records[0]
    assert raw.payload["attributes"]["size"] == "L"
    assert raw.payload["attributes"]["color"] == "Navy"

    norm = normalize_product(raw)
    assert norm.ok is True
    assert norm.product is not None


# 4. DB Persistence with CollectSource
def test_end_to_end_collection_and_retailer_offer_persistence(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)

        raw_item = _sample_paapi_item(asin="B09AMZ001", price=1999.0)
        raw_record = AmazonProductAdapter(
            associate_tag="fansivibe-21",
            records=None,
        )._parse_paapi_item(raw_item)
        assert raw_record is not None

        adapter = AmazonProductAdapter(records=[raw_record])
        collector = CollectSource(adapter=adapter, repository=repo)

        result = collector(CollectionConfig(source=SOURCE_AMAZON_IN, max_records=10))
        assert result.status == "completed"
        assert result.fetched == 1
        assert result.inserted == 1
        assert result.skipped == 0
        assert result.failed == 0

        # Verify RawSourceRecord
        raw_db = session.execute(
            select(RawSourceRecordModel).where(RawSourceRecordModel.source_record_id == "B09AMZ001")
        ).scalar_one()
        assert raw_db.source == SOURCE_AMAZON_IN

        # Verify Product
        product = session.execute(
            select(Product).where(Product.title == "Men's Relaxed Fit Cotton Shirt")
        ).scalar_one()
        assert product.price == 1999.0
        assert product.currency == "INR"
        assert product.availability is True
        assert product.attributes.get("fixture") is False

        # Verify Retailer
        retailer = session.execute(
            select(Retailer).where(Retailer.slug == SOURCE_AMAZON_IN)
        ).scalar_one()
        assert retailer.name == "Amazon India"
        assert retailer.domain == "amazon.in"

        # Verify RetailerOffer
        offer = session.execute(
            select(RetailerOffer).where(
                RetailerOffer.product_id == product.id,
                RetailerOffer.retailer_id == retailer.id,
            )
        ).scalar_one()
        assert offer.source_product_id == "B09AMZ001"
        assert float(offer.price) == 1999.0
        assert offer.currency == "INR"
        assert offer.availability is True
        assert offer.in_stock is True
        assert "fansivibe-21" in offer.product_url

        # Verify OfferPriceHistory
        history = session.execute(
            select(OfferPriceHistory).where(OfferPriceHistory.offer_id == offer.id)
        ).scalars().all()
        assert len(history) == 1
        assert float(history[0].price) == 1999.0


# 5. Idempotency on repeated collection
def test_idempotent_ingestion_no_duplicates(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)

        raw_item = _sample_paapi_item(asin="B09AMZ002", price=2499.0)
        raw_record = AmazonProductAdapter(
            associate_tag="fansivibe-21",
            records=None,
        )._parse_paapi_item(raw_item)

        adapter = AmazonProductAdapter(records=[raw_record])
        collector = CollectSource(adapter=adapter, repository=repo)

        # First run
        res1 = collector(CollectionConfig(source=SOURCE_AMAZON_IN, max_records=10))
        assert res1.inserted == 1

        # Second run with exact identical payload
        res2 = collector(CollectionConfig(source=SOURCE_AMAZON_IN, max_records=10))
        assert res2.status == "completed"
        assert res2.skipped == 1
        assert res2.inserted == 0
        assert res2.updated == 0

        # Ensure zero duplicate offers
        offers = session.execute(
            select(RetailerOffer).where(RetailerOffer.source_product_id == "B09AMZ002")
        ).scalars().all()
        assert len(offers) == 1


# 6. Price change updates offer and writes price history
def test_price_change_updates_offer_and_records_history(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)

        raw1 = AmazonProductAdapter(
            associate_tag="fansivibe-21",
            records=None,
        )._parse_paapi_item(_sample_paapi_item(asin="B09AMZ003", price=2999.0))
        raw2 = AmazonProductAdapter(
            associate_tag="fansivibe-21",
            records=None,
        )._parse_paapi_item(_sample_paapi_item(asin="B09AMZ003", price=2499.0))

        collector1 = CollectSource(
            adapter=AmazonProductAdapter(records=[raw1]),
            repository=repo,
        )
        res1 = collector1(CollectionConfig(source=SOURCE_AMAZON_IN, max_records=10))
        assert res1.inserted == 1

        collector2 = CollectSource(
            adapter=AmazonProductAdapter(records=[raw2]),
            repository=repo,
        )
        res2 = collector2(CollectionConfig(source=SOURCE_AMAZON_IN, max_records=10))
        assert res2.updated == 1

        # Verify single offer updated
        offers = session.execute(
            select(RetailerOffer).where(RetailerOffer.source_product_id == "B09AMZ003")
        ).scalars().all()
        assert len(offers) == 1
        assert float(offers[0].price) == 2499.0

        # Verify price history has 2 records
        history = session.execute(
            select(OfferPriceHistory)
            .where(OfferPriceHistory.offer_id == offers[0].id)
            .order_by(OfferPriceHistory.observed_at.asc())
        ).scalars().all()
        assert len(history) == 2
        assert float(history[0].price) == 2999.0
        assert float(history[1].price) == 2499.0


# 7. Cross-retailer isolation with GTIN match
def test_cross_retailer_offer_isolation(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        gtin14 = compute_test_gtin14(88)

        # Ingest Amazon product with GTIN
        raw_amz = RawSourceRecord(
            source=SOURCE_AMAZON_IN,
            source_record_id="B09AMZ088",
            payload={
                "source_product_id": "B09AMZ088",
                "title": "Dual Retailer Linen Shirt",
                "brand": "Heritage Atelier",
                "category": "tops",
                "price": 1899.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://www.amazon.in/dp/B09AMZ088",
                "gtin": gtin14,
                "attributes": {"fixture": False},
            },
        )
        collector_amz = CollectSource(
            adapter=AmazonProductAdapter(records=[raw_amz]),
            repository=repo,
        )
        res_amz = collector_amz(CollectionConfig(source=SOURCE_AMAZON_IN))
        assert res_amz.inserted == 1

        # Ingest Myntra product matching exact GTIN at different price
        raw_myn = RawSourceRecord(
            source="myntra",
            source_record_id="MYN-9988",
            payload={
                "source_product_id": "MYN-9988",
                "title": "Dual Retailer Linen Shirt",
                "brand": "Heritage Atelier",
                "category": "tops",
                "price": 2199.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://www.myntra.com/p/9988",
                "gtin": gtin14,
                "attributes": {"fixture": False},
            },
        )
        # Use repo directly to ingest myntra listing with proper collection run
        run_myn = repo.start_run(source="myntra")
        raw_myn_id, _ = repo.insert_raw_if_absent(
            run_id=run_myn,
            source="myntra",
            source_record_id="MYN-9988",
            payload=raw_myn.payload,
            payload_hash="myntra_hash_123",
            source_timestamp=datetime.now(timezone.utc),
        )
        norm_myn = normalize_product(raw_myn)
        decision = repo.upsert_product(
            product=norm_myn.product,
            run_id=run_myn,
            source="myntra",
            source_product_id="MYN-9988",
            raw_id=raw_myn_id,
            payload_hash="myntra_hash_123",
        )
        assert decision.creates_new_product is False

        # Check both retailer offers exist independently under the same product
        offers = session.execute(
            select(RetailerOffer).where(RetailerOffer.product_id == decision.product_id)
        ).scalars().all()
        assert len(offers) == 2
        retailer_ids = {o.retailer_id for o in offers}
        assert len(retailer_ids) == 2
        prices = {float(o.price) for o in offers}
        assert prices == {1899.0, 2199.0}


# 8. Synthetic fixture isolation
def test_synthetic_fixture_isolation(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)

        # Ingest a synthetic fixture record under a real collection run
        run_fix = repo.start_run(source="fashion_seed")
        raw_fix = RawSourceRecord(
            source="fashion_seed",
            source_record_id="SEED-01",
            payload={
                "source_product_id": "SEED-01",
                "title": "Synthetic Linen Trench",
                "brand": "Studio Atelier",
                "category": "outerwear",
                "price": 4999.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://fansivibe.test/products/seed-01",
                "attributes": {"fixture": True},
            },
        )
        raw_fix_id, _ = repo.insert_raw_if_absent(
            run_id=run_fix,
            source="fashion_seed",
            source_record_id="SEED-01",
            payload=raw_fix.payload,
            payload_hash="seed_hash_01",
            source_timestamp=datetime.now(timezone.utc),
        )
        norm_fix = normalize_product(raw_fix)
        dec_fix = repo.upsert_product(
            product=norm_fix.product,
            run_id=run_fix,
            source="fashion_seed",
            source_product_id="SEED-01",
            raw_id=raw_fix_id,
            payload_hash="seed_hash_01",
        )
        assert dec_fix.creates_new_product is True

        # Confirm fixture product has ZERO retailer offers
        fixture_offers = session.execute(
            select(RetailerOffer).where(RetailerOffer.product_id == dec_fix.product_id)
        ).scalars().all()
        assert len(fixture_offers) == 0


# 9. Offer API and Outbound Redirect Flow
def test_offer_api_and_redirect_flow(db):
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        event_repo = DiscoveryEventRepositorySQL(session)

        # Ingest genuine Amazon item
        raw_item = _sample_paapi_item(asin="B09AMZREDIRECT", price=1799.0)
        raw = AmazonProductAdapter(
            associate_tag="fansivibe-21",
            records=None,
        )._parse_paapi_item(raw_item)
        adapter = AmazonProductAdapter(records=[raw])
        collector = CollectSource(adapter=adapter, repository=repo)
        res = collector(CollectionConfig(source=SOURCE_AMAZON_IN))
        assert res.inserted == 1

        product = session.execute(
            select(Product).where(Product.title == "Men's Relaxed Fit Cotton Shirt")
        ).scalar_one()

        offer = session.execute(
            select(RetailerOffer).where(RetailerOffer.product_id == product.id)
        ).scalar_one()

        # Verify GET /v1/discovery/products/{product_id}/offers
        app.dependency_overrides[get_candidate_repository] = lambda: repo
        app.dependency_overrides[get_discovery_event_repository] = lambda: event_repo
        app.dependency_overrides[get_optional_user_id] = lambda: None

        client = TestClient(app)
        offers_resp = client.get(f"/v1/discovery/products/{product.id}/offers")
        assert offers_resp.status_code == 200
        offers_data = offers_resp.json()
        assert offers_data["isSyntheticFixture"] is False
        assert len(offers_data["offers"]) == 1
        off0 = offers_data["offers"][0]
        assert off0["retailer"]["name"] == "Amazon India"
        assert off0["retailer"]["slug"] == SOURCE_AMAZON_IN
        assert off0["price"] == 1799.0
        assert off0["isPriceFresh"] is True
        assert off0["freshnessStatus"] == "fresh"

        # Verify GET /v1/discovery/offers/{offer_id}/redirect
        redirect_resp = client.get(
            f"/v1/discovery/offers/{offer.id}/redirect?guestSessionId=00000000-0000-4000-8000-000000000001&surface=product_offer_sheet",
            follow_redirects=False,
        )
        assert redirect_resp.status_code == 307
        dest = redirect_resp.headers["location"]
        assert "amazon.in" in dest
        assert "fansivibe-21" in dest

        # Verify offer_click event recorded
        events = session.execute(
            select(DiscoveryEvent).where(DiscoveryEvent.event_type == "offer_click")
        ).scalars().all()
        assert len(events) == 1
        ev = events[0]
        assert ev.surface == "product_offer_sheet"
        assert ev.metadata_["retailer"] == "Amazon India"
        assert ev.metadata_["retailerSlug"] == SOURCE_AMAZON_IN
        assert ev.metadata_["offerId"] == str(offer.id)

        app.dependency_overrides.clear()
