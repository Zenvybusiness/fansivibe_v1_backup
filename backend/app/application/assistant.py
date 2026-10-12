"""Application use case — assistant card-interaction feedback (UC-23).

`SubmitAssistantCardFeedback` is the single client-facing signal input
(endpoint #17, `POST /v1/assistant/feedback`): one append-only
`learning_signals` row per call (tier 1, never idempotent — retries append).

The use case owns the interactionType → signal_type mapping. Only the two
contract interactions exist; the client can never name a `signal_type`
itself (M10 sole writer, PR-7). No card existence or ownership lookup:
assistant cards are ephemeral suggestions, so there is nothing to look up
and no card table exists.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, database_failure
from app.application.analysis import EphemeralGarmentAnalysis
from app.application.learning import mark_styled_today
from app.domain.ports.repositories import ActivityDayRepository, LearningSignalRepository
from app.models.schemas import (
    AssistantReply,
    ChatMessage,
    ClarificationOption,
    SuggestionCard,
    UserContext,
    WardrobeItem,
)

_INTERACTION_TO_SIGNAL_TYPE = {
    "opened": "suggestion_opened",
    "navigated": "assistant_navigation",
}


class SubmitAssistantCardFeedback:
    """Record one card interaction as a learning signal (endpoint #17)."""

    def __init__(
        self,
        *,
        signals: LearningSignalRepository,
        activity_days: Optional[ActivityDayRepository] = None,
    ) -> None:
        self._signals = signals
        self._activity_days = activity_days

    def __call__(
        self,
        *,
        user_id: UUID,
        card_id: Optional[str],
        card_title: Optional[str],
        interaction_type: str,
    ) -> str:
        """Persist the signal; returns the stored `signal_type`.

        Raises 422 for any interaction outside the frozen contract pair.
        The card reference is stored as the signal label (title preferred,
        then id); with neither supplied the interaction itself is the label
        so the append-only row always carries an honest, non-empty label.
        """
        signal_type = _INTERACTION_TO_SIGNAL_TYPE.get(interaction_type)
        if signal_type is None:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Some of the provided values are not valid. Please check your input.",
                details={
                    "field_errors": [
                        {
                            "field": "interactionType",
                            "error": "unknown value",
                            "allowed": sorted(_INTERACTION_TO_SIGNAL_TYPE),
                        }
                    ]
                },
            )
        label = card_title or card_id or interaction_type
        try:
            self._signals.insert_look_saved(
                user_id=user_id,
                signal_type=signal_type,
                label=label,
                context={"interaction_type": interaction_type},
            )
            if self._activity_days is not None:
                # M10-A: today's styled-day upsert rides this same commit.
                # Append-only behavior is unchanged — retries still append
                # another signal row while the day row stays one.
                mark_styled_today(activity_days=self._activity_days, user_id=user_id)
            self._signals.commit()
        except Exception:
            self._signals.rollback()
            raise database_failure()
        return signal_type


# --- Image-aware chat --------------------------------------------------------
# ponytail: single complementary-category lookup, extend only with a real
# gap (e.g. user-confirmed pairings), never a scoring engine.
_COMPLEMENTARY_CATEGORY = {
    "tops": ("bottoms", "footwear"),
    "bottoms": ("tops", "footwear"),
    "outerwear": ("tops", "bottoms"),
    "footwear": ("bottoms", "tops"),
    "accessories": ("tops", "outerwear"),
}

_MAX_WARDROBE_MATCHES = 3


def _match_wardrobe_items(
    wardrobe: list[WardrobeItem],
    *,
    category: str | None,
    color: str | None,
) -> list[tuple[WardrobeItem, str]]:
    """Match the observed garment against the caller's own wardrobe snapshot.

    Only items present in the supplied snapshot are ever returned, most
    relevant first: same-category items whose color shares a word with the
    observed color, then same-category rest, then favorites. Each match
    carries an honest reason naming the shared attribute. Empty when the
    category is unknown or nothing matches — never a fabricated item.
    """
    if not category or not wardrobe:
        return []
    same = [i for i in wardrobe if (i.category or "").strip().lower() == category]
    if not same:
        return []
    color_words = {w for w in (color or "").lower().split() if w}
    scored: list[tuple[int, int, str, WardrobeItem]] = []
    for item in same:
        item_words = {w for w in (item.color or "").lower().split() if w}
        color_hit = 1 if color_words and (color_words & item_words) else 0
        scored.append((-color_hit, 0 if item.isFavorite else 1, item.name.lower(), item))
    scored.sort()
    matches: list[tuple[WardrobeItem, str]] = []
    for _, _, _, item in scored[:_MAX_WARDROBE_MATCHES]:
        bits = [f"same category ({category})"]
        item_words = {w for w in (item.color or "").lower().split() if w}
        shared = sorted(color_words & item_words)
        if shared:
            bits.append(f"color match ({', '.join(shared)})")
        elif item.isFavorite:
            bits.append("one of your favorites")
        matches.append((item, "; ".join(bits)))
    return matches


