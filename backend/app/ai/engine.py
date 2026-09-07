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

from typing import List

from app.ai import intent, llm_backend, tools
from app.models.schemas import (
    AssistantReply,
    AssistantRequest,
    ClarificationOption,
    NavigationRequest,
    SuggestionCard,
    UserContext,
)
from app.data import catalog
from app.domain.services.analysis_rules import compute_clothing_intelligence, compute_outfit_intelligence

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


def handle(request: AssistantRequest) -> AssistantReply:
    messages = request.messages
    user = request.user
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

            # Extract item data from the wardrobe (use first item or defaults)
            if wardrobe:
                first_item = wardrobe[0]
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
                preferred_occasions=user.preferredOccasions if user else [],
            )

            # Compute outfit intelligence (STEP 7C)
            outfit = compute_outfit_intelligence(
                item_category=item_category,
                item_color=item_color,
                item_material=item_material,
                item_is_favorite=item_is_favorite,
                wardrobe_context=wardrobe_context,
                preferred_occasions=user.preferredOccasions if user else [],
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

            # Combined text: wardrobe summary + intelligence explanation + outfit info
            conf_disclaimer_text = ""
            if outfit.data_availability == "sparse":
                conf_disclaimer_text = " Based on limited wardrobe data."
            elif outfit.data_availability == "partial":
                conf_disclaimer_text = " Based on partial wardrobe data."

            text = f"Here's what I know about your wardrobe. {explanation_text}{outfit.confidence:.1f}/1.0 ({outfit.confidence_level.level}){conf_disclaimer_text}"
        else:
            text = cards[0].subtitle if cards else tools.unknown_reply()
        reply = AssistantReply(intent=it, text=text, cards=cards)

    # --- Optional LLM enrichment (server-side, never changes structure) ----
    if llm_backend.is_available() and reply.text:
        reply.text = llm_backend.enrich_reply(reply.intent, reply.text, _context_summary(user))

    return reply
