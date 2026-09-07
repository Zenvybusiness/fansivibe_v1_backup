"""Focused unit tests for the Clothing Intelligence engine (CL-0).

Tests deterministic rules only — no AI, no DB, no Flask.
Mirrors the test patterns from grooming_engine tests.
"""

from __future__ import annotations

import pytest

from app.domain.value_objects import (
    ClothingIntelligence,
    WardrobeContext,
    ColorCharacteristics,
    MaterialCharacteristics,
    SeasonSuitability,
    Formality,
    StylingExplanation,
    CompatibleCategory,
    OccasionContext,
)


# ---------------------------------------------------------------------------


def test_compute_clothing_intelligence_full():
    """Test with fully populated item and user context."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    result = compute_clothing_intelligence(
        item_category="tops",
        item_color="charcoal",
        item_material="wool",
        item_is_favorite=True,
        wardrobe_context=WardrobeContext(
            total_items=24,
            favorite_count=8,
            items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=87,
        ),
        preferred_occasions=["date", "office", "travel"],
    )

    # Verify types
    assert isinstance(result, ClothingIntelligence)
    assert result.confidence > 0.5  # full data → high confidence
    assert result.item_category == "tops"
    assert result.item_color == "charcoal"
    assert result.item_is_favorite is True
    assert result.wardrobe_context.total_items == 24
    assert result.color_characteristics.is_neutral is True  # charcoal is neutral
    assert result.material_characteristics.is_natural is True  # wool is natural
    assert isinstance(result.season_suitability, SeasonSuitability)
    assert isinstance(result.formality, Formality)
    assert len(result.compatible_categories) > 0
    assert len(result.suitable_occasions) > 0
    assert len(result.explanation.text) > 0


def test_compute_clothing_intelligence_missing_material():
    """Test with missing material (common case)."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    result = compute_clothing_intelligence(
        item_category="tops",
        item_color="navy",
        item_material=None,
        item_is_favorite=False,
        wardrobe_context=WardrobeContext(
            total_items=28,
            favorite_count=6,
            items_per_category={"tops": 9, "bottoms": 6, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=91,
        ),
        preferred_occasions=["travel"],
    )

    # Verify types
    assert isinstance(result, ClothingIntelligence)
    assert 0.3 < result.confidence < 0.6  # missing material → medium confidence
    assert result.material_characteristics.material == "unknown"
    assert result.material_characteristics.is_natural is False
    assert result.material_characteristics.is_seasonal is False
    # Explanation should note material is unspecified
    assert "material" in result.explanation.text.lower()


def test_compute_clothing_intelligence_favorite_item():
    """Test favorite item produces valid result."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    result = compute_clothing_intelligence(
        item_category="outerwear",
        item_color="black",
        item_material="leather",
        item_is_favorite=True,
        wardrobe_context=WardrobeContext(
            total_items=24,
            favorite_count=8,
            items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=87,
        ),
        preferred_occasions=["party", "date"],
    )

    assert isinstance(result, ClothingIntelligence)
    assert result.item_is_favorite is True
    assert result.confidence > 0.5
    assert len(result.explanation.text) > 0


def test_compute_clothing_intelligence_seasonal_material():
    """Test seasonal material produces appropriate season suitability."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    result = compute_clothing_intelligence(
        item_category="bottoms",
        item_color="beige",
        item_material="linen",
        item_is_favorite=False,
        wardrobe_context=WardrobeContext(
            total_items=30,
            favorite_count=5,
            items_per_category={"tops": 10, "bottoms": 7, "outerwear": 5, "footwear": 5, "accessories": 4},
            style_score=89,
        ),
        preferred_occasions=["travel", "casual"],
    )

    assert isinstance(result, ClothingIntelligence)
    # Linen should be marked seasonal
    assert result.material_characteristics.is_seasonal is True
    # Linen is summer-weighted
    assert result.season_suitability.suitable_for_summer is True
    # Should have some occasion matches
    assert len(result.suitable_occasions) > 0


