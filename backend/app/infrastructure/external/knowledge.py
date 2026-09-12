"""Knowledge source adapters.

`CatalogKnowledgeSource` serves the hairstyle and grooming look catalogs from
the in-code catalog (`app/data/catalog.py`) — deterministic, offline-safe, and
the approved knowledge seed (K9.1). It implements the `KnowledgeSource` port
with the two KN-10 access paths:

- ``lookup_hairstyle_look`` — exact keyed reads (validation, references).
- ``retrieve_hairstyle_looks`` — filtered/derived reads for the Decision
  Engine's candidate generation; deprecated entries are filtered, never
  served (KN-3), validated before they reach the engine.
- ``lookup_grooming_look`` — exact keyed reads for grooming looks.
- ``retrieve_grooming_looks`` — filtered/derived reads for the Decision
  Engine's candidate generation; deprecated entries are filtered, never
  served (KN-3), validated before they reach the engine.

The catalog content version (`knowledge_version`) is served alongside so
consumers can version-cite knowledge without touching user data (KN-7/KN-9).
"""

from __future__ import annotations

from typing import Optional

from app.data import catalog
from app.domain.ports.external import KnowledgeError, KnowledgeSource
from app.domain.value_objects import HairstyleRecommendation


# Fields a valid hairstyle look entry must carry (mirrors the wire DTO and
# the `looks` table payload contract).
_REQUIRED_TEXT_FIELDS = ("title", "description", "stylingTips", "maintenance", "bestFor")

# Fields a valid grooming look entry must carry (mirrors the wire DTO and
# the `looks` table payload contract for grooming).
_GREQUIRED_TEXT_FIELDS = ("title", "description", "stylingTips", "maintenance", "bestFor")


def _validate_occasion(entry: dict) -> dict:
    """Validate one `#21` occasion entry; raise `KnowledgeError` when malformed.

    Shape-only validation (DEC-014 freezes the 9 rows in `catalog.py`;
    this never invents codes — it only refuses to serve malformed rows).
    """
    code = entry.get("code")
    if not isinstance(code, str) or not code.strip():
        raise KnowledgeError("knowledge occasion entry has no stable code")
    label = entry.get("label")
    if not isinstance(label, str) or not label.strip():
        raise KnowledgeError(f"knowledge occasion '{code}' has invalid 'label'")
    order = entry.get("sortOrder")
    if isinstance(order, bool) or not isinstance(order, int) or order < 1:
        raise KnowledgeError(f"knowledge occasion '{code}' has invalid 'sortOrder'")
    return entry


def _validate_item_reference(entry: dict) -> dict:
    """Validate one `#22` item-reference entry; raise `KnowledgeError` if malformed.

    Frozen DEC-014 shape `{code, label, category, sortOrder}` — system-owned
    reference codes only (no user_id, price, vendor, stock, media, UUID).
    """
    code = entry.get("code")
    if not isinstance(code, str) or not code.strip():
        raise KnowledgeError("knowledge item entry has no stable code")
    label = entry.get("label")
    if not isinstance(label, str) or not label.strip():
        raise KnowledgeError(f"knowledge item '{code}' has invalid 'label'")
    category = entry.get("category")
    if not isinstance(category, str) or not category.strip():
        raise KnowledgeError(f"knowledge item '{code}' has invalid 'category'")
    order = entry.get("sortOrder")
    if isinstance(order, bool) or not isinstance(order, int) or order < 1:
        raise KnowledgeError(f"knowledge item '{code}' has invalid 'sortOrder'")
    return entry


def _validate_entry(entry: dict) -> dict:
    """Validate one catalog entry; raise `KnowledgeError` when malformed.

    Read-time validation (KNOWLEDGE_ARCHITECTURE §3.3): a look that fails
    validation is never served — the engine must not see fabricated rows.
    """
    code = entry.get("code")
    if not isinstance(code, str) or not code.strip():
        raise KnowledgeError("knowledge look entry has no stable code")

    for field in _REQUIRED_TEXT_FIELDS:
        if not isinstance(entry.get(field), str) or not entry.get(field).strip():
            raise KnowledgeError(f"knowledge look '{code}' has invalid '{field}'")

    reasons = entry.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        raise KnowledgeError(f"knowledge look '{code}' has empty 'reasons'")

    score = entry.get("scoreSeed")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise KnowledgeError(f"knowledge look '{code}' has invalid 'scoreSeed'")
    if not (0.0 <= float(score) <= 1.0):
        raise KnowledgeError(f"knowledge look '{code}' has out-of-range 'scoreSeed'")

    return entry


