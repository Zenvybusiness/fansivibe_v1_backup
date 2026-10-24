"""Tests for Grounded Discovery Explanation Engine (TASK DISCOVERY-05).

Covers:
- Product recommendation explanation formatting.
- Explicit preference matches translated to positive evidence.
- Missing preferences and unstated attributes handled neutrally without penalty or fabrication.
- Synthetic fixture products explicitly labeled and never described as retailer inventory.
- Complete looks explanation formatting across wardrobe-aware and catalog-only looks.
- Compatibility dimensions and warnings accurately captured.
- Trend explanation strictly preserving DEMAND_SIGNAL_AVAILABLE = False.
- Complete prohibition of fake popularity, trending claims, or viral demand signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pytest

from app.domain.ports.repositories import CatalogProductRecord, WardrobeItemRecord
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.domain.services.grounded_explanations import (
    EVIDENCE_TYPE_CATALOG,
    GroundedLookExplanation,
    GroundedProductExplanation,
    GroundedTrendExplanation,
    format_complete_look_explanation,
    format_product_recommendation_explanation,
    format_trend_candidate_explanation,
)
from app.domain.services.outfit_compatibility import (
    DEFAULT_OUTFIT_SLOTS,
    CompleteLook,
    LookItem,
    assemble_look_combinations,
    evaluate_look_compatibility,
)
from app.domain.services.personalization import (
    PersonalizationPreferences,
    PersonalizationScoreBreakdown,
    RankedCandidate,
    UserPersonalizationContext,
    WardrobeAffinityContext,
    score_product_candidate,
)
from app.domain.services.trends import (
    DEMAND_SIGNAL_AVAILABLE,
    REASON_NO_DEMAND,
    Signal,
    TrendCandidate,
)


def _make_candidate(
    *,
    title: str = "Classic Linen Shirt",
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
) -> tuple[CatalogProductRecord, RankedCandidate, UserPersonalizationContext]:
    prod = CatalogProductRecord(
        id=uuid4(),
        title=title,
        brand=brand,
        category=category,
        price=price,
        currency="INR",
        availability=availability,
        image_urls=("https://cdn.fansivibe.com/img.jpg",),
        attributes={
            "color": color,
            "material": material,
            "fit": fit,
            "silhouette": silhouette,
            "synthetic": is_synthetic,
            "fixture": is_fixture,
        },
        created_at=datetime.now(timezone.utc),
    )
    bridge = map_product_attributes_to_ffo(prod)
    prefs = PersonalizationPreferences(
        preferred_categories=(category,),
        preferred_brands=(brand,),
        preferred_colors=(color,),
        preferred_materials=(material,),
        max_price=3000.0,
    )
    context = UserPersonalizationContext(
        user_id=uuid4(),
        is_guest=False,
        preferences=prefs,
        wardrobe_context=WardrobeAffinityContext(has_wardrobe=False),
    )
    breakdown = score_product_candidate(prod, bridge, context)
    candidate = RankedCandidate(
        product=prod,
        ffo_bridge=bridge,
        score=breakdown.total_score,
        breakdown=breakdown,
        rank=1,
    )
    return prod, candidate, context


def test_product_explanation_grounded_in_verified_attributes() -> None:
    """Verify that explanation reasons and positive evidence derive strictly from verified matches."""
    prod, cand, ctx = _make_candidate(
        title="Linen Kurta",
        category="tops",
        brand="FabIndia",
        color="navy",
        material="linen",
    )
    expl = format_product_recommendation_explanation(cand, ctx)

    assert isinstance(expl, GroundedProductExplanation)
    assert "FabIndia" in expl.summary
    assert "tops" in expl.summary
    assert any("category 'tops'" in r for r in expl.positive_evidence)
    assert any("brand 'FabIndia'" in r for r in expl.positive_evidence)
    assert any("color 'navy'" in r for r in expl.positive_evidence)
    assert any("material 'linen'" in r for r in expl.positive_evidence)
    assert any("Verified price ₹2499" in r for r in expl.positive_evidence)
    assert expl.is_synthetic_fixture is True
    assert expl.provenance == "synthetic_fixture_catalog"


def test_product_explanation_neutral_dimensions_tracked() -> None:
    """Verify that unstated preferences/attributes are honestly reported in neutral_dimensions."""
    prod = CatalogProductRecord(
        id=uuid4(),
        title="Basic Tee",
        brand=None,
        category="tops",
        price=999.0,
        currency="INR",
        availability=True,
        image_urls=(),
        attributes={"synthetic": False, "fixture": False},
        created_at=datetime.now(timezone.utc),
    )
    bridge = map_product_attributes_to_ffo(prod)
    # Guest context with no preferences
    ctx = UserPersonalizationContext(user_id=None, is_guest=True)
    breakdown = score_product_candidate(prod, bridge, ctx)
    cand = RankedCandidate(
        product=prod,
        ffo_bridge=bridge,
        score=breakdown.total_score,
        breakdown=breakdown,
        rank=1,
    )

    expl = format_product_recommendation_explanation(cand, ctx)
    assert "category_preference" in expl.neutral_dimensions
    assert "brand_preference" in expl.neutral_dimensions
    assert "color_preference" in expl.neutral_dimensions
    assert "material_preference" in expl.neutral_dimensions
    assert expl.is_synthetic_fixture is False
    assert expl.provenance == "verified_catalog"
    assert "Catalog recommendation in tops with verified availability." == expl.summary


def test_product_explanation_prohibits_fake_popularity_and_retail_claims() -> None:
    """Verify that explanations never claim trending, viral, bestselling, or external retailer stock."""
    prod, cand, ctx = _make_candidate(is_synthetic=True, is_fixture=True)
    expl = format_product_recommendation_explanation(cand, ctx)

    # Convert entire explanation representation to lowercase text
    full_text = (
        f"{expl.summary} {' '.join(expl.reasons)} {' '.join(expl.positive_evidence)}"
    ).lower()

    banned_words = [
        "trending",
        "viral",
        "bestseller",
        "popular",
        "in high demand",
        "retailer inventory",
        "retail partner",
    ]
    for banned in banned_words:
        assert banned not in full_text, f"Found banned claim '{banned}' in explanation!"


def test_complete_look_explanation_catalog_only() -> None:
    """Verify complete look explanation formatting for a catalog-only outfit."""
    top = LookItem(
        item_id=uuid4(),
        source="catalog",
        title="Oxford Shirt",
        category="tops",
        color="white",
        material="cotton",
        price=2000.0,
    )
    bottom = LookItem(
        item_id=uuid4(),
        source="catalog",
        title="Chino Pants",
        category="bottoms",
        color="navy",
        material="cotton",
        price=3000.0,
    )
    slots = {"top": top, "bottom": bottom}
    breakdown = evaluate_look_compatibility(slots)
    look = CompleteLook(
        look_id="look_test123",
        slots=slots,
        total_catalog_price=5000.0,
        currency="INR",
        compatibility_score=breakdown.total_score,
        compatibility_breakdown=breakdown,
        compatibility_reasons=breakdown.reasons,
        unresolved_constraints=breakdown.warnings,
        is_wardrobe_aware=False,
        wardrobe_item_count=0,
        catalog_item_count=2,
        contains_synthetic_fixtures=False,
    )

    expl = format_complete_look_explanation(look)
    assert isinstance(expl, GroundedLookExplanation)
    assert expl.is_wardrobe_aware is False
    assert expl.is_synthetic_fixture is False
    assert "2-piece catalog ensemble" in expl.summary
    assert any("top and bottom foundation" in r for r in expl.positive_evidence)


def test_complete_look_explanation_wardrobe_aware() -> None:
    """Verify complete look explanation formatting for an outfit integrating owned wardrobe items."""
    owned_top = LookItem(
        item_id=uuid4(),
        source="wardrobe",
        title="Owned Cashmere Sweater",
        category="tops",
        color="charcoal",
        material="cashmere",
        price=0.0,
    )
    catalog_bottom = LookItem(
        item_id=uuid4(),
        source="catalog",
        title="Tailored Trousers",
        category="bottoms",
        color="black",
        material="wool",
        price=4500.0,
    )
    slots = {"top": owned_top, "bottom": catalog_bottom}
    breakdown = evaluate_look_compatibility(slots)
    look = CompleteLook(
        look_id="look_test456",
        slots=slots,
        total_catalog_price=4500.0,
        currency="INR",
        compatibility_score=breakdown.total_score,
        compatibility_breakdown=breakdown,
        compatibility_reasons=breakdown.reasons,
        unresolved_constraints=breakdown.warnings,
        is_wardrobe_aware=True,
        wardrobe_item_count=1,
        catalog_item_count=1,
        contains_synthetic_fixtures=False,
    )

    expl = format_complete_look_explanation(look)
    assert expl.is_wardrobe_aware is True
    assert "1 piece from your wardrobe with 1 catalog item" in expl.summary


def test_trend_candidate_explanation_preserves_no_demand() -> None:
    """Verify that trend explanations strictly report DEMAND_SIGNAL_AVAILABLE = False and catalog activity."""
    cand = TrendCandidate(
        concept="khadi-cotton",
        canonical_name="Khadi Cotton",
        category="tops",
        window_start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 10, 1, tzinfo=timezone.utc),
        observation_count=8,
        distinct_products=5,
        distinct_sources=2,
        first_observed_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        last_observed_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
        catalog_growth=0.25,
        price_change_ratio=None,
        in_stock_ratio=1.0,
        demand_signal_available=False,
        confidence=0.75,
        strength=0.25,
        stage="rising",
        is_fixture=False,
        publishable=False,
        reasons=(REASON_NO_DEMAND,),
        signals=(
            Signal(
                name="search_interest",
                kind="direct_demand",
                available=False,
                value=None,
                unit=None,
                detail=REASON_NO_DEMAND,
            ),
        ),
    )

    expl = format_trend_candidate_explanation(cand)
    assert isinstance(expl, GroundedTrendExplanation)
    assert expl.evidence_type == EVIDENCE_TYPE_CATALOG
    assert expl.demand_signal_available is False
    assert "Direct consumer demand signals are currently unavailable." in expl.summary
    assert REASON_NO_DEMAND in expl.reasons
