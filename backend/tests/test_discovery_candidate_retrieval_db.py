"""Database integration tests for shared candidate retrieval (TASK DISCOVERY-03).

Runs against the isolated test PostgreSQL database (fansivibe_test).
Verifies:
- Repository and application retrieval from seeded catalog (60 products).
- Category inclusion and exclusion.
- Brand and attribute filtering.
- Price boundary filtering in INR.
- Trustworthy stock/availability filtering.
- Synthetic fixture identification and exclusion.
- Bounded, stable, non-duplicated pagination across pages.
- Deterministic sort orders across repeated calls.
- FFO concept candidate filtering.
- Validation and error handling.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.collection import CollectSource, CollectionConfig
from app.domain.ports.repositories import ProductFilterCriteria
from app.infrastructure.db.models import Product
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from app.infrastructure.external.fashion_catalog_seed import (
    FASHION_SEED_SOURCE_ID,
    FashionCatalogSeedAdapter,
)
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


def test_catalog_total_and_category_candidate_retrieval(seeded_db) -> None:
    """Verify default retrieval and category inclusion/exclusion over the 60 products."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Default retrieval: 60 total, 20 on page 1, 3 pages total
    res = use_case(page=1, page_size=20)
    assert res.total_count == 60
    assert len(res.items) == 20
    assert res.total_pages == 3
    assert res.has_next is True
    assert res.has_prev is False
    assert res.next_cursor is not None

    # Category inclusion
    expected_categories = {
        "tops": 14,
        "bottoms": 12,
        "outerwear": 12,
        "footwear": 12,
        "accessories": 10,
    }
    for cat, expected_count in expected_categories.items():
        cat_res = use_case(ProductFilterCriteria(categories=(cat,)), page_size=50)
        assert cat_res.total_count == expected_count
        assert all(c.category == cat for c in cat_res.items)

    # Category exclusion: excluding footwear and accessories leaves 38 products
    exc_res = use_case(
        ProductFilterCriteria(exclude_categories=("footwear", "accessories")),
        page_size=50,
    )
    assert exc_res.total_count == 38
    assert all(c.category not in ("footwear", "accessories") for c in exc_res.items)


def test_price_boundary_filtering(seeded_db) -> None:
    """Verify price range boundaries in INR."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Range: INR 2000 to 4000
    res = use_case(ProductFilterCriteria(min_price=2000.0, max_price=4000.0), page_size=50)
    assert res.total_count == 25
    assert len(res.items) == 25
    for c in res.items:
        assert c.price is not None
        assert 2000.0 <= c.price <= 4000.0
        assert c.currency == "INR"

    # Strict lower bound: >= 10000
    high_res = use_case(ProductFilterCriteria(min_price=10000.0))
    for c in high_res.items:
        assert c.price is not None and c.price >= 10000.0

    # Strict upper bound: <= 1500
    low_res = use_case(ProductFilterCriteria(max_price=1500.0))
    for c in low_res.items:
        assert c.price is not None and c.price <= 1500.0


def test_brand_and_attribute_filtering(seeded_db) -> None:
    """Verify brand, material, fit, and silhouette filters."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Brand filter: "Indus Thread Co."
    brand_res = use_case(ProductFilterCriteria(brands=("Indus Thread Co.",)))
    assert brand_res.total_count > 0
    assert all(c.brand == "Indus Thread Co." for c in brand_res.items)

    # Material filter: "khadi_cotton"
    mat_res = use_case(ProductFilterCriteria(materials=("khadi_cotton",)))
    assert mat_res.total_count == 2
    assert all(c.product.material == "khadi_cotton" for c in mat_res.items)

    # Fit filter: "relaxed"
    fit_res = use_case(ProductFilterCriteria(fits=("relaxed",)))
    assert fit_res.total_count == 9
    assert all(c.product.fit == "relaxed" for c in fit_res.items)

    # Silhouette filter: "mandarin_collar"
    sil_res = use_case(ProductFilterCriteria(silhouettes=("mandarin_collar",)))
    assert sil_res.total_count == 2
    assert all(c.product.silhouette == "mandarin_collar" for c in sil_res.items)


