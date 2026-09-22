"""Embedding provider port — Phase 2D semantic retrieval seam.

The domain depends only on this interface (Protocol); no Ollama, no
vendor SDK, no network code may enter the domain layer. Concrete
providers (local model, API, test fakes) live outside `domain/` and are
injected by callers.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingError(Exception):
    """A provider failed to embed (unavailable model, bad input, timeout).

    Plain :class:`Exception` (not ValueError): provider failure is an
    infrastructure event, not a content problem. Semantic callers treat it
    as "no semantic signal" and fall back to lexical — never a crash.
    """


class EmbeddingProvider(Protocol):
    """Minimal embedding contract for semantic retrieval.

    - ``model_id`` / ``model_version`` identify the weights; indexes are
      stamped with both and never mixed across models/versions.
    - ``embed_text`` embeds one string; ``embed_texts`` batches (default
      loops over ``embed_text`` — override where the backend batches
      natively). Both raise :class:`EmbeddingError` on provider failure.
    - Vectors SHOULD be L2-normalized by the provider; retrieval uses
      cosine similarity either way (deterministic, no calibration claim).
    """

    model_id: str
    model_version: str

    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed; default loops (override for native batching)."""
        return [self.embed_text(text) for text in texts]
