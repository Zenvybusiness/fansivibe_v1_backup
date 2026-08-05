"""Recommendation catalog used by the assistant.

This mirrors the Flutter mock data files so the assistant's suggestion cards
match what the app's own screens show. In a later phase these are replaced by
learning-engine-backed generation.
"""

from __future__ import annotations

from typing import Dict, List

from app.models.schemas import SuggestionCard, WardrobeItem

# ---------------------------------------------------------------------------
# Wardrobe
# ---------------------------------------------------------------------------

WARDROBE: List[WardrobeItem] = [
    WardrobeItem(id="1", name="Merino Crew Neck", category="tops", color="Charcoal", material="Wool", isFavorite=True),
    WardrobeItem(id="2", name="Linen Button-Down", category="tops", color="White", material="Linen"),
    WardrobeItem(id="3", name="Cashmere Sweater", category="tops", color="Navy", material="Cashmere", isFavorite=True),
    WardrobeItem(id="4", name="Silk Blouse", category="tops", color="Blush", material="Silk"),
    WardrobeItem(id="5", name="Oxford Shirt", category="tops", color="Light Blue", material="Cotton"),
    WardrobeItem(id="6", name="Graphic Tee", category="tops", color="Black", material="Cotton"),
    WardrobeItem(id="7", name="Polo Shirt", category="tops", color="Burgundy", material="Pique Cotton"),
    WardrobeItem(id="8", name="Turtleneck", category="tops", color="Cream", material="Merino Wool"),
    WardrobeItem(id="9", name="Tapered Trousers", category="bottoms", color="Charcoal", material="Wool", isFavorite=True),
    WardrobeItem(id="10", name="Slim Chinos", category="bottoms", color="Khaki", material="Cotton"),
    WardrobeItem(id="11", name="Dark Denim Jeans", category="bottoms", color="Indigo", material="Denim", isFavorite=True),
    WardrobeItem(id="12", name="Linen Shorts", category="bottoms", color="Beige", material="Linen"),
    WardrobeItem(id="13", name="Pleated Trousers", category="bottoms", color="Black", material="Polyester"),
    WardrobeItem(id="14", name="Unstructured Blazer", category="outerwear", color="Charcoal", material="Wool Blend", isFavorite=True),
    WardrobeItem(id="15", name="Leather Jacket", category="outerwear", color="Black", material="Leather", isFavorite=True),
    WardrobeItem(id="16", name="Denim Jacket", category="outerwear", color="Light Wash", material="Denim"),
    WardrobeItem(id="17", name="Trench Coat", category="outerwear", color="Stone", material="Cotton"),
    WardrobeItem(id="18", name="Leather Chelsea Boots", category="footwear", color="Black", material="Leather", isFavorite=True),
    WardrobeItem(id="19", name="White Sneakers", category="footwear", color="White", material="Canvas"),
    WardrobeItem(id="20", name="Loafers", category="footwear", color="Brown", material="Suede"),
    WardrobeItem(id="21", name="Dress Oxfords", category="footwear", color="Tan", material="Leather"),
    WardrobeItem(id="22", name="Leather Belt", category="accessories", color="Black", material="Leather", isFavorite=True),
    WardrobeItem(id="23", name="Silk Tie", category="accessories", color="Navy", material="Silk"),
    WardrobeItem(id="24", name="Watch", category="accessories", color="Silver", material="Stainless Steel", isFavorite=True),
]

# ---------------------------------------------------------------------------
# Outfit recommendation (mirrors OutfitRecommendation.mock)
# ---------------------------------------------------------------------------

REFINED_OFFICE = SuggestionCard(
    kind="outfit",
    title="Refined Office Ensemble",
    subtitle="A structured navy blazer over a cream oxford with charcoal trousers and brown derbies.",
    score=91,
    items=[
        "Navy Textured Blazer - Outerwear",
        "Cream Cotton Oxford - Tops",
        "Charcoal Tailored Trousers - Bottoms",
        "Brown Leather Derbies - Footwear",
        "Gold Minimalist Watch - Accessories",
    ],
    action="open_outfit",
)

CASUAL_LOOK = SuggestionCard(
    kind="outfit",
    title="Effortless Casual",
    subtitle="A relaxed weekend look built around denim, a white tee, and clean white sneakers.",
    score=88,
    items=[
        "Light Wash Denim Jacket - Outerwear",
        "White Cotton Tee - Tops",
        "Dark Denim Jeans - Bottoms",
        "White Sneakers - Footwear",
    ],
    action="open_outfit",
)

