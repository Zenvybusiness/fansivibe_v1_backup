"""Candidate filtering, validation, and deterministic ordering policies (DISCOVERY-03).

Defines pure validation and deterministic filtering functions for catalog products.
Hard filters MUST be applied before any future personalization or ranking stage.
"""

from __future__ import annotations

import base64
from typing import Any, Optional
from uuid import UUID

from app.domain.ports.repositories import CatalogProductRecord, ProductFilterCriteria
from app.domain.services.ffo_bridge import ProductFfoBridgeResult

# Supported deterministic sort orders
VALID_SORT_ORDERS = frozenset({
    "newest",
    "oldest",
    "created_at_desc",
    "created_at_asc",
    "price_asc",
    "price_desc",
    "title_asc",
    "id_asc",
})

_PAGE_SIZE_MIN = 1
_PAGE_SIZE_MAX = 100


def validate_criteria(criteria: ProductFilterCriteria) -> None:
    """Validate filter criteria consistency and boundaries.

    Raises:
        ValueError: If prices are negative, bounds are inverted, or inclusions/exclusions overlap.
    """
    if criteria.min_price is not None and criteria.min_price < 0:
        raise ValueError("min_price must be non-negative")
    if criteria.max_price is not None and criteria.max_price < 0:
        raise ValueError("max_price must be non-negative")
    if (
        criteria.min_price is not None
        and criteria.max_price is not None
        and criteria.min_price > criteria.max_price
    ):
        raise ValueError(
            f"min_price ({criteria.min_price}) cannot exceed max_price ({criteria.max_price})"
        )

    # Check for overlapping inclusion and exclusion lists
    if criteria.categories and criteria.exclude_categories:
        inc = {c.lower().strip() for c in criteria.categories}
        exc = {c.lower().strip() for c in criteria.exclude_categories}
        overlap = inc & exc
        if overlap:
            raise ValueError(
                f"Categories cannot be both included and excluded: {sorted(overlap)}"
            )

    if criteria.subcategories and criteria.exclude_subcategories:
        inc = {s.lower().strip() for s in criteria.subcategories}
        exc = {s.lower().strip() for s in criteria.exclude_subcategories}
        overlap = inc & exc
        if overlap:
            raise ValueError(
                f"Subcategories cannot be both included and excluded: {sorted(overlap)}"
            )

    if criteria.brands and criteria.exclude_brands:
        inc = {b.lower().strip() for b in criteria.brands}
        exc = {b.lower().strip() for b in criteria.exclude_brands}
        overlap = inc & exc
        if overlap:
            raise ValueError(
                f"Brands cannot be both included and excluded: {sorted(overlap)}"
            )

    if criteria.q is not None and len(criteria.q) > 200:
        raise ValueError("q cannot exceed 200 characters")


