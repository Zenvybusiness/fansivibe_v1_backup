"""Domain personalization ranking and scoring policies for Fansivibe Discovery (DISCOVERY-04).

Defines deterministic, explainable scoring rules for ranking catalog product candidates
against verified user preferences, style profile attributes, and wardrobe context.

Invariants:
- Hard eligibility filters must be applied BEFORE scoring.
- Missing preferences remain neutral (0 points); unknown data is never penalized or rewarded.
- Transparent score breakdown with explainable reasons.
- Zero fabricated popularity, trend demand, or fake interaction signals.
- Deterministic tie-breaking: score desc -> created_at desc -> product_id asc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from app.domain.ports.repositories import CatalogProductRecord, WardrobeItemRecord
from app.domain.services.analysis_rules import (
    _CATEGORY_OCCASIONS,
    _is_natural_material,
    _is_neutral_color,
)
from app.domain.services.ffo_bridge import ProductFfoBridgeResult


@dataclass(frozen=True)
class PersonalizationPreferences:
    """Explicit preference specifications provided by user or query context."""

    preferred_categories: tuple[str, ...] = ()
    excluded_categories: tuple[str, ...] = ()
    preferred_brands: tuple[str, ...] = ()
    excluded_brands: tuple[str, ...] = ()
    preferred_colors: tuple[str, ...] = ()
    preferred_materials: tuple[str, ...] = ()
    preferred_fits: tuple[str, ...] = ()
    preferred_silhouettes: tuple[str, ...] = ()
    preferred_occasions: tuple[str, ...] = ()
    preferred_aesthetics: tuple[str, ...] = ()
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    currency: Optional[str] = None


CANONICAL_PREFERENCE_KEYS: tuple[str, ...] = (
    "preferred_categories",
    "excluded_categories",
    "preferred_brands",
    "excluded_brands",
    "preferred_colors",
    "preferred_materials",
    "preferred_fits",
    "preferred_silhouettes",
    "preferred_occasions",
    "preferred_aesthetics",
    "max_price",
    "min_price",
    "currency",
)

PREFERENCE_KEY_ALIASES: dict[str, str] = {
    "preferredCategories": "preferred_categories",
    "excludedCategories": "excluded_categories",
    "preferredBrands": "preferred_brands",
    "excludedBrands": "excluded_brands",
    "preferredColors": "preferred_colors",
    "preferredMaterials": "preferred_materials",
    "preferredFits": "preferred_fits",
    "preferredSilhouettes": "preferred_silhouettes",
    "preferredOccasions": "preferred_occasions",
    "preferredAesthetics": "preferred_aesthetics",
    "maxPrice": "max_price",
    "minPrice": "min_price",
    "currency": "currency",
}


def _extract_string_sequence(
    prefs: Mapping[str, Any],
    canonical_key: str,
    alternate_key: str,
) -> tuple[str, ...]:
    """Extract a clean tuple of unique lowercase strings with deterministic precedence.

    Precedence:
    1. If canonical_key is present in prefs and not None -> use canonical value.
    2. Else if alternate_key is present in prefs and not None -> use alternate value.
    3. Else if canonical_key is present in prefs (even if None) -> use canonical value.
    4. Else if alternate_key is present in prefs -> use alternate value.
    5. Else -> return empty tuple ().

    Validation & Safety:
    - If the selected value is not an iterable (list, tuple, set), return ().
    - If a string is passed directly instead of a sequence, do not coerce by iterating
      characters; return () to prevent accidental substring / false matches.
    - Each element must be a non-empty string. Non-string elements (ints, dicts, None)
      are safely filtered out without crashing.
    - Resulting strings are trimmed, lowercased, and deduplicated preserving order.
    """
    raw: Any = None
    if canonical_key in prefs and prefs[canonical_key] is not None:
        raw = prefs[canonical_key]
    elif alternate_key in prefs and prefs[alternate_key] is not None:
        raw = prefs[alternate_key]
    elif canonical_key in prefs:
        raw = prefs[canonical_key]
    elif alternate_key in prefs:
        raw = prefs[alternate_key]
    else:
        return ()

    if not isinstance(raw, (list, tuple, set)):
        return ()

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw:
        if isinstance(item, str):
            val = item.strip().lower()
            if val and val not in seen:
                seen.add(val)
                cleaned.append(val)
    return tuple(cleaned)


def _extract_float(
    prefs: Mapping[str, Any],
    canonical_key: str,
    alternate_key: str,
) -> Optional[float]:
    """Extract a non-negative float with deterministic canonical precedence."""
    raw: Any = None
    if canonical_key in prefs and prefs[canonical_key] is not None:
        raw = prefs[canonical_key]
    elif alternate_key in prefs and prefs[alternate_key] is not None:
        raw = prefs[alternate_key]
    elif canonical_key in prefs:
        raw = prefs[canonical_key]
    elif alternate_key in prefs:
        raw = prefs[alternate_key]
    else:
        return None

    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        val = float(raw)
        return val if val >= 0 else None
    return None


def _extract_string(
    prefs: Mapping[str, Any],
    canonical_key: str,
    alternate_key: str,
) -> Optional[str]:
    """Extract a stripped uppercase string with deterministic canonical precedence."""
    raw: Any = None
    if canonical_key in prefs and prefs[canonical_key] is not None:
        raw = prefs[canonical_key]
    elif alternate_key in prefs and prefs[alternate_key] is not None:
        raw = prefs[alternate_key]
    elif canonical_key in prefs:
        raw = prefs[canonical_key]
    elif alternate_key in prefs:
        raw = prefs[alternate_key]
    else:
        return None

    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return None


def normalize_preferences(
    raw_preferences: Optional[Mapping[str, Any]],
) -> PersonalizationPreferences:
    """Normalize raw preference dictionaries from storage or API payloads.

    Precedence: canonical snake_case storage keys take precedence over camelCase aliases.
    Invalid types and malformed values are safely ignored without crashing or falsifying matches.
    Empty lists are preserved. Missing values default to empty tuples / None.
    Does NOT mutate the input mapping.
    """
    if not isinstance(raw_preferences, Mapping):
        return PersonalizationPreferences()

    return PersonalizationPreferences(
        preferred_categories=_extract_string_sequence(
            raw_preferences, "preferred_categories", "preferredCategories"
        ),
        excluded_categories=_extract_string_sequence(
            raw_preferences, "excluded_categories", "excludedCategories"
        ),
        preferred_brands=_extract_string_sequence(
            raw_preferences, "preferred_brands", "preferredBrands"
        ),
        excluded_brands=_extract_string_sequence(
            raw_preferences, "excluded_brands", "excludedBrands"
        ),
        preferred_colors=_extract_string_sequence(
            raw_preferences, "preferred_colors", "preferredColors"
        ),
        preferred_materials=_extract_string_sequence(
            raw_preferences, "preferred_materials", "preferredMaterials"
        ),
        preferred_fits=_extract_string_sequence(
            raw_preferences, "preferred_fits", "preferredFits"
        ),
        preferred_silhouettes=_extract_string_sequence(
            raw_preferences, "preferred_silhouettes", "preferredSilhouettes"
        ),
        preferred_occasions=_extract_string_sequence(
            raw_preferences, "preferred_occasions", "preferredOccasions"
        ),
        preferred_aesthetics=_extract_string_sequence(
            raw_preferences, "preferred_aesthetics", "preferredAesthetics"
        ),
        max_price=_extract_float(
            raw_preferences, "max_price", "maxPrice"
        ),
        min_price=_extract_float(
            raw_preferences, "min_price", "minPrice"
        ),
        currency=_extract_string(
            raw_preferences, "currency", "currency"
        ),
    )


@dataclass(frozen=True)
class WardrobeAffinityContext:
    """Aggregated, privacy-safe facts from the user's owned wardrobe."""

    owned_categories: tuple[str, ...] = ()
    category_counts: dict[str, int] = field(default_factory=dict)
    frequent_colors: tuple[str, ...] = ()
    favorite_colors: tuple[str, ...] = ()
    frequent_materials: tuple[str, ...] = ()
    has_wardrobe: bool = False


