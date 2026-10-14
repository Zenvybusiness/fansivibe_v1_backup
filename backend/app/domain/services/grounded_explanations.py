"""Grounded Discovery Explanation Engine for Fansivibe (TASK DISCOVERY-05).

Provides deterministic, auditable explanation formatting for product recommendations,
complete looks, and trend candidate observations.

Invariants:
- Deterministic string formatting (pure templates, zero LLM calls).
- Strictly grounded in verified product attributes, explicit user preferences,
  actual personalization score breakdowns, and outfit compatibility dimensions.
- Honest handling of missing attributes: neutral dimensions are clearly reported
  without penalties or fabricated attributes.
- Synthetic fixtures are explicitly labeled and never described as verified retailer inventory.
- Popularity, bestselling status, or viral demand is NEVER claimed when no direct
  demand signal exists (DEMAND_SIGNAL_AVAILABLE = False).
- Preserves score components and audit provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.domain.services.outfit_compatibility import CompleteLook, LookItem
from app.domain.services.personalization import (
    PersonalizationScoreBreakdown,
    RankedCandidate,
    UserPersonalizationContext,
)
from app.domain.services.trends import (
    DEMAND_SIGNAL_AVAILABLE,
    REASON_NO_DEMAND,
    TrendCandidate,
)

EVIDENCE_TYPE_CATALOG = "catalog_activity"


@dataclass(frozen=True)
class GroundedProductExplanation:
    """Structured explanation for an individual product recommendation."""

    summary: str
    reasons: tuple[str, ...]
    positive_evidence: tuple[str, ...]
    neutral_dimensions: tuple[str, ...]
    is_synthetic_fixture: bool
    provenance: str


@dataclass(frozen=True)
class GroundedLookExplanation:
    """Structured explanation for an assembled complete look."""

    summary: str
    reasons: tuple[str, ...]
    positive_evidence: tuple[str, ...]
    neutral_dimensions: tuple[str, ...]
    warnings: tuple[str, ...]
    is_synthetic_fixture: bool
    is_wardrobe_aware: bool


@dataclass(frozen=True)
class GroundedTrendExplanation:
    """Structured explanation for a trend intelligence candidate."""

    summary: str
    evidence_type: str
    demand_signal_available: bool
    reasons: tuple[str, ...]


def format_product_recommendation_explanation(
    candidate: RankedCandidate,
    context: UserPersonalizationContext,
) -> GroundedProductExplanation:
    """Format a deterministic, grounded explanation for a ranked product candidate.

    Uses actual personalization score breakdown, verified product attributes,
    and user preference context. Never fabricates demand or unprovided attributes.
    """
    product = candidate.product
    breakdown = candidate.breakdown
    is_synthetic_fixture = bool(candidate.is_synthetic or candidate.is_fixture)

    positive_evidence: list[str] = []

    # 1. Collect verified positive match evidence from breakdown
    for reason in breakdown.match_reasons:
        positive_evidence.append(reason)

    # 2. Add verified factual product signals
    if product.price is not None:
        positive_evidence.append(f"Verified price ₹{product.price:g}")
    if product.availability is True:
        positive_evidence.append("In-stock availability verified")

    # 3. Provenance determination
    if is_synthetic_fixture:
        provenance = "synthetic_fixture_catalog"
    else:
        provenance = "verified_catalog"

    # 4. Deterministic summary sentence construction
    if context.is_guest:
        if is_synthetic_fixture:
            summary = (
                f"Catalog recommendation in {product.category or 'apparel'} "
                f"(demo fixture inventory)."
            )
        else:
            summary = (
                f"Catalog recommendation in {product.category or 'apparel'} "
                f"with verified availability."
            )
    else:
        # Authenticated user context
        matched_prefs: list[str] = [
            r for r in breakdown.match_reasons if r.startswith("Matches preferred")
        ]
        if matched_prefs:
            # If both brand and category match, highlight combined relevance
            prod_brand = product.brand
            prod_cat = product.category
            if (
                any("category" in r for r in matched_prefs)
                and any("brand" in r for r in matched_prefs)
                and prod_brand
                and prod_cat
            ):
                summary = (
                    f"Recommended based on your preference for {prod_brand} {prod_cat}."
                )
            else:
                summary = f"Recommended: {matched_prefs[0]}."
        elif breakdown.style_profile_match > 0:
            profile_style = context.style_profile.get("style_type")
            if profile_style:
                summary = (
                    f"Aligns with your '{profile_style}' style profile."
                )
            else:
                summary = "Aligns with your preferred style aesthetic and occasions."
        elif breakdown.wardrobe_complementarity > 0:
            summary = (
                "Complements your existing wardrobe palette and collection balance."
            )
        else:
            summary = (
                f"Catalog recommendation in {product.category or 'apparel'}."
            )

    return GroundedProductExplanation(
        summary=summary,
        reasons=breakdown.match_reasons,
        positive_evidence=tuple(positive_evidence),
        neutral_dimensions=breakdown.neutral_dimensions,
        is_synthetic_fixture=is_synthetic_fixture,
        provenance=provenance,
    )


def format_complete_look_explanation(
    look: CompleteLook,
) -> GroundedLookExplanation:
    """Format a deterministic, grounded explanation for an assembled complete look.

    Uses actual outfit compatibility breakdown, verified slot items,
    and wardrobe vs catalog provenance.
    """
    breakdown = look.compatibility_breakdown
    slots = look.slots
    item_list = list(slots.values())
    is_synthetic_fixture = look.contains_synthetic_fixtures
    is_wardrobe_aware = look.is_wardrobe_aware

    # Positive evidence
    positive_evidence = list(breakdown.reasons)

    # Neutral dimensions tracking
    neutral_dims: list[str] = []
    known_colors = [it.color for it in item_list if it.color]
    if len(known_colors) < 2:
        neutral_dims.append("color_harmony_neutral (single or unstated colors across pieces)")

    known_materials = [it.material for it in item_list if it.material]
    if not known_materials:
        neutral_dims.append("material_consistency_neutral (materials unstated)")

    all_concepts = [c for it in item_list for c in it.ffo_concepts]
    if not all_concepts:
        neutral_dims.append("style_concept_neutral (style aesthetic unclassified)")

    top_it = slots.get("top")
    bottom_it = slots.get("bottom")
    if not (top_it and bottom_it):
        neutral_dims.append("silhouette_balance_neutral (requires both top and bottom)")

    # Deterministic summary sentence construction
    slot_count = len(slots)
    if is_wardrobe_aware:
        w_count = look.wardrobe_item_count
        c_count = look.catalog_item_count
        w_str = f"{w_count} piece{'s' if w_count > 1 else ''} from your wardrobe"
        c_str = f"{c_count} catalog item{'s' if c_count > 1 else ''}"
        summary = f"Coordinated {slot_count}-piece look combining {w_str} with {c_str}."
    else:
        summary = f"Coordinated {slot_count}-piece catalog ensemble."

    if breakdown.reasons:
        # Append primary compatibility highlight
        summary += f" Features {breakdown.reasons[0].lower()}."

    return GroundedLookExplanation(
        summary=summary,
        reasons=breakdown.reasons,
        positive_evidence=tuple(positive_evidence),
        neutral_dimensions=tuple(neutral_dims),
        warnings=breakdown.warnings,
        is_synthetic_fixture=is_synthetic_fixture,
        is_wardrobe_aware=is_wardrobe_aware,
    )


def format_trend_candidate_explanation(
    candidate: TrendCandidate,
) -> GroundedTrendExplanation:
    """Format a deterministic, grounded explanation for a trend candidate observation.

    Strictly preserves DEMAND_SIGNAL_AVAILABLE = False and clearly reports
    that catalog/source observations represent catalog activity, not consumer demand.
    """
    reasons = list(candidate.reasons)
    if not DEMAND_SIGNAL_AVAILABLE and REASON_NO_DEMAND not in reasons:
        reasons.append(REASON_NO_DEMAND)

    summary = (
        f"Catalog activity observed across {candidate.distinct_products} "
        f"product{'s' if candidate.distinct_products != 1 else ''} "
        f"from {candidate.distinct_sources} distinct source{'s' if candidate.distinct_sources != 1 else ''}. "
        "Direct consumer demand signals are currently unavailable."
    )

    return GroundedTrendExplanation(
        summary=summary,
        evidence_type=EVIDENCE_TYPE_CATALOG,
        demand_signal_available=DEMAND_SIGNAL_AVAILABLE,
        reasons=tuple(reasons),
    )
