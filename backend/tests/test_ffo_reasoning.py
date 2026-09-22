"""Phase 3A tests — reasoning contracts, grounding semantics, versions.

No model calls, no prompts. Fixtures use the real Seed v0.1 corpus and
Phase 2C/2D evidence structures; every output is validated against its
input (evidence ids, max conclusions, version pins).
"""

from __future__ import annotations

import json

import pytest

from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    SUPPORTED_INTENTS,
    ReasoningContractError,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
    validate_output,
)
from app.domain.services.ffo_retrieval import retrieve
from app.domain.services.ffo_semantic import hybrid_retrieve

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}


def _evidence():
    pack = hybrid_retrieve("denim", provider=None)
    return [ReasoningEvidence.from_hybrid(item) for item in pack.items]


def _input_dict(**overrides):
    data = {
        "request": {"query": "what pairs with dark denim jeans?", "intent": "match"},
        "context": {"occasion": "casual"},
        "entities": ["dark-denim-jeans"],
        "evidence": [e.to_dict() for e in _evidence()],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def _output_dict(**overrides):
    data = {
        "answer": "Denim is a durable textile used for jeans and jackets.",
        "conclusions": [
            {
                "statement": "Denim is a durable textile used for jeans and jackets.",
                "evidence_ids": ["term-denim"],
                "ffo_refs": ["denim", "textile"],
                "reasoning_note": "Textile term, published status.",
                "standing": "supported",
            }
        ],
        "uncertainties": [],
        "missing_evidence": [],
        "contradictions": [],
        "confidence": "high",
        "unsupported": False,
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def test_valid_reasoning_input():
    parsed = validate_input(_input_dict())
    body = parsed.to_dict()
    assert set(body) == {
        "request", "context", "entities", "evidence",
        "constraints", "requirements", "versions",
    }
    assert body["request"]["intent"] == "match"
    assert len(body["evidence"]) == len(_evidence()) > 0


def test_invalid_reasoning_input():
    bad_query = _input_dict()
    bad_query["request"] = {"query": "  ", "intent": "match"}
    with pytest.raises(ReasoningContractError, match="'query'"):
        validate_input(bad_query)
    bad_intent = _input_dict()
    bad_intent["request"] = {"query": "q", "intent": "stylez"}
    with pytest.raises(ReasoningContractError, match="must be one of"):
        validate_input(bad_intent)
    bad_versions = _input_dict()
    del bad_versions["versions"]
    with pytest.raises(ReasoningContractError, match="versions"):
        validate_input(bad_versions)
    bad_max = _input_dict()
    bad_max["constraints"] = {"max_conclusions": 0}
    with pytest.raises(ReasoningContractError, match="max_conclusions"):
        validate_input(bad_max)


@pytest.mark.parametrize("intent", list(SUPPORTED_INTENTS))
def test_each_supported_intent(intent):
    data = _input_dict()
    data["request"] = {"query": "q", "intent": intent}
    assert validate_input(data).request.intent == intent


def test_deferred_recommend_intent_rejected():
    data = _input_dict()
    data["request"] = {"query": "q", "intent": "recommend"}
    with pytest.raises(ReasoningContractError, match="deferred"):
        validate_input(data)


def test_context_validation():
    data = _input_dict()
    data["context"] = {
        "occasion": "casual",
        "climate": "tropical",
        "region": "South Asia",
        "style_preference": "minimalist",
        "wardrobe_refs": ["65fd6999-b55c-4d27-98dc-0fcc7c770c18"],
        "budget": "mid-range",
        "fit_preference": "relaxed",
    }
    parsed = validate_input(data)
    assert parsed.context.wardrobe_refs == ("65fd6999-b55c-4d27-98dc-0fcc7c770c18",)
    bad = _input_dict()
    bad["context"] = {"budget": 42}
    with pytest.raises(ReasoningContractError, match="'budget'"):
        validate_input(bad)
    assert validate_input(_input_dict(context=None)).context.occasion is None


def test_evidence_preservation():
    pack = hybrid_retrieve("denim", provider=None)
    kept = [ReasoningEvidence.from_hybrid(item) for item in pack.items]
    assert [e.doc_id for e in kept] == [i.doc_id for i in pack.items]
    assert kept[0].provenance == pack.items[0].provenance
    assert kept[0].lexical_score == pack.items[0].lexical_score
    lex = retrieve("denim").items[0]
    assert ReasoningEvidence.from_retrieval(lex).semantic_score is None
    assert ReasoningEvidence.from_retrieval(lex).doc_id == lex.doc_id


def test_evidence_reference_validation():
    parsed = validate_input(_input_dict())
    unknown = _output_dict()
    unknown["conclusions"][0]["evidence_ids"] = ["ghost-doc"]
    with pytest.raises(ReasoningContractError, match="unknown evidence ids"):
        validate_output(unknown, input=parsed)
    dup = _output_dict()
    dup["conclusions"][0]["evidence_ids"] = ["term-denim", "term-denim"]
    with pytest.raises(ReasoningContractError, match="duplicate"):
        validate_output(dup, input=parsed)
    empty = _output_dict()
    empty["conclusions"][0]["evidence_ids"] = []
    with pytest.raises(ReasoningContractError, match="non-empty"):
        validate_output(empty, input=parsed)


def test_supported_conclusion():
    parsed = validate_input(_input_dict())
    out = validate_output(_output_dict(), input=parsed)
    assert out.conclusions[0].standing == "supported"
    assert out.confidence == "high"


def test_insufficient_evidence():
    parsed = validate_input(_input_dict())
    ok = _output_dict(
        answer="Insufficient evidence: no pairing edge found.",
        conclusions=[],
        missing_evidence=["pairing relationship for linen"],
        confidence="low",
    )
    assert validate_output(ok, input=parsed).missing_evidence == (
        "pairing relationship for linen",
    )
    bad = _output_dict(answer="Dunno.", conclusions=[], confidence="low")
    with pytest.raises(ReasoningContractError, match="missing_evidence"):
        validate_output(bad, input=parsed)


def test_conflicting_evidence():
    parsed = validate_input(_input_dict())
    contested = _output_dict()
    contested["conclusions"][0]["standing"] = "contested"
    contested["contradictions"] = ["reviewed pairing vs draft volume rule"]
    assert validate_output(contested, input=parsed).contradictions
    bare = _output_dict()
    bare["conclusions"][0]["standing"] = "contested"
    with pytest.raises(ReasoningContractError, match="contradictions"):
        validate_output(bare, input=parsed)


def test_uncertainty():
    parsed = validate_input(_input_dict())
    data = _output_dict(confidence="unknown")
    data["conclusions"][0]["standing"] = "uncertain"
    data["uncertainties"] = ["single reviewed source"]
    out = validate_output(data, input=parsed)
    assert out.conclusions[0].standing == "uncertain"
    for bad_conf in ("0.9", 42, "certain"):
        with pytest.raises(ReasoningContractError, match="'confidence'"):
            validate_output(_output_dict(confidence=bad_conf), input=parsed)


def test_unsupported_request():
    parsed = validate_input(_input_dict())
    ok = _output_dict(
        answer="Price comparison is outside this contract.",
        conclusions=[],
        uncertainties=["no product data in scope"],
        missing_evidence=["product catalog"],
        confidence="unknown",
        unsupported=True,
    )
    assert validate_output(ok, input=parsed).unsupported is True
    bad = _output_dict(unsupported=True)
    with pytest.raises(ReasoningContractError, match="forbids conclusions"):
        validate_output(bad, input=parsed)


def test_provenance_preservation():
    parsed = validate_input(_input_dict())
    by_id = {e.doc_id: e for e in parsed.evidence}
    out = validate_output(_output_dict(), input=parsed)
    for conclusion in out.conclusions:
        for doc_id in conclusion.evidence_ids:
            assert doc_id in by_id  # every citation traces to input evidence
            assert by_id[doc_id].provenance["source"]  # provenance travels verbatim


def test_version_preservation():
    parsed = validate_input(_input_dict())
    out = validate_output(_output_dict(), input=parsed)
    assert out.versions.to_dict() == parsed.versions.to_dict()
    tampered = _output_dict()
    tampered["versions"] = dict(VERSIONS, ffo_version="9.9")
    with pytest.raises(ReasoningContractError, match="version pins"):
        validate_output(tampered, input=parsed)
    bad_contract = _input_dict()
    bad_contract["versions"] = dict(VERSIONS, reasoning_contract_version="9.9")
    with pytest.raises(ReasoningContractError, match="contract"):
        validate_input(bad_contract)


def test_deterministic_serialization():
    first = validate_input(_input_dict()).to_dict()
    second = validate_input(_input_dict()).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert validate_input(json.loads(json.dumps(first))).to_dict() == first
    parsed = validate_input(_input_dict())
    out = validate_output(_output_dict(), input=parsed)
    assert validate_output(json.loads(json.dumps(out.to_dict())), input=parsed) == out
