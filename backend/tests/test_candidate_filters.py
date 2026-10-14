"""Unit tests for candidate filtering, validation, and cursor policies (TASK DISCOVERY-03).

Verifies:
- Hard filter boundaries and validation rules.
- Overlap detection for include/exclude sets.
- Pagination bounds enforcement (1 <= page_size <= 100, page >= 1).
- Deterministic sort order validation.
- Cursor encoding and decoding round-trip and error handling.
- Deterministic in-memory candidate filtering.
"""

from __future__ import annotations

import base64
from uuid import uuid4

import pytest

from app.domain.ports.repositories import CatalogProductRecord, ProductFilterCriteria
from app.domain.services.candidate_filters import (
    VALID_SORT_ORDERS,
    decode_product_cursor,
    encode_product_cursor,
    filter_candidate,
    validate_criteria,
    validate_pagination,
    validate_sort_order,
)
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo


def _sample_product(
    *,
    id=None,
    title="Cotton Tee",
    brand="Atelier Nord",
    category="tops",
    subcategory="t-shirt",
    price=1299.0,
    currency="INR",
    availability=True,
    is_synthetic=True,
    is_fixture=True,
    material="french_terry_cotton",
    color="washed_black",
    fit="oversized",
    silhouette="boxy",
    image_urls=("https://cdn.example.com/tee.jpg",),
) -> CatalogProductRecord:
    return CatalogProductRecord(
        id=id or uuid4(),
        title=title,
        brand=brand,
        category=category,
        subcategory=subcategory,
        price=price,
        currency=currency,
        availability=availability,
        image_urls=image_urls,
        attributes={
            "material": material,
            "color": color,
            "fit": fit,
            "silhouette": silhouette,
            "synthetic": is_synthetic,
            "fixture": is_fixture,
        },
    )


def test_validate_criteria_price_boundaries() -> None:
    """Verify price boundary validation."""
    # Negative min_price
    with pytest.raises(ValueError, match="min_price must be non-negative"):
        validate_criteria(ProductFilterCriteria(min_price=-10.0))

    # Negative max_price
    with pytest.raises(ValueError, match="max_price must be non-negative"):
        validate_criteria(ProductFilterCriteria(max_price=-1.0))

    # Inverted boundaries
    with pytest.raises(ValueError, match="min_price .* cannot exceed max_price"):
        validate_criteria(ProductFilterCriteria(min_price=5000.0, max_price=1000.0))

    # Equal boundaries are valid (exact price point)
    validate_criteria(ProductFilterCriteria(min_price=2000.0, max_price=2000.0))

    # Valid range
    validate_criteria(ProductFilterCriteria(min_price=1000.0, max_price=5000.0))


def test_validate_criteria_overlapping_sets() -> None:
    """Verify overlapping inclusion and exclusion lists are rejected."""
    # Categories overlap
    with pytest.raises(ValueError, match="Categories cannot be both included and excluded"):
        validate_criteria(
            ProductFilterCriteria(
                categories=("tops", "bottoms"),
                exclude_categories=("Tops", "footwear"),
            )
        )

    # Subcategories overlap
    with pytest.raises(ValueError, match="Subcategories cannot be both included and excluded"):
        validate_criteria(
            ProductFilterCriteria(
                subcategories=("shirt", "kurta"),
                exclude_subcategories=("SHIRT",),
            )
        )

    # Brands overlap
    with pytest.raises(ValueError, match="Brands cannot be both included and excluded"):
        validate_criteria(
            ProductFilterCriteria(
                brands=("Atelier Nord", "Indus Thread Co."),
                exclude_brands=("atelier nord",),
            )
        )


def test_validate_pagination_bounds() -> None:
    """Verify page and page_size bounds."""
    # page < 1
    with pytest.raises(ValueError, match="page must be >= 1"):
        validate_pagination(page=0, page_size=20)
    with pytest.raises(ValueError, match="page must be >= 1"):
        validate_pagination(page=-5, page_size=20)

    # page_size < 1
    with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
        validate_pagination(page=1, page_size=0)

    # page_size > 100
    with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
        validate_pagination(page=1, page_size=101)

    # Valid boundaries
    validate_pagination(page=1, page_size=1)
    validate_pagination(page=1, page_size=100)
    validate_pagination(page=50, page_size=20)


def test_validate_sort_orders() -> None:
    """Verify sort order validation."""
    for valid_order in VALID_SORT_ORDERS:
        validate_sort_order(valid_order)

    with pytest.raises(ValueError, match="Unsupported sort_order"):
        validate_sort_order("random_unsupported_sort")


