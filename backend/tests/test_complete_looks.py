"""Tests for Complete Looks Assembly (TASK DISCOVERY-04).

Covers:
- Valid slot assembly (required vs optional slots).
- Category integrity and no duplicate products.
- Multi-dimensional compatibility evaluation (color, material, season, style concept, silhouette).
- Budget enforcement (catalog price sum <= max_budget, wardrobe items cost ₹0).
- Wardrobe-aware assembly: wardrobe items filling slots and complementary catalog items.
- Catalog-only fallback when wardrobe is unavailable.
- Anchor item support (anchoring to an owned wardrobe item or catalog product).
- Privacy & owner scoping (User A cannot anchor User B's wardrobe item).
- Deterministic repeated results and tie-breaking.
- Honest handling of missing attributes (neutral scoring, no fabrication).
- Explicit synthetic fixture labeling.
- Database integration test against real seeded catalog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.collection import CollectSource, CollectionConfig
from app.application.complete_looks import (
    AssembleCompleteLooks,
    CompleteLooksResult,
)
from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductFilterCriteria,
    WardrobeItemRecord,
)
from app.domain.services.candidate_filters import filter_candidate
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.domain.services.grounded_explanations import format_complete_look_explanation
from app.domain.services.outfit_compatibility import (
    DEFAULT_OUTFIT_SLOTS,
    CompleteLook,
    LookItem,
    LookSlotDefinition,
    assemble_look_combinations,
    compute_look_similarity,
    evaluate_look_compatibility,
    rank_complete_looks,
    rerank_looks_for_diversity,
)
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.external.fashion_catalog_seed import (
    FASHION_SEED_SOURCE_ID,
    FashionCatalogSeedAdapter,
)
from tests.conftest import make_session


# ---------------------------------------------------------------------------
# In-Memory Test Fakes
# ---------------------------------------------------------------------------


class FakeCandidateRepository:
    def __init__(self, products: Optional[list[CatalogProductRecord]] = None) -> None:
        self.products: list[CatalogProductRecord] = list(products or [])

    def get_by_id(self, product_id: UUID) -> Optional[CatalogProductRecord]:
        for p in self.products:
            if p.id == product_id:
                return p
        return None

    def _matches(self, p: CatalogProductRecord, criteria: ProductFilterCriteria) -> bool:
        bridge = map_product_attributes_to_ffo(p)
        return filter_candidate(p, criteria, bridge_result=bridge)

    def count_candidates(self, criteria: ProductFilterCriteria) -> int:
        return sum(1 for p in self.products if self._matches(p, criteria))

    def get_candidates(
        self,
        criteria: ProductFilterCriteria,
        *,
        sort_order: str = "newest",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[CatalogProductRecord, ...]:
        matched = [p for p in self.products if self._matches(p, criteria)]
        return tuple(matched[offset : offset + limit])


class FakeWardrobeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, list[WardrobeItemRecord]] = {}

    def get_for_user(
        self, *, user_id: UUID, page: int = 1, page_size: int = 100, **kwargs
    ) -> tuple[list[WardrobeItemRecord], int]:
        user_items = self.items.get(user_id, [])
        offset = (page - 1) * page_size
        return user_items[offset : offset + page_size], len(user_items)

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> Optional[WardrobeItemRecord]:
        for it in self.items.get(user_id, []):
            if it.id == item_id:
                return it
        return None


def _make_look_item(
    *,
    id: Optional[UUID] = None,
    source: str = "catalog",
    title: str = "Item Title",
    category: str = "tops",
    color: str = "navy",
    material: str = "linen",
    fit: str = "relaxed",
    silhouette: str = "oversized",
    price: float = 2000.0,
    ffo_concepts: tuple[str, ...] = ("minimalist",),
    is_synthetic: bool = True,
    is_fixture: bool = True,
) -> LookItem:
    return LookItem(
        item_id=id or uuid4(),
        source=source,
        title=title,
        category=category,
        color=color,
        material=material,
        fit=fit,
        silhouette=silhouette,
        price=price if source == "catalog" else 0.0,
        currency="INR",
        is_synthetic=is_synthetic,
        is_fixture=is_fixture,
        ffo_concepts=ffo_concepts,
    )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


def test_valid_slot_assembly_and_required_vs_optional_slots() -> None:
    """Verify that required slots (top + bottom) assemble, and optional slots are included when available."""
    top = _make_look_item(category="tops", color="white", material="cotton")
    bottom = _make_look_item(category="bottoms", color="navy", material="denim")
    footwear = _make_look_item(category="footwear", color="white", material="leather")

    pool = {
        "top": [top],
        "bottom": [bottom],
        "footwear": [footwear],
    }

    # 1. Standard slots with footwear
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS)
    assert len(looks) == 1
    look = looks[0]
    assert "top" in look.slots
    assert "bottom" in look.slots
    assert "footwear" in look.slots
    assert look.slots["top"].category == "tops"
    assert look.slots["bottom"].category == "bottoms"
    assert look.slots["footwear"].category == "footwear"
    assert look.compatibility_score > 50.0

    # 2. If a required slot is missing (e.g. no bottom), assembly yields 0 looks
    incomplete_pool = {"top": [top], "footwear": [footwear]}
    looks_incomplete = assemble_look_combinations(incomplete_pool, DEFAULT_OUTFIT_SLOTS)
    assert len(looks_incomplete) == 0

    # 3. If an optional slot is missing (e.g. no outerwear or footwear), assembly still succeeds
    top_bottom_only_pool = {"top": [top], "bottom": [bottom]}
    looks_core = assemble_look_combinations(top_bottom_only_pool, DEFAULT_OUTFIT_SLOTS)
    assert len(looks_core) == 1
    assert "top" in looks_core[0].slots
    assert "bottom" in looks_core[0].slots
    assert "footwear" not in looks_core[0].slots


def test_no_duplicate_products_in_same_look() -> None:
    """Verify that the same product cannot be assigned to multiple slots in one look."""
    shared_id = uuid4()
    item_as_top = _make_look_item(id=shared_id, category="tops")
    item_as_bottom = _make_look_item(id=shared_id, category="bottoms")

    pool = {
        "top": [item_as_top],
        "bottom": [item_as_bottom],
    }

    # Should be rejected because item_ids collision
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS)
    assert len(looks) == 0


def test_budget_enforcement_and_wardrobe_zero_cost() -> None:
    """Verify that total catalog price does not exceed max_budget and wardrobe items cost ₹0."""
    catalog_top = _make_look_item(
        source="catalog", category="tops", price=3000.0
    )
    catalog_bottom = _make_look_item(
        source="catalog", category="bottoms", price=4000.0
    )
    wardrobe_bottom = _make_look_item(
        source="wardrobe", category="bottoms", price=0.0
    )

    # 1. Catalog top (3000) + Catalog bottom (4000) = 7000. With budget 5000, must be excluded.
    pool_expensive = {
        "top": [catalog_top],
        "bottom": [catalog_bottom],
    }
    looks_over = assemble_look_combinations(
        pool_expensive, DEFAULT_OUTFIT_SLOTS, max_budget=5000.0
    )
    assert len(looks_over) == 0

    # 2. Catalog top (3000) + Wardrobe bottom (0) = 3000. With budget 5000, must pass!
    pool_wardrobe = {
        "top": [catalog_top],
        "bottom": [wardrobe_bottom],
    }
    looks_within = assemble_look_combinations(
        pool_wardrobe, DEFAULT_OUTFIT_SLOTS, max_budget=5000.0
    )
    assert len(looks_within) == 1
    assert looks_within[0].total_catalog_price == 3000.0
    assert looks_within[0].is_wardrobe_aware is True
    assert looks_within[0].wardrobe_item_count == 1
    assert looks_within[0].catalog_item_count == 1


def test_wardrobe_aware_assembly_and_catalog_fallback() -> None:
    """Verify that wardrobe items fill slots when enabled, and catalog-only fallback occurs when disabled."""
    top_p = CatalogProductRecord(
        id=uuid4(),
        title="Catalog Oxford Shirt",
        category="tops",
        price=2499.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/top.jpg",),
        attributes={"color": "white", "material": "cotton", "synthetic": True, "fixture": True},
    )
    bot_p = CatalogProductRecord(
        id=uuid4(),
        title="Catalog Chinos",
        category="bottoms",
        price=2999.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/bottom.jpg",),
        attributes={"color": "beige", "material": "cotton", "synthetic": True, "fixture": True},
    )

    user_id = uuid4()
    owned_sneakers = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_id,
        name="Owned White Sneakers",
        category="footwear",
        color="white",
        material="leather",
        is_favorite=True,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    cand_repo = FakeCandidateRepository([top_p, bot_p])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [owned_sneakers]

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    # 1. Wardrobe-aware run with user_id: owned sneakers should fill the footwear slot!
    res_wardrobe = use_case(user_id=user_id, allow_wardrobe=True)
    assert res_wardrobe.total_looks >= 1
    look = res_wardrobe.looks[0]
    assert look.is_wardrobe_aware is True
    assert "footwear" in look.slots
    assert look.slots["footwear"].source == "wardrobe"
    assert look.slots["footwear"].item_id == owned_sneakers.id
    assert look.slots["top"].source == "catalog"
    assert look.slots["bottom"].source == "catalog"

    # 2. Catalog-only fallback: guest (user_id=None) or allow_wardrobe=False
    res_catalog_only = use_case(user_id=None, allow_wardrobe=False)
    assert res_catalog_only.total_looks >= 1
    c_look = res_catalog_only.looks[0]
    assert c_look.is_wardrobe_aware is False
    assert c_look.wardrobe_item_count == 0
    # Footwear is omitted because catalog has no footwear, but core top + bottom assemble cleanly
    assert "top" in c_look.slots
    assert "bottom" in c_look.slots
    assert "footwear" not in c_look.slots


def test_anchor_wardrobe_item_styling() -> None:
    """Verify that outfit assembly can be anchored around an owned wardrobe item."""
    top_p = CatalogProductRecord(
        id=uuid4(),
        title="Catalog Linen Shirt",
        category="tops",
        price=1999.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/top.jpg",),
        attributes={"color": "white", "material": "linen", "synthetic": True, "fixture": True},
    )
    user_id = uuid4()
    anchor_pants = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_id,
        name="My Favorite Navy Chinos",
        category="bottoms",
        color="navy",
        material="cotton",
        is_favorite=True,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    cand_repo = FakeCandidateRepository([top_p])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [anchor_pants]

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    res = use_case(
        user_id=user_id,
        anchor_wardrobe_item_id=anchor_pants.id,
    )
    assert res.total_looks == 1
    look = res.looks[0]
    assert look.slots["bottom"].item_id == anchor_pants.id
    assert look.slots["bottom"].source == "wardrobe"
    assert look.slots["top"].item_id == top_p.id
    assert look.slots["top"].source == "catalog"


def test_anchor_wardrobe_privacy_and_cross_user_boundary() -> None:
    """Verify that User A cannot anchor to User B's wardrobe item (fails closed)."""
    user_a = uuid4()
    user_b = uuid4()

    item_b = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_b,
        name="User B Private Pants",
        category="bottoms",
        color="black",
        material="wool",
        is_favorite=False,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_b] = [item_b]

    retrieval = RetrieveProductCandidates(FakeCandidateRepository([]))
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    # User A tries to anchor to User B's item ID
    with pytest.raises(ValueError, match="not found in user's wardrobe"):
        use_case(user_id=user_a, anchor_wardrobe_item_id=item_b.id)

    # Guest tries to anchor to a wardrobe item without user_id
    with pytest.raises(ValueError, match="without an authenticated user_id"):
        use_case(user_id=None, anchor_wardrobe_item_id=item_b.id)


