"""Assistant tools: our own recommendation functions.

Each tool takes the user context (wardrobe, face data, saved looks) plus any
parameters parsed from the message and returns suggestion cards. The LLM (when
configured) only writes natural-language text around these structured results.
"""

from __future__ import annotations

from typing import List, Optional

from app.data import catalog
from app.models.schemas import SuggestionCard, UserContext

# How many wardrobe items we already own that appear in a look.
_owned_names = {item.name.lower() for item in catalog.WARDROBE}


def _owned(items: List[str]) -> int:
    return sum(1 for item in items if item.split(" - ")[0].lower() in _owned_names)


def recommend_outfit(
    occasion: Optional[str], user: Optional[UserContext]
) -> List[SuggestionCard]:
    if occasion:
        card = catalog.OCCASION_TO_LOOK.get(occasion, catalog.REFINED_OFFICE)
        return [card]
    # No occasion specified — prefer a look that uses the most owned items.
    owned_casual = _owned(catalog.CASUAL_LOOK.items)
    owned_office = _owned(catalog.REFINED_OFFICE.items)
    return [catalog.CASUAL_LOOK if owned_casual >= owned_office else catalog.REFINED_OFFICE]


def recommend_hairstyle(user: Optional[UserContext]) -> List[SuggestionCard]:
    face = (user.face.faceShape.lower() if user and user.face and user.face.faceShape else "oval")
    if face in ("round", "square", "rectangle"):
        return [catalog.CLASSIC_POMPADOUR, catalog.TEXTURED_QUIFF]
    return [catalog.TEXTURED_QUIFF, catalog.CLASSIC_POMPADOUR]


def recommend_grooming(user: Optional[UserContext]) -> List[SuggestionCard]:
    return [catalog.STRUCTURED_GOATEE, catalog.CLASSIC_STUBBLE]


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
