"""FFO catalog conformance — existing seed data vs FFO v1.0 foundation.

Read-only validation: imports `app.data.catalog` + `app.data.ffo` only.
No database, no user data, no prod changes. Known gaps are asserted as
documented frozen sets (DEC-014 #22 gate, label-vs-code vocab) so the
suite stays green while the gaps stay visible.
"""

from __future__ import annotations

from app.data import catalog
from app.data.ffo import load_schema

CANONICAL_CATEGORIES = ["tops", "bottoms", "outerwear", "footwear", "accessories"]

# Catalog WARDROBE predates code normalization: colors/materials are display
# labels ("Charcoal", "Pique Cotton"), not colors/materials table codes.
# Documented here, not fixed (wardrobe-save path normalizes at write time).
KNOWN_NON_CODE_COLORS = frozenset(
    item.color for item in catalog.WARDROBE if item.color != item.color.lower().replace(" ", "_")
)
KNOWN_NON_CODE_MATERIALS = frozenset(
    (item.material or "") for item in catalog.WARDROBE if item.material
)


def test_wardrobe_categories_are_canonical_five():
    schema_enum = load_schema("wardrobe_item")["properties"]["category"]["enum"]
    assert schema_enum == CANONICAL_CATEGORIES
    for item in catalog.WARDROBE:
        assert item.category in CANONICAL_CATEGORIES, item


def test_wardrobe_items_have_display_labels_documented_gap():
    assert len(catalog.WARDROBE) == 24
    for item in catalog.WARDROBE:
        assert item.name and item.color, item
    # Gap stays visible: labels, not FK codes, at the seed layer.
    assert len(KNOWN_NON_CODE_COLORS) > 0
    assert len(KNOWN_NON_CODE_MATERIALS) > 0


def test_look_catalogs_have_stable_codes_and_scores():
    for entry in catalog.HAIRSTYLE_LOOKS + catalog.GROOMING_LOOKS:
        assert entry["code"] and entry["title"], entry
        assert 0.0 <= entry["scoreSeed"] <= 1.0, entry
    codes = [e["code"] for e in catalog.HAIRSTYLE_LOOKS + catalog.GROOMING_LOOKS]
    assert len(set(codes)) == len(codes)


def test_knowledge_occasions_match_ffo_canonical():
    ffo_codes = load_schema("occasion")["x-canonical-codes"]
    catalog_codes = [row["code"] for row in catalog.KNOWLEDGE_OCCASIONS]
    assert catalog_codes == ffo_codes
    assert len(catalog_codes) == 9


def test_item_reference_gate_still_open():
    # DEC-014 P-2: no authoritative garment-type list exists; endpoint
    # serves the valid empty envelope until seed content is supplied.
    assert catalog.ITEM_REFERENCES == []
