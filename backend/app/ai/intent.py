"""Intent classification for the Fansivibe assistant.

This is our own deterministic intent router. It maps a user message to a
typed intent. The self-hosted LLM (when configured) enriches the reply text
but never controls routing — structure stays ours.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.data.catalog import OCCASIONS

INTENT_OUTFIT = "outfit"
INTENT_HAIRSTYLE = "hairstyle"
INTENT_GROOMING = "grooming"
INTENT_WARDROBE = "wardrobe"
INTENT_NAVIGATE = "navigate"
INTENT_TIP = "tip"
INTENT_GREETING = "greeting"
INTENT_THANKS = "thanks"
INTENT_CLARIFY = "clarify"
INTENT_UNKNOWN = "unknown"

_OCCASION_PATTERN = re.compile(
    r"\b(" + "|".join(OCCASIONS) + r"|work|office|meeting|interview)\b"
)

_GREETING_WORDS = {"hi", "hello", "hey", "yo", "hola", "namaste"}
_THANKS_WORDS = {"thanks", "thank", "thx", "appreciate"}
_NAVIGATE_WORDS = {"open", "go to", "show me", "navigate", "take me", "launch"}
_NAVIGATE_TARGETS = {
    "wardrobe": "wardrobe",
    "stylist": "stylist",
    "discover": "discover",
    "home": "home",
    "profile": "profile",
    "today": "daily-outfit",
    "today's look": "daily-outfit",
    "outfit": "build-outfit",
    "hairstyle": "hairstyle",
    "grooming": "grooming",
}

_TOKENIZE = re.compile(r"[a-z']+")


def _tokens(text: str) -> List[str]:
    return _TOKENIZE.findall(text.lower())


def _contains_any(text: str, words) -> bool:
    """Match single keywords by token, multi-word phrases by substring."""
    tokens = set(_tokens(text))
    for phrase in words:
        if " " in phrase:
            if phrase in text:
                return True
        elif phrase in tokens:
            return True
    return False


def classify(text: str) -> str:
    """Return the intent for a single user message (rules-based)."""
    low = text.lower()

    if _contains_any(low, _GREETING_WORDS) and len(_tokens(low)) <= 3:
        return INTENT_GREETING
    if _contains_any(low, _THANKS_WORDS) and len(_tokens(low)) <= 4:
        return INTENT_THANKS

    # Navigation requests take priority over ambiguous content words.
    if any(word in low for word in ("open", "take me", "go to", "show me", "navigate")):
        for target, route in _NAVIGATE_TARGETS.items():
            if target in low:
                return INTENT_NAVIGATE
        return INTENT_NAVIGATE

    if _contains_any(low, {"grooming", "beard", "mustache", "moustache", "glasses", "eyewear", "stubble", "goatee", "shave"}):
        return INTENT_GROOMING

    if _contains_any(low, {"hairstyle", "hair", "haircut", "quiff", "pompadour", "fade", "barber", "undercut"}):
        return INTENT_HAIRSTYLE

    if _contains_any(low, {"wardrobe", "closet", "my clothes", "what do i own", "inventory", "clothing items"}):
        return INTENT_WARDROBE

    if _contains_any(low, {"outfit", "wear", "look", "dress", "style", "clothes", "jacket", "shirt", "what should i"}):
        return INTENT_OUTFIT

    if _contains_any(low, {"tip", "advice", "suggestion", "improve", "better"}):
        return INTENT_TIP

    if len(_tokens(low)) < 2:
        return INTENT_CLARIFY

    return INTENT_UNKNOWN


def detect_occasion(text: str) -> Optional[str]:
    """Return the occasion mentioned in a message, if any."""
    low = text.lower()
    match = _OCCASION_PATTERN.search(low)
    if not match:
        return None
    token = match.group(1)
    if token in ("work", "office", "meeting", "interview"):
        return "office"
    return token
