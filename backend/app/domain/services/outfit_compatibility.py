"""Outfit compatibility, slot definition, and assembly policies for Fansivibe Complete Looks (DISCOVERY-04).

Defines deterministic multi-category outfit assembly rules using verified product attributes,
FFO concepts, and owned wardrobe items.

Invariants:
- Categorical integrity: 1 item per slot, no duplicate products in the same look.
- Required slots (top, bottom) must be filled; optional slots (footwear, outerwear, accessories) enhance coverage.
- Compatibility rules: color harmony, natural materials, seasonal coherence, formality, silhouette balance, and FFO aesthetics.
- Budget constraint: total catalog product price <= max_budget (wardrobe items cost ₹0 towards catalog budget).
- Missing attributes remain neutral and are never fabricated.
- Deterministic tie-breaking: compatibility_score desc -> total_catalog_price asc -> filled_slots desc -> look_id asc.
- Explicit labeling of synthetic fixture products.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from app.domain.ports.repositories import CatalogProductRecord, WardrobeItemRecord
from app.domain.services.analysis_rules import (
    _CATEGORY_FORMALITY,
    _CATEGORY_OCCASIONS,
    _CATEGORY_SEASON_MAP,
    _MATERIAL_SEASON_MAP,
    _PALETTE_COLOR_SETS,
    _is_natural_material,
    _is_neutral_color,
)
from app.domain.services.ffo_bridge import ProductFfoBridgeResult

# Standard supported slot names and their canonical category mappings
CANONICAL_SLOT_CATEGORIES: dict[str, str] = {
    "top": "tops",
    "bottom": "bottoms",
    "footwear": "footwear",
    "outerwear": "outerwear",
    "accessories": "accessories",
}


@dataclass(frozen=True)
class LookSlotDefinition:
    """Definition of an outfit slot."""

    name: str  # e.g. "top", "bottom", "footwear", "outerwear", "accessories"
    category: str  # canonical category: "tops", "bottoms", "footwear", "outerwear", "accessories"
    is_required: bool = True


# Standard default outfit slots: top & bottom required, footwear/outerwear/accessories optional
DEFAULT_OUTFIT_SLOTS: tuple[LookSlotDefinition, ...] = (
    LookSlotDefinition(name="top", category="tops", is_required=True),
    LookSlotDefinition(name="bottom", category="bottoms", is_required=True),
    LookSlotDefinition(name="footwear", category="footwear", is_required=False),
    LookSlotDefinition(name="outerwear", category="outerwear", is_required=False),
    LookSlotDefinition(name="accessories", category="accessories", is_required=False),
)


@dataclass(frozen=True)
class LookItem:
    """An item participating in a complete look (catalog product or wardrobe item)."""

    item_id: UUID
    source: str  # "catalog" or "wardrobe"
    title: str
    category: str
    brand: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    fit: Optional[str] = None
    silhouette: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    is_synthetic: bool = False
    is_fixture: bool = False
    ffo_concepts: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LookCompatibilityBreakdown:
    """Transparent scoring breakdown for complete look compatibility."""

    category_completeness: float  # 0.0 - 25.0
    color_harmony: float  # 0.0 - 25.0
    material_consistency: float  # 0.0 - 20.0
    style_concept_match: float  # 0.0 - 15.0
    silhouette_formality: float  # 0.0 - 15.0
    total_score: float  # 0.0 - 100.0
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompleteLook:
    """A fully assembled, compatible multi-category look."""

    look_id: str
    slots: dict[str, LookItem]  # slot_name -> LookItem
    total_catalog_price: float
    currency: str
    compatibility_score: float
    compatibility_breakdown: LookCompatibilityBreakdown
    compatibility_reasons: tuple[str, ...]
    unresolved_constraints: tuple[str, ...]
    is_wardrobe_aware: bool
    wardrobe_item_count: int
    catalog_item_count: int
    contains_synthetic_fixtures: bool


def catalog_product_to_look_item(
    product: CatalogProductRecord,
    bridge: Optional[ProductFfoBridgeResult] = None,
) -> LookItem:
    """Convert a normalized catalog product to a standardized LookItem."""
    concepts = tuple(sorted(bridge.canonical_ids)) if bridge else ()
    image_url = product.image_urls[0] if product.image_urls else None
    return LookItem(
        item_id=product.id,
        source="catalog",
        title=product.title,
        category=(product.category or "").strip().lower(),
        brand=product.brand,
        subcategory=product.subcategory,
        color=product.color,
        material=product.material,
        fit=product.fit,
        silhouette=product.silhouette,
        price=product.price,
        currency=product.currency or "INR",
        image_url=image_url,
        is_synthetic=product.is_synthetic,
        is_fixture=product.is_fixture,
        ffo_concepts=concepts,
        attributes=dict(product.attributes or {}),
    )


def wardrobe_item_to_look_item(
    item: WardrobeItemRecord,
    bridge: Optional[ProductFfoBridgeResult] = None,
) -> LookItem:
    """Convert an owned wardrobe item to a standardized LookItem (price=0 for catalog budget)."""
    concepts = tuple(sorted(bridge.canonical_ids)) if bridge else ()
    return LookItem(
        item_id=item.id,
        source="wardrobe",
        title=item.name,
        category=(item.category or "").strip().lower(),
        brand=None,
        subcategory=None,
        color=item.color,
        material=item.material,
        fit=item.fit,
        silhouette=None,
        price=0.0,  # Wardrobe items already owned, zero catalog price
        currency="INR",
        image_url=None,
        is_synthetic=False,
        is_fixture=False,
        ffo_concepts=concepts,
        attributes={"fit_confidence": item.fit_confidence, "is_favorite": item.is_favorite},
    )


def evaluate_look_compatibility(
    items: Mapping[str, LookItem],
    target_occasion: Optional[str] = None,
    target_aesthetic: Optional[str] = None,
) -> LookCompatibilityBreakdown:
    """Evaluate multi-dimensional compatibility of an assembled look (0–100 score).

    Dimensions:
    1. Category Completeness (0–25): Core top+bottom (15 pts) + footwear (5 pts) + outerwear (3 pts) + accessories (2 pts).
    2. Color Harmony (0–25): Palette coherence (monochrome, warm, cool) or neutral-anchored pairings.
    3. Material & Season Consistency (0–20): Natural material synergy and shared seasonal intersection.
    4. Style / FFO Concept Alignment (0–15): Aesthetic consistency across garments.
    5. Silhouette & Formality Balance (0–15): Coherent formality register and volume balance.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    item_list = list(items.values())
    if not item_list:
        return LookCompatibilityBreakdown(
            category_completeness=0.0,
            color_harmony=0.0,
            material_consistency=0.0,
            style_concept_match=0.0,
            silhouette_formality=0.0,
            total_score=0.0,
            reasons=(),
            warnings=("No items in look",),
        )

    # 1. Category Completeness (0–25 pts)
    completeness = 0.0
    slots_present = set(items.keys())
    if "top" in slots_present and "bottom" in slots_present:
        completeness += 15.0
        reasons.append("Complete top and bottom foundation")
    elif "top" in slots_present or "bottom" in slots_present:
        completeness += 7.5
        warnings.append("Missing core top or bottom slot")
    else:
        warnings.append("Lacks both top and bottom foundation")

    if "footwear" in slots_present:
        completeness += 5.0
        reasons.append("Coordinated footwear included")
    if "outerwear" in slots_present:
        completeness += 3.0
        reasons.append("Layered outerwear included")
    if "accessories" in slots_present:
        completeness += 2.0
        reasons.append("Finishing accessory included")
    completeness = min(25.0, completeness)

    # 2. Color Harmony (0–25 pts)
    color_pts = 0.0
    known_colors = [
        (it.color or "").strip().lower() for it in item_list if it.color
    ]
    if len(known_colors) < 2:
        # Insufficient color data is neutral, not penalized
        color_pts = 12.5
    else:
        # Check palette consistency
        matched_palette = None
        for pal_name, pal_set in _PALETTE_COLOR_SETS.items():
            if all(c in pal_set for c in known_colors):
                matched_palette = pal_name
                break

        if matched_palette:
            color_pts = 25.0
            reasons.append(f"Harmonious {matched_palette} color palette across items")
        else:
            # Pairwise neutral-vocabulary check
            has_clash = False
            for i, c1 in enumerate(known_colors):
                for c2 in known_colors[i + 1 :]:
                    if not _is_neutral_color(c1) and not _is_neutral_color(c2):
                        has_clash = True
                        break
                if has_clash:
                    break

            if not has_clash:
                color_pts = 20.0
                reasons.append("Balanced, neutral-anchored color coordination")
            else:
                color_pts = 5.0
                warnings.append("Contains contrasting bright colors without neutral anchor")

    # 3. Material & Seasonal Consistency (0–20 pts)
    material_pts = 0.0
    known_materials = [
        (it.material or "").strip().lower() for it in item_list if it.material
    ]
    if known_materials:
        if all(_is_natural_material(m) for m in known_materials):
            material_pts += 10.0
            reasons.append("Natural fiber synergy across garments")
        else:
            material_pts += 5.0
    else:
        material_pts += 5.0  # Neutral when materials unstated

    # Seasonal intersection
    seasons_per_item: list[set[str]] = []
    for it in item_list:
        item_seasons = set(_CATEGORY_SEASON_MAP.get(it.category, set()))
        if it.material:
            item_seasons |= _MATERIAL_SEASON_MAP.get(it.material.strip().lower(), set())
        if item_seasons:
            seasons_per_item.append(item_seasons)

    if len(seasons_per_item) >= 2:
        shared = set.intersection(*seasons_per_item)
        if shared:
            material_pts += 10.0
            reasons.append(f"Seasonally cohesive for: {', '.join(sorted(shared))}")
        else:
            material_pts += 0.0
            warnings.append("Potential seasonal conflict across garment materials")
    else:
        material_pts += 5.0  # Neutral

    material_pts = min(20.0, material_pts)

    # 4. Style / FFO Concept Alignment (0–15 pts)
    style_pts = 0.0
    all_concepts = set()
    for it in item_list:
        all_concepts.update(c.lower() for c in it.ffo_concepts)

    if target_aesthetic:
        wanted_aes = target_aesthetic.strip().lower()
        if wanted_aes in all_concepts:
            style_pts += 15.0
            reasons.append(f"Curated for {target_aesthetic} aesthetic")
        else:
            style_pts += 7.5
    else:
        # Check if items share an aesthetic or culture concept
        aesthetic_concepts = {
            "minimalist",
            "streetwear",
            "quiet-luxury",
            "classic",
            "y2k",
            "punk",
            "indian-fashion",
            "british-tailoring",
            "japanese-streetwear",
        }
        shared_aes = all_concepts & aesthetic_concepts
        if shared_aes:
            style_pts += 15.0
            reasons.append(f"Unified style aesthetic: {', '.join(sorted(shared_aes))}")
        else:
            style_pts += 7.5  # Neutral baseline when unclassified

    style_pts = min(15.0, style_pts)

    # 5. Silhouette & Formality Balance (0–15 pts)
    sil_form_pts = 0.0

    # Formality consistency (+8.0 pts)
    formality_sets: set[str] = set()
    for it in item_list:
        form_flags = _CATEGORY_FORMALITY.get(it.category, {})
        for k, v in form_flags.items():
            if v:
                formality_sets.add(k)
    if formality_sets:
        if len(formality_sets) == 1:
            sil_form_pts += 8.0
            reasons.append("Consistent formality level across pieces")
        else:
            sil_form_pts += 4.0
    else:
        sil_form_pts += 4.0

    # Silhouette volume balance (+7.0 pts)
    top_it = items.get("top")
    bottom_it = items.get("bottom")
    if top_it and bottom_it:
        top_sil = (top_it.silhouette or top_it.fit or "").strip().lower()
        bot_sil = (bottom_it.silhouette or bottom_it.fit or "").strip().lower()

        # FFO Volume balance heuristics
        if "oversized" in top_sil and ("wide" in bot_sil or "relaxed" in bot_sil):
            sil_form_pts += 7.0
            reasons.append("Relaxed high-volume silhouette pairing")
        elif "fitted" in top_sil and ("wide" in bot_sil or "relaxed" in bot_sil):
            sil_form_pts += 7.0
            reasons.append("Balanced volume: fitted top with relaxed bottoms")
        elif "cropped" in top_sil and ("tapered" in bot_sil or "high" in bot_sil):
            sil_form_pts += 7.0
            reasons.append("Proportionate cropped silhouette with tapered bottoms")
        elif top_sil or bot_sil:
            sil_form_pts += 5.0
        else:
            sil_form_pts += 4.0  # Neutral
    else:
        sil_form_pts += 3.5

    sil_form_pts = min(15.0, sil_form_pts)

    # Occasion bonus check
    if target_occasion:
        target_occ_clean = target_occasion.strip().lower()
        all_suitable = all(
            target_occ_clean in _CATEGORY_OCCASIONS.get(it.category, set())
            for it in item_list
        )
        if all_suitable:
            reasons.append(f"Tailored for {target_occasion} occasions")

    total_score = round(
        completeness + color_pts + material_pts + style_pts + sil_form_pts, 2
    )
    total_score = max(0.0, min(100.0, total_score))

    return LookCompatibilityBreakdown(
        category_completeness=round(completeness, 2),
        color_harmony=round(color_pts, 2),
        material_consistency=round(material_pts, 2),
        style_concept_match=round(style_pts, 2),
        silhouette_formality=round(sil_form_pts, 2),
        total_score=total_score,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def compute_look_id(slots: Mapping[str, LookItem]) -> str:
    """Generate a stable, deterministic look ID from slot names and item UUIDs."""
    sorted_pairs = sorted((slot, str(item.item_id)) for slot, item in slots.items())
    token = "|".join(f"{s}:{i}" for s, i in sorted_pairs)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"look_{digest}"


# Default slot weights for pairwise similarity calculations in diversity selection
SLOT_SIMILARITY_WEIGHTS: dict[str, float] = {
    "top": 0.35,
    "bottom": 0.35,
    "outerwear": 0.15,
    "footwear": 0.10,
    "accessories": 0.05,
}

# Default trade-off weight for diversity vs quality in greedy re-ranking
DEFAULT_DIVERSITY_WEIGHT: float = 0.20


def compute_look_similarity(
    look1: CompleteLook | Mapping[str, LookItem],
    look2: CompleteLook | Mapping[str, LookItem],
    anchor_slot: Optional[str] = None,
) -> float:
    """Calculate overlap similarity in [0.0, 1.0] between two looks across non-anchor slots.

    - Primary slots (top, bottom) carry 70% of total weight.
    - Outerwear (15%), Footwear (10%), Accessories (5%) carry the remaining 30%.
    - If anchor_slot is specified, that slot is excluded from similarity calculations.
    - If both looks share no common slots, similarity is 0.0.
    """
    slots1 = look1.slots if isinstance(look1, CompleteLook) else look1
    slots2 = look2.slots if isinstance(look2, CompleteLook) else look2

    total_weight = 0.0
    matching_weight = 0.0

    for slot_name, weight in SLOT_SIMILARITY_WEIGHTS.items():
        if anchor_slot and slot_name == anchor_slot:
            continue
        if slot_name in slots1 and slot_name in slots2:
            total_weight += weight
            if slots1[slot_name].item_id == slots2[slot_name].item_id:
                matching_weight += weight

    if total_weight <= 0.0:
        return 0.0
    return matching_weight / total_weight


def rerank_looks_for_diversity(
    looks: Sequence[CompleteLook],
    limit: int = 10,
    anchor_slot: Optional[str] = None,
    diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT,
) -> list[CompleteLook]:
    """Deterministically select a diverse subset of complete looks using greedy marginal diversity.

    Objective:
    Balance outfit compatibility quality with aesthetic and product diversity across primary slots.
    Preserves exact CompleteLook compatibility_score semantics (unmodified).
    Uses strict deterministic tie-breaking:
    1. Diversity-adjusted selection score descending.
    2. Raw compatibility score descending.
    3. Total catalog price ascending.
    4. Slot count descending (more complete looks preferred).
    5. Look ID ascending (lexicographical tie-break).
    """
    if limit <= 0 or not looks:
        return []

    # Filter duplicates by look_id while preserving stable order
    unique_candidates: list[CompleteLook] = []
    seen_ids: set[str] = set()
    for look in looks:
        if look.look_id not in seen_ids:
            seen_ids.add(look.look_id)
            unique_candidates.append(look)

    # Initial sort by base quality
    def _base_sort_key(l: CompleteLook) -> tuple[float, float, int, str]:
        return (-l.compatibility_score, l.total_catalog_price, -len(l.slots), l.look_id)

    unique_candidates.sort(key=_base_sort_key)

    selected: list[CompleteLook] = []
    remaining = list(unique_candidates)

    # Step 1: Pick the highest-ranked candidate as the first result
    first = remaining.pop(0)
    selected.append(first)

    # Step 2: Greedily pick subsequent candidates maximizing marginal diversity
    while len(selected) < limit and remaining:
        def _selection_key(candidate: CompleteLook) -> tuple[float, float, float, int, str]:
            max_sim = max(
                compute_look_similarity(candidate, sel, anchor_slot=anchor_slot)
                for sel in selected
            )
            adj_score = candidate.compatibility_score - (diversity_weight * 100.0 * max_sim)
            return (
                -round(adj_score, 4),
                -candidate.compatibility_score,
                candidate.total_catalog_price,
                -len(candidate.slots),
                candidate.look_id,
            )

        remaining.sort(key=_selection_key)
        selected.append(remaining.pop(0))

    return selected


def assemble_look_combinations(
    candidate_pool: Mapping[str, Sequence[LookItem]],
    slot_definitions: Sequence[LookSlotDefinition] = DEFAULT_OUTFIT_SLOTS,
    max_budget: Optional[float] = None,
    anchor_slot: Optional[str] = None,
    anchor_item: Optional[LookItem] = None,
    target_occasion: Optional[str] = None,
    target_aesthetic: Optional[str] = None,
    max_combinations: int = 50,
    diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT,
    limit: Optional[int] = None,
) -> list[CompleteLook]:
    """Assemble valid complete looks from per-slot candidate pools.

    Enforces:
    - Exactly 1 item per slot.
    - Required slots must have candidates; looks without required slots are omitted.
    - No duplicate products in the same look.
    - Budget limit (catalog price sum <= max_budget).
    - Anchor item locked to anchor slot if provided.
    - Flexible slot cardinality: supports partial outfits (2-piece, 3-piece, 4-piece)
      when full outfits exceed budget or are unavailable.
    - Complete outfits preferred when feasible.
    - Deterministic capping, stable tie-breaking, and greedy diversity re-ranking.
    """
    if limit is not None:
        max_combinations = limit
    if max_combinations < 1:
        return []

    # 1. Determine required slots and anchor slot
    req_slot_names = [s.name for s in slot_definitions if s.is_required]
    if anchor_slot and anchor_item and anchor_slot not in req_slot_names:
        req_slot_names.append(anchor_slot)

    # 2. Build candidate map per available slot
    avail_slots: dict[str, list[LookItem]] = {}
    for s_def in slot_definitions:
        if anchor_slot and anchor_item and s_def.name == anchor_slot:
            avail_slots[s_def.name] = [anchor_item]
        elif s_def.name in candidate_pool and candidate_pool[s_def.name]:
            avail_slots[s_def.name] = list(candidate_pool[s_def.name])

    # If any required slot (or anchor slot) is missing candidates, cannot assemble valid looks
    for r_name in req_slot_names:
        if r_name not in avail_slots or not avail_slots[r_name]:
            return []

    # Optional slots available for combination
    opt_slot_names = [
        s_def.name
        for s_def in slot_definitions
        if s_def.name in avail_slots and s_def.name not in req_slot_names
    ]

    # 3. Explore slot configurations ordered by cardinality descending
    k_max = len(req_slot_names) + len(opt_slot_names)
    k_min = len(req_slot_names)

    candidate_looks: list[CompleteLook] = []
    seen_look_ids: set[str] = set()

    for k in range(k_max, k_min - 1, -1):
        num_opt = k - len(req_slot_names)
        for opt_combo in combinations(opt_slot_names, num_opt):
            cfg_slots = list(req_slot_names) + list(opt_combo)

            # Divide into core slots (top, bottom if present) and secondary slots
            core_slots = [s for s in ["top", "bottom"] if s in cfg_slots]
            if not core_slots:
                core_slots = [cfg_slots[0]]
            sec_slots = [s for s in cfg_slots if s not in core_slots]

            core_pools = [avail_slots[s] for s in core_slots]
            sec_pools = [avail_slots[s] for s in sec_slots]

            # Dynamic completions per core pair
            num_core = 1
            for cp in core_pools:
                num_core *= len(cp)
            max_per_core = max(2, (max_combinations * 2) // max(1, num_core))

            for core_items in product(*core_pools):
                # Check duplicate item IDs in core
                core_ids = [it.item_id for it in core_items]
                if len(core_ids) != len(set(core_ids)):
                    continue

                # Check budget on core items
                core_catalog_price = sum(
                    it.price
                    for it in core_items
                    if it.source == "catalog" and it.price is not None
                )
                if max_budget is not None and core_catalog_price > max_budget:
                    continue

                if not sec_slots:
                    slots_map = dict(zip(core_slots, core_items))
                    look_id = compute_look_id(slots_map)
                    if look_id in seen_look_ids:
                        continue
                    seen_look_ids.add(look_id)

                    bd = evaluate_look_compatibility(
                        slots_map,
                        target_occasion=target_occasion,
                        target_aesthetic=target_aesthetic,
                    )
                    w_count = sum(1 for it in core_items if it.source == "wardrobe")
                    c_count = sum(1 for it in core_items if it.source == "catalog")
                    has_fixtures = any(
                        it.is_synthetic or it.is_fixture for it in core_items
                    )

                    candidate_looks.append(
                        CompleteLook(
                            look_id=look_id,
                            slots=slots_map,
                            total_catalog_price=round(core_catalog_price, 2),
                            currency="INR",
                            compatibility_score=bd.total_score,
                            compatibility_breakdown=bd,
                            compatibility_reasons=bd.reasons,
                            unresolved_constraints=bd.warnings,
                            is_wardrobe_aware=w_count > 0,
                            wardrobe_item_count=w_count,
                            catalog_item_count=c_count,
                            contains_synthetic_fixtures=has_fixtures,
                        )
                    )
                else:
                    # Sample secondary pools to bound evaluation space
                    max_sec_per_slot = max(3, int(125 ** (1.0 / len(sec_pools))))
                    sec_sample_pools = [p[:max_sec_per_slot] for p in sec_pools]
                    core_completions: list[CompleteLook] = []

                    for sec_items in product(*sec_sample_pools):
                        all_items = list(core_items) + list(sec_items)
                        all_ids = [it.item_id for it in all_items]
                        if len(all_ids) != len(set(all_ids)):
                            continue

                        sec_price = sum(
                            it.price
                            for it in sec_items
                            if it.source == "catalog" and it.price is not None
                        )
                        total_price = core_catalog_price + sec_price
                        if max_budget is not None and total_price > max_budget:
                            continue

                        slots_map = dict(zip(core_slots + sec_slots, all_items))
                        look_id = compute_look_id(slots_map)
                        if look_id in seen_look_ids:
                            continue

                        bd = evaluate_look_compatibility(
                            slots_map,
                            target_occasion=target_occasion,
                            target_aesthetic=target_aesthetic,
                        )
                        w_count = sum(1 for it in all_items if it.source == "wardrobe")
                        c_count = sum(1 for it in all_items if it.source == "catalog")
                        has_fixtures = any(
                            it.is_synthetic or it.is_fixture for it in all_items
                        )

                        core_completions.append(
                            CompleteLook(
                                look_id=look_id,
                                slots=slots_map,
                                total_catalog_price=round(total_price, 2),
                                currency="INR",
                                compatibility_score=bd.total_score,
                                compatibility_breakdown=bd,
                                compatibility_reasons=bd.reasons,
                                unresolved_constraints=bd.warnings,
                                is_wardrobe_aware=w_count > 0,
                                wardrobe_item_count=w_count,
                                catalog_item_count=c_count,
                                contains_synthetic_fixtures=has_fixtures,
                            )
                        )

                    core_completions.sort(
                        key=lambda l: (
                            -l.compatibility_score,
                            l.total_catalog_price,
                            -len(l.slots),
                            l.look_id,
                        )
                    )
                    for comp in core_completions[:max_per_core]:
                        seen_look_ids.add(comp.look_id)
                        candidate_looks.append(comp)

        # Prefer complete outfits: if cardinality k provided feasible looks,
        # do not descend to smaller partial configurations (which are only used
        # when full-slot assembly fails or exceeds budget).
        if candidate_looks:
            break

    # 4. Rerank for diversity deterministically
    return rerank_looks_for_diversity(
        candidate_looks,
        limit=max_combinations,
        anchor_slot=anchor_slot,
        diversity_weight=diversity_weight,
    )


def rank_complete_looks(looks: Sequence[CompleteLook]) -> list[CompleteLook]:
    """Sort complete looks deterministically.

    Order:
    1. Compatibility score descending.
    2. Total catalog price ascending.
    3. Number of filled slots descending.
    4. Look ID ascending (lexical tie-break).
    """

    def _sort_key(look: CompleteLook) -> tuple[float, float, int, str]:
        return (
            -look.compatibility_score,
            look.total_catalog_price,
            -len(look.slots),
            look.look_id,
        )

    return sorted(looks, key=_sort_key)

