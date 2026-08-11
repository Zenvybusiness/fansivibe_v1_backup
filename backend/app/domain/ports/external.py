"""Domain ports — the seams the decision engine depends on.

The engine depends on these abstractions only (BA-3, BA-8); concrete adapters
live in `app/infrastructure`.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.value_objects import HairstyleRecommendation


class KnowledgeSource(Protocol):
    """Reads the hairstyle look catalog (K9.1).

    Implementations: `CatalogKnowledgeSource` (in-code catalog, offline/tests)
    and the DB-backed source in `app/infrastructure/db/repositories.py`.
    """

    def list_hairstyle_looks(self) -> list[HairstyleRecommendation]: ...