def test_synthetic_fixture_labeling() -> None:
    """Verify that synthetic fixture products are explicitly flagged in complete looks."""
    p1 = _make_look_item(source="catalog", category="tops", is_synthetic=True, is_fixture=True)
    p2 = _make_look_item(source="catalog", category="bottoms", is_synthetic=False, is_fixture=False)

    pool = {"top": [p1], "bottom": [p2]}
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS)
    assert len(looks) == 1
    assert looks[0].contains_synthetic_fixtures is True
    assert looks[0].slots["top"].is_synthetic is True
    assert looks[0].slots["bottom"].is_synthetic is False


def test_deterministic_repeated_results() -> None:
    """Verify that identical inputs produce bit-for-bit identical complete looks across repeated calls."""
    top1 = _make_look_item(title="Top 1", category="tops", price=2000.0)
    top2 = _make_look_item(title="Top 2", category="tops", price=1500.0)
    bot = _make_look_item(title="Bot 1", category="bottoms", price=2500.0)

    pool = {"top": [top1, top2], "bottom": [bot]}

    run1 = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS)
    run2 = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS)

    assert len(run1) == len(run2)
    for l1, l2 in zip(run1, run2):
        assert l1.look_id == l2.look_id
        assert l1.compatibility_score == l2.compatibility_score
        assert l1.total_catalog_price == l2.total_catalog_price
        assert tuple(l1.slots.keys()) == tuple(l2.slots.keys())


