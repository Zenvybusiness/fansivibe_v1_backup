"""Unit tests for RetrieveProductCandidates application use case (TASK DISCOVERY-03).

Uses an in-memory repository fake to test:
- Application use case orchestration.
- Empty catalog handling.
- Empty result sets when filters match nothing.
- Bounded pagination and out-of-range pagination behavior.
- Next/previous cursor generation.
- Deterministic stable ordering across repeated calls.
- Hard filter validation error propagation.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductCandidateRepository,
    ProductFilterCriteria,
)
from app.domain.services.candidate_filters import filter_candidate
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo


class FakeProductCandidateRepository:
    """In-memory fake implementation of ProductCandidateRepository."""

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
        if sort_order == "price_asc":
            matched.sort(key=lambda p: (p.price if p.price is not None else float("inf"), str(p.id)))
        elif sort_order == "price_desc":
            matched.sort(key=lambda p: (-(p.price if p.price is not None else -1), str(p.id)))
        elif sort_order == "title_asc":
            matched.sort(key=lambda p: (p.title, str(p.id)))
        else:
            # newest default: sort by title/id for deterministic fake
            matched.sort(key=lambda p: str(p.id))
        return tuple(matched[offset : offset + limit])


def _make_product(
    title: str,
    category: str,
    price: float,
    *,
    material: str = "cotton",
    brand: str = "BrandA",
) -> CatalogProductRecord:
    return CatalogProductRecord(
        id=uuid4(),
        title=title,
        brand=brand,
        category=category,
        price=price,
        currency="INR",
        availability=True,
        attributes={"material": material, "synthetic": True, "fixture": True},
    )


def test_empty_catalog_retrieval() -> None:
    """Verify clean empty result from an empty catalog."""
    repo = FakeProductCandidateRepository([])
    use_case = RetrieveProductCandidates(repo)

    result = use_case(page=1, page_size=20)
    assert result.total_count == 0
    assert result.items == ()
    assert result.total_pages == 0
    assert result.has_next is False
    assert result.has_prev is False
    assert result.next_cursor is None
    assert result.prev_cursor is None


def test_empty_result_when_filters_exclude_all() -> None:
    """Verify empty result when filters match no products in catalog."""
    products = [
        _make_product("Tee 1", "tops", 999.0),
        _make_product("Jeans 1", "bottoms", 2999.0),
    ]
    repo = FakeProductCandidateRepository(products)
    use_case = RetrieveProductCandidates(repo)

    # Filter for non-existent category
    result = use_case(ProductFilterCriteria(categories=("outerwear",)))
    assert result.total_count == 0
    assert result.items == ()
    assert result.total_pages == 0


def test_out_of_range_pagination() -> None:
    """Verify out-of-range pagination produces an empty page with accurate total count."""
    products = [
        _make_product(f"Tee {i}", "tops", 1000.0 + i * 100)
        for i in range(5)
    ]
    repo = FakeProductCandidateRepository(products)
    use_case = RetrieveProductCandidates(repo)

    # Page 1: 5 items
    r1 = use_case(page=1, page_size=5)
    assert r1.total_count == 5
    assert len(r1.items) == 5
    assert r1.total_pages == 1
    assert r1.has_next is False
    assert r1.has_prev is False

    # Page 2: out of range (total is 5, page_size is 5)
    r2 = use_case(page=2, page_size=5)
    assert r2.total_count == 5
    assert r2.items == ()
    assert r2.total_pages == 1
    assert r2.has_next is False
    assert r2.has_prev is True
    assert r2.next_cursor is None


def test_cursor_pagination_indicators() -> None:
    """Verify next_cursor and prev_cursor are accurately generated across pages."""
    products = [
        _make_product(f"Tee {i}", "tops", 1000.0 + i)
        for i in range(7)
    ]
    repo = FakeProductCandidateRepository(products)
    use_case = RetrieveProductCandidates(repo)

    # Page 1 of 3 (page_size 3)
    p1 = use_case(page=1, page_size=3)
    assert len(p1.items) == 3
    assert p1.has_next is True
    assert p1.has_prev is False
    assert p1.next_cursor is not None
    assert p1.prev_cursor is None

    # Page 2 of 3
    p2 = use_case(page=2, page_size=3)
    assert len(p2.items) == 3
    assert p2.has_next is True
    assert p2.has_prev is True
    assert p2.next_cursor is not None
    assert p2.prev_cursor is not None

    # Page 3 of 3 (1 item remaining)
    p3 = use_case(page=3, page_size=3)
    assert len(p3.items) == 1
    assert p3.has_next is False
    assert p3.has_prev is True
    assert p3.next_cursor is None
    assert p3.prev_cursor is not None


def test_stable_deterministic_ordering_repeated_calls() -> None:
    """Verify repeated retrieval with unchanged catalog and filters returns identical ordered IDs."""
    products = [
        _make_product(f"Product {i}", "tops", 2000.0 - i * 50)
        for i in range(15)
    ]
    repo = FakeProductCandidateRepository(products)
    use_case = RetrieveProductCandidates(repo)

    r1 = use_case(sort_order="price_asc", page=1, page_size=10)
    r2 = use_case(sort_order="price_asc", page=1, page_size=10)

    ids1 = [c.id for c in r1.items]
    ids2 = [c.id for c in r2.items]
    assert ids1 == ids2
    assert len(ids1) == 10


def test_invalid_parameters_raise_validation_errors() -> None:
    """Verify that validation errors from candidate_filters are properly raised."""
    repo = FakeProductCandidateRepository([])
    use_case = RetrieveProductCandidates(repo)

    with pytest.raises(ValueError, match="page must be >= 1"):
        use_case(page=0)

    with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
        use_case(page_size=200)

    with pytest.raises(ValueError, match="Unsupported sort_order"):
        use_case(sort_order="nonexistent_sort")

    with pytest.raises(ValueError, match="min_price .* cannot exceed max_price"):
        use_case(ProductFilterCriteria(min_price=1000.0, max_price=500.0))
