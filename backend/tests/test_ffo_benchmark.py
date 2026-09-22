"""Phase 3B tests — benchmark schema, grounding, metrics, versions.

No model calls. Cases load from the shipped benchmark file; metric
behavior is asserted with handcrafted outputs; retrieval alignment runs
against the real Seed v0.1 corpus.
"""

from __future__ import annotations

import json

import pytest

from app.data.ffo import corpus
from app.domain.services.ffo_benchmark import (
    BENCHMARK_VERSION,
    GROUNDINGS,
    METRIC_NAMES,
    BenchmarkError,
    derive_status,
    evaluate,
    load_benchmark,
    validate_case,
)
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    SUPPORTED_INTENTS,
    corpus_digest,
)
from app.domain.services.ffo_retrieval import retrieve

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}


def _bench():
    return load_benchmark()


def _by_id(case_id):
    return next(c for c in _bench()["cases"] if c["case_id"] == case_id)


def _input(intent="explain"):
    return {"request": {"query": "q", "intent": intent}, "versions": dict(VERSIONS)}


def _output(conclusions=(), **overrides):
    data = {
        "answer": "a",
        "conclusions": list(conclusions),
        "uncertainties": [],
        "missing_evidence": [],
        "contradictions": [],
        "confidence": "high",
        "unsupported": False,
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def _conclusion(ids=("term-denim",), refs=("denim",), standing="supported"):
    return {
        "statement": "s",
        "evidence_ids": list(ids),
        "ffo_refs": list(refs),
        "reasoning_note": "n",
        "standing": standing,
    }


def test_benchmark_loads_with_size_and_order():
    bench = _bench()
    assert bench["benchmark_version"] == BENCHMARK_VERSION == "1.0"
    assert bench["ffo_version"] == "1.0"
    assert 20 <= len(bench["cases"]) <= 30
    ids = [c["case_id"] for c in bench["cases"]]
    assert ids == sorted(ids)


def test_benchmark_schema_validation():
    with pytest.raises(BenchmarkError, match="duplicate case_id"):
        _dup_check()
    bad = dict(_by_id("exp-denim-textile"))
    del bad["query"]
    with pytest.raises(BenchmarkError, match="'query'"):
        validate_case(bad)
    bad_intent = dict(_by_id("exp-denim-textile"), expected_intent="recommend")
    with pytest.raises(BenchmarkError, match="supported"):
        validate_case(bad_intent)


def _dup_check():
    bench = _bench()
    dup = dict(bench["cases"][0])
    data = {"benchmark_version": "1.0", "ffo_version": "1.0", "cases": [bench["cases"][0], dup]}
    import tempfile, os

    handle, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
            json.dump(data, handle_file)
        from app.domain.services.ffo_benchmark import load_benchmark as loader

        loader(path)
    finally:
        os.remove(path)


def test_version_validation():
    import tempfile, os

    handle, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
            json.dump({"benchmark_version": "9.9", "ffo_version": "1.0", "cases": []}, handle_file)
        from app.domain.services.ffo_benchmark import load_benchmark as loader

        with pytest.raises(BenchmarkError, match="benchmark version"):
            loader(path)
    finally:
        os.remove(path)


def _reference_universe():
    universe = set()
    for doc in corpus.load_documents():
        for key in ("canonical_id", "alias", "entity_kind", "subject", "object", "rel_type"):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                universe.add(value)
        payload = doc.get("payload")
        if isinstance(payload, dict):
            if isinstance(payload.get("effect"), str):
                universe.add(payload["effect"])
            when = payload.get("when")
            if isinstance(when, dict):
                universe.update(v for v in when.values() if isinstance(v, str))
    return universe


def test_expected_evidence_references():
    docs = {d["doc_id"] for d in corpus.load_documents()}
    for case in _bench()["cases"]:
        for doc_id in case["expected_evidence_ids"]:
            assert doc_id in docs, (case["case_id"], doc_id)


def test_expected_ffo_references():
    universe = _reference_universe()
    for case in _bench()["cases"]:
        for ref in case["expected_ffo_refs"]:
            assert ref in universe, (case["case_id"], ref)


def test_expected_evidence_retrievable():
    for case in _bench()["cases"]:
        if not case["expected_evidence_ids"] or case["expected_grounding"] in (
            "insufficient", "unsupported",
        ):
            continue
        pack = retrieve(case["query"], **case.get("retrieval_filters", {}))
        retrieved = {item.doc_id for item in pack.items}
        for doc_id in case["expected_evidence_ids"]:
            assert doc_id in retrieved, (case["case_id"], doc_id)


def test_every_supported_intent():
    intents = {c["expected_intent"] for c in _bench()["cases"]}
    assert intents == set(SUPPORTED_INTENTS)
    assert "recommend" not in intents


def test_grounding_statuses():
    statuses = {c["expected_grounding"] for c in _bench()["cases"]}
    assert statuses == set(GROUNDINGS)


def test_unsupported_cases():
    unsupported = [c for c in _bench()["cases"] if c["expected_grounding"] == "unsupported"]
    assert unsupported
    for case in unsupported:
        assert case["requires_missing_evidence"]


def test_contradiction_cases():
    contested = [c for c in _bench()["cases"] if c["expected_grounding"] == "contested"]
    assert contested
    assert all(c["requires_contradictions"] for c in contested)


def test_metric_calculations():
    case = _by_id("exp-denim-textile")
    perfect = _output(conclusions=[_conclusion()])
    result = evaluate(case, _input("explain"), perfect)
    assert result.passed
    assert all(m["pass"] for m in result.metrics.values())

    wrong_intent = evaluate(case, _input("match"), perfect)
    assert wrong_intent.metrics["intent_accuracy"]["pass"] is False
    assert wrong_intent.passed is False

    invented = _output(conclusions=[_conclusion(ids=("term-denim", "ghost-doc"))])
    assert evaluate(case, _input("explain"), invented).metrics["evidence_precision"]["score"] == 0.5

    partial = _output(conclusions=[_conclusion(ids=("term-cotton",))])
    assert evaluate(case, _input("explain"), partial).metrics["evidence_recall"]["score"] == 0.0

    bad_ref = _output(conclusions=[_conclusion(refs=("silk-denim",))])
    assert evaluate(case, _input("explain"), bad_ref).metrics["ffo_correctness"]["score"] == 0.0

    over_max = _by_id("max-fit-bounds")
    three = _output(conclusions=[_conclusion(), _conclusion(), _conclusion()])
    assert evaluate(over_max, _input("identify"), three).metrics["constraint_compliance"]["pass"] is False


def test_malformed_outputs_score_without_raising():
    case = _by_id("exp-denim-textile")
    result = evaluate(case, _input("explain"), {})
    assert result.passed is False
    assert result.metrics["grounding_accuracy"]["actual"] == "insufficient"
    stringy = evaluate(case, _input("explain"), "nope")
    assert stringy.passed is False


def test_deterministic_ordering():
    first = load_benchmark()
    second = load_benchmark()
    assert [c["case_id"] for c in first["cases"]] == [c["case_id"] for c in second["cases"]]
    case = _by_id("exp-denim-textile")
    perfect = _output(conclusions=[_conclusion()])
    assert evaluate(case, _input("explain"), perfect).to_dict() == evaluate(
        case, _input("explain"), perfect
    ).to_dict()


def test_evaluation_result_serialization():
    case = _by_id("exp-denim-textile")
    result = evaluate(case, _input("explain"), _output(conclusions=[_conclusion()]))
    body = result.to_dict()
    assert set(body) == {
        "case_id", "metrics", "passed", "benchmark_version",
        "ffo_version", "reasoning_contract_version",
    }
    assert set(body["metrics"]) == set(METRIC_NAMES)
    assert json.loads(json.dumps(body)) == body
    assert body["benchmark_version"] == "1.0"


def test_corpus_ffo_contract_version_preservation():
    case = _by_id("exp-denim-textile")
    result = evaluate(case, _input("explain"), _output(conclusions=[_conclusion()]))
    assert result.ffo_version == "1.0"
    assert result.reasoning_contract_version == REASONING_CONTRACT_VERSION
    assert result.metrics["version_preservation"]["pass"] is True
    tampered_versions = dict(VERSIONS, ffo_version="9.9")
    tampered_out = _output(conclusions=[_conclusion()])
    tampered_out["versions"] = tampered_versions
    assert evaluate(case, _input("explain"), tampered_out).metrics["version_preservation"]["pass"] is False