def test_missing_attributes_handled_honestly() -> None:
    """Verify that unmapped FFO concepts and missing attributes do not fabricate claims."""
    # Product with no color, no material, no silhouette, no FFO concepts
    top = LookItem(
        item_id=uuid4(),
        source="catalog",
        title="Basic Tee",
        category="tops",
        color=None,
        material=None,
        fit=None,
        silhouette=None,
        price=999.0,
        currency="INR",
        ffo_concepts=(),
    )
    bottom = LookItem(
        item_id=uuid4(),
        source="catalog",
        title="Basic Pants",
        category="bottoms",
        color=None,
        material=None,
        fit=None,
        silhouette=None,
        price=1499.0,
        currency="INR",
        ffo_concepts=(),
    )

    breakdown = evaluate_look_compatibility({"top": top, "bottom": bottom})

    # Completeness gives 15.0 pts for top+bottom
    assert breakdown.category_completeness == 15.0
    # Missing colors and materials degrade neutrally, not 0 and not full
    assert breakdown.color_harmony == 12.5
    assert breakdown.material_consistency == 15.0
    assert breakdown.total_score > 0.0

    # Ensure no fabricated claims in reasons
    assert not any("color palette" in r for r in breakdown.reasons)
    assert not any("Natural fiber synergy" in r for r in breakdown.reasons)


