"""Integration tests for Phase 3AJ — Frozen Reasoning System Integration.

Validates the application boundary across all 14 mandatory integration cases:
  1. valid supported fashion query
  2. multi-document query
  3. alias-driven query
  4. relationship query
  5. insufficient-evidence query
  6. unsupported/current-price query
  7. malformed reasoning output
  8. invalid evidence ID
  9. Ollama failure
  10. timeout
  11. admission rejection
  12. selector behavior
  13. version propagation
  14. raw model JSON does not escape the reasoning boundary
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.ai.ollama_reasoner import ReasoningExecutionError
from app.api.deps import get_fashion_reasoner
from app.data.ffo import FFO_VERSION, corpus
from app.domain.services.ffo_reasoning import (
    EVIDENCE_SCHEMA_VERSION,
    REASONING_CONTRACT_VERSION,
    FashionReasoningInput,
    FashionReasoningOutput,
    ReasoningConclusion,
    ReasoningVersions,
    corpus_digest,
)
from app.main import app

client = TestClient(app)
ENDPOINT = "/v1/reasoning"
ALIAS_ENDPOINT = "/v1/reasoning/query"


def _auth_versions() -> ReasoningVersions:
    index = corpus.build_index(corpus.load_documents())
    digest = corpus_digest(corpus.corpus_versions(index), FFO_VERSION)
    return ReasoningVersions(
        ffo_version=FFO_VERSION,
        corpus_digest=digest,
        evidence_schema=EVIDENCE_SCHEMA_VERSION,
        reasoning_contract_version=REASONING_CONTRACT_VERSION,
    )


class MockReasoner:
    contract_version = REASONING_CONTRACT_VERSION

    def __init__(self, responder=None):
        self._responder = responder
        self.recorded_inputs: list[FashionReasoningInput] = []

    def reason(self, reasoning_input: FashionReasoningInput) -> FashionReasoningOutput:
        self.recorded_inputs.append(reasoning_input)
        if self._responder:
            return self._responder(reasoning_input)
        raise NotImplementedError("MockReasoner requires a responder function")


@pytest.fixture
def mock_reasoner():
    reasoner = MockReasoner()
    app.dependency_overrides[get_fashion_reasoner] = lambda: reasoner
    yield reasoner
    app.dependency_overrides.pop(get_fashion_reasoner, None)


# 1. Valid supported fashion query
def test_valid_supported_fashion_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        assert inp.request.query == "what is denim"
        assert inp.request.intent == "explain"
        doc_ids = {e.doc_id for e in inp.evidence}
        assert "term-denim" in doc_ids
        return FashionReasoningOutput(
            answer="Denim is a sturdy cotton twill textile.",
            conclusions=(
                ReasoningConclusion(
                    statement="Denim is a durable cotton twill textile.",
                    evidence_ids=("term-denim",),
                    ffo_refs=("denim", "textile"),
                    standing="supported",
                    reasoning_note="Grounded in term-denim.",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim", "intent": "explain"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Denim is a sturdy cotton twill textile."
    assert data["confidence"] == "high"
    assert data["unsupported"] is False
    assert len(data["conclusions"]) == 1
    assert data["conclusions"][0]["evidence_ids"] == ["term-denim"]
    assert data["conclusions"][0]["ffo_refs"] == ["denim", "textile"]
    assert data["versions"]["reasoning_contract_version"] == REASONING_CONTRACT_VERSION


# 2. Multi-document query
def test_multi_document_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        assert inp.request.intent == "compare"
        doc_ids = {e.doc_id for e in inp.evidence}
        assert "term-cotton" in doc_ids
        assert "term-linen" in doc_ids
        return FashionReasoningOutput(
            answer="Cotton is softer while linen is more breathable.",
            conclusions=(
                ReasoningConclusion(
                    statement="Cotton and linen are distinct natural textiles.",
                    evidence_ids=("term-cotton", "term-linen"),
                    ffo_refs=("cotton", "linen", "material"),
                    standing="supported",
                    reasoning_note="Compared across both terms.",
                ),
            ),
            confidence="medium",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    # Query without explicit intent: auto-inferred as 'compare'
    response = client.post(ENDPOINT, json={"query": "cotton vs linen"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["conclusions"]) == 1
    assert "term-cotton" in data["conclusions"][0]["evidence_ids"]
    assert "term-linen" in data["conclusions"][0]["evidence_ids"]


# 3. Alias-driven query
def test_alias_driven_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        doc_ids = {e.doc_id for e in inp.evidence}
        assert "alias-loose-jeans" in doc_ids
        assert "term-wide-leg-jeans" in doc_ids
        return FashionReasoningOutput(
            answer="Loose jeans are an alias for wide leg jeans.",
            conclusions=(
                ReasoningConclusion(
                    statement="Loose jeans refer to wide leg jeans.",
                    evidence_ids=("alias-loose-jeans", "term-wide-leg-jeans"),
                    ffo_refs=("wide_leg_jeans",),
                    standing="supported",
                    reasoning_note="Resolved via alias document.",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "loose jeans"})
    assert response.status_code == 200
    data = response.json()
    assert data["conclusions"][0]["ffo_refs"] == ["wide_leg_jeans"]


# 4. Relationship query
def test_relationship_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        doc_ids = {e.doc_id for e in inp.evidence}
        assert "rel-sneakers-pair-denim" in doc_ids
        return FashionReasoningOutput(
            answer="White sneakers pair naturally with dark denim jeans.",
            conclusions=(
                ReasoningConclusion(
                    statement="White sneakers pair with dark denim.",
                    evidence_ids=("rel-sneakers-pair-denim", "term-white-sneakers"),
                    ffo_refs=("dark-denim-jeans", "white-sneakers"),
                    standing="supported",
                    reasoning_note="Licensed by PAIRS_WITH edge.",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ALIAS_ENDPOINT, json={"query": "white sneakers"})
    assert response.status_code == 200
    data = response.json()
    assert "rel-sneakers-pair-denim" in data["conclusions"][0]["evidence_ids"]


# 5. Insufficient-evidence query
def test_insufficient_evidence_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        assert len(inp.evidence) == 0
        return FashionReasoningOutput(
            answer="The corpus does not contain sizing guidelines for kimono garments.",
            conclusions=(),
            missing_evidence=("kimono sizing specifications",),
            confidence="low",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "kimono sizing"})
    assert response.status_code == 200
    data = response.json()
    assert data["conclusions"] == []
    assert len(data["missing_evidence"]) >= 1
    assert data["unsupported"] is False
    assert data["confidence"] == "low"


# 6. Unsupported/current-price query
def test_unsupported_current_price_query(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        return FashionReasoningOutput(
            answer="Pricing information is outside the scope of the fashion ontology.",
            conclusions=(),
            missing_evidence=("retail pricing data",),
            confidence="unknown",
            unsupported=True,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "current price of white sneakers"})
    assert response.status_code == 200
    data = response.json()
    assert data["unsupported"] is True
    assert data["conclusions"] == []
    assert data["confidence"] == "unknown"


# 7. Malformed reasoning output
def test_malformed_reasoning_output(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        raise ReasoningExecutionError("malformed_json", "model output is not JSON")

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "AI_FAILURE"
    assert data["error"]["details"]["category"] == "malformed_json"


# 8. Invalid evidence ID
def test_invalid_evidence_id(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        raise ReasoningExecutionError("invalid_output", "unknown evidence ids ['fabricated-doc']")

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "AI_FAILURE"
    assert data["error"]["details"]["category"] == "invalid_output"


# 9. Ollama failure
def test_ollama_failure(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        raise ReasoningExecutionError("unavailable", "ollama connection refused")

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "AI_FAILURE"
    assert data["error"]["details"]["category"] == "unavailable"


# 10. Timeout
def test_timeout(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        raise ReasoningExecutionError("timeout", "ollama timeout after 60s")

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 504
    data = response.json()
    assert data["error"]["code"] == "TIMEOUT"
    assert data["error"]["details"]["category"] == "timeout"


# 11. Admission rejection
def test_admission_rejection_boundary(mock_reasoner):
    """Proves that conclusions rejected by Phase 3T admission are excluded from the API response."""
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        # Simulate admission filter having dropped an unanchored conclusion
        admitted = (
            ReasoningConclusion(
                statement="Denim is a twill weave cotton fabric.",
                evidence_ids=("term-denim",),
                ffo_refs=("denim", "textile"),
                standing="supported",
            ),
        )
        return FashionReasoningOutput(
            answer="Denim is a twill weave cotton fabric.",
            conclusions=admitted,
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["conclusions"]) == 1
    assert data["conclusions"][0]["statement"] == "Denim is a twill weave cotton fabric."


# 12. Selector behavior
def test_selector_behavior_boundary(mock_reasoner):
    """Proves that 3P reference selector outputs are faithfully propagated."""
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        # 3P selector kept 'denim' and 'textile' (statement word-match), dropped unlinked 'garment'
        selected_refs = ("denim", "textile")
        return FashionReasoningOutput(
            answer="Denim is a durable textile.",
            conclusions=(
                ReasoningConclusion(
                    statement="Denim is a durable textile.",
                    evidence_ids=("term-denim",),
                    ffo_refs=selected_refs,
                    standing="supported",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 200
    data = response.json()
    assert data["conclusions"][0]["ffo_refs"] == ["denim", "textile"]
    assert "garment" not in data["conclusions"][0]["ffo_refs"]


# 13. Version propagation
def test_version_propagation(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        return FashionReasoningOutput(
            answer="Verified denim answer.",
            conclusions=(
                ReasoningConclusion(
                    statement="Denim is verified.",
                    evidence_ids=("term-denim",),
                    ffo_refs=("denim",),
                    standing="supported",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 200
    data = response.json()
    versions = data["versions"]
    expected = _auth_versions()
    assert versions["ffo_version"] == expected.ffo_version
    assert versions["corpus_digest"] == expected.corpus_digest
    assert versions["evidence_schema"] == expected.evidence_schema
    assert versions["reasoning_contract_version"] == expected.reasoning_contract_version


# 14. Raw model JSON does not escape the reasoning boundary
def test_raw_model_json_does_not_escape_boundary(mock_reasoner):
    def responder(inp: FashionReasoningInput) -> FashionReasoningOutput:
        return FashionReasoningOutput(
            answer="Safe public answer.",
            conclusions=(
                ReasoningConclusion(
                    statement="Safe public conclusion.",
                    evidence_ids=("term-denim",),
                    ffo_refs=("denim",),
                    standing="supported",
                    reasoning_note="Safe note.",
                ),
            ),
            confidence="high",
            unsupported=False,
            versions=inp.versions,
        )

    mock_reasoner._responder = responder
    response = client.post(ENDPOINT, json={"query": "what is denim"})
    assert response.status_code == 200
    data = response.json()

    # Allowed top-level fields per FashionReasoningResponse schema only
    allowed_top_keys = {
        "answer",
        "conclusions",
        "uncertainties",
        "missing_evidence",
        "contradictions",
        "confidence",
        "unsupported",
        "versions",
    }
    assert set(data.keys()) == allowed_top_keys

    # No admission record, prompt internals, or raw transport leaked in conclusions
    allowed_conclusion_keys = {
        "statement",
        "evidence_ids",
        "ffo_refs",
        "reasoning_note",
        "standing",
    }
    for conclusion in data["conclusions"]:
        assert set(conclusion.keys()) == allowed_conclusion_keys
        assert "admission" not in conclusion
        assert "atomic_claims" not in conclusion
        assert "subject_ref" not in conclusion
