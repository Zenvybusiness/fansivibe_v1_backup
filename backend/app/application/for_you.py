"""For You Personalization application use case for Fansivibe Discovery (DISCOVERY-04).

Orchestrates candidate retrieval, privacy-safe user context resolution,
hard eligibility filtering, deterministic relevance ranking, and bounded pagination.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union
from uuid import UUID

from app.application.candidate_retrieval import RetrieveProductCandidates
from app.domain.ports.repositories import (
    ProductFilterCriteria,
    UserStateRepository,
    WardrobeItemRepository,
)
from app.domain.services.candidate_filters import (
    validate_criteria,
    validate_pagination,
)
from app.domain.services.personalization import (
    CANONICAL_PREFERENCE_KEYS,
    PREFERENCE_KEY_ALIASES,
    PersonalizationPreferences,
    RankedCandidate,
    UserPersonalizationContext,
    WardrobeAffinityContext,
    build_wardrobe_affinity_context,
    normalize_preferences,
    rank_personalized_candidates,
)


@dataclass(frozen=True)
class ForYouPersonalizationResult:
    """Paginated result of For You personalized product recommendations."""

    items: tuple[RankedCandidate, ...]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    applied_context: UserPersonalizationContext
    applied_criteria: ProductFilterCriteria = field(
        default_factory=ProductFilterCriteria
    )


class PersonalizeForYou:
    """Application use case for retrieving and ranking personalized product candidates.

    Invariants:
    - Hard eligibility filters are applied before scoring.
    - Unauthenticated/guest contexts (user_id=None or is_guest=True) CANNOT access another user's profile/wardrobe.
    - Missing preferences remain neutral; unknown data is neither penalized nor rewarded.
    - Deterministic tie-breaking across equal scores.
    """

    def __init__(
        self,
        candidate_retrieval: RetrieveProductCandidates,
        user_state_repo: Optional[UserStateRepository] = None,
        wardrobe_repo: Optional[WardrobeItemRepository] = None,
    ) -> None:
        self._retrieval = candidate_retrieval
        self._user_state_repo = user_state_repo
        self._wardrobe_repo = wardrobe_repo

    def _resolve_context(
        self,
        user_id: Optional[UUID],
        is_guest: bool,
        explicit_prefs: Optional[PersonalizationPreferences],
    ) -> UserPersonalizationContext:
        """Resolve verified user context or construct an unauthenticated guest context."""
        # Privacy guard: guest or unauthenticated contexts must never query user repositories
        if user_id is None or is_guest:
            return UserPersonalizationContext(
                user_id=None,
                is_guest=True,
                display_name=None,
                style_profile={},
                preferences=explicit_prefs or PersonalizationPreferences(),
                wardrobe_context=WardrobeAffinityContext(has_wardrobe=False),
            )

        # Authenticated context: read owner-scoped data only
        profile_style: dict = {}
        stored_prefs: dict = {}
        display_name: Optional[str] = None

        if self._user_state_repo is not None:
            profile = self._user_state_repo.get_profile(user_id=user_id)
            if profile is not None:
                display_name = profile.display_name
                profile_style = dict(profile.style_profile or {})
                stored_prefs = dict(profile.preferences or {})

        # Normalize stored preferences from database JSONB
        stored = normalize_preferences(stored_prefs)

        # Merge with explicit preferences (explicit takes precedence where provided)
        merged_categories = (
            explicit_prefs.preferred_categories
            if (explicit_prefs and explicit_prefs.preferred_categories)
            else stored.preferred_categories
        )
        merged_excluded_cats = (
            explicit_prefs.excluded_categories
            if (explicit_prefs and explicit_prefs.excluded_categories)
            else stored.excluded_categories
        )
        merged_brands = (
            explicit_prefs.preferred_brands
            if (explicit_prefs and explicit_prefs.preferred_brands)
            else stored.preferred_brands
        )
        merged_excluded_brands = (
            explicit_prefs.excluded_brands
            if (explicit_prefs and explicit_prefs.excluded_brands)
            else stored.excluded_brands
        )
        merged_occasions = (
            explicit_prefs.preferred_occasions
            if (explicit_prefs and explicit_prefs.preferred_occasions)
            else stored.preferred_occasions
        )
        merged_colors = (
            explicit_prefs.preferred_colors
            if (explicit_prefs and explicit_prefs.preferred_colors)
            else stored.preferred_colors
        )
        merged_materials = (
            explicit_prefs.preferred_materials
            if (explicit_prefs and explicit_prefs.preferred_materials)
            else stored.preferred_materials
        )
        merged_fits = (
            explicit_prefs.preferred_fits
            if (explicit_prefs and explicit_prefs.preferred_fits)
            else stored.preferred_fits
        )
        merged_silhouettes = (
            explicit_prefs.preferred_silhouettes
            if (explicit_prefs and explicit_prefs.preferred_silhouettes)
            else stored.preferred_silhouettes
        )
        merged_aesthetics = (
            explicit_prefs.preferred_aesthetics
            if (explicit_prefs and explicit_prefs.preferred_aesthetics)
            else stored.preferred_aesthetics
        )
        merged_max_price = (
            explicit_prefs.max_price
            if (explicit_prefs and explicit_prefs.max_price is not None)
            else stored.max_price
        )
        merged_min_price = (
            explicit_prefs.min_price
            if (explicit_prefs and explicit_prefs.min_price is not None)
            else stored.min_price
        )
        merged_currency = (
            explicit_prefs.currency
            if (explicit_prefs and explicit_prefs.currency is not None)
            else stored.currency
        )

        effective_prefs = PersonalizationPreferences(
            preferred_categories=merged_categories,
            excluded_categories=merged_excluded_cats,
            preferred_brands=merged_brands,
            excluded_brands=merged_excluded_brands,
            preferred_colors=merged_colors,
            preferred_materials=merged_materials,
            preferred_fits=merged_fits,
            preferred_silhouettes=merged_silhouettes,
            preferred_occasions=merged_occasions,
            preferred_aesthetics=merged_aesthetics,
            max_price=merged_max_price,
            min_price=merged_min_price,
            currency=merged_currency,
        )

        # Read owner-scoped wardrobe items
        wardrobe_affinity = WardrobeAffinityContext(has_wardrobe=False)
        if self._wardrobe_repo is not None:
            items, _ = self._wardrobe_repo.get_for_user(
                user_id=user_id, page=1, page_size=100
            )
            wardrobe_affinity = build_wardrobe_affinity_context(items)

        return UserPersonalizationContext(
            user_id=user_id,
            is_guest=False,
            display_name=display_name,
            style_profile=profile_style,
            preferences=effective_prefs,
            wardrobe_context=wardrobe_affinity,
        )

    def __call__(
        self,
        user_id: Optional[UUID] = None,
        criteria: Optional[ProductFilterCriteria] = None,
        preferences: Optional[Union[PersonalizationPreferences, Mapping[str, Any]]] = None,
        *,
        page: int = 1,
        page_size: int = 20,
        is_guest: bool = False,
    ) -> ForYouPersonalizationResult:
        validate_pagination(page, page_size)

        explicit_prefs = (
            normalize_preferences(preferences)
            if isinstance(preferences, Mapping)
            else preferences
        )

        # 1. Resolve user personalization context
        context = self._resolve_context(user_id, is_guest, explicit_prefs)

        # 2. Build effective hard criteria merging criteria with hard user exclusions / budget limits
        user_prefs = context.preferences
        effective_categories = criteria.categories if criteria else None
        effective_exclude_categories = (
            criteria.exclude_categories
            if (criteria and criteria.exclude_categories)
            else (user_prefs.excluded_categories if user_prefs.excluded_categories else None)
        )
        effective_brands = criteria.brands if criteria else None
        effective_exclude_brands = (
            criteria.exclude_brands
            if (criteria and criteria.exclude_brands)
            else (user_prefs.excluded_brands if user_prefs.excluded_brands else None)
        )
        effective_min_price = (
            criteria.min_price
            if (criteria and criteria.min_price is not None)
            else user_prefs.min_price
        )
        effective_max_price = (
            criteria.max_price
            if (criteria and criteria.max_price is not None)
            else user_prefs.max_price
        )
        effective_currency = (
            criteria.currency
            if (criteria and criteria.currency is not None)
            else user_prefs.currency
        )

        hard_criteria = ProductFilterCriteria(
            categories=effective_categories,
            exclude_categories=effective_exclude_categories,
            subcategories=criteria.subcategories if criteria else None,
            exclude_subcategories=criteria.exclude_subcategories if criteria else None,
            brands=effective_brands,
            exclude_brands=effective_exclude_brands,
            min_price=effective_min_price,
            max_price=effective_max_price,
            currency=effective_currency,
            materials=criteria.materials if criteria else None,
            colors=criteria.colors if criteria else None,
            fits=criteria.fits if criteria else None,
            silhouettes=criteria.silhouettes if criteria else None,
            in_stock_only=criteria.in_stock_only if criteria else None,
            include_synthetic=criteria.include_synthetic if criteria else True,
            has_price=criteria.has_price if criteria else None,
            has_images=criteria.has_images if criteria else None,
            ffo_concepts=criteria.ffo_concepts if criteria else None,
            q=criteria.q if criteria else None,
        )
        validate_criteria(hard_criteria)

        # 3. Retrieve candidate pool via candidate retrieval use case (bounded up to 500 candidates)
        items_accum: list = []
        first_page = self._retrieval(
            criteria=hard_criteria,
            sort_order="newest",
            page=1,
            page_size=100,
        )
        items_accum.extend(first_page.items)
        if first_page.total_count > 100:
            max_pages = min(first_page.total_pages, 5)
            for p in range(2, max_pages + 1):
                next_page = self._retrieval(
                    criteria=hard_criteria,
                    sort_order="newest",
                    page=p,
                    page_size=100,
                )
                items_accum.extend(next_page.items)

        # 4. Rank candidates deterministically
        candidate_pairs = [
            (c.product, c.ffo_bridge) for c in items_accum
        ]
        ranked_items = rank_personalized_candidates(candidate_pairs, context)

        # 5. Apply bounded pagination over ranked candidates
        total_count = len(ranked_items)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
        offset = (page - 1) * page_size
        items_slice = tuple(ranked_items[offset : offset + page_size])

        has_next = (page * page_size) < total_count
        has_prev = page > 1 and total_count > 0

        return ForYouPersonalizationResult(
            items=items_slice,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
            applied_context=context,
            applied_criteria=hard_criteria,
        )