# ---------------------------------------------------------------------------
# Database Integration Test (fansivibe_test seeded catalog)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DISCOVERY-09B: Diversity Re-Ranking and Flexible Cardinality Tests
# ---------------------------------------------------------------------------


def test_multiple_returned_looks_differ_in_meaningful_primary_slots() -> None:
    """1. Verify multiple returned looks differ in meaningful primary slots (top and bottom)."""
    top1 = _make_look_item(title="Ajrakh Cotton Shirt", category="tops", color="indigo", material="cotton", price=2299.0)
    top2 = _make_look_item(title="Oxford Button-Down", category="tops", color="white", material="cotton", price=2199.0)
    top3 = _make_look_item(title="Waffle Knit Top", category="tops", color="charcoal", material="cotton", price=1699.0)

    bot1 = _make_look_item(title="Carpenter Pants", category="bottoms", color="olive", material="cotton", price=3299.0)
    bot2 = _make_look_item(title="Chino Trousers", category="bottoms", color="beige", material="cotton", price=2499.0)
    bot3 = _make_look_item(title="Loose-Fit Jeans", category="bottoms", color="indigo", material="denim", price=2999.0)

    footwear = _make_look_item(title="Khadi Espadrilles", category="footwear", color="white", material="khadi", price=1599.0)
    outerwear = _make_look_item(title="Harrington Jacket", category="outerwear", color="navy", material="cotton", price=4499.0)
    acc = _make_look_item(title="Corduroy Cap", category="accessories", color="brown", material="corduroy", price=1099.0)

    pool = {
        "top": [top1, top2, top3],
        "bottom": [bot1, bot2, bot3],
        "footwear": [footwear],
        "outerwear": [outerwear],
        "accessories": [acc],
    }

    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=3)
    assert len(looks) == 3

    # Primary slots must differ meaningfully across returned looks
    top_ids = [l.slots["top"].item_id for l in looks]
    bottom_ids = [l.slots["bottom"].item_id for l in looks]

    assert len(set(top_ids)) >= 2, f"Expected varied tops, got {top_ids}"
    assert len(set(bottom_ids)) >= 2, f"Expected varied bottoms, got {bottom_ids}"
    # Verify no two consecutive looks have the exact same top AND bottom
    core_pairs = [(l.slots["top"].item_id, l.slots["bottom"].item_id) for l in looks]
    assert len(set(core_pairs)) == 3, f"Expected 3 distinct core pairs, got {core_pairs}"


