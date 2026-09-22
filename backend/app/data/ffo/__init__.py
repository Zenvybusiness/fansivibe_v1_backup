"""Fansivibe Fashion Intelligence Ontology (FFO) v1.0 — file-backed foundation.

K9.1 versioned backend config: additive only, no production behavior change,
no migrations. Reuses existing canonical codes (migration 0005, DEC-014)
instead of duplicating them. Stdlib only.

Layout:
  schemas/*.schema.json — 26 FFO Phase 1 schemas + the Phase 2A
  knowledge-document envelope (all registered in SCHEMA_NAMES, so the
  /ffo index always equals the files on disk — no special cases)
  knowledge/{taxonomy,relationships,aliases,rules,sources,evaluation}/
"""

from __future__ import annotations

import json
from pathlib import Path

FFO_VERSION = "1.0"

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

# ponytail: flat file list instead of a registry class; add dynamic
# discovery (SCHEMA_DIR.glob) only when a consumer needs it.
SCHEMA_NAMES = [
    "garment",
    "footwear",
    "accessory",
    "jewelry",
    "bag",
    "hair",
    "grooming",
    "makeup",
    "color",
    "material",
    "textile",
    "pattern",
    "silhouette",
    "fit",
    "aesthetic",
    "occasion",
    "climate",
    "culture",
    "designer",
    "brand",
    "trend",
    "trend_signal",
    "product",
    "wardrobe_item",
    "outfit",
    "user_style",
    "knowledge_document",
]


def load_schema(name: str) -> dict:
    """Load one FFO JSON Schema by short name (stdlib only)."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def list_schemas() -> list[str]:
    """Return the 26 canonical FFO schema names."""
    return list(SCHEMA_NAMES)
