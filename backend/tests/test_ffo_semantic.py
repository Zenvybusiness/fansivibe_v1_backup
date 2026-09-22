"""Phase 2D tests — semantic + hybrid retrieval with fake embeddings.

No model downloads, no network, no database, no user data. The fake
provider serves controlled vectors; every ordering assertion is exact.
"""

from __future__ import annotations

import pytest

from app.data.ffo import FFO_VERSION, corpus
from app.domain.ports.embeddings import EmbeddingError
from app.domain.services.ffo_retrieval import retrieve
from app.domain.services.ffo_semantic import (
    build_semantic_index,
    doc_text,
    hybrid_retrieve,
    semantic_search,
)


class FakeProvider:
    """Controlled test double: exact-text vector map, zero default (skipped)."""

    model_id = "fake-test"
    model_version = "v0"

    def __init__(self, vectors=None, fail_on=()):
        self.vectors = dict(vectors or {})
        self.fail_on = set(fail_on)
        self.calls = []

    def embed_text(self, text):
        self.calls.append(text)
        if text in self.fail_on:
            raise EmbeddingError("provider down")
        return list(self.vectors.get(text, [0.0, 0.0, 0.0]))

    def embed_texts(self, texts):
        return [self.embed_text(text) for text in texts]


def _docs():
    return corpus.load_documents()


def _by_id(doc_id):
    return next(d for d in _docs() if d["doc_id"] == doc_id)