def test_same_core_outfit_not_repeated_with_only_accessory_swaps() -> None:
    """2. Verify the same core outfit is not repeated with only accessory changes when diverse alternatives exist."""
    top1 = _make_look_item(title="Core Top 1", category="tops", color="navy", material="linen", price=2000.0)
    bot1 = _make_look_item(title="Core Bot 1", category="bottoms", color="beige", material="cotton", price=2500.0)

    top2 = _make_look_item(title="Core Top 2", category="tops", color="olive", material="cotton", price=2100.0)
    bot2 = _make_look_item(title="Core Bot 2", category="bottoms", color="charcoal", material="wool", price=2600.0)

    top3 = _make_look_item(title="Core Top 3", category="tops", color="white", material="cotton", price=1900.0)
    bot3 = _make_look_item(title="Core Bot 3", category="bottoms", color="black", material="cotton", price=2400.0)

    footwear = _make_look_item(category="footwear", color="white", material="leather", price=1500.0)
    outerwear = _make_look_item(category="outerwear", color="navy", material="wool", price=3000.0)

    acc1 = _make_look_item(title="Cap", category="accessories", price=500.0)
    acc2 = _make_look_item(title="Scarf", category="accessories", price=600.0)
    acc3 = _make_look_item(title="Tote", category="accessories", price=700.0)

    pool = {
        "top": [top1, top2, top3],
        "bottom": [bot1, bot2, bot3],
        "footwear": [footwear],
        "outerwear": [outerwear],
        "accessories": [acc1, acc2, acc3],
    }

    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=3)
    assert len(looks) == 3

    # All 3 returned looks must have distinct core (top, bottom) pairs rather than (top1, bot1) repeated 3 times with different accessories
    selected_cores = [(l.slots["top"].item_id, l.slots["bottom"].item_id) for l in looks]
    assert len(set(selected_cores)) == 3
    # Top 1 core must not appear more than once in the top 3
    top1_count = sum(1 for (t, b) in selected_cores if t == top1.item_id and b == bot1.item_id)
    assert top1_count == 1, "Core outfit 1 was repeated with accessory changes instead of selecting diverse cores!"


def test_identical_inputs_produce_identical_ordering() -> None:
    """3. Verify identical inputs produce 100% bit-for-bit identical results and ordering across runs."""
    top1 = _make_look_item(title="Top A", category="tops", price=1500.0)
    top2 = _make_look_item(title="Top B", category="tops", price=1800.0)
    bot1 = _make_look_item(title="Bot A", category="bottoms", price=2000.0)
    bot2 = _make_look_item(title="Bot B", category="bottoms", price=2200.0)
    footwear = _make_look_item(category="footwear", price=1200.0)

    pool = {"top": [top1, top2], "bottom": [bot1, bot2], "footwear": [footwear]}

    run1 = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=4)
    run2 = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=4)

    assert len(run1) == len(run2) == 4
    for i in range(len(run1)):
        assert run1[i].look_id == run2[i].look_id
        assert run1[i].compatibility_score == run2[i].compatibility_score
        assert run1[i].total_catalog_price == run2[i].total_catalog_price
        assert set(run1[i].slots.keys()) == set(run2[i].slots.keys())
        for slot in run1[i].slots:
            assert run1[i].slots[slot].item_id == run2[i].slots[slot].item_id


def test_higher_quality_candidates_not_discarded_for_trivial_diversity() -> None:
    """4. Verify higher-quality compatible candidates are not discarded for trivial diversity when the alternative is severely incompatible."""
    # Top 1 + Bot 1: Harmonious monochrome navy palette + natural materials (high score)
    top1 = _make_look_item(title="Navy Linen Shirt", category="tops", color="navy", material="linen", price=2000.0)
    bot1 = _make_look_item(title="Navy Linen Pants", category="bottoms", color="navy", material="linen", price=2500.0)

    # Top 2 + Bot 2: Severe clash (contrasting neon brights without neutrals, clashing materials)
    top2 = _make_look_item(title="Bright Orange Polyester Top", category="tops", color="orange", material="polyester", price=1500.0)
    bot2 = _make_look_item(title="Neon Lime Acrylic Pants", category="bottoms", color="lime", material="acrylic", price=1800.0)

    acc1 = _make_look_item(title="Leather Belt", category="accessories", color="navy", material="leather", price=800.0)
    acc2 = _make_look_item(title="Silk Scarf", category="accessories", color="navy", material="silk", price=900.0)

    pool = {
        "top": [top1, top2],
        "bottom": [bot1, bot2],
        "accessories": [acc1, acc2],
    }

    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=2)
    assert len(looks) == 2

    # Both selected looks should be the high-scoring combinations of Top 1 + Bot 1 with different accessories,
    # rather than picking the low-quality clashing Top 2 + Bot 2 combination
    assert looks[0].slots["top"].item_id == top1.item_id
    assert looks[1].slots["top"].item_id == top1.item_id
    assert looks[0].compatibility_score >= 60.0
    assert looks[1].compatibility_score >= 60.0
    assert all(l.slots["top"].item_id != top2.item_id for l in looks)


