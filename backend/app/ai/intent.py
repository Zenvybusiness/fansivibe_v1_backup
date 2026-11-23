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
INTENT_CLOTHING_INTELLIGENCE = "clothing_intelligence"
INTENT_NAVIGATE = "navigate"
INTENT_TIP = "tip"
INTENT_GREETING = "greeting"
INTENT_THANKS = "thanks"
INTENT_CLARIFY = "clarify"
INTENT_UNKNOWN = "unknown"

_OCCASION_SYNONYMS = {
    "work": "office",
    "office": "office",
    "meeting": "office",
    "interview": "office",
    "business": "office",
    "corporate": "office",
    "conference": "office",
    "wedding": "formal",
    "formal": "formal",
    "gala": "formal",
    "black tie": "formal",
    "dinner": "date",
    "date": "date",
    "anniversary": "date",
    "party": "party",
    "club": "party",
    "celebration": "party",
    "travel": "travel",
    "flight": "travel",
    "trip": "travel",
    "airport": "travel",
    "vacation": "travel",
    "casual": "casual",
    "weekend": "casual",
    "errands": "casual",
    "brunch": "casual",
    "everyday": "casual",
    "daily": "casual",
    "today": "today",
    "now": "today",
}

_OCCASION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _OCCASION_SYNONYMS.keys()) + r")\b",
    re.IGNORECASE,
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

_GARMENT_TERMS = {
    "trousers", "pants", "chinos", "jeans", "shorts", "skirt",
    "shirt", "t-shirt", "tee", "polo", "sweater", "crewneck", "crew neck",
    "turtleneck", "blouse", "top", "tops",
    "blazer", "jacket", "coat", "trench", "outerwear",
    "shoes", "sneakers", "boots", "loafers", "derbies", "oxfords", "footwear",
    "suit", "tuxedo", "hoodie", "cardigan",
}

_SLOT_SWAP_PATTERNS = [
    (re.compile(r"\b(?:replace|change|swap|different)\s+(?:the\s+)?(shoes?|sneakers?|boots?|loafers?|footwear)\b", re.IGNORECASE), "footwear"),
    (re.compile(r"\b(?:replace|change|swap|different)\s+(?:the\s+)?(shirt|t-?shirt|tee|polo|sweater|top|tops|blouse)\b", re.IGNORECASE), "tops"),
    (re.compile(r"\b(?:replace|change|swap|different)\s+(?:the\s+)?(pants|trousers|chinos|jeans|bottom|bottoms|shorts)\b", re.IGNORECASE), "bottoms"),
    (re.compile(r"\b(?:replace|change|swap|different)\s+(?:the\s+)?(jacket|coat|blazer|outerwear)\b", re.IGNORECASE), "outerwear"),
    (re.compile(r"\b(?:replace|change|swap|different)\s+(?:the\s+)?(accessories|belt|watch|tie|hat)\b", re.IGNORECASE), "accessories"),
]

_FORMALITY_PATTERNS = [
    (re.compile(r"\b(?:more|make it|dress it)\s+(?:more\s+)?(?:formal|dressy|elegant|elevated|classy)\b", re.IGNORECASE), "more_formal"),
    (re.compile(r"\b(?:more|make it|dress it)\s+(?:more\s+)?(?:casual|relaxed|laid[- ]back|informal)\b", re.IGNORECASE), "more_casual"),
]

_ALTERNATIVES_PATTERNS = [
    re.compile(r"\b(?:suggest|give me|show me|provide)\s+(?:three|3|another|other|alternative)\s+(?:outfits?|options?|looks?)\b", re.IGNORECASE),
    re.compile(r"\b(?:three|3)\s+outfits?\b", re.IGNORECASE),
    re.compile(r"\b(?:another|different|other)\s+(?:option|look|outfit)\b", re.IGNORECASE),
    re.compile(r"\balternatives?\b", re.IGNORECASE),
]

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

    # Follow-ups (formality, swaps, alternatives)
    if detect_swap_slot(text) is not None:
        return INTENT_OUTFIT
    if detect_formality_change(text) is not None:
        return INTENT_OUTFIT
    if detect_alternatives_request(text):
        return INTENT_OUTFIT

    # Styling garments or queries like "style my black trousers" / "what can I wear with my white shirt"
    if any(phrase in low for phrase in ("style my", "style this", "wear with", "pair with", "what should i wear", "what can i wear")):
        return INTENT_OUTFIT

    if _contains_any(low, {"outfit", "wear", "look", "dress", "style", "clothes", "what should i"} | _GARMENT_TERMS):
        return INTENT_OUTFIT

    if _contains_any(low, {"tip", "advice", "suggestion", "improve", "better"}):
        return INTENT_TIP

    if len(_tokens(low)) < 2:
        return INTENT_CLARIFY

    return INTENT_UNKNOWN


