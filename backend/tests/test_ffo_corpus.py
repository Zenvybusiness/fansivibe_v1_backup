"""FFO knowledge corpus tests — ingestion/provenance foundation (Phase 2A).

File-backed only: no database, no user data, no prod behavior change.
Covers: valid records (all 4 doc types + shipped seed), invalid records,
duplicate entities, missing provenance, invalid FFO references, version
handling, and read-only KnowledgeService integration.
"""

from __future__ import annotations

import json

import pytest

from app.data.ffo import corpus
from app.domain.ports.external import KnowledgeError
from app.infrastructure.external.knowledge import CatalogKnowledgeSource


def _term(**overrides) -> dict:
    doc = {
        "doc_id": "term-wide-leg-jeans",
        "doc_type": "term",
        "entity_kind": "garment",
        "canonical_id": "wide_leg_jeans",
        "payload": {"category": "bottoms", "subcategory": "wide-leg jeans"},
        "status": "published",
        "version": 1,
        "language": "en",
        "provenance": {
            "source": "seed",
            "source_type": "AUTHORITATIVE",
            "confidence": 0.85,
        },
    }
    doc.update(overrides)
    return doc


def _alias(**overrides) -> dict:
    doc = {
        "doc_id": "alias-baggy-jeans",
        "doc_type": "alias",
        "canonical_id": "wide_leg_jeans",
        "alias": "baggy jeans",
        "status": "published",
        "version": 1,
        "language": "en",
        "provenance": {
            "source": "seed",
            "source_type": "AUTHORITATIVE",
            "confidence": 0.8,
        },
    }
    doc.update(overrides)
    return doc


def test_valid_records_all_types():
    relationship = {
        "doc_id": "rel-a",
        "doc_type": "relationship",
        "rel_type": "PAIRS_WITH",
        "subject": "wide_leg_jeans",
        "object": "fitted_top",
        "status": "reviewed",
        "version": 1,
        "language": "en",
        "provenance": {"source": "seed", "source_type": "AUTHORITATIVE", "confidence": 0.7},
    }
    rule = {
        "doc_id": "rule-a",
        "doc_type": "rule",
        "payload": {"when": {"top": "oversized"}, "effect": "high_volume_outfit"},
        "status": "draft",
        "version": 1,
        "language": "en",
        "provenance": {"source": "seed", "source_type": "AUTHORITATIVE", "confidence": 0.6},
    }
    for doc in (_term(), _alias(), relationship, rule):
        assert corpus.validate_document(doc) == []


def test_shipped_seed_loads_and_indexes_clean():
    docs = corpus.load_documents()
    assert 50 <= len(docs) <= 100
    index = corpus.build_index(docs)
    assert len(index["by_id"]) == len(docs)
    assert "term-wide-leg-jeans" in index["by_id"]
    assert "alias-baggy-jeans" in index["by_id"]
    assert index["aliases"]["baggy jeans"] == "wide_leg_jeans"
    assert set(index["versions"].values()) == {1}


def test_invalid_records_rejected():
    cases = [
        (_term(doc_type="entry"), "doc_type"),
        (_term(status="live"), "status"),
        (_term(version=0), "version"),
        (_term(version=True), "version"),
        (_term(language="english"), "language"),
        (_term(published_at="yesterday"), "published_at"),
        (_term(doc_id="BAD ID!"), "doc_id"),
        (_term(payload={"category": "bottoms"}), "required keys"),
        (_alias(alias=""), "alias"),
        (_term(entity_kind="nope"), "entity_kind"),
    ]
    for doc, fragment in cases:
        errors = corpus.validate_document(doc)
        assert errors, doc
        assert any(fragment in error for error in errors), errors


def test_missing_provenance_rejected():
    assert any("provenance" in e for e in corpus.validate_document(_term(provenance=None)))
    no_source = _term()
    del no_source["provenance"]["source"]
    assert any("provenance.source" in e for e in corpus.validate_document(no_source))
    bad_tier = _term()
    bad_tier["provenance"]["source_type"] = "VIRAL"
    assert any("source_type" in e for e in corpus.validate_document(bad_tier))
    bad_conf = _term()
    bad_conf["provenance"]["confidence"] = 1.5
    assert any("confidence" in e for e in corpus.validate_document(bad_conf))


def test_invalid_ffo_references_rejected():
    assert "entity_kind" in "; ".join(corpus.validate_document(_term(entity_kind="nope")))
    orphan = _alias(canonical_id="ghost_jeans")
    with pytest.raises(corpus.CorpusError, match="unknown term"):
        corpus.build_index([_term(), orphan])
    bad_rel = {
        "doc_id": "rel-x",
        "doc_type": "relationship",
        "rel_type": "VIBES_WITH",
        "subject": "a",
        "object": "b",
        "status": "draft",
        "version": 1,
        "language": "en",
        "provenance": {"source": "s", "source_type": "COMMUNITY", "confidence": 0.5},
    }
    assert any("rel_type" in e for e in corpus.validate_document(bad_rel))


def test_duplicate_entities_rejected():
    with pytest.raises(corpus.CorpusError, match="duplicate doc_id"):
        corpus.build_index([_term(), _term()])
    twin = _term(doc_id="term-wide-leg-jeans-2")
    with pytest.raises(corpus.CorpusError, match="canonical collision"):
        corpus.build_index([_term(), twin])
    rival = _alias(doc_id="alias-loose-jeans", alias="baggy jeans", canonical_id="other")
    other_term = _term(doc_id="term-other", canonical_id="other")
    with pytest.raises(corpus.CorpusError, match="alias collision"):
        corpus.build_index([_term(), other_term, _alias(), rival])


def test_multiple_aliases_may_share_one_target():
    index = corpus.build_index(
        [_term(), _alias(), _alias(doc_id="alias-loose-jeans", alias="loose jeans")]
    )
    assert index["aliases"] == {
        "baggy jeans": "wide_leg_jeans",
        "loose jeans": "wide_leg_jeans",
    }


def test_version_handling():
    assert corpus.validate_document(_term(version=2)) == []
    index = corpus.build_index([_term(version=2), _alias()])
    assert corpus.corpus_versions(index)["term-wide-leg-jeans"] == 2
    with pytest.raises(corpus.CorpusError, match="duplicate doc_id"):
        corpus.build_index([_term(version=1), _term(version=2)])


def test_unparsable_file_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(corpus.CorpusError, match="cannot load"):
        corpus.load_documents(tmp_path)


def test_service_integration():
    source = CatalogKnowledgeSource()
    docs = source.retrieve_corpus_documents()
    assert 50 <= len(docs) <= 100
    assert [doc["doc_id"] for doc in docs] == sorted(doc["doc_id"] for doc in docs)
    aliases = source.retrieve_corpus_documents(doc_type="alias")
    assert len(aliases) == len(
        [doc for doc in docs if doc["doc_type"] == "alias"]
    )
    assert all(doc["doc_type"] == "alias" for doc in aliases)
    with pytest.raises(KnowledgeError, match="unknown corpus doc_type"):
        source.retrieve_corpus_documents(doc_type="entry")


def test_service_invalid_seed_raises_knowledge_error(tmp_path, monkeypatch):
    bad = _term(doc_type="entry")
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(corpus, "DOCUMENTS_DIR", tmp_path)
    with pytest.raises(KnowledgeError, match="invalid knowledge corpus"):
        CatalogKnowledgeSource().retrieve_corpus_documents()