def test_feasible_full_outfit_preferred_when_appropriate() -> None:
    """5. Verify a feasible full outfit is preferred over partial outfits when budget and candidates permit."""
    top = _make_look_item(category="tops", price=2000.0)
    bottom = _make_look_item(category="bottoms", price=2500.0)
    footwear = _make_look_item(category="footwear", price=1500.0)
    outerwear = _make_look_item(category="outerwear", price=3000.0)
    acc = _make_look_item(category="accessories", price=1000.0)

    pool = {
        "top": [top],
        "bottom": [bottom],
        "footwear": [footwear],
        "outerwear": [outerwear],
        "accessories": [acc],
    }

    # Total full outfit is ₹10,000. Budget is ₹15,000.
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=15000.0, limit=1)
    assert len(looks) == 1
    # Full outfit must have all 5 slots
    assert len(looks[0].slots) == 5
    assert set(looks[0].slots.keys()) == {"top", "bottom", "footwear", "outerwear", "accessories"}
    assert looks[0].total_catalog_price == 10000.0


def test_valid_partial_outfit_returned_when_full_outfit_infeasible() -> None:
    """6. Verify a valid partial outfit can be returned when a full outfit is infeasible under budget constraints."""
    top = _make_look_item(title="Tee", category="tops", price=1500.0)
    bottom = _make_look_item(title="Shorts", category="bottoms", price=1500.0)
    footwear = _make_look_item(title="Boots", category="footwear", price=3000.0)
    outerwear = _make_look_item(title="Jacket", category="outerwear", price=5000.0)

    pool = {
        "top": [top],
        "bottom": [bottom],
        "footwear": [footwear],
        "outerwear": [outerwear],
    }

    # Full 4-piece outfit costs 1500+1500+3000+5000 = ₹11,000 (infeasible under ₹4,000 budget).
    # 3-piece with footwear costs 1500+1500+3000 = ₹6,000 (infeasible under ₹4,000 budget).
    # 2-piece (top + bottom) costs 1500+1500 = ₹3,000 (feasible under ₹4,000 budget!).
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=4000.0, limit=1)
    assert len(looks) == 1
    look = looks[0]
    assert len(look.slots) == 2
    assert "top" in look.slots
    assert "bottom" in look.slots
    assert "footwear" not in look.slots
    assert "outerwear" not in look.slots
    assert look.total_catalog_price == 3000.0
    assert look.slots["top"].item_id == top.item_id
    assert look.slots["bottom"].item_id == bottom.item_id


def test_low_budgets_produce_affordable_combinations_when_valid_candidates_exist() -> None:
    """7. Verify low budgets produce affordable combinations when valid cheaper candidates exist."""
    exp_top = _make_look_item(title="Expensive Shirt", category="tops", price=4500.0)
    cheap_top = _make_look_item(title="Affordable Tee", category="tops", price=1000.0)

    exp_bot = _make_look_item(title="Expensive Trousers", category="bottoms", price=5000.0)
    cheap_bot = _make_look_item(title="Affordable Shorts", category="bottoms", price=1200.0)

    pool = {
        "top": [exp_top, cheap_top],
        "bottom": [exp_bot, cheap_bot],
    }

    # Budget ₹3000: only cheap_top (1000) + cheap_bot (1200) = ₹2200 is affordable.
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=3000.0, limit=2)
    assert len(looks) == 1
    look = looks[0]
    assert look.total_catalog_price == 2200.0
    assert look.slots["top"].item_id == cheap_top.item_id
    assert look.slots["bottom"].item_id == cheap_bot.item_id


def test_every_returned_outfit_respects_max_budget() -> None:
    """8. Verify every returned outfit strictly respects max_budget across all combinations."""
    tops = [_make_look_item(category="tops", price=1000.0 * i) for i in range(1, 5)]
    bottoms = [_make_look_item(category="bottoms", price=1000.0 * i) for i in range(1, 5)]
    footwear = [_make_look_item(category="footwear", price=1000.0 * i) for i in range(1, 4)]

    pool = {"top": tops, "bottom": bottoms, "footwear": footwear}
    max_budget = 4000.0

    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=max_budget, limit=10)
    assert len(looks) > 0
    for look in looks:
        assert look.total_catalog_price <= max_budget, f"Look {look.look_id} price {look.total_catalog_price} exceeded {max_budget}"


