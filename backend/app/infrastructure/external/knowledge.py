"""Knowledge source adapters.

`CatalogKnowledgeSource` serves the hairstyle look catalog from the in-code
catalog (`app/data/catalog.py`) — deterministic, offline-safe, and the
test/unit source. The running API uses the DB-backed adapter in
`app/infrastructure/db/repositories.py` (same `KnowledgeSource` contract).
"""

from __future__ import annotations

from app.data import catalog
from app.domain.ports.external import KnowledgeSource
from app.domain.value_objects import HairstyleRecommendation


class CatalogKnowledgeSource:
    """`KnowledgeSource` backed by `catalog.HAIRSTYLE_LOOKS`."""

    def list_hairstyle_looks(self) -> list[HairstyleRecommendation]:
        return [
            HairstyleRecommendation(
                id=look["code"],
                name=look["title"],
                description=look["description"],
                matchScore=float(look["scoreSeed"]),
                reasons=list(look["reasons"]),
                stylingTips=look["stylingTips"],
                maintenance=look["maintenance"],
                bestFor=look["bestFor"],
            )
            for look in catalog.HAIRSTYLE_LOOKS
        ]


def build_knowledge_source() -> KnowledgeSource:
    """Default adapter factory for the application layer."""
    return CatalogKnowledgeSource()
