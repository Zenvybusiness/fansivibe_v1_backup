"""Assistant tools: our own recommendation functions.

Each tool takes the user context (wardrobe, face data, saved looks) plus any
parameters parsed from the message and returns suggestion cards. The LLM (when
configured) only writes natural-language text around these structured results.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence
from uuid import UUID

from app.application.outfits import (
    EMPTY_WARDROBE,
    MISSING_REQUIRED_CATEGORY,
    NO_LEGAL_CANDIDATE,
    GenerateOutfit,
)
from app.application.today import _utc_today
from app.data import catalog
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    UserEventRepository,
    UserStateRepository,
    WardrobeItemRepository,
)
from app.domain.services import analysis_rules, grooming_rules
from app.domain.services.vibe_mapping import (
    resolve_effective_occasions,
    resolve_vibe_attributes,
)
from app.domain.value_objects import AppearanceProfile, HairstylePreferences, WeatherContext
from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.infrastructure.external.knowledge import CatalogKnowledgeSource
from app.models.schemas import (
    OutfitComposition,
    OutfitIntelligence,
    SuggestionCard,
    UserContext,
)

logger = logging.getLogger("fansivibe.tools")


def _format_tips(tips: str | list[str] | None) -> list[str]:
    if not tips:
        return []
    if isinstance(tips, (list, tuple)):
        return [str(t).strip() for t in tips if str(t).strip()]
    raw_parts = [p.strip() for p in tips.replace("•", ",").replace(";", ",").split(",")]
    items: list[str] = []
    for part in raw_parts:
        for sub in part.split("."):
            s = sub.strip()
            if s:
                items.append(s[0].upper() + s[1:])
    return items


def _safe_subtitle(
    reasons: list[str],
    description: str,
    raw_face: str,
    unmeasured_fallback: str,
) -> str:
    if not raw_face:
        return unmeasured_fallback
    canonical_face = "rectangular" if raw_face.lower() == "rectangle" else raw_face.lower()
    for r in reasons:
        if r.startswith("Strongest match for your") and canonical_face in r.lower():
            return r
    all_face_shapes = {"oval", "round", "square", "rectangular", "heart", "diamond", "oblong"}
    incompatible = all_face_shapes - {canonical_face}
    for r in reasons:
        r_low = r.lower()
        if not any(f"{shape} face" in r_low or f"{shape}s benefit" in r_low for shape in incompatible):
            return r
    return description


def derive_canonical_outfit_recommendation(
    occasion: Optional[str],
    user: Optional[UserContext],
    *,
    user_id: Optional[UUID] = None,
    generate_outfit: Optional[GenerateOutfit] = None,
    wardrobe_items: Optional[WardrobeItemRepository] = None,
    user_state: Optional[UserStateRepository] = None,
    events: Optional[UserEventRepository] = None,
    preferred_item_ids: Optional[Sequence[str]] = None,
    preferred_occasions: Optional[Sequence[str]] = None,
    fit: Optional[str] = None,
    color_palette: Optional[str] = None,
    mood: Optional[str] = None,
    seed: Optional[str] = None,
    weather_context: Optional[WeatherContext | str] = None,
    slot_to_swap: Optional[str] = None,
    include_alternatives: bool = False,
) -> tuple[List[SuggestionCard], OutfitIntelligence]:
    """Derive canonical outfit recommendation and synchronize SuggestionCard and OutfitIntelligence.

    Stage 1D Batch 4B.4: Assistant Response Harmonization.
    Single execution of canonical GenerateOutfit.derive_with_reason.
    Both reply.cards[0] and reply.outfitIntelligence represent the EXACT same recommendation result.
    """
    clean_occasion: Optional[str] = None
    if occasion and isinstance(occasion, str) and occasion.strip():
        clean_occasion = occasion.strip().lower()

    profile = None
    vibe_attrs = None
    if user_state is not None and user_id is not None:
        try:
            profile = user_state.get_profile(user_id=user_id)
            style_profile = getattr(profile, "style_profile", None) if profile else None
            if isinstance(style_profile, dict):
                raw_style = style_profile.get("style_type") or style_profile.get("styleType")
                vibe_attrs = resolve_vibe_attributes(raw_style)
        except Exception:
            profile = None
            vibe_attrs = None

    if vibe_attrs is None and user is not None and getattr(user, "face", None) is not None:
        vibe_attrs = resolve_vibe_attributes(getattr(user.face, "styleType", None))

    resolved_occasions: list[str] = []
    if preferred_occasions is not None:
        resolved_occasions = [
            str(o).strip().lower()
            for o in preferred_occasions
            if isinstance(o, str) and o.strip()
        ]
    elif user and user.preferredOccasions:
        resolved_occasions = [
            str(o).strip().lower()
            for o in user.preferredOccasions
            if isinstance(o, str) and o.strip()
        ]
    elif profile is not None and isinstance(getattr(profile, "preferences", None), dict):
        raw_pref_occ = profile.preferences.get("preferred_occasions")
        if isinstance(raw_pref_occ, list):
            resolved_occasions = [
                str(o).strip().lower()
                for o in raw_pref_occ
                if isinstance(o, str) and o.strip()
            ]

    event_code: Optional[str] = None
    if user_id is not None and events is not None:
        try:
            today_utc = _utc_today()
            nearest = events.list_for_user(
                user_id=user_id, from_date=today_utc, order="asc", page=1, page_size=1
            )[0]
            if nearest:
                nearest_event = nearest[0]
                event_date = getattr(nearest_event, "event_date", None)
                if event_date is None or event_date >= today_utc:
                    raw_event_type = getattr(nearest_event, "event_type", None)
                    if isinstance(raw_event_type, str) and raw_event_type.strip():
                        event_code = raw_event_type.strip().lower()
        except Exception as exc:
            logger.warning(
                "Failed to retrieve upcoming event for AI stylist (%s)",
                type(exc).__name__,
            )
            event_code = None

    clean_occasion, _ = resolve_effective_occasions(
        explicit_occasion=clean_occasion,
        event_code=event_code,
        preferred_occasions=resolved_occasions,
        vibe_attrs=vibe_attrs,
    )

    structured_weather: Optional[WeatherContext] = None
    weather_label: Optional[str] = None
    if isinstance(weather_context, WeatherContext):
        structured_weather = weather_context
        temp_round = int(round(weather_context.temperature_c))
        weather_label = f"{temp_round}°C • {weather_context.condition_text}"
    elif isinstance(weather_context, str) and weather_context.strip():
        weather_label = weather_context.strip()

    clean_mood = mood.strip().lower() if (mood and isinstance(mood, str) and mood.strip()) else "classic"
    clean_fit: Optional[str] = (
        fit.strip().lower()
        if (fit and isinstance(fit, str) and fit.strip())
        else (vibe_attrs.preferred_fit if vibe_attrs is not None else None)
    )
    clean_palette: Optional[str] = (
        color_palette.strip().lower()
        if (color_palette and isinstance(color_palette, str) and color_palette.strip())
        else (vibe_attrs.preferred_palette if vibe_attrs is not None else None)
    )

    pref_item_ids: list[str] = []
    if preferred_item_ids is not None:
        pref_item_ids = [str(i) for i in preferred_item_ids if i is not None]

    # Slot swap variant seed if user asked to swap a slot
    effective_seed = seed
    if slot_to_swap and not effective_seed:
        effective_seed = f"swap_{slot_to_swap}_alt"

    # Resolve GenerateOutfit use case and user_id
    exec_user_id: Optional[UUID] = None
    if generate_outfit is not None:
        use_case = generate_outfit
        exec_user_id = user_id
    elif user_id is not None and wardrobe_items is not None:
        # Authenticated user with server repositories
        use_case = GenerateOutfit(
            wardrobe_items=wardrobe_items,
            user_state=user_state or EphemeralUserStateRepository(preferred_occasions=resolved_occasions),
        )
        exec_user_id = user_id
    else:
        # Guest or in-memory execution: zero database writes, zero fabricated UUIDs
        ephemeral_wardrobe = (
            wardrobe_items
            if isinstance(wardrobe_items, EphemeralWardrobeItemRepository)
            else EphemeralWardrobeItemRepository(user.wardrobe if user and user.wardrobe else [])
        )
        ephemeral_user_state = (
            user_state
            if isinstance(user_state, EphemeralUserStateRepository)
            else EphemeralUserStateRepository(preferred_occasions=resolved_occasions)
        )
        use_case = GenerateOutfit(
            wardrobe_items=ephemeral_wardrobe,
            user_state=ephemeral_user_state,
        )
        exec_user_id = None

    try:
        derive_kwargs = dict(
            user_id=exec_user_id,
            occasion=clean_occasion,
            mood=clean_mood,
            fit=clean_fit,
            color_palette=clean_palette,
            seed=effective_seed,
            preferred_item_ids=pref_item_ids or None,
        )
        if structured_weather is not None:
            derive_kwargs["weather_context"] = structured_weather
        if clean_occasion is None:
            derive_kwargs["allow_empty_occasion"] = True
        if clean_fit is None or clean_palette is None:
            derive_kwargs["allow_empty_preferences"] = True
        rec, empty_reason = use_case.derive_with_reason(**derive_kwargs)
    except Exception as exc:
        logger.exception("Failed to derive canonical outfit recommendation: %s", exc)
        card = SuggestionCard(
            kind="outfit",
            title="Outfit Recommendation Unavailable",
            subtitle="Unable to generate an outfit recommendation at this time. Please try again.",
            score=None,
            items=[],
            action="open_wardrobe",
        )
        oi = OutfitIntelligence(
            selectedItemIds=[],
            outfitComposition=OutfitComposition(),
            occasion=clean_occasion or "",
            stylingRationale=card.subtitle,
            compatibilityRationale="",
            confidence=0.0,
            explanation="",
            dataAvailability="full",
            matchScore=None,
            status="unavailable",
        )
        return [card], oi

    if rec is None:
        if empty_reason == EMPTY_WARDROBE or empty_reason == "empty_wardrobe":
            card = SuggestionCard(
                kind="outfit",
                title="Empty Wardrobe",
                subtitle="Add tops and bottoms to your wardrobe to get personalized outfit recommendations.",
                score=None,
                items=["No wardrobe items catalogued yet"],
                action="open_wardrobe",
            )
            oi = OutfitIntelligence(
                selectedItemIds=[],
                outfitComposition=OutfitComposition(),
                occasion=clean_occasion or "",
                stylingRationale=card.subtitle,
                compatibilityRationale="",
                confidence=0.0,
                explanation="",
                dataAvailability="full",
                matchScore=None,
                status="empty_wardrobe",
            )
            return [card], oi
        elif empty_reason == MISSING_REQUIRED_CATEGORY or empty_reason == "missing_required_category":
            card = SuggestionCard(
                kind="outfit",
                title="Incomplete Wardrobe",
                subtitle="You need at least one top and one bottom in your wardrobe to build an outfit.",
                score=None,
                items=["Add missing wardrobe categories to unlock outfits"],
                action="open_wardrobe",
            )
            oi = OutfitIntelligence(
                selectedItemIds=[],
                outfitComposition=OutfitComposition(),
                occasion=clean_occasion or "",
                stylingRationale=card.subtitle,
                compatibilityRationale="",
                confidence=0.0,
                explanation="",
                dataAvailability="full",
                matchScore=None,
                status="missing_required_category",
            )
            return [card], oi
        else:
            card = SuggestionCard(
                kind="outfit",
                title="No Matching Outfit",
                subtitle="No compatible outfit combination found for this occasion.",
                score=None,
                items=[],
                action="open_wardrobe",
            )
            oi = OutfitIntelligence(
                selectedItemIds=[],
                outfitComposition=OutfitComposition(),
                occasion=clean_occasion or "",
                stylingRationale=card.subtitle,
                compatibilityRationale="",
                confidence=0.0,
                explanation="",
                dataAvailability="full",
                matchScore=None,
                status="no_legal_candidate",
            )
            return [card], oi

    # Successful recommendation: Map canonical result into SuggestionCard & OutfitIntelligence
    card_score = int(round(rec.match_score * 100))
    if rec.reasons:
        card_subtitle = ". ".join(r.rstrip(".") for r in rec.reasons[:2]) + "."
    else:
        card_subtitle = rec.occasion_match or (
            f"Assembled for a {clean_occasion} occasion."
            if clean_occasion
            else "Assembled for your outfit."
        )

    if weather_label:
        card_subtitle = f"{card_subtitle} (Weather: {weather_label})"

    items = [f"{c.name} - {c.category.title()}" for c in rec.components]

    # Categorize components
    top_ids = [
        c.id for c in rec.components
        if c.category.lower() in ("top", "tops", "shirt", "shirts", "tee", "t-shirt", "t-shirts", "polos", "polo", "sweater", "sweaters")
    ]
    bottom_ids = [
        c.id for c in rec.components
        if c.category.lower() in ("bottom", "bottoms", "pants", "trousers", "jeans", "shorts", "chino", "chinos")
    ]
    outerwear_ids = [
        c.id for c in rec.components
        if c.category.lower() in ("outerwear", "jacket", "jackets", "blazer", "blazers", "coat", "coats")
    ]
    footwear_ids = [
        c.id for c in rec.components
        if c.category.lower() in ("footwear", "shoes", "shoe", "sneakers", "boots", "boot", "oxford", "derbies", "loafers")
    ]
    accessory_ids = [
        c.id for c in rec.components
        if c.category.lower() in ("accessory", "accessories", "hat", "belt", "watch", "tie", "scarf")
    ]

    card = SuggestionCard(
        kind="outfit",
        title=rec.title,
        subtitle=card_subtitle,
        score=card_score,
        items=items,
        action="open_outfit",
    )

    comp = OutfitComposition(
        topIds=top_ids,
        bottomIds=bottom_ids,
        outerwearIds=outerwear_ids,
        footwearIds=footwear_ids,
        accessoryIds=accessory_ids,
        styleScore=0,
    )

    oi = OutfitIntelligence(
        selectedItemIds=[c.id for c in rec.components],
        outfitComposition=comp,
        occasion=clean_occasion or "",
        stylingRationale=card_subtitle,
        compatibilityRationale=rec.color_harmony or rec.body_fit or "",
        confidence=round(rec.match_score, 2),
        explanation=rec.reasons[0] if rec.reasons else (rec.occasion_match or ""),
        dataAvailability="full" if len(rec.components) >= 4 else "partial",
        matchScore=card_score,
        status="success",
    )

    cards = [card]

    # If alternatives were specifically requested, generate runner-up alternatives
    if include_alternatives:
        for seed_idx, alt_seed in enumerate(["alt_look_1", "alt_look_2"], start=1):
            try:
                alt_kwargs = dict(
                    user_id=exec_user_id,
                    occasion=clean_occasion,
                    mood=clean_mood,
                    fit=clean_fit,
                    color_palette=clean_palette,
                    seed=alt_seed,
                )
                if structured_weather is not None:
                    alt_kwargs["weather_context"] = structured_weather
                if clean_occasion is None:
                    alt_kwargs["allow_empty_occasion"] = True
                if clean_fit is None or clean_palette is None:
                    alt_kwargs["allow_empty_preferences"] = True
                alt_rec, _ = use_case.derive_with_reason(**alt_kwargs)
                if alt_rec and alt_rec.components:
                    alt_items = [f"{c.name} - {c.category.title()}" for c in alt_rec.components]
                    cards.append(
                        SuggestionCard(
                            kind="outfit",
                            title=f"Alternative {seed_idx}: {alt_rec.title}",
                            subtitle=f"{alt_rec.match_score:.0%} match • {alt_rec.occasion_match or 'Alternative ensemble'}",
                            score=int(round(alt_rec.match_score * 100)),
                            items=alt_items,
                            action="open_outfit",
                        )
                    )
            except Exception:
                pass

    return cards, oi


def recommend_outfit(
    occasion: Optional[str],
    user: Optional[UserContext],
    *,
    user_id: Optional[UUID] = None,
    generate_outfit: Optional[GenerateOutfit] = None,
    wardrobe_items: Optional[WardrobeItemRepository] = None,
    user_state: Optional[UserStateRepository] = None,
    events: Optional[UserEventRepository] = None,
    preferred_item_ids: Optional[Sequence[str]] = None,
    preferred_occasions: Optional[Sequence[str]] = None,
    fit: Optional[str] = None,
    color_palette: Optional[str] = None,
    mood: Optional[str] = None,
    seed: Optional[str] = None,
    weather_context: Optional[WeatherContext | str] = None,
) -> List[SuggestionCard]:
    """Recommend an outfit by delegating to canonical GenerateOutfit use case.

    Stage 1D Batch 4B.3: Canonical Outfit Recommendation Delegation.
    Replaces static catalog lookups with canonical candidate generation, filtering,
    scoring, ranking, and grounded explanation reasons.

    Execution paths:
    - Authenticated: uses validated user_id and authoritative database/provided repositories.
    - Guest: uses in-memory EphemeralWardrobeItemRepository and EphemeralUserStateRepository
      with zero database queries, zero persistence, and zero fabricated UUIDs.
    """
    cards, _ = derive_canonical_outfit_recommendation(
        occasion,
        user,
        user_id=user_id,
        generate_outfit=generate_outfit,
        wardrobe_items=wardrobe_items,
        user_state=user_state,
        events=events,
        preferred_item_ids=preferred_item_ids,
        preferred_occasions=preferred_occasions,
        fit=fit,
        color_palette=color_palette,
        mood=mood,
        seed=seed,
        weather_context=weather_context,
    )
    return cards


def recommend_hairstyle(
    user: Optional[UserContext],
    *,
    knowledge: Optional[KnowledgeSource] = None,
) -> List[SuggestionCard]:
    raw_face = (
        user.face.faceShape.strip()
        if user and user.face and user.face.faceShape
        else ""
    )
    skin_tone = (
        user.face.skinTone.strip()
        if user and user.face and user.face.skinTone
        else ""
    )
    body_type = (
        user.face.bodyType.strip()
        if user and user.face and user.face.bodyType
        else ""
    )
    style_type = (
        user.face.styleType.strip()
        if user and user.face and user.face.styleType
        else ""
    )

    appearance = AppearanceProfile(
        faceShape=raw_face,
        skinTone=skin_tone,
        bodyType=body_type,
        styleType=style_type,
    )

    preferred_ids = (
        frozenset(user.savedLooks) | frozenset(s.lower().replace(" ", "_") for s in user.savedLooks)
        if user and user.savedLooks
        else frozenset()
    )
    preferences = HairstylePreferences(preferredLookIds=preferred_ids)

    ks = knowledge or CatalogKnowledgeSource()
    result = analysis_rules.recommend_hairstyle(ks, appearance, preferences=preferences)

    top = result.top
    top_score = int(round(top.matchScore * 100))
    top_subtitle = _safe_subtitle(
        list(top.reasons),
        top.description,
        raw_face,
        "Versatile style that works across various face proportions. Add a face scan to personalize.",
    )

    cards = [
        SuggestionCard(
            kind="hairstyle",
            title=top.name,
            subtitle=top_subtitle,
            score=top_score,
            items=_format_tips(top.stylingTips),
            action="open_hairstyle",
        )
    ]

    if result.alternatives:
        alt = result.alternatives[0]
        alt_score = int(round(alt.matchScore * 100))
        alt_subtitle = _safe_subtitle(
            list(alt.reasons),
            alt.description,
            raw_face,
            "Alternative versatile style. Add a face scan to see personalized fit.",
        )
        cards.append(
            SuggestionCard(
                kind="hairstyle",
                title=alt.name,
                subtitle=alt_subtitle,
                score=alt_score,
                items=_format_tips(alt.stylingTips),
                action="open_hairstyle",
            )
        )

    return cards


def recommend_grooming(
    user: Optional[UserContext],
    *,
    knowledge: Optional[KnowledgeSource] = None,
) -> List[SuggestionCard]:
    raw_face = (
        user.face.faceShape.strip()
        if user and user.face and user.face.faceShape
        else ""
    )
    skin_tone = (
        user.face.skinTone.strip()
        if user and user.face and user.face.skinTone
        else ""
    )
    body_type = (
        user.face.bodyType.strip()
        if user and user.face and user.face.bodyType
        else ""
    )
    style_type = (
        user.face.styleType.strip()
        if user and user.face and user.face.styleType
        else ""
    )

    appearance = AppearanceProfile(
        faceShape=raw_face,
        skinTone=skin_tone,
        bodyType=body_type,
        styleType=style_type,
    )

    preferred_ids = (
        frozenset(user.savedLooks) | frozenset(s.lower().replace(" ", "_") for s in user.savedLooks)
        if user and user.savedLooks
        else frozenset()
    )
    preferences = HairstylePreferences(preferredLookIds=preferred_ids)

    ks = knowledge or CatalogKnowledgeSource()
    result = grooming_rules.recommend_grooming(ks, appearance, preferences=preferences)

    top = result.top
    top_score = int(round(top.matchScore * 100))
    top_subtitle = _safe_subtitle(
        list(top.reasons),
        top.description,
        raw_face,
        "Versatile grooming style with clean defined lines. Add a face scan to personalize.",
    )

    cards = [
        SuggestionCard(
            kind="grooming",
            title=top.name,
            subtitle=top_subtitle,
            score=top_score,
            items=_format_tips(top.stylingTips),
            action="open_grooming",
        )
    ]

    if result.alternatives:
        alt = result.alternatives[0]
        alt_score = int(round(alt.matchScore * 100))
        alt_subtitle = _safe_subtitle(
            list(alt.reasons),
            alt.description,
            raw_face,
            "Alternative grooming option with minimal daily maintenance.",
        )
        cards.append(
            SuggestionCard(
                kind="grooming",
                title=alt.name,
                subtitle=alt_subtitle,
                score=alt_score,
                items=_format_tips(alt.stylingTips),
                action="open_grooming",
            )
        )

    return cards


def wardrobe_summary(user: Optional[UserContext]) -> List[SuggestionCard]:
    items = user.wardrobe if user and user.wardrobe else catalog.WARDROBE
    favorites = sum(1 for i in items if i.isFavorite)
    categories = sorted({i.category for i in items})
    return [
        SuggestionCard(
            kind="wardrobe",
            title="Wardrobe Health",
            subtitle=(
                f"You have {len(items)} items across {len(categories)} categories "
                f"with {favorites} favourites. Consider a lightweight jacket to "
                "unlock more combinations."
            ),
            items=[f"{len(items)} items catalogued", f"{favorites} favourites", f"{len(categories)} categories"],
            action="open_wardrobe",
        )
    ]


def daily_tip(user: Optional[UserContext]) -> List[SuggestionCard]:
    return [catalog.STYLE_TIP]


def greeting_reply() -> str:
    return (
        "Hey! I'm your Fansivibe stylist. Ask me what to wear, "
        "how to style your hair, or which grooming look suits you. "
        "I learn from your wardrobe and scans as we talk."
    )


def thanks_reply() -> str:
    return "Anytime! Want me to build an outfit or find you a new hairstyle next?"


def clarify_outfit_text() -> str:
    return "What's the occasion? That helps me pick the perfect look for you."


def unknown_reply() -> str:
    return (
        "I can help with outfits, hairstyles, grooming, and your wardrobe. "
        "Try asking: 'What should I wear to a date?' or 'Which beard suits me?'"
    )