def test_wardrobe_owned_items_contribute_zero_to_catalog_spend_extended() -> None:
    """9. Verify wardrobe-owned items contribute exactly ₹0 to catalog spend in complete looks."""
    w_top = _make_look_item(source="wardrobe", category="tops", price=0.0)
    c_bottom = _make_look_item(source="catalog", category="bottoms", price=4500.0)
    c_footwear = _make_look_item(source="catalog", category="footwear", price=1500.0)

    pool = {"top": [w_top], "bottom": [c_bottom], "footwear": [c_footwear]}
    # Budget ₹5000: w_top (0) + c_bottom (4500) = 4500 <= 5000 (feasible). Footwear (1500) makes it 6000 > 5000.
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=5000.0, limit=1)
    assert len(looks) == 1
    look = looks[0]
    assert look.total_catalog_price == 4500.0
    assert look.is_wardrobe_aware is True
    assert look.wardrobe_item_count == 1
    assert look.catalog_item_count == 1
    assert look.slots["top"].source == "wardrobe"
    assert look.slots["bottom"].source == "catalog"


def test_wardrobe_anchors_remain_present_and_owner_scoped_extended() -> None:
    """10. Verify wardrobe anchors remain present in all returned looks and enforce owner-scoping."""
    user_a = uuid4()
    user_b = uuid4()

    owned_jacket = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_a,
        name="User A Linen Jacket",
        category="outerwear",
        color="beige",
        material="linen",
        is_favorite=True,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    top = CatalogProductRecord(
        id=uuid4(),
        title="Linen Shirt",
        category="tops",
        price=2000.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/top.jpg",),
        attributes={"color": "white", "material": "linen", "synthetic": True, "fixture": True},
    )
    bottom = CatalogProductRecord(
        id=uuid4(),
        title="Linen Shorts",
        category="bottoms",
        price=1800.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/bot.jpg",),
        attributes={"color": "beige", "material": "linen", "synthetic": True, "fixture": True},
    )

    cand_repo = FakeCandidateRepository([top, bottom])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_a] = [owned_jacket]

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    # 1. User A successfully anchors to their own jacket
    res = use_case(user_id=user_a, anchor_wardrobe_item_id=owned_jacket.id, limit=3)
    assert res.total_looks >= 1
    for look in res.looks:
        assert "outerwear" in look.slots
        assert look.slots["outerwear"].item_id == owned_jacket.id
        assert look.slots["outerwear"].source == "wardrobe"
        assert look.slots["outerwear"].price == 0.0

    # 2. User B cannot anchor to User A's jacket
    with pytest.raises(ValueError, match="not found in user's wardrobe"):
        use_case(user_id=user_b, anchor_wardrobe_item_id=owned_jacket.id)


def test_missing_optional_slots_represented_truthfully() -> None:
    """11. Verify missing optional slots are represented truthfully without placeholder items."""
    top = _make_look_item(title="Basic White Tee", category="tops", price=999.0)
    bottom = _make_look_item(title="Basic Black Jeans", category="bottoms", price=1499.0)

    pool = {"top": [top], "bottom": [bottom]}
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=1)
    assert len(looks) == 1
    look = looks[0]

    # Exactly 2 slots present
    assert set(look.slots.keys()) == {"top", "bottom"}
    assert "footwear" not in look.slots
    assert "outerwear" not in look.slots
    assert "accessories" not in look.slots

    # Grounded explanation truthfully states 2-piece look with zero fabricated items
    explanation = format_complete_look_explanation(look)
    assert "2-piece" in explanation.summary
    assert not any("footwear" in r.lower() for r in explanation.reasons)
    assert not any("outerwear" in r.lower() for r in explanation.reasons)


def test_no_feasible_outfit_produces_honest_empty_result() -> None:
    """12. Verify no feasible outfit produces an honest empty result when budget cannot be met."""
    top = _make_look_item(category="tops", price=2500.0)
    bottom = _make_look_item(category="bottoms", price=3000.0)

    pool = {"top": [top], "bottom": [bottom]}
    # Minimum outfit is ₹5500. Budget is ₹2000.
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, max_budget=2000.0, limit=5)
    assert looks == []


