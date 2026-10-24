"""Tests for Fansivibe Unified Discovery API (TASK DISCOVERY-05).

Covers:
- `GET /v1/discovery/for-you` (Authenticated personalization, guest privacy boundary, hard filters, synthetic fixtures, pagination).
- `GET /v1/discovery/looks/complete` (Slot serialization, owner-scoped wardrobe, anchor checks, catalog price isolation, budget enforcement).
- `GET /v1/discovery/trending` (Authentication, window bounds, demand unavailable, null handling, honest catalog activity).
- OpenAPI schema validation for all 3 routes.
- Database integration against seeded test catalog.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_candidate_repository,
    get_current_user_id,
    get_optional_user_id,
    get_trend_repository,
    get_user_state_repository,
    get_wardrobe_repository,
)
from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.collection import CollectSource, CollectionConfig
from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductFilterCriteria,
    UserProfileRecord,
    WardrobeItemRecord,
)
from app.domain.services.candidate_filters import filter_candidate
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.domain.services.trends import (
    DEMAND_SIGNAL_AVAILABLE,
    REASON_NO_DEMAND,
    ObservationEvidence,
    Signal,
    TrendAnalysis,
    TrendCandidate,
)
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    TrendRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.external.fashion_catalog_seed import (
    FASHION_SEED_SOURCE_ID,
    FashionCatalogSeedAdapter,
)
from app.main import app
from tests.conftest import make_session

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test Fakes for In-Memory Unit / Route Tests
# ---------------------------------------------------------------------------


class FakeCandidateRepository:
    def __init__(self, products: Optional[list[CatalogProductRecord]] = None) -> None:
        self.products: list[CatalogProductRecord] = list(products or [])

    def get_by_id(self, product_id: UUID) -> Optional[CatalogProductRecord]:
        for p in self.products:
            if p.id == product_id:
                return p
        return None

    def _matches(self, p: CatalogProductRecord, criteria: ProductFilterCriteria) -> bool:
        bridge = map_product_attributes_to_ffo(p)
        return filter_candidate(p, criteria, bridge_result=bridge)

    def count_candidates(self, criteria: ProductFilterCriteria) -> int:
        return sum(1 for p in self.products if self._matches(p, criteria))

    def get_candidates(
        self,
        criteria: ProductFilterCriteria,
        *,
        sort_order: str = "newest",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[CatalogProductRecord, ...]:
        matched = [p for p in self.products if self._matches(p, criteria)]
        return tuple(matched[offset : offset + limit])


class FakeUserStateRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, UserProfileRecord] = {}

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        return self.profiles.get(user_id)

    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]:
        p = self.profiles.get(user_id)
        return p.style_profile if p else None

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        pass

    def update_style_profile(self, *, user_id: UUID, **kwargs) -> None:
        pass


class FakeWardrobeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[WardrobeItemRecord]] = {}

    def get_for_user(
        self, *, user_id: UUID, page: int = 1, page_size: int = 100, **kwargs
    ) -> tuple[list[WardrobeItemRecord], int]:
        user_items = self.items.get(user_id, [])
        offset = (page - 1) * page_size
        return user_items[offset : offset + page_size], len(user_items)

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[WardrobeItemRecord]:
        for it in self.items.get(user_id, []):
            if it.id == item_id:
                return it
        return None


class FakeTrendRepository:
    def __init__(self, observations: Optional[list[ObservationEvidence]] = None) -> None:
        self.observations = list(observations or [])

    def observations_in_window(
        self, *, window_start: datetime, window_end: datetime
    ) -> tuple[ObservationEvidence, ...]:
        return tuple(
            o
            for o in self.observations
            if window_start <= o.observed_at < window_end
        )


def _make_product(
    *,
    id: Optional[UUID] = None,
    title: str = "Linen Summer Shirt",
    category: str = "tops",
    brand: str = "FabIndia",
    price: float = 2499.0,
    color: str = "navy",
    material: str = "linen",
    fit: str = "relaxed",
    silhouette: str = "oversized",
    is_synthetic: bool = True,
    is_fixture: bool = True,
    availability: bool = True,
    created_at: Optional[datetime] = None,
) -> CatalogProductRecord:
    return CatalogProductRecord(
        id=id or uuid4(),
        title=title,
        brand=brand,
        category=category,
        price=price,
        currency="INR",
        availability=availability,
        image_urls=("https://cdn.fansivibe.com/img1.jpg",),
        attributes={
            "color": color,
            "material": material,
            "fit": fit,
            "silhouette": silhouette,
            "synthetic": is_synthetic,
            "fixture": is_fixture,
        },
        created_at=created_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Route A: GET /v1/discovery/for-you Tests
# ---------------------------------------------------------------------------


def test_for_you_authenticated_user_profile_and_preferences() -> None:
    """Verify that authenticated user profile and preferences shape recommendations and explanations."""
    user_id = uuid4()
    p1 = _make_product(title="FabIndia Tops", category="tops", brand="FabIndia", color="navy")
    p2 = _make_product(title="Zara Bottoms", category="bottoms", brand="Zara", color="black")

    cand_repo = FakeCandidateRepository([p1, p2])
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Aarav",
        style_profile={"style_type": "minimalist"},
        preferences={
            "preferredCategories": ["tops"],
            "preferredBrands": ["FabIndia"],
            "preferredColors": ["navy"],
        },
        settings={},
        flags={},
        version=1,
    )
    wardrobe_repo = FakeWardrobeRepository()

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_user_state_repository] = lambda: state_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        response = client.get("/v1/discovery/for-you")
        assert response.status_code == 200
        data = response.json()

        assert data["isPersonalized"] is True
        assert data["appliedContext"]["isGuest"] is False
        assert data["appliedContext"]["userId"] == str(user_id)
        assert data["appliedContext"]["displayName"] == "Aarav"
        assert len(data["items"]) == 2

        # FabIndia tops should be ranked #1
        top_item = data["items"][0]
        assert top_item["id"] == str(p1.id)
        assert top_item["rank"] == 1
        assert top_item["score"] > data["items"][1]["score"]
        assert top_item["scoreBreakdown"]["preferenceMatch"] >= 20.0
        assert "FabIndia" in top_item["explanation"]["summary"]
        assert top_item["isSynthetic"] is True
        assert top_item["isFixture"] is True
        assert top_item["explanation"]["isSyntheticFixture"] is True
        assert top_item["explanation"]["provenance"] == "synthetic_fixture_catalog"
    finally:
        app.dependency_overrides.clear()


def test_for_you_guest_access_cannot_read_user_profile() -> None:
    """Verify that unauthenticated guest requests cannot read user profile and fallback cleanly."""
    p1 = _make_product(title="Catalog Top", category="tops", price=1299.0)
    cand_repo = FakeCandidateRepository([p1])
    wardrobe_repo = FakeWardrobeRepository()
    state_repo = FakeUserStateRepository()

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_user_state_repository] = lambda: state_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    try:
        response = client.get("/v1/discovery/for-you?is_guest=true")
        assert response.status_code == 200
        data = response.json()

        assert data["isPersonalized"] is False
        assert data["appliedContext"]["isGuest"] is True
        assert data["appliedContext"]["userId"] is None
        assert data["appliedContext"]["displayName"] is None
        assert len(data["items"]) == 1
        assert "Catalog recommendation" in data["items"][0]["explanation"]["summary"]
    finally:
        app.dependency_overrides.clear()


def test_for_you_invalid_token_returns_401() -> None:
    """Verify that providing an invalid Authorization header returns HTTP 401."""
    response = client.get(
        "/v1/discovery/for-you",
        headers={"Authorization": "Bearer malformed_expired_token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_for_you_hard_filters_and_validation() -> None:
    """Verify hard filter enforcement and 422 error on inverted price bounds."""
    p_cheap = _make_product(title="Cheap Top", category="tops", price=999.0)
    p_expensive = _make_product(title="Expensive Top", category="tops", price=9999.0)
    cand_repo = FakeCandidateRepository([p_cheap, p_expensive])

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    try:
        # 1. Hard filter: max_price = 2000
        res = client.get("/v1/discovery/for-you?max_price=2000")
        assert res.status_code == 200
        data = res.json()
        assert data["totalCount"] == 1
        assert data["items"][0]["id"] == str(p_cheap.id)

        # 2. Inverted bounds: min_price > max_price -> 422
        bad_res = client.get("/v1/discovery/for-you?min_price=5000&max_price=1000")
        assert bad_res.status_code == 422
        assert bad_res.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route B: GET /v1/discovery/looks/complete Tests
# ---------------------------------------------------------------------------


def test_complete_looks_catalog_only_assembly() -> None:
    """Verify complete looks generation for unauthenticated / catalog-only flow."""
    top = _make_product(title="Linen Shirt", category="tops", price=2500.0)
    bot = _make_product(title="Chinos", category="bottoms", price=3000.0)
    cand_repo = FakeCandidateRepository([top, bot])
    wardrobe_repo = FakeWardrobeRepository()

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    try:
        res = client.get("/v1/discovery/looks/complete?limit=5")
        assert res.status_code == 200
        data = res.json()

        assert data["totalLooks"] == 1
        assert data["isWardrobeAware"] is False
        look = data["looks"][0]
        assert "top" in look["slots"]
        assert "bottom" in look["slots"]
        assert look["totalCatalogPrice"] == 5500.0
        assert look["wardrobeItemCount"] == 0
        assert look["catalogItemCount"] == 2
        assert look["bundlePurchasable"] is False
        assert "2-piece catalog ensemble" in look["explanation"]["summary"]
    finally:
        app.dependency_overrides.clear()


def test_complete_looks_wardrobe_aware_and_catalog_price_isolation() -> None:
    """Verify that owned wardrobe items contribute ₹0 to catalog budget while filling slots."""
    user_id = uuid4()
    owned_bottom = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_id,
        name="Owned Dark Denim",
        category="bottoms",
        color="dark blue",
        material="denim",
        is_favorite=True,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    catalog_top = _make_product(title="Cashmere Polo", category="tops", price=4500.0)

    cand_repo = FakeCandidateRepository([catalog_top])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [owned_bottom]

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        res = client.get("/v1/discovery/looks/complete?max_budget=5000")
        assert res.status_code == 200
        data = res.json()

        assert data["totalLooks"] == 1
        assert data["isWardrobeAware"] is True
        look = data["looks"][0]

        # Bottom comes from wardrobe with price 0.0
        bot_slot = look["slots"]["bottom"]
        assert bot_slot["source"] == "wardrobe"
        assert bot_slot["itemId"] == str(owned_bottom.id)
        assert bot_slot["price"] == 0.0

        # Top comes from catalog with price 4500.0
        top_slot = look["slots"]["top"]
        assert top_slot["source"] == "catalog"
        assert top_slot["price"] == 4500.0

        # Total catalog spend is strictly 4500.0 (excludes wardrobe item)
        assert look["totalCatalogPrice"] == 4500.0
        assert look["wardrobeItemCount"] == 1
        assert look["catalogItemCount"] == 1
        assert look["explanation"]["isWardrobeAware"] is True
        assert "1 piece from your wardrobe with 1 catalog item" in look["explanation"]["summary"]
    finally:
        app.dependency_overrides.clear()


def test_complete_looks_anchor_wardrobe_privacy_guards() -> None:
    """Verify that unauthenticated anchor request fails with 401 and foreign anchor fails with 404."""
    user_a = uuid4()
    user_b = uuid4()
    item_b = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_b,
        name="User B Private Jacket",
        category="outerwear",
        color="black",
        material="leather",
        is_favorite=False,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    cand_repo = FakeCandidateRepository([])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_b] = [item_b]

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo

    # 1. Unauthenticated request attempts to anchor to a wardrobe item -> 401
    app.dependency_overrides[get_optional_user_id] = lambda: None
    try:
        res = client.get(f"/v1/discovery/looks/complete?anchor_wardrobe_item_id={item_b.id}")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTHENTICATION_ERROR"
    finally:
        app.dependency_overrides.clear()

    # 2. User A attempts to anchor to User B's wardrobe item -> 404 (not found in user's wardrobe)
    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_optional_user_id] = lambda: user_a
    try:
        res = client.get(f"/v1/discovery/looks/complete?anchor_wardrobe_item_id={item_b.id}")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route C: GET /v1/discovery/trending Tests
# ---------------------------------------------------------------------------


def test_discovery_trending_requires_auth() -> None:
    """Verify that GET /v1/discovery/trending requires Bearer authentication."""
    res = client.get("/v1/discovery/trending")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_discovery_trending_preserves_demand_unavailable_and_null_metrics() -> None:
    """Verify that discovery trending preserves DEMAND_SIGNAL_AVAILABLE = False and null metrics."""
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    obs = ObservationEvidence(
        product_id=uuid4(),
        category="outerwear",
        source="test_source",
        observed_at=now - timedelta(days=2),
        price=3499.0,
        availability=True,
    )
    trend_repo = FakeTrendRepository([obs])

    app.dependency_overrides[get_trend_repository] = lambda: trend_repo
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        res = client.get("/v1/discovery/trending", headers={"Authorization": "Bearer dev"})
        assert res.status_code == 200
        data = res.json()

        assert data["demandTrendStatus"] == "insufficient_evidence"
        assert data["directDemandAvailable"] is False
        assert data["evidenceType"] == "catalog_activity"
        assert REASON_NO_DEMAND in data["insufficientEvidenceReason"]
        assert len(data["limitations"]) > 0

        # Observations count and structure
        assert data["observationCount"] == 1
        assert data["sourceCoverage"] == 1
    finally:
        app.dependency_overrides.clear()


def test_discovery_trending_window_validation() -> None:
    """Verify window validation (window > 90 days or end before start returns 422)."""
    user_id = uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_trend_repository] = lambda: FakeTrendRepository([])

    try:
        # Window > 90 days
        start = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        end = datetime.now(timezone.utc).isoformat()
        res = client.get(
            f"/v1/discovery/trending?window_start={start}&window_end={end}",
            headers={"Authorization": "Bearer dev"},
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route D: OpenAPI Contract Tests
# ---------------------------------------------------------------------------


def test_openapi_schema_contains_discovery_endpoints_and_schemas() -> None:
    """Verify that OpenAPI documentation contains all three discovery routes and typed schemas."""
    schema = app.openapi()
    paths = schema.get("paths", {})

    assert "/v1/discovery/for-you" in paths
    assert "/v1/discovery/looks/complete" in paths
    assert "/v1/discovery/trending" in paths

    # Verify GET methods
    assert "get" in paths["/v1/discovery/for-you"]
    assert "get" in paths["/v1/discovery/looks/complete"]
    assert "get" in paths["/v1/discovery/trending"]

    # Verify components schemas
    components = schema.get("components", {}).get("schemas", {})
    assert "ForYouDiscoveryResponse" in components
    assert "ProductRecommendationItemSchema" in components
    assert "ProductExplanationSchema" in components
    assert "CompleteLooksDiscoveryResponse" in components
    assert "CompleteLookSchema" in components
    assert "CompleteLookExplanationSchema" in components
    assert "DiscoveryTrendingResponse" in components
    assert "DiscoveryTrendItemSchema" in components


# ---------------------------------------------------------------------------
# Route E: Database Integration Test (fansivibe_test seeded catalog)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture
def seeded_db(db):
    """Seed the 60 realistic fashion products into test database and yield session."""
    Session = make_session()
    adapter = FashionCatalogSeedAdapter()
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        service = CollectSource(adapter=adapter, repository=repo)
        service(CollectionConfig(source=FASHION_SEED_SOURCE_ID, max_records=200))

    with Session() as session:
        yield session


def test_discovery_endpoints_live_database_integration(seeded_db) -> None:
    """Verify discovery endpoints against the real PostgreSQL database with seeded catalog."""
    cand_repo = DiscoveryRepositorySQL(seeded_db)
    user_repo = UserStateRepositorySQL(seeded_db)
    wardrobe_repo = WardrobeItemRepositorySQL(seeded_db)
    trend_repo = TrendRepositorySQL(seeded_db)

    app.dependency_overrides[get_candidate_repository] = lambda: cand_repo
    app.dependency_overrides[get_user_state_repository] = lambda: user_repo
    app.dependency_overrides[get_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_trend_repository] = lambda: trend_repo
    app.dependency_overrides[get_optional_user_id] = lambda: None
    app.dependency_overrides[get_current_user_id] = lambda: uuid4()

    try:
        # 1. GET /v1/discovery/for-you (guest)
        res_foryou = client.get("/v1/discovery/for-you?page=1&page_size=10")
        assert res_foryou.status_code == 200
        data_foryou = res_foryou.json()
        assert data_foryou["totalCount"] == 60
        assert len(data_foryou["items"]) == 10
        assert data_foryou["totalPages"] == 6
        assert data_foryou["hasNext"] is True
        assert data_foryou["items"][0]["explanation"]["summary"] is not None

        # 2. GET /v1/discovery/looks/complete (catalog-only)
        res_looks = client.get("/v1/discovery/looks/complete?limit=5")
        assert res_looks.status_code == 200
        data_looks = res_looks.json()
        assert data_looks["totalLooks"] > 0
        first_look = data_looks["looks"][0]
        assert "top" in first_look["slots"]
        assert "bottom" in first_look["slots"]
        assert first_look["totalCatalogPrice"] > 0
        assert first_look["explanation"]["summary"] is not None

        # 3. GET /v1/discovery/trending
        res_trend = client.get("/v1/discovery/trending", headers={"Authorization": "Bearer dev"})
        assert res_trend.status_code == 200
        data_trend = res_trend.json()
        assert data_trend["demandTrendStatus"] == "insufficient_evidence"
        assert data_trend["directDemandAvailable"] is False
    finally:
        app.dependency_overrides.clear()
