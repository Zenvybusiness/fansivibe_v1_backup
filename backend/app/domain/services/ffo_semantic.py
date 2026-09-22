"""Semantic + hybrid retrieval over the FFO corpus (Phase 2D).

Layered on the untouched Phase 2C baseline (`ffo_retrieval`): lexical
matching is never weakened — hybrid ranks lexical hits first in lexical
order, then semantic-only hits by similarity. Cosine scores are raw
geometric measures, NOT calibrated probabilities.

- `SemanticIndex`: in-memory `{doc_id: vector}` stamped with model id +
  version, FFO version, and per-doc versions. Replaceable later by a
  vector-DB adapter behind the same function shapes.
- Mixing guards (loud, never silent): ragged provider dims → ValueError
  at build; index/provider model mismatch → ValueError; stale index
  ( caller passes both documents and an index whose versions differ) →
  ValueError.
- Graceful degradation (skip, never crash): empty vectors, zero-norm
  vectors, per-entry dim mismatch, missing entries, provider
  `EmbeddingError` → lexical-only fallback with `fallback: True`.
- Determinism: same corpus + model/version + query + config → same
  order; ties break by doc_id; cosine rounded to 6 decimals.

Deferred: vector DB, hybrid score fusion, reranking, learned weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from app.data.ffo import FFO_VERSION, corpus
from app.domain.ports.embeddings import EmbeddingError, EmbeddingProvider
from app.domain.services.ffo_retrieval import (
    _passes_filters,
    _text_fields,
    doc_domain,
    doc_label,
    ffo_references,
    retrieve,
)


@dataclass(frozen=True)
class SemanticIndex:
    """In-memory semantic index (76-doc scale; replaceable, not a DB)."""

    model_id: str
    model_version: str
    ffo_version: str
    dim: int
    entries: dict  # doc_id -> {"vector": tuple[float, ...], "doc_version": int}


def doc_text(doc: dict) -> str:
    """Deterministic embeddable text for one document (public seam for providers)."""
    return " ".join(_text_fields(doc))


def build_semantic_index(documents: list, provider: EmbeddingProvider) -> SemanticIndex:
    """Embed validated documents; ragged non-empty dims raise ValueError."""
    texts = [doc_text(doc) for doc in documents]
    try:
        vectors = provider.embed_texts(texts)
    except EmbeddingError:
        raise
    entries: dict[str, dict] = {}
    dim = 0
    for doc, vector in zip(documents, vectors):
        doc_id = doc.get("doc_id")
        version = doc.get("version")
        if not isinstance(doc_id, str) or not isinstance(version, int):
            raise ValueError("semantic index needs validated docs (doc_id, int version)")
        clean = tuple(float(v) for v in (vector or ()))
        if clean:
            if dim == 0:
                dim = len(clean)
            elif len(clean) != dim:
                raise ValueError(
                    f"ragged embedding dims for '{doc_id}': {len(clean)} != {dim}"
                )
        entries[doc_id] = {"vector": clean, "doc_version": version}
    return SemanticIndex(
        model_id=provider.model_id,
        model_version=provider.model_version,
        ffo_version=FFO_VERSION,
        dim=dim,
        entries=entries,
    )


def _cosine(left: tuple, right: list) -> float | None:
    """Cosine similarity, rounded; None when undefined (empty/zero-norm)."""
    if not left or not right or len(left) != len(right):
        return None
    denom = sqrt(sum(a * a for a in left)) * sqrt(sum(b * b for b in right))
    if denom == 0:
        return None
    return round(sum(a * b for a, b in zip(left, right)) / denom, 6)


def semantic_search(
    query: str,
    index: SemanticIndex,
    provider: EmbeddingProvider,
    *,
    min_score: float = 0.0,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Cosine-ranked [(doc_id, score)] desc, doc_id tiebreak.

    Skips empty vectors, zero-norm vectors, and dim mismatches.
    Provider `EmbeddingError` propagates (hybrid converts to fallback).
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("'limit' must be a positive integer")
    query_vector = provider.embed_text(query)
    scored = []
    for doc_id in sorted(index.entries):
        vector = index.entries[doc_id]["vector"]
        score = _cosine(tuple(query_vector or ()), list(vector))
        if score is not None and score > min_score:
            scored.append((doc_id, score))
    scored.sort(key=lambda row: (-row[1], row[0]))
    return scored[:limit] if limit is not None else scored


@dataclass(frozen=True)
class HybridResult:
    """One hybrid candidate with both signals preserved (either may be None)."""

    doc_id: str
    doc_type: str
    label: str
    domain: str
    ffo_references: tuple
    provenance: dict
    confidence: float
    status: str
    matched_terms: tuple
    lexical_score: int | None
    lexical_reason: str | None
    semantic_score: float | None
    semantic_reason: str | None

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "label": self.label,
            "domain": self.domain,
            "ffo_references": list(self.ffo_references),
            "provenance": dict(self.provenance),
            "confidence": self.confidence,
            "status": self.status,
            "matched_terms": list(self.matched_terms),
            "lexical_score": self.lexical_score,
            "lexical_reason": self.lexical_reason,
            "semantic_score": self.semantic_score,
            "semantic_reason": self.semantic_reason,
        }


@dataclass(frozen=True)
class HybridPack:
    """Hybrid candidate set: lexical hits first, then semantic-only."""

    query: str
    filters: dict
    items: tuple
    metadata: dict
    corpus: dict
    semantic: dict

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "filters": dict(self.filters),
            "items": [item.to_dict() for item in self.items],
            "metadata": dict(self.metadata),
            "corpus": {
                "ffo_version": self.corpus["ffo_version"],
                "document_count": self.corpus["document_count"],
                "versions": dict(self.corpus["versions"]),
            },
            "semantic": dict(self.semantic),
        }


def hybrid_retrieve(
    query: str,
    *,
    provider: EmbeddingProvider | None = None,
    index: SemanticIndex | None = None,
    doc_type: str | None = None,
    domain: str | None = None,
    entity: str | None = None,
    language: str | None = None,
    region: str | None = None,
    limit: int | None = None,
    min_semantic_score: float = 0.0,
    documents: list | None = None,
) -> HybridPack:
    """Lexical (Phase 2C, untouched) + semantic candidate union.

    `provider=None` (or provider failure) → lexical-only with
    `fallback: True`. Prebuilt `index` must match the provider's model;
    passing both `documents` and a version-stale index raises.
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("'limit' must be a positive integer")
    docs = documents if documents is not None else corpus.load_documents()
    corpus.build_index(docs)  # validated input only; raises otherwise
    by_id = {doc["doc_id"]: doc for doc in docs}

    pack = retrieve(
        query,
        doc_type=doc_type,
        domain=domain,
        entity=entity,
        language=language,
        region=region,
        documents=docs,
    )
    lex_ids = [item.doc_id for item in pack.items]
    lex_by_id = {item.doc_id: item for item in pack.items}

    semantic_hits: list[tuple[str, float]] = []
    fallback = provider is None
    model_id = model_version = None
    if provider is not None and query.strip():
        try:
            model_id, model_version = provider.model_id, provider.model_version
            if index is None:
                index = build_semantic_index(docs, provider)
            else:
                if (
                    index.model_id != provider.model_id
                    or index.model_version != provider.model_version
                ):
                    raise ValueError(
                        "semantic index model "
                        f"'{index.model_id}/{index.model_version}' != provider "
                        f"'{provider.model_id}/{provider.model_version}'"
                    )
                if documents is not None and {
                    d["doc_id"]: d["version"] for d in docs
                } != {k: v["doc_version"] for k, v in index.entries.items()}:
                    raise ValueError("semantic index is stale for these documents")
            semantic_hits = [
                (doc_id, score)
                for doc_id, score in semantic_search(
                    query, index, provider, min_score=min_semantic_score
                )
                if _passes_filters(
                    by_id[doc_id],
                    doc_type=doc_type,
                    domain=domain,
                    entity=entity,
                    language=language,
                    region=region,
                )
            ]
        except EmbeddingError:
            fallback, semantic_hits = True, []
            model_id, model_version = provider.model_id, provider.model_version
    elif provider is not None:
        model_id, model_version = provider.model_id, provider.model_version

    sem_by_id = dict(semantic_hits)
    ordered_ids = list(lex_ids) + [d for d, _ in semantic_hits if d not in lex_by_id]
    if limit is not None:
        ordered_ids = ordered_ids[:limit]

    def _hybrid(doc_id: str) -> HybridResult:
        doc = by_id[doc_id]
        lex = lex_by_id.get(doc_id)
        sim = sem_by_id.get(doc_id)
        return HybridResult(
            doc_id=doc_id,
            doc_type=doc["doc_type"],
            label=doc_label(doc),
            domain=doc_domain(doc),
            ffo_references=tuple(ffo_references(doc)),
            provenance=dict(doc["provenance"]),
            confidence=float(doc["provenance"]["confidence"]),
            status=doc["status"],
            matched_terms=lex.matched_terms if lex else (),
            lexical_score=lex.score if lex else None,
            lexical_reason=lex.reason if lex else None,
            semantic_score=sim,
            semantic_reason=f"cosine_similarity {sim:.4f}" if sim is not None else None,
        )

    items = tuple(_hybrid(doc_id) for doc_id in ordered_ids)
    versions = {d["doc_id"]: d["version"] for d in docs}
    return HybridPack(
        query=query,
        filters={
            "doc_type": doc_type,
            "domain": domain,
            "entity": entity,
            "language": language,
            "region": region,
        },
        items=items,
        metadata={
            "returned": len(items),
            "lexical_hits": len(lex_ids),
            "semantic_hits": len(semantic_hits),
            "fallback": fallback,
            "limit": limit,
        },
        corpus={
            "ffo_version": FFO_VERSION,
            "document_count": len(docs),
            "versions": versions,
        },
        semantic={"model_id": model_id, "model_version": model_version, "fallback": fallback},
    )


__all__ = [
    "HybridPack",
    "HybridResult",
    "SemanticIndex",
    "build_semantic_index",
    "doc_text",
    "hybrid_retrieve",
    "semantic_search",
]
