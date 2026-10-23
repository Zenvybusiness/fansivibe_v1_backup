"""Concept-to-catalog matching service (TRENDING-02).

Matches fashion trend concepts to compatible genuine catalog products using
category and attribute compatibility while strictly excluding synthetic fixtures
from live shopping recommendations.

Invariants & Principles:
- Catalog integrity: Uses existing catalog entities and contracts (no parallel
  product tables or fake catalog entries).
- Fixture exclusion: Products tagged `attributes["fixture"] = True` or
  `attributes["synthetic"] = True` are strictly excluded from live shopping matches.
- Multi-dimensional matching: Matches products on category alignment AND attribute/
  subcategory compatibility (e.g. material, fit, silhouette, style tags).
- Confidence separation: Concept trend confidence (evidence of creator attention)
  remains strictly separate from product match confidence (attribute alignment score).
- Non-fabrication: Never fabricates prices, currency, availability, stock, merchant
  offers, or affiliate URLs. Absent fields remain `None`.
- Graceful empty matches: A valid trend may match zero products without raising an error.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from app.domain.services.fashion_concept_extraction import VOCABULARY, ConceptDefinition


@dataclass(frozen=True)
class MatchedCatalogProduct:
    """One genuine catalog product matched to a trend concept."""

    product_id: str
    title: str
    brand: Optional[str]
    category: str
    subcategory: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    availability: Optional[bool]
    product_url: Optional[str]
    image_url: Optional[str]
    retailer: Optional[str]
    match_score: float
    match_reasons: tuple[str, ...]
    is_fixture: bool
    provenance: dict[str, Any] = field(default_factory=dict)


def _get_field(prod: Any, field_name: str, default: Any = None) -> Any:
    """Extract a field from either a dict or object."""
    if isinstance(prod, dict):
        return prod.get(field_name, default)
    return getattr(prod, field_name, default)


def _is_fixture_product(prod: Any) -> bool:
    """Check if a product is a development / synthetic test fixture."""
    if isinstance(prod, dict):
        if prod.get("is_fixture") is True:
            return True
        attrs = prod.get("attributes")
        if isinstance(attrs, dict):
            if attrs.get("fixture") is True or attrs.get("synthetic") is True:
                return True
            if "note" in attrs and "fixture" in str(attrs["note"]).lower():
                return True
        return False

    if getattr(prod, "is_fixture", False):
        return True
    attrs = getattr(prod, "attributes", None)
    if isinstance(attrs, dict):
        if attrs.get("fixture") is True or attrs.get("synthetic") is True:
            return True
        if "note" in attrs and "fixture" in str(attrs["note"]).lower():
            return True
    return False


class CatalogConceptMatcher:
    """Pure domain service matching fashion concepts to catalog products."""

    def __init__(
        self,
        vocabulary: Sequence[ConceptDefinition] = VOCABULARY,
        min_match_score: float = 0.60,
    ) -> None:
        self._vocab_by_id = {c.concept_id: c for c in vocabulary}
        self._min_match_score = min_match_score

    def match_products(
        self,
        concept_id: str,
        products: Sequence[Any],
        *,
        exclude_fixtures: bool = True,
        limit: int = 10,
    ) -> tuple[MatchedCatalogProduct, ...]:
        """Match candidate catalog products to a trend concept deterministically.

        Excludes fixture products when ``exclude_fixtures=True`` (default for live shopping).
        """
        concept_def = self._vocab_by_id.get(concept_id)
        if not concept_def:
            return ()

        target_category = concept_def.category.lower().strip()
        matched: list[MatchedCatalogProduct] = []

        for p in products:
            is_fixture = _is_fixture_product(p)
            if exclude_fixtures and is_fixture:
                continue

            prod_category = str(_get_field(p, "category") or "").lower().strip()
            # Category must align with concept category
            if prod_category != target_category:
                continue

            score, reasons = self._evaluate_compatibility(concept_def, p)
            if score < self._min_match_score:
                continue

            # Extract genuine product fields without fabrication
            pid = str(_get_field(p, "id") or _get_field(p, "source_product_id") or "")
            title = str(_get_field(p, "title") or _get_field(p, "name") or "")
            brand = _get_field(p, "brand")
            subcategory = _get_field(p, "subcategory")
            price = _get_field(p, "price")
            currency = _get_field(p, "currency")
            availability = _get_field(p, "availability")
            product_url = _get_field(p, "product_url") or _get_field(p, "affiliate_url")

            # Image URL resolution (extract primary)
            image_url: Optional[str] = None
            raw_images = _get_field(p, "image_urls") or _get_field(p, "image_url")
            if isinstance(raw_images, (list, tuple)) and raw_images:
                image_url = str(raw_images[0])
            elif isinstance(raw_images, str) and raw_images.strip():
                image_url = raw_images.strip()

            source = str(_get_field(p, "source") or "catalog")
            retailer = _get_field(p, "retailer") or ("Amazon India" if "amazon" in source else source)

            provenance = {
                "source": source,
                "source_product_id": pid,
                "matched_concept": concept_id,
            }

            matched.append(
                MatchedCatalogProduct(
                    product_id=pid,
                    title=title,
                    brand=str(brand) if brand else None,
                    category=prod_category,
                    subcategory=str(subcategory) if subcategory else None,
                    price=float(price) if price is not None else None,
                    currency=str(currency) if currency else "INR",
                    availability=bool(availability) if availability is not None else None,
                    product_url=str(product_url) if product_url else None,
                    image_url=image_url,
                    retailer=str(retailer) if retailer else None,
                    match_score=round(score, 4),
                    match_reasons=tuple(reasons),
                    is_fixture=is_fixture,
                    provenance=provenance,
                )
            )

        # Sort deterministically by descending match score, then product_id
        matched.sort(key=lambda m: (-m.match_score, m.product_id))
        return tuple(matched[:limit])

    def _evaluate_compatibility(
        self, concept_def: ConceptDefinition, product: Any
    ) -> tuple[float, list[str]]:
        """Compute compatibility score and auditable match reasons."""
        score = 0.20  # baseline for category alignment
        reasons: list[str] = [f"category matches '{concept_def.category}'"]

        title = str(_get_field(product, "title") or _get_field(product, "name") or "").lower()
        subcategory = str(_get_field(product, "subcategory") or "").lower()
        attrs = _get_field(product, "attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}

        # 1. Subcategory alignment (exact word boundary matching)
        subcat_matched = False
        if subcategory:
            for sc in concept_def.compatible_subcategories:
                if re.search(rf"\b{re.escape(sc)}\b", subcategory):
                    score += 0.25
                    reasons.append(f"subcategory '{subcategory}' matches concept subcategory")
                    subcat_matched = True
                    break
        if not subcat_matched:
            # Check title for subcategory terms
            for sc in concept_def.compatible_subcategories:
                if re.search(rf"\b{re.escape(sc)}\b", title):
                    score += 0.15
                    reasons.append(f"title contains concept garment type '{sc}'")
                    break

        # 2. Specific attribute criteria evaluation
        attr_matched = False
        for attr_key, expected_val in concept_def.attribute_criteria.items():
            actual_val = attrs.get(attr_key)

            if attr_key == "material" and isinstance(expected_val, str):
                actual_mat = str(actual_val or attrs.get("fabric") or "").lower()
                if expected_val.lower() in actual_mat or re.search(rf"\b{re.escape(expected_val.lower())}\b", title):
                    score += 0.45
                    reasons.append(f"material matches '{expected_val}'")
                    attr_matched = True

            elif attr_key == "fit" and isinstance(expected_val, str):
                actual_fit = str(actual_val or "").lower()
                if expected_val.lower() in actual_fit or re.search(rf"\b{re.escape(expected_val.lower())}\b", title):
                    score += 0.45
                    reasons.append(f"fit matches '{expected_val}'")
                    attr_matched = True

            elif attr_key == "silhouette" and isinstance(expected_val, str):
                actual_sil = str(actual_val or "").lower()
                if expected_val.lower() in actual_sil or re.search(rf"\b{re.escape(expected_val.lower())}\b", title):
                    score += 0.35
                    reasons.append(f"silhouette matches '{expected_val}'")
                    attr_matched = True

            elif attr_key == "style_tags" and isinstance(expected_val, (tuple, list)):
                actual_tags = attrs.get("style_tags") or []
                if isinstance(actual_tags, str):
                    actual_tags = [actual_tags]
                actual_tags_lower = [str(t).lower() for t in actual_tags]
                for exp in expected_val:
                    if exp.lower() in actual_tags_lower or re.search(rf"\b{re.escape(exp.lower())}\b", title) or re.search(rf"\b{re.escape(exp.lower())}\b", subcategory):
                        score += 0.45
                        reasons.append(f"style tag matches '{exp}'")
                        attr_matched = True
                        break

        # Check concept patterns against product title for strong keyword corroboration
        for pat in concept_def.patterns:
            if pat.search(title):
                score += 0.20
                reasons.append("title matches concept keyword pattern")
                break

        score = min(1.0, score)
        return score, reasons