def validate_pagination(page: int, page_size: int) -> None:
    """Validate page and page_size boundaries.

    Raises:
        ValueError: If page < 1 or page_size not in [1, 100].
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if not (_PAGE_SIZE_MIN <= page_size <= _PAGE_SIZE_MAX):
        raise ValueError(
            f"page_size must be between {_PAGE_SIZE_MIN} and {_PAGE_SIZE_MAX}"
        )


def validate_sort_order(sort_order: str) -> None:
    """Validate sort order identifier.

    Raises:
        ValueError: If sort_order is unrecognized.
    """
    if sort_order not in VALID_SORT_ORDERS:
        raise ValueError(
            f"Unsupported sort_order '{sort_order}'. Allowed: {sorted(VALID_SORT_ORDERS)}"
        )


def filter_candidate(
    product: CatalogProductRecord,
    criteria: ProductFilterCriteria,
    bridge_result: Optional[ProductFfoBridgeResult] = None,
) -> bool:
    """Apply hard filters to a candidate product deterministically in-memory.

    Returns:
        bool: True if the product satisfies all hard filter criteria, False otherwise.
    """
    # 1. Synthetic fixture filter
    if not criteria.include_synthetic and (product.is_synthetic or product.is_fixture):
        return False

    # 2. Category inclusion / exclusion
    cat = (product.category or "").lower().strip()
    if criteria.categories:
        inc_cats = {c.lower().strip() for c in criteria.categories}
        if cat not in inc_cats:
            return False
    if criteria.exclude_categories:
        exc_cats = {c.lower().strip() for c in criteria.exclude_categories}
        if cat in exc_cats:
            return False

    # 3. Subcategory inclusion / exclusion
    sub = (product.subcategory or "").lower().strip()
    if criteria.subcategories:
        inc_subs = {s.lower().strip() for s in criteria.subcategories}
        if sub not in inc_subs:
            return False
    if criteria.exclude_subcategories:
        exc_subs = {s.lower().strip() for s in criteria.exclude_subcategories}
        if sub in exc_subs:
            return False

    # 4. Brand inclusion / exclusion
    brand = (product.brand or "").lower().strip()
    if criteria.brands:
        inc_brands = {b.lower().strip() for b in criteria.brands}
        if brand not in inc_brands:
            return False
    if criteria.exclude_brands:
        exc_brands = {b.lower().strip() for b in criteria.exclude_brands}
        if brand in exc_brands:
            return False

    # 5. Price bounds
    if criteria.has_price is True and product.price is None:
        return False
    if criteria.has_price is False and product.price is not None:
        return False

    if criteria.min_price is not None:
        if product.price is None or product.price < criteria.min_price:
            return False
    if criteria.max_price is not None:
        if product.price is None or product.price > criteria.max_price:
            return False

    # 6. Currency match
    if criteria.currency is not None:
        curr = (product.currency or "").strip().upper()
        if curr != criteria.currency.strip().upper():
            return False

    # 7. Images requirement
    if criteria.has_images is True and not product.image_urls:
        return False
    if criteria.has_images is False and product.image_urls:
        return False

    # 8. Availability (trustworthy stock only)
    if criteria.in_stock_only is True:
        if product.availability is not True:
            return False
    elif criteria.in_stock_only is False:
        if product.availability is not False:
            return False

    # 9. Attribute filters (materials, colors, fits, silhouettes)
    if criteria.materials:
        p_mat = (product.material or "").lower().strip()
        wanted_mats = {m.lower().strip() for m in criteria.materials}
        # Check either exact match or substring in raw material
        if not any(m in p_mat for m in wanted_mats):
            return False

    if criteria.colors:
        p_col = (product.color or "").lower().strip()
        wanted_cols = {c.lower().strip() for c in criteria.colors}
        if not any(c in p_col for c in wanted_cols):
            return False

    if criteria.fits:
        p_fit = (product.fit or "").lower().strip()
        wanted_fits = {f.lower().strip() for f in criteria.fits}
        if not any(f in p_fit for f in wanted_fits):
            return False

    if criteria.silhouettes:
        p_sil = (product.silhouette or "").lower().strip()
        wanted_sils = {s.lower().strip() for s in criteria.silhouettes}
        if not any(s in p_sil for s in wanted_sils):
            return False

    # 10. FFO Concepts
    if criteria.ffo_concepts:
        if not bridge_result:
            return False
        product_cids = bridge_result.canonical_ids
        wanted_cids = {cid.strip().lower() for cid in criteria.ffo_concepts}
        # Requires at least one matching concept
        if not (product_cids & wanted_cids):
            return False

    # 11. Text search query across title, brand, category, subcategory
    if criteria.q:
        q_clean = criteria.q.strip().lower()
        if q_clean:
            matches_q = (
                q_clean in (product.title or "").lower()
                or q_clean in (product.brand or "").lower()
                or q_clean in (product.category or "").lower()
                or q_clean in (product.subcategory or "").lower()
            )
            if not matches_q:
                return False

    return True


# ---------------------------------------------------------------------------
# Cursors for Deterministic Pagination
# ---------------------------------------------------------------------------


def encode_product_cursor(*, sort_value: Any, product_id: UUID) -> str:
    """Encode an opaque, stable cursor from a sort key and product UUID."""
    val_str = str(sort_value) if sort_value is not None else ""
    raw = f"{val_str}:{product_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_product_cursor(cursor: str) -> tuple[str, UUID]:
    """Decode an opaque cursor to sort value and product UUID.

    Raises:
        ValueError: If the cursor is malformed or invalid.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError("cursor is malformed or invalid") from exc

    val_str, sep, id_str = raw.partition(":")
    if not sep or not id_str:
        raise ValueError("cursor is malformed or invalid")
    try:
        product_id = UUID(id_str)
    except ValueError as exc:
        raise ValueError("cursor contains an invalid UUID") from exc

    return val_str, product_id