def _describe_observation(snapshot: dict) -> str:
    """Grounded observation sentences from measured attributes only.

    Null attributes are omitted, never defaulted. Uncertain inferences are
    hedged ("looks like"); brand, price, and exact fabric composition are
    never claimed.
    """
    subject = snapshot.get("subcategory") or snapshot.get("category") or "garment"
    color = snapshot.get("color")
    pattern = snapshot.get("pattern")
    material = snapshot.get("material")
    style = snapshot.get("style")
    fit = snapshot.get("fit")
    bits = [f"I can see {subject}"]
    if color:
        bits[-1] += f" in {color}"
    bits[0] += " in this photo."
    if pattern and pattern.lower() != "solid":
        bits.append(f"The pattern reads as {pattern}.")
    if material:
        bits.append(f"The material looks like {material} from the photo.")
    if style:
        bits.append(f"The overall vibe is {style}.")
    if fit:
        bits.append(f"The fit appears {fit}.")
    confidence = snapshot.get("confidence") or 0.0
    if confidence < 0.6:
        bits.append(
            "I'm less certain about some details, so confirm the category "
            "before saving anything."
        )
    return " ".join(bits)


class ChatWithImage:
    """Answer one outfit-photo question with genuine vision measurement.

    Runs the ACTUAL uploaded bytes through the shared garment vision port
    (the same adapter as the garment passes — never a text placeholder),
    then grounds the reply in the measured snapshot plus the caller's own
    wardrobe snapshot. Stateless and ephemeral: bytes are hashed and
    discarded by the analysis use case, never persisted or logged.
    """

    def __init__(self, *, garment_port) -> None:
        self._garment_port = garment_port

    def __call__(
        self,
        *,
        image,
        message: str = "",
        history: list[ChatMessage] | None = None,
        user: UserContext | None = None,
    ) -> AssistantReply:
        snapshot = EphemeralGarmentAnalysis(garment_port=self._garment_port)(
            image=image
        )
        wardrobe = list(user.wardrobe) if user and user.wardrobe else []
        matches = _match_wardrobe_items(
            wardrobe,
            category=snapshot.get("category"),
            color=snapshot.get("color"),
        )
        style_type = (user.face.styleType if user and user.face else None) or ""

        paragraphs = [_describe_observation(snapshot)]
        if style_type:
            paragraphs.append(
                f"For your {style_type} style, this "
                f"{snapshot.get('category') or 'piece'} is a workable base — "
                "keep the rest of the outfit in the same lane."
            )
        if matches:
            names = ", ".join(m[0].name for m in matches)
            paragraphs.append(
                f"From your own wardrobe, the closest match{'es are' if len(matches) > 1 else ' is'} "
                f"{names}."
            )
        elif wardrobe:
            paragraphs.append(
                "Nothing in your saved wardrobe closely matches this piece, "
                "so I'd style it with what you own rather than force a match."
            )
        else:
            paragraphs.append(
                "Your wardrobe looks empty from here — add a few pieces and "
                "I can match this photo against clothes you actually own."
            )
        # Complementary-category hint reuses the observed category only.
        complement = _COMPLEMENTARY_CATEGORY.get(snapshot.get("category") or "")
        if complement:
            paragraphs.append(
                f"To complete the look, reach for {complement[0]} and "
                f"{complement[1]} that echo these tones."
            )
        paragraphs.append(
            "What I can't tell from a photo: brand, price, or exact fabric."
        )
        if not (message or "").strip():
            paragraphs.append("What would you like to know about this outfit?")

        cards = [
            SuggestionCard(
                kind="outfit",
                title=f"Observed: {snapshot.get('subcategory') or snapshot.get('category') or 'garment'}",
                subtitle="Measured from your photo — null means not clearly visible.",
                items=[
                    f"{key}: {snapshot[key]}"
                    for key in ("category", "color", "pattern", "material", "style", "fit")
                    if snapshot.get(key)
                ],
            )
        ]
        for item, reason in matches:
            facts = [f"Category: {item.category}", f"Color: {item.color}"]
            if item.material:
                facts.append(f"Material: {item.material}")
            cards.append(
                SuggestionCard(
                    kind="wardrobe",
                    title=item.name,
                    subtitle=f"From your wardrobe — {reason}.",
                    items=facts,
                    action="open_wardrobe",
                )
            )

        return AssistantReply(
            intent="outfit_image",
            text=" ".join(paragraphs),
            cards=cards,
            clarifications=[
                ClarificationOption(
                    label="Closest wardrobe match?",
                    value="Which item in my wardrobe is the closest match?",
                ),
                ClarificationOption(
                    label="What shoes work?",
                    value="What shoes would work with this outfit?",
                ),
                ClarificationOption(
                    label="Make it casual?",
                    value="How can I make this outfit more casual?",
                ),
            ],
        )