@dataclass(frozen=True)
class UserPersonalizationContext:
    """Aggregated verified user context for personalization."""

    user_id: Optional[UUID] = None
    is_guest: bool = False
    display_name: Optional[str] = None
    style_profile: dict[str, Any] = field(default_factory=dict)
    preferences: PersonalizationPreferences = field(
        default_factory=PersonalizationPreferences
    )
    wardrobe_context: WardrobeAffinityContext = field(
        default_factory=WardrobeAffinityContext
    )


@dataclass(frozen=True)
class PersonalizationScoreBreakdown:
    """Transparent breakdown of how candidate relevance score was computed."""

    preference_match: float  # 0.0 - 40.0
    style_profile_match: float  # 0.0 - 25.0
    wardrobe_complementarity: float  # 0.0 - 20.0
    budget_availability: float  # 0.0 - 15.0
    total_score: float  # 0.0 - 100.0
    match_reasons: tuple[str, ...] = ()
    neutral_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankedCandidate:
    """A product candidate paired with its personalization score and explanation."""

    product: CatalogProductRecord
    ffo_bridge: ProductFfoBridgeResult
    score: float
    breakdown: PersonalizationScoreBreakdown
    rank: int

    @property
    def id(self) -> UUID:
        return self.product.id

    @property
    def title(self) -> str:
        return self.product.title

    @property
    def brand(self) -> Optional[str]:
        return self.product.brand

    @property
    def category(self) -> Optional[str]:
        return self.product.category

    @property
    def price(self) -> Optional[float]:
        return self.product.price

    @property
    def currency(self) -> Optional[str]:
        return self.product.currency

    @property
    def availability(self) -> Optional[bool]:
        return self.product.availability

    @property
    def is_synthetic(self) -> bool:
        return self.product.is_synthetic

    @property
    def is_fixture(self) -> bool:
        return self.product.is_fixture