def test_compute_clothing_intelligence_unknown_category():
    """Test edge case with unrecognized category."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    result = compute_clothing_intelligence(
        item_category="unknown",
        item_color="",
        item_material=None,
        item_is_favorite=False,
        wardrobe_context=WardrobeContext(
            total_items=24,
            favorite_count=8,
            items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=87,
        ),
        preferred_occasions=[],
    )

    assert isinstance(result, ClothingIntelligence)
    # Low confidence for unknown category
    assert result.confidence < 0.5
    # Explanation should have content
    assert len(result.explanation.text) > 0


def test_clothing_intelligence_deterministic_repeatability():
    """Test that same inputs produce same outputs (deterministic)."""
    from app.domain.services.analysis_rules import compute_clothing_intelligence

    # Same inputs twice
    result1 = compute_clothing_intelligence(
        item_category="tops",
        item_color="charcoal",
        item_material="wool",
        item_is_favorite=True,
        wardrobe_context=WardrobeContext(
            total_items=24,
            favorite_count=8,
            items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=87,
        ),
        preferred_occasions=["date", "office"],
    )

    result2 = compute_clothing_intelligence(
        item_category="tops",
        item_color="charcoal",
        item_material="wool",
        item_is_favorite=True,
        wardrobe_context=WardrobeContext(
            total_items=24,
            favorite_count=8,
            items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
            style_score=87,
        ),
        preferred_occasions=["date", "office"],
    )

    # Deterministic: same inputs → same confidence
    assert result1.confidence == result2.confidence
    # Both should have key content
    assert "charcoal" in result1.explanation.text
    assert "charcoal" in result2.explanation.text
    assert "tops" in result1.explanation.text
    assert "tops" in result2.explanation.text


def test_color_characteristics_neutral():
    """Test neutral color classification."""
    from app.domain.value_objects import ColorCharacteristics

    # Neutral colors
    assert ColorCharacteristics(item_color="black", is_neutral=True).is_neutral is True
    assert ColorCharacteristics(item_color="white", is_neutral=True).is_neutral is True
    assert ColorCharacteristics(item_color="charcoal", is_neutral=True).is_neutral is True
    assert ColorCharacteristics(item_color="grey", is_neutral=True).is_neutral is True

    # Non-neutral colors
    assert ColorCharacteristics(item_color="navy", is_neutral=False).is_neutral is False
    assert ColorCharacteristics(item_color="beige", is_neutral=False).is_neutral is False
    assert ColorCharacteristics(item_color="burgundy", is_neutral=False).is_neutral is False


def test_material_characteristics_natural():
    """Test natural material classification."""
    from app.domain.value_objects import MaterialCharacteristics

    # Natural materials
    assert MaterialCharacteristics(material="cotton", is_natural=True).is_natural is True
    assert MaterialCharacteristics(material="linen", is_natural=True).is_natural is True
    assert MaterialCharacteristics(material="wool", is_natural=True).is_natural is True
    assert MaterialCharacteristics(material="silk", is_natural=True).is_natural is True
    assert MaterialCharacteristics(material="leather", is_natural=True).is_natural is True

    # Non-natural/synthetic
    assert MaterialCharacteristics(material="polyester", is_natural=False).is_natural is False
    assert MaterialCharacteristics(material="unknown", is_natural=False).is_natural is False


def test_season_suitability_creation():
    """Test SeasonSuitability can be created and checked."""
    from app.domain.value_objects import SeasonSuitability

    ss = SeasonSuitability(
        suitable_for_spring=True,
        suitable_for_summer=False,
        suitable_for_fall=True,
        suitable_for_winter=False,
        rationale="Spring and fall appropriate",
    )

    assert ss.suitable_for_spring is True
    assert ss.suitable_for_summer is False
    assert ss.suitable_for_fall is True
    assert ss.suitable_for_winter is False
    assert ss.rationale == "Spring and fall appropriate"


def test_formality_creation():
    """Test Formality can be created and checked."""
    from app.domain.value_objects import Formality

    formal = Formality(is_formal=True, is_casual=False, is_business=True, rationale="Formal business attire")
    casual = Formality(is_formal=False, is_casual=True, is_business=False, rationale="Casual attire")

    assert formal.is_formal is True
    assert formal.is_casual is False
    assert formal.is_business is True

    assert casual.is_formal is False
    assert casual.is_casual is True
    assert casual.is_business is False


def test_occasion_context_creation():
    """Test OccasionContext creation and confidence."""
    from app.domain.value_objects import OccasionContext

    # High confidence
    oc1 = OccasionContext(occasion="date", confidence=0.8, rationale="Strong match")
    assert oc1.confidence == 0.8
    assert oc1.occasion == "date"

    # Low confidence
    oc2 = OccasionContext(occasion="travel", confidence=0.3, rationale="Weak match")
    assert oc2.confidence == 0.3
    assert oc2.occasion == "travel"


def test_compatible_category_creation():
    """Test CompatibleCategory creation."""
    from app.domain.value_objects import CompatibleCategory

    cc = CompatibleCategory(category="bottoms", rationale="Pairs well with tops for outfits")
    assert cc.category == "bottoms"
    assert "Pairs well" in cc.rationale


def test_wardrobe_context_creation():
    """Test WardrobeContext creation and usage."""
    from app.domain.value_objects import WardrobeContext

    wc = WardrobeContext(
        total_items=24,
        favorite_count=8,
        items_per_category={"tops": 8, "bottoms": 5, "outerwear": 4, "footwear": 4, "accessories": 3},
        style_score=87,
    )

    assert wc.total_items == 24
    assert wc.favorite_count == 8
    assert wc.items_per_category["tops"] == 8
    assert wc.style_score == 87


def test_styling_explanation_creation():
    """Test StylingExplanation creation."""
    from app.domain.value_objects import StylingExplanation

    se = StylingExplanation(text="Your charcoal top is a favorite piece suitable for casual occasions.")
    assert len(se.text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
