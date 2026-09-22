"""Phase 3C unit tests — Ollama adapter over a fake transport.

No live server: `httpx.MockTransport` serves controlled responses or
raises real httpx errors, so the adapter's mapping is genuinely
exercised. Covers prompt construction, serialization, config, the full
validation pipeline, every failure category, and the retry limit.
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


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_client(payload=None, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"model": "m", "message": {"content": json.dumps(payload or _output())}})

    return _client(handler)


def test_prompt_construction_separates_sections():
    parsed = _input()
    system = build_system_prompt()
    for required in (
        "evidence IDs",
        "insufficient evidence",
        "contradictions",
        "max_conclusions",
        "markdown",
    ):
        assert required in system
    user = build_user_prompt(parsed)
    for marker in ("## A. USER REQUEST", "## B. STRUCTURED CONTEXT",
                   "## C. RETRIEVED EVIDENCE", "## D. OUTPUT CONTRACT"):
        assert marker in user
    assert "term-denim" in user and "max_conclusions: 3" in user


def test_evidence_only_behavior_instructed():
    assert "ONLY from the supplied evidence" in build_system_prompt()


def test_evidence_serialization_compact():
    parsed = _input()
    text = serialize_evidence(parsed.evidence)
    assert "[term-denim]" in text and "denim" in text and "0.9" in text
    assert "term-cotton" not in text  # never the corpus, only supplied evidence
    assert serialize_evidence(()) == "No evidence documents were retrieved."


def test_model_configuration():
    default = ReasoningConfig.from_env()
    assert default.base_url == "http://localhost:11434"
    assert default.model == "llama3.1:8b"
    assert default.temperature == 0.0
    assert default.timeout_s == 60.0
    assert default.max_retries == 1
    assert default.num_predict is None


def test_model_configuration_from_env(monkeypatch):
    monkeypatch.setenv("FANSIVIBE_OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("FANSIVIBE_REASONING_TEMPERATURE", "0.2")
    monkeypatch.setenv("FANSIVIBE_REASONING_TIMEOUT_S", "30")
    monkeypatch.setenv("FANSIVIBE_REASONING_MAX_RETRIES", "0")
    monkeypatch.setenv("FANSIVIBE_REASONING_NUM_PREDICT", "512")
    config = ReasoningConfig.from_env(model="override")
    assert (config.model, config.temperature, config.timeout_s) == ("override", 0.2, 30.0)
    assert (config.max_retries, config.num_predict) == (0, 512)


def test_request_payload_shape():
    seen = []
    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m", temperature=0.0, num_predict=256),
        _ok_client(seen=seen),
    )
    adapter.reason(_input())
    payload = seen[0]
    assert payload["model"] == "m" and payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["options"] == {"temperature": 0.0, "num_predict": 256}
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]


def test_successful_structured_response():
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client())
    assert adapter.contract_version == REASONING_CONTRACT_VERSION
    out = adapter.reason(_input())
    assert out.conclusions[0].standing == "supported"
    assert out.versions.ffo_version == "1.0"


def test_malformed_json():
    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"),
        _client(lambda request: httpx.Response(200, text="not json{{{")),
    )
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "malformed_json"


def test_invalid_evidence_reference():
    bad = _output()
    bad["conclusions"][0]["evidence_ids"] = ["ghost-doc"]
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client(bad))
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "invalid_output"


def test_invalid_ffo_reference():
    bad = _output()
    bad["conclusions"][0]["ffo_refs"] = ["silk-denim"]
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client(bad))
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert "silk-denim" in str(caught.value)


def test_version_mismatch():
    bad = _output()
    bad["versions"] = dict(VERSIONS, ffo_version="9.9")
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client(bad))
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "invalid_output"


def test_max_conclusions_violation():
    one_max = _input(constraints={"evidence_only": True, "max_conclusions": 1})
    bad = _output()
    bad["conclusions"] = [bad["conclusions"][0], dict(bad["conclusions"][0])]
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client(bad))
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(one_max)
    assert caught.value.category == "invalid_output"


def test_output_validation_unknown_standing():
    bad = _output()
    bad["conclusions"][0]["standing"] = "confident"
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"), _ok_client(bad))
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "invalid_output"


def test_timeout_category():
    def handler(request):
        raise httpx.TimeoutException("slow")

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m", max_retries=0), _client(handler)
    )
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "timeout"


def test_connection_failure_category():
    def handler(request):
        raise httpx.ConnectError("down")

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m", max_retries=0), _client(handler)
    )
    with pytest.raises(ReasoningExecutionError) as caught:
        adapter.reason(_input())
    assert caught.value.category == "unavailable"


def test_http_failure_categories():
    for status in (500, 404):
        adapter = OllamaFashionReasoner(
            ReasoningConfig(model="m", max_retries=0),
            _client(lambda request, s=status: httpx.Response(s, json={})),
        )
        with pytest.raises(ReasoningExecutionError) as caught:
            adapter.reason(_input())
        assert caught.value.category == "http_error"


def test_retry_limit():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.TimeoutException("slow")
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m", max_retries=1), _client(handler)
    )
    assert adapter.reason(_input()).answer.startswith("Denim")
    assert len(calls) == 2

    always_down = OllamaFashionReasoner(
        ReasoningConfig(model="m", max_retries=0), _client(handler)
    )
    calls.clear()
    with pytest.raises(ReasoningExecutionError):
        always_down.reason(_input())
    assert len(calls) == 1


def test_adapter_describe_for_eval_metadata():
    describe = OllamaFashionReasoner(ReasoningConfig(model="m")).describe()
    assert describe["provider"] == "ollama" and describe["model"] == "m"
    assert describe["contract_version"] == REASONING_CONTRACT_VERSION
    assert "secret" not in str(describe).lower()