def test_existing_compatibility_score_semantics_remain_unchanged() -> None:
    """13. Verify existing compatibility score semantics remain unchanged after diversity reranking."""
    top = _make_look_item(category="tops", color="navy", material="linen", price=2000.0)
    bottom = _make_look_item(category="bottoms", color="navy", material="linen", price=2500.0)
    footwear = _make_look_item(category="footwear", color="white", material="leather", price=1500.0)

    pool = {"top": [top], "bottom": [bottom], "footwear": [footwear]}
    looks = assemble_look_combinations(pool, DEFAULT_OUTFIT_SLOTS, limit=1)
    assert len(looks) == 1
    look = looks[0]

    expected_bd = evaluate_look_compatibility(look.slots)
    assert look.compatibility_score == expected_bd.total_score
    assert look.compatibility_breakdown.category_completeness == expected_bd.category_completeness
    assert look.compatibility_breakdown.color_harmony == expected_bd.color_harmony
    assert look.compatibility_breakdown.material_consistency == expected_bd.material_consistency
    assert look.compatibility_breakdown.style_concept_match == expected_bd.style_concept_match
    assert look.compatibility_breakdown.silhouette_formality == expected_bd.silhouette_formality
    # Scores must stay within [0.0, 100.0]
    assert 0.0 <= look.compatibility_score <= 100.0


def test_guest_isolation_and_cross_user_wardrobe_protection_extended() -> None:
    """14. Verify guest isolation and cross-user wardrobe protection remain strictly intact."""
    user_id = uuid4()
    owned_sneakers = WardrobeItemRecord(
        id=uuid4(),
        user_id=user_id,
        name="Private White Sneakers",
        category="footwear",
        color="white",
        material="leather",
        is_favorite=True,
        image_ref=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    top = CatalogProductRecord(
        id=uuid4(),
        title="Catalog Shirt",
        category="tops",
        price=1999.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/top.jpg",),
        attributes={"color": "white", "material": "cotton", "synthetic": True, "fixture": True},
    )
    bottom = CatalogProductRecord(
        id=uuid4(),
        title="Catalog Trousers",
        category="bottoms",
        price=2499.0,
        currency="INR",
        availability=True,
        image_urls=("https://cdn.example.com/bot.jpg",),
        attributes={"color": "navy", "material": "cotton", "synthetic": True, "fixture": True},
    )

    cand_repo = FakeCandidateRepository([top, bottom])
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [owned_sneakers]

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    # 1. Guest request (user_id=None, allow_wardrobe=False) cannot access wardrobe
    guest_res = use_case(user_id=None, allow_wardrobe=False)
    assert guest_res.is_wardrobe_aware is False
    for look in guest_res.looks:
        assert look.is_wardrobe_aware is False
        assert look.wardrobe_item_count == 0
        assert all(it.source == "catalog" for it in look.slots.values())

    # 2. Guest attempting to anchor to a wardrobe item raises ValueError
    with pytest.raises(ValueError, match="without an authenticated user_id"):
        use_case(user_id=None, anchor_wardrobe_item_id=owned_sneakers.id)


# ---------------------------------------------------------------------------
# Database Integration Test (fansivibe_test seeded catalog)
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_db(db):
    """Seed the 60 realistic fashion products into test database and yield session."""
    Session = make_session()
    adapter = FashionCatalogSeedAdapter()
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        service = CollectSource(adapter=adapter, repository=repo)
        service(CollectionConfig(source=FASHION_SEED_SOURCE_ID, max_records=200))

    with Session() as session:
        yield session


def test_complete_looks_database_assembly(seeded_db) -> None:
    """Verify Complete Looks assembly using the real 60-product seeded catalog."""
    cand_repo = DiscoveryRepositorySQL(seeded_db)
    wardrobe_repo = WardrobeItemRepositorySQL(seeded_db)

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = AssembleCompleteLooks(retrieval, wardrobe_repo)

    # 1. Assemble looks across catalog products (catalog-only)
    res = use_case(user_id=None, allow_wardrobe=False, limit=5)

    assert res.total_looks > 0
    top_look = res.looks[0]
    assert "top" in top_look.slots
    assert "bottom" in top_look.slots
    assert top_look.slots["top"].category == "tops"
    assert top_look.slots["bottom"].category == "bottoms"
    assert top_look.total_catalog_price > 0.0
    assert top_look.compatibility_score > 0.0
    assert top_look.contains_synthetic_fixtures is True
    assert len(top_look.compatibility_reasons) > 0

    # 2. Budget-constrained run: max budget ₹8000
    res_budget = use_case(user_id=None, max_budget=8000.0, limit=5)
    for look in res_budget.looks:
        assert look.total_catalog_price <= 8000.0

