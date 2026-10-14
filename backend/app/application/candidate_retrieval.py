"""Shared candidate retrieval application use case for Fansivibe Discovery (DISCOVERY-03).

Provides deterministic product candidate generation, combining repository retrieval with
hard filtering, FFO concept bridging, and bounded pagination.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductCandidateRepository,
    ProductFilterCriteria,
)
from app.domain.services.candidate_filters import (
    decode_product_cursor,
    encode_product_cursor,
    filter_candidate,
    validate_criteria,
    validate_pagination,
    validate_sort_order,
)
from app.domain.services.ffo_bridge import (
    FfoConceptMapping,
    ProductFfoBridgeResult,
    map_product_attributes_to_ffo,
)


@dataclass(frozen=True)
class ProductCandidate:
    """A catalog product candidate enriched with verified FFO concept mappings."""

    product: CatalogProductRecord
    ffo_bridge: ProductFfoBridgeResult

    @property
    def id(self) -> UUID:
        return self.product.id

    @property
    def title(self) -> str:
        return self.product.title

    @property
    def brand(self) -> Optional[str]:
        return self.product.brand

    @property
    def category(self) -> Optional[str]:
        return self.product.category

    @property
    def subcategory(self) -> Optional[str]:
        return self.product.subcategory

    @property
    def price(self) -> Optional[float]:
        return self.product.price

    @property
    def currency(self) -> Optional[str]:
        return self.product.currency

    @property
    def availability(self) -> Optional[bool]:
        return self.product.availability

    @property
    def image_urls(self) -> tuple[str, ...]:
        return self.product.image_urls

    @property
    def is_synthetic(self) -> bool:
        return self.product.is_synthetic

    @property
    def is_fixture(self) -> bool:
        return self.product.is_fixture

    @property
    def ffo_canonical_ids(self) -> set[str]:
        return self.ffo_bridge.canonical_ids

    @property
    def ffo_concepts(self) -> tuple[FfoConceptMapping, ...]:
        return self.ffo_bridge.concepts

    @property
    def unmapped_attributes(self) -> dict[str, Any]:
        return self.ffo_bridge.unmapped_attributes


@dataclass(frozen=True)
class CandidateRetrievalResult:
    """Paginated result of candidate retrieval."""

    items: tuple[ProductCandidate, ...]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    applied_criteria: ProductFilterCriteria = field(default_factory=ProductFilterCriteria)


def _extract_sort_value(product: CatalogProductRecord, sort_order: str) -> Any:
    """Extract the primary sort value from a product record for cursor encoding."""
    sort = sort_order.lower().strip()
    if sort in ("newest", "created_at_desc", "oldest", "created_at_asc"):
        return product.created_at.isoformat() if product.created_at else ""
    if sort in ("price_asc", "price_desc"):
        return str(product.price) if product.price is not None else ""
    if sort == "title_asc":
        return product.title
    return str(product.id)


class RetrieveProductCandidates:
    """Reusable application use case for retrieving normalized catalog candidates.

    Orchestrates repository retrieval, deterministic hard filters, FFO concept
    bridging, and bounded pagination.
    """

    def __init__(self, repository: ProductCandidateRepository) -> None:
        self._repo = repository

    def __call__(
        self,
        criteria: Optional[ProductFilterCriteria] = None,
        *,
        sort_order: str = "newest",
        page: int = 1,
        page_size: int = 20,
        cursor: Optional[str] = None,
    ) -> CandidateRetrievalResult:
        criteria = criteria or ProductFilterCriteria()
        validate_criteria(criteria)
        validate_pagination(page, page_size)
        validate_sort_order(sort_order)

        # Handle cursor if supplied
        if cursor is not None:
            _sort_val, _cursor_id = decode_product_cursor(cursor)

        # When FFO concept filtering is requested, we apply bridge filtering across candidates
        if criteria.ffo_concepts:
            # Query base matching records (limit to 1000 for safe bounded memory)
            base_criteria = ProductFilterCriteria(
                categories=criteria.categories,
                exclude_categories=criteria.exclude_categories,
                subcategories=criteria.subcategories,
                exclude_subcategories=criteria.exclude_subcategories,
                brands=criteria.brands,
                exclude_brands=criteria.exclude_brands,
                min_price=criteria.min_price,
                max_price=criteria.max_price,
                currency=criteria.currency,
                materials=criteria.materials,
                colors=criteria.colors,
                fits=criteria.fits,
                silhouettes=criteria.silhouettes,
                in_stock_only=criteria.in_stock_only,
                include_synthetic=criteria.include_synthetic,
                has_price=criteria.has_price,
                has_images=criteria.has_images,
                ffo_concepts=None,
                q=criteria.q,
            )
            raw_products = self._repo.get_candidates(
                base_criteria, sort_order=sort_order, offset=0, limit=1000
            )

            # Bridge and filter
            matching_candidates: list[ProductCandidate] = []
            for p in raw_products:
                bridge = map_product_attributes_to_ffo(p)
                if filter_candidate(p, criteria, bridge_result=bridge):
                    matching_candidates.append(ProductCandidate(product=p, ffo_bridge=bridge))

            total_count = len(matching_candidates)
            offset = (page - 1) * page_size
            items_slice = tuple(matching_candidates[offset : offset + page_size])
        else:
            total_count = self._repo.count_candidates(criteria)
            offset = (page - 1) * page_size
            raw_products = self._repo.get_candidates(
                criteria, sort_order=sort_order, offset=offset, limit=page_size
            )
            items_slice = tuple(
                ProductCandidate(product=p, ffo_bridge=map_product_attributes_to_ffo(p))
                for p in raw_products
            )

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
        has_next = (page * page_size) < total_count
        has_prev = page > 1 and total_count > 0

        next_cursor = None
        prev_cursor = None
        if items_slice and has_next:
            last = items_slice[-1]
            val = _extract_sort_value(last.product, sort_order)
            next_cursor = encode_product_cursor(sort_value=val, product_id=last.id)

        if items_slice and has_prev:
            first = items_slice[0]
            val = _extract_sort_value(first.product, sort_order)
            prev_cursor = encode_product_cursor(sort_value=val, product_id=first.id)

        return CandidateRetrievalResult(
            items=items_slice,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            applied_criteria=criteria,
        )
