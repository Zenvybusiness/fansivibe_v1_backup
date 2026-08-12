"""Domain ports — the seams the decision engine depends on.

The engine depends on these abstractions only (BA-3, BA-8); concrete adapters
live in `app/infrastructure`.
"""

from __future__ import annotations

from typing import Optional, Protocol

from app.domain.value_objects import HairstyleRecommendation


class KnowledgeError(ValueError):
    """Raised when knowledge is missing or fails validation on read.

    Subclasses :class:`ValueError` so existing callers that treat a failed
    knowledge read as a value problem keep working unchanged. Knowledge
    failures are truthful signals about system-owned content — they never
    carry user data (KN-9).
    """


class KnowledgeSource(Protocol):
    """Reads the hairstyle knowledge catalog (K9.1, KN-10).

    Two access paths per `KNOWLEDGE_ARCHITECTURE.md` §3.5/§3.6:

    - ``lookup`` — exact, keyed reads for reference and validation (e.g. the
      save slice validates a client look id against the known catalog).
    - ``retrieve`` — filtered/derived reads for the Decision Engine's
      candidate generation (deprecated entries never served, KN-3).

    ``knowledge_version`` is the curated content version (KN-1 §5.1),
    distinct from the rules-code ``engine_version``.

    Implementation: `CatalogKnowledgeSource` (in-code catalog, offline-safe,
    the approved knowledge seed). A DB-backed adapter may implement the same
    contract later behind this unmoved port.
    """

    knowledge_version: str

    def lookup_hairstyle_look(self, code: str) -> Optional[HairstyleRecommendation]: ...

    def retrieve_hairstyle_looks(self) -> list[HairstyleRecommendation]: ...
