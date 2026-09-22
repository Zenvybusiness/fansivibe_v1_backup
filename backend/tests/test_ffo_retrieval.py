"""FFO retrieval V0 tests — deterministic lexical + metadata (Phase 2C).

Domain-level only: no database, no user data, no HTTP, no prod behavior
change. Every ranking test asserts actual order, never mere existence.
"""

from __future__ import annotations

import pytest

from app.data.ffo import FFO_VERSION, corpus
from app.domain.services.ffo_retrieval import retrieve


def test_exact_canonical_term_retrieval():
    pack = retrieve("wide_leg_jeans")
    assert [(item.doc_id, item.score) for item in pack.items[:3]] == [
        ("term-wide-leg-jeans", 700),
        ("alias-baggy-jeans", 600),
        ("alias-loose-jeans", 600),
    ]
    first = pack.items[0]
    assert first.reason == "exact_canonical"
    assert first.matched_terms == ("wide_leg_jeans",)


def test_alias_retrieval():
    pack = retrieve("baggy jeans")
    first = pack.items[0]
    assert first.doc_id == "alias-baggy-jeans"
    assert (first.score, first.reason) == (600, "exact_alias")
    assert [item.doc_id for item in pack.items] == [
        "alias-baggy-jeans",
        "alias-loose-jeans",
        "term-dark-denim-jeans",
        "term-denim",
        "term-wide-leg-jeans",
    ]


def test_partial_token_retrieval():
    pack = retrieve("cotton denim")
    assert [item.doc_id for item in pack.items] == [
        "term-cotton",
        "term-dark-denim-jeans",
        "term-denim",
        "term-oxford-shirt",
        "term-trench-coat",
        "term-wide-leg-jeans",
    ]
    assert all(item.score == 400 and item.reason == "token" for item in pack.items)


def test_document_type_filtering():
    pack = retrieve("jeans", doc_type="alias")
    assert pack.items, "expected alias hits"
    assert all(item.doc_type == "alias" for item in pack.items)
    assert [item.doc_id for item in pack.items] == ["alias-baggy-jeans", "alias-loose-jeans"]
    with pytest.raises(ValueError, match="unknown doc_type"):
        retrieve("jeans", doc_type="entry")


def test_domain_filtering():
    pack = retrieve("", domain="footwear")
    assert [item.doc_id for item in pack.items] == [
        "alias-chelsea-boot",
        "alias-white-sneaker",
        "term-chelsea-boots",
        "term-loafers",
        "term-white-sneakers",
    ]
    assert all(item.domain == "footwear" for item in pack.items)
    single = retrieve("leather", domain="footwear")
    assert [item.doc_id for item in single.items] == ["term-chelsea-boots"]


def test_ffo_reference_retrieval():
    pack = retrieve("garment")
    assert len(pack.items) == 9
    assert all(item.reason == "ffo_reference" and item.score == 300 for item in pack.items)
    assert pack.items[0].doc_id == "alias-baggy-jeans"
    punk = retrieve("punk")
    assert [(item.doc_id, item.score) for item in punk.items] == [
        ("term-punk", 700),
        ("rel-grunge-influenced-punk", 300),
    ]
    effect = retrieve("balanced_volume")
    assert [item.doc_id for item in effect.items] == ["rule-fitted-wide-balanced"]


def test_language_filtering():
    assert len(retrieve("", language="en").items) == 76
    assert retrieve("", language="fr").items == ()
    assert retrieve("denim", language="en").items[0].doc_id == "term-denim"


def test_region_filtering():
    pack = retrieve("", region="South Asia")
    assert [item.doc_id for item in pack.items] == ["term-indian-fashion"]
    assert retrieve("", region="Atlantis").items == ()


def test_ranking_order():
    pack = retrieve("denim")
    assert [(item.doc_id, item.score) for item in pack.items] == [
        ("term-denim", 700),
        ("term-dark-denim-jeans", 500),
        ("term-wide-leg-jeans", 400),
        ("rel-denim-made-from-cotton", 300),
    ]
    phrase = retrieve("jeans")
    assert [item.doc_id for item in phrase.items] == [
        "alias-baggy-jeans",
        "alias-loose-jeans",
        "term-dark-denim-jeans",
        "term-denim",
        "term-wide-leg-jeans",
    ]
    assert {item.score for item in phrase.items} == {500}


def test_deterministic_tie_breaking():
    first = retrieve("jeans").to_dict()
    second = retrieve("jeans").to_dict()
    assert first == second
    ids = [item["doc_id"] for item in first["items"]]
    assert ids == sorted(ids)


def test_result_limit():
    full = retrieve("jeans")
    assert len(full.items) == 5
    limited = retrieve("jeans", limit=2)
    assert [item.doc_id for item in limited.items] == [
        item.doc_id for item in full.items[:2]
    ]
    assert limited.metadata["limit"] == 2
    for bad in (0, -1, True, "2"):
        with pytest.raises(ValueError, match="'limit'"):
            retrieve("jeans", limit=bad)


def test_empty_query_behavior():
    pack = retrieve("")
    assert len(pack.items) == 76
    assert all(item.score == 0 and item.reason == "unscored" for item in pack.items)
    assert [item.doc_id for item in pack.items] == sorted(item.doc_id for item in pack.items)
    blank = retrieve("   ")
    assert blank.items == pack.items  # blank behaves as empty ...
    assert blank.query == "   "  # ... but the verbatim query is preserved


def test_no_result_behavior():
    pack = retrieve("kimono")
    assert pack.items == ()
    assert pack.metadata == {"returned": 0, "total_candidates": 76, "limit": None}
    saree = retrieve("saree")  # no saree term (v0.1 gap) — culture doc answers
    assert [(item.doc_id, item.score) for item in saree.items] == [
        ("term-indian-fashion", 400)
    ]


def test_provenance_preservation():
    doc = next(
        d for d in corpus.load_documents() if d["doc_id"] == "term-denim"
    )
    result = retrieve("denim").items[0]
    assert result.provenance == doc["provenance"]
    assert result.status == doc["status"]


def test_confidence_preservation():
    pack = retrieve("denim")
    assert pack.items[0].confidence == 0.9
    for item in retrieve("", limit=5).items:
        source = next(
            d for d in corpus.load_documents() if d["doc_id"] == item.doc_id
        )
        assert item.confidence == float(source["provenance"]["confidence"])


def test_evidence_pack_construction():
    pack = retrieve("denim", doc_type="term", limit=3)
    body = pack.to_dict()
    assert body["query"] == "denim"
    assert body["filters"] == {
        "doc_type": "term",
        "domain": None,
        "entity": None,
        "language": None,
        "region": None,
    }
    assert len(body["items"]) == 3
    assert body["metadata"]["returned"] == 3
    assert body["metadata"]["total_candidates"] == 76
    assert body["items"][0]["doc_id"] == "term-denim"


def test_corpus_version_preservation():
    pack = retrieve("denim")
    assert pack.corpus["ffo_version"] == FFO_VERSION == "1.0"
    assert pack.corpus["document_count"] == 76
    expected = corpus.corpus_versions(corpus.build_index(corpus.load_documents()))
    assert pack.corpus["versions"] == expected
    assert pack.to_dict()["corpus"]["versions"] == expected