def test_stock_availability_filtering(seeded_db) -> None:
    """Verify explicit stock/availability filtering."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Seed products have availability=True
    res_in_stock = use_case(ProductFilterCriteria(in_stock_only=True))
    assert res_in_stock.total_count == 60
    assert all(c.availability is True for c in res_in_stock.items)

    # in_stock_only=False matches 0 of the seeded products
    res_out_stock = use_case(ProductFilterCriteria(in_stock_only=False))
    assert res_out_stock.total_count == 0
    assert res_out_stock.items == ()


def test_synthetic_fixture_isolation(seeded_db) -> None:
    """Verify synthetic fixtures are explicitly identified and filterable."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # include_synthetic=True returns all 60 fixtures
    res_incl = use_case(ProductFilterCriteria(include_synthetic=True))
    assert res_incl.total_count == 60
    for c in res_incl.items:
        assert c.is_synthetic is True
        assert c.is_fixture is True

    # include_synthetic=False excludes all synthetic test fixtures
    res_excl = use_case(ProductFilterCriteria(include_synthetic=False))
    assert res_excl.total_count == 0
    assert res_excl.items == ()


def test_pagination_and_non_duplication(seeded_db) -> None:
    """Verify pages are stable and produce zero duplicated items across pages."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Fetch 3 full pages of 20 items
    p1 = use_case(page=1, page_size=20)
    p2 = use_case(page=2, page_size=20)
    p3 = use_case(page=3, page_size=20)
    p4 = use_case(page=4, page_size=20)

    assert len(p1.items) == 20
    assert len(p2.items) == 20
    assert len(p3.items) == 20
    assert len(p4.items) == 0

    ids1 = {c.id for c in p1.items}
    ids2 = {c.id for c in p2.items}
    ids3 = {c.id for c in p3.items}

    # Mutual disjointness: zero duplicates across pages
    assert len(ids1 & ids2) == 0
    assert len(ids2 & ids3) == 0
    assert len(ids1 & ids3) == 0

    # Exhaustive coverage
    all_ids = ids1 | ids2 | ids3
    assert len(all_ids) == 60

    # Verify pagination indicators
    assert p1.has_next is True and p1.has_prev is False
    assert p2.has_next is True and p2.has_prev is True
    assert p3.has_next is False and p3.has_prev is True
    assert p4.has_next is False and p4.has_prev is True


def test_deterministic_ordering_across_repeated_calls(seeded_db) -> None:
    """Verify that repeated queries with the same filters return identical ordered results."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    for sort_order in ("price_asc", "price_desc", "title_asc", "newest", "id_asc"):
        r1 = use_case(sort_order=sort_order, page=1, page_size=25)
        r2 = use_case(sort_order=sort_order, page=1, page_size=25)

        ids1 = [c.id for c in r1.items]
        ids2 = [c.id for c in r2.items]
        assert ids1 == ids2
        assert len(ids1) == 25

        if sort_order == "price_asc":
            prices = [c.price for c in r1.items if c.price is not None]
            assert prices == sorted(prices)
        elif sort_order == "price_desc":
            prices = [c.price for c in r1.items if c.price is not None]
            assert prices == sorted(prices, reverse=True)
        elif sort_order == "title_asc":
            titles = [c.title for c in r1.items]
            assert titles == sorted(titles)


def test_ffo_concept_candidate_filtering(seeded_db) -> None:
    """Verify candidate filtering by verified FFO concepts."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    # Filter for 'cotton'
    cotton_res = use_case(ProductFilterCriteria(ffo_concepts=("cotton",)), page_size=50)
    assert cotton_res.total_count == 29
    for c in cotton_res.items:
        assert "cotton" in c.ffo_canonical_ids

    # Filter for 'streetwear'
    streetwear_res = use_case(ProductFilterCriteria(ffo_concepts=("streetwear",)))
    assert streetwear_res.total_count > 0
    for c in streetwear_res.items:
        assert "streetwear" in c.ffo_canonical_ids

    # Filter for 'indian-fashion'
    culture_res = use_case(ProductFilterCriteria(ffo_concepts=("indian-fashion",)))
    assert culture_res.total_count > 0
    for c in culture_res.items:
        assert "indian-fashion" in c.ffo_canonical_ids


def test_malformed_queries_rejected_in_db_use_case(seeded_db) -> None:
    """Verify invalid parameters raise proper ValueError."""
    repo = DiscoveryRepositorySQL(seeded_db)
    use_case = RetrieveProductCandidates(repo)

    with pytest.raises(ValueError, match="min_price .* cannot exceed max_price"):
        use_case(ProductFilterCriteria(min_price=5000.0, max_price=1000.0))

    with pytest.raises(ValueError, match="page must be >= 1"):
        use_case(page=0)

    with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
        use_case(page_size=101)

    with pytest.raises(ValueError, match="Unsupported sort_order"):
        use_case(sort_order="unsupported_sort")
