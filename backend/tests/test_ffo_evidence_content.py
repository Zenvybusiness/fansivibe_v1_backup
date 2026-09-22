"""Phase 3D Part A/C tests — evidence content contract (no Ollama).

Covers: extraction per doc type, content/provenance alignment,
serialization content inclusion without corpus dumps, backward
compatibility, and malformed-content rejection.
"""

from __future__ import annotations

import pytest

from app.ai.reasoning_prompt import build_user_prompt, serialize_evidence
from app.application.reasoning import build_case_input
from app.data.ffo import corpus
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_retrieval import retrieve


def _by_id(doc_id):
    return corpus.build_index(corpus.load_documents())["by_id"][doc_id]


def test_content_extraction_term():
    content = corpus.evidence_content(_by_id("term-denim"))
    assert content["doc_id"] == "term-denim"
    assert content["entity_kind"] == "textile"
    assert content["canonical_id"] == "denim"
    assert content["payload"]["typical_use"] == "jeans, jackets"


def test_content_extraction_alias():
    content = corpus.evidence_content(_by_id("alias-baggy-jeans"))
    assert content == {
        "doc_id": "alias-baggy-jeans",
        "alias": "baggy jeans",
        "canonical_id": "wide_leg_jeans",
        "entity_kind": "garment",
    }


def test_content_extraction_relationship():
    content = corpus.evidence_content(_by_id("rel-denim-made-from-cotton"))
    assert content == {
        "doc_id": "rel-denim-made-from-cotton",
        "rel_type": "MADE_FROM",
        "subject": "denim",
        "object": "cotton",
    }


def test_content_extraction_rule():
    content = corpus.evidence_content(_by_id("rule-fitted-wide-balanced"))
    assert content["payload"]["effect"] == "balanced_volume"
    assert content["payload"]["when"] == {"bottom": "wide", "top": "fitted"}


def test_content_provenance_alignment():
    docs = {d["doc_id"]: d for d in corpus.load_documents()}
    for doc_id in (
        "term-denim", "alias-baggy-jeans",
        "rel-denim-made-from-cotton", "rule-fitted-wide-balanced",
    ):
        before = dict(docs[doc_id])
        content = corpus.evidence_content(docs[doc_id])
        assert content["doc_id"] == doc_id  # belonging traceable
        assert docs[doc_id] == before  # extraction never mutates the source
    with pytest.raises(corpus.CorpusError):
        corpus.evidence_content({"doc_id": "x", "doc_type": "term"})


def test_serialization_includes_content():
    pack = retrieve("denim")
    evidence = []
    by_id = corpus.build_index(corpus.load_documents())["by_id"]
    for item in pack.items:
        record = ReasoningEvidence.from_retrieval(item).to_dict()
        record["content"] = corpus.evidence_content(by_id[item.doc_id])
        evidence.append(ReasoningEvidence(**record))
    text = serialize_evidence(evidence)
    assert "knowledge: durability=high" in text  # term payload content
    assert "denim MADE_FROM cotton" in text  # relationship content


def test_serialization_no_unrelated_dump():
    pack = retrieve("denim")
    by_id = corpus.build_index(corpus.load_documents())["by_id"]
    evidence = []
    for item in pack.items:
        record = ReasoningEvidence.from_retrieval(item).to_dict()
        record["content"] = corpus.evidence_content(by_id[item.doc_id])
        evidence.append(ReasoningEvidence(**record))
    text = serialize_evidence(evidence)
    assert "term-silk" not in text and "burgundy" not in text
    assert ".json" not in text and "knowledge/documents" not in text


def test_backward_compatibility():
    legacy = {
        "doc_id": "term-denim",
        "doc_type": "term",
        "label": "denim",
        "reason": "exact_canonical",
        "lexical_score": 700,
        "semantic_score": None,
        "ffo_references": ["denim"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
        "confidence": 0.9,
        "status": "published",
    }
    parsed = ReasoningEvidence(**legacy)
    assert parsed.content == {}
    assert parsed.to_dict()["content"] == {}
    data = {
        "request": {"query": "q", "intent": "explain"},
        "evidence": [legacy],
        "versions": {
            "ffo_version": "1.0",
            "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
            "evidence_schema": "evidence-pack/1",
            "reasoning_contract_version": REASONING_CONTRACT_VERSION,
        },
    }
    assert validate_input(data).evidence[0].content == {}


def test_malformed_content_handling():
    from app.domain.services.ffo_reasoning import ReasoningContractError

    base = {
        "doc_id": "term-denim",
        "doc_type": "term",
        "label": "denim",
        "reason": "exact_canonical",
        "lexical_score": 700,
        "semantic_score": None,
        "ffo_references": ["denim"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
        "confidence": 0.9,
        "status": "published",
    }

    def _input_with(content):
        return {
            "request": {"query": "q", "intent": "explain"},
            "evidence": [dict(base, content=content)],
            "versions": {
                "ffo_version": "1.0",
                "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
                "evidence_schema": "evidence-pack/1",
                "reasoning_contract_version": REASONING_CONTRACT_VERSION,
            },
        }

    with pytest.raises(ReasoningContractError, match="'content' must be an object"):
        validate_input(_input_with("denim is great"))
    with pytest.raises(ReasoningContractError, match="does not belong"):
        validate_input(_input_with({"doc_id": "term-cotton"}))
    assert validate_input(
        _input_with({"doc_id": "term-denim", "payload": {"name": "denim"}})
    ).evidence[0].content["doc_id"] == "term-denim"


def test_case_input_attaches_content():
    from app.domain.services.ffo_benchmark import load_benchmark

    case = next(
        c for c in load_benchmark()["cases"] if c["case_id"] == "exp-denim-textile"
    )
    built = build_case_input(case)
    assert built["evidence"], "expected retrieved evidence"
    for item in built["evidence"]:
        assert item["content"]["doc_id"] == item["doc_id"]
    prompt = build_user_prompt(validate_input(built))
    assert "knowledge:" in prompt
