"""Tests for Multi-Retailer Product Comparison & Redirect Foundation (DISCOVERY-10B-3).

Validates:
1. Product with zero offers returns honest empty state.
2. Synthetic fixture product returns isSyntheticFixture=True with zero offers.
3. Product with multiple retailer offers returns verified prices, retailer details, and variants.
4. Price freshness metadata: <=24h is fresh, >24h is stale, None is unverified.
5. Inactive offers are excluded from GET /products/{product_id}/offers.
6. Outbound redirect (GET /offers/{offer_id}/redirect) returns HTTP 307 to authorized destination.
7. Redirect rejects inactive offers with HTTP 410.
8. Redirect rejects unauthorized destination domains with HTTP 403.
9. Redirect records minimal offer_click attribution event in discovery_events.
10. Redirect supports both authenticated user_id and guest_session_id.
11. POST /v1/discovery/events accepts valid offer_click events and rejects disallowed metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import (
    get_candidate_repository,
    get_discovery_event_repository,
    get_optional_user_id,
)
from app.infrastructure.db.models import (
    DiscoveryEvent,
    Product,
    ProductVariant,
    Retailer,
    RetailerOffer,
)
from app.infrastructure.db.repositories import (
    DiscoveryEventRepositorySQL,
    DiscoveryRepositorySQL,
)
from app.main import app

pytestmark = pytest.mark.usefixtures("db")


def _setup_catalog_and_offers(session):
    """Seed test canonical products, retailers, variants, and offers."""
    now = datetime.now(timezone.utc)

    # 1. Retailers
    myntra = Retailer(
        id=uuid4(),
        slug="myntra",
        name="Myntra",
        domain="myntra.com",
        is_active=True,
    )
    amazon = Retailer(
        id=uuid4(),
        slug="amazon_in",
        name="Amazon India",
        domain="amazon.in",
        is_active=True,
    )
    inactive_retailer = Retailer(
        id=uuid4(),
        slug="closed_shop",
        name="Closed Shop",
        domain="closedshop.com",
        is_active=False,
    )
    session.add_all([myntra, amazon, inactive_retailer])
    session.flush()

    # 2. Canonical Real Product
    real_product = Product(
        id=uuid4(),
        title="Linen Overshirt",
        brand="Studio Atelier",
        category="tops",
        subcategory="shirts",
        price=2499.0,
        currency="INR",
        availability=True,
        attributes={"color": "Olive", "fixture": False},
    )

    # 3. Canonical Synthetic Fixture Product
    fixture_product = Product(
        id=uuid4(),
        title="Heritage Trench Coat",
        brand="Heritage Archive",
        category="outerwear",
        subcategory="coats",
        price=5999.0,
        currency="INR",
        availability=True,
        attributes={"fixture": True},
    )

    # 4. Canonical Product with zero offers
    empty_product = Product(
        id=uuid4(),
        title="Minimalist Silk Scarf",
        brand="Studio Atelier",
        category="accessories",
        subcategory="scarves",
        price=999.0,
        currency="INR",
        availability=True,
        attributes={"fixture": False},
    )

    session.add_all([real_product, fixture_product, empty_product])
    session.flush()

    # 5. Product Variant
    variant_m = ProductVariant(
        id=uuid4(),
        product_id=real_product.id,
        sku="ATELIER-LINEN-M-OLV",
        gtin="08901234567890",
        size="M",
        color="Olive",
        attributes={"fit": "relaxed"},
    )
    session.add(variant_m)
    session.flush()

    # 6. Retailer Offers for real_product
    # Offer 1: Fresh price (checked 2h ago)
    offer_myntra = RetailerOffer(
        id=uuid4(),
        product_id=real_product.id,
        retailer_id=myntra.id,
        variant_id=variant_m.id,
        source_product_id="MYN-401",
        product_url="https://www.myntra.com/p/401",
        price=2499.0,
        original_price=2999.0,
        currency="INR",
        availability=True,
        in_stock=True,
        last_checked_at=now - timedelta(hours=2),
        is_active=True,
    )

    # Offer 2: Stale price (checked 30h ago)
    offer_amazon = RetailerOffer(
        id=uuid4(),
        product_id=real_product.id,
        retailer_id=amazon.id,
        variant_id=variant_m.id,
        source_product_id="AMZ-B09123",
        product_url="https://www.amazon.in/dp/B09123",
        price=2199.0,
        original_price=2499.0,
        currency="INR",
        availability=True,
        in_stock=True,
        last_checked_at=now - timedelta(hours=30),
        is_active=True,
    )

    # Offer 3: Inactive offer
    offer_inactive = RetailerOffer(
        id=uuid4(),
        product_id=real_product.id,
        retailer_id=myntra.id,
        source_product_id="MYN-INACTIVE-1",
        product_url="https://www.myntra.com/p/inactive",
        price=1899.0,
        currency="INR",
        availability=False,
        in_stock=False,
        last_checked_at=now,
        is_active=False,
    )

    # Offer 4: Unauthorized domain destination
    offer_unauthorized = RetailerOffer(
        id=uuid4(),
        product_id=real_product.id,
        retailer_id=myntra.id,
        source_product_id="MYN-HACK-1",
        product_url="https://phishing-site.evil.com/fake",
        price=999.0,
        currency="INR",
        availability=True,
        in_stock=True,
        last_checked_at=now,
        is_active=True,
    )

    session.add_all([offer_myntra, offer_amazon, offer_inactive, offer_unauthorized])
    session.commit()

    return {
        "real_product": real_product,
        "fixture_product": fixture_product,
        "empty_product": empty_product,
        "myntra": myntra,
        "amazon": amazon,
        "variant_m": variant_m,
        "offer_myntra": offer_myntra,
        "offer_amazon": offer_amazon,
        "offer_inactive": offer_inactive,
        "offer_unauthorized": offer_unauthorized,
    }


def test_product_with_zero_offers_returns_honest_empty(db):
    """A real canonical product with no commercial offers returns an honest empty state."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        empty_id = str(data["empty_product"].id)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)

        client = TestClient(app)
        resp = client.get(f"/v1/discovery/products/{empty_id}/offers")
        assert resp.status_code == 200
        payload = resp.json()

        assert payload["productId"] == empty_id
        assert payload["isSyntheticFixture"] is False
        assert payload["offersCount"] == 0
        assert payload["offers"] == []


