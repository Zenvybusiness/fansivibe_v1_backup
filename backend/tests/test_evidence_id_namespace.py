"""Phase 3F-A focused tests — bracket-reserved evidence-ID namespace.

No Ollama: serialization asserted directly (including over the full
76-doc corpus); adapter rejection runs over `httpx.MockTransport`.
Validator semantics unchanged — these tests pin that ONLY supplied IDs
are referenceable and that labels/content/refs can never become IDs.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest

from app.ai.ollama_reasoner import (
    OllamaFashionReasoner,
    ReasoningConfig,
    ReasoningExecutionError,
)
from app.ai.reasoning_prompt import build_user_prompt, serialize_evidence
from app.data.ffo import corpus
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_retrieval import retrieve

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}

EVIDENCE = {
    "doc_id": "term-denim",
    "doc_type": "term",
    "label": "denim",
    "reason": "exact_canonical",
    "lexical_score": 700,
    "semantic_score": None,
    "ffo_references": ["denim", "textile"],
    "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
    "confidence": 0.9,
    "status": "published",
    "content": {
        "doc_id": "term-denim",
        "entity_kind": "textile",
        "canonical_id": "denim",
        "payload": {"durability": "high", "name": "denim"},
    },
}


def _input(**overrides):
    data = {
        "request": {"query": "what is denim", "intent": "explain"},
        "context": {},
        "entities": ["denim"],
        "evidence": [dict(EVIDENCE)],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return validate_input(data)


def _output(**overrides):
    data = {
        "answer": "Denim is a durable textile.",
        "conclusions": [
            {
                "statement": "Denim is a durable textile.",
                "evidence_ids": ["term-denim"],
                "ffo_refs": ["denim"],
                "reasoning_note": "n",
                "standing": "supported",
                "admission": {
                    "subject_ref": "denim",
                    "atomic_claims": [
                        {"text": "Denim is a durable textile.",
                         "cited_doc_ids": ["term-denim"]}
                    ],
                },
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


def _reason(payload, reasoning_input=None):
    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(payload)}}
        )

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return adapter.reason(reasoning_input or _input())


def _full_corpus_evidence():
    docs = corpus.load_documents()
    by_id = corpus.build_index(docs)["by_id"]
    pack = retrieve("", documents=docs)  # blank query: unscored, all pass filters
    out = []
    for item in pack.items:
        record = ReasoningEvidence.from_retrieval(item).to_dict()
        record["content"] = corpus.evidence_content(by_id[item.doc_id])
        out.append(ReasoningEvidence(**record))
    return out


# --- rendering ---


def test_inventory_lists_exactly_supplied_ids():
    text = serialize_evidence(_input().evidence)
    assert text.startswith("Valid evidence IDs:\n[term-denim]")
    assert "ID: [term-denim]" in text


def test_brackets_reserved_for_ids_over_full_corpus():
    evidence = _full_corpus_evidence()
    assert len(evidence) == 76
    text = serialize_evidence(evidence)
    supplied = {e.doc_id for e in evidence}
    for token in re.findall(r"\[([^\]]*)\]", text):
        assert token in supplied, f"non-ID bracketed token: [{token}]"


def test_all_prior_information_preserved():
    text = serialize_evidence(_input().evidence)
    for kept in (
        "term", "denim", "textile", "0.9", "exact_canonical",
        "lexical 700", "published", "knowledge: durability=high",
    ):
        assert kept in text


# --- rejection (validator unchanged, still authoritative) ---


def test_valid_id_reference_passes():
    assert _reason(_output()).conclusions[0].evidence_ids == ("term-denim",)


def test_label_cannot_become_id():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["denim"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_ffo_ref_cannot_become_id():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["textile"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_content_cannot_become_id():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["durability=high, name=denim"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_unknown_id_rejected():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["term-silk"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_empty_and_non_string_ids_rejected():
    for ids in ([], [["term-denim"]]):
        bad = _output()
        bad["conclusions"][0]["evidence_ids"] = ids
        with pytest.raises(ReasoningExecutionError) as caught:
            _reason(bad)
        assert caught.value.category == "invalid_output"


def test_user_prompt_carries_inventory():
    assert "Valid evidence IDs:" in build_user_prompt(_input())
