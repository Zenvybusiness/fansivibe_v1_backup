"""Tests for For You Personalization (TASK DISCOVERY-04).

Covers:
- Deterministic scoring formula and ranking.
- Explicit preferences affecting ranking.
- Hard filters excluding ineligible products.
- Neutral handling of missing preferences (no invented matches).
- Deterministic tie-breaking across equal scores.
- Budget boundaries and price filtering.
- Guest and cross-user privacy boundaries.
- Database integration test against seeded catalog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.collection import CollectSource, CollectionConfig
from app.application.for_you import ForYouPersonalizationResult, PersonalizeForYou
from app.domain.ports.repositories import (
    CatalogProductRecord,
    ProductCandidateRepository,
    ProductFilterCriteria,
    UserProfileRecord,
    UserStateRepository,
    WardrobeItemRecord,
    WardrobeItemRepository,
)
from app.domain.services.candidate_filters import filter_candidate
from app.domain.services.ffo_bridge import map_product_attributes_to_ffo
from app.domain.services.personalization import (
    CANONICAL_PREFERENCE_KEYS,
    PREFERENCE_KEY_ALIASES,
    PersonalizationPreferences,
    PersonalizationScoreBreakdown,
    UserPersonalizationContext,
    build_wardrobe_affinity_context,
    normalize_preferences,
    rank_personalized_candidates,
    score_product_candidate,
)
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    UserStateRepositorySQL,
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


class FakeUserStateRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, UserProfileRecord] = {}

    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]:
        p = self.profiles.get(user_id)
        return p.style_profile if p else None

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]:
        return self.profiles.get(user_id)

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        pass

    def update_style_profile(self, *, user_id: UUID, **kwargs) -> None:
        pass


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


# ---------------------------------------------------------------------------
# Unit Tests: Scoring, Preferences, Neutrality, Tie-Breaking
# ---------------------------------------------------------------------------


def _make_sample_product(
    *,
    id: Optional[UUID] = None,
    title: str = "Sample Linen Shirt",
    category: str = "tops",
    brand: str = "FabIndia",
    price: float = 2499.0,
    color: str = "navy",
    material: str = "linen",
    fit: str = "relaxed",
    silhouette: str = "oversized",
    style_tags: tuple[str, ...] = ("minimalist",),
    availability: bool = True,
    created_at: Optional[datetime] = None,
) -> CatalogProductRecord:
    attrs = {
        "color": color,
        "material": material,
        "fit": fit,
        "silhouette": silhouette,
        "style_tags": list(style_tags),
        "synthetic": True,
        "fixture": True,
    }
    return CatalogProductRecord(
        id=id or uuid4(),
        title=title,
        brand=brand,
        category=category,
        price=price,
        currency="INR",
        availability=availability,
        image_urls=("https://cdn.fansivibe.com/img1.jpg",),
        attributes=attrs,
        created_at=created_at or datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_explicit_preferences_affect_ranking_deterministically() -> None:
    """Verify that products matching explicit user preferences score higher."""
    prod_matching = _make_sample_product(
        title="Matching Linen Shirt",
        category="tops",
        brand="FabIndia",
        color="navy",
        material="linen",
        price=2499.0,
    )
    prod_other = _make_sample_product(
        title="Other Polyester Pants",
        category="bottoms",
        brand="Zara",
        color="charcoal",
        material="polyester",
        price=3999.0,
    )

    bridge_matching = map_product_attributes_to_ffo(prod_matching)
    bridge_other = map_product_attributes_to_ffo(prod_other)

    prefs = PersonalizationPreferences(
        preferred_categories=("tops",),
        preferred_brands=("FabIndia",),
        preferred_colors=("navy",),
        preferred_materials=("linen",),
    )
    context = UserPersonalizationContext(
        user_id=uuid4(),
        preferences=prefs,
    )

    breakdown_match = score_product_candidate(prod_matching, bridge_matching, context)
    breakdown_other = score_product_candidate(prod_other, bridge_other, context)

    # Matching candidate gains category (+10), brand (+10), color (+8), material (+6)
    assert breakdown_match.preference_match == 34.0
    assert breakdown_other.preference_match == 0.0
    assert breakdown_match.total_score > breakdown_other.total_score

    # Check explainability reasons
    assert any("category 'tops'" in r for r in breakdown_match.match_reasons)
    assert any("brand 'FabIndia'" in r for r in breakdown_match.match_reasons)
    assert any("color 'navy'" in r for r in breakdown_match.match_reasons)
    assert any("material 'linen'" in r for r in breakdown_match.match_reasons)


def test_missing_preferences_remain_neutral() -> None:
    """Verify that unknown/missing preferences do not penalize or reward products."""
    prod = _make_sample_product()
    bridge = map_product_attributes_to_ffo(prod)

    # Empty context: no preferences, no wardrobe, no style profile
    empty_context = UserPersonalizationContext(user_id=None, is_guest=True)
    breakdown = score_product_candidate(prod, bridge, empty_context)

    # Preference, style profile, and wardrobe scores are neutral 0.0
    assert breakdown.preference_match == 0.0
    assert breakdown.style_profile_match == 0.0
    assert breakdown.wardrobe_complementarity == 0.0
    # Availability + Price baseline (5.0 in-stock + 5.0 valid price + 5.0 within budget)
    assert breakdown.budget_availability == 15.0
    assert breakdown.total_score == 15.0

    # Ensure unmapped dimensions are recorded honestly
    assert "category_preference" in breakdown.neutral_dimensions
    assert "brand_preference" in breakdown.neutral_dimensions
    assert "color_preference" in breakdown.neutral_dimensions
    assert "wardrobe_context" in breakdown.neutral_dimensions


def test_deterministic_tie_breaking_order() -> None:
    """Verify stable ordering when scores are identical: created_at desc, then product_id asc."""
    id1 = UUID("00000000-0000-0000-0000-000000000001")
    id2 = UUID("00000000-0000-0000-0000-000000000002")

    t_earlier = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    t_later = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    # Two products with identical scores, but p2 was created later
    p1 = _make_sample_product(id=id1, created_at=t_earlier)
    p2 = _make_sample_product(id=id2, created_at=t_later)

    context = UserPersonalizationContext()
    ranked = rank_personalized_candidates(
        [(p1, map_product_attributes_to_ffo(p1)), (p2, map_product_attributes_to_ffo(p2))],
        context,
    )

    # Newer product must rank first
    assert ranked[0].id == id2
    assert ranked[1].id == id1

    # When created_at is also equal, lexical ID breaks tie
    p1_same_time = _make_sample_product(id=id1, created_at=t_earlier)
    p2_same_time = _make_sample_product(id=id2, created_at=t_earlier)

    ranked_id_tie = rank_personalized_candidates(
        [(p2_same_time, map_product_attributes_to_ffo(p2_same_time)), (p1_same_time, map_product_attributes_to_ffo(p1_same_time))],
        context,
    )
    # id1 ('...001') sorts before id2 ('...002')
    assert ranked_id_tie[0].id == id1
    assert ranked_id_tie[1].id == id2


def test_budget_boundaries_respected() -> None:
    """Verify that hard criteria exclude out-of-budget products before ranking."""
    cheap_p = _make_sample_product(title="Budget Tee", price=999.0)
    expensive_p = _make_sample_product(title="Luxury Jacket", price=12999.0)

    repo = FakeCandidateRepository([cheap_p, expensive_p])
    retrieval = RetrieveProductCandidates(repo)
    use_case = PersonalizeForYou(retrieval)

    # User set budget max_price = 3000
    prefs = PersonalizationPreferences(max_price=3000.0)
    res = use_case(preferences=prefs)

    assert res.total_count == 1
    assert res.items[0].product.id == cheap_p.id


def test_guest_cannot_access_user_data() -> None:
    """Verify that unauthenticated/guest contexts cannot access any stored user profile or wardrobe."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Private User",
        style_profile={"style_type": "streetwear"},
        preferences={"preferredCategories": ["tops"]},
        settings={},
        flags={},
        version=1,
    )
    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [
        WardrobeItemRecord(
            id=uuid4(),
            user_id=user_id,
            name="Secret Silk Shirt",
            category="tops",
            color="emerald",
            material="silk",
            is_favorite=True,
            image_ref=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    prod = _make_sample_product(category="tops", color="emerald", material="silk")
    candidate_repo = FakeCandidateRepository([prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
        wardrobe_repo=wardrobe_repo,
    )

    # 1. Calling as guest (user_id=None or is_guest=True)
    guest_res = use_case(user_id=None, is_guest=True)
    assert guest_res.applied_context.is_guest is True
    assert guest_res.applied_context.user_id is None
    assert guest_res.applied_context.display_name is None
    assert guest_res.applied_context.wardrobe_context.has_wardrobe is False
    assert guest_res.applied_context.style_profile == {}

    # 2. Even if an attacker passes is_guest=True with another user's ID
    guest_with_id_res = use_case(user_id=user_id, is_guest=True)
    assert guest_with_id_res.applied_context.is_guest is True
    assert guest_with_id_res.applied_context.user_id is None
    assert guest_with_id_res.applied_context.display_name is None
    assert guest_with_id_res.applied_context.wardrobe_context.has_wardrobe is False


def test_cross_user_isolation() -> None:
    """Verify that User A cannot see or be influenced by User B's profile or wardrobe."""
    user_a = uuid4()
    user_b = uuid4()

    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_a] = UserProfileRecord(
        user_id=user_a,
        display_name="User A",
        style_profile={"style_type": "quiet-luxury"},
        preferences={"preferredCategories": ["outerwear"]},
        settings={},
        flags={},
        version=1,
    )
    state_repo.profiles[user_b] = UserProfileRecord(
        user_id=user_b,
        display_name="User B",
        style_profile={"style_type": "streetwear"},
        preferences={"preferredCategories": ["bottoms"]},
        settings={},
        flags={},
        version=1,
    )

    p_outer = _make_sample_product(category="outerwear", price=5000.0)
    p_bottom = _make_sample_product(category="bottoms", price=5000.0)

    candidate_repo = FakeCandidateRepository([p_outer, p_bottom])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    res_a = use_case(user_id=user_a)
    res_b = use_case(user_id=user_b)

    # User A prefers outerwear, User B prefers bottoms
    assert res_a.applied_context.user_id == user_a
    assert res_a.applied_context.display_name == "User A"
    assert res_a.items[0].product.category == "outerwear"

    assert res_b.applied_context.user_id == user_b
    assert res_b.applied_context.display_name == "User B"
    assert res_b.items[0].product.category == "bottoms"


# ---------------------------------------------------------------------------
# DISCOVERY-09A: Preference Schema Normalization Regression Tests
# ---------------------------------------------------------------------------


def test_snake_case_preferred_occasions_affects_score() -> None:
    """1. Verify snake_case preferred_occasions in user profile affects style scoring."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Occasion User",
        style_profile={},
        preferences={"preferred_occasions": ["casual"]},
        settings={},
        flags={},
        version=1,
    )

    # Product in 'tops' is suitable for ('casual', 'office', 'date', 'party')
    top_prod = _make_sample_product(title="Casual Linen Shirt", category="tops", price=1999.0)
    candidate_repo = FakeCandidateRepository([top_prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    assert len(result.items) == 1
    item = result.items[0]

    # Style profile match must be +10.0 pts for occasion alignment
    assert item.breakdown.style_profile_match == 10.0
    assert item.breakdown.budget_availability == 15.0
    assert item.score == 25.0
    assert any("Suitable for preferred occasion(s): casual" in r for r in item.breakdown.match_reasons)
    assert "preferred_occasions" not in item.breakdown.neutral_dimensions


def test_snake_case_preferred_categories_affects_score() -> None:
    """2. Verify snake_case preferred_categories in user profile affects preference scoring."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Category User",
        style_profile={},
        preferences={"preferred_categories": ["tops"]},
        settings={},
        flags={},
        version=1,
    )

    p_top = _make_sample_product(title="Linen Shirt", category="tops", price=1999.0)
    p_foot = _make_sample_product(title="Leather Boots", category="footwear", price=1999.0)

    candidate_repo = FakeCandidateRepository([p_foot, p_top])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    assert len(result.items) == 2

    # 'tops' product ranks first due to category preference match (+10.0 pts)
    top_item = result.items[0]
    assert top_item.id == p_top.id
    assert top_item.breakdown.preference_match == 10.0
    assert top_item.score == 25.0
    assert any("Matches preferred category 'tops'" in r for r in top_item.breakdown.match_reasons)

    foot_item = result.items[1]
    assert foot_item.id == p_foot.id
    assert foot_item.breakdown.preference_match == 0.0
    assert foot_item.score == 15.0


def test_supported_camel_case_inputs_remain_compatible() -> None:
    """3. Verify supported camelCase inputs remain 100% compatible."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="CamelCase User",
        style_profile={},
        preferences={
            "preferredCategories": ["tops"],
            "preferredBrands": ["FabIndia"],
            "preferredColors": ["navy"],
            "preferredMaterials": ["linen"],
            "preferredOccasions": ["casual"],
        },
        settings={},
        flags={},
        version=1,
    )

    matching_prod = _make_sample_product(
        title="Matching Linen Shirt",
        category="tops",
        brand="FabIndia",
        color="navy",
        material="linen",
        price=2499.0,
    )
    candidate_repo = FakeCandidateRepository([matching_prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    item = result.items[0]

    # Category (+10), Brand (+10), Color (+8), Material (+6) = 34.0 preference
    assert item.breakdown.preference_match == 34.0
    # Occasion (+10.0) = 10.0 style
    assert item.breakdown.style_profile_match == 10.0
    # Availability (+15.0) = 15.0 budget
    assert item.breakdown.budget_availability == 15.0
    # Total = 59.0
    assert item.score == 59.0


def test_both_key_forms_present_follow_canonical_precedence() -> None:
    """4. Verify canonical snake_case takes precedence when both key forms are present."""
    # 4a: Occasions conflict: canonical 'party' vs camelCase 'casual'
    raw_occasions = {
        "preferred_occasions": ["party"],
        "preferredOccasions": ["casual"],
    }
    normalized_occ = normalize_preferences(raw_occasions)
    assert normalized_occ.preferred_occasions == ("party",)

    # 4b: Categories conflict: canonical 'bottoms' vs camelCase 'tops'
    raw_cats = {
        "preferred_categories": ["bottoms"],
        "preferredCategories": ["tops"],
    }
    normalized_cats = normalize_preferences(raw_cats)
    assert normalized_cats.preferred_categories == ("bottoms",)

    # 4c: Canonical empty list vs camelCase populated list: canonical empty list wins
    raw_empty_precedence = {
        "preferred_occasions": [],
        "preferredOccasions": ["casual"],
    }
    normalized_empty = normalize_preferences(raw_empty_precedence)
    assert normalized_empty.preferred_occasions == ()

    # Test scoring with conflicting preferences in user profile
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Precedence User",
        style_profile={},
        preferences={
            "preferred_categories": ["bottoms"],
            "preferredCategories": ["tops"],
        },
        settings={},
        flags={},
        version=1,
    )

    p_bottom = _make_sample_product(category="bottoms", price=2000.0)
    p_top = _make_sample_product(category="tops", price=2000.0)

    candidate_repo = FakeCandidateRepository([p_top, p_bottom])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    # Bottoms must rank first because canonical preferred_categories='bottoms' won
    assert result.items[0].id == p_bottom.id
    assert result.items[0].breakdown.preference_match == 10.0
    assert result.items[1].id == p_top.id
    assert result.items[1].breakdown.preference_match == 0.0


def test_missing_preferences_preserve_cold_start_behavior() -> None:
    """5. Verify missing preferences preserve exact neutral cold-start score (15.0)."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Cold Start User",
        style_profile={},
        preferences={},
        settings={},
        flags={},
        version=1,
    )

    prod = _make_sample_product(price=1999.0)
    candidate_repo = FakeCandidateRepository([prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    item = result.items[0]

    assert item.breakdown.preference_match == 0.0
    assert item.breakdown.style_profile_match == 0.0
    assert item.breakdown.wardrobe_complementarity == 0.0
    assert item.breakdown.budget_availability == 15.0
    assert item.score == 15.0
    assert "preferred_occasions" in item.breakdown.neutral_dimensions
    assert "category_preference" in item.breakdown.neutral_dimensions


def test_empty_preference_lists_handled_correctly() -> None:
    """6. Verify explicitly empty preference lists are preserved and remain neutral."""
    prefs = normalize_preferences({
        "preferred_categories": [],
        "preferred_brands": [],
        "preferred_colors": [],
        "preferred_occasions": [],
        "preferred_materials": [],
    })
    assert prefs.preferred_categories == ()
    assert prefs.preferred_brands == ()
    assert prefs.preferred_colors == ()
    assert prefs.preferred_occasions == ()
    assert prefs.preferred_materials == ()

    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Empty Prefs User",
        style_profile={},
        preferences={
            "preferred_categories": [],
            "preferred_occasions": [],
        },
        settings={},
        flags={},
        version=1,
    )

    prod = _make_sample_product(price=1999.0)
    candidate_repo = FakeCandidateRepository([prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    result = use_case(user_id=user_id)
    item = result.items[0]
    assert item.score == 15.0
    assert "preferred_occasions" in item.breakdown.neutral_dimensions


def test_malformed_preference_values_do_not_crash_or_create_false_matches() -> None:
    """7. Verify malformed preference values do not crash or create false matches."""
    malformed_raw = {
        "preferred_categories": "tops",  # String: must not iterate characters
        "preferred_occasions": 12345,     # Int: must not crash
        "preferred_brands": [None, 999, "   ", "FabIndia", {"invalid": "object"}],
        "preferred_colors": {"navy": True},  # Dict: must not crash
        "max_price": "invalid_number",    # Invalid string float: must be None
        "min_price": -50.0,                # Negative float: must be None
    }
    normalized = normalize_preferences(malformed_raw)

    assert normalized.preferred_categories == ()  # String not coerced into character list
    assert normalized.preferred_occasions == ()   # Non-sequence ignored
    assert normalized.preferred_brands == ("fabindia",)  # Only valid string extracted
    assert normalized.preferred_colors == ()      # Dict ignored
    assert normalized.max_price is None
    assert normalized.min_price is None

    # Test scoring with malformed profile
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Malformed User",
        style_profile={},
        preferences=malformed_raw,
        settings={},
        flags={},
        version=1,
    )

    p_matching_brand = _make_sample_product(
        title="FabIndia Kurta",
        category="tops",
        brand="FabIndia",
        price=2999.0,
    )
    candidate_repo = FakeCandidateRepository([p_matching_brand])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    # Must complete without crashing
    result = use_case(user_id=user_id)
    item = result.items[0]

    # Only the valid FabIndia brand matched (+10.0 pts), category did not match (+0.0 pts)
    assert item.breakdown.preference_match == 10.0
    assert any("Matches preferred brand 'FabIndia'" in r for r in item.breakdown.match_reasons)
    assert not any("Matches preferred category" in r for r in item.breakdown.match_reasons)
    assert item.score == 25.0


def test_guest_behavior_isolated_from_private_preferences() -> None:
    """8. Verify guest behavior remains strictly isolated from stored preferences."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Private User",
        style_profile={},
        preferences={"preferred_categories": ["tops"]},
        settings={},
        flags={},
        version=1,
    )

    prod = _make_sample_product(category="tops", price=1999.0)
    candidate_repo = FakeCandidateRepository([prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
    )

    # 1. Unauthenticated guest
    guest_res = use_case(is_guest=True, user_id=None)
    assert guest_res.applied_context.is_guest is True
    assert guest_res.applied_context.user_id is None
    assert guest_res.applied_context.preferences.preferred_categories == ()
    assert guest_res.items[0].score == 15.0

    # 2. Guest with another user's ID passed
    spoofed_guest_res = use_case(is_guest=True, user_id=user_id)
    assert spoofed_guest_res.applied_context.is_guest is True
    assert spoofed_guest_res.applied_context.user_id is None
    assert spoofed_guest_res.applied_context.preferences.preferred_categories == ()
    assert spoofed_guest_res.items[0].score == 15.0


def test_wardrobe_budget_availability_and_total_score_integrity() -> None:
    """9. Verify wardrobe complementarity, budget, availability, and total-score integrity."""
    user_id = uuid4()
    state_repo = FakeUserStateRepository()
    state_repo.profiles[user_id] = UserProfileRecord(
        user_id=user_id,
        display_name="Full Context User",
        style_profile={},
        preferences={
            "preferred_categories": ["tops"],
            "preferred_colors": ["navy"],
            "max_price": 3000.0,
        },
        settings={},
        flags={},
        version=1,
    )

    wardrobe_repo = FakeWardrobeRepository()
    wardrobe_repo.items[user_id] = [
        WardrobeItemRecord(
            id=uuid4(),
            user_id=user_id,
            name="Navy Blazer",
            category="outerwear",
            color="navy",
            material="wool",
            is_favorite=True,
            image_ref=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        WardrobeItemRecord(
            id=uuid4(),
            user_id=user_id,
            name="Black Chinos",
            category="bottoms",
            color="black",
            material="cotton",
            is_favorite=False,
            image_ref=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]

    # Candidate: Navy silk shirt at ₹2,499 (within ₹3,000 budget)
    prod = _make_sample_product(
        title="Silk Navy Top",
        category="tops",
        color="navy",
        material="silk",
        price=2499.0,
    )
    candidate_repo = FakeCandidateRepository([prod])
    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=state_repo,
        wardrobe_repo=wardrobe_repo,
    )

    result = use_case(user_id=user_id)
    item = result.items[0]

    # 1. Preference Match (10 category + 8 color = 18.0)
    assert item.breakdown.preference_match == 18.0
    # 2. Style Match (0.0 - no occasion or style_type)
    assert item.breakdown.style_profile_match == 0.0
    # 3. Wardrobe Complementarity:
    #    - palette synergy (+10.0 pts: navy is frequent color in wardrobe)
    #    - category gap (+5.0 pts: owns 0 tops in wardrobe)
    #    - natural material (+5.0 pts: silk is natural material)
    #    Total wardrobe = 20.0 pts (max cap)
    assert item.breakdown.wardrobe_complementarity == 20.0
    # 4. Budget & Availability:
    #    - in_stock (+5.0 pts)
    #    - has_price (+5.0 pts)
    #    - within_budget (+5.0 pts: 2499 <= 3000)
    #    Total budget = 15.0 pts
    assert item.breakdown.budget_availability == 15.0
    # Total Score: 18.0 + 0.0 + 20.0 + 15.0 = 53.0 pts
    assert item.score == 53.0


# ---------------------------------------------------------------------------
# Database Integration Test (fansivibe_test seeded catalog)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures("db")


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


def test_for_you_database_personalization(seeded_db) -> None:
    """Verify For You ranking against the real seeded PostgreSQL database."""
    cand_repo = DiscoveryRepositorySQL(seeded_db)
    user_repo = UserStateRepositorySQL(seeded_db)
    wardrobe_repo = WardrobeItemRepositorySQL(seeded_db)

    retrieval = RetrieveProductCandidates(cand_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=user_repo,
        wardrobe_repo=wardrobe_repo,
    )

    # 1. Unauthenticated / guest search returns 20 items on page 1 of 60 total
    guest_res = use_case(is_guest=True, page=1, page_size=20)
    assert guest_res.total_count == 60
    assert len(guest_res.items) == 20
    assert guest_res.total_pages == 3
    assert guest_res.has_next is True

    # 2. Personalize with explicit preferences: preferred brand "Indus Thread Co.", preferred category "tops"
    prefs = PersonalizationPreferences(
        preferred_categories=("tops",),
        preferred_brands=("Indus Thread Co.",),
        max_price=5000.0,
    )
    res = use_case(preferences=prefs, page=1, page_size=10)

    # Top ranked items should be Indus Thread Co. tops within budget
    top_item = res.items[0]
    assert top_item.product.category == "tops"
    assert top_item.product.brand == "Indus Thread Co."
    assert top_item.score > 20.0
    assert top_item.breakdown.preference_match >= 10.0
    assert top_item.product.price <= 5000.0
