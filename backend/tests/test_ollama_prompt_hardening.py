"""Phase 3E focused tests — prompt ID-fidelity rules + strict rejection.

No Ollama: prompt text is asserted directly; adapter behavior runs over
`httpx.MockTransport`. Validation semantics are unchanged (3A contract
is authoritative) — these tests pin the hardened instructions and the
rejections the 3D baseline showed were needed.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.ollama_reasoner import (
    OllamaFashionReasoner,
    ReasoningConfig,
    ReasoningExecutionError,
)
from app.ai.reasoning_prompt import (
    build_system_prompt,
    build_user_prompt,
    serialize_evidence,
)
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    corpus_digest,
    validate_input,
)

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


def _client(payload):
    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(payload)}}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _reason(payload, reasoning_input=None):
    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"), _client(payload)
    )
    return adapter.reason(reasoning_input or _input())


# --- prompt rules (Task B pins) ---


def test_system_prompt_id_fidelity_rules():
    system = build_system_prompt()
    assert "ONLY" in system and "one JSON object" in system
    assert "square-bracketed IDs" in system
    assert "never use knowledge text" in system
    assert "all four keys" in system


def test_user_prompt_evidence_id_and_versions_rules():
    user = build_user_prompt(_input())
    assert "never use the knowledge text as an ID" in user
    assert "all four keys, unchanged" in user
    assert "never knowledge text" in user


def test_term_knowledge_line_single_prefix():
    text = serialize_evidence(_input().evidence)
    assert "knowledge: durability=high" in text
    assert "knowledge: knowledge:" not in text  # the 3D confusion source


# --- strict validation preserved (Task C) ---


def test_valid_evidence_ids_with_content_pass():
    out = _reason(_output())
    assert out.conclusions[0].evidence_ids == ("term-denim",)


def test_knowledge_text_as_evidence_id_rejected():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = [
        "knowledge: durability=high, name=denim"
    ]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_unknown_evidence_id_rejected():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["alias-wide_leg_jeans"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_duplicate_evidence_ids_rejected():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["term-denim", "term-denim"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_evidence_schema_preserved_exactly():
    bad = _output()
    bad["versions"] = dict(VERSIONS, evidence_schema="")
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"
    assert _reason(_output()).versions.evidence_schema == "evidence-pack/1"


def test_max_conclusions_enforced():
    one_max = _input(constraints={"evidence_only": True, "max_conclusions": 1})
    bad = _output()
    bad["conclusions"] = [bad["conclusions"][0], dict(bad["conclusions"][0])]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad, one_max)
    assert caught.value.category == "invalid_output"


def test_malformed_json_remains_transport_failure():
    def handler(request):
        return httpx.Response(200, text="not json{{{")

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "malformed_json"
