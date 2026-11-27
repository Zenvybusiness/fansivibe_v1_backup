"""Canonical vibe-to-fashion-attribute mapping for Fansivibe recommendations.

Maps the supported onboarding and preference vibe identifiers to deterministic
scoring attributes (`preferred_palette`, `preferred_fit`, `default_occasion`,
`aesthetics`) without inventing unsupported vibe names or fabricating matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class VibeAttributes:
    """Fashion attributes associated with a supported style vibe."""

    canonical_id: str
    display_label: str
    preferred_palette: str
    preferred_fit: str
    default_occasion: str
    aesthetics: tuple[str, ...] = ()


_VIBE_DEFINITIONS: dict[str, VibeAttributes] = {
    "minimalist": VibeAttributes(
        canonical_id="minimalist",
        display_label="Minimalist",
        preferred_palette="monochrome",
        preferred_fit="slim",
        default_occasion="office",
        aesthetics=("minimalist", "minimal", "clean", "monochrome"),
    ),
    "classic": VibeAttributes(
        canonical_id="classic",
        display_label="Classic",
        preferred_palette="cool",
        preferred_fit="slim",
        default_occasion="formal",
        aesthetics=("classic", "tailored", "timeless", "formal"),
    ),
    "bold": VibeAttributes(
        canonical_id="bold",
        display_label="Bold",
        preferred_palette="warm",
        preferred_fit="relaxed",
        default_occasion="party",
        aesthetics=("bold", "statement", "expressive"),
    ),
    "trendy": VibeAttributes(
        canonical_id="trendy",
        display_label="Trendy",
        preferred_palette="monochrome",
        preferred_fit="relaxed",
        default_occasion="casual",
        aesthetics=("trendy", "streetwear", "street", "urban"),
    ),
    "streetwear": VibeAttributes(
        canonical_id="streetwear",
        display_label="Street Style",
        preferred_palette="monochrome",
        preferred_fit="relaxed",
        default_occasion="casual",
        aesthetics=("streetwear", "street", "trendy", "urban", "relaxed"),
    ),
    "natural": VibeAttributes(
        canonical_id="natural",
        display_label="Natural",
        preferred_palette="warm",
        preferred_fit="relaxed",
        default_occasion="casual",
        aesthetics=("natural", "bohemian", "boho", "earthy", "relaxed"),
    ),
    "bohemian": VibeAttributes(
        canonical_id="bohemian",
        display_label="Bohemian",
        preferred_palette="warm",
        preferred_fit="relaxed",
        default_occasion="casual",
        aesthetics=("bohemian", "boho", "natural", "flowing", "expressive"),
    ),
    "edgy": VibeAttributes(
        canonical_id="edgy",
        display_label="Edgy",
        preferred_palette="monochrome",
        preferred_fit="slim",
        default_occasion="party",
        aesthetics=("edgy", "dark", "monochrome", "unconventional"),
    ),
    "athleisure": VibeAttributes(
        canonical_id="athleisure",
        display_label="Athleisure",
        preferred_palette="cool",
        preferred_fit="relaxed",
        default_occasion="workout",
        aesthetics=("athleisure", "sporty", "athletic", "casual"),
    ),
}

_VIBE_ALIASES: dict[str, str] = {
    "minimal": "minimalist",
    "minimalist": "minimalist",
    "modern minimalist": "minimalist",
    "classic": "classic",
    "timeless": "classic",
    "formal": "classic",
    "bold": "bold",
    "statement": "bold",
    "trendy": "trendy",
    "street": "streetwear",
    "street style": "streetwear",
    "street_style": "streetwear",
    "streetwear": "streetwear",
    "natural": "natural",
    "boho": "bohemian",
    "bohemian": "bohemian",
    "edgy": "edgy",
    "athleisure": "athleisure",
    "sporty": "athleisure",
    "athletic": "athleisure",
    "casual": "trendy",
}


def resolve_vibe_attributes(raw_vibe: Optional[str]) -> Optional[VibeAttributes]:
    """Resolve a raw vibe/styleType string to its canonical [VibeAttributes].

    Returns `None` when the input is absent or unrecognized — never fabricates
    a vibe match.
    """
    if not isinstance(raw_vibe, str):
        return None
    normalized = " ".join(raw_vibe.strip().lower().split())
    if not normalized:
        return None
    canonical_key = _VIBE_ALIASES.get(normalized)
    if canonical_key is None:
        return None
    return _VIBE_DEFINITIONS.get(canonical_key)


def resolve_effective_occasions(
    *,
    explicit_occasion: Optional[str] = None,
    event_code: Optional[str] = None,
    preferred_occasions: Sequence[str] = (),
    vibe_attrs: Optional[VibeAttributes] = None,
) -> tuple[Optional[str], list[str]]:
    """Resolve primary occasion and deduplicated scoring occasions consistently.

    Precedence:
    1. Explicit user-selected occasion (when provided and not ``"today"``).
    2. Nearest upcoming event occasion code.
    3. User's persisted preferred occasions.
    4. Style vibe's default occasion.
    5. ``(None, [])`` — neutral 0 occasion points (never fabricate ``"casual"``).
    """
    clean_explicit = (
        explicit_occasion.strip().lower()
        if isinstance(explicit_occasion, str) and explicit_occasion.strip()
        else None
    )
    if clean_explicit == "today":
        clean_explicit = None

    clean_event = (
        event_code.strip().lower()
        if isinstance(event_code, str) and event_code.strip()
        else None
    )

    clean_prefs: list[str] = []
    for item in preferred_occasions:
        if isinstance(item, str) and item.strip():
            norm = item.strip().lower()
            if norm not in clean_prefs:
                clean_prefs.append(norm)

    if clean_explicit is not None:
        occasions = [clean_explicit]
        for pref in clean_prefs:
            if pref not in occasions:
                occasions.append(pref)
        return clean_explicit, occasions

    if clean_event is not None:
        occasions = [clean_event]
        for pref in clean_prefs:
            if pref not in occasions:
                occasions.append(pref)
        return clean_event, occasions

    if clean_prefs:
        return clean_prefs[0], clean_prefs

    if vibe_attrs is not None and vibe_attrs.default_occasion:
        default_occ = vibe_attrs.default_occasion.strip().lower()
        if default_occ:
            return default_occ, [default_occ]

    return None, []