def build_wardrobe_affinity_context(
    wardrobe_items: Sequence[WardrobeItemRecord],
) -> WardrobeAffinityContext:
    """Extract deterministic, privacy-safe wardrobe affinity signals.

    Summarizes owned categories, color palette frequencies, and material preferences
    without leaking private identifiers or raw image data.
    """
    if not wardrobe_items:
        return WardrobeAffinityContext(has_wardrobe=False)

    cat_counts: dict[str, int] = {}
    color_counts: dict[str, int] = {}
    fav_color_counts: dict[str, int] = {}
    material_counts: dict[str, int] = {}

    for item in wardrobe_items:
        cat = (item.category or "").strip().lower()
        if cat:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        color = (item.color or "").strip().lower()
        if color:
            color_counts[color] = color_counts.get(color, 0) + 1
            if item.is_favorite:
                fav_color_counts[color] = fav_color_counts.get(color, 0) + 1

        mat = (item.material or "").strip().lower()
        if mat:
            material_counts[mat] = material_counts.get(mat, 0) + 1

    # Deterministic top colors/materials (sorted by count desc, name asc)
    top_colors = tuple(
        c
        for c, _ in sorted(color_counts.items(), key=lambda x: (-x[1], x[0]))[:5]
    )
    fav_colors = tuple(
        c
        for c, _ in sorted(fav_color_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    )
    top_materials = tuple(
        m
        for m, _ in sorted(material_counts.items(), key=lambda x: (-x[1], x[0]))[:5]
    )

    return WardrobeAffinityContext(
        owned_categories=tuple(sorted(cat_counts.keys())),
        category_counts=cat_counts,
        frequent_colors=top_colors,
        favorite_colors=fav_colors,
        frequent_materials=top_materials,
        has_wardrobe=True,
    )


def score_product_candidate(
    product: CatalogProductRecord,
    ffo_bridge: ProductFfoBridgeResult,
    context: UserPersonalizationContext,
) -> PersonalizationScoreBreakdown:
    """Calculate deterministic personalization score (0–100) and explanation breakdown.

    Scoring dimensions:
    1. Preference Match (0–40 pts): Explicit user preferences (category, brand, color, material, fit, silhouette).
    2. Style Profile Match (0–25 pts): Style aesthetic, body type, occasion alignment.
    3. Wardrobe Complementarity (0–20 pts): Palette harmony, category gap-filling, material synergy.
    4. Budget & Availability (0–15 pts): Price within budget, in-stock trustworthiness.

    Unknown or unprovided dimensions contribute 0 points (neutral) and are documented in neutral_dimensions.
    """
    reasons: list[str] = []
    neutrals: list[str] = []

    # -----------------------------------------------------------------------
    # 1. Preference Match (0–40 pts)
    # -----------------------------------------------------------------------
    pref_score = 0.0
    prefs = context.preferences

    # Category preference (+10.0 pts)
    if prefs.preferred_categories:
        prod_cat = (product.category or "").strip().lower()
        wanted_cats = {c.strip().lower() for c in prefs.preferred_categories}
        if prod_cat in wanted_cats:
            pref_score += 10.0
            reasons.append(f"Matches preferred category '{product.category}'")
    else:
        neutrals.append("category_preference")

    # Brand preference (+10.0 pts)
    if prefs.preferred_brands:
        prod_brand = (product.brand or "").strip().lower()
        wanted_brands = {b.strip().lower() for b in prefs.preferred_brands}
        if prod_brand in wanted_brands:
            pref_score += 10.0
            reasons.append(f"Matches preferred brand '{product.brand}'")
    else:
        neutrals.append("brand_preference")

    # Color preference (+8.0 pts)
    if prefs.preferred_colors:
        prod_color = (product.color or "").strip().lower()
        wanted_colors = {c.strip().lower() for c in prefs.preferred_colors}
        bridge_colors = {
            m.canonical_id.lower()
            for m in ffo_bridge.concepts_for_kind("color")
        }
        if prod_color in wanted_colors or (bridge_colors & wanted_colors):
            pref_score += 8.0
            reasons.append(f"Matches preferred color '{product.color}'")
    else:
        neutrals.append("color_preference")

    # Material preference (+6.0 pts)
    if prefs.preferred_materials:
        prod_mat = (product.material or "").strip().lower()
        wanted_mats = {m.strip().lower() for m in prefs.preferred_materials}
        bridge_mats = {
            m.canonical_id.lower()
            for m in ffo_bridge.concepts
            if m.entity_kind in ("material", "textile")
        }
        if (
            any(w in prod_mat for w in wanted_mats)
            or (bridge_mats & wanted_mats)
        ):
            pref_score += 6.0
            reasons.append(f"Matches preferred material '{product.material}'")
    else:
        neutrals.append("material_preference")

    # Fit & Silhouette preference (+3.0 pts fit, +3.0 pts silhouette)
    if prefs.preferred_fits:
        prod_fit = (product.fit or "").strip().lower()
        wanted_fits = {f.strip().lower() for f in prefs.preferred_fits}
        bridge_fits = {
            m.canonical_id.lower()
            for m in ffo_bridge.concepts_for_kind("fit")
        }
        if prod_fit in wanted_fits or (bridge_fits & wanted_fits):
            pref_score += 3.0
            reasons.append(f"Matches preferred fit '{product.fit}'")
    else:
        neutrals.append("fit_preference")

    if prefs.preferred_silhouettes:
        prod_sil = (product.silhouette or "").strip().lower()
        wanted_sils = {s.strip().lower() for s in prefs.preferred_silhouettes}
        bridge_sils = {
            m.canonical_id.lower()
            for m in ffo_bridge.concepts_for_kind("silhouette")
        }
        if prod_sil in wanted_sils or (bridge_sils & wanted_sils):
            pref_score += 3.0
            reasons.append(f"Matches preferred silhouette '{product.silhouette}'")
    else:
        neutrals.append("silhouette_preference")

    pref_score = min(40.0, pref_score)

    # -----------------------------------------------------------------------
    # 2. Style Profile Match (0–25 pts)
    # -----------------------------------------------------------------------
    style_score = 0.0

    # Aesthetic / style_type from style profile or explicit aesthetic (+15.0 pts)
    profile_style = (context.style_profile.get("style_type") or "").strip().lower()
    wanted_aesthetics = {a.strip().lower() for a in prefs.preferred_aesthetics}
    if profile_style:
        wanted_aesthetics.add(profile_style)

    if wanted_aesthetics:
        product_aesthetics = {
            m.canonical_id.lower()
            for m in ffo_bridge.concepts
            if m.entity_kind in ("aesthetic", "culture")
        }
        # Also check raw style tags
        raw_tags = {t.strip().lower() for t in product.style_tags}
        matched_aes = (product_aesthetics | raw_tags) & wanted_aesthetics
        if matched_aes:
            style_score += 15.0
            reasons.append(
                f"Aligns with style aesthetic '{sorted(matched_aes)[0]}'"
            )
    else:
        neutrals.append("style_aesthetic")

    # Occasion alignment (+10.0 pts)
    if prefs.preferred_occasions:
        prod_cat = (product.category or "").strip().lower()
        suitable_for_cat = _CATEGORY_OCCASIONS.get(prod_cat, set())
        wanted_occ = {o.strip().lower() for o in prefs.preferred_occasions}
        matched_occ = suitable_for_cat & wanted_occ
        if matched_occ:
            style_score += 10.0
            reasons.append(
                f"Suitable for preferred occasion(s): {', '.join(sorted(matched_occ))}"
            )
    else:
        neutrals.append("preferred_occasions")

    style_score = min(25.0, style_score)

    # -----------------------------------------------------------------------
    # 3. Wardrobe Complementarity (0–20 pts)
    # -----------------------------------------------------------------------
    wardrobe_score = 0.0
    w_ctx = context.wardrobe_context

    if w_ctx.has_wardrobe:
        # Palette synergy: neutral color OR matches frequent/favorite wardrobe colors (+10.0 pts)
        prod_color = (product.color or "").strip().lower()
        if prod_color:
            if _is_neutral_color(prod_color):
                wardrobe_score += 10.0
                reasons.append("Versatile neutral color complements your wardrobe palette")
            elif prod_color in w_ctx.favorite_colors or prod_color in w_ctx.frequent_colors:
                wardrobe_score += 10.0
                reasons.append(f"Color '{prod_color}' coordinates with your frequent wardrobe tones")

        # Category gap filling: user has fewer than 2 items in this category (+5.0 pts)
        prod_cat = (product.category or "").strip().lower()
        if prod_cat:
            owned_in_cat = w_ctx.category_counts.get(prod_cat, 0)
            if owned_in_cat < 2:
                wardrobe_score += 5.0
                reasons.append(f"Balances your wardrobe (currently {owned_in_cat} in '{prod_cat}')")

        # Material synergy: natural material consistency (+5.0 pts)
        prod_mat = (product.material or "").strip().lower()
        if prod_mat and _is_natural_material(prod_mat):
            wardrobe_score += 5.0
            reasons.append("Natural material complements your wardrobe quality baseline")
    else:
        neutrals.append("wardrobe_context")

    wardrobe_score = min(20.0, wardrobe_score)

    # -----------------------------------------------------------------------
    # 4. Budget & Availability (0–15 pts)
    # -----------------------------------------------------------------------
    budget_score = 0.0

    # Stock availability (+5.0 pts)
    if product.availability is True:
        budget_score += 5.0
        reasons.append("In stock and available")
    elif product.availability is None:
        neutrals.append("stock_availability")

    # Verified price (+5.0 pts)
    if product.price is not None:
        budget_score += 5.0
    else:
        neutrals.append("product_price")

    # Budget threshold adherence (+5.0 pts)
    if prefs.max_price is not None:
        if product.price is not None and product.price <= prefs.max_price:
            budget_score += 5.0
            reasons.append(f"Within your budget limit of ₹{prefs.max_price:g}")
    else:
        # User specified no budget limit: neutral +5.0 pts if price is present
        if product.price is not None:
            budget_score += 5.0
        else:
            neutrals.append("budget_limit")

    budget_score = min(15.0, budget_score)

    # -----------------------------------------------------------------------
    # Total Score Composition
    # -----------------------------------------------------------------------
    total = round(pref_score + style_score + wardrobe_score + budget_score, 2)
    total = max(0.0, min(100.0, total))

    return PersonalizationScoreBreakdown(
        preference_match=round(pref_score, 2),
        style_profile_match=round(style_score, 2),
        wardrobe_complementarity=round(wardrobe_score, 2),
        budget_availability=round(budget_score, 2),
        total_score=total,
        match_reasons=tuple(reasons),
        neutral_dimensions=tuple(neutrals),
    )


def rank_personalized_candidates(
    candidates: Sequence[tuple[CatalogProductRecord, ProductFfoBridgeResult]],
    context: UserPersonalizationContext,
) -> list[RankedCandidate]:
    """Rank product candidates deterministically by personalized relevance score.

    Ordering invariants:
    1. Total score descending.
    2. Product created_at descending (newest first).
    3. Product ID ascending (lexical UUID tie-breaker).
    """
    scored: list[RankedCandidate] = []
    for product, bridge in candidates:
        breakdown = score_product_candidate(product, bridge, context)
        # Placeholder rank 0, assigned after sorting
        scored.append(
            RankedCandidate(
                product=product,
                ffo_bridge=bridge,
                score=breakdown.total_score,
                breakdown=breakdown,
                rank=0,
            )
        )

    # Deterministic sorting
    def _sort_key(item: RankedCandidate) -> tuple[float, float, str]:
        created_ts = (
            item.product.created_at.timestamp()
            if item.product.created_at
            else 0.0
        )
        return (-item.score, -created_ts, str(item.id))

    sorted_candidates = sorted(scored, key=_sort_key)

    # Assign 1-indexed ranks
    result: list[RankedCandidate] = []
    for idx, item in enumerate(sorted_candidates, start=1):
        result.append(
            RankedCandidate(
                product=item.product,
                ffo_bridge=item.ffo_bridge,
                score=item.score,
                breakdown=item.breakdown,
                rank=idx,
            )
        )
    return result
