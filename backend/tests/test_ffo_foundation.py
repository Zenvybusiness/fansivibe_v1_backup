"""FFO v1.0 foundation tests — additive file-backed ontology, zero prod impact.

Covers: 26 schemas exist + valid JSON + $id/title/type + x-ffo-version +
extensible additionalProperties; provenance mixin present; canonical reuse
(5 wardrobe categories from 0005, 9 DEC-014 occasions); knowledge skeleton
(6 files) valid; loader works on stdlib only. No database; no user data.
"""

from __future__ import annotations

import json
from pathlib import Path

FFO_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "ffo"
SCHEMA_DIR = FFO_DIR / "schemas"

EXPECTED_SCHEMAS = [
    "garment", "footwear", "accessory", "jewelry", "bag", "hair",
    "grooming", "makeup", "color", "material", "textile", "pattern",
    "silhouette", "fit", "aesthetic", "occasion", "climate", "culture",
    "designer", "brand", "trend", "trend_signal", "product",
    "wardrobe_item", "outfit", "user_style", "knowledge_document",
]

EXPECTED_CATEGORIES = ["tops", "bottoms", "outerwear", "footwear", "accessories"]
EXPECTED_OCCASIONS = [
    "casual", "formal", "business", "date", "party",
    "travel", "workout", "other", "office",
]


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_all_26_schemas_exist_and_parse():
    files = sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))
    assert len(files) == 27, files
    for name in EXPECTED_SCHEMAS:
        data = _load(name)
        assert data["$schema"].startswith("https://json-schema.org/"), name
        assert data["$id"].endswith(f"{name}.schema.json"), name
        assert data["title"], name
        assert data["type"] == "object", name
        assert data["x-ffo-version"] == "1.0", name
        assert data.get("additionalProperties") is True, name


def test_provenance_mixin_present():
    for name in EXPECTED_SCHEMAS:
        data = _load(name)
        prov = data["properties"]["provenance"]
        assert prov["$ref"] == "#/$defs/provenance", name
        fields = data["$defs"]["provenance"]["properties"]
        for field in (
            "confidence", "source", "source_type",
            "created_at", "updated_at", "verified_at",
        ):
            assert field in fields, (name, field)


def test_wardrobe_category_reuses_canonical_five():
    data = _load("wardrobe_item")
    assert data["properties"]["category"]["enum"] == EXPECTED_CATEGORIES
    garment = _load("garment")
    assert garment["properties"]["category"]["enum"] == EXPECTED_CATEGORIES


def test_occasion_reuses_dec014_nine():
    data = _load("occasion")
    assert data["x-canonical-codes"] == EXPECTED_OCCASIONS


def test_color_material_keep_canonical_subset():
    color = _load("color")
    assert len(color["x-canonical-codes"]) == 17
    assert "burgundy" in color["x-canonical-codes"]
    material = _load("material")
    assert len(material["x-canonical-codes"]) == 16
    assert "denim" in material["x-canonical-codes"]


def test_knowledge_skeleton_valid():
    expected = [
        "taxonomy/ffo_domains.json",
        "relationships/relationship_types.json",
        "aliases/canonical_aliases.json",
        "rules/compatibility_heuristics.json",
        "sources/source_classes.json",
        "evaluation/phase1_checklist.json",
    ]
    for rel in expected:
        path = FFO_DIR / "knowledge" / rel
        assert path.exists(), rel
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["x-ffo-version"] == "1.0", rel


def test_loader_uses_stdlib_only():
    src = (FFO_DIR / "__init__.py").read_text(encoding="utf-8")
    for mod in ("fastapi", "sqlalchemy", "pydantic"):
        assert f"import {mod}" not in src, mod
        assert f"from {mod}" not in src, mod
    from app.data.ffo import FFO_VERSION, list_schemas, load_schema
    assert FFO_VERSION == "1.0"
    assert list_schemas() == EXPECTED_SCHEMAS
    assert load_schema("outfit")["title"] == "FFO Outfit"
