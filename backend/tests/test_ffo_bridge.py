"""Unit tests for the FFO Concept Bridge (TASK DISCOVERY-03).

Verifies:
- All bridge-mapped concepts strictly exist in the approved FFO corpus.
- Zero fabricated concepts.
- Material and textile mappings.
- Fit and silhouette mappings.
- Color mappings.
- Style tag aesthetic and culture mappings.
- Subcategory and iconic garment/footwear/accessory mappings.
- Provenance and rule version tracking.
- Honest handling of unmapped attributes and missing data.
- Input validation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.data.ffo.corpus import build_index, load_documents
from app.domain.ports.repositories import CatalogProductRecord
from app.domain.services.ffo_bridge import (
    FFO_BRIDGE_RULE_VERSION,
    VERIFIED_FFO_ALIASES,
    VERIFIED_FFO_TERMS,
    FfoConceptMapping,
    ProductFfoBridgeResult,
    map_product_attributes_to_ffo,
)


def test_corpus_verification_baseline() -> None:
    """Verify that the bridge loads the real FFO corpus and indexes known terms and aliases."""
    assert len(VERIFIED_FFO_TERMS) == 54
    assert len(VERIFIED_FFO_ALIASES) == 10

    # Key ontology terms must be present
    assert "cotton" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["cotton"] == "material"
    assert "denim" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["denim"] == "textile"
    assert "relaxed-fit" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["relaxed-fit"] == "fit"
    assert "oversized" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["oversized"] == "silhouette"
    assert "streetwear" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["streetwear"] == "aesthetic"
    assert "indian-fashion" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["indian-fashion"] == "culture"
    assert "trench-coat" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["trench-coat"] == "garment"
    assert "chelsea-boots" in VERIFIED_FFO_TERMS
    assert VERIFIED_FFO_TERMS["chelsea-boots"] == "footwear"


def test_material_and_textile_mappings() -> None:
    """Test deterministic mapping of raw materials to verified FFO materials and textiles."""
    # 1. Khadi cotton -> cotton (material)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "khadi_cotton"},
    })
    cids = res.canonical_ids
    assert "cotton" in cids
    mat_concepts = res.concepts_for_kind("material")
    assert len(mat_concepts) == 1
    assert mat_concepts[0].canonical_id == "cotton"
    assert mat_concepts[0].provenance == "rule:material_substring_khadi"
    assert mat_concepts[0].rule_version == FFO_BRIDGE_RULE_VERSION

    # 2. Raw selvedge denim -> denim (textile)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "raw_selvedge_denim"},
    })
    assert "denim" in res.canonical_ids
    assert res.concepts_for_kind("textile")[0].canonical_id == "denim"

    # 3. Pure organic linen -> linen (material)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "pure_organic_linen"},
    })
    assert "linen" in res.canonical_ids
    assert res.concepts_for_kind("material")[0].canonical_id == "linen"

    # 4. Cotton twill -> composite matches both cotton (material) and twill (textile)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "cotton_twill"},
    })
    assert "cotton" in res.canonical_ids
    assert "twill" in res.canonical_ids

    # 5. Full grain leather -> leather (material)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "full_grain_leather"},
    })
    assert "leather" in res.canonical_ids

    # 6. Mulberry silk -> silk (material)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "mulberry_silk"},
    })
    assert "silk" in res.canonical_ids

    # 7. Merino wool -> wool (material)
    res = map_product_attributes_to_ffo({
        "attributes": {"material": "merino_wool"},
    })
    assert "wool" in res.canonical_ids


def test_fit_and_silhouette_mappings() -> None:
    """Test deterministic fit and silhouette normalization."""
    # Fit: regular, relaxed, slim
    for raw, expected in (
        ("regular", "regular-fit"),
        ("regular_fit", "regular-fit"),
        ("relaxed", "relaxed-fit"),
        ("loose", "relaxed-fit"),
        ("slim", "slim-fit"),
        ("tailored", "slim-fit"),
    ):
        res = map_product_attributes_to_ffo({"attributes": {"fit": raw}})
        assert expected in res.canonical_ids
        fit_concepts = res.concepts_for_kind("fit")
        assert len(fit_concepts) == 1
        assert fit_concepts[0].canonical_id == expected
        assert fit_concepts[0].entity_kind == "fit"

    # Silhouette: oversized, tapered, cropped, relaxed, a-line
    for raw, expected in (
        ("oversized", "oversized"),
        ("boxy", "oversized"),
        ("tapered", "tapered"),
        ("cropped", "cropped"),
        ("relaxed", "relaxed"),
        ("a_line", "a-line"),
    ):
        res = map_product_attributes_to_ffo({"attributes": {"silhouette": raw}})
        assert expected in res.canonical_ids
        sil_concepts = res.concepts_for_kind("silhouette")
        assert len(sil_concepts) == 1
        assert sil_concepts[0].canonical_id == expected
        assert sil_concepts[0].entity_kind == "silhouette"


def test_color_mappings() -> None:
    """Test deterministic color mappings to the verified FFO color palette."""
    verified_colors = {"charcoal", "olive", "navy", "beige", "burgundy", "emerald"}

    # Exact colors
    for col in verified_colors:
        res = map_product_attributes_to_ffo({"attributes": {"color": col}})
        assert col in res.canonical_ids
        assert res.concepts_for_kind("color")[0].canonical_id == col

    # Aliases & variants
    res = map_product_attributes_to_ffo({"attributes": {"color": "charcoal_grey"}})
    assert "charcoal" in res.canonical_ids

    res = map_product_attributes_to_ffo({"attributes": {"color": "wine"}})
    assert "burgundy" in res.canonical_ids

    res = map_product_attributes_to_ffo({"attributes": {"color": "olive_green"}})
    assert "olive" in res.canonical_ids

    res = map_product_attributes_to_ffo({"attributes": {"color": "forest_green"}})
    assert "emerald" in res.canonical_ids


def test_style_tags_aesthetic_and_culture() -> None:
    """Test style tags mapped to FFO aesthetics and culture."""
    res = map_product_attributes_to_ffo({
        "attributes": {
            "style_tags": ["streetwear", "minimalist", "heritage_indian"],
        }
    })
    cids = res.canonical_ids
    assert "streetwear" in cids
    assert "minimalist" in cids
    assert "indian-fashion" in cids

    aesthetics = res.concepts_for_kind("aesthetic")
    assert {a.canonical_id for a in aesthetics} == {"streetwear", "minimalist"}

    cultures = res.concepts_for_kind("culture")
    assert {c.canonical_id for c in cultures} == {"indian-fashion"}


def test_subcategory_iconic_garments() -> None:
    """Test subcategories mapping to iconic FFO garments, footwear, and accessories."""
    res = map_product_attributes_to_ffo({
        "category": "outerwear",
        "subcategory": "trench_coat",
        "title": "Classic Trench Coat",
    })
    assert "trench-coat" in res.canonical_ids
    assert res.concepts_for_kind("garment")[0].canonical_id == "trench-coat"

    res = map_product_attributes_to_ffo({
        "category": "footwear",
        "subcategory": "chelsea_boots",
        "title": "Leather Chelsea Boots",
    })
    assert "chelsea-boots" in res.canonical_ids
    assert res.concepts_for_kind("footwear")[0].canonical_id == "chelsea-boots"

    res = map_product_attributes_to_ffo({
        "category": "accessories",
        "subcategory": "leather_belt",
        "title": "Full Grain Leather Belt",
    })
    assert "leather-belt" in res.canonical_ids
    assert res.concepts_for_kind("accessory")[0].canonical_id == "leather-belt"

    res = map_product_attributes_to_ffo({
        "category": "accessories",
        "subcategory": "canvas_tote",
        "title": "Everyday Canvas Tote",
    })
    assert "canvas-tote" in res.canonical_ids
    assert res.concepts_for_kind("bag")[0].canonical_id == "canvas-tote"


def test_pattern_mappings() -> None:
    """Test pattern mapping to verified FFO patterns."""
    for raw, expected in (
        ("floral", "floral"),
        ("plaid", "plaid"),
        ("polka_dot", "polka-dot"),
        ("striped", "stripe"),
    ):
        res = map_product_attributes_to_ffo({"attributes": {"pattern": raw}})
        assert expected in res.canonical_ids
        assert res.concepts_for_kind("pattern")[0].canonical_id == expected


def test_honest_handling_of_unmapped_attributes() -> None:
    """Ensure unmapped attributes are never fabricated and are preserved in unmapped_attributes."""
    res = map_product_attributes_to_ffo({
        "category": "tops",
        "subcategory": "kurta",
        "title": "Handloom Kurta",
        "attributes": {
            "material": "bamboo_fiber",
            "fit": "one_size",
            "silhouette": "mandarin_collar",
            "color": "ecru",
            "style_tags": ["casual", "resort_vibe"],
        },
    })
    # None of the above exist in FFO ontology
    assert res.is_empty is True
    assert len(res.concepts) == 0

    # Unmapped dictionary must contain all unmapped raw values honestly
    assert res.unmapped_attributes["material"] == "bamboo_fiber"
    assert res.unmapped_attributes["fit"] == "one_size"
    assert res.unmapped_attributes["silhouette"] == "mandarin_collar"
    assert res.unmapped_attributes["color"] == "ecru"
    assert res.unmapped_attributes["subcategory"] == "kurta"
    assert "casual" in res.unmapped_attributes["style_tags"]
    assert "resort_vibe" in res.unmapped_attributes["style_tags"]


def test_catalog_product_record_integration() -> None:
    """Test bridge execution directly on a domain CatalogProductRecord."""
    pid = uuid4()
    record = CatalogProductRecord(
        id=pid,
        title="[Seed] Handloom Khadi Cotton Short Kurta",
        brand="Indus Thread Co.",
        category="tops",
        subcategory="kurta",
        attributes={
            "material": "khadi_cotton",
            "fit": "relaxed",
            "silhouette": "short_kurta",
            "color": "ecru",
            "style_tags": ["heritage_indian", "casual"],
            "fixture": True,
            "synthetic": True,
        },
        price=1899.0,
        currency="INR",
        availability=True,
    )

    res = map_product_attributes_to_ffo(record)
    assert res.product_id == pid
    assert res.canonical_ids == {"cotton", "relaxed-fit", "indian-fashion"}
    assert res.unmapped_attributes["color"] == "ecru"
    assert res.unmapped_attributes["silhouette"] == "short_kurta"
    assert res.unmapped_attributes["subcategory"] == "kurta"
    assert res.unmapped_attributes["style_tags"] == ["casual"]


def test_invalid_input_type_rejected() -> None:
    """Verify non-record non-dict inputs raise TypeError."""
    with pytest.raises(TypeError, match="Expected CatalogProductRecord or dict"):
        map_product_attributes_to_ffo("invalid-string-input")  # type: ignore


def test_every_mapped_concept_exists_in_verified_corpus() -> None:
    """Exhaustive invariant test: every concept emitted by the bridge must exist in FFO corpus."""
    from app.infrastructure.external.fashion_catalog_seed import FASHION_SEED_RECORDS

    for record in FASHION_SEED_RECORDS:
        payload = record.payload if hasattr(record, "payload") else record
        res = map_product_attributes_to_ffo({
            "category": payload.get("category"),
            "subcategory": payload.get("subcategory"),
            "title": payload.get("title", ""),
            "attributes": payload.get("attributes", {}),
        })
        for concept in res.concepts:
            assert concept.canonical_id in VERIFIED_FFO_TERMS or concept.canonical_id in VERIFIED_FFO_ALIASES
            assert concept.entity_kind in (
                "material",
                "textile",
                "fit",
                "silhouette",
                "color",
                "aesthetic",
                "culture",
                "garment",
                "footwear",
                "accessory",
                "bag",
                "jewelry",
                "pattern",
            )
            assert concept.rule_version == FFO_BRIDGE_RULE_VERSION
            assert concept.provenance.startswith("rule:")
            assert 0.0 <= concept.confidence <= 1.0
