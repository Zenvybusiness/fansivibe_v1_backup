"""FFO concept bridge — deterministic mapping from normalized product attributes to verified FFO concepts (DISCOVERY-03).

Bridges commercial catalog products to the verified FFO knowledge ontology.
Pure Python, deterministic, offline, zero LLM calls.

Invariants:
- References ONLY concepts that actually exist in the approved FFO corpus.
- Preserves the distinction between raw product attributes and inferred fashion concepts.
- Records mapping provenance and mapping-rule version (ffo_bridge_v1).
- Represents unknown or unmapped attributes honestly without fabrication.
- Zero modifications to the frozen FFO corpus or reasoning contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from app.data.ffo.corpus import build_index, load_documents
from app.domain.ports.repositories import CatalogProductRecord

# Rule version for tracking mapping provenance
FFO_BRIDGE_RULE_VERSION = "ffo_bridge_v1"

# Load and index the verified FFO corpus once at import
_CORPUS_DOCS = load_documents()
_CORPUS_INDEX = build_index(_CORPUS_DOCS)

# Verified terms: canonical_id -> entity_kind
VERIFIED_FFO_TERMS: dict[str, str] = {
    canonical_id: doc.get("entity_kind", "")
    for (doc_type, canonical_id), doc in _CORPUS_INDEX["by_canonical"].items()
    if doc_type == "term"
}

# Verified aliases: alias -> canonical_id
VERIFIED_FFO_ALIASES: dict[str, str] = dict(_CORPUS_INDEX["aliases"])


@dataclass(frozen=True)
class FfoConceptMapping:
    """One deterministic mapping from a product attribute to a verified FFO concept."""

    attribute_field: str
    raw_value: str
    canonical_id: str
    entity_kind: str
    confidence: float
    rule_version: str = FFO_BRIDGE_RULE_VERSION
    provenance: str = "rule:deterministic_mapping"


@dataclass(frozen=True)
class ProductFfoBridgeResult:
    """Complete FFO concept mapping result for one product."""

    product_id: Optional[UUID]
    concepts: tuple[FfoConceptMapping, ...]
    unmapped_attributes: dict[str, Any] = field(default_factory=dict)
    rule_version: str = FFO_BRIDGE_RULE_VERSION

    @property
    def canonical_ids(self) -> set[str]:
        return {c.canonical_id for c in self.concepts}

    def concepts_for_kind(self, entity_kind: str) -> tuple[FfoConceptMapping, ...]:
        return tuple(c for c in self.concepts if c.entity_kind == entity_kind)

    @property
    def is_empty(self) -> bool:
        return len(self.concepts) == 0


def _clean_text(value: object) -> str:
    """Normalize text for attribute matching (lowercase, alphanumeric + single spaces)."""
    text = str(value or "").lower().replace("-", " ").replace("_", " ")
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text).split())


def _verified_concept(
    *,
    attribute_field: str,
    raw_value: str,
    canonical_id: str,
    confidence: float,
    provenance: str,
) -> Optional[FfoConceptMapping]:
    """Create a mapping only if canonical_id is strictly verified in the FFO corpus."""
    if canonical_id in VERIFIED_FFO_ALIASES:
        canonical_id = VERIFIED_FFO_ALIASES[canonical_id]
    entity_kind = VERIFIED_FFO_TERMS.get(canonical_id)
    if not entity_kind:
        return None
    return FfoConceptMapping(
        attribute_field=attribute_field,
        raw_value=raw_value,
        canonical_id=canonical_id,
        entity_kind=entity_kind,
        confidence=confidence,
        rule_version=FFO_BRIDGE_RULE_VERSION,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Deterministic Attribute Mappings
# ---------------------------------------------------------------------------

_MATERIAL_EXACT: dict[str, tuple[str, str, float]] = {
    "cotton": ("cotton", "rule:exact_material", 1.0),
    "linen": ("linen", "rule:exact_material", 1.0),
    "leather": ("leather", "rule:exact_material", 1.0),
    "silk": ("silk", "rule:exact_material", 1.0),
    "wool": ("wool", "rule:exact_material", 1.0),
    "polyester": ("polyester", "rule:exact_material", 1.0),
    "denim": ("denim", "rule:exact_textile", 1.0),
    "chiffon": ("chiffon", "rule:exact_textile", 1.0),
    "satin": ("satin", "rule:exact_textile", 1.0),
    "tweed": ("tweed", "rule:exact_textile", 1.0),
    "twill": ("twill", "rule:exact_textile", 1.0),
    "velvet": ("velvet", "rule:exact_textile", 1.0),
}

_MATERIAL_SUBSTRINGS: tuple[tuple[str, str, str, float], ...] = (
    ("khadi", "cotton", "rule:material_substring_khadi", 0.95),
    ("french terry", "cotton", "rule:material_substring_french_terry", 0.95),
    ("terry", "cotton", "rule:material_substring_terry", 0.9),
    ("oxford", "cotton", "rule:material_substring_oxford", 0.9),
    ("poplin", "cotton", "rule:material_substring_poplin", 0.9),
    ("selvedge", "denim", "rule:material_substring_selvedge", 0.95),
    ("merino", "wool", "rule:material_substring_merino", 0.95),
    ("cashmere", "wool", "rule:material_substring_cashmere", 0.95),
    ("suede", "leather", "rule:material_substring_suede", 0.9),
    ("poly", "polyester", "rule:material_substring_poly", 0.9),
)

_FIT_MAP: dict[str, tuple[str, str, float]] = {
    "regular": ("regular-fit", "rule:fit_normalization", 1.0),
    "regular fit": ("regular-fit", "rule:fit_normalization", 1.0),
    "standard": ("regular-fit", "rule:fit_normalization", 0.9),
    "relaxed": ("relaxed-fit", "rule:fit_normalization", 1.0),
    "relaxed fit": ("relaxed-fit", "rule:fit_normalization", 1.0),
    "loose": ("relaxed-fit", "rule:fit_normalization", 0.9),
    "easy": ("relaxed-fit", "rule:fit_normalization", 0.85),
    "slim": ("slim-fit", "rule:fit_normalization", 1.0),
    "slim fit": ("slim-fit", "rule:fit_normalization", 1.0),
    "tailored": ("slim-fit", "rule:fit_normalization", 0.9),
    "fitted": ("slim-fit", "rule:fit_normalization", 0.9),
    "slim straight": ("slim-fit", "rule:fit_normalization", 0.9),
}

_SILHOUETTE_MAP: dict[str, tuple[str, str, float]] = {
    "oversized": ("oversized", "rule:exact_silhouette", 1.0),
    "oversize": ("oversized", "rule:silhouette_normalization", 0.95),
    "boxy": ("oversized", "rule:silhouette_normalization_boxy", 0.9),
    "box fit": ("oversized", "rule:silhouette_normalization_box_fit", 0.9),
    "tapered": ("tapered", "rule:exact_silhouette", 1.0),
    "cropped": ("cropped", "rule:exact_silhouette", 1.0),
    "relaxed": ("relaxed", "rule:exact_silhouette", 1.0),
    "a line": ("a-line", "rule:silhouette_normalization_a_line", 1.0),
    "aline": ("a-line", "rule:silhouette_normalization_a_line", 1.0),
}

_COLOR_MAP: dict[str, tuple[str, str, float]] = {
    "charcoal": ("charcoal", "rule:exact_color", 1.0),
    "charcoal grey": ("charcoal", "rule:color_alias_charcoal_grey", 0.95),
    "dark grey": ("charcoal", "rule:color_alias_dark_grey", 0.9),
    "olive": ("olive", "rule:exact_color", 1.0),
    "olive green": ("olive", "rule:color_alias_olive_green", 0.95),
    "navy": ("navy", "rule:exact_color", 1.0),
    "navy blue": ("navy", "rule:color_alias_navy_blue", 0.95),
    "dark blue": ("navy", "rule:color_alias_dark_blue", 0.9),
    "beige": ("beige", "rule:exact_color", 1.0),
    "sand": ("beige", "rule:color_alias_sand", 0.9),
    "tan": ("beige", "rule:color_alias_tan", 0.9),
    "camel": ("beige", "rule:color_alias_camel", 0.9),
    "burgundy": ("burgundy", "rule:exact_color", 1.0),
    "wine": ("burgundy", "rule:color_alias_wine", 1.0),
    "maroon": ("burgundy", "rule:color_alias_maroon", 0.9),
    "oxblood": ("burgundy", "rule:color_alias_oxblood", 0.9),
    "emerald": ("emerald", "rule:exact_color", 1.0),
    "emerald green": ("emerald", "rule:color_alias_emerald_green", 0.95),
    "forest green": ("emerald", "rule:color_alias_forest_green", 0.9),
}

_STYLE_TAG_MAP: dict[str, tuple[str, str, float]] = {
    "streetwear": ("streetwear", "rule:style_tag_aesthetic", 1.0),
    "minimalist": ("minimalist", "rule:style_tag_aesthetic", 1.0),
    "minimal": ("minimalist", "rule:style_tag_aesthetic", 0.95),
    "quiet luxury": ("quiet-luxury", "rule:style_tag_aesthetic", 1.0),
    "old money": ("quiet-luxury", "rule:style_tag_aesthetic", 0.9),
    "y2k": ("y2k", "rule:style_tag_aesthetic", 1.0),
    "punk": ("punk", "rule:style_tag_aesthetic", 1.0),
    "grunge": ("punk", "rule:style_tag_aesthetic", 0.85),
    "classic": ("classic", "rule:style_tag_aesthetic", 1.0),
    "heritage indian": ("indian-fashion", "rule:style_tag_culture", 1.0),
    "artisan indian": ("indian-fashion", "rule:style_tag_culture", 1.0),
    "ethnic indian": ("indian-fashion", "rule:style_tag_culture", 1.0),
    "indian": ("indian-fashion", "rule:style_tag_culture", 0.95),
    "british tailoring": ("british-tailoring", "rule:style_tag_culture", 1.0),
    "sartorial": ("british-tailoring", "rule:style_tag_culture", 0.9),
    "japanese streetwear": ("japanese-streetwear", "rule:style_tag_culture", 1.0),
    "tokyo street": ("japanese-streetwear", "rule:style_tag_culture", 0.9),
}

_GARMENT_SUBCATEGORY_MAP: dict[str, tuple[str, str, float]] = {
    "trench coat": ("trench-coat", "rule:subcategory_garment", 1.0),
    "trench": ("trench-coat", "rule:subcategory_garment", 1.0),
    "oxford shirt": ("oxford-shirt", "rule:subcategory_garment", 1.0),
    "pleated trousers": ("pleated-trousers", "rule:subcategory_garment", 1.0),
    "wide leg jeans": ("wide_leg_jeans", "rule:subcategory_garment", 1.0),
    "baggy jeans": ("wide_leg_jeans", "rule:subcategory_garment", 1.0),
    "loose jeans": ("wide_leg_jeans", "rule:subcategory_garment", 1.0),
    "dark denim jeans": ("dark-denim-jeans", "rule:subcategory_garment", 1.0),
    "raw denim jeans": ("dark-denim-jeans", "rule:subcategory_garment", 0.95),
    "fitted top": ("fitted-top", "rule:subcategory_garment", 1.0),
    "chelsea boots": ("chelsea-boots", "rule:subcategory_footwear", 1.0),
    "chelsea boot": ("chelsea-boots", "rule:subcategory_footwear", 1.0),
    "loafers": ("loafers", "rule:subcategory_footwear", 1.0),
    "loafer": ("loafers", "rule:subcategory_footwear", 1.0),
    "white sneakers": ("white-sneakers", "rule:subcategory_footwear", 1.0),
    "white sneaker": ("white-sneakers", "rule:subcategory_footwear", 1.0),
    "leather belt": ("leather-belt", "rule:subcategory_accessory", 1.0),
    "belt": ("leather-belt", "rule:subcategory_accessory", 0.9),
    "silk tie": ("silk-tie", "rule:subcategory_accessory", 1.0),
    "tie": ("silk-tie", "rule:subcategory_accessory", 0.9),
    "wayfarer sunglasses": ("wayfarer-sunglasses", "rule:subcategory_accessory", 1.0),
    "wayfarer": ("wayfarer-sunglasses", "rule:subcategory_accessory", 1.0),
    "canvas tote": ("canvas-tote", "rule:subcategory_bag", 1.0),
    "tote bag": ("canvas-tote", "rule:subcategory_bag", 1.0),
    "tote": ("canvas-tote", "rule:subcategory_bag", 0.9),
    "leather briefcase": ("leather-briefcase", "rule:subcategory_bag", 1.0),
    "briefcase": ("leather-briefcase", "rule:subcategory_bag", 0.9),
    "gold hoops": ("gold-hoops", "rule:subcategory_jewelry", 1.0),
}

_PATTERN_MAP: dict[str, tuple[str, str, float]] = {
    "floral": ("floral", "rule:pattern_matching", 1.0),
    "flower": ("floral", "rule:pattern_matching", 0.9),
    "plaid": ("plaid", "rule:pattern_matching", 1.0),
    "tartan": ("plaid", "rule:pattern_matching", 0.95),
    "check": ("plaid", "rule:pattern_matching", 0.9),
    "polka dot": ("polka-dot", "rule:pattern_matching", 1.0),
    "polka dots": ("polka-dot", "rule:pattern_matching", 1.0),
    "stripe": ("stripe", "rule:pattern_matching", 1.0),
    "stripes": ("stripe", "rule:pattern_matching", 1.0),
    "striped": ("stripe", "rule:pattern_matching", 1.0),
}


# ---------------------------------------------------------------------------
# Bridge Implementation
# ---------------------------------------------------------------------------


def map_product_attributes_to_ffo(
    product: CatalogProductRecord | dict[str, Any],
) -> ProductFfoBridgeResult:
    """Deterministically map product attributes to verified FFO concepts.

    Operates on a ``CatalogProductRecord`` or a dictionary containing
    attribute values. Returns mapped FFO concepts and explicitly identifies
    unmapped attributes.
    """
    if isinstance(product, CatalogProductRecord):
        product_id = product.id
        raw_attributes = dict(product.attributes or {})
        subcategory = product.subcategory
        category = product.category
        title = product.title
    elif isinstance(product, dict):
        product_id = product.get("id")
        raw_attributes = dict(product.get("attributes") or {})
        subcategory = product.get("subcategory")
        category = product.get("category")
        title = product.get("title", "")
    else:
        raise TypeError(f"Expected CatalogProductRecord or dict, got {type(product)}")

    concepts: list[FfoConceptMapping] = []
    unmapped: dict[str, Any] = {}

    # 1. Material & Textile mapping
    raw_material = raw_attributes.get("material")
    if raw_material:
        norm_mat = _clean_text(raw_material)
        matched_mat = False

        # Exact check
        if norm_mat in _MATERIAL_EXACT:
            target_cid, prov, conf = _MATERIAL_EXACT[norm_mat]
            mapping = _verified_concept(
                attribute_field="material",
                raw_value=str(raw_material),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping:
                concepts.append(mapping)
                matched_mat = True

        # Substring / pattern check
        for sub, target_cid, prov, conf in _MATERIAL_SUBSTRINGS:
            if sub in norm_mat:
                mapping = _verified_concept(
                    attribute_field="material",
                    raw_value=str(raw_material),
                    canonical_id=target_cid,
                    confidence=conf,
                    provenance=prov,
                )
                if mapping and not any(c.canonical_id == mapping.canonical_id for c in concepts):
                    concepts.append(mapping)
                    matched_mat = True

        # Check for composite materials like "cotton twill", "linen silk"
        for exact_name, (target_cid, prov, conf) in _MATERIAL_EXACT.items():
            if exact_name in norm_mat and not any(c.canonical_id == target_cid for c in concepts):
                mapping = _verified_concept(
                    attribute_field="material",
                    raw_value=str(raw_material),
                    canonical_id=target_cid,
                    confidence=conf,
                    provenance=f"rule:material_composite_{exact_name}",
                )
                if mapping:
                    concepts.append(mapping)
                    matched_mat = True

        if not matched_mat:
            unmapped["material"] = raw_material

    # 2. Fit mapping
    raw_fit = raw_attributes.get("fit")
    if raw_fit:
        norm_fit = _clean_text(raw_fit)
        if norm_fit in _FIT_MAP:
            target_cid, prov, conf = _FIT_MAP[norm_fit]
            mapping = _verified_concept(
                attribute_field="fit",
                raw_value=str(raw_fit),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping:
                concepts.append(mapping)
        else:
            unmapped["fit"] = raw_fit

    # 3. Silhouette mapping
    raw_sil = raw_attributes.get("silhouette")
    if raw_sil:
        norm_sil = _clean_text(raw_sil)
        if norm_sil in _SILHOUETTE_MAP:
            target_cid, prov, conf = _SILHOUETTE_MAP[norm_sil]
            mapping = _verified_concept(
                attribute_field="silhouette",
                raw_value=str(raw_sil),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping:
                concepts.append(mapping)
        else:
            unmapped["silhouette"] = raw_sil

    # 4. Color mapping
    raw_color = raw_attributes.get("color")
    if raw_color:
        norm_color = _clean_text(raw_color)
        if norm_color in _COLOR_MAP:
            target_cid, prov, conf = _COLOR_MAP[norm_color]
            mapping = _verified_concept(
                attribute_field="color",
                raw_value=str(raw_color),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping:
                concepts.append(mapping)
        else:
            # Substring color check (e.g. "dark charcoal", "deep navy")
            matched_color = False
            for color_term, (target_cid, prov, conf) in _COLOR_MAP.items():
                if color_term in norm_color:
                    mapping = _verified_concept(
                        attribute_field="color",
                        raw_value=str(raw_color),
                        canonical_id=target_cid,
                        confidence=conf * 0.95,
                        provenance=f"rule:color_substring_{color_term}",
                    )
                    if mapping:
                        concepts.append(mapping)
                        matched_color = True
                        break
            if not matched_color:
                unmapped["color"] = raw_color

    # 5. Style Tags mapping (Aesthetic & Culture)
    raw_tags = raw_attributes.get("style_tags")
    if isinstance(raw_tags, (list, tuple)):
        unmapped_tags: list[str] = []
        for tag in raw_tags:
            norm_tag = _clean_text(tag)
            if norm_tag in _STYLE_TAG_MAP:
                target_cid, prov, conf = _STYLE_TAG_MAP[norm_tag]
                mapping = _verified_concept(
                    attribute_field="style_tags",
                    raw_value=str(tag),
                    canonical_id=target_cid,
                    confidence=conf,
                    provenance=prov,
                )
                if mapping and not any(c.canonical_id == mapping.canonical_id for c in concepts):
                    concepts.append(mapping)
            else:
                unmapped_tags.append(str(tag))
        if unmapped_tags:
            unmapped["style_tags"] = unmapped_tags

    # 6. Subcategory & Garment/Footwear/Accessory mapping
    if subcategory:
        norm_sub = _clean_text(subcategory)
        if norm_sub in _GARMENT_SUBCATEGORY_MAP:
            target_cid, prov, conf = _GARMENT_SUBCATEGORY_MAP[norm_sub]
            mapping = _verified_concept(
                attribute_field="subcategory",
                raw_value=str(subcategory),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping and not any(c.canonical_id == mapping.canonical_id for c in concepts):
                concepts.append(mapping)
        else:
            unmapped["subcategory"] = subcategory

    # Also check title keywords for specific iconic garments (e.g. trench coat, oxford shirt)
    if title:
        norm_title = _clean_text(title)
        for term, (target_cid, prov, conf) in _GARMENT_SUBCATEGORY_MAP.items():
            if term in norm_title and not any(c.canonical_id == target_cid for c in concepts):
                mapping = _verified_concept(
                    attribute_field="title",
                    raw_value=str(term),
                    canonical_id=target_cid,
                    confidence=conf * 0.9,
                    provenance=f"rule:title_keyword_{target_cid}",
                )
                if mapping:
                    concepts.append(mapping)

    # 7. Pattern mapping
    raw_pattern = raw_attributes.get("pattern")
    if raw_pattern:
        norm_pat = _clean_text(raw_pattern)
        if norm_pat in _PATTERN_MAP:
            target_cid, prov, conf = _PATTERN_MAP[norm_pat]
            mapping = _verified_concept(
                attribute_field="pattern",
                raw_value=str(raw_pattern),
                canonical_id=target_cid,
                confidence=conf,
                provenance=prov,
            )
            if mapping:
                concepts.append(mapping)
        else:
            unmapped["pattern"] = raw_pattern

    return ProductFfoBridgeResult(
        product_id=product_id,
        concepts=tuple(concepts),
        unmapped_attributes=unmapped,
        rule_version=FFO_BRIDGE_RULE_VERSION,
    )
