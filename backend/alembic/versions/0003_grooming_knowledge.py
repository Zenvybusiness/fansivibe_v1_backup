"""Grooming knowledge addition — adds grooming run type and look rows.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Grooming look entries — 4 cards mirroring the hairstyle cardinality.
# These mirror the wire HairstyleRecommendation fields plus scoreSeed used by
# the Scoring stage. `code` is the stable catalog id (looks.code, PR-3).
# ---------------------------------------------------------------------------

GROOMING_LOOKS: list[dict] = [
    {
        "code": "structured_goatee",
        "title": "Structured Goatee",
        "description": (
            "Frames the chin for oval faces. Keep edges clean, oil daily, "
            "trim every 3-4 days."
        ),
        "reasons": [
            "Strong jawline complement for oval face shapes",
            "Clean geometric shape reads intentional and polished",
            "Daily oiling keeps the skin and hair healthy",
        ],
        "stylingTips": (
            "Maintain medium-long length (10-15mm), define the cheek line "
            "at mid-cheek, use rectangular or wayfarer frames in dark acetate."
        ),
        "maintenance": "Medium • Trim every 3-4 days",
        "bestFor": "Oval, Heart, and Diamond face shapes",
        "scoreSeed": 0.92,
    },
    {
        "code": "classic_stubble",
        "title": "Classic Stubble",
        "description": (
            "Low-maintenance 3mm stubble that reads professional and rugged."
        ),
        "reasons": [
            "3mm stubble reads professional and rugged",
            "Requires minimal daily maintenance",
            "Suits most face shapes with even growth",
        ],
        "stylingTips": (
            "Use a 3mm guard trim, keep the neckline just above the Adam's apple."
        ),
        "maintenance": "Low • 3mm guard trim",
        "bestFor": "Oval, Round, and Square face shapes",
        "scoreSeed": 0.85,
    },
    {
        "code": "full_beard",
        "title": "Full Beard",
        "description": (
            "A full beard that provides strong facial framing. Best for "
            "oval and square face shapes with dense growth."
        ),
        "reasons": [
            "Provides strong facial framing for oval face shapes",
            "Adds density to patchy areas on square faces",
            "Reads as authoritative and grounded",
        ],
        "stylingTips": (
            "Comb daily with a boar-bristle brush, trim the neckline and "
            "cheeks every 1-2 weeks for a polished look."
        ),
        "maintenance": "High • Trim every 1-2 weeks",
        "bestFor": "Oval, Square, and Diamond face shapes",
        "scoreSeed": 0.75,
    },
    {
        "code": "goatee_with_mustache",
        "title": "Goatee with Mustache",
        "description": (
            "Combined goatee and mustache style that balances facial "
            "features. Suits rectangular and heart face shapes."
        ),
        "reasons": [
            "Balances broader foreheads on heart face shapes",
            "Adds width to narrow chins on rectangular faces",
            "Creates facial symmetry through central focus",
        ],
        "stylingTips": (
            "Trim the goatee to 5-7mm, shape the mustache to lie flat, "
            "clean the cheek lines daily for a neat appearance."
        ),
        "maintenance": "Medium • Trim every 3-5 days",
        "bestFor": "Rectangular and Heart face shapes",
        "scoreSeed": 0.71,
    },
]

# Grooming vocabulary — stable identifiers used by the decision engine and
# the save-layer look_id field. Mirrors the hairstyle code mapping (PR-3).
GROOMING_VOCAB: dict[str, str] = {
    "structured_goatee": "structured_goatee",
    "classic_stubble": "classic_stubble",
    "full_beard": "full_beard",
    "goatee_with_mustache": "goatee_with_mustache",
}


# ---------------------------------------------------------------------------
# Seed data — mirrors 0001's LOOKS_SEED + RUN_TYPES_SEED pattern
# ---------------------------------------------------------------------------

# Original run types from migration 0001, plus grooming
ALL_RUN_TYPES = [("hairstyle", "Hairstyle analysis"), ("grooming", "Grooming analysis")]

# Original looks from migration 0001, plus grooming looks
ALL_LOOKS_SEED = [
    # hairstyle looks (from 0001)
    (
        "textured_quiff",
        "Textured Quiff",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A modern take on the classic quiff with added texture and "
                "movement. The volume on top complements oval face shapes by "
                "adding vertical dimension while the textured finish keeps it "
                "effortless and contemporary."
            ),
            "stylingTips": (
                "Apply a volumizing mousse to damp hair, blow-dry upward using a "
                "round brush, then finish with a light-hold matte clay. Use fingers "
                "to create separation and texture."
            ),
            "maintenance": "Medium • Trim every 4-5 weeks",
            "bestFor": "Oval, Heart, and Rectangle face shapes",
            "reasons": [
                "Oval face shapes benefit from volume on top, which the quiff provides naturally",
                "Textured finish softens the structured silhouette for a modern, approachable look",
                "Works exceptionally well with warm medium skin tones and adds contrast",
                "Aligns with your Modern Classic Style DNA for a cohesive appearance",
            ],
            "scoreSeed": 0.94,
        },
    ),
    (
        "classic_pompadour",
        "Classic Pompadour",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A timeless pompadour with swept-back volume and clean sides. "
                "Offers a more polished, formal alternative while maintaining "
                "the vertical emphasis that suits your face shape."
            ),
            "stylingTips": (
                "Use a strong-hold pomade on towel-dried hair, blow-dry back "
                "and up, then comb into place. Finish with a light hairspray "
                "for all-day hold."
            ),
            "maintenance": "High • Trim every 3-4 weeks",
            "bestFor": "Oval, Round, and Square face shapes",
            "reasons": [
                "Provides elegant volume that elongates and balances facial features",
                "Clean sides keep the silhouette sharp and intentional",
                "Pairs naturally with structured, tailored wardrobe pieces",
            ],
            "scoreSeed": 0.87,
        },
    ),
    (
        "side_part",
        "Side Part",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A refined side part with medium length on top and tapered "
                "sides. A versatile, professional option that works across "
                "settings while maintaining a clean, structured appearance."
            ),
            "stylingTips": (
                "Apply a styling cream to damp hair, create a deep side part, "
                "and blow-dry in place. Finish with a light-hold wax for "
                "natural movement."
            ),
            "maintenance": "Low • Trim every 5-6 weeks",
            "bestFor": "Oval, Square, and Diamond face shapes",
            "reasons": [
                "Creates asymmetry that adds visual interest to symmetrical face shapes",
                "Tapered sides prevent the silhouette from feeling too wide",
                "Easy to transition from professional to casual settings",
            ],
            "scoreSeed": 0.82,
        },
    ),
    (
        "brushed_up_undercut",
        "Brushed Up Undercut",
        "1.0",
        {
            "kind": "hairstyle",
            "description": (
                "A contemporary undercut with brushed-up length on top. "
                "Provides maximum contrast between the longer top and faded "
                "sides for a bold, fashion-forward statement."
            ),
            "stylingTips": (
                "Apply a sea salt spray for texture, blow-dry forward and up, "
                "then use a matte paste to shape. Keep the sides faded every "
                "2-3 weeks."
            ),
            "maintenance": "Medium • Trim every 3-4 weeks",
            "bestFor": "Oval, Heart, and Diamond face shapes",
            "reasons": [
                "High contrast silhouette makes a strong style statement",
                "Undercut keeps the look clean and low-maintenance on the sides",
                "Brushed-up top adds height that complements oval face proportions",
            ],
            "scoreSeed": 0.78,
        },
    ),
    # grooming looks (added by this migration)
    *[
        (
            entry["code"],
            entry["title"],
            "1.1",  # content_version bumped with Grooming knowledge (G7)
            {
                "kind": "grooming",
                "description": entry["description"],
                "stylingTips": entry["stylingTips"],
                "maintenance": entry["maintenance"],
                "bestFor": entry["bestFor"],
                "reasons": entry["reasons"],
                "scoreSeed": entry["scoreSeed"],
            },
        )
        for entry in GROOMING_LOOKS
    ],
]


def _q(value: str) -> str:
    """Inline SQL literal for a trusted seed constant (never user input)."""
    return "'" + value.replace("'", "''") + "'"


def _seed() -> None:
    # Run types — add grooming alongside existing hairstyle
    for i, (code, label) in enumerate(ALL_RUN_TYPES):
        op.execute(
            f"INSERT INTO run_types (code, label, sort_order) "
            f"VALUES ({_q(code)}, {_q(label)}, {i}) "
            f"ON CONFLICT (code) DO NOTHING"
        )

    # Looks — add all entries (existing hairstyle + new grooming)
    for code, title, version, payload in ALL_LOOKS_SEED:
        op.execute(
            f"INSERT INTO looks (code, title, content_version, payload, published_at) "
            f"VALUES ({_q(code)}, {_q(title)}, {_q(version)}, "
            f"CAST({_q(json.dumps(payload))} AS jsonb), now()) "
            f"ON CONFLICT (code) DO NOTHING"
        )


def upgrade() -> None:
    _seed()


def downgrade() -> None:
    # Remove grooming run types
    op.execute(sa.text("DELETE FROM run_types WHERE code = 'grooming'"))
    # Remove grooming look rows
    for entry in GROOMING_LOOKS:
        code = entry["code"]
        op.execute(f"DELETE FROM looks WHERE code = {_q(code)}")
    # Do NOT drop the shared complete_analysis_run function
    # Do NOT drop the looks table or run_types table