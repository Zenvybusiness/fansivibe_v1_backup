"""Regression tests for server-backed discovery search (TASK DISCOVERY-09C).

Covers all 14 Phase E backend test requirements:
1. Matching by product title.
2. Matching by brand where supported by the schema.
3. Case-insensitive matching.
4. Leading and trailing whitespace.
5. Empty and whitespace-only queries.
6. No-match results with correct pagination metadata.
7. Search combined with category filters.
8. Search combined with price and brand filters.
9. Search combined with include_synthetic.
10. A matching product beyond the first unfiltered page remains discoverable.
11. Search is applied before pagination and total-count calculation.
12. Special SQL wildcard characters are handled safely and consistently.
13. Stable ordering across repeated identical requests.
14. Guest and authenticated access rules remain unchanged.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.api.deps import (
    get_candidate_repository,
    get_optional_user_id,
    get_user_state_repository,
    get_wardrobe_repository,
)
from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.collection import CollectSource, CollectionConfig
from app.application.for_you import PersonalizeForYou
from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductFilterCriteria,
    UserProfileRecord,
)
from app.domain.services.candidate_filters import filter_candidate, validate_criteria
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.infrastructure.db.models import Product
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.external.fashion_catalog_seed import (
    FASHION_SEED_SOURCE_ID,
    FashionCatalogSeedAdapter,
)
from app.main import app
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture
def seeded_db(db):
    """Seed the 60 realistic fashion products into the test database and yield a session."""
    Session = make_session()
    adapter = FashionCatalogSeedAdapter()
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        service = CollectSource(adapter=adapter, repository=repo)
        service(CollectionConfig(source=FASHION_SEED_SOURCE_ID, max_records=200))

    with Session() as session:
        count = session.query(func.count(Product.id)).scalar()
        assert count == 60
        yield session


# ---------------------------------------------------------------------------
# 1. Matching by product title
# ---------------------------------------------------------------------------


def test_search_by_product_title(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    response = client.get("/v1/discovery/for-you?q=Oxford&is_guest=true")
    assert response.status_code == 200
    data = response.json()
    assert data["totalCount"] == 1
    assert data["items"][0]["title"] == "[Seed] Classic Oxford Cloth Button-Down"
    assert data["items"][0]["brand"] == "Harbor & Thread"


# ---------------------------------------------------------------------------
# 2. Matching by brand where supported by schema
# ---------------------------------------------------------------------------


def test_search_by_brand(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    response = client.get("/v1/discovery/for-you?q=Nordic Minimal&is_guest=true")
    assert response.status_code == 200
    data = response.json()
    # Nordic Minimal has multiple seeded products
    assert data["totalCount"] >= 3
    for item in data["items"]:
        assert (
            item["brand"] == "Nordic Minimal"
            or "Nordic Minimal" in item["title"]
        )


# ---------------------------------------------------------------------------
# 3. Case-insensitive matching
# ---------------------------------------------------------------------------


def test_search_case_insensitive(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # Lowercase
    res_lower = client.get("/v1/discovery/for-you?q=oxford&is_guest=true").json()
    # Uppercase
    res_upper = client.get("/v1/discovery/for-you?q=OXFORD&is_guest=true").json()
    # Mixed case
    res_mixed = client.get("/v1/discovery/for-you?q=oXfOrD&is_guest=true").json()

    assert res_lower["totalCount"] == 1
    assert res_upper["totalCount"] == 1
    assert res_mixed["totalCount"] == 1
    assert res_lower["items"][0]["id"] == res_upper["items"][0]["id"]
    assert res_lower["items"][0]["id"] == res_mixed["items"][0]["id"]


# ---------------------------------------------------------------------------
# 4. Leading and trailing whitespace
# ---------------------------------------------------------------------------


def test_search_leading_and_trailing_whitespace(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    res_trimmed = client.get("/v1/discovery/for-you?q=Oxford&is_guest=true").json()
    res_padded = client.get("/v1/discovery/for-you?q=%20%20%20Oxford%20%20%20&is_guest=true").json()

    assert res_padded["totalCount"] == res_trimmed["totalCount"]
    assert res_padded["items"][0]["id"] == res_trimmed["items"][0]["id"]


# ---------------------------------------------------------------------------
# 5. Empty and whitespace-only queries
# ---------------------------------------------------------------------------


def test_search_empty_and_whitespace_only_queries(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    res_all = client.get("/v1/discovery/for-you?is_guest=true").json()
    res_empty = client.get("/v1/discovery/for-you?q=&is_guest=true").json()
    res_spaces = client.get("/v1/discovery/for-you?q=%20%20%20&is_guest=true").json()

    assert res_empty["totalCount"] == res_all["totalCount"] == 60
    assert res_spaces["totalCount"] == res_all["totalCount"] == 60
    assert len(res_empty["items"]) == len(res_all["items"]) == 20


# ---------------------------------------------------------------------------
# 6. No-match results with correct pagination metadata
# ---------------------------------------------------------------------------


def test_search_no_match_pagination_metadata(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    response = client.get("/v1/discovery/for-you?q=NonexistentBrandXYZ123&is_guest=true")
    assert response.status_code == 200
    data = response.json()

    assert data["items"] == []
    assert data["totalCount"] == 0
    assert data["page"] == 1
    assert data["pageSize"] == 20
    assert data["totalPages"] == 0
    assert data["hasNext"] is False
    assert data["hasPrev"] is False


# ---------------------------------------------------------------------------
# 7. Search combined with category filters
# ---------------------------------------------------------------------------


def test_search_combined_with_category_filters(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # Khadi without category returns 4 products across tops, bottoms, outerwear, footwear
    all_khadi = client.get("/v1/discovery/for-you?q=Khadi&is_guest=true").json()
    assert all_khadi["totalCount"] == 4

    # Khadi + footwear category returns only 1 product (Espadrilles)
    footwear_khadi = client.get(
        "/v1/discovery/for-you?categories=footwear&q=Khadi&is_guest=true"
    ).json()
    assert footwear_khadi["totalCount"] == 1
    assert footwear_khadi["items"][0]["category"] == "footwear"
    assert "Espadrilles" in footwear_khadi["items"][0]["title"]

    # Khadi + tops category returns only 1 product (Kurta)
    tops_khadi = client.get(
        "/v1/discovery/for-you?categories=tops&q=Khadi&is_guest=true"
    ).json()
    assert tops_khadi["totalCount"] == 1
    assert tops_khadi["items"][0]["category"] == "tops"
    assert "Kurta" in tops_khadi["items"][0]["title"]


# ---------------------------------------------------------------------------
# 8. Search combined with price and brand filters
# ---------------------------------------------------------------------------


def test_search_combined_with_price_and_brand_filters(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # Harbor & Thread products matching Jacket under INR 8,000
    res = client.get(
        "/v1/discovery/for-you?brands=Harbor%20%26%20Thread&max_price=8000&q=Jacket&is_guest=true"
    ).json()
    assert res["totalCount"] == 1
    item = res["items"][0]
    assert item["brand"] == "Harbor & Thread"
    assert "Jacket" in item["title"]
    assert item["price"] <= 8000

    # Harbor & Thread products matching Jacket with budget too low (max_price=1000)
    res_empty = client.get(
        "/v1/discovery/for-you?brands=Harbor%20%26%20Thread&max_price=1000&q=Jacket&is_guest=true"
    ).json()
    assert res_empty["totalCount"] == 0
    assert res_empty["items"] == []


# ---------------------------------------------------------------------------
# 9. Search combined with include_synthetic
# ---------------------------------------------------------------------------


def test_search_combined_with_include_synthetic(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # When include_synthetic=true (default), synthetic seed products are found
    res_synth = client.get(
        "/v1/discovery/for-you?q=Oxford&include_synthetic=true&is_guest=true"
    ).json()
    assert res_synth["totalCount"] == 1
    assert res_synth["items"][0]["isSynthetic"] is True

    # When include_synthetic=false, synthetic fixtures are excluded
    res_no_synth = client.get(
        "/v1/discovery/for-you?q=Oxford&include_synthetic=false&is_guest=true"
    ).json()
    assert res_no_synth["totalCount"] == 0
    assert res_no_synth["items"] == []


# ---------------------------------------------------------------------------
# 10. Matching product beyond first unfiltered page remains discoverable
# ---------------------------------------------------------------------------


def test_product_beyond_first_page_is_discoverable(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # In the unfiltered catalog (page_size=20), page 1 contains items 1–20.
    # Classic Oxford Cloth Button-Down is at position 55 (page 3).
    page1_unfiltered = client.get("/v1/discovery/for-you?page=1&page_size=20&is_guest=true").json()
    unfiltered_titles = [it["title"] for it in page1_unfiltered["items"]]
    assert "[Seed] Classic Oxford Cloth Button-Down" not in unfiltered_titles

    # With server-backed search for "Oxford", it is discovered immediately on page 1!
    search_res = client.get("/v1/discovery/for-you?page=1&page_size=20&q=Oxford&is_guest=true").json()
    assert search_res["totalCount"] == 1
    assert search_res["page"] == 1
    assert search_res["totalPages"] == 1
    assert search_res["hasNext"] is False
    assert search_res["items"][0]["title"] == "[Seed] Classic Oxford Cloth Button-Down"


# ---------------------------------------------------------------------------
# 11. Search is applied before pagination and total-count calculation
# ---------------------------------------------------------------------------


def test_search_applied_before_pagination_and_total_count(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # "Shirt" matches multiple tops in the seeded catalog
    res = client.get("/v1/discovery/for-you?q=Shirt&page=1&page_size=3&is_guest=true").json()
    assert res["totalCount"] > 3
    assert res["page"] == 1
    assert res["pageSize"] == 3
    assert len(res["items"]) == 3
    assert res["totalPages"] == (res["totalCount"] + 3 - 1) // 3
    assert res["hasNext"] is True

    # Page 2 returns the next slice of matching items without duplicating page 1
    res_p2 = client.get("/v1/discovery/for-you?q=Shirt&page=2&page_size=3&is_guest=true").json()
    assert res_p2["page"] == 2
    assert len(res_p2["items"]) == 3
    assert res_p2["hasPrev"] is True
    p1_ids = {it["id"] for it in res["items"]}
    p2_ids = {it["id"] for it in res_p2["items"]}
    assert p1_ids.isdisjoint(p2_ids)


# ---------------------------------------------------------------------------
# 12. Special SQL wildcard characters are handled safely and consistently
# ---------------------------------------------------------------------------


def test_special_sql_wildcards_handled_safely(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    # % must NOT act as match-all wildcard; no product has literal % in title/brand/category
    res_percent = client.get("/v1/discovery/for-you?q=%25&is_guest=true").json()
    assert res_percent["totalCount"] == 0
    assert res_percent["items"] == []

    # _ must NOT act as match-any-char wildcard; it matches only products with literal _
    # (specifically the 8 items with underscores in subcategories like cargo_pants, chelsea_boots)
    res_underscore = client.get("/v1/discovery/for-you?q=_&is_guest=true").json()
    assert res_underscore["totalCount"] == 8
    for item in res_underscore["items"]:
        # Verify literal _ exists in subcategory or title
        sub = item.get("subcategory") or ""
        assert "_" in sub or "_" in item["title"]

    # Backslash \ must not cause SQL syntax errors
    res_slash = client.get("/v1/discovery/for-you?q=%5C&is_guest=true").json()
    assert res_slash["totalCount"] == 0
    assert res_slash["items"] == []


# ---------------------------------------------------------------------------
# 13. Stable ordering across repeated identical requests
# ---------------------------------------------------------------------------


def test_search_stable_ordering(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo
    app.dependency_overrides[get_optional_user_id] = lambda: None

    run1 = client.get("/v1/discovery/for-you?q=Pants&is_guest=true").json()
    run2 = client.get("/v1/discovery/for-you?q=Pants&is_guest=true").json()

    assert run1["totalCount"] == run2["totalCount"]
    assert len(run1["items"]) == len(run2["items"])
    assert [it["id"] for it in run1["items"]] == [it["id"] for it in run2["items"]]
    assert [it["score"] for it in run1["items"]] == [it["score"] for it in run2["items"]]


# ---------------------------------------------------------------------------
# 14. Guest and authenticated access rules remain unchanged
# ---------------------------------------------------------------------------


def test_search_guest_and_authenticated_access(seeded_db) -> None:
    repo = DiscoveryRepositorySQL(seeded_db)
    client = TestClient(app)
    app.dependency_overrides[get_candidate_repository] = lambda: repo

    # Guest access succeeds without credentials
    app.dependency_overrides[get_optional_user_id] = lambda: None
    guest_res = client.get("/v1/discovery/for-you?q=Khadi&is_guest=true")
    assert guest_res.status_code == 200
    guest_data = guest_res.json()
    assert guest_data["isPersonalized"] is False
    assert guest_data["appliedContext"]["isGuest"] is True

    # Invalid Bearer token fails closed with 401
    # Clear optional user id override to exercise real token validation dependency
    app.dependency_overrides.pop(get_optional_user_id, None)
    invalid_token_res = client.get(
        "/v1/discovery/for-you?q=Khadi",
        headers={"Authorization": "Bearer totally-invalid-jwt-token-xyz"},
    )
    assert invalid_token_res.status_code == 401