def test_fixture_product_returns_synthetic_disclosure_and_no_offers(db):
    """Synthetic test fixture product returns isSyntheticFixture=True with zero offers."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        fixture_id = str(data["fixture_product"].id)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)

        client = TestClient(app)
        resp = client.get(f"/v1/discovery/products/{fixture_id}/offers")
        assert resp.status_code == 200
        payload = resp.json()

        assert payload["productId"] == fixture_id
        assert payload["isSyntheticFixture"] is True
        assert payload["offersCount"] == 0
        assert payload["offers"] == []


def test_product_with_multiple_retailer_offers_and_freshness(db):
    """Product with multiple retailer offers returns sorted offers, variants, and accurate freshness."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        product_id = str(data["real_product"].id)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)

        client = TestClient(app)
        resp = client.get(f"/v1/discovery/products/{product_id}/offers")
        assert resp.status_code == 200
        payload = resp.json()

        assert payload["productId"] == product_id
        assert payload["isSyntheticFixture"] is False
        # Active offers only (inactive excluded)
        offers = payload["offers"]
        retailer_slugs = [o["retailer"]["slug"] for o in offers]
        assert "myntra" in retailer_slugs
        assert "amazon_in" in retailer_slugs

        # Amazon offer: 2199.0, checked 30h ago -> stale
        amazon_offer = next(o for o in offers if o["retailer"]["slug"] == "amazon_in")
        assert amazon_offer["price"] == 2199.0
        assert amazon_offer["currency"] == "INR"
        assert amazon_offer["isPriceFresh"] is False
        assert amazon_offer["freshnessStatus"] == "stale"
        assert amazon_offer["variant"]["size"] == "M"
        assert amazon_offer["redirectUrl"] == f"/v1/discovery/offers/{amazon_offer['id']}/redirect"

        # Myntra offer: 2499.0, checked 2h ago -> fresh
        myntra_offer = next(
            o for o in offers if o["retailer"]["slug"] == "myntra" and o["price"] == 2499.0
        )
        assert myntra_offer["price"] == 2499.0
        assert myntra_offer["originalPrice"] == 2999.0
        assert myntra_offer["isPriceFresh"] is True
        assert myntra_offer["freshnessStatus"] == "fresh"
        assert myntra_offer["variant"]["color"] == "Olive"


def test_unknown_product_returns_404(db):
    """Querying offers for a non-existent product UUID returns 404 Not Found."""
    with db() as session:
        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)

        client = TestClient(app)
        resp = client.get(f"/v1/discovery/products/{uuid4()}/offers")
        assert resp.status_code == 404


def _create_test_user(session, user_id: Optional[UUID] = None) -> UUID:
    uid = user_id or uuid4()
    session.execute(
        select(Retailer).limit(1)  # keep connection warm
    )
    from sqlalchemy import text
    session.execute(
        text(
            "INSERT INTO users (id, auth_provider, auth_subject, display_name) "
            "VALUES (:id, 'test_provider', :sub, 'Test User')"
        ),
        {"id": uid, "sub": str(uid)},
    )
    session.commit()
    return uid