# ---------------------------------------------------------------------------
# Hairstyle (mirrors HairstyleAnalysisResult.mock)
# ---------------------------------------------------------------------------

TEXTURED_QUIFF = SuggestionCard(
    kind="hairstyle",
    title="Textured Quiff",
    subtitle="Modern volume on top that suits oval faces. Medium maintenance, trim every 4-5 weeks.",
    score=94,
    items=[
        "Volumizing mousse on damp hair",
        "Blow-dry upward with a round brush",
        "Finish with light-hold matte clay",
    ],
    action="open_hairstyle",
)

CLASSIC_POMPADOUR = SuggestionCard(
    kind="hairstyle",
    title="Classic Pompadour",
    subtitle="A polished, formal alternative with clean sides and swept-back volume.",
    score=87,
    items=["Strong-hold pomade", "Blow-dry back and up", "Finish with light hairspray"],
    action="open_hairstyle",
)

# ---------------------------------------------------------------------------
# Grooming (mirrors GroomingAnalysisResult.mock)
# ---------------------------------------------------------------------------

STRUCTURED_GOATEE = SuggestionCard(
    kind="grooming",
    title="Structured Goatee",
    subtitle="Frames the chin for oval faces. Keep edges clean, oil daily, trim every 3-4 days.",
    score=92,
    items=[
        "Medium-long length (10-15mm)",
        "Natural cheek line mid-cheek",
        "Rectangular or wayfarer frames in dark acetate",
    ],
    action="open_grooming",
)

CLASSIC_STUBBLE = SuggestionCard(
    kind="grooming",
    title="Classic Stubble",
    subtitle="Low-maintenance 3mm stubble that reads professional and rugged.",
    score=85,
    items=["3mm guard trim", "Neckline just above the Adam's apple"],
    action="open_grooming",
)

# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------

STYLE_TIP = SuggestionCard(
    kind="tip",
    title="Daily Style Tip",
    subtitle="A textured leather belt in warm brown adds depth to monochrome outfits without breaking the clean silhouette.",
    action="open_stylist",
)

WARDROBE_INSIGHT = SuggestionCard(
    kind="wardrobe",
    title="Wardrobe Health",
    subtitle="Your wardrobe is balanced across seasons. A lightweight jacket would unlock 8+ more combinations.",
    items=["24 items catalogued", "8 favourites", "6 categories"],
    action="open_wardrobe",
)

# ---------------------------------------------------------------------------
# Intents / tools
# ---------------------------------------------------------------------------

OCCASIONS = ["casual", "office", "date", "party", "travel"]

OCCASION_TO_LOOK: Dict[str, SuggestionCard] = {
    "office": REFINED_OFFICE,
    "casual": CASUAL_LOOK,
    "date": SuggestionCard(
        kind="outfit",
        title="Date Night Refined",
        subtitle="Dark denim, a burgundy polo, and Chelsea boots for a memorable evening.",
        score=89,
        items=[
            "Leather Chelsea Boots - Footwear",
            "Burgundy Polo - Tops",
            "Dark Denim Jeans - Bottoms",
        ],
        action="open_outfit",
    ),
    "party": SuggestionCard(
        kind="outfit",
        title="Party Statement",
        subtitle="Black pleated trousers, a black tee, and a leather jacket for standout confidence.",
        score=86,
        items=[
            "Leather Jacket - Outerwear",
            "Black Graphic Tee - Tops",
            "Black Pleated Trousers - Bottoms",
        ],
        action="open_outfit",
    ),
    "travel": SuggestionCard(
        kind="outfit",
        title="Travel Comfort",
        subtitle="Linen shirt, chinos, and loafers keep you comfortable through long days.",
        score=87,
        items=[
            "Linen Button-Down - Tops",
            "Slim Chinos - Bottoms",
            "Loafers - Footwear",
        ],
        action="open_outfit",
    ),
}

# Actions the assistant can request; the client maps these to app routes.
NAVIGATION_MAP = {
    "open_outfit": ("build-outfit", "Build Outfit"),
    "open_hairstyle": ("hairstyle", "Hairstyle Studio"),
    "open_grooming": ("grooming", "Grooming Studio"),
    "open_wardrobe": ("wardrobe", "My Wardrobe"),
    "open_stylist": ("stylist", "Stylist"),
    "open_daily": ("daily-outfit", "Today's Look"),
    "open_discover": ("discover", "Discover"),
}
