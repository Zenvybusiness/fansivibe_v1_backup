"""The Fansivibe assistant engine — our own orchestration layer.

Flow for every message:
  1. classify intent (rules-based, deterministic)
  2. parse parameters (e.g. occasion)
  3. call the matching tool(s) to build typed suggestion cards
  4. apply our dialogue policy (clarify ambiguous questions, navigation requests)
  5. enrich the reply text via the self-hosted model when available

Structure is always ours; the LLM only writes natural language.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from app.ai import intent, llm_backend, tools
from app.models.schemas import (
    AssistantReply,
    AssistantRequest,
    ClarificationOption,
    NavigationRequest,
    OutfitIntelligence,
    OutfitComposition,
    SuggestionCard,
    UserContext,
)
from app.data import catalog
from app.domain.services.analysis_rules import (
    compute_clothing_intelligence,
    compute_outfit_intelligence,
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
    select_outfit_alternatives,
)

_OUTFIT_CLARIFICATION = [
    ClarificationOption(label="Casual", value="casual"),
    ClarificationOption(label="Office", value="office"),
    ClarificationOption(label="Date", value="date"),
    ClarificationOption(label="Party", value="party"),
    ClarificationOption(label="Travel", value="travel"),
]


def _context_summary(user: UserContext | None) -> str:
    if not user:
        return "No user context yet."
    face = user.face or None
    face_line = ""
    if face:
        bits = [face.faceShape, face.skinTone, face.bodyType, face.styleType]
        face_line = "Face/analysis: " + ", ".join(b for b in bits if b) + "."
    wardrobe_line = (
        "Wardrobe: " + ", ".join(i.name for i in user.wardrobe[:12]) + "."
        if user.wardrobe
        else "Wardrobe: empty."
    )
    looks = "Saved looks: " + ", ".join(user.savedLooks) + "." if user.savedLooks else ""
    return f"{face_line}\n{wardrobe_line}\n{looks}"


def _cards_from(intents: List[str], user: UserContext | None, occasion: str | None) -> List[SuggestionCard]:
    cards: List[SuggestionCard] = []
    for it in intents:
        if it == intent.INTENT_OUTFIT:
            cards.extend(tools.recommend_outfit(occasion, user))
        elif it == intent.INTENT_HAIRSTYLE:
            cards.extend(tools.recommend_hairstyle(user))
        elif it == intent.INTENT_GROOMING:
            cards.extend(tools.recommend_grooming(user))
        elif it == intent.INTENT_WARDROBE:
            cards.extend(tools.wardrobe_summary(user))
        elif it == intent.INTENT_TIP:
            cards.extend(tools.daily_tip(user))
    return cards


def _navigation_for(message: str) -> NavigationRequest | None:
    low = message.lower()
    for target, (route, label) in catalog.NAVIGATION_MAP.items():
        if target.startswith("open_") and target[5:] in low:
            return NavigationRequest(route=route, label=label)
    for target, (route, label) in {
        "wardrobe": ("wardrobe", "My Wardrobe"),
        "stylist": ("stylist", "Stylist"),
        "discover": ("discover", "Discover"),
        "home": ("home", "Home"),
        "profile": ("profile", "Profile"),
        "today": ("daily-outfit", "Today's Look"),
        "hairstyle": ("hairstyle", "Hairstyle Studio"),
        "grooming": ("grooming", "Grooming Studio"),
        "outfit": ("build-outfit", "Build Outfit"),
    }.items():
        if target in low:
            return NavigationRequest(route=route, label=label)
    return None


def handle(
    request: AssistantRequest,
    *,
    preferred_occasions: Optional[List[str]] = None,
    preferred_item_ids: Optional[List[str]] = None,
) -> AssistantReply:
    """Handle one assistant turn.

    ``preferred_occasions`` carries the already-resolved occasions list:
    STEP 11.10 lets the entry point prefer the server-persisted list while
    callers that pass ``None`` keep the historical client-driven behavior
    (``request.user.preferredOccasions``). The engine itself stays free of
    database concerns.

    ``preferred_item_ids`` carries the already-resolved saved-outfit wardrobe
    IDs (STEP 11.17: ``resolve_preferred_item_ids`` over the owner's
    ``saved_looks`` at the entry point). Callers that pass ``None`` (or an
    empty list) keep the exact pre-11.17 behavior. The INTENT_WARDROBE and
    INTENT_OUTFIT (STEP 13.13) paths consume it; every other intent is
    untouched.
    """
    messages = request.messages
    user = request.user
    request_occasions = (
        preferred_occasions
        if preferred_occasions is not None
        else (user.preferredOccasions if user else [])
    )
    if not messages:
        return AssistantReply(
            intent=intent.INTENT_GREETING,
            text=tools.greeting_reply(),
        )

    last = messages[-1].content
    user_text = last if messages[-1].role == "user" else ""
    it = intent.classify(user_text)
    occasion = intent.detect_occasion(user_text)

    # A bare occasion reply (e.g. "date" or "office") is an outfit request.
    if occasion is not None and it in (intent.INTENT_CLARIFY, intent.INTENT_UNKNOWN):
        it = intent.INTENT_OUTFIT

    # --- Dialogue policy ----------------------------------------------------
    if it == intent.INTENT_GREETING:
        reply = AssistantReply(intent=it, text=tools.greeting_reply())
    elif it == intent.INTENT_THANKS:
        reply = AssistantReply(intent=it, text=tools.thanks_reply())
    elif it == intent.INTENT_NAVIGATE:
        nav = _navigation_for(user_text)
        reply = AssistantReply(
            intent=it,
            text=(
                f"Taking you to {nav.label}." if nav
                else "I can take you to your wardrobe, stylist, discover, or profile."
            ),
            navigation=nav,
        )
    elif it == intent.INTENT_CLARIFY or it == intent.INTENT_UNKNOWN:
        reply = AssistantReply(
            intent=it,
            text=tools.unknown_reply(),
            clarifications=[
                ClarificationOption(label="What should I wear?", value="outfit"),
                ClarificationOption(label="Best hairstyle for me?", value="hairstyle"),
                ClarificationOption(label="Grooming tips", value="grooming"),
                ClarificationOption(label="Show my wardrobe", value="wardrobe"),
            ],
        )
    elif it == intent.INTENT_OUTFIT and occasion is None:
        # Ambiguous outfit question → ask a clarifying question (our policy).
        reply = AssistantReply(
            intent=it,
            text=tools.clarify_outfit_text(),
            clarifications=_OUTFIT_CLARIFICATION,
        )
    else:
        cards = _cards_from([it], user, occasion)
        if it == intent.INTENT_OUTFIT:
            text = (
                f"For {occasion}, I'd go with the {cards[0].title} — "
                + (cards[0].subtitle or "")
                + " Tap the card to build it."
            )
        elif it == intent.INTENT_HAIRSTYLE:
            text = (
                f"Your top pick is the {cards[0].title} ({cards[0].score}% match). "
                + (cards[0].subtitle or "")
            )
        elif it == intent.INTENT_GROOMING:
            text = (
                f"The {cards[0].title} suits you best ({cards[0].score}% match). "
                + (cards[0].subtitle or "")
            )
        elif it == intent.INTENT_WARDROBE:
            wardrobe = user.wardrobe if user and user.wardrobe else []

            # STEP 13.6: candidate pipeline (pure domain helpers; no DB/IO).
            # Wardrobe → generate → score → rank → winner. The winner's
            # primary item becomes the evaluated item below; its IDs populate
            # the selection fields. No viable candidate (e.g. sparse wardrobe
            # without tops+bottoms) falls through to the historical
            # wardrobe[0] path, byte-identical to before this step.
            preferred_set = (
                frozenset(preferred_item_ids)
                if preferred_item_ids
                else frozenset()
            )
            items_by_id = {
                item.id: item for item in wardrobe
                if getattr(item, "id", None)
            }
            # STEP 13.12: keep the ranked list so the already-ranked
            # runners-up (ranked[1:3]) can surface as alternatives below.
            # No second ranking: select_best_outfit_candidate reuses the
            # same single ranking contract (idempotent on ranked input).
            ranked = rank_outfit_candidates([
                score_outfit_candidate(
                    candidate, items_by_id, preferred_set, request_occasions,
                )
                for candidate in generate_outfit_candidates(wardrobe)
            ])
            winner = select_best_outfit_candidate(ranked)
            alternatives = select_outfit_alternatives(ranked)
            if winner is None:
                first_item = wardrobe[0] if wardrobe else None
                winner_ids: List[str] = []
                winner_buckets: tuple = ((), (), (), (), ())
            else:
                winner_buckets = (
                    winner.top_ids, winner.bottom_ids, winner.outerwear_ids,
                    winner.footwear_ids, winner.accessory_ids,
                )
                winner_ids = [item_id for bucket in winner_buckets for item_id in bucket]
                first_item = items_by_id.get(winner_ids[0]) if winner_ids else None
                if first_item is None:
                    first_item = wardrobe[0] if wardrobe else None

            # Extract item data from the featured item (wardrobe[0] when no
            # winner; the winner's primary item otherwise).
            if first_item is not None:
                item_category = first_item.category
                item_color = first_item.color
                item_material = first_item.material
                item_is_favorite = first_item.isFavorite
            else:
                item_category = ""
                item_color = ""
                item_material = None
                item_is_favorite = False

            # Build wardrobe context from full wardrobe
            from app.domain.value_objects import (
                OutfitComposition as DomainOutfitComposition,
            )
            from app.domain.value_objects import WardrobeContext
            items_per_category: dict[str, int] = {}
            favorite_count = 0
            for item in wardrobe:
                items_per_category[item.category] = items_per_category.get(item.category, 0) + 1
                if item.isFavorite:
                    favorite_count += 1

            wardrobe_context = WardrobeContext(
                total_items=len(wardrobe),
                favorite_count=favorite_count,
                items_per_category=items_per_category,
                style_score=87,  # default, not user-specific without LearningService
            )

            # Compute clothing intelligence with all required arguments
            intelligence = compute_clothing_intelligence(
                item_category=item_category,
                item_color=item_color,
                item_material=item_material,
                item_is_favorite=item_is_favorite,
                wardrobe_context=wardrobe_context,
                preferred_occasions=request_occasions,
            )

            # Compute outfit intelligence (STEP 7C) — reuse pre-computed CI.
            # STEP 11.17: the evaluated item's own ID plus the resolved
            # saved-outfit set flow into OI; None/empty keeps baseline output.
            outfit = compute_outfit_intelligence(
                clothing_intelligence=intelligence,
                item_color=item_color,
                item_material=item_material,
                item_is_favorite=item_is_favorite,
                wardrobe_context=wardrobe_context,
                preferred_occasions=request_occasions,
                item_id=first_item.id if first_item is not None else "",
                preferred_item_ids=preferred_set,
            )

            # STEP 13.6: surface the winner through the existing selection
            # fields (STEP 7C.2 rendering below already handles populated
            # fields). No-API/schema change: domain object copy only.
            if winner_ids:
                top, bottom, outer, shoe, acc = winner_buckets
                outfit = replace(
                    outfit,
                    selected_item_ids=list(winner_ids),
                    outfit_composition=DomainOutfitComposition(
                        top_ids=list(top),
                        bottom_ids=list(bottom),
                        outerwear_ids=list(outer),
                        footwear_ids=list(shoe),
                        accessory_ids=list(acc),
                    ),
                )

            # Build explanation text with confidence disclaimer (STEP 6)
            conf = intelligence.confidence
            conf_disclaimer = ""
            if conf < 0.5:
                conf_disclaimer = " (Note: limited data — this is informational only, not a strong styling claim.)"
            elif conf < 0.3:
                conf_disclaimer = " (Note: very limited data — this is purely informational.)"

            explanation_text = intelligence.explanation.text + conf_disclaimer

            # Build suggestion cards from compatible categories and suitable occasions
            cards: List[SuggestionCard] = []

            # Compatible category cards
            for compat in intelligence.compatible_categories:
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title=f"Compatible: {compat.category}",
                    subtitle=compat.rationale,
                    action="open_wardrobe",
                ))

            # Suitable occasion cards
            for occ in intelligence.suitable_occasions:
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title=f"Suitable for: {occ.occasion}",
                    subtitle=f"Confidence: {occ.confidence:.0%}",
                    action="open_wardrobe",
                ))

            # Outfit intelligence cards (STEP 7C)
            # Confidence level card
            cards.append(SuggestionCard(
                kind="clothing_intelligence",
                title=f"Confidence: {outfit.confidence_level.level}",
                subtitle=f"{outfit.confidence:.1f}/1.0",
                action="open_wardrobe",
            ))

            # Data availability card
            availability_text = ""
            if outfit.data_availability == "sparse":
                availability_text = "Based on limited wardrobe data"
            elif outfit.data_availability == "partial":
                availability_text = "Based on partial wardrobe data"
            if availability_text:
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title=f"Data Availability",
                    subtitle=availability_text,
                    action="open_wardrobe",
                ))

            # Coverage card
            cards.append(SuggestionCard(
                kind="clothing_intelligence",
                title=f"Coverage: {len(outfit.outfit_coverage.missing_categories)}/5 categories missing",
                subtitle=f"Ratio: {outfit.outfit_coverage.coverage_ratio:.0%}",
                action="open_wardrobe",
            ))

            # Selected item IDs card (STEP 7C.2)
            if outfit.selected_item_ids:
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title=f"Selected Items: {len(outfit.selected_item_ids)}",
                    subtitle=", ".join(outfit.selected_item_ids[:4]) + ("..." if len(outfit.selected_item_ids) > 4 else ""),
                    action="open_wardrobe",
                ))

            # Outfit composition by category card (STEP 7C.2)
            comp = outfit.outfit_composition
            comp_parts = []
            if comp.top_ids:
                comp_parts.append(f"Top(s): {len(comp.top_ids)}")
            if comp.bottom_ids:
                comp_parts.append(f"Bottom(s): {len(comp.bottom_ids)}")
            if comp.outerwear_ids:
                comp_parts.append(f"Outerwear: {len(comp.outerwear_ids)}")
            if comp.footwear_ids:
                comp_parts.append(f"Footwear: {len(comp.footwear_ids)}")
            if comp.accessory_ids:
                comp_parts.append(f"Accessories: {len(comp.accessory_ids)}")
            if comp_parts:
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title="Outfit Composition",
                    subtitle=" | ".join(comp_parts),
                    action="open_wardrobe",
                ))

            # STEP 13.12: ranked alternatives (already-ranked runners-up,
            # same objects, no rescore/rerank). Reuses the Selected-Items
            # card vocabulary (owned IDs only — never scores, confidence,
            # or styleScore, so no new card kind or schema field). Sparse
            # wardrobes add no cards here (fallback identical to before).
            for position, alternative in enumerate(alternatives, start=1):
                alternative_ids = [
                    item_id
                    for bucket in (
                        alternative.top_ids, alternative.bottom_ids,
                        alternative.outerwear_ids, alternative.footwear_ids,
                        alternative.accessory_ids,
                    )
                    for item_id in bucket
                ]
                cards.append(SuggestionCard(
                    kind="clothing_intelligence",
                    title=f"Alternative {position}",
                    subtitle=", ".join(alternative_ids[:4]) + ("..." if len(alternative_ids) > 4 else ""),
                    action="open_wardrobe",
                ))

            # Combined text: wardrobe summary + intelligence explanation + outfit info
            conf_disclaimer_text = ""
            if outfit.data_availability == "sparse":
                conf_disclaimer_text = " Based on limited wardrobe data."
            elif outfit.data_availability == "partial":
                conf_disclaimer_text = " Based on partial wardrobe data."

            # Build category-specific item ID mapping for the Assistant response
            item_id_map = {}
            for item_id in outfit.selected_item_ids:
                # Parse item IDs to categorize them - use first letter or known mapping
                # This is a best-effort mapping; the client should use the wardrobe screen for full details
                item_id_map.setdefault("all", []).append(item_id)

            text = f"Here's what I know about your wardrobe. {explanation_text}{outfit.confidence:.1f}/1.0 ({outfit.confidence_level.level}){conf_disclaimer_text}"
        else:
            text = cards[0].subtitle if cards else tools.unknown_reply()
        reply = AssistantReply(intent=it, text=text, cards=cards)
        if it == intent.INTENT_OUTFIT:
            # STEP 11.4.1: the domain `outfit` object is bound only inside the
            # INTENT_WARDROBE branch, so referencing it here raised NameError
            # on the outfit path — and its domain shape never matched the wire
            # `AssistantReply.outfitIntelligence` contract. Build the wire
            # object directly from the existing recommendation outputs (the
            # detected occasion + the recommended card's own text); every other
            # field keeps the schema's existing default. No scoring change, no
            # selection change, no personalization input.
            # STEP 13.13: owned-wardrobe winner integration (integration
            # only; the frozen pipeline is reused unmodified). Wardrobe →
            # generate → score → rank → select; the winner's IDs populate
            # the existing selection fields below. No viable candidate (e.g.
            # empty/sparse wardrobe) keeps the historical static-catalog
            # wire shell (empty selection, default composition). No
            # alternatives in OUTFIT (WARDROBE-only); no confidence /
            # styleScore involvement.
            outfit_wardrobe = user.wardrobe if user and user.wardrobe else []
            outfit_preferred = (
                frozenset(preferred_item_ids)
                if preferred_item_ids
                else frozenset()
            )
            outfit_items_by_id = {
                item.id: item for item in outfit_wardrobe
                if getattr(item, "id", None)
            }
            outfit_winner = select_best_outfit_candidate(
                rank_outfit_candidates([
                    score_outfit_candidate(
                        candidate, outfit_items_by_id, outfit_preferred,
                        request_occasions,
                    )
                    for candidate in generate_outfit_candidates(outfit_wardrobe)
                ])
            )
            reply.outfitIntelligence = OutfitIntelligence(
                occasion=occasion or "",
                stylingRationale=cards[0].subtitle if cards else "",
            )
            if outfit_winner is not None:
                outfit_winner_ids = [
                    item_id
                    for bucket in (
                        outfit_winner.top_ids, outfit_winner.bottom_ids,
                        outfit_winner.outerwear_ids, outfit_winner.footwear_ids,
                        outfit_winner.accessory_ids,
                    )
                    for item_id in bucket
                ]
                if outfit_winner_ids:
                    reply.outfitIntelligence = OutfitIntelligence(
                        occasion=reply.outfitIntelligence.occasion,
                        stylingRationale=(
                            reply.outfitIntelligence.stylingRationale
                        ),
                        selectedItemIds=list(outfit_winner_ids),
                        outfitComposition=OutfitComposition(
                            topIds=list(outfit_winner.top_ids),
                            bottomIds=list(outfit_winner.bottom_ids),
                            outerwearIds=list(outfit_winner.outerwear_ids),
                            footwearIds=list(outfit_winner.footwear_ids),
                            accessoryIds=list(outfit_winner.accessory_ids),
                        ),
                    )

    # --- Optional LLM enrichment (server-side, never changes structure) ----
    if llm_backend.is_available() and reply.text:
        reply.text = llm_backend.enrich_reply(reply.intent, reply.text, _context_summary(user))

    return reply