def test_cursor_round_trip_and_errors() -> None:
    """Verify opaque cursor encoding and decoding."""
    pid = uuid4()
    cursor = encode_product_cursor(sort_value=2499.0, product_id=pid)
    assert isinstance(cursor, str)
    assert len(cursor) > 0

    val_str, decoded_id = decode_product_cursor(cursor)
    assert val_str == "2499.0"
    assert decoded_id == pid

    # Malformed base64
    with pytest.raises(ValueError, match="cursor is malformed or invalid"):
        decode_product_cursor("not-valid-base64!@#$")

    # Missing separator
    with pytest.raises(ValueError, match="cursor is malformed or invalid"):
        decode_product_cursor("bm9zZXBhcmF0b3I=")

    # Invalid UUID
    with pytest.raises(ValueError, match="cursor contains an invalid UUID"):
        decode_product_cursor(base64.urlsafe_b64encode(b"test:not-a-uuid").decode("ascii"))


def test_filter_candidate_category_inclusion_exclusion() -> None:
    """Test category inclusion and exclusion."""
    p = _sample_product(category="tops")

    # Included
    assert filter_candidate(p, ProductFilterCriteria(categories=("tops", "bottoms"))) is True
    # Not included
    assert filter_candidate(p, ProductFilterCriteria(categories=("bottoms", "footwear"))) is False
    # Excluded
    assert filter_candidate(p, ProductFilterCriteria(exclude_categories=("tops",))) is False
    # Not excluded
    assert filter_candidate(p, ProductFilterCriteria(exclude_categories=("footwear",))) is True


def test_filter_candidate_brand_and_price() -> None:
    """Test brand and price boundary filtering."""
    p = _sample_product(brand="Atelier Nord", price=2500.0)

    # Brand match
    assert filter_candidate(p, ProductFilterCriteria(brands=("Atelier Nord",))) is True
    assert filter_candidate(p, ProductFilterCriteria(brands=("Indus Thread Co.",))) is False
    assert filter_candidate(p, ProductFilterCriteria(exclude_brands=("Atelier Nord",))) is False

    # Price match
    assert filter_candidate(p, ProductFilterCriteria(min_price=2000.0, max_price=3000.0)) is True
    assert filter_candidate(p, ProductFilterCriteria(min_price=3000.0)) is False
    assert filter_candidate(p, ProductFilterCriteria(max_price=2000.0)) is False

    # Missing price product
    no_price_p = _sample_product(price=None)
    assert filter_candidate(no_price_p, ProductFilterCriteria(has_price=True)) is False
    assert filter_candidate(no_price_p, ProductFilterCriteria(has_price=False)) is True
    assert filter_candidate(no_price_p, ProductFilterCriteria(min_price=100.0)) is False


def test_filter_candidate_stock_availability() -> None:
    """Test trustworthy availability filtering."""
    in_stock = _sample_product(availability=True)
    out_stock = _sample_product(availability=False)
    unverified = _sample_product(availability=None)

    # in_stock_only = True
    assert filter_candidate(in_stock, ProductFilterCriteria(in_stock_only=True)) is True
    assert filter_candidate(out_stock, ProductFilterCriteria(in_stock_only=True)) is False
    assert filter_candidate(unverified, ProductFilterCriteria(in_stock_only=True)) is False

    # in_stock_only = False
    assert filter_candidate(in_stock, ProductFilterCriteria(in_stock_only=False)) is False
    assert filter_candidate(out_stock, ProductFilterCriteria(in_stock_only=False)) is True
    assert filter_candidate(unverified, ProductFilterCriteria(in_stock_only=False)) is False

    # in_stock_only = None (accepts all)
    assert filter_candidate(in_stock, ProductFilterCriteria(in_stock_only=None)) is True
    assert filter_candidate(out_stock, ProductFilterCriteria(in_stock_only=None)) is True
    assert filter_candidate(unverified, ProductFilterCriteria(in_stock_only=None)) is True


def test_filter_candidate_synthetic_fixture_isolation() -> None:
    """Test synthetic fixture identification and exclusion."""
    synth_p = _sample_product(is_synthetic=True, is_fixture=True)
    real_p = _sample_product(is_synthetic=False, is_fixture=False)

    # include_synthetic = True
    assert filter_candidate(synth_p, ProductFilterCriteria(include_synthetic=True)) is True
    assert filter_candidate(real_p, ProductFilterCriteria(include_synthetic=True)) is True

    # include_synthetic = False
    assert filter_candidate(synth_p, ProductFilterCriteria(include_synthetic=False)) is False
    assert filter_candidate(real_p, ProductFilterCriteria(include_synthetic=False)) is True


def test_filter_candidate_ffo_concepts() -> None:
    """Test candidate filtering by mapped FFO concept canonical IDs."""
    p = _sample_product(material="khadi_cotton")
    bridge = map_product_attributes_to_ffo(p)
    assert "cotton" in bridge.canonical_ids

    # Matches cotton
    assert filter_candidate(p, ProductFilterCriteria(ffo_concepts=("cotton",)), bridge_result=bridge) is True

    # Does not match silk
    assert filter_candidate(p, ProductFilterCriteria(ffo_concepts=("silk",)), bridge_result=bridge) is False

    # Missing bridge result returns False when ffo_concepts are required
    assert filter_candidate(p, ProductFilterCriteria(ffo_concepts=("cotton",)), bridge_result=None) is False