def _validate_grooming_entry(entry: dict) -> dict:
    """Validate one grooming catalog entry; raise `KnowledgeError` when malformed.

    Read-time validation (KNOWLEDGE_ARCHITECTURE §3.3): a look that fails
    validation is never served — the engine must not see fabricated rows.
    """
    code = entry.get("code")
    if not isinstance(code, str) or not code.strip():
        raise KnowledgeError("knowledge grooming entry has no stable code")

    for field in _GREQUIRED_TEXT_FIELDS:
        if not isinstance(entry.get(field), str) or not entry.get(field).strip():
            raise KnowledgeError(f"knowledge grooming look '{code}' has invalid '{field}'")

    reasons = entry.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        raise KnowledgeError(f"knowledge grooming look '{code}' has empty 'reasons'")

    score = entry.get("scoreSeed")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise KnowledgeError(f"knowledge grooming look '{code}' has invalid 'scoreSeed'")
    if not (0.0 <= float(score) <= 1.0):
        raise KnowledgeError(f"knowledge grooming look '{code}' has out-of-range 'scoreSeed'")

    return entry


def _to_recommendation(entry: dict) -> HairstyleRecommendation:
    return HairstyleRecommendation(
        id=entry["code"],
        name=entry["title"],
        description=entry["description"],
        matchScore=float(entry["scoreSeed"]),
        reasons=list(entry["reasons"]),
        stylingTips=entry["stylingTips"],
        maintenance=entry["maintenance"],
        bestFor=entry["bestFor"],
    )


def _to_grooming_recommendation(entry: dict) -> "GroomingRecommendation":
    """Convert a validated grooming catalog entry to a wire DTO."""
    from app.domain.value_objects import GroomingRecommendation  # noqa: F811

    return GroomingRecommendation(
        id=entry["code"],
        name=entry["title"],
        description=entry["description"],
        matchScore=float(entry["scoreSeed"]),
        reasons=list(entry["reasons"]),
        stylingTips=entry["stylingTips"],
        maintenance=entry["maintenance"],
        bestFor=entry["bestFor"],
        icon=None,
    )


def _is_deprecated(entry: dict) -> bool:
    return bool(entry.get("deprecated", False))


class CatalogKnowledgeSource:
    """`KnowledgeSource` backed by `catalog.HAIRSTYLE_LOOKS` and
    `catalog.GROOMING_LOOKS`.

    Deterministic test/unit source and the approved knowledge seed. The
    running API also uses it (no user data — catalog only, KN-2/KN-9). A
    DB-backed implementation of the same port can replace it without
    touching consumers.
    """

    knowledge_version: str = catalog.KNOWLEDGE_VERSION

    def lookup_hairstyle_look(self, code: str) -> Optional[HairstyleRecommendation]:
        for entry in catalog.HAIRSTYLE_LOOKS:
            entry = _validate_entry(entry)
            if entry["code"] == code:
                return _to_recommendation(entry)
        return None

    def retrieve_hairstyle_looks(self) -> list[HairstyleRecommendation]:
        return [
            _to_recommendation(entry)
            for entry in catalog.HAIRSTYLE_LOOKS
            if not _is_deprecated(_validate_entry(entry))
        ]

    def lookup_grooming_look(self, code: str) -> Optional["GroomingRecommendation"]:
        """Exact keyed read for a grooming look by its stable code."""
        for entry in catalog.GROOMING_LOOKS:
            entry = _validate_grooming_entry(entry)
            if entry["code"] == code:
                return _to_grooming_recommendation(entry)
        return None

    def retrieve_grooming_looks(self) -> list["GroomingRecommendation"]:
        """Filtered/derived reads for the Decision Engine's candidate generation.

        Deprecated entries are filtered, never served (KN-3), validated before
        they reach the engine.
        """
        return [
            _to_grooming_recommendation(entry)
            for entry in catalog.GROOMING_LOOKS
            if not _is_deprecated(_validate_grooming_entry(entry))
        ]

    def retrieve_occasions(self) -> list[dict]:
        """Ordered `#21` occasion rows from the frozen K9.1 config (DEC-014 P-1).

        Served verbatim in config order (deterministic `sortOrder` 1..9);
        malformed rows raise instead of serving invented vocabulary.
        """
        return [_validate_occasion(dict(entry)) for entry in catalog.KNOWLEDGE_OCCASIONS]

    def retrieve_item_references(self) -> list[dict]:
        """Ordered `#22` item-reference rows from the K9.1 config (DEC-014 P-2).

        Currently content-gated (empty): the architecture serves the catalog
        once authoritative content is supplied; nothing is invented here.
        """
        return [_validate_item_reference(dict(entry)) for entry in catalog.ITEM_REFERENCES]


def build_knowledge_source() -> KnowledgeSource:
    """Default adapter factory for the application layer."""
    return CatalogKnowledgeSource()