def test_redirect_to_authorized_offer_and_records_attribution(db):
    """Outbound redirect validates merchant domain, records attribution, and redirects with HTTP 307."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        offer_id = str(data["offer_myntra"].id)
        test_user_id = _create_test_user(session)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: test_user_id

        client = TestClient(app)
        resp = client.get(
            f"/v1/discovery/offers/{offer_id}/redirect?surface=product_offers",
            follow_redirects=False,
        )

        # 1. HTTP 307 Temporary Redirect
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://www.myntra.com/p/401"

        # 2. Minimal attribution event was recorded
        events = session.execute(
            select(DiscoveryEvent).where(DiscoveryEvent.user_id == test_user_id)
        ).scalars().all()
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "offer_click"
        assert ev.target_type == "product"
        assert ev.target_id == str(data["real_product"].id)
        assert ev.surface == "product_offers"
        assert ev.metadata_["offerId"] == offer_id
        assert ev.metadata_["retailer"] == "Myntra"


def test_redirect_supports_guest_session_attribution(db):
    """Guest requests record attribution under guest_session_id without user_id."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        offer_id = str(data["offer_amazon"].id)
        guest_session_id = uuid4()

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: None

        client = TestClient(app)
        resp = client.get(
            f"/v1/discovery/offers/{offer_id}/redirect?guest_session_id={guest_session_id}&surface=product_offers",
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://www.amazon.in/dp/B09123"

        # Guest event recorded
        events = session.execute(
            select(DiscoveryEvent).where(
                DiscoveryEvent.guest_session_id == guest_session_id
            )
        ).scalars().all()
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None
        assert ev.guest_session_id == guest_session_id
        assert ev.event_type == "offer_click"
        assert ev.metadata_["offerId"] == offer_id


def test_redirect_inactive_offer_returns_410(db):
    """Attempting to redirect to an inactive offer returns HTTP 410 Gone."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        inactive_id = str(data["offer_inactive"].id)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: None

        client = TestClient(app)
        resp = client.get(
            f"/v1/discovery/offers/{inactive_id}/redirect",
            follow_redirects=False,
        )
        assert resp.status_code == 410
        assert resp.json()["error"]["code"] == "OFFER_INACTIVE"


def test_redirect_unauthorized_domain_returns_403(db):
    """Destination URL with domain outside retailer.domain is rejected with HTTP 403."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        unauth_id = str(data["offer_unauthorized"].id)

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: None

        client = TestClient(app)
        resp = client.get(
            f"/v1/discovery/offers/{unauth_id}/redirect",
            follow_redirects=False,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "UNAUTHORIZED_DESTINATION"


def test_batch_ingress_accepts_valid_offer_click_event(db):
    """POST /v1/discovery/events accepts offer_click events with approved metadata."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        product_id = str(data["real_product"].id)
        offer_id = str(data["offer_myntra"].id)
        user_id = uuid4()

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: user_id

        client = TestClient(app)
        payload = {
            "events": [
                {
                    "eventId": str(uuid4()),
                    "eventType": "offer_click",
                    "targetType": "product",
                    "targetId": product_id,
                    "surface": "product_offers",
                    "position": 0,
                    "metadata": {
                        "offerId": offer_id,
                        "retailer": "Myntra",
                        "retailerSlug": "myntra",
                    },
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        resp = client.post("/v1/discovery/events", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["acceptedCount"] == 1
        assert body["events"][0]["status"] in {"accepted", "acknowledged"}


def test_batch_ingress_rejects_disallowed_offer_click_metadata(db):
    """POST /v1/discovery/events rejects offer_click with disallowed metadata keys."""
    with db() as session:
        data = _setup_catalog_and_offers(session)
        product_id = str(data["real_product"].id)
        user_id = uuid4()

        app.dependency_overrides[get_candidate_repository] = lambda: DiscoveryRepositorySQL(session)
        app.dependency_overrides[get_discovery_event_repository] = lambda: DiscoveryEventRepositorySQL(session)
        app.dependency_overrides[get_optional_user_id] = lambda: user_id

        client = TestClient(app)
        payload = {
            "events": [
                {
                    "eventId": str(uuid4()),
                    "eventType": "offer_click",
                    "targetType": "product",
                    "targetId": product_id,
                    "surface": "product_offers",
                    "metadata": {
                        "unauthorizedSecretKey": "malicious_value",
                    },
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        resp = client.post("/v1/discovery/events", json=payload)
        assert resp.status_code == 422
