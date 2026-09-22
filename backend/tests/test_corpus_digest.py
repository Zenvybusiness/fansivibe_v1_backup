"""Phase 3F-B focused tests — corpus digest contract 2.0.

No Ollama. Pins the single authoritative `corpus_digest` function
(determinism, key-order independence, FFO binding), the new versions
shape (old `corpus_versions` map rejected, never converted; full-hex
enforced; contract pinned to 2.0), and the unchanged evidence_schema.
"""

from __future__ import annotations

import pytest

from app.domain.services.ffo_reasoning import (
    EVIDENCE_SCHEMA_VERSION,
    REASONING_CONTRACT_VERSION,
    ReasoningContractError,
    corpus_digest,
    validate_input,
    validate_output,
)


def _versions(**overrides):
    data = {
        "ffo_version": "1.0",
        "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
        "evidence_schema": EVIDENCE_SCHEMA_VERSION,
        "reasoning_contract_version": REASONING_CONTRACT_VERSION,
    }
    data.update(overrides)
    return data


def _input(**overrides):
    data = {
        "request": {"query": "q", "intent": "explain"},
        "evidence": [],
        "versions": _versions(),
    }
    data.update(overrides)
    return data


def test_contract_is_2_0_and_schema_unchanged():
    assert REASONING_CONTRACT_VERSION == "2.0"
    assert EVIDENCE_SCHEMA_VERSION == "evidence-pack/1"


def test_digest_deterministic_and_order_independent():
    left = corpus_digest({"b": 2, "a": 1}, "1.0")
    assert left == corpus_digest({"a": 1, "b": 2}, "1.0") == corpus_digest({"b": 2, "a": 1}, "1.0")
    assert len(left) == 64 and all(c in "0123456789abcdef" for c in left)


def test_digest_bound_to_ffo_and_versions():
    base = corpus_digest({"a": 1}, "1.0")
    assert corpus_digest({"a": 1}, "2.0") != base
    assert corpus_digest({"a": 2}, "1.0") != base
    assert corpus_digest({"a": 1, "b": 1}, "1.0") != base


def test_digest_rejects_bad_shapes():
    for bad_versions, bad_ffo in (
        ({"a": 0}, "1.0"), ({"a": True}, "1.0"), ({"a": "1"}, "1.0"),
        ("not-a-dict", "1.0"), ({"a": 1}, ""),
    ):
        with pytest.raises(ReasoningContractError):
            corpus_digest(bad_versions, bad_ffo)


def test_old_corpus_versions_map_rejected_never_converted():
    data = _input()
    data["versions"] = {
        "ffo_version": "1.0",
        "corpus_versions": {"term-denim": 1},
        "evidence_schema": EVIDENCE_SCHEMA_VERSION,
        "reasoning_contract_version": "2.0",
    }
    with pytest.raises(ReasoningContractError, match="removed in contract 2.0"):
        validate_input(data)


def test_digest_hex_and_contract_enforced():
    for field, value in (
        ("corpus_digest", "xyz"),
        ("corpus_digest", "ab" * 16 + "XY"),
        ("corpus_digest", corpus_digest({"a": 1}, "1.0")[:32]),
        ("reasoning_contract_version", "1.0"),
        ("evidence_schema", ""),
    ):
        with pytest.raises(ReasoningContractError):
            validate_input(_input(versions=_versions(**{field: value})))


def test_digest_round_trip_input_output():
    parsed = validate_input(_input())
    output = {
        "answer": "ok",
        "conclusions": [],
        "uncertainties": [],
        "missing_evidence": ["x"],
        "contradictions": [],
        "confidence": "low",
        "unsupported": False,
        "versions": _versions(),
    }
    assert validate_output(output, input=parsed).versions.corpus_digest == parsed.versions.corpus_digest
    tampered = dict(output)
    tampered["versions"] = _versions(
        corpus_digest=corpus_digest({"other": 1}, "1.0")
    )
    with pytest.raises(ReasoningContractError, match="version pins"):
        validate_output(tampered, input=parsed)