def detect_occasion(text: str) -> Optional[str]:
    """Return the normalized canonical occasion mentioned in a message, if any."""
    low = text.lower()
    match = _OCCASION_PATTERN.search(low)
    if not match:
        return None
    token = match.group(1).lower()
    return _OCCASION_SYNONYMS.get(token, token)


def detect_swap_slot(text: str) -> Optional[str]:
    """Detect if the user requests swapping a specific slot (e.g. 'replace the shoes')."""
    for pattern, slot in _SLOT_SWAP_PATTERNS:
        if pattern.search(text):
            return slot
    return None


def detect_formality_change(text: str) -> Optional[str]:
    """Detect if the user requests shifting formality (e.g. 'make it more formal')."""
    for pattern, direction in _FORMALITY_PATTERNS:
        if pattern.search(text):
            return direction
    return None


def detect_alternatives_request(text: str) -> bool:
    """Detect if the user requests multiple or alternative outfits."""
    for pattern in _ALTERNATIVES_PATTERNS:
        if pattern.search(text):
            return True
    return False


def extract_target_garment_query(text: str) -> Optional[str]:
    """Extract a mentioned garment phrase from requests like 'style my black trousers'."""
    low = text.lower()
    patterns = [
        re.compile(r"\b(?:style|pair|wear)\s+(?:my|this|the|with my|with the)\s+([a-z\s]+?)(?:\s+(?:differently|today|for|with)|\?|\.|$)", re.IGNORECASE),
        re.compile(r"\bwhat\s+(?:can|should)\s+i\s+wear\s+with\s+(?:my|this|the)\s+([a-z\s]+?)(?:\s+(?:today|for)|\?|\.|$)", re.IGNORECASE),
        re.compile(r"\bhow\s+(?:to|can i)\s+style\s+(?:my|this|the)\s+([a-z\s]+?)(?:\s+(?:differently|today|for)|\?|\.|$)", re.IGNORECASE),
    ]
    for p in patterns:
        m = p.search(low)
        if m:
            candidate = m.group(1).strip()
            # Verify candidate contains at least one garment term or color
            tokens = set(_tokens(candidate))
            if tokens.intersection(_GARMENT_TERMS) or len(tokens) >= 1:
                return candidate
    return None


def match_wardrobe_item(
    garment_query: str,
    wardrobe: list,
) -> tuple[Optional[Any], Optional[str]]:
    """Match a garment query against the user's actual wardrobe items.

    Returns (matched_item_or_none, queried_garment_name).
    Never fabricates an item; returns None when the user doesn't own it.
    """
    if not garment_query or not wardrobe:
        return None, garment_query

    q = garment_query.lower().strip()
    q_tokens = set(_tokens(q))

    # 1. Exact or partial match on item name
    for item in wardrobe:
        name = getattr(item, "name", "").lower()
        if q == name or q in name or name in q:
            return item, getattr(item, "name", q)

    # 2. Match on color + category (e.g. "black trousers", "white shirt")
    best_item = None
    best_overlap = 0
    for item in wardrobe:
        name_tokens = set(_tokens(getattr(item, "name", "").lower()))
        color = getattr(item, "color", "").lower()
        cat = getattr(item, "category", "").lower()
        item_words = name_tokens | {color, cat}
        
        # Category aliases
        if cat in ("bottoms", "pants"):
            item_words.update({"trousers", "pants", "chinos", "jeans", "bottoms"})
        elif cat in ("tops", "shirt"):
            item_words.update({"shirt", "t-shirt", "tee", "top", "tops", "sweater"})
        elif cat in ("footwear", "shoes"):
            item_words.update({"shoes", "sneakers", "boots", "loafers", "footwear"})
        elif cat in ("outerwear", "jackets"):
            item_words.update({"jacket", "coat", "blazer", "outerwear"})

        overlap = len(q_tokens.intersection(item_words))
        if overlap > best_overlap and overlap >= 2:
            best_overlap = overlap
            best_item = item

    if best_item is not None:
        return best_item, getattr(best_item, "name", q)

    return None, garment_query