def test_embedding_provider_contract():
    provider = FakeProvider(vectors={"hi": [1.0, 0.0, 0.0]})
    assert (provider.model_id, provider.model_version) == ("fake-test", "v0")
    assert provider.embed_text("hi") == [1.0, 0.0, 0.0]
    assert provider.embed_texts(["hi", "yo"]) == [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    assert provider.calls == ["hi", "hi", "yo"]  # default batches via embed_text


def test_embedding_dimension_validation():
    docs = [_by_id("term-denim"), _by_id("term-cotton")]
    provider = FakeProvider(
        vectors={doc_text(docs[0]): [1.0, 0.0, 0.0], doc_text(docs[1]): [1.0, 0.0]}
    )
    with pytest.raises(ValueError, match="ragged embedding dims"):
        build_semantic_index(docs, provider)


def test_semantic_exact_neighbor_retrieval():
    docs = _docs()
    provider = FakeProvider(vectors={doc_text(_by_id("term-denim")): [1.0, 0.0, 0.0]})
    index = build_semantic_index(docs, provider)
    searcher = FakeProvider(vectors={"denim query": [1.0, 0.0, 0.0]})
    assert semantic_search("denim query", index, searcher) == [("term-denim", 1.0)]


def test_semantic_similarity_ordering():
    docs = [_by_id("term-denim"), _by_id("term-cotton"), _by_id("term-silk")]
    provider = FakeProvider(
        vectors={
            doc_text(docs[0]): [1.0, 0.0, 0.0],
            doc_text(docs[1]): [1.0, 1.0, 0.0],
            doc_text(docs[2]): [0.0, 1.0, 0.0],
        }
    )
    index = build_semantic_index(docs, provider)
    searcher = FakeProvider(vectors={"q": [1.0, 0.0, 0.0]})
    assert semantic_search("q", index, searcher) == [
        ("term-denim", 1.0),
        ("term-cotton", 0.707107),
    ]


def test_empty_embedding_handling():
    docs = [_by_id("term-denim")]
    full = FakeProvider(vectors={doc_text(docs[0]): [1.0, 0.0, 0.0]})
    index = build_semantic_index(docs, full)
    assert semantic_search("q", index, FakeProvider()) == []  # empty query vector
    assert semantic_search("q", index, full) == []  # unmapped -> zero default
    empty_index = build_semantic_index(docs, FakeProvider())
    assert semantic_search("q", empty_index, full) == []  # empty entry vector


def test_unavailable_provider_fallback():
    down = FakeProvider(fail_on={"denim"})
    with pytest.raises(EmbeddingError):
        semantic_search("denim", build_semantic_index(_docs(), FakeProvider()), down)
    pack = hybrid_retrieve("denim", provider=FakeProvider(fail_on={"denim"}))
    assert pack.metadata["fallback"] is True
    assert [item.doc_id for item in pack.items] == [
        item.doc_id for item in retrieve("denim").items
    ]
    assert all(item.semantic_score is None for item in pack.items)


def test_embedding_version_metadata():
    index = build_semantic_index(_docs(), FakeProvider())
    assert (index.model_id, index.model_version) == ("fake-test", "v0")
    assert index.ffo_version == FFO_VERSION == "1.0"
    assert index.entries["term-denim"]["doc_version"] == 1
    other = FakeProvider()
    other.model_id = "other-model"
    with pytest.raises(ValueError, match="!= provider"):
        hybrid_retrieve("denim", provider=other, index=index)
    stale = build_semantic_index(_docs(), FakeProvider())
    evolved = [dict(d, version=2) if d["doc_id"] == "term-denim" else d for d in _docs()]
    with pytest.raises(ValueError, match="stale"):
        hybrid_retrieve("denim", provider=FakeProvider(), index=stale, documents=evolved)


def test_corpus_version_metadata():
    pack = hybrid_retrieve("denim", provider=FakeProvider())
    assert pack.corpus["ffo_version"] == "1.0"
    assert pack.corpus["document_count"] == 76
    expected = corpus.corpus_versions(corpus.build_index(_docs()))
    assert pack.corpus["versions"] == expected
    assert pack.to_dict()["corpus"]["versions"] == expected


def test_lexical_only_fallback():
    pack = hybrid_retrieve("denim", provider=None)
    assert pack.metadata["fallback"] is True
    assert pack.semantic == {"model_id": None, "model_version": None, "fallback": True}
    assert [item.doc_id for item in pack.items] == [
        item.doc_id for item in retrieve("denim").items
    ]
    assert all(
        item.semantic_score is None and item.lexical_score is not None
        for item in pack.items
    )


def test_semantic_only_candidate():
    provider = FakeProvider(vectors={doc_text(_by_id("term-denim")): [0.0, 1.0, 0.0]})
    searcher = FakeProvider(vectors={"zzzqqq": [0.0, 1.0, 0.0]})
    index = build_semantic_index(_docs(), provider)
    pack = hybrid_retrieve("zzzqqq", provider=searcher, index=index)
    assert [(item.doc_id, item.semantic_score) for item in pack.items] == [
        ("term-denim", 1.0)
    ]
    only = pack.items[0]
    assert only.lexical_score is None and only.lexical_reason is None
    assert only.matched_terms == ()
    assert only.semantic_reason == "cosine_similarity 1.0000"


def test_hybrid_candidate_union():
    provider = FakeProvider(vectors={doc_text(_by_id("term-silk")): [1.0, 0.0, 0.0]})
    searcher = FakeProvider(vectors={"denim": [1.0, 0.0, 0.0]})
    index = build_semantic_index(_docs(), provider)
    pack = hybrid_retrieve("denim", provider=searcher, index=index)
    ids = [item.doc_id for item in pack.items]
    assert ids[:4] == [item.doc_id for item in retrieve("denim").items]
    assert "term-silk" in ids
    assert pack.metadata["lexical_hits"] == 4
    assert pack.metadata["semantic_hits"] == 1


def test_duplicate_candidate_deduplication():
    provider = FakeProvider(vectors={doc_text(_by_id("term-denim")): [1.0, 0.0, 0.0]})
    searcher = FakeProvider(vectors={"denim": [1.0, 0.0, 0.0]})
    index = build_semantic_index(_docs(), provider)
    pack = hybrid_retrieve("denim", provider=searcher, index=index)
    denim = next(item for item in pack.items if item.doc_id == "term-denim")
    assert pack.items[0].doc_id == "term-denim"
    assert (denim.lexical_score, denim.lexical_reason) == (700, "exact_canonical")
    assert denim.semantic_score == 1.0
    assert [item.doc_id for item in pack.items].count("term-denim") == 1


def test_deterministic_ordering():
    kwargs = {"provider": FakeProvider(), "limit": 5}
    assert hybrid_retrieve("denim", **kwargs).to_dict() == hybrid_retrieve(
        "denim", **kwargs
    ).to_dict()


def test_provenance_preservation():
    doc = _by_id("term-denim")
    pack = hybrid_retrieve("denim", provider=FakeProvider())
    result = next(item for item in pack.items if item.doc_id == "term-denim")
    assert result.provenance == doc["provenance"]
    assert result.confidence == float(doc["provenance"]["confidence"])
    assert result.status == doc["status"]
