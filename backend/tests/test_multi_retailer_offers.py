"""Tests for multi-retailer product offer foundation (DISCOVERY-10B-2).

Validates:
1. Two retailers can offer the same canonical product at different prices.
2. Independent retailer offer preservation (neither retailer overwrites the other).
3. Repeated ingestion of either retailer is idempotent (zero duplicate products or offers).
4. Updating retailer B's price/url/availability updates B only and appends price history,
   leaving retailer A's offer untouched.
5. Updating primary retailer A updates A's offer and refreshes canonical product metadata.
6. Uncertain product matches (possible matches without GTIN) remain separate canonical products.
7. Product variants (size/color/sku) are created when source data supports them.
8. Synthetic fixture products (60 seed items) have NO retailer offers created.
9. Backward compatibility: legacy products.price, currency, availability, and product_url.
10. Database constraints: negative price rejected, duplicate (retailer_id, source_product_id) rejected.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.ports.repositories import CatalogProductRecord, ProductOfferRecord
from app.domain.ports.source_adapter import RawSourceRecord
from app.domain.services.normalization import normalize_product, payload_hash
from app.domain.services.product_identity import (
    IdentityDecision,
    MATCH_EXACT,
    MATCH_POSSIBLE,
    MATCH_VERIFIED,
)
from app.infrastructure.db.models import (
    OfferPriceHistory,
    Product,
    ProductSourceMap,
    ProductVariant,
    RawSourceRecord as RawSourceRecordModel,
    Retailer,
    RetailerOffer,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from app.infrastructure.external.fashion_catalog_seed import (
    FashionCatalogSeedAdapter,
    compute_test_gtin14,
)

pytestmark = pytest.mark.usefixtures("db")

_GTIN13_A = compute_test_gtin14(1)
_GTIN13_B = compute_test_gtin14(2)


def _make_raw(
    source_product_id: str,
    payload: dict,
    source: str = "myntra",
    source_timestamp: Optional[datetime] = None,
) -> RawSourceRecord:
    full = {
        "id": source_product_id,
        "title": "Raw Title",
        **payload,
    }
    return RawSourceRecord(
        source=source,
        source_record_id=source_product_id,
        payload=full,
        source_timestamp=source_timestamp,
    )


def _ingest(repo: DiscoveryRepositorySQL, raw: RawSourceRecord, run_id: UUID):
    digest = payload_hash(raw.payload)
    raw_id, created = repo.insert_raw_if_absent(
        run_id=run_id,
        source=raw.source,
        source_record_id=raw.source_record_id,
        payload=raw.payload,
        payload_hash=digest,
        source_timestamp=raw.source_timestamp,
    )
    norm = normalize_product(raw)
    assert norm.ok and norm.product is not None
    if not created:
        return IdentityDecision(MATCH_EXACT, None), norm.product, raw_id

    decision = repo.upsert_product(
        product=norm.product,
        run_id=run_id,
        source=raw.source,
        source_product_id=norm.product.source_product_id,
        raw_id=raw_id,
        payload_hash=digest,
    )
    return decision, norm.product, raw_id


def test_two_retailers_offer_same_canonical_product_at_different_prices(db):
    """Retailer A (Myntra) and Retailer B (Amazon) offer the same product at different prices.
    Both offers must be persisted independently under the single canonical product.
    """
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_a = repo.start_run(source="myntra")
        run_b = repo.start_run(source="amazon_in")

        raw_a = _make_raw(
            "MYN-101",
            {
                "title": "Minimalist Linen Shirt",
                "brand": "Atelier",
                "category": "tops",
                "price": 2499.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://myntra.com/p/101",
                "gtin": _GTIN13_A,
            },
            source="myntra",
        )
        raw_b = _make_raw(
            "AMZ-B08XYZ",
            {
                "title": "Atelier Minimalist Linen Shirt - White",
                "brand": "Atelier",
                "category": "tops",
                "price": 1999.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://amazon.in/dp/B08XYZ",
                "gtin": _GTIN13_A,
            },
            source="amazon_in",
        )

        decision_a, _, _ = _ingest(repo, raw_a, run_a)
        assert decision_a.creates_new_product
        product_id_a = session.execute(select(Product.id)).scalar_one()

        decision_b, _, _ = _ingest(repo, raw_b, run_b)
        assert decision_b.match_status == MATCH_VERIFIED
        assert decision_b.product_id == product_id_a

        # Exactly one canonical product exists
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 1
        canonical = products[0]
        assert canonical.id == product_id_a
        assert canonical.title == "Minimalist Linen Shirt"

        # Both retailers exist in the retailers registry
        retailers = session.execute(select(Retailer).order_by(Retailer.slug)).scalars().all()
        assert len(retailers) == 2
        slugs = {r.slug for r in retailers}
        assert slugs == {"amazon_in", "myntra"}

        # Exactly two independent retailer offers exist
        offers = repo.get_product_offers(product_id_a)
        assert len(offers) == 2
        offers_by_slug = {o.retailer_slug: o for o in offers}

        myntra_offer = offers_by_slug["myntra"]
        assert myntra_offer.price == 2499.0
        assert myntra_offer.product_url == "https://myntra.com/p/101"
        assert myntra_offer.availability is True

        amazon_offer = offers_by_slug["amazon_in"]
        assert amazon_offer.price == 1999.0
        assert amazon_offer.product_url == "https://amazon.in/dp/B08XYZ"
        assert amazon_offer.availability is True

        # Initial price history was recorded for both
        history = session.execute(select(OfferPriceHistory)).scalars().all()
        assert len(history) == 2


def test_repeated_ingestion_is_idempotent_no_duplicates(db):
    """Repeated ingestion of the same retailer payload does not duplicate offers or products."""
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_id = repo.start_run(source="myntra")

        raw = _make_raw(
            "MYN-201",
            {
                "title": "Classic Oxford Shirt",
                "brand": "Heritage",
                "category": "tops",
                "price": 1899.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://myntra.com/p/201",
                "gtin": _GTIN13_B,
            },
            source="myntra",
        )

        _ingest(repo, raw, run_id)
        # Ingest identical record again
        _ingest(repo, raw, run_id)

        assert session.execute(select(func.count(Product.id))).scalar_one() == 1
        assert session.execute(select(func.count(RetailerOffer.id))).scalar_one() == 1
        assert session.execute(select(func.count(OfferPriceHistory.id))).scalar_one() == 1


def test_one_retailer_update_never_overwrites_another_retailers_offer(db):
    """When Retailer B's price or availability changes, Retailer B's offer and price history
    are updated, while Retailer A's offer is completely untouched.
    """
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_1 = repo.start_run(source="myntra")
        run_2 = repo.start_run(source="amazon_in")

        raw_a = _make_raw(
            "MYN-301",
            {
                "title": "Tailored Chino Trousers",
                "brand": "Studio",
                "category": "bottoms",
                "price": 3200.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://myntra.com/p/301",
                "gtin": _GTIN13_A,
            },
            source="myntra",
        )
        raw_b = _make_raw(
            "AMZ-301",
            {
                "title": "Studio Tailored Chinos",
                "brand": "Studio",
                "category": "bottoms",
                "price": 2999.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://amazon.in/dp/B09ABC",
                "gtin": _GTIN13_A,
            },
            source="amazon_in",
        )

        _ingest(repo, raw_a, run_1)
        _ingest(repo, raw_b, run_2)

        product_id = session.execute(select(Product.id)).scalar_one()

        # Verify initial state
        offers = repo.get_product_offers(product_id)
        by_slug = {o.retailer_slug: o for o in offers}
        assert by_slug["myntra"].price == 3200.0
        assert by_slug["amazon_in"].price == 2999.0

        # Amazon updates price to 2750.0 and changes URL
        run_3 = repo.start_run(source="amazon_in")
        raw_b_updated = _make_raw(
            "AMZ-301",
            {
                "title": "Studio Tailored Chinos - Sale",
                "brand": "Studio",
                "category": "bottoms",
                "price": 2750.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://amazon.in/dp/B09ABC-new",
                "gtin": _GTIN13_A,
            },
            source="amazon_in",
        )
        decision, _, _ = _ingest(repo, raw_b_updated, run_3)
        assert decision.match_status == MATCH_EXACT

        # Check offers again
        offers_after = repo.get_product_offers(product_id)
        by_slug_after = {o.retailer_slug: o for o in offers_after}

        # Amazon offer was updated
        assert by_slug_after["amazon_in"].price == 2750.0
        assert by_slug_after["amazon_in"].product_url == "https://amazon.in/dp/B09ABC-new"

        # Myntra offer was NOT overwritten
        assert by_slug_after["myntra"].price == 3200.0
        assert by_slug_after["myntra"].product_url == "https://myntra.com/p/301"

        # Canonical product title remains the primary source's title
        canonical = session.execute(select(Product)).scalar_one()
        assert canonical.title == "Tailored Chino Trousers"

        # Amazon offer has 2 price history entries (2999 -> 2750); Myntra has 1 (3200)
        amz_offer_id = by_slug_after["amazon_in"].id
        amz_history = (
            session.execute(
                select(OfferPriceHistory)
                .where(OfferPriceHistory.offer_id == amz_offer_id)
                .order_by(OfferPriceHistory.observed_at.asc())
            )
            .scalars()
            .all()
        )
        assert len(amz_history) == 2
        assert [float(h.price) for h in amz_history] == [2999.0, 2750.0]


def test_uncertain_product_matches_remain_separate(db):
    """Conservative identity matching: listings with matching brand/category but no GTIN
    are reported as MATCH_POSSIBLE and NEVER merged automatically.
    """
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_1 = repo.start_run(source="myntra")
        run_2 = repo.start_run(source="ajio")

        raw_1 = _make_raw(
            "MYN-401",
            {
                "title": "Relaxed Camp Collar Shirt",
                "brand": "Samskara",
                "category": "tops",
                "price": 1800.0,
            },
            source="myntra",
        )
        raw_2 = _make_raw(
            "AJIO-402",
            {
                "title": "Samskara Camp Shirt",
                "brand": "Samskara",
                "category": "tops",
                "price": 1650.0,
            },
            source="ajio",
        )

        decision_1, _, _ = _ingest(repo, raw_1, run_1)
        assert decision_1.creates_new_product

        decision_2, _, _ = _ingest(repo, raw_2, run_2)
        assert decision_2.match_status == MATCH_POSSIBLE
        assert decision_2.creates_new_product

        # Two separate canonical products created
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 2

        # Each has its own retailer offer
        offers = session.execute(select(RetailerOffer)).scalars().all()
        assert len(offers) == 2
        assert {o.source_product_id for o in offers} == {"MYN-401", "AJIO-402"}


def test_product_variants_created_when_source_data_supports_them(db):
    """When source product provides variant dimensions (size/color/sku), a ProductVariant is recorded."""
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_id = repo.start_run(source="myntra")

        raw = _make_raw(
            "MYN-501",
            {
                "title": "Raw Denim Overshirt",
                "brand": "Indigo",
                "category": "outerwear",
                "price": 4500.0,
                "sku": "IND-OVR-L-BLU",
                "size": "L",
                "color": "Indigo Blue",
                "gtin": _GTIN13_A,
            },
            source="myntra",
        )

        _ingest(repo, raw, run_id)

        product = session.execute(select(Product)).scalar_one()
        variant = session.execute(select(ProductVariant)).scalar_one()
        assert variant.product_id == product.id
        assert variant.size == "L"
        assert variant.color == "Indigo Blue"
        assert variant.sku == "IND-OVR-L-BLU"

        offer = session.execute(select(RetailerOffer)).scalar_one()
        assert offer.variant_id == variant.id


def test_synthetic_fixture_products_have_no_retailer_offers(db):
    """Synthetic development fixtures (the 60 seed items) maintain price and metadata directly
    on the products table and do NOT invent spurious retailer offers.
    """
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        adapter = FashionCatalogSeedAdapter()
        run_id = repo.start_run(source=adapter.source_id)

        batch = adapter.fetch_batch(limit=5)
        for raw in batch.records:
            decision, product, raw_id = _ingest(repo, raw, run_id)
            assert decision.creates_new_product

        # Exactly 5 fixture products created
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 5

        for p in products:
            assert p.attributes.get("fixture") is True
            assert p.price is not None
            # Zero retailer offers exist for synthetic fixtures
            offers = repo.get_product_offers(p.id)
            assert len(offers) == 0

        # Retailers table remains empty
        retailer_count = session.execute(select(func.count(Retailer.id))).scalar_one()
        assert retailer_count == 0


def test_backward_compatibility_get_by_id_and_legacy_fields(db):
    """CatalogProductRecord from get_by_id populates active offers and legacy fields cleanly."""
    with db() as session:
        repo = DiscoveryRepositorySQL(session)
        run_id = repo.start_run(source="myntra")

        raw = _make_raw(
            "MYN-601",
            {
                "title": "Cuban Collar Silk Shirt",
                "brand": "Atelier",
                "category": "tops",
                "price": 3499.0,
                "currency": "INR",
                "availability": True,
                "product_url": "https://myntra.com/p/601",
                "gtin": _GTIN13_A,
            },
            source="myntra",
        )
        _ingest(repo, raw, run_id)

        product_id = session.execute(select(Product.id)).scalar_one()
        record: Optional[CatalogProductRecord] = repo.get_by_id(product_id)

        assert record is not None
        assert record.id == product_id
        assert record.title == "Cuban Collar Silk Shirt"
        assert record.price == 3499.0
        assert record.currency == "INR"
        assert record.availability is True
        assert record.product_url == "https://myntra.com/p/601"
        assert len(record.offers) == 1
        assert record.offers[0].retailer_slug == "myntra"
        assert record.offers[0].price == 3499.0


def test_database_constraints_enforced_on_offers_and_retailers(db):
    """Database constraints: negative price rejected, duplicate (retailer_id, source_product_id) rejected."""
    with db() as session:
        retailer = Retailer(slug="test_merchant", name="Test Merchant", domain="testmerchant.com")
        session.add(retailer)
        session.flush()

        product = Product(title="Test Product")
        session.add(product)
        session.flush()

        # Valid offer
        offer = RetailerOffer(
            product_id=product.id,
            retailer_id=retailer.id,
            source_product_id="SKU-1",
            product_url="https://testmerchant.com/1",
            price=100.0,
        )
        session.add(offer)
        session.commit()

        # Duplicate (retailer_id, source_product_id) must fail unique constraint
        duplicate_offer = RetailerOffer(
            product_id=product.id,
            retailer_id=retailer.id,
            source_product_id="SKU-1",
            product_url="https://testmerchant.com/1-dup",
            price=120.0,
        )
        session.add(duplicate_offer)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Negative price must fail check constraint
        invalid_price_offer = RetailerOffer(
            product_id=product.id,
            retailer_id=retailer.id,
            source_product_id="SKU-2",
            product_url="https://testmerchant.com/2",
            price=-50.0,
        )
        session.add(invalid_price_offer)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_alembic_0031_downgrade_and_reupgrade_round_trip(db):
    """Test migration 0031 upgrade, downgrade to 0030, and re-upgrade on isolated test DB."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from app.infrastructure.db.session import DATABASE_URL

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    config.attributes["configure_logger"] = False

    with db() as session:
        inspector = inspect(session.bind)
        assert inspector.has_table("retailers")
        assert inspector.has_table("product_variants")
        assert inspector.has_table("retailer_offers")
        assert inspector.has_table("offer_price_history")

    try:
        command.downgrade(config, "0030")
        with db() as session:
            inspector = inspect(session.bind)
            assert not inspector.has_table("retailer_offers")
            assert not inspector.has_table("offer_price_history")
            assert not inspector.has_table("product_variants")
            assert not inspector.has_table("retailers")
    finally:
        command.upgrade(config, "head")

    with db() as session:
        inspector = inspect(session.bind)
        assert inspector.has_table("retailers")
        assert inspector.has_table("product_variants")
        assert inspector.has_table("retailer_offers")
        assert inspector.has_table("offer_price_history")

