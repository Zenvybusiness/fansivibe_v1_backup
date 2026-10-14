"""Complete Looks assembly application use case for Fansivibe Discovery (DISCOVERY-04).

Orchestrates multi-category outfit assembly across catalog products and owned wardrobe items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence
from uuid import UUID

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.domain.ports.repositories import (
    ProductFilterCriteria,
    WardrobeItemRepository,
)
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.domain.services.outfit_compatibility import (
    CANONICAL_SLOT_CATEGORIES,
    DEFAULT_DIVERSITY_WEIGHT,
    DEFAULT_OUTFIT_SLOTS,
    CompleteLook,
    LookItem,
    LookSlotDefinition,
    assemble_look_combinations,
    catalog_product_to_look_item,
    wardrobe_item_to_look_item,
)


@dataclass(frozen=True)
class CompleteLooksResult:
    """Result of complete looks assembly."""

    looks: tuple[CompleteLook, ...]
    total_looks: int
    target_occasion: Optional[str] = None
    target_aesthetic: Optional[str] = None
    max_budget: Optional[float] = None
    anchor_item: Optional[LookItem] = None
    is_wardrobe_aware: bool = False
    slot_definitions: tuple[LookSlotDefinition, ...] = field(
        default_factory=lambda: DEFAULT_OUTFIT_SLOTS
    )


class AssembleCompleteLooks:
    """Application use case for assembling coordinated, multi-category looks.

    Invariants:
    - Enforces category integrity (1 item per slot, no duplicates in a look).
    - Hard budget constraints: catalog item total price <= max_budget.
    - Owner-scoped wardrobe access: guest/unauthenticated requests (user_id=None) cannot access any wardrobe data.
    - Anchored styling: locks outfit generation around a specific wardrobe piece or catalog product when requested.
    - Transparent synthetic labeling: explicitly flags fixture products.
    """

    def __init__(
        self,
        candidate_retrieval: RetrieveProductCandidates,
        wardrobe_repo: Optional[WardrobeItemRepository] = None,
    ) -> None:
        self._retrieval = candidate_retrieval
        self._wardrobe_repo = wardrobe_repo

    def __call__(
        self,
        *,
        user_id: Optional[UUID] = None,
        anchor_wardrobe_item_id: Optional[UUID] = None,
        anchor_product_id: Optional[UUID] = None,
        target_occasion: Optional[str] = None,
        target_aesthetic: Optional[str] = None,
        max_budget: Optional[float] = None,
        slot_definitions: Optional[Sequence[LookSlotDefinition]] = None,
        limit: int = 10,
        allow_wardrobe: bool = True,
        include_synthetic: bool = True,
        candidates_per_slot: int = 10,
        diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT,
    ) -> CompleteLooksResult:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if max_budget is not None and max_budget < 0:
            raise ValueError("max_budget must be non-negative")

        effective_slots = tuple(slot_definitions or DEFAULT_OUTFIT_SLOTS)

        # 1. Resolve Anchor Item if specified
        resolved_anchor_item: Optional[LookItem] = None
        anchor_slot_name: Optional[str] = None

        if anchor_wardrobe_item_id is not None:
            # Privacy & owner-scoping guard: user_id is mandatory to anchor a wardrobe item
            if user_id is None:
                raise ValueError(
                    "Cannot anchor to a wardrobe item without an authenticated user_id"
                )
            if self._wardrobe_repo is None:
                raise ValueError("Wardrobe repository is not configured")

            wardrobe_record = self._wardrobe_repo.get_by_id(
                user_id=user_id, item_id=anchor_wardrobe_item_id
            )
            if wardrobe_record is None:
                # Owner-scoped: unknown or foreign item ID fails closed
                raise ValueError(
                    f"Wardrobe item {anchor_wardrobe_item_id} not found in user's wardrobe"
                )

            # Bridge wardrobe item attributes to FFO concepts
            w_bridge = map_product_attributes_to_ffo(
                {
                    "id": wardrobe_record.id,
                    "title": wardrobe_record.name,
                    "category": wardrobe_record.category,
                    "attributes": {
                        "color": wardrobe_record.color,
                        "material": wardrobe_record.material,
                        "fit": wardrobe_record.fit,
                    },
                }
            )
            resolved_anchor_item = wardrobe_item_to_look_item(
                wardrobe_record, bridge=w_bridge
            )

            # Determine matching slot name for anchor item
            for s_def in effective_slots:
                if s_def.category == resolved_anchor_item.category:
                    anchor_slot_name = s_def.name
                    break

        elif anchor_product_id is not None:
            # Fetch catalog product by ID via candidate repo
            prod_record = self._retrieval._repo.get_by_id(anchor_product_id)
            if prod_record is None:
                raise ValueError(
                    f"Catalog product {anchor_product_id} not found"
                )
            p_bridge = map_product_attributes_to_ffo(prod_record)
            resolved_anchor_item = catalog_product_to_look_item(
                prod_record, bridge=p_bridge
            )
            for s_def in effective_slots:
                if s_def.category == (prod_record.category or "").strip().lower():
                    anchor_slot_name = s_def.name
                    break

        # 2. Retrieve owned wardrobe items if user is authenticated and wardrobe enabled
        wardrobe_items_by_cat: dict[str, list[LookItem]] = {}
        is_wardrobe_enabled = allow_wardrobe and (user_id is not None)

        if is_wardrobe_enabled and self._wardrobe_repo is not None:
            owned_records, _ = self._wardrobe_repo.get_for_user(
                user_id=user_id, page=1, page_size=100
            )
            for w_rec in owned_records:
                cat = (w_rec.category or "").strip().lower()
                w_bridge = map_product_attributes_to_ffo(
                    {
                        "id": w_rec.id,
                        "title": w_rec.name,
                        "category": w_rec.category,
                        "attributes": {
                            "color": w_rec.color,
                            "material": w_rec.material,
                            "fit": w_rec.fit,
                        },
                    }
                )
                l_item = wardrobe_item_to_look_item(w_rec, bridge=w_bridge)
                wardrobe_items_by_cat.setdefault(cat, []).append(l_item)

        # 3. Build candidate pool for each slot
        candidate_pool: dict[str, list[LookItem]] = {}

        for slot_def in effective_slots:
            slot_category = slot_def.category
            items_for_slot: list[LookItem] = []

            # (a) If wardrobe is enabled, add owned wardrobe items for this category first
            if is_wardrobe_enabled and slot_category in wardrobe_items_by_cat:
                items_for_slot.extend(wardrobe_items_by_cat[slot_category])

            # (b) Retrieve catalog candidate products for this category
            catalog_criteria = ProductFilterCriteria(
                categories=(slot_category,),
                in_stock_only=True,
                include_synthetic=include_synthetic,
                has_price=True,
            )
            catalog_result = self._retrieval(
                criteria=catalog_criteria,
                sort_order="newest",
                page=1,
                page_size=candidates_per_slot,
            )
            for cand in catalog_result.items:
                items_for_slot.append(
                    catalog_product_to_look_item(cand.product, cand.ffo_bridge)
                )

            candidate_pool[slot_def.name] = items_for_slot

        # 4. Assemble look combinations
        assembled = assemble_look_combinations(
            candidate_pool=candidate_pool,
            slot_definitions=effective_slots,
            max_budget=max_budget,
            anchor_slot=anchor_slot_name,
            anchor_item=resolved_anchor_item,
            target_occasion=target_occasion,
            target_aesthetic=target_aesthetic,
            max_combinations=limit,
            diversity_weight=diversity_weight,
        )

        return CompleteLooksResult(
            looks=tuple(assembled),
            total_looks=len(assembled),
            target_occasion=target_occasion,
            target_aesthetic=target_aesthetic,
            max_budget=max_budget,
            anchor_item=resolved_anchor_item,
            is_wardrobe_aware=any(l.is_wardrobe_aware for l in assembled),
            slot_definitions=effective_slots,
        )
