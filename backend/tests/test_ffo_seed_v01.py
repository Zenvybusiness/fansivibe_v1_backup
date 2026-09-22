"""FFO Seed v0.1 verification — the curated foundation dataset as a whole.

File-backed only: no database, no user data, no prod behavior change.
Verifies the 8 required properties: full load, universal validity, FFO
reference resolution, ID uniqueness, alias resolution, relationship
resolution, provenance presence, and deterministic ordering.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.data.ffo import corpus, list_schemas
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

DOCUMENTS_DIR = Path(corpus.__file__).resolve().parent / "knowledge" / "documents"

EXPECTED_TOTAL = 76
EXPECTED_BY_TYPE = {"term": 54, "alias": 10, "relationship": 9, "rule": 3}

# Relationship subjects/objects that name external history concepts rather
# than corpus terms (free strings by design; documented here, not invented
# as terms because no history entity schema exists — see the v0.1 gap log).
EXTERNAL_CONCEPTS = frozenset({"grunge", "hip-hop", "modernism"})


def _docs() -> list[dict]:
    return corpus.load_documents(DOCUMENTS_DIR)


def test_complete_seed_loads_with_expected_counts():
    docs = _docs()
    assert len(docs) == EXPECTED_TOTAL
    by_type: dict[str, int] = {}
    for doc in docs:
        by_type[doc["doc_type"]] = by_type.get(doc["doc_type"], 0) + 1
    assert by_type == EXPECTED_BY_TYPE


def test_every_document_validates():
    for doc in _docs():
        assert corpus.validate_document(doc) == [], doc.get("doc_id")
    corpus.build_index(_docs())  # duplicates/collisions raise


def test_every_ffo_reference_resolves():
    schemas = set(list_schemas())
    rel_types = set(
        json.loads(
            (
                Path(corpus.__file__).resolve().parent
                / "knowledge"
                / "relationships"
                / "relationship_types.json"
            ).read_text(encoding="utf-8")
        )["relationships"]
    )
    for doc in _docs():
        if doc["doc_type"] == "term":
            assert doc["entity_kind"] in schemas, doc["doc_id"]
        elif doc.get("entity_kind") is not None:
            assert doc["entity_kind"] in schemas, doc["doc_id"]
        if doc["doc_type"] == "relationship":
            assert doc["rel_type"] in rel_types, doc["doc_id"]


def test_ids_unique():
    docs = _docs()
    assert len({doc["doc_id"] for doc in docs}) == len(docs)


def test_aliases_resolve():
    index = corpus.build_index(_docs())
    term_canonicals = {
        doc["canonical_id"] for doc in _docs() if doc["doc_type"] == "term"
    }
    assert len(index["aliases"]) == EXPECTED_BY_TYPE["alias"]
    for alias, target in index["aliases"].items():
        assert target in term_canonicals, alias


def test_relationships_resolve():
    index = corpus.build_index(_docs())
    term_canonicals = {
        doc["canonical_id"] for doc in _docs() if doc["doc_type"] == "term"
    }
    rels = [doc for doc in _docs() if doc["doc_type"] == "relationship"]
    assert len(rels) == EXPECTED_BY_TYPE["relationship"]
    for doc in rels:
        assert doc["subject"] and doc["object"], doc["doc_id"]
        for endpoint in (doc["subject"], doc["object"]):
            assert endpoint in term_canonicals or endpoint in EXTERNAL_CONCEPTS, (
                doc["doc_id"],
                endpoint,
            )
    _ = index


def test_provenance_present():
    for doc in _docs():
        provenance = doc["provenance"]
        assert provenance["source"], doc["doc_id"]
        assert provenance["source_type"] in corpus.SOURCE_TYPES, doc["doc_id"]
        assert 0.0 <= float(provenance["confidence"]) <= 1.0, doc["doc_id"]


def test_deterministic_ordering_preserved():
    first = [doc["doc_id"] for doc in _docs()]
    second = [doc["doc_id"] for doc in corpus.load_documents(DOCUMENTS_DIR)]
    assert first == second  # sorted filenames in, same order every load
    served = CatalogKnowledgeSource().retrieve_corpus_documents()
    assert [doc["doc_id"] for doc in served] == sorted(first)
    assert len(served) == EXPECTED_TOTAL
